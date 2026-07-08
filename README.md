# Tradebase AI Platform

Event-driven, low-latency, machine-learning-powered trading platform specializing in real-time currency feature streams and premium execution signals.

## Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/tradebase.git
cd tradebase

# Install pre-commit hooks (recommended)
pip install pre-commit && pre-commit install

# Start development environment
docker-compose up -d

# View logs
docker-compose logs -f

# Run tests
pytest tests/ -v
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture-diagram.md) | System architecture and data flow |
| [Implementation Plan](docs/implementation-plan.md) | 12-phase development roadmap |
| [Quick Reference](docs/quick-reference.md) | Phase overview and quick commands |
| [CI/CD Guide](docs/cicd-guide.md) | Continuous integration/deployment |
| [Data Aggregation](docs/data-aggregation-strategy.md) | Timeframe materialized views strategy |
| [JWT/NKey Auth](docs/nats-jwt-auth-guide.md) | Authentication setup and usage |

## Services Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3001 | admin/admin |
| Prometheus | http://localhost:9090 | - |
| Jaeger | http://localhost:16686 | - |
| TimescaleDB | localhost:5432 | postgres/postgres |
| NATS | localhost:4222 | JWT/NKey required |
| Subscription API | http://localhost:8002 | See docs |

## CI/CD Status

[![CI](https://github.com/your-org/tradebase/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/tradebase/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/your-org/tradebase/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/tradebase)

## Architecture

## Services

| Service | Description | Status |
|---------|-------------|--------|
| [ingestion](services/ingestion/) | Data ingestion from YFinance | ✅ **Complete** |
| [subscription](services/subscription/) | JWT provisioning & auth | ✅ **Complete** |
| [features](services/features/) | Feature calculation pipeline | ❌ Phase 5 |
| [ml-engine](services/ml-engine/) | ML models (J48, XGBoost, RL) | ❌ Phase 6,10 |
| [paper-trading](services/paper-trading/) | Virtual trading simulation | ❌ Phase 7 |
| [api-gateway](services/api-gateway/) | FastAPI REST backend | ❌ Phase 8 |
| [dashboard](services/dashboard/) | Web UI with WebSocket | ❌ Phase 9 |

## Libraries

| Library | Description | Status |
|---------|-------------|--------|
| [nats-client](libs/nats_client/) | NATS wrapper with JWT/NKey auth | ✅ Complete |
| [db-repo](libs/db_repo/) | Database abstraction layer | ✅ Complete |
| [indicators](libs/indicators/) | Technical indicators library | ⚠️ Stub only |
| [common](libs/common/) | Shared utilities and observability | ✅ Complete |

## Configuration

Environment-specific configs in [config/](config/):

- `.env.example` - Template
- `.env.dev` - Development
- `.env.prod` - Production (git-ignored)

## Deployment

```bash
# Production build
docker-compose -f docker-compose.prod.yml build

# Deploy to VPS
./scripts/deploy.sh
```

## Documentation

- [Architecture](docs/architecture-diagram.md)
- [Implementation Plan](docs/implementation-plan.md)
- [Quick Reference](docs/quick-reference.md)
