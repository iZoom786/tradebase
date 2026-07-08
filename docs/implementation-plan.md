# Tradebase AI Platform - Phase-Wise Implementation Plan

**Version:** 1.0.0  
**Date:** July 2026  
**Strategy:** Loosely Coupled, Independently Testable, Docker-Based Deployment  

---

## Architecture Principles

### 1. **Loose Coupling Strategy**
- **Event-Driven Communication:** All modules communicate via NATS pub/sub, never direct calls
- **Interface Segregation:** Each module exposes well-defined interfaces/contracts
- **Dependency Injection:** All dependencies injected via configuration
- **Database Abstraction:** Repository pattern with pluggable data sources

### 2. **Scalability Approach**
- **Horizontal Ready:** All services stateless where possible
- **CQRS Pattern:** Separate read/write paths for optimal performance
- **Connection Pooling:** Efficient database/NATS connection management
- **Async Processing:** Non-blocking I/O throughout

### 3. **Observability & Traceability**
- **OpenTelemetry Integration:** Distributed tracing across all services
- **Structured Logging:** JSON logs with correlation IDs
- **Metrics Pipeline:** Prometheus + Grafana dashboards
- **Health Checks:** Readiness/Liveness probes for all services
- **Audit Trail:** Immutable logs for all trading decisions

### 4. **Reliability & Robustness**
- **Circuit Breakers:** Prevent cascade failures
- **Retry Policies:** Exponential backoff for transient failures
- **Dead Letter Queues:** Handle failed messages gracefully
- **Graceful Degradation:** Fallback modes when services degraded
- **Idempotency:** Safe retry for all operations

### 5. **Ultra-Fast Performance**
- **In-Memory Caching:** Redis for hot data
- **Columnar Storage:** TimescaleDB compression for time-series
- **Batch Processing:** Vectorized operations with NumPy/Pandas
- **Lazy Loading:** Only compute features on-demand
- **Connection Keep-Alive:** Persistent NATS connections

---

## Phase 1: Foundation & Infrastructure (Week 1-2)
**Complexity:** Easy | **Standalone:** ✅ Yes | **Dependencies:** None

### Objectives
- Establish project structure and tooling
- Docker development environment
- CI/CD pipeline foundation
- Observability scaffolding

### Components

#### 1.1 Project Structure
```
tradebase/
├── services/
│   ├── ingestion/         # Data ingestion service
│   ├── features/          # Feature calculation
│   ├── ml-engine/         # ML models & predictions
│   ├── paper-trading/     # Virtual trading engine
│   ├── subscription/      # Billing & access control
│   ├── api-gateway/       # FastAPI backend
│   └── dashboard/         # Web UI
├── libs/
│   ├── nats-client/       # NATS wrapper library
│   ├── db-repo/           # Database abstraction
│   ├── indicators/        # Technical indicators
│   └── common/            # Shared utilities
├── infrastructure/
│   ├── docker/            # Docker compose files
│   ├── nats/              # NATS config
│   ├── timescaledb/       # DB schemas & migrations
│   └── monitoring/        # Prometheus, Grafana, Jaeger
├── config/                # Environment-specific configs
├── tests/                 # Integration/E2E tests
└── docs/                  # Documentation
```

#### 1.2 Docker Foundation
**Files:**
- `docker-compose.yml` - Development environment
- `docker-compose.prod.yml` - Production overrides
- `Dockerfile.*` - Service-specific Dockerfiles

**Services:**
```yaml
services:
  timescaledb:
    image: timescale/timescaledb:latest
    environment:
      POSTGRES_DB: tradebase
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
      - ./infrastructure/timescaledb/init.sql:/docker-entrypoint-initdb.d/init.sql

  nats:
    image: nats:latest
    command: "--jetstream --config /etc/nats/nats.conf"
    volumes:
      - ./infrastructure/nats/nats.conf:/etc/nats/nats.conf
      - nats_data:/data

  redis:
    image: redis:latest
    
  prometheus:
    image: prom/prometheus
    
  grafana:
    image: grafana/grafana
    
  jaeger:
    image: jaegertracing/all-in-one
```

#### 1.3 Observability Scaffolding
**Lib: `libs/common/observability/`**

```python
# Tracing setup
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger import JaegerExporter

# Metrics setup  
from prometheus_client import Counter, Histogram, Gauge

# Structured logging
import structlog
logger = structlog.get_logger()
```

**Instrumentation:**
- Auto-instrument all HTTP calls
- NATS message tracing with correlation IDs
- Database query logging
- Custom business metrics

#### 1.4 Configuration Management
**Lib: `libs/common/config/`**

```python
from pydantic_settings import BaseSettings

class DatabaseConfig(BaseSettings):
    host: str
    port: int
    database: str
    pool_size: int = 20
    
class NATSConfig(BaseSettings):
    url: str
    max_reconnect: int = 10
    ping_interval: int = 60
    
class FeatureConfig(BaseSettings):
    enabled_indicators: list[str]
    cache_ttl_seconds: int = 300
```

**Environment Files:**
- `.env.example` - Template
- `.env.dev` - Development
- `.env.prod` - Production (git-ignored)

#### 1.5 CI/CD Foundation
**`.github/workflows/`**

```yaml
# ci.yml
- Run tests on PR
- Docker build validation
- Security scanning

# deploy.yml  
- Deploy on merge to main
- Deploy via Docker Compose on VPS
- Health check validation
```

### Deliverables
✅ Docker development environment operational  
✅ TimescaleDB & NATS containers running  
✅ Observability stack (Prometheus, Grafana, Jaeger) accessible  
✅ Project structure with empty service stubs  
✅ CI/CD pipeline running on GitHub  

### Validation Criteria
- `docker-compose up` brings all infrastructure online
- Prometheus scraping metrics from dummy service
- Jaeger receiving traces
- TimescaleDB accepting connections

---

## Phase 2: Database Layer & Schema (Week 2-3)
**Complexity:** Easy-Medium | **Standalone:** ✅ Yes | **Dependencies:** Phase 1

### Objectives
- TimescaleDB schema implementation
- Hypertable configuration
- Migration framework
- Repository pattern foundation

### Components

#### 2.1 Schema Implementation
**File: `infrastructure/timescaledb/init.sql`**

```sql
-- Market data hypertable
CREATE TABLE market_features (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    indicators JSONB,
    sentiment JSONB,
    PRIMARY KEY (time, symbol, interval)
);

-- Convert to hypertable
SELECT create_hypertable('market_features', 'time', 
    chunk_time_interval => INTERVAL '1 day');

-- Compression policy
SELECT add_compression_policy('market_features', 
    INTERVAL '7 days');

-- Retention policy (1 year rolling)
SELECT add_retention_policy('market_features', 
    INTERVAL '1 year');

-- Paper trading tables
CREATE TABLE paper_orders (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'LONG' or 'SHORT'
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ,
    entry_price DOUBLE PRECISION,
    exit_price DOUBLE PRECISION,
    quantity DOUBLE PRECISION,
    pnl DOUBLE PRECISION,
    status VARCHAR(20) DEFAULT 'OPEN'  -- 'OPEN', 'CLOSED'
);

CREATE INDEX idx_paper_orders_user ON paper_orders(user_id, status);

-- Trade log for all executed trades
CREATE TABLE trade_log (
    time TIMESTAMPTZ NOT NULL,
    order_id INTEGER REFERENCES paper_orders(id),
    symbol VARCHAR(20),
    action VARCHAR(20),  -- 'ENTRY', 'EXIT', 'MODIFY'
    price DOUBLE PRECISION,
    quantity DOUBLE PRECISION
);

-- Continuous aggregates for 1H and 4H
CREATE MATERIALIZED VIEW market_features_1h
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
GROUP BY bucket, symbol;

-- Refresh policy
SELECT add_continuous_aggregate_policy('market_features_1h',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 second',
    schedule_interval => INTERVAL '1 hour');
```

#### 2.2 Repository Pattern
**Lib: `libs/db-repo/`**

```python
# base.py
from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class MarketData:
    time: datetime
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    indicators: Optional[dict] = None
    sentiment: Optional[dict] = None

class Repository(ABC):
    @abstractmethod
    async def upsert(self, data: MarketData) -> None:
        pass
    
    @abstractmethod
    async def query_range(self, symbol: str, start: datetime, end: datetime) -> List[MarketData]:
        pass
    
    @abstractmethod
    async def get_latest(self, symbol: str, interval: str) -> Optional[MarketData]:
        pass

# timescaledb.py
import asyncpg
from asyncpg.pool import Pool

class TimescaleDBRepository(Repository):
    def __init__(self, config: DatabaseConfig):
        self.pool: Optional[Pool] = None
        self.config = config
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            min_size=5,
            max_size=self.config.pool_size
        )
    
    async def upsert(self, data: MarketData) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO market_features 
                (time, symbol, interval, open, high, low, close, volume, indicators, sentiment)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (time, symbol, interval)
                DO UPDATE SET 
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    indicators = EXCLUDED.indicators,
                    sentiment = EXCLUDED.sentiment
            """, data.time, data.symbol, data.interval, 
                data.open, data.high, data.low, data.close, 
                data.volume, data.indicators, data.sentiment)
    
    async def query_range(self, symbol: str, start: datetime, end: datetime) -> List[MarketData]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM market_features
                WHERE symbol = $1 AND time BETWEEN $2 AND $3
                ORDER BY time ASC
            """, symbol, start, end)
            return [MarketData(**dict(r)) for r in rows]
    
    async def get_latest(self, symbol: str, interval: str) -> Optional[MarketData]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM market_features
                WHERE symbol = $1 AND interval = $2
                ORDER BY time DESC LIMIT 1
            """, symbol, interval)
            return MarketData(**dict(row)) if row else None
```

#### 2.3 Migration Framework
**Lib: `libs/db-repo/migrations/`**

```python
# migrate.py
class MigrationRunner:
    def __init__(self, repo: TimescaleDBRepository):
        self.repo = repo
        self.migrations = []
    
    def register(self, version: int, name: str, up_fn, down_fn):
        self.migrations.append((version, name, up_fn, down_fn))
        self.migrations.sort(key=lambda x: x[0])
    
    async def run(self):
        for version, name, up_fn, _ in self.migrations:
            logger.info("migration_running", version=version, name=name)
            await up_fn(self.repo.pool)
```

### Deliverables
✅ TimescaleDB schema deployed  
✅ Hypertables configured with retention  
✅ Continuous aggregates operational  
✅ Repository pattern implemented with tests  
✅ Migration framework functional  

### Validation Criteria
- Can insert and query market data
- Hypertables automatically partitioning
- Continuous aggregates updating
- Connection pool handling concurrent requests

---

## Phase 3: Data Ingestion Engine (Week 3-4)
**Complexity:** Easy-Medium | **Standalone:** ✅ Yes | **Dependencies:** Phase 2

### Objectives
- YFinance integration
- MVC pattern for pluggable sources
- 1-minute candle fetching
- Historical backfill capability
- NATS publishing of raw data

### Components

#### 3.1 MVC Architecture for Data Sources
**Service: `services/ingestion/`**

```
ingestion/
├── models/
│   ├── market_data.py      # Data models
│   └── source_config.py    # Source configuration
├── views/
│   └── data_publisher.py    # NATS publishing interface
├── controllers/
│   ├── ingestion_controller.py  # Orchestration
│   └── scheduler.py         # Timer-based triggers
└── providers/
    ├── base.py              # Abstract provider
    ├── yfinance.py          # YFinance implementation
    ├── alpaca.py            # (Future) Alpaca implementation
    └── mt5.py               # (Future) MT5 implementation
```

#### 3.2 Base Provider Interface
**File: `services/ingestion/providers/base.py`**

```python
from abc import ABC, abstractmethod
from typing import List
from datetime import datetime

class DataProvider(ABC):
    """Abstract base for all market data providers"""
    
    @abstractmethod
    async def fetch_latest_candle(self, symbol: str) -> MarketData:
        """Get the most recent completed candle"""
        pass
    
    @abstractmethod
    async def fetch_historical(self, symbol: str, start: datetime, end: datetime) -> List[MarketData]:
        """Backfill historical data"""
        pass
    
    @abstractmethod
    async def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol is supported"""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass
```

#### 3.3 YFinance Provider
**File: `services/ingestion/providers/yfinance.py`**

```python
import yfinance as yf
from typing import List
from datetime import datetime, timedelta

class YFinanceProvider(DataProvider):
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.tickers = {s: yf.Ticker(s) for s in symbols}
    
    @property
    def provider_name(self) -> str:
        return "yfinance"
    
    async def fetch_latest_candle(self, symbol: str) -> MarketData:
        ticker = self.tickers[symbol]
        
        # Fetch last 2 minutes to get the completed candle
        data = ticker.history(period="1d", interval="1m")
        
        if len(data) < 2:
            raise ValueError(f"Insufficient data for {symbol}")
        
        # Get the second-to-last (completed) candle
        latest = data.iloc[-2]
        
        return MarketData(
            time=datetime.fromtimestamp(latest.name.timestamp()),
            symbol=symbol,
            interval="1m",
            open=float(latest['Open']),
            high=float(latest['High']),
            low=float(latest['Low']),
            close=float(latest['Close']),
            volume=int(latest['Volume'])
        )
    
    async def fetch_historical(self, symbol: str, start: datetime, end: datetime) -> List[MarketData]:
        ticker = self.tickers[symbol]
        
        data = ticker.history(
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            interval="1m"
        )
        
        candles = []
        for timestamp, row in data.iterrows():
            candles.append(MarketData(
                time=datetime.fromtimestamp(timestamp.timestamp()),
                symbol=symbol,
                interval="1m",
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close']),
                volume=int(row['Volume'])
            ))
        
        return candles
    
    async def validate_symbol(self, symbol: str) -> bool:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return bool(info.get('regularMarketPrice'))
        except:
            return False
```

#### 3.4 Ingestion Controller
**File: `services/ingestion/controllers/ingestion_controller.py`**

```python
import asyncio
from structlog import get_logger
from opentelemetry import trace

logger = get_logger()
tracer = trace.get_tracer(__name__)

class IngestionController:
    def __init__(
        self,
        provider: DataProvider,
        repository: Repository,
        publisher: 'DataPublisher'
    ):
        self.provider = provider
        self.repository = repository
        self.publisher = publisher
        self._running = False
    
    async def ingest_latest(self, symbol: str) -> None:
        """Fetch and publish the latest completed candle"""
        with tracer.start_as_current_span("ingest_latest") as span:
            span.set_attribute("symbol", symbol)
            
            try:
                # Fetch from provider
                candle = await self.provider.fetch_latest_candle(symbol)
                logger.info("candle_fetched", symbol=symbol, time=candle.time)
                
                # Store in database
                await self.repository.upsert(candle)
                
                # Publish to NATS
                await self.publisher.publish_raw(candle)
                
                logger.info("candle_published", symbol=symbol, time=candle.time)
                span.set_attribute("success", True)
                
            except Exception as e:
                logger.error("ingestion_failed", symbol=symbol, error=str(e))
                span.set_attribute("error", str(e))
                span.set_attribute("success", False)
                raise
    
    async def backfill_historical(self, symbol: str, days: int = 365) -> None:
        """Backfill historical data"""
        with tracer.start_as_current_span("backfill_historical") as span:
            end = datetime.now()
            start = end - timedelta(days=days)
            
            logger.info("backfill_start", symbol=symbol, start=start, end=end)
            
            candles = await self.provider.fetch_historical(symbol, start, end)
            
            for candle in candles:
                await self.repository.upsert(candle)
            
            logger.info("backfill_complete", symbol=symbol, count=len(candles))
    
    async def run(self, symbols: List[str]) -> None:
        """Continuous ingestion loop"""
        self._running = True
        
        while self._running:
            tasks = [self.ingest_latest(s) for s in symbols]
            
            # Fetch all symbols concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successes = sum(1 for r in results if not isinstance(r, Exception))
            logger.info("batch_complete", successes=successes, total=len(symbols))
            
            # Wait for next minute
            await asyncio.sleep(60 - datetime.now().second)
```

#### 3.5 Data Publisher (View)
**File: `services/ingestion/views/data_publisher.py`**

```python
import json
from nats.aio.client import Client as NATS

class DataPublisher:
    def __init__(self, nats_client: NATS):
        self.nc = nats_client
    
    async def publish_raw(self, data: MarketData) -> None:
        """Publish raw OHLCV data"""
        subject = f"tradebase.{self._get_asset_class(data.symbol)}.{data.symbol.lower()}.raw.{data.interval.lower()}"
        
        payload = {
            "timestamp": data.time.isoformat(),
            "symbol": data.symbol,
            "interval": data.interval,
            "open": data.open,
            "high": data.high,
            "low": data.low,
            "close": data.close,
            "volume": data.volume
        }
        
        await self.nc.publish(subject, json.dumps(payload).encode())
        logger.info("published_raw", subject=subject, time=data.time)
    
    def _get_asset_class(self, symbol: str) -> str:
        # Simple heuristic
        if len(symbol) == 6 and symbol[:3].isalpha():
            return "forex"
        return "other"
```

#### 3.6 Scheduler
**File: `services/ingestion/controllers/scheduler.py`**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class IngestionScheduler:
    def __init__(self, controller: IngestionController):
        self.scheduler = AsyncIOScheduler()
        self.controller = controller
    
    def start(self, symbols: List[str]) -> None:
        # Run every minute at second 5
        self.scheduler.add_job(
            self._run_all,
            'cron',
            second='5',
            args=[symbols]
        )
        self.scheduler.start()
        logger.info("scheduler_started", symbols=symbols)
    
    async def _run_all(self, symbols: List[str]) -> None:
        for symbol in symbols:
            await self.controller.ingest_latest(symbol)
```

### Deliverables
✅ YFinance provider implemented  
✅ MVC pattern established for pluggable sources  
✅ Historical backfill functional  
✅ Real-time minute-by-minute ingestion  
✅ NATS publishing of raw candles  
✅ Comprehensive metrics and tracing  

### Validation Criteria
- Can backfill 1 year of EURUSD data
- Real-time ingestion running <100ms from candle close
- NATS messages flowing to raw subjects
- Idempotent (re-running doesn't create duplicates)

---

## Phase 4: NATS Messaging & Security Core (Week 4-5)
**Complexity:** Medium | **Standalone:** ✅ Yes | **Dependencies:** Phase 1

### Objectives
- Complete NATS infrastructure
- JWT + NKey authentication
- Subject namespace enforcement
- Connection management library

### Components

#### 4.1 NATS Configuration
**File: `infrastructure/nats/nats.conf`**

```nginx
# NATS Server Configuration

host: "0.0.0.0"
port: 4222
monitor_port: 8222

# JetStream enabled
jetstream {
    store_dir: /data/jetstream
    max_memory: 1GB
    max_file: 10GB
}

# Logging
log_file: /var/log/nats.log
log_time: true
debug: false
trace: false

# Security
authorization {
    # Use custom resolver for JWT
    timeout: 2s
    
    # Default deny all
    default_permissions = {
        publish: "deny"
        subscribe: "deny"
    }
}

# TLS (production)
tls {
    cert_file: "/etc/nats/certs/server.crt"
    key_file: "/etc/nats/certs/server.key"
    ca_file: "/etc/nats/certs/ca.crt"
    verify: true
}

# Cluster configuration (for HA)
cluster {
    name: "tradebase_cluster"
    listen: 0.0.0.0:6222
    routes: [
        nats://nats-2:6222
        nats://nats-3:6222
    ]
}

# Leaf nodes for multi-region
leafnodes {
    listen: 0.0.0.0:7422
}
```

#### 4.2 JWT/NKey Authentication System
**Lib: `libs/nats-client/auth/`**

```python
# nkey_manager.py
import nkeys
from typing import Tuple

class NKeyManager:
    """Manage NKey pairs for JWT signing"""
    
    @staticmethod
    def generate_user_keypair() -> Tuple[str, str]:
        """Generate (seed, public_key) for a user"""
        kp = nkeys.from_seed(nkeys.create_pair(nkeys.KeyType.USER))  # Creates User keypair
        seed = kp.seed
        public_key = kp.public_key
        return seed.decode(), public_key.decode()
    
    @staticmethod
    def sign_challenge(seed: str, challenge: bytes) -> bytes:
        """Sign a nonce with private key"""
        kp = nkeys.from_seed(seed.encode())
        return kp.sign(challenge)
    
    @staticmethod
    def verify_signature(public_key: str, signature: bytes, challenge: bytes) -> bool:
        """Verify a signature"""
        kp = nkeys.from_public_key(public_key.encode())
        return kp.verify(challenge, signature)

# jwt_manager.py
import jwt
from datetime import datetime, timedelta
from typing import Dict, List

class NATSJWTManager:
    """Generate and validate NATS JWTs"""
    
    def __init__(self, issuer_keypair_seed: str):
        self.issuer_seed = issuer_keypair_seed
    
    def generate_user_jwt(
        self,
        user_id: str,
        tier: str,  # 'basic', 'premium', 'trial'
        expires_hours: int = 24
    ) -> str:
        """Generate a JWT with permissions based on tier"""
        
        now = int(datetime.now().timestamp())
        exp = now + (expires_hours * 3600)
        
        # Define permissions based on tier
        permissions = self._get_permissions_for_tier(tier)
        
        payload = {
            "jti": f"user_{user_id}_{now}",
            "iat": now,
            "exp": exp,
            "iss": "TRADEBASE",  # Issuer
            "sub": user_id,
            "nats": {
                "pub": permissions["publish"],
                "sub": permissions["subscribe"],
                "sub_allowations": permissions.get("sub_allowations", [])
            },
            "tier": tier
        }
        
        # Sign with issuer NKey
        kp = nkeys.from_seed(self.issuer_seed.encode())
        header = {"alg": "ed25519", "typ": "JWT"}
        
        return jwt.encode(payload, kp, algorithm="Ed25519", headers=header)
    
    def _get_permissions_for_tier(self, tier: str) -> Dict:
        """Define subject permissions by tier"""
        
        if tier == "basic":
            return {
                "publish": {"deny": [">"]},  # No publish
                "subscribe": {
                    "allow": [
                        "tradebase.forex.*.raw.1m",
                        "tradebase.crypto.*.raw.1m"
                    ]
                }
            }
        elif tier == "premium":
            return {
                "publish": {"deny": [">"]},
                "subscribe": {
                    "allow": [
                        "tradebase.*. Prediction.*",
                        "tradebase.*.raw.1m",
                        "tradebase.*.indicators.1m"
                    ]
                }
            }
        elif tier == "trial":
            return {
                "publish": {"deny": [">"]},
                "subscribe": {
                    "allow": [
                        "tradebase.public.papertrading.*"
                    ]
                }
            }
        else:
            return {"publish": {"deny": [">"]}, "subscribe": {"deny": [">"]}}
```

#### 4.3 NATS Client Library
**Lib: `libs/nats-client/client.py`**

```python
from nats.aio.client import Client as NATS
from nats.errors import TimeoutError
import asyncio
from typing import Optional, Callable
from opentelemetry import trace

class NATSClient:
    """High-level NATS client with reconnection and tracing"""
    
    def __init__(self, config: NATSConfig, user_jwt: Optional[str] = None, user_seed: Optional[str] = None):
        self.config = config
        self.nc = NATS()
        self.user_jwt = user_jwt
        self.user_seed = user_seed
        self._connected = False
        self.tracer = trace.get_tracer(__name__)
    
    async def connect(self) -> None:
        """Connect with JWT/NKey authentication"""
        with self.tracer.start_as_current_span("nats_connect"):
            if self.user_jwt and self.user_seed:
                # JWT user authentication
                await self.nc.connect(
                    servers=[self.config.url],
                    user_jwt=self.user_jwt,
                    signature_cb=self._sign_nonce,
                    max_reconnect_attempts=self.config.max_reconnect,
                    ping_interval=self.config.ping_interval,
                    disconnected_cb=self._on_disconnect,
                    reconnected_cb=self._on_reconnect,
                    error_cb=self._on_error
                )
            else:
                # Internal system connection
                await self.nc.connect(
                    servers=[self.config.url],
                    max_reconnect_attempts=self.config.max_reconnect
                )
            
            self._connected = True
            logger.info("nats_connected", url=self.config.url)
    
    def _sign_nonce(self, nonce: str) -> bytes:
        """Sign server challenge with NKey"""
        return NKeyManager.sign_challenge(self.user_seed, nonce.encode())
    
    async def publish(self, subject: str, payload: bytes) -> None:
        """Publish with tracing"""
        with self.tracer.start_as_current_span("nats_publish") as span:
            span.set_attribute("subject", subject)
            await self.nc.publish(subject, payload)
            logger.debug("published", subject=subject)
    
    async def subscribe(
        self,
        subject: str,
        handler: Callable,
        queue_name: Optional[str] = None
    ) -> None:
        """Subscribe with automatic tracing"""
        
        async def wrapper(msg):
            with self.tracer.start_as_current_span("nats_message") as span:
                span.set_attribute("subject", msg.subject)
                span.set_attribute("reply", msg.reply or "")
                await handler(msg)
        
        if queue_name:
            await self.nc.subscribe(subject, queue_name, cb=wrapper)
        else:
            await self.nc.subscribe(subject, cb=wrapper)
        
        logger.info("subscribed", subject=subject, queue=queue_name)
    
    def _on_disconnect(self):
        logger.warning("nats_disconnected")
    
    def _on_reconnect(self):
        logger.info("nats_reconnected")
    
    def _on_error(self, error):
        logger.error("nats_error", error=str(error))
    
    async def close(self):
        await self.nc.close()
        self._connected = False
```

#### 4.4 Account Server
**Service: `services/subscription/account_server.py`**

```python
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

app = FastAPI(title="Tradebase Account Server")

class SubscriptionRequest(BaseModel):
    user_id: str
    tier: str  # 'basic', 'premium'
    duration_hours: int = 720  # 30 days default

class SubscriptionResponse(BaseModel):
    user_jwt: str
    nkey_seed: str
    public_key: str
    expires_at: datetime

@app.post("/subscribe", response_model=SubscriptionResponse)
async def create_subscription(req: SubscriptionRequest):
    """Provision JWT for a new subscriber"""
    
    # Generate user NKey pair
    seed, public_key = NKeyManager.generate_user_keypair()
    
    # Generate JWT with tier-based permissions
    jwt_manager = NATSJWTManager(issuer_seed=ISSUER_SEED)
    user_jwt = jwt_manager.generate_user_jwt(
        user_id=req.user_id,
        tier=req.tier,
        expires_hours=req.duration_hours
    )
    
    # Store in database
    await db.store_subscription(
        user_id=req.user_id,
        public_key=public_key,
        tier=req.tier,
        expires_at=datetime.now() + timedelta(hours=req.duration_hours)
    )
    
    return SubscriptionResponse(
        user_jwt=user_jwt,
        nkey_seed=seed,
        public_key=public_key,
        expires_at=datetime.now() + timedelta(hours=req.duration_hours)
    )

@app.post("/validate")
async def validate_jwt(token: str = Depends(oauth2_scheme)):
    """Validate a JWT (called by NATS resolver)"""
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return {"valid": True, "tier": payload.get("tier")}
    except:
        return {"valid": False}
```

### Deliverables
✅ NATS server configured with JetStream  
✅ JWT authentication operational  
✅ NKey signing implemented  
✅ Tier-based subject permissioning  
✅ Account server for JWT provisioning  
✅ NATS client library with reconnection  

### Validation Criteria
- Cannot subscribe without valid JWT
- Basic tier cannot access prediction subjects
- Premium tier can access all data
- Reconnection on network failure
- Tracing spans for all messages

---

## Phase 5: Feature Calculation Pipeline (Week 5-6)
**Complexity:** Medium | **Standalone:** ✅ Yes | **Dependencies:** Phase 2, 3, 4

### Objectives
- Technical indicators (RSI, Elder Ray, MACD, etc.)
- Sentiment scoring
- Feature computation engine
- NATS publishing of features
- Performance optimization

### Components

#### 5.1 Indicators Library
**Lib: `libs/indicators/`**

```python
# base.py
from abc import ABC, abstractmethod
from typing import List
import numpy as np
import pandas as pd

class Indicator(ABC):
    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.Series:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

# rsi.py
class RSI(Indicator):
    def __init__(self, period: int = 14):
        self.period = period
    
    @property
    def name(self) -> str:
        return f"rsi_{self.period}"
    
    def compute(self, df: pd.DataFrame) -> pd.Series:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

# elder_ray.py
class ElderRay(Indicator):
    """Elder Ray Index - Bull Power and Bear Power"""
    
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        ema13 = df['close'].ewm(span=13, adjust=False).mean()
        
        bull_power = df['high'] - ema13
        bear_power = df['low'] - ema13
        
        return pd.DataFrame({
            'elder_bull': bull_power,
            'elder_bear': bear_power,
            'elder_impulse': self._impulse(df, bull_power, bear_power)
        })
    
    def _impulse(self, df, bull, bear):
        """Elder Impulse System: 1=Buy, -1=Sell, 0=Neutral"""
        # MACD Histogram
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        macd_hist = (ema12 - ema26) - df['close'].ewm(span=9).mean()
        
        # Signal combination
        signal = pd.Series(0, index=df.index)
        
        # Buy when MACD hist > 0 and bull > 0
        signal[(macd_hist > 0) & (bull > 0)] = 1
        
        # Sell when MACD hist < 0 and bear < 0
        signal[(macd_hist < 0) & (bear < 0)] = -1
        
        return signal

# bollinger.py
class BollingerBands(Indicator):
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev
    
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        sma = df['close'].rolling(window=self.period).mean()
        std = df['close'].rolling(window=self.period).std()
        
        upper = sma + (std * self.std_dev)
        lower = sma - (std * self.std_dev)
        
        # %B position within bands
        percent_b = (df['close'] - lower) / (upper - lower)
        
        return pd.DataFrame({
            'bb_upper': upper,
            'bb_middle': sma,
            'bb_lower': lower,
            'bb_percent_b': percent_b
        })

# atr.py
class ATR(Indicator):
    """Average True Range for volatility"""
    
    def __init__(self, period: int = 14):
        self.period = period
    
    def compute(self, df: pd.DataFrame) -> pd.Series:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=self.period).mean()
        
        return atr
```

#### 5.2 Sentiment Engine
**Lib: `libs/indicators/sentiment.py`**

```python
from typing import Dict, Optional
from datetime import datetime, timedelta
import numpy as np

class SentimentEngine:
    """
    Time-decayed sentiment scoring
    Combine multiple signals with exponential decay
    """
    
    def __init__(self, hourly_decay: float = 0.95, weekly_decay: float = 0.7):
        self.hourly_decay = hourly_decay
        self.weekly_decay = weekly_decay
    
    def calculate_hourly_sentiment(
        self,
        price_momentum: float,      # Current price vs 1h ago
        volume_surge: float,        # Volume vs avg
        rsi_strength: float,        # RSI normalized to -1 to 1
        macd_signal: float          # MACD histogram
    ) -> float:
        """Calculate sentiment score [-1, 1] for hourly timeframe"""
        
        # Normalize inputs to -1 to 1 range
        norm_momentum = np.tanh(price_momentum * 10)
        norm_volume = np.tanh((volume_surge - 1) * 2)
        norm_rsi = (rsi_strength - 50) / 50  # RSI 0-100 -> -1 to 1
        norm_macd = np.tanh(macd_signal)
        
        # Weighted combination
        score = (
            norm_momentum * 0.3 +
            norm_volume * 0.2 +
            norm_rsi * 0.3 +
            norm_macd * 0.2
        )
        
        # Clamp to [-1, 1]
        return np.clip(score, -1, 1)
    
    def calculate_weekly_sentiment(
        self,
        daily_returns: pd.Series,
        volatility: pd.Series,
        trend_strength: float
    ) -> float:
        """Calculate sentiment for weekly timeframe"""
        
        # Exponential weighted sentiment
        weights = np.exp(-np.arange(len(daily_returns)) / 7)
        weights = weights / weights.sum()
        
        weighted_sentiment = np.sum(daily_returns.values * weights)
        
        # Adjust for volatility (high vol = reduce confidence)
        vol_adjusted = weighted_sentiment / (1 + volatility.std())
        
        return np.clip(vol_adjusted, -1, 1)
```

#### 5.3 Feature Computation Engine
**Service: `services/features/engine.py`**

```python
import pandas as pd
from typing import Dict, List, Optional
from collections import defaultdict

class FeatureEngine:
    """
    Orchestrate indicator calculations
    Cache results for efficiency
    """
    
    def __init__(self, repository: Repository, config: FeatureConfig):
        self.repo = repository
        self.config = config
        self.indicators = self._init_indicators()
        self.sentiment = SentimentEngine()
        self._cache = defaultdict(dict)
    
    def _init_indicators(self) -> Dict[str, Indicator]:
        """Initialize configured indicators"""
        return {
            'rsi': RSI(period=15),
            'rsi_1h': RSI(period=15),
            'elder': ElderRay(),
            'bb': BollingerBands(),
            'atr': ATR()
        }
    
    async def compute_features(
        self,
        symbol: str,
        interval: str = "1m",
        lookback_bars: int = 100
    ) -> Dict:
        """
        Compute all features for a symbol
        Returns dict with latest values
        """
        
        # Check cache first
        cache_key = f"{symbol}_{interval}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self.config.cache_ttl):
                return cached_data
        
        # Fetch historical data for context
        end = datetime.now()
        start = end - timedelta(minutes=lookback_bars)
        
        historical = await self.repo.query_range(symbol, start, end)
        
        if len(historical) < lookback_bars:
            logger.warning("insufficient_data", symbol=symbol, count=len(historical))
            return {}
        
        # Convert to DataFrame for vectorized operations
        df = pd.DataFrame([{
            'time': h.time,
            'open': h.open,
            'high': h.high,
            'low': h.low,
            'close': h.close,
            'volume': h.volume
        } for h in historical])
        
        df = df.set_index('time')
        
        # Compute indicators
        features = {}
        
        # RSI
        rsi_15m = self.indicators['rsi'].compute(df)
        features['rsi_15m'] = float(rsi_15m.iloc[-1])
        
        # Elder Ray
        elder = self.indicators['elder'].compute(df)
        features['elder_impulse_1m'] = int(elder['elder_impulse'].iloc[-1])
        features['elder_bull'] = float(elder['elder_bull'].iloc[-1])
        features['elder_bear'] = float(elder['elder_bear'].iloc[-1])
        
        # Bollinger Bands
        bb = self.indicators['bb'].compute(df)
        features['bb_percent_b'] = float(bb['bb_percent_b'].iloc[-1])
        
        # ATR
        atr = self.indicators['atr'].compute(df)
        features['atr'] = float(atr.iloc[-1])
        
        # Sentiment
        hourly_sent = self.sentiment.calculate_hourly_sentiment(
            price_momentum=self._calc_momentum(df, 60),
            volume_surge=df['volume'].iloc[-60:].mean() / df['volume'].mean(),
            rsi_strength=features['rsi_15m'],
            macd_signal=self._calc_macd_hist(df)
        )
        features['sentiment_hourly'] = hourly_sent
        
        weekly_sent = self.sentiment.calculate_weekly_sentiment(
            daily_returns=df['close'].pct_change(),
            volatility=df['close'].pct_change().rolling(20).std(),
            trend_strength=0.5
        )
        features['sentiment_weekly'] = weekly_sent
        
        # Cache with timestamp
        self._cache[cache_key] = (datetime.now(), features)
        
        return features
    
    def _calc_momentum(self, df: pd.DataFrame, periods: int) -> float:
        """Calculate price momentum"""
        return (df['close'].iloc[-1] - df['close'].iloc[-periods]) / df['close'].iloc[-periods]
    
    def _calc_macd_hist(self, df: pd.DataFrame) -> float:
        """Calculate MACD histogram value"""
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        return macd.iloc[-1] - signal.iloc[-1]
```

#### 5.4 Feature Publisher
**Service: `services/features/publisher.py`**

```python
class FeaturePublisher:
    """Publish computed features to NATS"""
    
    def __init__(self, nats_client: NATSClient):
        self.nc = nats_client
    
    async def publish_features(
        self,
        symbol: str,
        interval: str,
        features: Dict,
        timestamp: datetime
    ) -> None:
        """Publish enriched data with features"""
        
        subject = f"tradebase.forex.{symbol.lower()}.features.{interval.lower()}"
        
        payload = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "interval": interval,
            "features": features
        }
        
        await self.nc.publish(subject, json.dumps(payload).encode())
        logger.info("features_published", symbol=symbol, feature_count=len(features))
```

### Deliverables
✅ Complete indicator library  
✅ Sentiment calculation engine  
✅ Feature computation with caching  
✅ NATS publishing of features  
✅ Performance optimizations  

### Validation Criteria
- All indicators computing correctly
- Cached results returning within 5ms
- Feature payloads flowing to NATS
- Computations complete within 50ms per symbol

---

## Phase 6: Machine Learning Engine (Week 6-8)
**Complexity:** Medium-Hard | **Standalone:** ✅ Yes | **Dependencies:** Phase 5

### Objectives
- Data preparation for ML
- Weka J48 integration
- XGBoost models
- Training pipeline
- Prediction generation
- Model versioning

### Components

#### 6.1 Feature Store
**Lib: `libs/ml/feature_store.py`**

```python
import pandas as pd
from typing import List, Dict
from datetime import datetime, timedelta

class MLFeatureStore:
    """
    Prepare features for ML training/inference
    Handle sliding windows and label generation
    """
    
    def __init__(self, repository: Repository):
        self.repo = repository
    
    async def get_training_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        feature_columns: List[str],
        label_horizon_minutes: int = 5
    ) -> pd.DataFrame:
        """
        Get dataset with features and future labels
        """
        
        # Fetch extended range for label generation
        data_end = end + timedelta(minutes=label_horizon_minutes + 1)
        data = await self.repo.query_range(symbol, start, data_end)
        
        # Convert to DataFrame
        df = pd.DataFrame([self._flatten_row(d) for d in data])
        
        # Calculate future return as label
        df['future_return'] = df['close'].shift(-label_horizon_minutes) / df['close'] - 1
        df['direction'] = (df['future_return'] > 0).astype(int)
        
        # Drop rows without labels
        df = df[df['future_return'].notna()]
        
        # Select feature columns
        X = df[feature_columns]
        y = df['direction']
        
        return X, y
    
    def _flatten_row(self, market_data: MarketData) -> Dict:
        """Flatten nested structure for ML"""
        row = {
            'time': market_data.time,
            'open': market_data.open,
            'high': market_data.high,
            'low': market_data.low,
            'close': market_data.close,
            'volume': market_data.volume
        }
        
        if market_data.indicators:
            row.update(market_data.indicators)
        
        if market_data.sentiment:
            row.update({f"sent_{k}": v for k, v in market_data.sentiment.items()})
        
        return row
```

#### 6.2 Weka Integration
**Service: `services/ml-engine/weka_model.py`**

```python
import subprocess
import json
from typing import List, Dict
import pandas as pd

class WekaJ48Model:
    """
    J48 Decision Tree via Weka
    Best for interpretable trading rules
    """
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model_trained = False
    
    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        confidence_factor: float = 0.25,
        min_leaf_objects: int = 2
    ) -> Dict:
        """
        Train J48 decision tree
        
        Args:
            X: Feature DataFrame
            y: Binary labels (0/1)
            confidence_factor: Pruning confidence (lower = less pruning)
            min_leaf_objects: Minimum instances per leaf
        """
        
        # Combine X and y for Weka ARFF format
        df = X.copy()
        df['label'] = y
        
        # Convert to ARFF
        arff_path = self._to_arff(df, f"{self.model_path}.arff")
        
        # Run Weka training
        cmd = [
            "java", "-cp", "/path/to/weka.jar",
            "weka.classifiers.trees.J48",
            f"-C {confidence_factor}",
            f"-M {min_leaf_objects}",
            f"-t {arff_path}",
            f"-d {self.model_path}.model"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Weka training failed: {result.stderr}")
        
        # Parse output for metrics
        metrics = self._parse_weka_output(result.stdout)
        
        self.model_trained = True
        logger.info("j48_trained", metrics=metrics)
        
        return metrics
    
    def predict(self, features: Dict) -> tuple[int, float]:
        """
        Predict direction and probability
        
        Returns:
            (direction: 0/1, probability: float)
        """
        if not self.model_trained:
            raise ValueError("Model not trained")
        
        # Create single instance ARFF
        # Run Weka prediction
        # Parse result
        
        # Simplified (actual implementation needs Weka integration)
        # Return (direction, probability)
        return 1, 0.75
    
    def _to_arff(self, df: pd.DataFrame, path: str) -> str:
        """Convert DataFrame to Weka ARFF format"""
        with open(path, 'w') as f:
            f.write("@RELATION tradebase\n\n")
            
            # Attributes
            for col in df.columns[:-1]:
                f.write(f"@ATTRIBUTE {col} NUMERIC\n")
            f.write("@ATTRIBUTE label {0,1}\n\n")
            f.write("@DATA\n")
            
            # Data rows
            for _, row in df.iterrows():
                values = ','.join(str(v) for v in row.values)
                f.write(values + "\n")
        
        return path
    
    def _parse_weka_output(self, output: str) -> Dict:
        """Extract metrics from Weka stdout"""
        # Parse accuracy, kappa, etc.
        return {"accuracy": 0.85, "tree_size": 42}
```

#### 6.3 XGBoost Model
**Service: `services/ml-engine/xgb_model.py`**

```python
import xgboost as xgb
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, log_loss
import joblib
from datetime import datetime

class XGBoostClassifier:
    """
    XGBoost for prediction accuracy
    Better performance than J48, less interpretable
    """
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.feature_names = None
    
    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        early_stopping_rounds: int = 50
    ) -> Dict:
        """Train XGBoost classifier"""
        
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=test_size, shuffle=False
        )
        
        self.feature_names = X.columns.tolist()
        
        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=self.feature_names)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=self.feature_names)
        
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'logloss',
            'max_depth': 6,
            'eta': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'tree_method': 'hist'  # Faster training
        }
        
        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=1000,
            evals=[(dtrain, 'train'), (dval, 'val')],
            early_stopping_rounds=early_stopping_rounds,
            verbose_eval=False
        )
        
        # Calculate metrics
        val_pred = self.model.predict(dval)
        accuracy = accuracy_score(y_val, (val_pred > 0.5).astype(int))
        logloss = log_loss(y_val, val_pred)
        
        metrics = {
            'accuracy': accuracy,
            'log_loss': logloss,
            'best_iteration': self.model.best_iteration
        }
        
        # Save model
        self._save()
        
        logger.info("xgb_trained", metrics=metrics)
        return metrics
    
    def predict(self, features: Dict) -> tuple[int, float]:
        """Predict direction and probability"""
        if self.model is None:
            self._load()
        
        # Convert dict to array in correct feature order
        X = np.array([features.get(f, 0) for f in self.feature_names])
        dmatrix = xgb.DMatrix(X, feature_names=self.feature_names)
        
        probability = float(self.model.predict(dmatrix)[0])
        direction = 1 if probability > 0.5 else 0
        
        return direction, probability
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores"""
        if self.model is None:
            self._load()
        
        importance = self.model.get_score(importance_type='gain')
        
        # Normalize to sum to 1
        total = sum(importance.values())
        return {k: v/total for k, v in importance.items()}
    
    def _save(self):
        """Save model to disk"""
        model_data = {
            'model': self.model,
            'feature_names': self.feature_names,
            'trained_at': datetime.now().isoformat()
        }
        joblib.dump(model_data, self.model_path)
    
    def _load(self):
        """Load model from disk"""
        model_data = joblib.load(self.model_path)
        self.model = model_data['model']
        self.feature_names = model_data['feature_names']
```

#### 6.4 Training Pipeline
**Service: `services/ml-engine/training.py`**

```python
class MLTrainingPipeline:
    """
    Orchestrates model training and validation
    Runs weekend retraining automatically
    """
    
    def __init__(
        self,
        feature_store: MLFeatureStore,
        j48_model: WekaJ48Model,
        xgb_model: XGBoostClassifier,
        repository: Repository
    ):
        self.feature_store = feature_store
        self.j48 = j48_model
        self.xgb = xgb_model
        self.repo = repository
    
    async def run_weekend_retraining(self, symbols: List[str]) -> Dict:
        """
        Perform rolling walk-forward validation
        Train on last 6 months, validate on 1 month
        """
        
        results = {}
        
        for symbol in symbols:
            logger.info("retraining_start", symbol=symbol)
            
            # Get 7 months data
            end = datetime.now()
            start = end - timedelta(days=210)
            
            X, y = await self.feature_store.get_training_data(
                symbol, start, end,
                feature_columns=self.feature_store.feature_columns
            )
            
            # Walk-forward: train on 6 months, validate on 1 month
            split_idx = int(len(X) * 0.85)
            X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
            y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]
            
            # Train J48
            j48_metrics = self.j48.train(X_train, y_train)
            
            # Train XGBoost
            xgb_metrics = self.xgb.train(X_train, y_train)
            
            # Validate
            val_j48 = self._validate(self.j48, X_val, y_val)
            val_xgb = self._validate(self.xgb, X_val, y_val)
            
            results[symbol] = {
                'j48': {**j48_metrics, 'validation': val_j48},
                'xgb': {**xgb_metrics, 'validation': val_xgb}
            }
            
            logger.info("retraining_complete", symbol=symbol, results=results[symbol])
        
        return results
    
    def _validate(self, model, X: pd.DataFrame, y: pd.Series) -> Dict:
        """Calculate validation metrics"""
        predictions = []
        probabilities = []
        
        for _, row in X.iterrows():
            direction, prob = model.predict(row.to_dict())
            predictions.append(direction)
            probabilities.append(prob)
        
        accuracy = accuracy_score(y, predictions)
        logloss = log_loss(y, probabilities)
        
        return {'accuracy': accuracy, 'log_loss': logloss}
```

#### 6.5 Prediction Service
**Service: `services/ml-engine/prediction.py`**

```python
class PredictionService:
    """
    Generate real-time predictions
    Ensemble multiple models
    """
    
    def __init__(
        self,
        j48_model: WekaJ48Model,
        xgb_model: XGBoostClassifier,
        nats_client: NATSClient
    ):
        self.j48 = j48_model
        self.xgb = xgb_model
        self.nc = nats_client
    
    async def generate_prediction(
        self,
        symbol: str,
        features: Dict,
        timestamp: datetime
    ) -> Dict:
        """Generate ensemble prediction"""
        
        # Get predictions from both models
        j48_dir, j48_prob = self.j48.predict(features)
        xgb_dir, xgb_prob = self.xgb.predict(features)
        
        # Weighted ensemble (XGBoost weighted higher)
        ensemble_prob = (j48_prob * 0.3 + xgb_prob * 0.7)
        ensemble_dir = 1 if ensemble_prob > 0.5 else 0
        
        prediction = {
            'direction': 'UP' if ensemble_dir == 1 else 'DOWN',
            'probability': ensemble_prob,
            'model_votes': {
                'j48': {'direction': j48_dir, 'probability': j48_prob},
                'xgb': {'direction': xgb_dir, 'probability': xgb_prob}
            }
        }
        
        # Publish to NATS
        subject = f"tradebase.forex.{symbol.lower()}.prediction.1m"
        payload = {
            'timestamp': timestamp.isoformat(),
            'symbol': symbol,
            'prediction': prediction
        }
        
        await self.nc.publish(subject, json.dumps(payload).encode())
        
        logger.info("prediction_generated", 
                   symbol=symbol, direction=prediction['direction'], 
                   probability=prediction['probability'])
        
        return prediction
```

### Deliverables
✅ Feature store for ML preparation  
✅ J48 decision tree model  
✅ XGBoost gradient boosting model  
✅ Automated training pipeline  
✅ Ensemble prediction service  
✅ Model versioning and persistence  

### Validation Criteria
- Models train within 10 minutes
- Validation accuracy > 60%
- Predictions generated within 20ms
- Models handle missing features gracefully

---

## Phase 7: Paper Trading System (Week 8-9)
**Complexity:** Medium | **Standalone:** ✅ Yes | **Dependencies:** Phase 5, 6

### Objectives
- Virtual account management
- Order simulation
- P&L tracking
- Performance metrics
- Public equity curve

### Components

#### 7.1 Account Manager
**Service: `services/paper-trading/account.py`**

```python
from typing import Optional
from datetime import datetime
from decimal import Decimal

class PaperAccount:
    """Virtual trading account"""
    
    def __init__(
        self,
        account_id: str,
        initial_balance: float = 100.0,
        lot_size: float = 0.01
    ):
        self.account_id = account_id
        self.balance = Decimal(str(initial_balance))
        self.initial_balance = Decimal(str(initial_balance))
        self.lot_size = lot_size
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
    
    @property
    def equity(self) -> Decimal:
        """Total equity including open positions"""
        total = self.balance
        for pos in self.positions.values():
            total += pos.unrealized_pnl
        return total
    
    @property
    def total_pnl(self) -> Decimal:
        """Total realized P&L"""
        return sum(order.pnl for order in self.orders if order.closed)
    
    @property
    def win_rate(self) -> float:
        """Win rate percentage"""
        closed = [o for o in self.orders if o.closed]
        if not closed:
            return 0.0
        wins = sum(1 for o in closed if o.pnl > 0)
        return (wins / len(closed)) * 100
    
    @property
    def profit_factor(self) -> float:
        """Profit factor (gross wins / gross losses)"""
        closed = [o for o in self.orders if o.closed]
        wins = sum(o.pnl for o in closed if o.pnl > 0)
        losses = abs(sum(o.pnl for o in closed if o.pnl < 0))
        return float(wins / losses) if losses > 0 else 0.0
    
    def reset_balance(self) -> None:
        """Reset account to initial state"""
        self.balance = self.initial_balance
        self.positions.clear()
        self.orders.clear()
        logger.info("account_reset", account_id=self.account_id)

class Position:
    """Open trading position"""
    
    def __init__(
        self,
        symbol: str,
        side: str,  # 'LONG' or 'SHORT'
        entry_price: Decimal,
        quantity: Decimal,
        entry_time: datetime
    ):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity
        self.entry_time = entry_time
    
    @property
    def unrealized_pnl(self) -> Decimal:
        """Calculate unrealized P&L (requires current price)"""
        # Will be updated with each price tick
        return Decimal('0')
    
    def close(self, exit_price: Decimal, exit_time: datetime) -> Decimal:
        """Close position and return realized P&L"""
        
        if self.side == 'LONG':
            pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            pnl = (self.entry_price - exit_price) * self.quantity
        
        return pnl
```

#### 7.2 Execution Engine
**Service: `services/paper-trading/execution.py`**

```python
class PaperExecutionEngine:
    """
    Simulate order execution
    Handle position management
    """
    
    def __init__(
        self,
        account: PaperAccount,
        repository: Repository,
        nats_client: NATSClient
    ):
        self.account = account
        self.repo = repository
        self.nc = nats_client
    
    async def process_prediction(
        self,
        symbol: str,
        prediction: Dict,
        current_price: Decimal,
        timestamp: datetime
    ) -> None:
        """Process ML prediction and execute if criteria met"""
        
        # Check if we already have a position
        has_position = symbol in self.account.positions
        
        # Decision logic
        if not has_position and prediction['probability'] > 0.7:
            # Enter new position
            direction = prediction['direction']
            side = 'LONG' if direction == 'UP' else 'SHORT'
            
            await self._open_position(
                symbol=symbol,
                side=side,
                price=current_price,
                timestamp=timestamp
            )
        
        elif has_position:
            position = self.account.positions[symbol]
            
            # Exit criteria: opposite prediction or take profit
            should_exit = (
                (position.side == 'LONG' and prediction['direction'] == 'DOWN') or
                (position.side == 'SHORT' and prediction['direction'] == 'UP') or
                self._check_stop_take(position, current_price)
            )
            
            if should_exit:
                await self._close_position(
                    symbol=symbol,
                    price=current_price,
                    timestamp=timestamp
                )
    
    async def _open_position(
        self,
        symbol: str,
        side: str,
        price: Decimal,
        timestamp: datetime
    ) -> None:
        """Open a new position"""
        
        # Calculate position size (fixed lot for simplicity)
        quantity = Decimal(str(self.account.lot_size))
        
        # Check margin (simplified - no actual margin in paper trading)
        if self.account.balance < 10:  # Minimum balance
            logger.warning("insufficient_balance", account=self.account.account_id)
            return
        
        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=price,
            quantity=quantity,
            entry_time=timestamp
        )
        
        self.account.positions[symbol] = position
        
        # Log to database
        await self.repo.log_order_open(
            account_id=self.account.account_id,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            time=timestamp
        )
        
        logger.info("position_opened", 
                   symbol=symbol, side=side, price=price)
        
        # Publish to NATS
        await self._publish_trade_event('OPEN', symbol, side, price, timestamp)
    
    async def _close_position(
        self,
        symbol: str,
        price: Decimal,
        timestamp: datetime
    ) -> None:
        """Close existing position"""
        
        position = self.account.positions.pop(symbol)
        pnl = position.close(price, timestamp)
        
        # Update balance
        self.account.balance += pnl
        
        # Log order
        await self.repo.log_order_close(
            order_id=position.order_id,
            exit_price=price,
            exit_time=timestamp,
            pnl=pnl
        )
        
        logger.info("position_closed",
                   symbol=symbol, pnl=float(pnl))
        
        # Publish to NATS
        await self._publish_trade_event('CLOSE', symbol, position.side, price, timestamp, pnl)
    
    def _check_stop_take(self, position: Position, current_price: Decimal) -> bool:
        """Check stop loss or take profit"""
        pip_value = Decimal('0.0001')  # For forex
        
        if position.side == 'LONG':
            pip_move = (current_price - position.entry_price) / pip_value
            # Stop at 50 pips, take at 100 pips
            return pip_move <= -50 or pip_move >= 100
        else:
            pip_move = (position.entry_price - current_price) / pip_value
            return pip_move <= -50 or pip_move >= 100
    
    async def _publish_trade_event(self, action: str, symbol: str, side: str, 
                                  price: Decimal, time: datetime, pnl: Decimal = None):
        """Publish trade event to public feed"""
        subject = f"tradebase.public.papertrading.{symbol.lower()}"
        
        payload = {
            'timestamp': time.isoformat(),
            'account_id': self.account.account_id,
            'action': action,
            'symbol': symbol,
            'side': side,
            'price': float(price),
            'pnl': float(pnl) if pnl else None,
            'equity': float(self.account.equity)
        }
        
        await self.nc.publish(subject, json.dumps(payload).encode())
```

#### 7.3 Performance Tracker
**Service: `services/paper-trading/performance.py`**

```python
class PerformanceTracker:
    """Track and calculate trading performance metrics"""
    
    def __init__(self, repository: Repository):
        self.repo = repository
    
    async def calculate_metrics(self, account_id: str) -> Dict:
        """Calculate comprehensive performance metrics"""
        
        trades = await self.repo.get_closed_trades(account_id)
        
        if not trades:
            return self._empty_metrics()
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        win_rate = (len(winning_trades) / total_trades) * 100
        
        # P&L metrics
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Drawdown
        equity_curve = await self._build_equity_curve(account_id)
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        
        # Risk metrics
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0
        avg_loss = gross_loss / len(losing_trades) if losing_trades else 0
        expectancy = ((avg_win * len(winning_trades)) - (avg_loss * len(losing_trades))) / total_trades
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'gross_profit': float(gross_profit),
            'gross_loss': float(gross_loss),
            'max_drawdown': max_drawdown,
            'expectancy': float(expectancy),
            'avg_win': float(avg_win),
            'avg_loss': float(avg_loss),
            'current_equity': float(equity_curve[-1] if equity_curve else 100)
        }
    
    async def _build_equity_curve(self, account_id: str) -> List[float]:
        """Build historical equity curve"""
        trades = await self.repo.get_all_trades(account_id)
        
        equity = 100.0
        curve = [equity]
        
        for trade in trades:
            if trade.closed:
                equity += trade.pnl
                curve.append(equity)
        
        return curve
    
    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculate maximum drawdown percentage"""
        if not equity_curve:
            return 0.0
        
        peak = equity_curve[0]
        max_dd = 0.0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def _empty_metrics(self) -> Dict:
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'max_drawdown': 0.0,
            'expectancy': 0.0,
            'current_equity': 100.0
        }
```

### Deliverables
✅ Virtual account system  
✅ Position management  
✅ Order execution simulation  
✅ Performance metrics tracking  
✅ Public trade events via NATS  

### Validation Criteria
- Account starts at exactly $100
- Positions open/close correctly
- P&L calculations accurate
- Win rate and profit factor correct
- Equity curve publishable

---

## Phase 8: Subscription & Billing (Week 9-10)
**Complexity:** Medium | **Standalone:** ✅ Yes | **Dependencies:** Phase 4

### Objectives
- User management
- Tier system
- JWT provisioning
- Payment integration (Stripe placeholder)
- Access control enforcement

### Components

#### 8.1 User Management
**Service: `services/subscription/users.py`**

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid

class User(BaseModel):
    user_id: uuid.UUID
    email: str
    created_at: datetime
    tier: Literal['trial', 'basic', 'premium'] = 'trial'
    subscription_expires: Optional[datetime] = None
    nkey_public: Optional[str] = None
    is_active: bool = True

class UserRepository:
    """User data access"""
    
    def __init__(self, db: TimescaleDBRepository):
        self.db = db
    
    async def create_user(self, email: str) -> User:
        """Create new trial user"""
        
        user = User(
            user_id=uuid.uuid4(),
            email=email,
            created_at=datetime.now(),
            tier='trial'
        )
        
        await self.db.execute("""
            INSERT INTO users (user_id, email, tier, created_at)
            VALUES ($1, $2, $3, $4)
        """, user.user_id, user.email, user.tier, user.created_at)
        
        return user
    
    async def get_user(self, user_id: uuid.UUID) -> Optional[User]:
        """Fetch user by ID"""
        row = await self.db.fetchrow(
            "SELECT * FROM users WHERE user_id = $1",
            user_id
        )
        return User(**dict(row)) if row else None
    
    async def update_tier(
        self,
        user_id: uuid.UUID,
        new_tier: Literal['basic', 'premium'],
        duration_days: int
    ) -> User:
        """Update subscription tier"""
        
        expires = datetime.now() + timedelta(days=duration_days)
        
        await self.db.execute("""
            UPDATE users
            SET tier = $2, subscription_expires = $3
            WHERE user_id = $1
        """, user_id, new_tier, expires)
        
        return await self.get_user(user_id)
    
    async def store_nkey(self, user_id: uuid.UUID, public_key: str) -> None:
        """Store user's NKey public key"""
        await self.db.execute("""
            UPDATE users
            SET nkey_public = $2
            WHERE user_id = $1
        """, user_id, public_key)
```

#### 8.2 Subscription Service
**Service: `services/subscription/service.py`**

```python
class SubscriptionService:
    """
    Manage subscriptions and JWT provisioning
    """
    
    def __init__(
        self,
        user_repo: UserRepository,
        jwt_manager: NATSJWTManager,
        nats: NATSClient
    ):
        self.users = user_repo
        self.jwt = jwt_manager
        self.nats = nats
    
    async def start_trial(self, email: str) -> Dict:
        """Start free trial with limited access"""
        
        user = await self.users.create_user(email)
        
        # Generate trial JWT (no NKey for trial)
        trial_jwt = self.jwt.generate_user_jwt(
            str(user.user_id),
            tier='trial',
            expires_hours=24 * 30  # 30 days
        )
        
        return {
            'user_id': str(user.user_id),
            'jwt': trial_jwt,
            'tier': 'trial',
            'websocket_url': 'wss://tradebase.com/trial'
        }
    
    async def subscribe_basic(
        self,
        user_id: uuid.UUID,
        payment_method_id: str
    ) -> Dict:
        """Process basic subscription"""
        
        # In production: Process payment via Stripe
        # await stripe.payment_intent.create(...)
        
        # Update user tier
        user = await self.users.update_tier(user_id, 'basic', 30)
        
        # Generate NKey pair
        seed, public_key = NKeyManager.generate_user_keypair()
        await self.users.store_nkey(user_id, public_key)
        
        # Generate JWT
        user_jwt = self.jwt.generate_user_jwt(
            str(user_id),
            tier='basic',
            expires_hours=24 * 30
        )
        
        return {
            'user_id': str(user_id),
            'jwt': user_jwt,
            'nkey_seed': seed,
            'public_key': public_key,
            'tier': 'basic',
            'nats_url': 'nats://tradebase.com:4222',
            'expires': user.subscription_expires
        }
    
    async def subscribe_premium(
        self,
        user_id: uuid.UUID,
        payment_method_id: str
    ) -> Dict:
        """Process premium subscription"""
        
        user = await self.users.update_tier(user_id, 'premium', 30)
        
        seed, public_key = NKeyManager.generate_user_keypair()
        await self.users.store_nkey(user_id, public_key)
        
        user_jwt = self.jwt.generate_user_jwt(
            str(user_id),
            tier='premium',
            expires_hours=24 * 30
        )
        
        return {
            'user_id': str(user_id),
            'jwt': user_jwt,
            'nkey_seed': seed,
            'public_key': public_key,
            'tier': 'premium',
            'nats_url': 'nats://tradebase.com:4222',
            'expires': user.subscription_expires
        }
    
    async def revoke_access(self, user_id: uuid.UUID) -> None:
        """Revoke all access"""
        
        # Invalidate by updating user
        await self.users.db.execute("""
            UPDATE users
            SET is_active = false, tier = 'expired'
            WHERE user_id = $1
        """, user_id)
        
        # NATS will reject on next connection validation
```

#### 8.3 FastAPI Backend
**Service: `services/api-gateway/main.py`**

```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict

app = FastAPI(title="Tradebase API")
security = HTTPBearer()

# Dependencies injected via startup
subscription_service: SubscriptionService = None

@app.on_event("startup")
async def startup():
    global subscription_service
    subscription_service = SubscriptionService(...)

@app.post("/auth/trial")
async def start_trial(request: TrialRequest):
    """Start free trial"""
    return await subscription_service.start_trial(request.email)

@app.post("/auth/subscribe")
async def create_subscription(request: SubscriptionRequest):
    """Create paid subscription"""
    if request.tier == 'basic':
        return await subscription_service.subscribe_basic(
            request.user_id, request.payment_method
        )
    elif request.tier == 'premium':
        return await subscription_service.subscribe_premium(
            request.user_id, request.payment_method
        )

@app.get("/auth/validate")
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate user token"""
    token = credentials.credentials
    payload = jwt.decode(token, options={"verify_signature": False})
    
    user = await subscription_service.users.get_user(uuid.UUID(payload['sub']))
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return {
        "valid": True,
        "tier": user.tier,
        "expires": user.subscription_expires
    }

@app.post("/paper/reset")
async def reset_paper_account(user_id: uuid.UUID):
    """Reset paper trading account"""
    await subscription_service.reset_account(user_id)
    return {"message": "Account reset to $100"}
```

### Deliverables
✅ User management system  
✅ Tier-based subscriptions  
✅ JWT provisioning  
✅ Payment integration placeholder  
✅ API gateway  

### Validation Criteria
- Can create trial user
- JWT contains correct permissions
- NATS rejects unauthorized subjects
- Can upgrade tiers

---

## Phase 9: Web Dashboard (Week 10-11)
**Complexity:** Medium-Hard | **Standalone:** ✅ Yes | **Dependencies:** Phase 7, 8

### Objectives
- Real-time data visualization
- Equity curve display
- Portfolio overview
- WebSocket integration
- Trial user access

### Components

#### 9.1 Frontend Architecture
**Service: `services/dashboard/`**

```
dashboard/
├── src/
│   ├── components/
│   │   ├── EquityChart.tsx      # Real-time equity curve
│   │   ├── TradeTable.tsx       # Recent trades
│   │   ├── PerformanceCard.tsx  # Key metrics
│   │   └── PriceChart.tsx       # Live price
│   ├── hooks/
│   │   ├── useNATS.ts           # NATS WebSocket hook
│   │   └── usePaperTrading.ts   # Paper trading state
│   ├── pages/
│   │   ├── Dashboard.tsx         # Main dashboard
│   │   └── Trial.tsx            # Public trial view
│   └── lib/
│       ├── nats-ws.ts           # NATS WebSocket client
│       └── api.ts                # REST API client
├── public/
└── package.json
```

#### 9.2 NATS WebSocket Client
**File: `services/dashboard/src/lib/nats-ws.ts`**

```typescript
import { connect, NatsConnection } from 'nats.ws';

interface NATSMessage {
  timestamp: string;
  symbol: string;
  [key: string]: any;
}

class TradebaseNATS {
  private nc: NatsConnection | null = null;
  private subscriptions: Map<string, (msg: any) => void> = new Map();

  async connect(jwt: string, nkeySeed?: string) {
    this.nc = await connect({
      servers: 'wss://nats.tradebase.com',
      userJWT: jwt,
      nkeySeed: nkeySeed,
    });
  }

  async subscribe(subject: string, callback: (msg: NATSMessage) => void) {
    if (!this.nc) throw new Error('Not connected');
    
    const sub = await this.nc.subscribe(subject);
    
    (async () => {
      for await (const msg of sub) {
        const data = JSON.parse(new TextDecoder().decode(msg.data));
        callback(data);
      }
    })();
    
    this.subscriptions.set(subject, callback);
  }

  async disconnect() {
    if (this.nc) {
      await this.nc.close();
      this.nc = null;
    }
  }
}

export const natsClient = new TradebaseNATS();
```

#### 9.3 Equity Chart Component
**File: `services/dashboard/src/components/EquityChart.tsx`**

```typescript
import React from 'react';
import { Line } from 'react-chartjs-2';
import { usePaperTrading } from '../hooks/usePaperTrading';

export const EquityChart: React.FC = () => {
  const { equityHistory } = usePaperTrading();
  
  const data = {
    labels: equityHistory.map(pt => pt.time),
    datasets: [{
      label: 'Virtual Portfolio ($)',
      data: equityHistory.map(pt => pt.equity),
      borderColor: 'rgb(75, 192, 192)',
      backgroundColor: 'rgba(75, 192, 192, 0.1)',
      tension: 0.4,
      fill: true
    }]
  };
  
  const options = {
    responsive: true,
    scales: {
      y: {
        beginAtZero: false,
        title: { display: true, text: 'Equity ($)' }
      },
      x: {
        type: 'time' as const,
        time: { unit: 'hour' as const }
      }
    },
    plugins: {
      tooltip: {
        callbacks: {
          label: (ctx) => `$${ctx.parsed.y.toFixed(2)}`
        }
      }
    }
  };
  
  return <Line data={data} options={options} />;
};
```

#### 9.4 Paper Trading Hook
**File: `services/dashboard/src/hooks/usePaperTrading.ts`**

```typescript
import { useState, useEffect } from 'react';
import { natsClient } from '../lib/nats-ws';

interface Trade {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entryTime: string;
  entryPrice: number;
  exitPrice?: number;
  pnl?: number;
  status: 'OPEN' | 'CLOSED';
}

interface EquityPoint {
  time: string;
  equity: number;
}

export const usePaperTrading = () => {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [equityHistory, setEquityHistory] = useState<EquityPoint[]>([]);
  
  useEffect(() => {
    // Subscribe to paper trading updates
    natsClient.subscribe('tradebase.public.papertrading.*', (msg) => {
      if (msg.action === 'OPEN') {
        setTrades(prev => [...prev, {
          id: msg.order_id,
          symbol: msg.symbol,
          side: msg.side,
          entryTime: msg.timestamp,
          entryPrice: msg.price,
          status: 'OPEN'
        }]);
      } else if (msg.action === 'CLOSE') {
        setTrades(prev => prev.map(t =>
          t.id === msg.order_id
            ? { ...t, exitPrice: msg.price, pnl: msg.pnl, status: 'CLOSED' }
            : t
        ));
      }
      
      // Update equity history
      setEquityHistory(prev => [...prev, {
        time: msg.timestamp,
        equity: msg.equity
      }]);
    });
  }, []);
  
  return { trades, equityHistory };
};
```

#### 9.5 Dashboard Page
**File: `services/dashboard/src/pages/Dashboard.tsx`**

```typescript
import React from 'react';
import { EquityChart } from '../components/EquityChart';
import { PerformanceCard } from '../components/PerformanceCard';
import { TradeTable } from '../components/TradeTable';
import { usePaperTrading } from '../hooks/usePaperTrading';

export const Dashboard: React.FC = () => {
  const { trades } = usePaperTrading();
  
  const closedTrades = trades.filter(t => t.status === 'CLOSED');
  const winRate = closedTrades.length > 0
    ? (closedTrades.filter(t => t.pnl && t.pnl > 0).length / closedTrades.length) * 100
    : 0;
  
  return (
    <div className="dashboard">
      <header>
        <h1>Tradebase Paper Trading</h1>
        <button>Reset Balance ($100)</button>
      </header>
      
      <div className="metrics">
        <PerformanceCard title="Win Rate" value={`${winRate.toFixed(1)}%`} />
        <PerformanceCard title="Total Trades" value={trades.length} />
        <PerformanceCard title="Open Positions" value={trades.filter(t => t.status === 'OPEN').length} />
      </div>
      
      <div className="charts">
        <EquityChart />
      </div>
      
      <TradeTable trades={trades} />
    </div>
  );
};
```

### Deliverables
✅ React/Vue frontend  
✅ Real-time equity chart  
✅ Trade table  
✅ Performance cards  
✅ WebSocket integration  
✅ Trial access  

### Validation Criteria
- WebSocket connects with trial JWT
- Equity updates in real-time
- Trades appear within 1 second
- Chart renders smoothly

---

## Phase 10: Advanced ML - RL Pipeline (Week 11-13)
**Complexity:** Hard | **Standalone:** ✅ Yes | **Dependencies:** Phase 6

### Objectives
- Gymnasium environment
- PPO implementation
- RL training pipeline
- Model deployment

### Components

#### 10.1 Trading Environment
**Service: `services/ml-engine/rl/environment.py`**

```python
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Tuple, Dict, Any

class TradingEnv(gym.Env):
    """
    Custom trading environment for reinforcement learning
    """
    
    metadata = {'render_modes': ['human']}
    
    def __init__(self, feature_store: MLFeatureStore):
        super().__init__()
        
        self.feature_store = feature_store
        
        # Action space: 0=Hold, 1=Long, 2=Short
        self.action_space = spaces.Discrete(3)
        
        # Observation space: technical features + position state
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(10,), dtype=np.float32
        )
        
        # Trading state
        self.position = 0  # 0=flat, +1=long, -1=short
        self.entry_price = None
        self.total_pnl = 0.0
        self.current_step = 0
        
    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None
    ) -> Tuple[np.ndarray, Dict]:
        """Reset environment for new episode"""
        
        super().reset(seed=seed)
        
        self.position = 0
        self.entry_price = None
        self.total_pnl = 0.0
        self.current_step = 0
        
        # Get initial observation
        obs = self._get_observation()
        
        info = {}
        return obs, info
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """Execute one trading step"""
        
        # Get current features
        obs = self._get_observation()
        current_price = obs[0]  # First feature is price
        
        reward = 0.0
        # Execute action
        if action == 1 and self.position == 0:  # Enter Long
            self.position = 1
            self.entry_price = current_price
        elif action == 2 and self.position == 0:  # Enter Short
            self.position = -1
            self.entry_price = current_price
        elif action == 0 and self.position != 0:  # Close position
            if self.position == 1:
                reward = current_price - self.entry_price
            else:
                reward = self.entry_price - current_price
            self.position = 0
            self.entry_price = None
        
        # Calculate unrealized PnL for open position
        if self.position != 0:
            unrealized = (current_price - self.entry_price) * self.position
            # Small reward for being profitable
            reward = unrealized * 0.1
        
        self.total_pnl += reward
        self.current_step += 1
        
        # Check termination (episode end)
        terminated = self.current_step >= 1000  # Max steps
        truncated = abs(self.total_pnl) > 50  # Stop loss / take profit
        
        info = {
            'total_pnl': self.total_pnl,
            'position': self.position,
            'step': self.current_step
        }
        
        return obs, reward, terminated, truncated, info
    
    def _get_observation(self) -> np.ndarray:
        """Build observation vector"""
        # Features: [price, rsi, bb_position, sentiment, ...]
        # Would fetch from feature store
        
        # Simplified placeholder
        return np.random.randn(10).astype(np.float32)
    
    def render(self):
        """Render environment state"""
        print(f"Step: {self.current_step}, Position: {self.position}, PnL: {self.total_pnl:.2f}")
```

#### 10.2 PPO Training
**Service: `services/ml-engine/rl/ppo.py`**

```python
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardPlateau

class RLTrainingPipeline:
    """
    Train PPO agent on trading environment
    """
    
    def __init__(
        self,
        env: TradingEnv,
        model_path: str
    ):
        self.env = env
        self.model_path = model_path
        self.model = None
    
    def train(
        self,
        total_timesteps: int = 100_000,
        eval_freq: int = 5_000
    ) -> Dict:
        """Train PPO model"""
        
        # Create evaluation environment
        eval_env = TradingEnv(self.env.feature_store)
        
        # Callbacks
        eval_callback = EvalCallback(
            eval_env,
            best_model_save_path=self.model_path,
            log_path=f"{self.model_path}/logs",
            eval_freq=eval_freq,
            deterministic=True,
            render=False
        )
        
        stop_callback = StopTrainingOnRewardPlateau(
            reward_threshold=-5.0,  # Minimum acceptable reward
            verbose=1
        )
        
        # Create and train model
        self.model = PPO(
            'MlpPolicy',
            self.env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1,
            tensorboard_log=f"{self.model_path}/tb"
        )
        
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=[eval_callback, stop_callback]
        )
        
        # Save final model
        self.model.save(f"{self.model_path}/final_model")
        
        # Evaluate final performance
        mean_reward, std_reward = self._evaluate(eval_env, n_episodes=10)
        
        return {
            'mean_reward': mean_reward,
            'std_reward': std_reward,
            'model_path': f"{self.model_path}/final_model"
        }
    
    def _evaluate(self, env, n_episodes: int = 10) -> Tuple[float, float]:
        """Evaluate trained model"""
        
        episode_rewards = []
        
        for _ in range(n_episodes):
            obs, _ = env.reset()
            episode_reward = 0
            done = False
            
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, _ = env.step(action)
                episode_reward += reward
                done = terminated or truncated
            
            episode_rewards.append(episode_reward)
        
        return np.mean(episode_rewards), np.std(episode_rewards)
```

#### 10.3 RL Model Deployment
**Service: `services/ml-engine/rl/deploy.py`**

```python
class RLModelServer:
    """
    Serve trained RL model for predictions
    """
    
    def __init__(self, model_path: str, env: TradingEnv):
        self.model = PPO.load(model_path)
        self.env = env
    
    def predict_action(self, features: Dict) -> Tuple[int, float]:
        """
        Predict action using trained model
        
        Returns:
            (action: 0/1/2, probability: float)
        """
        
        # Build observation
        obs = self._features_to_obs(features)
        
        # Predict
        action, states = self.model.predict(obs, deterministic=True)
        
        # Get action probabilities
        # (SB3 doesn't expose this directly, need to use the policy network)
        
        return int(action), 0.8  # Placeholder probability
    
    def _features_to_obs(self, features: Dict) -> np.ndarray:
        """Convert feature dict to observation vector"""
        return np.array([
            features.get('price', 0),
            features.get('rsi', 50) / 100,
            features.get('bb_percent', 0.5),
            features.get('sentiment', 0),
            # ... more features
        ], dtype=np.float32)
```

### Deliverables
✅ Gymnasium trading environment  
✅ PPO model training  
✅ Model evaluation  
✅ RL prediction service  

### Validation Criteria
- Environment conforms to Gymnasium API
- Model trains without errors
- Achieves positive rewards
- Predictions returned in <50ms

---

## Phase 11: Feedback Loop & Auto-Retraining (Week 13-14)
**Complexity:** Hard | **Standalone:** ✅ Yes | **Dependencies:** Phase 6, 7

### Objectives
- Performance monitoring
- Automatic model retraining
- Rollback capability
- Alert system

### Components

#### 11.1 Performance Monitor
**Service: `services/ml-engine/monitor.py`**

```python
from dataclasses import dataclass
from typing import List
from datetime import datetime, timedelta

@dataclass
class PerformanceThreshold:
    win_rate_min: float = 0.55
    profit_factor_min: float = 1.5
    max_drawdown_max: float = 20.0

class ModelPerformanceMonitor:
    """
    Monitor live model performance
    Trigger alerts when thresholds breached
    """
    
    def __init__(
        self,
        perf_tracker: PerformanceTracker,
        account_id: str,
        thresholds: PerformanceThreshold = PerformanceThreshold()
    ):
        self.tracker = perf_tracker
        self.account_id = account_id
        self.thresholds = thresholds
        self.alert_history: List[Dict] = []
    
    async def check_performance(self) -> Dict:
        """Check current performance against thresholds"""
        
        metrics = await self.tracker.calculate_metrics(self.account_id)
        
        alerts = []
        
        # Check win rate
        if metrics['win_rate'] < self.thresholds.win_rate_min:
            alerts.append({
                'metric': 'win_rate',
                'value': metrics['win_rate'],
                'threshold': self.thresholds.win_rate_min,
                'severity': 'HIGH' if metrics['win_rate'] < 0.5 else 'MEDIUM'
            })
        
        # Check profit factor
        if metrics['profit_factor'] < self.thresholds.profit_factor_min:
            alerts.append({
                'metric': 'profit_factor',
                'value': metrics['profit_factor'],
                'threshold': self.thresholds.profit_factor_min,
                'severity': 'HIGH'
            })
        
        # Check drawdown
        if metrics['max_drawdown'] > self.thresholds.max_drawdown_max:
            alerts.append({
                'metric': 'max_drawdown',
                'value': metrics['max_drawdown'],
                'threshold': self.thresholds.max_drawdown_max,
                'severity': 'CRITICAL'
            })
        
        if alerts:
            await self._send_alerts(alerts)
            self.alert_history.extend(alerts)
        
        return {
            'metrics': metrics,
            'alerts': alerts,
            'needs_retraining': len(alerts) > 0
        }
    
    async def _send_alerts(self, alerts: List[Dict]):
        """Send alerts via configured channels"""
        
        for alert in alerts:
            logger.error("performance_alert", alert=alert)
            
            # Send to monitoring system
            # Send to Slack/email (optional)
```

#### 11.2 Auto-Retraining Pipeline
**Service: `services/ml-engine/retrain.py`**

```python
class AutoRetrainingPipeline:
    """
    Automatically retrain models when performance degrades
    """
    
    def __init__(
        self,
        monitor: ModelPerformanceMonitor,
        training_pipeline: MLTrainingPipeline,
        model_registry: 'ModelRegistry'
    ):
        self.monitor = monitor
        self.training = training_pipeline
        self.registry = model_registry
        self._running = False
    
    async def run_continuous_monitoring(self, interval_minutes: int = 60):
        """Run continuous monitoring loop"""
        
        self._running = True
        
        while self._running:
            status = await self.monitor.check_performance()
            
            if status['needs_retraining']:
                logger.warning("performance_degraded", alerts=status['alerts'])
                
                # Trigger retraining
                await self._retrain_and_deploy()
            
            await asyncio.sleep(interval_minutes * 60)
    
    async def _retrain_and_deploy(self) -> None:
        """Retrain models and deploy if improved"""
        
        logger.info("retraining_started")
        
        # Archive current model
        current_model_id = await self.registry.get_current_model()
        await self.registry.archive_model(current_model_id)
        
        # Train new model
        training_result = await self.training.run_weekend_retraining(['EURUSD'])
        
        # Validate new model
        new_accuracy = training_result['EURUSD']['xgb']['validation']['accuracy']
        old_accuracy = await self.registry.get_model_accuracy(current_model_id)
        
        if new_accuracy > old_accuracy:
            # Deploy new model
            new_model_id = await self.registry.register_model(
                type='xgb',
                metrics=training_result['EURUSD']['xgb']
            )
            
            await self.registry.promote_to_production(new_model_id)
            logger.info("model_deployed", model_id=new_model_id, accuracy=new_accuracy)
        else:
            logger.warning("model_not_improved", new=new_accuracy, old=old_accuracy)
            # Rollback to archived model if needed
            await self.registry.rollback_to_archived()
```

#### 11.3 Model Registry
**Service: `services/ml-engine/registry.py`**

```python
from typing import Optional, Dict
from dataclasses import dataclass

@dataclass
class ModelMetadata:
    model_id: str
    model_type: str  # 'j48', 'xgb', 'ppo'
    created_at: datetime
    accuracy: float
    log_loss: float
    training_samples: int
    status: str  # 'staging', 'production', 'archived'
    file_path: str

class ModelRegistry:
    """
    Track model versions
    Handle promotion and rollback
    """
    
    def __init__(self, repository: Repository):
        self.repo = repository
    
    async def register_model(
        self,
        model_type: str,
        metrics: Dict,
        file_path: str
    ) -> str:
        """Register a new trained model"""
        
        model_id = f"{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        metadata = ModelMetadata(
            model_id=model_id,
            model_type=model_type,
            created_at=datetime.now(),
            accuracy=metrics.get('accuracy', 0),
            log_loss=metrics.get('log_loss', 0),
            training_samples=metrics.get('training_samples', 0),
            status='staging',
            file_path=file_path
        )
        
        await self.repo.execute("""
            INSERT INTO model_registry 
            (model_id, model_type, created_at, accuracy, log_loss, status, file_path)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, metadata.model_id, metadata.model_type, metadata.created_at,
            metadata.accuracy, metadata.log_loss, metadata.status, metadata.file_path)
        
        logger.info("model_registered", model_id=model_id)
        return model_id
    
    async def promote_to_production(self, model_id: str) -> None:
        """Promote model to production"""
        
        await self.repo.execute("""
            UPDATE model_registry
            SET status = 'production'
            WHERE model_id = $1
        """, model_id)
        
        logger.info("model_promoted", model_id=model_id)
    
    async def get_current_model(self) -> Optional[str]:
        """Get current production model"""
        row = await self.repo.fetchrow(
            "SELECT model_id FROM model_registry WHERE status = 'production' LIMIT 1"
        )
        return row['model_id'] if row else None
    
    async def archive_model(self, model_id: str) -> None:
        """Archive a model"""
        await self.repo.execute("""
            UPDATE model_registry
            SET status = 'archived'
            WHERE model_id = $1
        """, model_id)
```

### Deliverables
✅ Performance monitoring system  
✅ Automatic retraining pipeline  
✅ Model registry  
✅ Rollback capability  
✅ Alert system  

### Validation Criteria
- Monitors detect performance degradation
- Retraining triggers automatically
- Model rollback works correctly
- Alerts sent appropriately

---

## Phase 12: Production Readiness & Optimization (Week 14-16)
**Complexity:** Hard | **Standalone:** ✅ Yes | **Dependencies:** All phases

### Objectives
- Load testing
- Security hardening
- Deployment automation
- Documentation
- Monitoring dashboards

### Components

#### 12.1 Load Testing
**Tool: `tests/load/locustfile.py`**

```python
from locust import HttpUser, task, between
import nats
from nats.aio.client import Client as NATS

class TradebaseUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Initialize NATS connection"""
        self.nc = NATS()
    
    @task(3)
    async def consume_raw_data(self):
        """Consume raw market data"""
        await self.nc.subscribe("tradebase.forex.*.raw.1m")
    
    @task(2)
    async def consume_features(self):
        """Consume computed features"""
        await self.nc.subscribe("tradebase.forex.*.features.1m")
    
    @task(1)
    async def consume_predictions(self):
        """Consume ML predictions"""
        await self.nc.subscribe("tradebase.forex.*.prediction.1m")
```

#### 12.2 Security Hardening
**File: `infrastructure/security/`

- TLS certificates for NATS
- API rate limiting
- Input validation
- SQL injection prevention
- Secrets management

#### 12.3 Deployment Automation
**File: `.github/workflows/deploy.yml`**

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Docker images
        run: docker-compose -f docker-compose.prod.yml build
      
      - name: Deploy to VPS
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_KEY }}
          script: |
            cd /opt/tradebase
            git pull
            docker-compose -f docker-compose.prod.yml up -d
            docker-compose -f docker-compose.prod.yml exec -T timescaledb psql -U tradebase -d tradebase -c "SELECT version();"
```

#### 12.4 Monitoring Dashboards
**File: `infrastructure/monitoring/grafana/dashboards/`**

- System metrics dashboard
- Trading performance dashboard
- ML model performance dashboard
- Error rates dashboard

#### 12.5 Documentation
**Files: `docs/`**

- API documentation
- Architecture diagrams
- Runbooks
- Troubleshooting guide
- Onboarding guide

### Deliverables
✅ Load testing passing  
✅ Security audit passed  
✅ Automated deployment  
✅ Complete documentation  
✅ Production monitoring  

### Validation Criteria
- System handles 1000 concurrent connections
- Security vulnerabilities addressed
- One-command deployment
- Complete API documentation

---

## Summary Timeline

| Phase | Duration | Complexity | Key Deliverable |
|-------|----------|------------|-----------------|
| 1. Foundation | 2 weeks | Easy | Docker + Observability |
| 2. Database | 1 week | Easy-Med | TimescaleDB Schema |
| 3. Ingestion | 1 week | Easy-Med | YFinance Data Pipeline |
| 4. NATS Core | 1 week | Medium | JWT Auth + Messaging |
| 5. Features | 1 week | Medium | Indicators + Sentiment |
| 6. ML Engine | 2 weeks | Med-Hard | J48 + XGBoost Models |
| 7. Paper Trading | 1 week | Medium | Virtual Trading |
| 8. Subscription | 1 week | Medium | Billing + JWT Provisioning |
| 9. Dashboard | 1 week | Med-Hard | Web UI + WebSocket |
| 10. RL Pipeline | 2 weeks | Hard | PPO Training |
| 11. Feedback Loop | 1 week | Hard | Auto-Retraining |
| 12. Production | 2 weeks | Hard | Deployment + Monitoring |

**Total: 16 weeks**

---

## Success Metrics

### Technical Metrics
- **Latency:** <1ms from candle close to NATS publish
- **Throughput:** 10,000+ concurrent NATS connections
- **Uptime:** 99.9% availability
- **Accuracy:** ML models >60% directional accuracy

### Business Metrics
- **Conversion:** Trial to paid conversion >10%
- **Retention:** Monthly churn <5%
- **Performance:** Win rate >55%, Profit Factor >1.5

---

## Next Steps

1. Review and approve this plan
2. Set up development environment (Phase 1)
3. Begin implementation from Phase 1

Each phase can be developed and tested independently, with clear handoff points to the next phase.
