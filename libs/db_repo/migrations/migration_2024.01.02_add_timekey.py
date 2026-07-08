"""
Migration: Add timekey column and update primary key

Author: Tradebase
Version: 2024.01.02

This migration:
1. Adds timekey column (YYYYMMDDHHMM format as BIGINT) to market_features
2. Changes primary key from (time, symbol, interval) to (timekey, symbol)
3. Updates all materialized views with timekey
4. Disables auto-refresh policies
5. Adds ingestion_state table for resume capability
"""

import logging
from typing import List
from libs.db_repo.migrations.migration import Migration

logger = logging.getLogger(__name__)


class Migration_20240102(Migration):
    """Migration 2024.01.02: Add timekey column and update primary key"""

    version = "2024.01.02"
    description = "Add timekey column and update primary key"
    author = "Tradebase"
    depends_on = ["2024.01.01"]

    async def up(self) -> None:
        """Apply migration"""
        async with self.pool.acquire() as conn:
            # Step 1: Create timekey generation function (returns BIGINT)
            await conn.execute("""
                CREATE OR REPLACE FUNCTION generate_timekey(ts TIMESTAMPTZ)
                RETURNS BIGINT AS $$
                BEGIN
                    RETURN (TO_CHAR(ts, 'YYYYMMDDHH24MI'))::BIGINT;
                END;
                $$ LANGUAGE plpgsql IMMUTABLE;
            """)
            logger.info("Created generate_timekey function (BIGINT)")

            # Step 2: Add timekey column to market_features
            # First check if column exists to avoid errors
            column_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'market_features'
                    AND column_name = 'timekey'
                );
            """)

            if not column_exists:
                await conn.execute("""
                    ALTER TABLE market_features
                    ADD COLUMN timekey BIGINT
                    GENERATED ALWAYS AS (generate_timekey(time)) STORED;
                """)
                logger.info("Added timekey column (BIGINT) to market_features")
            else:
                logger.info("timekey column already exists")

            # Step 3: Drop existing primary key and add new one
            # Check current primary key
            pk_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'market_features'
                    AND constraint_type = 'PRIMARY KEY'
                );
            """)

            if pk_exists:
                # Drop old primary key
                await conn.execute("""
                    ALTER TABLE market_features DROP CONSTRAINT market_features_pkey;
                """)
                logger.info("Dropped old primary key")

            # Add new primary key on (timekey, symbol)
            # First check if it already exists
            new_pk_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'market_features'
                    AND constraint_name = 'market_features_pkey'
                );
                """)

            if not new_pk_exists:
                await conn.execute("""
                    ALTER TABLE market_features ADD PRIMARY KEY (time, timekey, symbol);
                """)
                logger.info("Added new primary key (time, timekey, symbol)")

            # Step 4: Drop old materialized views and recreate with timekey
            for view_name in ['market_features_5m', 'market_features_15m',
                             'market_features_30m', 'market_features_1h',
                             'market_features_4h', 'market_features_1d',
                             'market_features_1w']:
                # Check if view exists and needs to be updated
                view_has_timekey = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = $1
                        AND column_name = 'timekey'
                    );
                """, view_name)

                if not view_has_timekey:
                    # Drop and recreate view
                    intervals = {
                        'market_features_5m': ('5 minutes', '5m'),
                        'market_features_15m': ('15 minutes', '15m'),
                        'market_features_30m': ('30 minutes', '30m'),
                        'market_features_1h': ('1 hour', '1h'),
                        'market_features_4h': ('4 hours', '4h'),
                        'market_features_1d': ('1 day', '1d'),
                        'market_features_1w': ('1 week', '1w'),
                    }
                    bucket_interval, _ = intervals[view_name]

                    await conn.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view_name} CASCADE;")
                    await conn.execute(f"""
                        CREATE MATERIALIZED VIEW {view_name}
                        WITH (timescaledb.continuous) AS
                        SELECT
                            time_bucket('{bucket_interval}', time) AS bucket,
                            generate_timekey(time_bucket('{bucket_interval}', time)) AS timekey,
                            symbol,
                            first(open, time) AS open,
                            max(high) AS high,
                            min(low) AS low,
                            last(close, time) AS close,
                            sum(volume) AS volume
                        FROM market_features
                        WHERE interval = '1m'
                        GROUP BY bucket, timekey, symbol;
                    """)
                    logger.info(f"Recreated materialized view {view_name} with timekey")

            # Step 5: Remove auto-refresh policies (manual refresh only)
            # Remove continuous aggregate policies
            policies_exist = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.jobs
                    WHERE proc_name = 'policy_refresh_continuous_aggregate'
                );
            """)

            if policies_exist:
                # Remove all continuous aggregate refresh policies
                for view_name in ['market_features_5m', 'market_features_15m',
                                 'market_features_30m', 'market_features_1h',
                                 'market_features_4h', 'market_features_1d',
                                 'market_features_1w']:
                    try:
                        await conn.execute(f"""
                            SELECT remove_continuous_aggregate_policy('{view_name}');
                        """)
                    except Exception:
                        pass  # Policy might not exist
                logger.info("Removed auto-refresh policies")

            # Step 6: Create manual refresh function
            await conn.execute("""
                CREATE OR REPLACE FUNCTION refresh_continuous_aggregates()
                RETURNS TABLE(view_name TEXT, rows_affected BIGINT) AS $$
                DECLARE
                    view_rec RECORD;
                BEGIN
                    FOR view_rec IN
                        SELECT viewname
                        FROM pg_matviews
                        WHERE schemaname = 'public'
                          AND viewname LIKE 'market_features_%'
                        ORDER BY viewname
                    LOOP
                        EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', view_rec.viewname);
                        RETURN NEXT;
                    END LOOP;
                    RETURN;
                END;
                $$ LANGUAGE plpgsql;
            """)
            logger.info("Created manual refresh function")

            # Step 7: Create ingestion_state table for resume capability
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'ingestion_state'
                );
            """)

            if not table_exists:
                await conn.execute("""
                    CREATE TABLE ingestion_state (
                        symbol VARCHAR(20) PRIMARY KEY,
                        last_backfill_time TIMESTAMPTZ,
                        last_backfill_timekey VARCHAR(12),
                        last_ingest_time TIMESTAMPTZ,
                        last_ingest_timekey VARCHAR(12),
                        backfill_complete BOOLEAN DEFAULT FALSE,
                        error_count INTEGER DEFAULT 0,
                        last_error TEXT,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                logger.info("Created ingestion_state table")

            # Step 8: Create gap detection function
            await conn.execute("""
                CREATE OR REPLACE FUNCTION detect_data_gap(
                    p_symbol VARCHAR(20),
                    p_interval VARCHAR DEFAULT '1m',
                    p_gap_minutes INTEGER DEFAULT 5
                ) RETURNS TABLE(
                    gap_start TIMESTAMPTZ,
                    gap_end TIMESTAMPTZ,
                    gap_minutes INTEGER
                ) AS $$
                BEGIN
                    RETURN QUERY
                    WITH ranked_data AS (
                        SELECT
                            time,
                            LEAD(time) OVER (ORDER BY time) - time AS time_diff
                        FROM market_features
                        WHERE symbol = p_symbol
                          AND interval = p_interval
                        ORDER BY time DESC
                    )
                    SELECT
                        time AS gap_start,
                        time + (time_diff - INTERVAL '1 minute') AS gap_end,
                        EXTRACT(EPOCH FROM (time_diff - INTERVAL '1 minute')) / 60 AS gap_minutes
                    FROM ranked_data
                    WHERE time_diff > INTERVAL '1 minute'
                      AND time_diff > (p_gap_minutes || ' minutes')::INTERVAL;
                END;
                $$ LANGUAGE plpgsql;
            """)
            logger.info("Created gap detection function")

            logger.info("Migration 2024.01.02 completed successfully")

    async def down(self) -> None:
        """Rollback migration"""
        async with self.pool.acquire() as conn:
            # This is a complex migration with many changes
            # Full rollback would require:
            # 1. Restoring old primary key
            # 2. Removing timekey column
            # 3. Recreating old views
            # 4. Restoring auto-refresh policies
            # For safety, we only drop newly created objects

            await conn.execute("DROP FUNCTION IF EXISTS detect_data_gap CASCADE;")
            await conn.execute("DROP TABLE IF EXISTS ingestion_state;")
            await conn.execute("DROP FUNCTION IF EXISTS refresh_continuous_aggregates;")

            logger.warning("Partial rollback: Only dropped new objects")
            logger.warning("Manual intervention required to restore old schema")
