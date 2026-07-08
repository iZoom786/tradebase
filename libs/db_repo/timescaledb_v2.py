"""
TimescaleDB repository implementation (v2.0)

Changes:
- Added timekey support (YYYYMMDDHHMM format)
- Updated upsert to use timekey in ON CONFLICT
- Added ingestion state tracking methods
- Added gap detection methods
- Added manual materialized view refresh
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

import asyncpg
from asyncpg.pool import Pool

from .base import Repository

logger = logging.getLogger(__name__)


def generate_timekey(timestamp: datetime) -> int:
    """Generate timekey in YYYYMMDDHHMM format as integer"""
    return int(timestamp.strftime("%Y%m%d%H%M"))


class TimescaleDBRepository(Repository):
    """
    TimescaleDB repository with timekey support

    Features:
    - Timekey-based unique constraints
    - Ingestion state tracking
    - Gap detection
    - Manual materialized view refresh
    """

    def __init__(self, config):
        """Initialize repository"""
        self.config = config
        self.pool: Optional[Pool] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish database connection pool"""
        async with self._lock:
            if self.pool is not None:
                logger.warning("repository_already_connected")
                return

            logger.info(
                "repository_connecting",
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                pool_size=self.config.pool_size
            )

            self.pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=5,
                max_size=self.config.pool_size,
                command_timeout=60
            )

            logger.info("repository_connected")

    async def close(self) -> None:
        """Close database connection pool"""
        async with self._lock:
            if self.pool is None:
                return

            await self.pool.close()
            self.pool = None
            logger.info("repository_closed")

    async def upsert(self, data) -> None:
        """
        Insert or update market data using timekey

        Uses ON CONFLICT on (time, timekey, symbol) for hypertable compatibility.
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        # Generate timekey if not present
        timekey = getattr(data, 'timekey', None) or generate_timekey(data.time)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO market_features
                (time, timekey, symbol, interval, open, high, low, close, volume, indicators, sentiment)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (time, timekey, symbol)
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    indicators = EXCLUDED.indicators,
                    sentiment = EXCLUDED.sentiment
            """,
                data.time,
                timekey,
                data.symbol,
                data.interval,
                float(data.open),
                float(data.high),
                float(data.low),
                float(data.close),
                data.volume,
                data.indicators,
                data.sentiment
            )

            logger.debug(
                "repository_upsert",
                symbol=data.symbol,
                time=data.time.isoformat(),
                timekey=timekey
            )

    async def upsert_batch(self, data_list: List) -> int:
        """
        Batch upsert multiple records for better performance

        Returns:
            Number of records upserted
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        if not data_list:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for data in data_list:
                    timekey = getattr(data, 'timekey', None) or generate_timekey(data.time)

                    await conn.execute("""
                        INSERT INTO market_features
                        (time, timekey, symbol, interval, open, high, low, close, volume, indicators, sentiment)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (time, timekey, symbol)
                        DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            indicators = EXCLUDED.indicators,
                            sentiment = EXCLUDED.sentiment
                    """,
                        data.time,
                        timekey,
                        data.symbol,
                        data.interval,
                        float(data.open),
                        float(data.high),
                        float(data.low),
                        float(data.close),
                        data.volume,
                        data.indicators,
                        data.sentiment
                    )

            logger.info("repository_batch_upsert", count=len(data_list))
            return len(data_list)

    async def query_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m"
    ) -> List:
        """Query market data for a time range"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT time, timekey, symbol, interval,
                       open, high, low, close, volume,
                       indicators, sentiment
                FROM market_features
                WHERE symbol = $1
                  AND interval = $2
                  AND time BETWEEN $3 AND $4
                ORDER BY time ASC
            """, symbol, interval, start, end)

            # Import here to avoid circular dependency
            from services.ingestion.models.market_data_v2 import MarketData

            return [
                MarketData(
                    time=row['time'],
                    symbol=row['symbol'],
                    interval=row['interval'],
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    volume=row['volume'],
                    indicators=row.get('indicators'),
                    sentiment=row.get('sentiment')
                )
                for row in rows
            ]

    async def get_latest(
        self,
        symbol: str,
        interval: str = "1m"
    ) -> Optional:
        """Get the most recent data point for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT time, timekey, symbol, interval,
                       open, high, low, close, volume,
                       indicators, sentiment
                FROM market_features
                WHERE symbol = $1 AND interval = $2
                ORDER BY time DESC
                LIMIT 1
            """, symbol, interval)

            if row is None:
                return None

            from services.ingestion.models.market_data_v2 import MarketData

            return MarketData(
                time=row['time'],
                symbol=row['symbol'],
                interval=row['interval'],
                open=Decimal(str(row['open'])),
                high=Decimal(str(row['high'])),
                low=Decimal(str(row['low'])),
                close=Decimal(str(row['close'])),
                volume=row['volume'],
                indicators=row.get('indicators'),
                sentiment=row.get('sentiment')
            )

    async def execute(self, sql: str, *args) -> None:
        """Execute arbitrary SQL"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            await conn.execute(sql, *args)

    async def fetchone(self, sql: str, *args) -> Optional[dict]:
        """Fetch single row"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row else None

    async def fetchall(self, sql: str, *args) -> List[dict]:
        """Fetch all rows"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]

    # =====================================================
    # Ingestion State Tracking Methods
    # =====================================================

    async def get_ingestion_state(self, symbol: str) -> Optional[dict]:
        """Get ingestion state for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT symbol, last_backfill_time, last_backfill_timekey,
                       last_ingest_time, last_ingest_timekey,
                       backfill_complete, error_count, last_error, updated_at
                FROM ingestion_state
                WHERE symbol = $1
            """, symbol)

            return dict(row) if row else None

    async def update_ingestion_state(
        self,
        symbol: str,
        last_backfill_time: Optional[datetime] = None,
        last_backfill_timekey: Optional[int] = None,
        last_ingest_time: Optional[datetime] = None,
        last_ingest_timekey: Optional[int] = None,
        backfill_complete: bool = False,
        error_count: int = 0,
        last_error: Optional[str] = None
    ) -> None:
        """Update ingestion state for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ingestion_state
                (symbol, last_backfill_time, last_backfill_timekey,
                 last_ingest_time, last_ingest_timekey,
                 backfill_complete, error_count, last_error, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (symbol)
                DO UPDATE SET
                    last_backfill_time = COALESCE(EXCLUDED.last_backfill_time, ingestion_state.last_backfill_time),
                    last_backfill_timekey = COALESCE(EXCLUDED.last_backfill_timekey, ingestion_state.last_backfill_timekey),
                    last_ingest_time = COALESCE(EXCLUDED.last_ingest_time, ingestion_state.last_ingest_time),
                    last_ingest_timekey = COALESCE(EXCLUDED.last_ingest_timekey, ingestion_state.last_ingest_timekey),
                    backfill_complete = EXCLUDED.backfill_complete,
                    error_count = EXCLUDED.error_count,
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
            """, symbol, last_backfill_time, last_backfill_timekey,
                last_ingest_time, last_ingest_timekey,
                backfill_complete, error_count, last_error)

    async def increment_error_count(self, symbol: str, error: str) -> None:
        """Increment error count for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ingestion_state (symbol, error_count, last_error, updated_at)
                VALUES ($1, 1, $2, NOW())
                ON CONFLICT (symbol)
                DO UPDATE SET
                    error_count = ingestion_state.error_count + 1,
                    last_error = $2,
                    updated_at = NOW()
            """, symbol, error)

    # =====================================================
    # Gap Detection Methods
    # =====================================================

    async def detect_gaps(
        self,
        symbol: str,
        interval: str = "1m",
        gap_threshold_minutes: int = 5
    ) -> List[dict]:
        """
        Detect gaps in data for a symbol

        Returns:
            List of gap information dictionaries
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM detect_data_gap($1, $2, $3)
            """, symbol, interval, gap_threshold_minutes)

            return [dict(row) for row in rows]

    async def get_last_data_time(self, symbol: str, interval: str = "1m") -> Optional[datetime]:
        """Get the timestamp of the last data point for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT time FROM market_features
                WHERE symbol = $1 AND interval = $2
                ORDER BY time DESC
                LIMIT 1
            """, symbol, interval)

            return row['time'] if row else None

    # =====================================================
    # Materialized View Refresh
    # =====================================================

    async def refresh_continuous_aggregates(self) -> List[dict]:
        """
        Manually refresh all continuous aggregate materialized views

        Returns:
            List of refresh results for each view
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        views = [
            "market_features_5m",
            "market_features_15m",
            "market_features_30m",
            "market_features_1h",
            "market_features_4h",
            "market_features_1d",
            "market_features_1w"
        ]

        results = []
        for view in views:
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                    results.append({"view": view, "status": "success"})
                    logger.info(f"Refreshed materialized view: {view}")
            except Exception as e:
                results.append({"view": view, "status": "error", "error": str(e)})
                logger.error(f"Failed to refresh {view}: {e}")

        return results

    # =====================================================
    # Aggregated Timeframe Methods (Materialized Views)
    # =====================================================

    async def query_aggregated(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> List:
        """Query aggregated data from materialized views"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        view_map = {
            "5m": "market_features_5m",
            "15m": "market_features_15m",
            "30m": "market_features_30m",
            "1h": "market_features_1h",
            "4h": "market_features_4h",
            "1d": "market_features_1d",
            "1w": "market_features_1w"
        }

        if interval not in view_map:
            raise ValueError(f"Invalid interval '{interval}'. Use one of: {', '.join(view_map.keys())} or '1m'")

        view_name = view_map[interval]

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT bucket AS time, timekey, symbol,
                       open, high, low, close, volume
                FROM """ + view_name + """
                WHERE symbol = $1
                  AND bucket BETWEEN $2 AND $3
                ORDER BY bucket ASC
            """, symbol, start, end)

            from services.ingestion.models.market_data_v2 import MarketData

            return [
                MarketData(
                    time=row['time'],
                    symbol=row['symbol'],
                    interval=interval,
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    volume=row['volume'],
                    indicators=None,
                    sentiment=None
                )
                for row in rows
            ]

    # =====================================================
    # Data Count Statistics
    # =====================================================

    async def get_data_count(self, symbol: str, interval: str = "1m") -> int:
        """Get count of data points for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT COUNT(*) FROM market_features
                WHERE symbol = $1 AND interval = $2
            """, symbol, interval)

    async def get_data_range(
        self,
        symbol: str,
        interval: str = "1m"
    ) -> Optional[tuple[datetime, datetime]]:
        """Get the time range of data for a symbol"""
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    MIN(time) AS min_time,
                    MAX(time) AS max_time
                FROM market_features
                WHERE symbol = $1 AND interval = $2
            """, symbol, interval)

            if row and row['min_time']:
                return (row['min_time'], row['max_time'])
            return None
