# Phase 2: 1-Hour Verification Guide

**Purpose:** Quick verification of Phase 2 database layer functionality
**Duration:** ~1 hour
**Prerequisites:** Docker running, services up

---

## Quick Setup (5 minutes)

```bash
# 1. Navigate to project
cd e:/tradebase

# 2. Start services
docker-compose up -d

# 3. Wait for healthy status
docker-compose ps
```

---

## Verification Steps

### Part 1: Database Connection (10 minutes)

```bash
# 1. Check TimescaleDB is healthy
docker-compose ps timescaledb
# Expected: Up (healthy)

# 2. Test database connection
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT version();"
# Expected: PostgreSQL 16.14 with TimescaleDB

# 3. Check current database
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT current_database();"
# Expected: tradebase
```

### Part 2: Schema Verification (15 minutes)

```bash
# 1. List all tables (should be 6)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\dt"
# Expected: market_features, paper_orders, trade_log, model_registry, users, ingestion_state

# 2. Check market_features structure
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d market_features"
# Verify: timekey column exists, PK is (time, timekey, symbol)

# 3. Check ingestion_state structure
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d ingestion_state"
# Verify: symbol (PK), timekey columns are BIGINT
```

### Part 3: Hypertable & Continuous Aggregates (15 minutes)

```bash
# 1. Verify hypertable
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'market_features';"
# Expected: 1 row, primary_dimension = time

# 2. Count continuous aggregates
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT COUNT(*) FROM timescaledb_information.continuous_aggregates WHERE view_name LIKE 'market_features_%';"
# Expected: 7

# 3. List all continuous aggregates
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT view_name FROM timescaledb_information.continuous_aggregates ORDER BY view_name;"
# Expected: 5m, 15m, 30m, 1h, 4h, 1d, 1w
```

### Part 4: v2.0 Features Test (15 minutes)

```bash
# 1. Test timekey generation
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT generate_timekey('2024-01-15 14:30:00+00'::timestamptz);"
# Expected: 202401151430

# 2. Test ingestion_state insert
docker-compose exec timescaledb psql -U postgres -d tradebase -c "INSERT INTO ingestion_state (symbol, last_backfill_time, last_backfill_timekey, backfill_complete) VALUES ('TEST', NOW(), generate_timekey(NOW()), TRUE);"
# Expected: INSERT 0 1

# 3. Test ingestion_state query
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT symbol, last_backfill_timekey, backfill_complete FROM ingestion_state WHERE symbol = 'TEST';"
# Expected: 1 row with data

# 4. Test ingestion_state upsert
docker-compose exec timescaledb psql -U postgres -d tradebase -c "INSERT INTO ingestion_state (symbol, backfill_complete) VALUES ('TEST', FALSE) ON CONFLICT (symbol) DO UPDATE SET backfill_complete = TRUE;"
# Expected: INSERT 0 1

# 5. Verify upsert worked
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT backfill_complete FROM ingestion_state WHERE symbol = 'TEST';"
# Expected: backfill_complete = t (true)

# 6. Cleanup test data
docker-compose exec timescaledb psql -U postgres -d tradebase -c "DELETE FROM ingestion_state WHERE symbol = 'TEST';"
```

### Part 5: Function Tests (5 minutes)

```bash
# 1. List v2.0 functions
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\df" | grep -E "generate_timekey|detect_data_gap|refresh_continuous_aggregates"
# Expected: 3 functions listed

# 2. Test gap detection (will be empty - no data)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT * FROM detect_data_gap('EURUSD', '1m', 5);"
# Expected: 0 rows (no data yet)
```

---

## Quick Checklist

| Item | Status | Notes |
|------|--------|-------|
| TimescaleDB running | ☐ | `docker-compose ps` |
| 6 tables exist | ☐ | `\dt` shows 6 tables |
| timekey column exists | ☐ | `\d market_features` |
| PK includes time column | ☐ | PK is (time, timekey, symbol) |
| Hypertable configured | ☐ | 1 hypertable for market_features |
| 7 continuous aggregates | ☐ | 5m, 15m, 30m, 1h, 4h, 1d, 1w |
| generate_timekey works | ☐ | Returns YYYYMMDDHHMM |
| ingestion_state works | ☐ | Insert/query/upsert OK |
| Functions exist | ☐ | 3 v2.0 functions |

---

## Success Criteria

✅ **PASS** if all 9 checklist items complete

❌ **FAIL** if any item fails - check logs:
```bash
docker-compose logs timescaledb | tail -50
```

---

## Expected Completion Time

| Part | Duration |
|------|----------|
| Setup | 5 min |
| Connection Tests | 10 min |
| Schema Verification | 15 min |
| Hypertable & Aggregates | 15 min |
| v2.0 Features | 15 min |
| **Total** | **~60 min** |

---

## Troubleshooting

### Issue: Container not healthy
```bash
docker-compose logs timescaledb
docker-compose restart timescaledb
```

### Issue: Wrong table count
```bash
# Check if init completed
docker-compose logs timescaledb | grep "initialized successfully"
```

### Issue: No timekey column
```bash
# Rebuild with correct schema
docker-compose down -v
docker-compose up -d
```

---

**Next Steps After Verification:**
1. Load test data with backfill_v2.py
2. Verify continuous aggregates populate
3. Proceed to Phase 3 (Ingestion) testing
