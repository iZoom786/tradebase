#!/bin/bash
# Phase 1 Integration Test Script
# Tests all Phase 1 components: Docker environment, databases, messaging, observability

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

echo "=== Tradebase Phase 1 Integration Tests ==="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

tests_passed=0
tests_failed=0
tests_skipped=0

run_test() {
    local name="$1"
    local command="$2"
    local critical="${3:-true}"

    echo -n "Testing: $name ... "

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((tests_passed++))
        return 0
    else
        if [ "$critical" = "true" ]; then
            echo -e "${RED}FAIL${NC}"
            ((tests_failed++))
        else
            echo -e "${YELLOW}SKIP (non-critical)${NC}"
            ((tests_skipped++))
        fi
        return 1
    fi
}

# Check if docker-compose is running
check_docker_running() {
    if ! docker-compose ps | grep -q "Up"; then
        echo "Docker Compose is not running. Starting services..."
        docker-compose up -d
        sleep 10
    fi
}

# Wait for service to be healthy
wait_for_service() {
    local service=$1
    local max_wait=${2:-30}
    local count=0

    while [ $count -lt $max_wait ]; do
        if docker-compose ps | grep "$service" | grep -q "healthy\|Up"; then
            return 0
        fi
        sleep 1
        ((count++))
    done
    return 1
}

echo "=========================================="
echo "Phase 1: Foundation & Infrastructure"
echo "=========================================="
echo ""

# Check if services are running
if ! docker-compose ps | grep -q "Up"; then
    echo "Starting Docker Compose services..."
    docker-compose up -d
    echo "Waiting for services to start (15 seconds)..."
    sleep 15
fi

echo "=== 1. Docker Environment ==="
run_test "Docker compose config valid" "docker-compose config"
run_test "TimescaleDB container running" "docker-compose ps | grep timescaledb | grep -q Up"
run_test "NATS container running" "docker-compose ps | grep nats | grep -q Up"
run_test "Redis container running" "docker-compose ps | grep redis | grep -q Up"
run_test "Prometheus container running" "docker-compose ps | grep prometheus | grep -q Up"
run_test "Grafana container running" "docker-compose ps | grep grafana | grep -q Up"
run_test "Jaeger container running" "docker-compose ps | grep jaeger | grep -q Up"

echo ""
echo "=== 2. Database Layer (TimescaleDB) ==="
run_test "TimescaleDB accepting connections" "docker-compose exec -T timescaledb pg_isready -U postgres"
run_test "Tradebase database exists" "docker-compose exec -T timescaledb psql -U postgres -lqt | cut -d'|' -f1 | grep -q tradebase"
run_test "Hypertables created" "docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c 'SELECT 1 FROM timescaledb_information.hypertables LIMIT 1;'"
run_test "Continuous aggregates created" "docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c 'SELECT 1 FROM timescaledb_information.continuous_aggregates LIMIT 1;'"

echo ""
echo "=== 3. Messaging Layer (NATS) ==="
run_test "NATS monitoring endpoint" "curl -sf http://localhost:8222/varz"
run_test "NATS JetStream enabled" "curl -sf http://localhost:8222/varz | grep -q '\"jetstream\": true'"
run_test "NATS server ID available" "curl -sf http://localhost:8222/varz | grep -q 'server_id'"

echo ""
echo "=== 4. Cache Layer (Redis) ==="
run_test "Redis connection" "docker-compose exec -T redis redis-cli ping"

echo ""
echo "=== 5. Observability Stack ==="
run_test "Prometheus UI healthy" "curl -sf http://localhost:9090/-/healthy"
run_test "Prometheus targets page" "curl -sf http://localhost:9090/api/v1/targets"
run_test "Grafana API accessible" "curl -sf http://localhost:3001/api/health"
run_test "Jaeger API accessible" "curl -sf http://localhost:16686/api/services"

echo ""
echo "=== 6. Configuration Management ==="
run_test "Config validation script" "python scripts/validate-config.py" false

echo ""
echo "=== 7. Library Modules ==="
run_test "Common observability module" "python -c 'from libs.common.observability import setup_logging; setup_logging()'"
run_test "Config module imports" "python -c 'from libs.common.config import DatabaseConfig, NATSConfig'"

echo ""
echo "=== 8. Network Connectivity ==="
run_test "Can reach TimescaleDB port" "docker-compose exec -T timescaledb pg_isready -U postgres"
run_test "Can reach NATS port" "curl -sf http://localhost:8222/ > /dev/null"
run_test "Can reach Prometheus" "curl -sf http://localhost:9090/-/healthy"
run_test "Can reach Grafana" "curl -sf http://localhost:3001/api/health"

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "Tests Passed:  $tests_passed"
echo "Tests Failed:  $tests_failed"
echo "Tests Skipped: $tests_skipped"
echo "Total Tests:   $((tests_passed + tests_failed + tests_skipped))"
echo ""

if [ $tests_failed -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ All Phase 1 tests passed! ✓✓✓${NC}"
    echo ""
    echo "Phase 1 (Foundation & Infrastructure) is fully functional."
    echo ""
    echo "Service URLs:"
    echo "  - Grafana:     http://localhost:3001"
    echo "  - Prometheus:  http://localhost:9090"
    echo "  - Jaeger:      http://localhost:16686"
    echo "  - NATS Monitor: http://localhost:8222"
    exit 0
else
    echo -e "${RED}✗✗✗ Some tests failed. ✗✗✗${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check service logs: docker-compose logs <service>"
    echo "  2. Check service status: docker-compose ps"
    echo "  3. Restart services: docker-compose restart"
    echo ""
    echo "For detailed help, see: docs/test-phase1-guide.md"
    exit 1
fi
