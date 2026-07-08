-- TimescaleDB initialization script for Tradebase Platform (v2.0)
-- Changes:
-- - Added timekey column (YYYYMMDDHHMM format)
-- - Changed primary key to (timekey, symbol)
-- - Deactivated auto-refresh on materialized views (manual refresh)
-- - Enhanced for 1-year backfill support

-- Create database if it doesn't exist (already created by POSTGRES_DB env var)
-- CREATE DATABASE tradebase;

-- Connect to tradebase database
\c tradebase

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =====================================================
-- Helper Function: Generate Timekey
-- =====================================================
-- Generates timekey in YYYYMMDDHHMM format as BIGINT
-- Example: 2024-01-15 14:30:00 → 202401151430
CREATE OR REPLACE FUNCTION generate_timekey(ts TIMESTAMPTZ) RETURNS BIGINT AS $$
BEGIN
    RETURN (TO_CHAR(ts, 'YYYYMMDDHH24MI'))::BIGINT;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- Market Features Hypertable (v2.0)
-- =====================================================
CREATE TABLE IF NOT EXISTS market_features (
    time TIMESTAMPTZ NOT NULL,
    timekey BIGINT GENERATED ALWAYS AS (generate_timekey(time)) STORED,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL DEFAULT '1m',
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    indicators JSONB,
    sentiment JSONB,
    -- Primary key includes partitioning column (time) for hypertable compatibility
    PRIMARY KEY (time, timekey, symbol)
);

-- Convert to hypertable (creates chunks for time-based partitioning)
SELECT create_hypertable('market_features', 'time',
    chunk_time_interval => INTERVAL '1 day');

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_market_features_time ON market_features(time DESC);
CREATE INDEX IF NOT EXISTS idx_market_features_symbol_time ON market_features(symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_market_features_interval ON market_features(interval);

-- Enable compression (disabled for now - requires columnstore)
-- SELECT add_compression_policy('market_features', INTERVAL '7 days');

-- Enable retention (disabled for now - requires compression)
-- SELECT add_retention_policy('market_features', INTERVAL '1 year');

-- =====================================================
-- Paper Orders Table
-- =====================================================
CREATE TABLE IF NOT EXISTS paper_orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'LONG' or 'SHORT'
    entry_time TIMESTAMPTZ NOT NULL,
    entry_timekey BIGINT GENERATED ALWAYS AS (generate_timekey(entry_time)) STORED,
    exit_time TIMESTAMPTZ,
    exit_timekey BIGINT,
    entry_price DOUBLE PRECISION,
    exit_price DOUBLE PRECISION,
    quantity DOUBLE PRECISION,
    pnl DOUBLE PRECISION,
    status VARCHAR(20) DEFAULT 'OPEN',  -- 'OPEN', 'CLOSED'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_orders_user ON paper_orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders(symbol, entry_time DESC);

-- =====================================================
-- Trade Log Table
-- =====================================================
CREATE TABLE IF NOT EXISTS trade_log (
    time TIMESTAMPTZ NOT NULL,
    timekey BIGINT GENERATED ALWAYS AS (generate_timekey(time)) STORED,
    order_id INTEGER REFERENCES paper_orders(id),
    symbol VARCHAR(20),
    action VARCHAR(20),  -- 'ENTRY', 'EXIT', 'MODIFY'
    price DOUBLE PRECISION,
    quantity DOUBLE PRECISION,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_trade_log_time ON trade_log(time DESC);
CREATE INDEX IF NOT EXISTS idx_trade_log_order ON trade_log(order_id);

-- =====================================================
-- Model Registry
-- =====================================================
CREATE TABLE IF NOT EXISTS model_registry (
    model_id VARCHAR(100) PRIMARY KEY,
    model_type VARCHAR(50) NOT NULL,  -- 'j48', 'xgb', 'ppo'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accuracy DOUBLE PRECISION,
    log_loss DOUBLE PRECISION,
    training_samples INTEGER,
    status VARCHAR(20) DEFAULT 'staging',  -- 'staging', 'production', 'archived'
    file_path TEXT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_model_registry_status ON model_registry(status);
CREATE INDEX IF NOT EXISTS idx_model_registry_type ON model_registry(model_type, created_at DESC);

-- =====================================================
-- Users Table
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    tier VARCHAR(20) DEFAULT 'trial',  -- 'trial', 'basic', 'premium'
    subscription_expires TIMESTAMPTZ,
    nkey_public VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active) WHERE is_active = TRUE;

-- =====================================================
-- Ingestion State Tracking (for resume capability)
-- =====================================================
CREATE TABLE IF NOT EXISTS ingestion_state (
    symbol VARCHAR(20) PRIMARY KEY,
    last_backfill_time TIMESTAMPTZ,
    last_backfill_timekey BIGINT,
    last_ingest_time TIMESTAMPTZ,
    last_ingest_timekey BIGINT,
    backfill_complete BOOLEAN DEFAULT FALSE,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_state_time ON ingestion_state(last_backfill_time DESC);

-- =====================================================
-- Continuous Aggregates (Materialized Views) - v2.0
-- =====================================================
-- IMPORTANT: Auto-refresh policies are DISABLED
-- Use refresh_continuous_aggregates() function for manual refresh
-- =====================================================

-- Drop existing views if any (for fresh start)
DROP MATERIALIZED VIEW IF EXISTS market_features_5m CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_features_15m CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_features_30m CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_features_1h CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_features_4h CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_features_1d CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_features_1w CASCADE;

-- 5-minute aggregate
CREATE MATERIALIZED VIEW market_features_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    generate_timekey(time_bucket('5 minutes', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- 15-minute aggregate
CREATE MATERIALIZED VIEW market_features_15m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', time) AS bucket,
    generate_timekey(time_bucket('15 minutes', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- 30-minute aggregate
CREATE MATERIALIZED VIEW market_features_30m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('30 minutes', time) AS bucket,
    generate_timekey(time_bucket('30 minutes', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- 1-hour aggregate
CREATE MATERIALIZED VIEW market_features_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    generate_timekey(time_bucket('1 hour', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- 4-hour aggregate
CREATE MATERIALIZED VIEW market_features_4h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('4 hours', time) AS bucket,
    generate_timekey(time_bucket('4 hours', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- 1-day aggregate
CREATE MATERIALIZED VIEW market_features_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    generate_timekey(time_bucket('1 day', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- 1-week aggregate
CREATE MATERIALIZED VIEW market_features_1w
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 week', time) AS bucket,
    generate_timekey(time_bucket('1 week', time)) AS timekey,
    symbol,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume
FROM market_features
WHERE interval = '1m'
GROUP BY bucket, timekey, symbol;

-- =====================================================
-- Manual Refresh Function for Materialized Views
-- =====================================================
-- Refreshes all continuous aggregates manually
-- Call this after large backfills or periodically
CREATE OR REPLACE FUNCTION refresh_continuous_aggregates()
RETURNS TABLE(view_name TEXT, rows_affected BIGINT) AS $$
DECLARE
    view_rec RECORD;
    row_count BIGINT;
BEGIN
    FOR view_rec IN
        SELECT matviewname
        FROM pg_matviews
        WHERE schemaname = 'public'
          AND matviewname LIKE 'market_features_%'
        ORDER BY matviewname
    LOOP
        EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', view_rec.matviewname);
        GET DIAGNOSTICS row_count = ROW_COUNT;
        RETURN NEXT;
    END LOOP;
    RETURN;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Helper View: All Timeframes for a Symbol (v2.0)
-- =====================================================
CREATE OR REPLACE VIEW market_data_all_timeframes AS
SELECT
    time AS bucket,
    timekey,
    symbol,
    '1m' AS interval,
    open, high, low, close, volume
FROM market_features
WHERE interval = '1m'

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '5m' AS interval,
    open, high, low, close, volume
FROM market_features_5m

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '15m' AS interval,
    open, high, low, close, volume
FROM market_features_15m

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '30m' AS interval,
    open, high, low, close, volume
FROM market_features_30m

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '1h' AS interval,
    open, high, low, close, volume
FROM market_features_1h

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '4h' AS interval,
    open, high, low, close, volume
FROM market_features_4h

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '1d' AS interval,
    open, high, low, close, volume
FROM market_features_1d

UNION ALL

SELECT
    bucket AS time,
    timekey,
    symbol,
    '1w' AS interval,
    open, high, low, close, volume
FROM market_features_1w

ORDER BY bucket DESC;

-- =====================================================
-- Data Gap Detection Function
-- =====================================================
-- Finds gaps in data for a symbol and interval
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
        (EXTRACT(EPOCH FROM (time_diff - INTERVAL '1 minute')) / 60)::INTEGER AS gap_minutes
    FROM ranked_data
    WHERE time_diff > INTERVAL '1 minute'
      AND time_diff > (p_gap_minutes || ' minutes')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Grant permissions
-- =====================================================
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tradebase;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tradebase;

-- Log initialization completion
DO $$
BEGIN
    RAISE NOTICE 'Tradebase database v2.0 initialized successfully';
    RAISE NOTICE '- timekey column added as BIGINT (YYYYMMDDHHMM format)';
    RAISE NOTICE '- Primary key changed to (timekey, symbol)';
    RAISE NOTICE '- Auto-refresh policies DISABLED (use refresh_continuous_aggregates())';
    RAISE NOTICE '- Ingestion state tracking enabled';
    RAISE NOTICE '- Gap detection function available';
END $$;
