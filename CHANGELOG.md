# Changelog

All notable changes to the Tradebase AI Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - Phase 1: Foundation & Infrastructure ✅
- Complete Docker Compose development environment
- Observability stack (Prometheus, Grafana, Jaeger)
- Grafana datasources and dashboard provisioning
- CI/CD pipeline with comprehensive checks
- Pre-commit hooks for code quality
- Project structure with all service stubs
- Configuration management with Pydantic
- GitHub Actions workflows for CI/CD

### Added - Phase 3: Data Ingestion ✅
- YFinance data provider implementation
- MVC pattern for pluggable data sources
- Real-time 1-minute candle fetching
- Historical backfill capability
- NATS publishing of raw market data
- Configuration validation framework
- Comprehensive test coverage

### Added - Phase 4: NATS JWT/NKey Authentication ✅
- NKey manager for generating and managing cryptographic keypairs
- JWT manager for tier-based permission claims (Trial, Basic, Premium)
- NATS client with JWT/NKey authentication support
- NATS server configuration with JWT/NKey authentication
- Subscription service (Account Server) for JWT provisioning
- FastAPI REST endpoints for subscription management
- Tier-based subject permissions enforcement
- JWT validation and permission checking
- Comprehensive test suite for authentication
- JWT/NKey authentication documentation guide

### Changed
- Updated NATS configuration to use JWT auth mode
- Enhanced NATS client with signature callback support
- Added JWT/NKey configuration to environment variables

### Fixed
- Missing imports in ingestion controller (timedelta)
- Missing imports in data publisher (datetime)
- Missing imports in main.py (logging)

## [0.1.0] - 2024-01-XX

### Added
- Project structure and foundation
- Docker Compose development environment
- TimescaleDB with hypertables and continuous aggregates
- NATS messaging broker configuration
- Observability stack (Prometheus, Grafana, Jaeger)
- Data ingestion service (YFinance provider)
- NATS client library with reconnection
- Database repository pattern
- Configuration management with Pydantic
- Technical indicators library structure
- Documentation (architecture, implementation plan)

### Services
- **ingestion**: YFinance data provider with 1m candle fetching

### Libraries
- **nats-client**: NATS wrapper with auto-reconnect
- **db-repo**: TimescaleDB repository with async operations
- **common**: Configuration and observability utilities

### Infrastructure
- TimescaleDB schema with market_features hypertable
- NATS server with JetStream enabled
- Prometheus metrics collection
- Grafana dashboards
- Jaeger distributed tracing

## [Future]

### Planned (Phase 4-12)
- JWT/NKey authentication for NATS
- Feature calculation pipeline (5m, 15m, 30m, 1h, etc.)
- Machine Learning Engine (J48, XGBoost)
- Paper Trading System
- Subscription and Billing
- Web Dashboard
- RL Pipeline (PPO)
- Auto-retraining and feedback loop
- Production hardening

---

## Version Format

**MAJOR.MINOR.PATCH**

- **MAJOR**: Breaking changes, architectural redesigns
- **MINOR**: New features, services, or significant enhancements
- **PATCH**: Bug fixes, small improvements, documentation

### Example

```
1.2.3
│ │ │
│ │ └─ PATCH: Bug fix, small improvement
│ └─── MINOR: New feature, new service
└───── MAJOR: Breaking change
```

---

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release branch: `release/vX.Y.Z`
4. Update documentation
5. Create PR to main
6. Merge triggers CI/CD
7. Manual deploy to production
8. Create GitHub Release
