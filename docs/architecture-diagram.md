# Tradebase AI Platform - Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Tradebase Platform                                 │
│                                                                              │
│  ┌────────────────┐        ┌─────────────────────────────────────────────┐ │
│  │   Data Sources │       │             Messaging Layer (NATS)           │ │
│  │                │       │                                             │ │
│  │  ┌──────────┐  │       │  ┌─────────────────────────────────────┐  │ │
│  │  │YFinance  │──┼───────┼─▶│ Subject: tradebase.forex.*.raw.1m   │  │ │
│  │  └──────────┘  │       │  ├─────────────────────────────────────┤  │ │
│  │  ┌──────────┐  │       │  │ Subject: tradebase.forex.*.features  │  │ │
│  │  │ Alpaca   │──┼───────┼─▶│ Subject: tradebase.forex.*.prediction│  │ │
│  │  │(Future)  │  │       │  └─────────────────────────────────────┘  │ │
│  │  └──────────┘  │       │                                             │ │
│  │  ┌──────────┐  │       │  ┌─────────────────────────────────────┐  │ │
│  │  │   MT5    │──┼───────┼─▶│ JWT + NKey Authentication            │  │ │
│  │  │(Future)  │  │       │  │ - Tier-based permissions              │  │ │
│  │  └──────────┘  │       │  │ - Basic: raw data only                │  │ │
│  └────────────────┘       │  │ - Premium: predictions + features      │  │ │
│                            │  └─────────────────────────────────────┘  │ │
│                            └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Service Layer                                       │
│                                                                              │
│  ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐    │
│  │  Ingestion Service│   │  Feature Engine   │   │   ML Engine        │    │
│  │                   │   │                   │   │                    │    │
│  │ - Fetch candles   │──▶│ - RSI             │──▶│ - J48 (Weka)      │    │
│  │ - Store to TSDB   │   │ - Elder Ray       │   │ - XGBoost         │    │
│  │ - Publish raw     │   │ - Bollinger Bands │   │ - Ensemble        │    │
│  │                   │   │ - Sentiment       │   │                    │    │
│  └───────────────────┘   └───────────────────┘   └───────────────────┘    │
│                                                                              │
│  ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐    │
│  │  Paper Trading    │   │  Subscription     │   │  Web Dashboard    │    │
│  │                   │   │  Service          │   │                   │    │
│  │ - Virtual account │   │ - User mgmt       │   │ - React/Vue UI    │    │
│  │ - Order sim       │   │ - JWT provisioning│   │ - Equity chart   │    │
│  │ - P&L tracking    │   │ - Billing         │   │ - Trade table    │    │
│  │ - Performance     │   │                   │   │ - WebSocket      │    │
│  └───────────────────┘   └───────────────────┘   └───────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Data & Observability Layer                          │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                        TimescaleDB                                    │   │
│  │                                                                       │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │   │
│  │  │ market_features │  │  paper_orders   │  │  model_registry │      │   │
│  │  │ - Hypertable    │  │  - Orders/P&L    │  │  - Versions     │      │   │
│  │  │ - 1yr retention │  │  - Trade log     │  │  - Metrics      │      │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘      │   │
│  │                                                                       │   │
│  │  Continuous Aggregates: 1H, 4H                                       │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                    Observability Stack                                 │ │
│  │                                                                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│ │
│  │  │ Prometheus  │  │  Grafana    │  │  Jaeger     │  │  ELK Stack   ││ │
│  │  │ - Metrics   │  │ - Dashboards│  │ - Tracing   │  │ - Logging    ││ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Real-Time Data Pipeline
```
YFinance → Ingestion Service → TimescaleDB → NATS (raw.1m)
                                                    ↓
                                            Feature Engine → NATS (features.1m)
                                                          ↓
                                                  ML Engine → NATS (prediction.1m)
```

### 2. Paper Trading Flow
```
NATS (prediction.1m) → Paper Trading Engine → Order Execution
                                                          ↓
                                            TimescaleDB (paper_orders)
                                                          ↓
                                            NATS (public.papertrading.*)
                                                          ↓
                                            Web Dashboard (WebSocket)
```

### 3. User Authentication Flow
```
User → API Gateway → Subscription Service → JWT Generation
                                             ↓
                                      NKey Pair Generation
                                             ↓
                                      User receives (JWT + Seed)
                                             ↓
                              NATS Connection (JWT + NKey signature)
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  TimescaleDB │  │     NATS     │  │    Redis     │      │
│  │  Port: 5432  │  │  Port: 4222  │  │  Port: 6379  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Ingestion  │  │  Features    │  │  ML Engine   │      │
│  │              │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Paper Trade  │  │ Subscription │  │  API Gateway │      │
│  │              │  │              │  │  Port: 8000   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Grafana    │  │  Prometheus  │  │    Jaeger    │      │
│  │  Port: 3001  │  │  Port: 9090  │  │  Port: 16686 │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────┐                                          │
│  │  Dashboard   │                                          │
│  │  Port: 3001  │                                          │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

## Security Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      Security Architecture                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Network Layer                                               │
│  ├─ TLS/SSL for all external connections                    │
│  ├─ VPC/firewall rules                                      │
│  └─ DDoS protection                                         │
│                                                              │
│  Authentication Layer                                        │
│  ├─ NATS JWT + NKey                                         │
│  ├─ Subject-based permissions                              │
│  └─ Token expiration                                        │
│                                                              │
│  Application Layer                                           │
│  ├─ Input validation                                        │
│  ├─ SQL injection prevention                                │
│  ├─ Rate limiting                                           │
│  └─ Secrets management                                      │
│                                                              │
│  Data Layer                                                  │
│  ├─ Database encryption at rest                            │
│  ├─ Backups                                                 │
│  └─ Audit trails                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Scalability Strategy

### Horizontal Scaling
- **Stateless services**: Can run multiple instances
- **Load balancer**: HAProxy/Nginx for API gateway
- **NATS clustering**: Multiple brokers for HA

### Vertical Optimization
- **Connection pooling**: Database & NATS
- **In-memory caching**: Redis for hot data
- **Columnar storage**: TimescaleDB compression

### Disaster Recovery
- **Database replication**: Streaming replication
- **NATS persistence**: JetStream storage
- **Backups**: Automated S3/Glacier backups

## Monitoring & Observability

### Metrics (Prometheus)
```yaml
# System Metrics
- CPU/Memory/Network
- Container health
- Disk I/O

# Business Metrics
- Active subscriptions
- Trade execution rate
- Model accuracy
- Win rate, profit factor

# Application Metrics
- Request latency
- Error rates
- Queue depths
- Cache hit rates
```

### Tracing (Jaeger)
- Distributed tracing across services
- Request latency breakdown
- Error correlation

### Logging (ELK)
- Structured JSON logs
- Centralized log aggregation
- Alert integration

## Technology Stack Summary

| Service | Port | Purpose |
|---------|------|---------|
| Grafana | 3001 | Metrics dashboards |
| Prometheus | 9090 | Metrics collection |
| Jaeger | 16686 | Distributed tracing |

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Messaging** | NATS | Real-time pub/sub, JWT auth |
| **Database** | TimescaleDB | Time-series data storage |
| **Cache** | Redis | Fast data access |
| **ML** | Weka, XGBoost, Stable-Baselines3 | Prediction models |
| **API** | FastAPI | REST backend |
| **Frontend** | React/Vue | Dashboard |
| **Monitoring** | Prometheus, Grafana, Jaeger | Observability |
| **Deployment** | Docker, Docker Compose | Containerization |
| **CI/CD** | GitHub Actions | Automation |
