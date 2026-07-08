# EURUSD 1-Minute Data Ingestion Guide

## Overview

Two-step process to load and maintain EURUSD 1-minute data in TimescaleDB:

1. **Initial Backfill** - Load 1 year of historical 1-minute data (~525,600 candles)
2. **Incremental Fetch** - Continuously fetch the latest 3 candles every minute

---

## Quick Start (Windows)

```bash
# Run the batch script - it does both steps
scripts\start_eurusd_ingestion.bat
```

---

## Manual Steps

### Step 1: Initial Backfill (1 Year)

Load historical data from 1 year ago to now.

```bash
python scripts\backfill_eurusd_1y_1m.py
```

**What it does:**
- Fetches 1 year of 1-minute EURUSD data in 30-day chunks
- ~525,600 expected candles (365 × 24 × 60)
- Takes 10-15 minutes due to YFinance rate limits
- Upserts to database (duplicates are skipped)

**Output:**
```
✓ Total candles retrieved: 525,483
✓ Total inserted: 525,483
✓ Total skipped (duplicates): 0
```

---

### Step 2: Incremental Fetch (Continuous)

Start the continuous incremental fetcher.

```bash
python scripts\incremental_fetch_1m.py
```

**What it does:**
- Runs continuously until Ctrl+C
- Every ~60 seconds, fetches the 3 most recent candles
- Skips the current forming minute (only stores completed candles)
- Upserts to database

**Output every minute:**
```
[========================================================]
Cycle 123 - 2026-07-08 12:34:56
[========================================================]
  Fetched 3 candles from YFinance

  Latest candles:
    12:32: O=1.08050 H=1.08055 L=1.08048 C=1.08052
    12:33: O=1.08052 H=1.08060 L=1.08050 C=1.08058
    12:34: O=1.08058 H=1.08062 L=1.08056 C=1.08061

  ✓ Upserted 2 candles to database

  Waiting 58.3 seconds until next fetch...
  Total inserted so far: 8,542
```

---

## File Structure

```
scripts/
├── backfill_eurusd_1y_1m.py          # Initial 1-year backfill
├── incremental_fetch_1m.py            # Continuous incremental fetcher
└── start_eurusd_ingestion.bat         # Windows batch script (both steps)
```

---

## Verification Commands

### Check Database Status

```bash
# Using psql
docker exec -it tradebase_timescaledb psql -U postgres -d tradebase -c "
SELECT
    symbol,
    COUNT(*) as total_rows,
    MIN(time) as earliest,
    MAX(time) as latest,
    EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))/60 as minutes_covered
FROM public.market_features
WHERE symbol = 'EURUSD'
GROUP BY symbol;
"
```

**Expected output:**
```
 symbol  | total_rows |      earliest      |       latest       | minutes_covered
---------+------------+-------------------+--------------------+-----------------
 EURUSD  |     525483 | 2025-07-08 00:00  | 2026-07-08 12:34  |       525474.00
```

### Check Latest Data

```bash
# Get the 5 most recent candles
docker exec -it tradebase_timescaledb psql -U postgres -d tradebase -c "
SELECT time, open, high, low, close, volume
FROM public.market_features
WHERE symbol = 'EURUSD'
ORDER BY time DESC
LIMIT 5;
"
```

### Check Data Freshness

```bash
# How old is the latest data?
docker exec -it tradebase_timescaledb psql -U postgres -d tradebase -c "
SELECT
    MAX(time) as latest_candle,
    NOW() - MAX(time) as age,
    EXTRACT(EPOCH FROM (NOW() - MAX(time)))/60 as minutes_behind
FROM public.market_features
WHERE symbol = 'EURUSD';
"
```

**Should be < 2 minutes behind** when incremental fetch is running.

---

## Troubleshooting

### Issue: "Database connection failed"

**Solution:** Ensure TimescaleDB is running
```bash
docker ps | findstr timescaledb
# or
docker ps | grep timescaledb
```

### Issue: "No data returned" from YFinance

**Causes:**
- Market closed (weekends)
- Network issues
- YFinance rate limit

**Solution:** Wait a few minutes and try again. YFinance has rate limits.

### Issue: Incremental fetch shows "No new candles"

**Normal behavior:** When the current minute is still forming, it gets skipped.
Only completed minutes are stored.

### Issue: Too many duplicates

**Check:** Verify the timekey is being generated correctly
```sql
SELECT time, timekey FROM public.market_features
WHERE symbol = 'EURUSD'
ORDER BY time DESC LIMIT 10;
```

---

## Resource Requirements

| Resource | Requirement |
|----------|-------------|
| **Disk Space** | ~500 MB for 1 year of 1-minute data |
| **Memory** | Minimal for Python scripts |
| **Network** | Required for YFinance API calls |
| **CPU** | Minimal |

---

## YFinance Rate Limits

YFinance has undocumented rate limits. The backfill script:
- Fetches in 30-day chunks
- Adds 0.5 second delays between chunks
- Should complete in 10-15 minutes without hitting limits

If you hit rate limits:
```python
# In backfill_eurusd_1y_1m.py
# Increase the delay:
time.sleep(1.0)  # instead of time.sleep(0.5)
```

---

## Stopping Incremental Fetch

Press `Ctrl+C` to stop gracefully. The script will:
1. Finish current cycle
2. Display summary statistics
3. Close database connection

```
^C
Shutdown signal received. Finishing current cycle...

============================================================
SHUTDOWN SUMMARY
============================================================
Total cycles completed: 156
Total candles inserted: 2,456
Final DB stats:
  Total rows: 527,939
  Latest candle: 2026-07-08 14:32:00

✓ Database connection closed
```

---

## Next Steps

After initial backfill is running:

1. **Verify data quality** - Check for gaps
2. **Refresh materialized views** - Update continuous aggregates
3. **Set up monitoring** - Track ingestion health via Grafana

---

## Files Created

- `scripts/backfill_eurusd_1y_1m.py` - Initial backfill script
- `scripts/incremental_fetch_1m.py` - Incremental fetcher
- `scripts/start_eurusd_ingestion.bat` - Windows launcher
- `docs/eurusd-ingestion-guide.md` - This guide
