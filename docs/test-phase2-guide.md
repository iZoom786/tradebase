# Phase 2: Database Layer & Schema - Test Guide

**Last Updated:** 2026-07-07
**Phase:** Database Layer & Schema (v2.0)
**Purpose:** Verify database schema, hypertables, continuous aggregates, and v2.0 features

---

## Test Overview

This guide tests the TimescaleDB database layer including:
- Database connection and basic operations
- Schema validation (tables, columns, types)
- Hypertable configuration
- Continuous aggregate materialized views
- v2.0 features: timekey, ingestion_state, gap detection
- Repository pattern functionality

---

## Prerequisites

1. Docker services running
2. TimescaleDB container healthy
3. Database initialized with v2.0 schema

---

## Test Categories

### 1. Database Connection Tests

### 2. Schema Validation Tests

### 3. Hypertable Tests

### 4. Continuous Aggregate Tests

### 5. v2.0 Feature Tests

### 6. Repository Pattern Tests

---

## Test Commands

### 1. Database Connection Tests

```bash
# Test 1.1: Check TimescaleDB is running
docker-compose ps timescaledb

# Test 1.2: Test database connection
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT version();"

# Test 1.3: Test basic query
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT current_database(), current_user;"
```

**Expected Results:**
- ✅ TimescaleDB container status: "Up (healthy)"
- ✅ PostgreSQL version displayed (16.x with TimescaleDB)
- ✅ Database name: `tradebase`, User: `postgres`

---

### 2. Schema Validation Tests

```bash
# Test 2.1: List all tables
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\dt"

# Test 2.2: Check market_features table structure (v2.0)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d market_features"

# Test 2.3: Check other tables exist
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d paper_orders"
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d trade_log"
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d model_registry"
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d users"

# Test 2.4: Check ingestion_state table (v2.0)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d ingestion_state"

# Test 2.5: Verify timekey column exists (v2.0)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'market_features' AND column_name = 'timekey';"
```

**Expected Results:**
- ✅ 6 tables: market_features, paper_orders, trade_log, model_registry, users, ingestion_state
- ✅ market_features has `timekey BIGINT GENERATED ALWAYS AS STORED`
- ✅ Primary key is `(timekey, symbol)`
- ✅ ingestion_state table exists with all required columns

---

### 3. Hypertable Tests

```bash
# Test 3.1: Check market_features is a hypertable
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT hypertable_name, time_column_name, chunk_time_interval FROM timescaledb_information.hypertables WHERE hypertable_name = 'market_features';"

# Test 3.2: Check chunks exist
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT chunk_name, range_start, range_end FROM timescaledb_information.chunks WHERE hypertable_name = 'market_features' ORDER BY range_start DESC LIMIT 5;"

# Test 3.3: Check indexes on market_features
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'market_features';"
```

**Expected Results:**
- ✅ Hypertable exists: `market_features`
- ✅ Time column: `time`
- ✅ Chunk interval: `1 day`
- ✅ At least 3 indexes: pkey (timekey, symbol), time DESC, symbol + time DESC

---

### 4. Continuous Aggregate Tests

```bash
# Test 4.1: List all materialized views
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT matviewname FROM pg_matviews WHERE matviewname LIKE 'market_features_%' ORDER BY matviewname;"

# Test 4.2: Check continuous aggregate status
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT view_name, transparent = false AS is_continuous FROM timescaledb_information.continuous_aggregates WHERE view_name LIKE 'market_features_%' ORDER BY view_name;"

# Test 4.3: Check materialized view structure (5m)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d+ market_features_5m"

# Test 4.4: Check timekey in materialized views (v2.0)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'market_features_5m' AND column_name = 'timekey';"
```

**Expected Results:**
- ✅ 7 materialized views: market_features_5m, 15m, 30m, 1h, 4h, 1d, 1w
- ✅ All marked as continuous aggregates
- ✅ All have timekey column (BIGINT)
- ✅ Columns: bucket (time), timekey, symbol, open, high, low, close, volume

---

### 5. v2.0 Feature Tests

#### 5.1 Timekey Function Tests

```bash
# Test 5.1.1: Check generate_timekey function exists
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT routine_name, routine_type FROM information_schema.routines WHERE routine_name = 'generate_timekey';"

# Test 5.1.2: Test timekey generation
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT generate_timekey('2024-01-15 14:30:00+00'::timestamptz) AS expected_202401151430;"

# Test 5.1.3: Test timekey generation with different timestamps
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT generate_timekey(NOW()) AS current_timekey;"
```

**Expected Results:**
- ✅ Function exists and returns BIGINT
- ✅ `2024-01-15 14:30:00` → `202401151430`
- ✅ Current timekey is valid BIGINT in `YYYYMMDDHHMM` format

#### 5.2 Ingestion State Tests

```bash
# Test 5.2.1: Check ingestion_state table structure
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\d ingestion_state"

# Test 5.2.2: Insert test data
docker-compose exec timescaledb psql -U postgres -d tradebase -c "INSERT INTO ingestion_state (symbol, last_backfill_time, last_backfill_timekey, backfill_complete) VALUES ('EURUSD', NOW(), generate_timekey(NOW()), TRUE);"

# Test 5.2.3: Query test data
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT * FROM ingestion_state WHERE symbol = 'EURUSD';"

# Test 5.2.4: Test upsert (ON CONFLICT)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "INSERT INTO ingestion_state (symbol, last_backfill_time, last_backfill_timekey, backfill_complete) VALUES ('EURUSD', NOW(), generate_timekey(NOW()), FALSE) ON CONFLICT (symbol) DO UPDATE SET backfill_complete = TRUE;"

# Test 5.2.5: Cleanup test data
docker-compose exec timescaledb psql -U postgres -d tradebase -c "DELETE FROM ingestion_state WHERE symbol = 'EURUSD';"
```

**Expected Results:**
- ✅ Table structure: symbol (PK), last_backfill_time, last_backfill_timekey (BIGINT), etc.
- ✅ Insert works
- ✅ Query returns inserted data
- ✅ Upsert (ON CONFLICT) updates existing record
- ✅ Delete works

#### 5.3 Gap Detection Function Tests

```bash
# Test 5.3.1: Check detect_data_gap function exists
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\df detect_data_gap"

# Test 5.3.2: Test gap detection (will return empty if no data)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT * FROM detect_data_gap('EURUSD', '1m', 5);"

# Test 5.3.3: Test with different parameters
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT * FROM detect_data_gap('GBPUSD', '1m', 10) LIMIT 5;"
```

**Expected Results:**
- ✅ Function exists with signature: `(p_symbol, p_interval, p_gap_minutes)`
- ✅ Returns: `gap_start, gap_end, gap_minutes`
- ✅ Returns empty set if no gaps found

#### 5.4 Manual Refresh Function Tests

```bash
# Test 5.4.1: Check refresh_continuous_aggregates function exists
docker-compose exec timescaledb psql -U postgres -d tradebase -c "\df refresh_continuous_aggregates"

# Test 5.4.2: Test manual refresh (may be empty if no data)
docker-compose exec timescaledb psql -U postgres -d tradebase -c "SELECT * FROM refresh_continuous_aggregates();"
```

**Expected Results:**
- ✅ Function exists
- ✅ Returns: `view_name, rows_affected` for each materialized view
- ✅ Views: market_features_5m, 15m, 30m, 1h, 4h, 1d, 1w

---

### 6. Repository Pattern Tests

```bash
# Test 6.1: Check repository files exist
ls -la libs/db_repo/base.py
ls -la libs/db_repo/timescaledb.py
ls -la libs/db_repo/timescaledb_v2.py

# Test 6.2: Check migration framework
ls -la libs/db_repo/migrations/
```

**Expected Results:**
- ✅ `base.py` - Abstract Repository class
- ✅ `timescaledb.py` - TimescaleDB repository implementation
- ✅ `timescaledb_v2.py` - v2.0 with timekey support
- ✅ Migrations directory exists with migration files

---

## Quick Test Script

```bash
#!/bin/bash
# Quick Phase 2 Test Script

echo "=== Phase 2: Database Layer Tests ==="
echo ""

# 1. Connection Test
echo "1. Testing database connection..."
docker-compose exec -T timescaledb psql -U postgres -d tradebase -c "SELECT current_database();" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "   ✅ Database connection OK"
else
    echo "   ❌ Database connection FAILED"
    exit 1
fi

# 2. Tables Test
echo "2. Testing tables exist..."
TABLE_COUNT=$(docker-compose exec -T timescaledb psql -U postgres -d tradebase -c "\dt" -t | grep -c "market_features\|paper_orders\|trade_log\|model_registry\|users\|ingestion_state")
if [ "$TABLE_COUNT" -ge 6 ]; then
    echo "   ✅ All 6+ tables exist"
else
    echo "   ❌ Missing tables (found: $TABLE_COUNT)"
fi

# 3. Timekey Test
echo "3. Testing timekey column..."
TIMEKEY_EXISTS=$(docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = 'market_features' AND column_name = 'timekey');")
if [ "$TIMEKEY_EXISTS" = " t" ]; then
    echo "   ✅ timekey column exists"
else
    echo "   ❌ timekey column missing"
fi

# 4. Hypertable Test
echo "4. Testing hypertable..."
HT_EXISTS=$(docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c "SELECT COUNT(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'market_features';")
if [ "$HT_EXISTS" -eq 1 ]; then
    echo "   ✅ market_features is a hypertable"
else
    echo "   ❌ market_features is not a hypertable"
fi

# 5. Continuous Aggregates Test
echo "5. Testing continuous aggregates..."
CA_COUNT=$(docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c "SELECT COUNT(*) FROM timescaledb_information.continuous_aggregates WHERE view_name LIKE 'market_features_%';")
if [ "$CA_COUNT" -ge 7 ]; then
    echo "   ✅ $CA_COUNT continuous aggregates exist"
else
    echo "   ❌ Insufficient continuous aggregates (found: $CA_COUNT)"
fi

# 6. Functions Test
echo "6. Testing v2.0 functions..."
FUNC_COUNT=$(docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c "SELECT COUNT(*) FROM information_schema.routines WHERE routine_name IN ('generate_timekey', 'detect_data_gap', 'refresh_continuous_aggregates');")
if [ "$FUNC_COUNT" -ge 3 ]; then
    echo "   ✅ $FUNC_COUNT v2.0 functions exist"
else
    echo "   ❌ Missing v2.0 functions (found: $FUNC_COUNT)"
fi

echo ""
echo "=== Phase 2 Tests Complete ==="
```

---

## Test Results Template

```markdown
## Phase 2 Test Results

**Date:** [DATE]
**Tester:** [NAME]
**Environment:** [DEV/STAGING/PROD]

### Test Summary

| Test Category | Result | Notes |
|--------------|--------|-------|
| Database Connection | ✅/❌ | |
| Schema Validation | ✅/❌ | |
| Hypertable Configuration | ✅/❌ | |
| Continuous Aggregates | ✅/❌ | |
| v2.0 Features | ✅/❌ | |
| Repository Pattern | ✅/❌ | |

### Issues Found

1. [Issue description]
   - Severity: [HIGH/MEDIUM/LOW]
   - Resolution: [FIXED/PENDING/IGNORED]

### Recommendations

1. [Recommendation 1]
2. [Recommendation 2]
```

---

## Troubleshooting

### Issue: Database container not healthy
**Solution:** Check logs: `docker-compose logs timescaledb`

### Issue: timekey column missing
**Solution:** Apply v2.0 migration or rebuild database

### Issue: Materialized views not refreshing
**Solution:** Use manual refresh: `SELECT refresh_continuous_aggregates();`

### Issue: No data in continuous aggregates
**Solution:** Insert 1m data first, then manually refresh views

---

**Next Steps:**
1. Run all tests in this guide
2. Document results in `docs/phase2-test-results.md`
3. Fix any issues found
4. Re-test after fixes
