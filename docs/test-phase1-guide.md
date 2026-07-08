# Phase 1 Testing Guide - Foundation & Infrastructure

This guide provides comprehensive testing steps for Phase 1 (Foundation & Infrastructure).

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ installed
- Git repository cloned
- Ports 5432, 4222, 6379, 9090, 3001, 16686 available

---

## Quick Test (5 minutes)

### 1. Start All Infrastructure

```bash
# From project root
docker-compose up -d
```

**Expected Output:**
```
Creating tradebase_timescaledb    ... done
Creating tradebase_nats           ... done
Creating tradebase_redis          ... done
Creating tradebase_prometheus     ... done
Creating tradebase_grafana        ... done
Creating tradebase_jaeger         ... done
```

### 2. Verify All Services Are Running

```bash
docker-compose ps
```

**Expected Output:** All services should show "Up" status

### 3. Quick Health Checks

```bash
# TimescaleDB
docker-compose exec timescaledb pg_isready -U postgres

# NATS
curl -s http://localhost:8222/varz | grep -o "server_id.*"

# Prometheus
curl -s http://localhost:9090/-/healthy

# Grafana
curl -s http://localhost:3001/api/health

# Redis
docker-compose exec redis redis-cli ping
```

**If all pass:** ✅ Phase 1 basics are working!

---

## Comprehensive Test Checklist

### ✅ Docker Environment Tests

#### Test 1.1: Docker Compose Configuration

```bash
# Validate docker-compose syntax
docker-compose config

# Check for errors
echo $?  # Should return 0
```

**Validation:**
- [ ] No syntax errors
- [ ] All services defined correctly
- [ ] Volume declarations valid
- [ ] Network configurations correct

#### Test 1.2: Build Validation

```bash
# Validate service images can be built
docker-compose config | grep image

# Check no image conflicts
docker-compose config | grep -c "image:" | grep -q "6"
```

**Expected:**
- 6 external images (timescaledb, nats, redis, prometheus, grafana, jaeger)

#### Test 1.3: Volume Creation

```bash
# Check volumes were created
docker volume ls | grep tradebase

# Expected volumes:
# - tradebase_timescaledb_data
# - tradebase_nats_data
# - tradebase_redis_data
# - tradebase_prometheus_data
# - tradebase_grafana_data
```

**Validation:**
- [ ] All 5 volumes created
- [ ] Volumes have correct names

---

### ✅ TimescaleDB Tests

#### Test 2.1: Database Connection

```bash
# Connect to database
docker-compose exec timescaledb psql -U postgres -d tradebase

# Run inside psql:
\conninfo      # Should show connection info
\dt           # Should list tables (0 initially)
\q            # Quit
```

**Expected Output:**
```
You are connected to database "tradebase" as user "postgres".
```

#### Test 2.2: Hypertable Creation

```bash
# Check if init.sql ran successfully
docker-compose exec timescaledb psql -U postgres -d tradebase -c "
SELECT hypertable_name 
FROM timescaledb_information.hypertables;
"
```

**Expected:**
```
 hypertable_name
-----------------
 market_features
(1 row)
```

#### Test 2.3: Continuous Aggregates

```bash
# Check continuous aggregates
docker-compose exec timescaledb psql -U postgres -d tradebase -c "
SELECT view_name 
FROM timescaledb_information.continuous_aggregates;
"
```

**Expected:** Should show 7 aggregates (5m, 15m, 30m, 1h, 4h, 1d, 1w)

#### Test 2.4: Health Check

```bash
# Test health check endpoint
docker-compose exec timescaledb pg_isready -U postgres

# Expected: "accepting connections"
```

---

### ✅ NATS Tests

#### Test 3.1: NATS Server Status

```bash
# Check NATS monitoring endpoint
curl -s http://localhost:8222/varz | jq -r '.server_id'

# Expected: Returns a server ID
```

#### Test 3.2: JetStream Enabled

```bash
# Check if JetStream is running
curl -s http://localhost:8222/varz | jq -r '.jetstream'

# Expected: "true"
```

#### Test 3.3: Connection Test

```bash
# Test NATS connection (requires nc or telnet)
telnet localhost 4222

# Or with netcat (if available):
echo "INFO" | nc localhost 4222

# Expected: Connected and response received
```

#### Test 3.4: NATS Logs

```bash
# Check NATS logs for errors
docker-compose logs nats | grep -i error

# Expected: No errors found
```

---

### ✅ Redis Tests

#### Test 4.1: Redis Connection

```bash
# Test Redis ping
docker-compose exec redis redis-cli ping

# Expected: PONG
```

#### Test 4.2: Redis Operations

```bash
# Set and get a value
docker-compose exec redis redis-cli SET test "hello"
docker-compose exec redis redis-cli GET test

# Expected: "hello"
```

#### Test 4.3: Redis Info

```bash
# Check Redis info
docker-compose exec redis redis-cli INFO server

# Expected: Server information displayed
```

---

### ✅ Prometheus Tests

#### Test 5.1: Prometheus UI

```bash
# Open browser to:
# http://localhost:9090

# Check:
# - UI loads
# - Status > Targets shows NATS endpoint
```

**Validation:**
- [ ] UI accessible at http://localhost:9090
- [ ] Targets page shows NATS endpoint
- [ ] NATS endpoint shows "UP" status

#### Test 5.2: Prometheus Metrics

```bash
# Query NATS metrics
curl -s 'http://localhost:9090/api/v1/query?query=nats_server_connections' | jq

# Expected: Returns metrics data
```

#### Test 5.3: Prometheus Configuration

```bash
# Check Prometheus loaded config
curl -s http://localhost:9090/api/v1/status/config | jq -r '.yaml' | head -20

# Expected: Shows scrape configurations
```

---

### ✅ Grafana Tests

#### Test 6.1: Grafana UI

```bash
# Open browser to:
# http://localhost:3001
# Default credentials: admin / admin

# Check:
# - Login successful
# - Home page loads
# - Data sources configured
```

**Validation:**
- [ ] UI accessible at http://localhost:3001
- [ ] Login with admin/admin works
- [ ] Home dashboard loads

#### Test 6.2: Grafana Datasource

```bash
# Check Prometheus datasource is configured
curl -s http://admin:admin@localhost:3001/api/datasources | jq

# Expected: Shows Prometheus datasource
```

#### Test 6.3: Grafana Dashboard

```bash
# Check dashboards are provisioned
curl -s http://admin:admin@localhost:3001/api/search | jq

# Expected: Shows system-metrics dashboard
```

---

### ✅ Jaeger Tests

#### Test 7.1: Jaeger UI

```bash
# Open browser to:
# http://localhost:16686

# Check:
# - UI loads
# - Search page visible
# - Can search for traces
```

**Validation:**
- [ ] UI accessible at http://localhost:16686
- [ ] Search interface loads
- [ ] Services dropdown appears (may be empty initially)

#### Test 7.2: Jaeger API

```bash
# Check Jaeger API
curl -s http://localhost:16686/api/services | jq

# Expected: Returns empty array or service list
```

---

### ✅ Configuration Management Tests

#### Test 8.1: Config Validation Script

```bash
# Run config validation
python scripts/validate-config.py

# Expected: All configurations valid
```

#### Test 8.2: Environment Variables

```bash
# Check required environment variables
docker-compose config | grep -E "POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD"

# Expected: All variables have default values
```

---

### ✅ Observability Scaffolding Tests

#### Test 9.1: Logging Setup

```bash
# Test the observability module
python -c "from libs.common.observability import setup_logging; setup_logging(); print('OK')"

# Expected: "OK"
```

#### Test 9.2: Metrics Export

```bash
# Test Prometheus metrics library
python -c "
from libs.common.observability import message_counter, processing_duration
counter = message_counter.labels(service='test', status='success')
counter.inc()
print('OK')
"

# Expected: "OK"
```

#### Test 9.3: Tracing Setup

```bash
# Test tracing initialization
python -c "
from libs.common.observability import setup_tracing
setup_tracing('test', 'http://localhost:14268/api/traces')
print('OK')
"

# Expected: "OK"
```

---

### ✅ Project Structure Tests

#### Test 10.1: Directory Structure

```bash
# Verify all required directories exist
ls -d services/
ls -d libs/
ls -d infrastructure/
ls -d config/
ls -d tests/
ls -d docs/

# Expected: All directories exist
```

#### Test 10.2: Library Stubs

```bash
# Check all library stubs were created
ls libs/common/__init__.py
ls libs/db_repo/__init__.py
ls libs/nats_client/__init__.py

# Expected: All __init__.py files exist
```

---

## Integration Test Script

Save this as `test-phase1.sh` and run it:

```bash
#!/bin/bash
# Phase 1 Integration Test Script

set -e

echo "=== Phase 1 Integration Tests ==="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

tests_passed=0
tests_failed=0

run_test() {
    local name="$1"
    local command="$2"
    
    echo -n "Testing: $name ... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((tests_passed++))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        ((tests_failed++))
        return 1
    fi
}

echo "=== Docker Environment ==="
run_test "Docker compose config" "docker-compose config"
run_test "TimescaleDB container running" "docker-compose ps | grep timescaledb | grep Up"
run_test "NATS container running" "docker-compose ps | grep nats | grep Up"
run_test "Redis container running" "docker-compose ps | grep redis | grep Up"
run_test "Prometheus container running" "docker-compose ps | grep prometheus | grep Up"
run_test "Grafana container running" "docker-compose ps | grep grafana | grep Up"
run_test "Jaeger container running" "docker-compose ps | grep jaeger | grep Up"

echo ""
echo "=== Database Tests ==="
run_test "TimescaleDB connection" "docker-compose exec timescaledb pg_isready -U postgres"
run_test "Database exists" "docker-compose exec timescaledb psql -U postgres -lqt | cut -d\\| -f1 | grep tradebase"

echo ""
echo "=== NATS Tests ==="
run_test "NATS monitoring endpoint" "curl -s http://localhost:8222/varz"
run_test "NATS JetStream enabled" "curl -s http://localhost:8222/varz | grep jetstream"

echo ""
echo "=== Redis Tests ==="
run_test "Redis connection" "docker-compose exec redis redis-cli ping"

echo ""
echo "=== Observability Tests ==="
run_test "Prometheus UI" "curl -s http://localhost:9090/-/healthy"
run_test "Grafana UI" "curl -s http://localhost:3001/api/health"
run_test "Jaeger UI" "curl -s http://localhost:16686/api/services"

echo ""
echo "=== Configuration Tests ==="
run_test "Config validation" "python scripts/validate-config.py"

echo ""
echo "=== Summary ==="
echo "Tests Passed: $tests_passed"
echo "Tests Failed: $tests_failed"
echo ""

if [ $tests_failed -eq 0 ]; then
    echo -e "${GREEN}✓ All Phase 1 tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Check output above.${NC}"
    exit 1
fi
```

**Usage:**
```bash
chmod +x test-phase1.sh
./test-phase1.sh
```

---

## Troubleshooting

### Issue: Docker containers won't start

```bash
# Check Docker daemon
docker ps

# Check for port conflicts
netstat -an | grep -E "4222|5432|6379|9090|3001|16686"

# Solution: Kill conflicting processes or change ports
```

### Issue: TimescaleDB init.sql not running

```bash
# Check if volume has existing data
docker volume inspect tradebase_timescaledb_data

# Solution: Reset volume
docker-compose down -v
docker-compose up -d
```

### Issue: NATS monitoring not accessible

```bash
# Check NATS logs
docker-compose logs nats

# Verify port mapping
docker-compose ps nats
```

### Issue: Grafana won't load

```bash
# Check Grafana logs
docker-compose logs grafana

# Try reset admin password
docker-compose exec grafana grafana-cli admin reset-admin-password admin
```

---

## Success Criteria

Phase 1 is successfully tested when:

- [x] All 6 Docker containers start successfully
- [x] TimescaleDB accepts connections and has hypertables
- [x] NATS server responds on monitoring port
- [x] Redis responds to ping command
- [x] Prometheus UI is accessible and scraping NATS
- [x] Grafana UI is accessible with Prometheus datasource
- [x] Jaeger UI is accessible
- [x] Config validation passes
- [x] Observability library imports work

---

## Test Results Template

Use this template to record your test results:

```
Phase 1 Test Results
Date: _______________
Tester: ______________

| Test Category | Passed | Failed | Notes |
|---------------|--------|--------|-------|
| Docker Environment | __ | __ | |
| TimescaleDB | __ | __ | |
| NATS | __ | __ | |
| Redis | __ | __ | |
| Prometheus | __ | __ | |
| Grafana | __ | __ | |
| Jaeger | __ | __ | |
| Configuration | __ | __ | |
| Observability | __ | __ | |

Overall: __ PASS / __ FAIL
```
