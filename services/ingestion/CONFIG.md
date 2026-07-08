# Ingestion Service Configuration Guide

## Overview

The ingestion service validates all configuration on startup using Pydantic. Invalid configuration will prevent the service from starting and provide clear error messages.

## Configuration Sections

### 1. Database Configuration (`DB_*`)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DB_HOST` | string | `localhost` | Database host address |
| `DB_PORT` | integer | `5432` | Database port (1-65535) |
| `DB_DATABASE` | string | `tradebase` | Database name |
| `DB_USER` | string | `postgres` | Database user |
| `DB_PASSWORD` | string | `postgres` | Database password |
| `DB_POOL_SIZE` | integer | `20` | Connection pool size (1-100) |

**Validation:**
- Port must be between 1-65535
- Database name must contain only alphanumeric characters, underscores, and hyphens
- Pool size must be between 1-100

### 2. NATS Configuration (`NATS_*`)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `NATS_URL` | string | `nats://localhost:4222` | NATS server URL |
| `NATS_MAX_RECONNECT` | integer | `10` | Max reconnection attempts (0-100) |
| `NATS_PING_INTERVAL` | integer | `60` | Ping interval in seconds (10-300) |
| `NATS_CONNECT_TIMEOUT` | integer | `5` | Connection timeout (1-60) |

**Validation:**
- URL must start with `nats://` and format: `nats://host:port`
- All numeric constraints as shown above

### 3. Observability Configuration (`OBS_*`)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OBS_JAEGER_ENDPOINT` | string | `None` | Jaeger tracing endpoint |
| `OBS_PROMETHEUS_PORT` | integer | `9091` | Metrics port (1024-65535) |
| `OBS_LOG_LEVEL` | string | `INFO` | Logging level |
| `OBS_ENABLE_TRACING` | boolean | `true` | Enable distributed tracing |
| `OBS_ENABLE_METRICS` | boolean | `true` | Enable Prometheus metrics |

**Validation:**
- Log level must be one of: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- Prometheus port must be valid port number

### 4. Ingestion Configuration (`INGESTION_*`)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `INGESTION_PROVIDER` | enum | `yfinance` | Data provider (yfinance, alpaca, mt5) |
| `INGESTION_SYMBOLS` | list | `EURUSD,GBPUSD,USDJPY` | Comma-separated symbols (1-50) |
| `INGESTION_INTERVAL` | enum | `1m` | Candle interval (1m, 5m, 15m, 1h, 1d) |
| `INGESTION_BACKFILL_DAYS` | integer | `365` | Historical days to backfill (1-3650) |
| `INGESTION_FETCH_DELAY_SECONDS` | integer | `5` | Seconds past minute to fetch (0-59) |
| `INGESTION_RETRY_ATTEMPTS` | integer | `3` | Retry attempts (0-10) |
| `INGESTION_RETRY_DELAY_SECONDS` | float | `1.0` | Retry delay (0.1-30.0) |
| `INGESTION_ASSET_CLASS` | enum | `forex` | Asset class for NATS subjects |
| `INGESTION_ENABLE_BACKFILL` | boolean | `true` | Enable backfill on startup |

**Validation:**
- Symbols must be 3-12 alphanumeric characters
- No duplicate symbols allowed
- Interval must be supported by the selected provider
- Provider-specific validation applied

## Example Configurations

### Development (`.env.dev`)
```bash
DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=tradebase_dev
DB_USER=postgres
DB_PASSWORD=postgres

NATS_URL=nats://localhost:4222
NATS_MAX_RECONNECT=10

OBS_LOG_LEVEL=DEBUG
OBS_PROMETHEUS_PORT=9091

INGESTION_PROVIDER=yfinance
INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY
INGESTION_INTERVAL=1m
INGESTION_BACKFILL_DAYS=30
```

### Production (`.env.prod`)
```bash
DB_HOST=timescaledb.prod.internal
DB_PORT=5432
DB_DATABASE=tradebase_prod
DB_USER=tradebase_rw
DB_PASSWORD=${DB_PASSWORD}

NATS_URL=nats://nats.prod.internal:4222
NATS_MAX_RECONNECT=100

OBS_JAEGER_ENDPOINT=http://jaeger.prod.internal:14268/api/traces
OBS_LOG_LEVEL=INFO

INGESTION_PROVIDER=yfinance
INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD
INGESTION_INTERVAL=1m
INGESTION_BACKFILL_DAYS=365
```

## Validation

### Validate Configuration Before Running

```bash
# Using the validation script
python scripts/validate-config.py

# Validate with custom environment
INGESTION_SYMBOLS=XYZ,ABC python scripts/validate-config.py
```

### Sample Validation Output

**Success:**
```
============================================================
  TRADEBASE INGESTION SERVICE - CONFIGURATION VALIDATION
============================================================

[1/4] Database Configuration
✓ Host: localhost:5432
✓ Database: tradebase
✓ User: postgres
✓ Pool Size: 20

[2/4] NATS Configuration
✓ URL: nats://localhost:4222
✓ Max Reconnect: 10

[3/4] Observability Configuration
✓ Log Level: INFO
✓ Prometheus Port: 9091

[4/4] Ingestion Configuration
✓ Provider: yfinance
✓ Symbols: EURUSD, GBPUSD, USDJPY
✓ Interval: 1m

============================================================
  SUMMARY
============================================================
✓ Configuration is valid!
```

**Failure:**
```
[4/4] Ingestion Configuration
✗ symbols
  Symbol 'INVALID_123' must contain only alphanumeric characters

✗ interval
  Interval '99m' not supported by YFinance
```

## Configuration Errors

### Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `Symbol 'X' must be 3-12 characters` | Invalid symbol format | Use proper forex pairs like `EURUSD` |
| `Duplicate symbols found` | Symbol repeated in list | Remove duplicates |
| `NATS URL must start with 'nats://'` | Invalid URL format | Use `nats://host:port` format |
| `Interval not supported by YFinance` | Invalid interval | Use: `1m`, `5m`, `15m`, `1h`, `1d` |
| `Port out of range` | Invalid port number | Use port between 1-65535 |

## Best Practices

1. **Use environment files** - Store configuration in `.env` files (don't commit secrets)
2. **Validate before deployment** - Run validation script before deploying
3. **Document changes** - Update this doc when adding new variables
4. **Use defaults** - Only override what you need
5. **Separate environments** - Use different configs for dev/staging/prod
