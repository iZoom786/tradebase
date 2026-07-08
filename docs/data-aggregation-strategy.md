# Data Aggregation Strategy

## Overview

The Tradebase platform uses a **single-source, multi-timeframe** architecture where:
- **1-minute candles** are the only data fetched from external sources (YFinance)
- **All higher timeframes** are generated via TimescaleDB continuous aggregates (materialized views)
- **Auto-refresh policies** keep aggregated data current

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION FLOW                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Every Minute (at 00:05):                                                │
│  ┌──────────────┐    ┌───────────────┐    ┌─────────────────────────┐  │
│  │   YFinance   │───▶│ 3 Recent Candles│──▶│  Completed 1m Candle   │  │
│  │   API        │    │ (buffer/forming) │   │  (second-to-last)       │  │
│  └──────────────┘    └───────────────┘    └─────────────────────────┘  │
│                                                   │                      │
│                                                   ▼                      │
│                                          ┌─────────────────────┐         │
│                                          │  TimescaleDB        │         │
│                                          │  market_features     │         │
│                                          │  (1m base data)      │         │
│                                          └──────────┬──────────┘         │
│                                                     │                    │
│                     ┌───────────────────────────────┼────────────┐     │
│                     ▼               ▼               ▼            ▼     │
│         ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│         │  5m View    │ │  15m View   │ │  30m View   │ │   1h View │ │
│         │ (auto 5m)   │ │ (auto 15m)  │ │ (auto 30m)  │ │ (auto 1h) │ │
│         └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                     │               │               │            │     │
│                     ▼               ▼               ▼            ▼     │
│         ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│         │  4h View    │ │   1d View   │ │   1w View   │ │           │ │
│         │ (auto 1h)   │ │ (auto 1d)   │ │ (auto 1d)   │ │   ...     │ │
│         └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Benefits

### 1. **Reduced API Calls**
- Only 1m candles fetched from YFinance
- 7 fewer API calls per symbol per minute
- For 3 symbols: 21 saved API calls per minute = 30,240 per day

### 2. **Data Consistency**
- All timeframes derived from same base data
- No discrepancies between 5m aggregated from 1m vs 5m fetched directly
- Single source of truth

### 3. **Performance**
- TimescaleDB continuous aggregates are highly optimized
- Materialized views pre-compute aggregations
- Queries on aggregated data are instant

### 4. **Simplified Logic**
- Ingestion service only handles 1m data
- No need to fetch/manage multiple timeframes
- Auto-refresh handles updates automatically

## Timeframe Coverage

| Timeframe | Source | Refresh Policy | Lag |
|-----------|--------|----------------|-----|
| **1m** | YFinance API | Every minute @ :05 | <1 second |
| **5m** | Materialized View | Every 5 minutes | <1 minute |
| **15m** | Materialized View | Every 15 minutes | <1 minute |
| **30m** | Materialized View | Every 30 minutes | <1 minute |
| **1h** | Materialized View | Every hour | <1 minute |
| **4h** | Materialized View | Every hour | <1 hour |
| **1d** | Materialized View | Daily | <1 day |
| **1w** | Materialized View | Daily | <1 week |

## Implementation Details

### Ingestion Service
Runs every minute at second 5:
```python
# Fetch 3 candles: [previous, completed, forming]
data = ticker.history(period="1d", interval="1m")

# Use the completed candle (second-to-last)
completed_candle = data.iloc[-2]
```

### TimescaleDB Setup
```sql
-- Create materialized view for 5m
CREATE MATERIALIZED VIEW market_features_5m
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

-- Auto-refresh every 5 minutes
SELECT add_continuous_aggregate_policy('market_features_5m',
    start_offset => INTERVAL '5 minutes',
    end_offset => INTERVAL '1 second',
    schedule_interval => INTERVAL '5 minutes');
```

### Querying Any Timeframe
```python
# Query 1m data (base)
SELECT * FROM market_features
WHERE symbol = 'EURUSD' AND interval = '1m'

# Query 5m aggregated data
SELECT * FROM market_features_5m
WHERE symbol = 'EURUSD'

# Query 1h aggregated data
SELECT * FROM market_features_1h
WHERE symbol = 'EURUSD'

# Or use the unified view
SELECT * FROM market_data_all_timeframes
WHERE symbol = 'EURUSD' AND interval = '1h'
```

## OHLCV Aggregation Method

When aggregating from 1m to higher timeframes:

| Field | Method |
|-------|--------|
| **Open** | `first(open, time)` - First open in period |
| **High** | `max(high)` - Highest price in period |
| **Low** | `min(low)` - Lowest price in period |
| **Close** | `last(close, time)` - Last close in period |
| **Volume** | `sum(volume)` - Total volume in period |

This ensures accurate OHLCV representation for any timeframe.

## Data Freshness

### Real-time Requirements
- **1m data**: Available within 1 second of candle close
- **5m-30m data**: Available within 1 minute of period close
- **1h+ data**: Available within the refresh interval

### Refresh Timing
```
1m:  :00, :01, :02, :03, ... (every minute)
5m:  :00, :05, :10, :15, ... (every 5 minutes)
15m: :00, :15, :30, :45 (every 15 minutes)
30m: :00, :30 (every 30 minutes)
1h:  :00 (every hour)
4h:  :00 (every hour, checks for new 4h buckets)
1d:  Daily (once per day)
1w:  Daily (once per day)
```

## Monitoring

### Verify Aggregations are Refreshing
```sql
-- Check last update time for each view
SELECT
    'market_features_5m' AS view_name,
    max(bucket) AS last_data_point
FROM market_features_5m
UNION ALL
SELECT 'market_features_15m', max(bucket) FROM market_features_15m
UNION ALL
SELECT 'market_features_1h', max(bucket) FROM market_features_1h;
```

### Check Refresh Policy Status
```sql
SELECT * FROM timescaledb_information.jobs
WHERE proc_name LIKE 'refresh_continuous_aggregate%';
```

## Future Enhancements

### Additional Timeframes
Can easily add more timeframes:
```sql
-- 3-minute timeframe
CREATE MATERIALIZED VIEW market_features_3m ...;
```

### Custom Aggregations
```sql
-- Weekly with different timezone
CREATE MATERIALIZED VIEW market_features_1w_london ...;
```

### Indicators on Aggregated Data
```sql
-- Materialized view with pre-computed RSI
CREATE MATERIALIZED VIEW market_features_1h_with_rsi ...;
```

## References

- [TimescaleDB Continuous Aggregates](https://docs.timescale.com/api/latest/continuous-aggregates/)
- [YFinance API Documentation](https://github.com/ranaroussi/yfinance)
