# Ingestion Service

Data ingestion service for fetching market data from various providers (YFinance, Alpaca, MT5) and publishing to NATS.

## Architecture

MVC Pattern for pluggable data sources:
- **models/** - Data models (MarketData, SourceConfig)
- **views/** - NATS publishing interface (DataPublisher)
- **controllers/** - Orchestration (IngestionController, Scheduler)
- **providers/** - Data source implementations (yfinance.py, alpaca.py, mt5.py)

## Quick Start

```bash
# Run ingestion service
python -m services.ingestion.main

# Ingest specific symbols
python -m services.ingestion.main --symbols EURUSD GBPUSD

# Backfill historical data
python -m services.ingestion.backfill --symbol EURUSD --days 365
```

## Configuration

```yaml
ingestion:
  provider: yfinance  # yfinance, alpaca, mt5
  symbols:
    - EURUSD
    - GBPUSD
    - USDJPY
  interval: 1m
  backfill_days: 365
```

## API Endpoints

None - this is a background service that publishes to NATS.

## NATS Subjects

Publishes to:
- `tradebase.forex.{symbol}.raw.1m` - Raw OHLCV data

## Status

✅ **Phase 3** - Complete

## Dependencies

- Phase 2: Database Layer ✅
- Phase 4: NATS Core ✅
