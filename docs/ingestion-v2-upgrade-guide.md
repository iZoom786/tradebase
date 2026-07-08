# Ingestion System v2.0 - Upgrade Guide

## Overview

The ingestion system has been significantly enhanced with the following improvements:

1. **Timekey-based unique constraint** - `YYYYMMDDHHMM` format for unique identification
2. **3-row per minute fetching** - More robust data collection
3. **Resume/backfill capability** - Handles service interruptions gracefully
4. **Manual materialized view refresh** - No auto-refresh policies
5. **State tracking** - Tracks ingestion progress for recovery
6. **Gap detection** - Automatically detects and fills data gaps

---

## Changes Summary

### Database Schema Changes

| Change | Old | New |
|--------|-----|-----|
| Primary Key | `(time, symbol, interval)` | `(timekey, symbol)` |
| timekey column | None | `BIGINT GENERATED ALWAYS AS (generate_timekey(time)) STORED` |
| Materialized Views | Auto-refresh | Manual refresh only |

### New Files

| File | Purpose |
|------|---------|
| `infrastructure/timescaledb/init_v2.sql` | New schema with timekey |
| `libs/db_repo/migrations/migration_2024.01.02_add_timekey.py` | Migration for existing databases |
| `services/ingestion/models/market_data_v2.py` | MarketData model with timekey |
| `libs/db_repo/timescaledb_v2.py` | Repository with timekey support |
| `services/ingestion/controllers/ingestion_controller_v2.py` | Enhanced controller with 3-row logic |
| `services/ingestion/providers/yfinance_v2.py` | Provider with N-candle support |
| `scripts/backfill_v2.py` | Enhanced backfill CLI |

---

## Upgrade Instructions

### Option 1: Fresh Installation (Recommended for Testing)

```bash
# Stop existing services
docker-compose down

# Remove existing volumes (WARNING: This deletes all data)
docker-compose down -v

# Update docker-compose.yml to use init_v2.sql
# Change: ./infrastructure/timescaledb/init.sql
# To:     ./infrastructure/timescaledb/init_v2.sql

# Start services
docker-compose up -d
```

### Option 2: Migrate Existing Database

```bash
# Run migration
python scripts/migrate.py

# Verify migration
docker-compose exec timescaledb psql -U postgres -d tradebase -c "
\d market_features
"

# Should show timekey column and new primary key
```

---

## Usage Guide

### 1. Initial 1-Year Backfill

```bash
# Backfill last 365 days for EURUSD
python scripts/backfill_v2.py backfill --symbols EURUSD --days 365

# Backfill multiple symbols
python scripts/backfill_v2.py backfill --symbols EURUSD,GBPUSD,USDJPY --days 365

# After completion, materialized views are automatically refreshed
```

### 2. Resume Interrupted Backfill

If the backfill is interrupted (network issue, service stop, etc.):

```bash
# Resume from last checkpoint
python scripts/backfill_v2.py backfill --symbols EURUSD --resume
```

The system:
- Tracks last backfilled timestamp in `ingestion_state` table
- Continues from where it left off
- No duplicate data inserted

### 3. Continuous Ingestion (3-Row Mode)

```bash
# Start ingestion service
# (Update service to use ingestion_controller_v2.py)
python services/ingestion/main.py
```

The ingestion service:
- Fetches 3 recent candles every minute
- Stores only complete candles (not the currently forming one)
- Tracks state for resume capability

### 4. Gap Detection and Repair

```bash
# Detect and fill gaps for a symbol
python scripts/backfill_v2.py gap --symbols EURUSD --threshold 5

# Check status first
python scripts/backfill_v2.py status --symbols EURUSD
```

### 5. Manual Materialized View Refresh

```bash
# Refresh all materialized views manually
python scripts/backfill_v2.py refresh

# Or via SQL
docker-compose exec timescaledb psql -U postgres -d tradebase -c "
SELECT refresh_continuous_aggregates();
"
```

---

## Timekey Format

The timekey is generated as a `BIGINT` in `YYYYMMDDHHMM` format:

```
2024-01-15 14:30:00 → 202401151430 (as integer)
2024-12-31 23:59:00 → 202412312359 (as integer)
```

### Advantages

1. **Sortable** - Numerical ordering matches chronological ordering
2. **Compact** - 8 bytes (BIGINT) vs 12 bytes (VARCHAR) or 26 bytes (ISO timestamp)
3. **Human-readable** - Easy to identify date/time
4. **Fast lookups** - Integer comparison is fastest
5. **Index-efficient** - Optimized for database indexes

### Example Usage

```sql
-- Find data for a specific minute
SELECT * FROM market_features
WHERE timekey = 202401151430 AND symbol = 'EURUSD';

-- Find data for a specific hour range
SELECT * FROM market_features
WHERE timekey BETWEEN 202401151400 AND 202401151459
  AND symbol = 'EURUSD';

-- Find data for a specific day range
SELECT * FROM market_features
WHERE timekey BETWEEN 202401150000 AND 202401152359
  AND symbol = 'EURUSD';

-- Find data using modulo for hour (timekey DIV 100 gives YYYYMMDDHH)
SELECT * FROM market_features
WHERE timekey DIV 100 = 2024011514 AND symbol = 'EURUSD';
```

---

## Scenarios Handled

### Scenario 1: Service Interruption During Backfill

**Before v2.0:**
- No state tracking
- Must restart from beginning
- Wastes time and API calls

**v2.0:**
```
# Backfill stops at 2024-01-10 due to network issue
# Service restarts

python scripts/backfill_v2.py backfill --symbols EURUSD --resume

# Output: "Resuming from 2024-01-10 00:01:00"
# Continues from where it stopped
```

### Scenario 2: Internet Issue During Ingestion

**Before v2.0:**
- Loses data during outage
- Manual gap detection required
- Complex recovery process

**v2.0:**
```
# Ingestion stops during outage
# Service resumes when connection restored

# System automatically:
# 1. Detects gaps in recent data
# 2. Fetches missing candles
# 3. Fills gaps automatically
# 4. Continues normal operation
```

### Scenario 3: Duplicate Data Handling

**Before v2.0:**
- Complex duplicate detection
- `(time, symbol, interval)` constraint

**v2.0:**
```
# Simpler duplicate handling
# timekey+symbol is unique
# ON CONFLICT handles duplicates automatically

INSERT INTO market_features (...) VALUES (...)
ON CONFLICT (timekey, symbol)
DO UPDATE SET ...;
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Ingestion System v2.0                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌──────────────────┐    ┌─────────────┐  │
│  │ YFinance     │───▶│ 3-Row Selector   │───▶│ TimescaleDB │  │
│  │ Provider v2  │    │ (Complete only)  │    │ Repository  │  │
│  └──────────────┘    └──────────────────┘    └─────────────┘  │
│         │                                             │         │
│         │                 State Tracking              │         │
│         ▼                                             ▼         │
│  ┌──────────────┐                            ┌─────────────┐  │
│  │ Resume       │◀──────────────────────────│ Gap         │  │
│  │ on Resume    │                            │ Detection   │  │
│  └──────────────┘                            └─────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Manual Refresh Control                          │  │
│  │   No auto-refresh policies - manual refresh only          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Performance Improvements

### Batch Operations

```python
# Old: One upsert at a time
for candle in candles:
    await repository.upsert(candle)  # N round trips

# New: Batch upsert
await repository.upsert_batch(candles)  # 1 round trip
```

### Connection Pooling

- Min connections: 5
- Max connections: 20 (configurable)
- Automatic retry on transient failures

### Materialized View Refresh

- **Old:** Auto-refresh every 5 minutes (7 views = frequent CPU usage)
- **New:** Manual refresh after backfill (controlled timing)

---

## API Reference

### IngestionControllerV2

```python
controller = IngestionControllerV2(
    provider=provider,
    repository=repository,
    publisher=publisher,
    rows_per_minute=3  # Configurable
)

# Ingest latest (3-row mode)
result = await controller.ingest_latest(symbol)
# Returns: {fetched, upserted, published, errors}

# Backfill with resume
result = await controller.backfill_historical(
    symbol=symbol,
    days=365,
    batch_size=1000,
    resume=True  # Resume from checkpoint
)

# Detect and fill gaps
result = await controller.backfill_gaps(
    symbol=symbol,
    gap_threshold_minutes=5
)
```

### RepositoryV2

```python
# Timekey-based operations
timekey = generate_timekey(datetime.now())

# Batch upsert
count = await repository.upsert_batch(data_list)

# Ingestion state
state = await repository.get_ingestion_state(symbol)
await repository.update_ingestion_state(symbol, ...)

# Gap detection
gaps = await repository.detect_gaps(symbol, "1m", 5)

# Manual refresh
results = await repository.refresh_continuous_aggregates()
```

---

## Troubleshooting

### Issue: Migration fails with "timekey already exists"

```bash
# Check if migration already ran
docker-compose exec timescaledb psql -U postgres -d tradebase -c "
SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;
"

# If migration 2024.01.02 exists, skip migration
# Use init_v2.sql for fresh installations
```

### Issue: Backfill is slow

```bash
# Reduce batch size
python scripts/backfill_v2.py backfill --symbols EURUSD --days 365 --batch-size 500

# Or backfill in smaller chunks
# First 6 months
python scripts/backfill_v2.py backfill --symbols EURUSD --days 180
# Next 6 months
python scripts/backfill_v2.py backfill --symbols EURUSD --days 180 --resume
```

### Issue: Materialized views not updating

```bash
# Manual refresh
python scripts/backfill_v2.py refresh

# Check view status
docker-compose exec timescaledb psql -U postgres -d tradebase -c "
SELECT viewname, last_refresh
FROM timescaledb_information.matviews;
"
```

---

## Testing Checklist

- [ ] Fresh database installation with init_v2.sql
- [ ] Migration from existing database
- [ ] 1-year backfill completes successfully
- [ ] Resume works after interruption
- [ ] Gap detection finds missing data
- [ ] Gap repair fills missing data
- [ ] 3-row ingestion filters correctly
- [ ] Materialized view refresh works
- [ ] No duplicate data in database
- [ ] timekey values are correct format

---

## Next Steps

1. **Deploy v2.0 to staging** - Test with real data
2. **Run 1-year backfill** - Verify performance
3. **Monitor gap detection** - Ensure it finds real gaps
4. **Optimize batch size** - Tune for performance
5. **Update documentation** - Add operational guides

---

## Rollback Plan

If issues occur:

```bash
# Stop services
docker-compose down

# Restore previous database
# (From backup taken before migration)

# Revert to v1.0 files
git checkout <commit-before-v2>

# Restart services
docker-compose up -d
```

**Note:** Timekey migration is one-way. Rollback requires database restore from backup.
