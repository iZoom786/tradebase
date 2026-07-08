"""
Migration: Initial Schema

Author: Tradebase Team
Version: 2024.01.01
"""

from libs.db_repo.migrations import Migration
import logging

logger = logging.getLogger(__name__)


class Migration_20240101(Migration):
    """Initial database schema with hypertables and aggregates"""

    version = "2024.01.01"
    description = "Initial schema with hypertables and materialized views"
    author = "Tradebase Team"
    depends_on = []

    async def up(self) -> None:
        """Apply initial schema"""
        async with self.pool.acquire() as conn:
            # =====================================================
            # Market Features Hypertable
            # =====================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_features (
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
            """)

            # Convert to hypertable
            try:
                await conn.execute("""
                    SELECT create_hypertable('market_features', 'time',
                        chunk_time_interval => INTERVAL '1 day')
                """)
            except Exception as e:
                if "already a hypertable" not in str(e):
                    raise

            # Enable compression
            await conn.execute("""
                SELECT add_compression_policy('market_features',
                    INTERVAL '7 days')
            """)

            # Enable retention
            await conn.execute("""
                SELECT add_retention_policy('market_features',
                    INTERVAL '1 year')
            """)

            # =====================================================
            # Paper Orders Table
            # =====================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    entry_time TIMESTAMPTZ NOT NULL,
                    exit_time TIMESTAMPTZ,
                    entry_price DOUBLE PRECISION,
                    exit_price DOUBLE PRECISION,
                    quantity DOUBLE PRECISION,
                    pnl DOUBLE PRECISION,
                    status VARCHAR(20) DEFAULT 'OPEN',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_paper_orders_user
                ON paper_orders(user_id, status);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol
                ON paper_orders(symbol, entry_time DESC);
            """)

            # =====================================================
            # Trade Log Table
            # =====================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_log (
                    time TIMESTAMPTZ NOT NULL,
                    order_id INTEGER REFERENCES paper_orders(id),
                    symbol VARCHAR(20),
                    action VARCHAR(20),
                    price DOUBLE PRECISION,
                    quantity DOUBLE PRECISION,
                    metadata JSONB
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_log_time
                ON trade_log(time DESC);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_log_order
                ON trade_log(order_id);
            """)

            # =====================================================
            # Model Registry
            # =====================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS model_registry (
                    model_id VARCHAR(100) PRIMARY KEY,
                    model_type VARCHAR(50) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    accuracy DOUBLE PRECISION,
                    log_loss DOUBLE PRECISION,
                    training_samples INTEGER,
                    status VARCHAR(20) DEFAULT 'staging',
                    file_path TEXT,
                    metadata JSONB
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_registry_status
                ON model_registry(status);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_registry_type
                ON model_registry(model_type, created_at DESC);
            """)

            # =====================================================
            # Users Table
            # =====================================================
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id UUID PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    tier VARCHAR(20) DEFAULT 'trial',
                    subscription_expires TIMESTAMPTZ,
                    nkey_public VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    is_active BOOLEAN DEFAULT TRUE
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_tier
                ON users(tier);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_active
                ON users(is_active) WHERE is_active = TRUE;
            """)

            # =====================================================
            # Continuous Aggregates (Materialized Views)
            # =====================================================
            # 5-minute aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_5m
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('5 minutes', time) AS bucket,
                    symbol,
                    first(open, time) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, time) AS close,
                    sum(volume) AS volume
                FROM market_features
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_5m',
                    start_offset => INTERVAL '5 minutes',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '5 minutes');
            """)

            # 15-minute aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_15m
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('15 minutes', time) AS bucket,
                    symbol,
                    first(open, time) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, time) AS close,
                    sum(volume) AS volume
                FROM market_features
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_15m',
                    start_offset => INTERVAL '15 minutes',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '15 minutes');
            """)

            # 30-minute aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_30m
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('30 minutes', time) AS bucket,
                    symbol,
                    first(open, time) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, time) AS close,
                    sum(volume) AS volume
                FROM market_features
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_30m',
                    start_offset => INTERVAL '30 minutes',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '30 minutes');
            """)

            # 1-hour aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_1h
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
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_1h',
                    start_offset => INTERVAL '1 hour',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '1 hour');
            """)

            # 4-hour aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_4h
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('4 hours', time) AS bucket,
                    symbol,
                    first(open, time) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, time) AS close,
                    sum(volume) AS volume
                FROM market_features
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_4h',
                    start_offset => INTERVAL '4 hours',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '1 hour');
            """)

            # 1-day aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_1d
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 day', time) AS bucket,
                    symbol,
                    first(open, time) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, time) AS close,
                    sum(volume) AS volume
                FROM market_features
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_1d',
                    start_offset => INTERVAL '1 day',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '1 day');
            """)

            # 1-week aggregate
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_1w
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 week', time) AS bucket,
                    symbol,
                    first(open, time) AS open,
                    max(high) AS high,
                    min(low) AS low,
                    last(close, time) AS close,
                    sum(volume) AS volume
                FROM market_features
                WHERE interval = '1m'
                GROUP BY bucket, symbol;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('market_features_1w',
                    start_offset => INTERVAL '1 week',
                    end_offset => INTERVAL '1 second',
                    schedule_interval => INTERVAL '1 day');
            """)

            # =====================================================
            # Helper View: All Timeframes
            # =====================================================
            await conn.execute("""
                CREATE OR REPLACE VIEW market_data_all_timeframes AS
                SELECT
                    time AS bucket,
                    symbol,
                    '1m' AS interval,
                    open, high, low, close, volume
                FROM market_features
                WHERE interval = '1m'
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '5m' AS interval,
                    open, high, low, close, volume
                FROM market_features_5m
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '15m' AS interval,
                    open, high, low, close, volume
                FROM market_features_15m
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '30m' AS interval,
                    open, high, low, close, volume
                FROM market_features_30m
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '1h' AS interval,
                    open, high, low, close, volume
                FROM market_features_1h
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '4h' AS interval,
                    open, high, low, close, volume
                FROM market_features_4h
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '1d' AS interval,
                    open, high, low, close, volume
                FROM market_features_1d
                UNION ALL
                SELECT
                    bucket AS time,
                    symbol,
                    '1w' AS interval,
                    open, high, low, close, volume
                FROM market_features_1w
                ORDER BY time DESC;
            """)

        self.log("Initial schema created successfully")

    async def down(self) -> None:
        """Rollback initial schema"""
        async with self.pool.acquire() as conn:
            # Drop all objects in reverse order of creation
            await conn.execute("DROP VIEW IF EXISTS market_data_all_timeframes CASCADE;")

            # Drop materialized views
            views = [
                "market_features_1w",
                "market_features_1d",
                "market_features_4h",
                "market_features_1h",
                "market_features_30m",
                "market_features_15m",
                "market_features_5m"
            ]
            for view in views:
                try:
                    await conn.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view} CASCADE;")
                    await conn.execute(f"SELECT remove_continuous_aggregate_policy('{view}');")
                except Exception:
                    pass

            # Drop tables
            await conn.execute("DROP TABLE IF EXISTS trade_log CASCADE;")
            await conn.execute("DROP TABLE IF EXISTS paper_orders CASCADE;")
            await conn.execute("DROP TABLE IF EXISTS model_registry CASCADE;")
            await conn.execute("DROP TABLE IF EXISTS users CASCADE;")
            await conn.execute("DROP TABLE IF EXISTS market_features CASCADE;")

        self.log("Initial schema rolled back")
