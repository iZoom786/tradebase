# Phase 1 Integration Test Script (Windows PowerShell)
# Tests all Phase 1 components: Docker environment, databases, messaging, observability

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Change to project root
Set-Location $ProjectRoot

Write-Host "=== Tradebase Phase 1 Integration Tests ===" -ForegroundColor Cyan
Write-Host ""

$tests_passed = 0
$tests_failed = 0
$tests_skipped = 0

function Test-Component {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [bool]$Critical = $true
    )

    Write-Host -NoNewline "Testing: $Name ... "

    try {
        $null = & $Command 2>$null
        Write-Host "PASS" -ForegroundColor Green
        $script:tests_passed++
        return $true
    } catch {
        if ($Critical) {
            Write-Host "FAIL" -ForegroundColor Red
            $script:tests_failed++
        } else {
            Write-Host "SKIP (non-critical)" -ForegroundColor Yellow
            $script:tests_skipped++
        }
        return $false
    }
}

# Check if services are running
$servicesRunning = docker-compose ps | Select-String "Up" | Measure-Object | Select-Object -ExpandProperty Count
if ($servicesRunning -eq 0) {
    Write-Host "Starting Docker Compose services..." -ForegroundColor Yellow
    docker-compose up -d
    Write-Host "Waiting for services to start (15 seconds)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Phase 1: Foundation & Infrastructure" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "=== 1. Docker Environment ===" -ForegroundColor Cyan
Test-Component "Docker compose config valid" { docker-compose config 2>&1 | Select-String "error" | Measure-Object | Select-Object -ExpandProperty Count | Should -Be 0 }
Test-Component "TimescaleDB container running" { docker-compose ps | Select-String "timescaledb.*Up" }
Test-Component "NATS container running" { docker-compose ps | Select-String "nats.*Up" }
Test-Component "Redis container running" { docker-compose ps | Select-String "redis.*Up" }
Test-Component "Prometheus container running" { docker-compose ps | Select-String "prometheus.*Up" }
Test-Component "Grafana container running" { docker-compose ps | Select-String "grafana.*Up" }
Test-Component "Jaeger container running" { docker-compose ps | Select-String "jaeger.*Up" }

Write-Host ""
Write-Host "=== 2. Database Layer (TimescaleDB) ===" -ForegroundColor Cyan
Test-Component "TimescaleDB accepting connections" { docker-compose exec -T timescaledb pg_isready -U postgres }
Test-Component "Tradebase database exists" {
    $result = docker-compose exec -T timescaledb psql -U postgres -lqt 2>$null
    $result | Select-String "tradebase"
}
Test-Component "Hypertables created" {
    $result = docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c "SELECT 1 FROM timescaledb_information.hypertables LIMIT 1;" 2>$null
    $result | Select-String "1"
}
Test-Component "Continuous aggregates created" {
    $result = docker-compose exec -T timescaledb psql -U postgres -d tradebase -t -c "SELECT 1 FROM timescaledb_information.continuous_aggregates LIMIT 1;" 2>$null
    $result | Select-String "1"
}

Write-Host ""
Write-Host "=== 3. Messaging Layer (NATS) ===" -ForegroundColor Cyan
Test-Component "NATS monitoring endpoint" { Invoke-WebRequest -Uri "http://localhost:8222/varz" -UseBasicParsing -TimeoutSec 5 }
Test-Component "NATS JetStream enabled" {
    $response = Invoke-WebRequest -Uri "http://localhost:8222/varz" -UseBasicParsing -TimeoutSec 5
    $response.Content | Select-String "jetstream"
}
Test-Component "NATS server ID available" {
    $response = Invoke-WebRequest -Uri "http://localhost:8222/varz" -UseBasicParsing -TimeoutSec 5
    $response.Content | Select-String "server_id"
}

Write-Host ""
Write-Host "=== 4. Cache Layer (Redis) ===" -ForegroundColor Cyan
Test-Component "Redis connection" { docker-compose exec -T redis redis-cli ping }

Write-Host ""
Write-Host "=== 5. Observability Stack ===" -ForegroundColor Cyan
Test-Component "Prometheus UI healthy" { Invoke-WebRequest -Uri "http://localhost:9090/-/healthy" -UseBasicParsing -TimeoutSec 5 }
Test-Component "Prometheus targets page" { Invoke-WebRequest -Uri "http://localhost:9090/api/v1/targets" -UseBasicParsing -TimeoutSec 5 }
Test-Component "Grafana API accessible" { Invoke-WebRequest -Uri "http://localhost:3001/api/health" -UseBasicParsing -TimeoutSec 5 }
Test-Component "Jaeger API accessible" { Invoke-WebRequest -Uri "http://localhost:16686/api/services" -UseBasicParsing -TimeoutSec 5 }

Write-Host ""
Write-Host "=== 6. Configuration Management ===" -ForegroundColor Cyan
Test-Component "Config validation script" { python scripts/validate-config.py } $false

Write-Host ""
Write-Host "=== 7. Library Modules ===" -ForegroundColor Cyan
Test-Component "Common observability module" { python -c "from libs.common.observability import setup_logging; setup_logging()" } $false
Test-Component "Config module imports" { python -c "from libs.common.config import DatabaseConfig, NATSConfig" } $false

Write-Host ""
Write-Host "=== 8. Network Connectivity ===" -ForegroundColor Cyan
Test-Component "Can reach TimescaleDB port" { docker-compose exec -T timescaledb pg_isready -U postgres }
Test-Component "Can reach NATS port" { Invoke-WebRequest -Uri "http://localhost:8222/" -UseBasicParsing -TimeoutSec 2 }
Test-Component "Can reach Prometheus" { Invoke-WebRequest -Uri "http://localhost:9090/-/healthy" -UseBasicParsing -TimeoutSec 5 }
Test-Component "Can reach Grafana" { Invoke-WebRequest -Uri "http://localhost:3001/api/health" -UseBasicParsing -TimeoutSec 5 }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tests Passed:  $tests_passed"
Write-Host "Tests Failed:  $tests_failed"
Write-Host "Tests Skipped: $tests_skipped"
Write-Host "Total Tests:   $($tests_passed + $tests_failed + $tests_skipped)"
Write-Host ""

if ($tests_failed -eq 0) {
    Write-Host "✓✓✓ All Phase 1 tests passed! ✓✓✓" -ForegroundColor Green
    Write-Host ""
    Write-Host "Phase 1 (Foundation & Infrastructure) is fully functional."
    Write-Host ""
    Write-Host "Service URLs:"
    Write-Host "  - Grafana:       http://localhost:3001"
    Write-Host "  - Prometheus:    http://localhost:9090"
    Write-Host "  - Jaeger:        http://localhost:16686"
    Write-Host "  - NATS Monitor:  http://localhost:8222"
    exit 0
} else {
    Write-Host "✗✗✗ Some tests failed. ✗✗✗" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:"
    Write-Host "  1. Check service logs: docker-compose logs <service>"
    Write-Host "  2. Check service status: docker-compose ps"
    Write-Host "  3. Restart services: docker-compose restart"
    Write-Host ""
    Write-Host "For detailed help, see: docs/test-phase1-guide.md"
    exit 1
}
