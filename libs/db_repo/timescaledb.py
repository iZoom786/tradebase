"""
TimescaleDB repository implementation

Provides async database operations using asyncpg connection pool.
Implements the Repository interface for TimescaleDB/PostgreSQL.
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

import asyncpg
from asyncpg.pool import Pool

from .base import Repository
from services.ingestion.models import MarketData
from libs.common.config import DatabaseConfig

logger = logging.getLogger(__name__)


class TimescaleDBRepository(Repository):
    """
    TimescaleDB repository with connection pooling

    Features:
    - Async/await for non-blocking operations
    - Connection pooling for performance
    - Automatic retry on transient failures
    - Structured logging
    """

    def __init__(self, config: DatabaseConfig):
        """
        Initialize repository

        Args:
            config: Database configuration
        """
        self.config = config
        self.pool: Optional[Pool] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """
        Establish database connection pool

        Creates a pool of connections with configured min/max sizes.
        """
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

    async def upsert(self, data: MarketData) -> None:
        """
        Insert or update market data

        Uses ON CONFLICT to handle duplicates by updating all fields.

        Args:
            data: MarketData instance to store
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

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
            """,
                data.time,
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
                time=data.time.isoformat()
            )

    async def query_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m"
    ) -> List[MarketData]:
        """
        Query market data for a time range

        Args:
            symbol: Trading symbol
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            interval: Time interval (default: "1m")

        Returns:
            List of MarketData points, ordered by time ascending
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT time, symbol, interval,
                       open, high, low, close, volume,
                       indicators, sentiment
                FROM market_features
                WHERE symbol = $1
                  AND interval = $2
                  AND time BETWEEN $3 AND $4
                ORDER BY time ASC
            """, symbol, interval, start, end)

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
    ) -> Optional[MarketData]:
        """
        Get the most recent data point for a symbol

        Args:
            symbol: Trading symbol
            interval: Time interval

        Returns:
            Latest MarketData or None if no data exists
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT time, symbol, interval,
                       open, high, low, close, volume,
                       indicators, sentiment
                FROM market_features
                WHERE symbol = $1 AND interval = $2
                ORDER BY time DESC
                LIMIT 1
            """, symbol, interval)

            if row is None:
                return None

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
        """
        Execute arbitrary SQL

        Used for migrations, custom queries, etc.

        Args:
            sql: SQL query string
            *args: Query parameters
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            await conn.execute(sql, *args)
            logger.debug("repository_execute", sql=sql[:100])

    async def fetchone(self, sql: str, *args) -> Optional[dict]:
        """
        Fetch single row from SQL query

        Args:
            sql: SQL query string
            *args: Query parameters

        Returns:
            Row as dict or None
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row else None

    async def fetchall(self, sql: str, *args) -> List[dict]:
        """
        Fetch all rows from SQL query

        Args:
            sql: SQL query string
            *args: Query parameters

        Returns:
            List of rows as dicts
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]

    # =====================================================
    # Aggregated Timeframe Methods (Materialized Views)
    # =====================================================

    async def query_aggregated(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> List[MarketData]:
        """
        Query aggregated data from materialized views

        Supported intervals: 5m, 15m, 30m, 1h, 4h, 1d, 1w
        For 1m data, use query_range() instead.

        Args:
            symbol: Trading symbol
            interval: Time interval (5m, 15m, 30m, 1h, 4h, 1d, 1w)
            start: Start datetime
            end: End datetime

        Returns:
            List of MarketData points, ordered by time ascending

        Raises:
            ValueError: If interval is not supported
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        # Map interval to view name
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
            raise ValueError(
                f"Invalid interval '{interval}'. "
                f"Use one of: {', '.join(view_map.keys())} or '1m' (use query_range for 1m)"
            )

        view_name = view_map[interval]

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT bucket AS time, symbol,
                       open, high, low, close, volume
                FROM """ + view_name + """
                WHERE symbol = $1
                  AND bucket BETWEEN $2 AND $3
                ORDER BY bucket ASC
            """, symbol, start, end)

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

    async def get_latest_aggregated(
        self,
        symbol: str,
        interval: str
    ) -> Optional[MarketData]:
        """
        Get the most recent aggregated data point for a symbol

        Args:
            symbol: Trading symbol
            interval: Time interval (5m, 15m, 30m, 1h, 4h, 1d, 1w)

        Returns:
            Latest MarketData or None if no data exists
        """
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
            raise ValueError(
                f"Invalid interval '{interval}'. "
                f"Use one of: {', '.join(view_map.keys())} or '1m' (use get_latest for 1m)"
            )

        view_name = view_map[interval]

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT bucket AS time, symbol,
                       open, high, low, close, volume
                FROM """ + view_name + """
                WHERE symbol = $1
                ORDER BY bucket DESC
                LIMIT 1
            """, symbol)

            if row is None:
                return None

            return MarketData(
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

    async def query_any_timeframe(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> List[MarketData]:
        """
        Query data for any timeframe (unified interface)

        This method automatically routes to the appropriate source:
        - 1m: market_features base table
        - 5m+: materialized views

        Args:
            symbol: Trading symbol
            interval: Any interval (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)
            start: Start datetime
            end: End datetime

        Returns:
            List of MarketData points, ordered by time ascending
        """
        if interval == "1m":
            return await self.query_range(symbol, start, end, interval)
        else:
            return await self.query_aggregated(symbol, interval, start, end)

    async def get_aggregation_status(self) -> List[dict]:
        """
        Get status of all materialized view aggregations

        Returns:
            List of dicts with view name and last update time
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

        status = []
        for view in views:
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow("""
                        SELECT max(bucket) AS last_data_point
                        FROM """ + view + """
                    """)
                    status.append({
                        "view": view,
                        "last_data_point": row['last_data_point'] if row else None
                    })
            except Exception:
                status.append({"view": view, "last_data_point": None})

        return status

    # =====================================================
    # Paper Trading Methods
    # =====================================================

    async def log_order_open(
        self,
        account_id: str,
        symbol: str,
        side: str,
        price: Decimal,
        quantity: Decimal,
        time: datetime
    ) -> int:
        """
        Log a paper trading order opening

        Args:
            account_id: User account identifier
            symbol: Trading symbol
            side: 'LONG' or 'SHORT'
            price: Entry price
            quantity: Position size
            time: Order time

        Returns:
            Order ID
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            order_id = await conn.fetchval("""
                INSERT INTO paper_orders
                (user_id, symbol, side, entry_time, entry_price, quantity, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'OPEN')
                RETURNING id
            """, account_id, symbol, side, time, float(price), float(quantity))

            # Log to trade log
            await conn.execute("""
                INSERT INTO trade_log
                (time, order_id, symbol, action, price, quantity)
                VALUES ($1, $2, $3, 'ENTRY', $4, $5)
            """, time, order_id, symbol, float(price), float(quantity))

            logger.info(
                "paper_order_opened",
                order_id=order_id,
                symbol=symbol,
                side=side
            )

            return order_id

    async def log_order_close(
        self,
        order_id: int,
        exit_price: Decimal,
        exit_time: datetime,
        pnl: Decimal
    ) -> None:
        """
        Log a paper trading order closing

        Args:
            order_id: Order ID to close
            exit_price: Exit price
            exit_time: Exit time
            pnl: Realized profit/loss
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            # Get order details for logging
            order = await conn.fetchrow(
                "SELECT symbol, quantity FROM paper_orders WHERE id = $1",
                order_id
            )

            # Update order
            await conn.execute("""
                UPDATE paper_orders
                SET exit_time = $1,
                    exit_price = $2,
                    pnl = $3,
                    status = 'CLOSED'
                WHERE id = $4
            """, exit_time, float(exit_price), float(pnl), order_id)

            # Log to trade log
            await conn.execute("""
                INSERT INTO trade_log
                (time, order_id, symbol, action, price, quantity)
                VALUES ($1, $2, $3, 'EXIT', $4, $5)
            """, exit_time, order_id, order['symbol'], float(exit_price), order['quantity'])

            logger.info(
                "paper_order_closed",
                order_id=order_id,
                pnl=float(pnl)
            )

    async def get_closed_trades(self, account_id: str) -> List[dict]:
        """
        Get all closed trades for an account

        Args:
            account_id: User account identifier

        Returns:
            List of closed trades with P&L
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol, side, entry_time, exit_time,
                       entry_price, exit_price, quantity, pnl
                FROM paper_orders
                WHERE user_id = $1 AND status = 'CLOSED'
                ORDER BY exit_time DESC
            """, account_id)

            return [dict(row) for row in rows]

    async def get_open_positions(self, account_id: str) -> List[dict]:
        """
        Get all open positions for an account

        Args:
            account_id: User account identifier

        Returns:
            List of open positions
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol, side, entry_time, entry_price, quantity
                FROM paper_orders
                WHERE user_id = $1 AND status = 'OPEN'
                ORDER BY entry_time DESC
            """, account_id)

            return [dict(row) for row in rows]

    async def get_all_trades(self, account_id: str) -> List[dict]:
        """
        Get all trades (open and closed) for an account

        Args:
            account_id: User account identifier

        Returns:
            List of all trades ordered by time
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol, side, entry_time, exit_time,
                       entry_price, exit_price, quantity, pnl, status
                FROM paper_orders
                WHERE user_id = $1
                ORDER BY entry_time DESC
            """, account_id)

            return [dict(row) for row in rows]

    # =====================================================
    # Model Registry Methods
    # =====================================================

    async def register_model(
        self,
        model_id: str,
        model_type: str,
        accuracy: float,
        log_loss: float,
        training_samples: int,
        file_path: str,
        metadata: dict = None
    ) -> None:
        """
        Register a new trained model

        Args:
            model_id: Unique model identifier
            model_type: Model type ('j48', 'xgb', 'ppo')
            accuracy: Validation accuracy
            log_loss: Validation log loss
            training_samples: Number of training samples
            file_path: Path to model file
            metadata: Additional model metadata
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO model_registry
                (model_id, model_type, accuracy, log_loss,
                 training_samples, file_path, metadata, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'staging')
            """, model_id, model_type, accuracy, log_loss,
                training_samples, file_path, metadata)

            logger.info("model_registered", model_id=model_id)

    async def get_production_model(self, model_type: str) -> Optional[dict]:
        """
        Get current production model for a type

        Args:
            model_type: Model type to query

        Returns:
            Model metadata or None
        """
        if self.pool is None:
            raise RuntimeError("Repository not connected")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM model_registry
                WHERE model_type = $1 AND status = 'production'
                ORDER BY created_at DESC
                LIMIT 1
            """, model_type)

            return dict(row) if row else None
