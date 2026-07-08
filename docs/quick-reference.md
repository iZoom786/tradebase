# Tradebase Platform - Quick Reference

## Phase Overview (12 Phases, 16 Weeks)

| Phase | Duration | Module | Key Outputs | Dependencies |
|-------|----------|--------|-------------|--------------|
| **1** | 2 weeks | Foundation | Docker env, observability stack | None |
| **2** | 1 week | Database | TimescaleDB schema, repository | Phase 1 |
| **3** | 1 week | Ingestion | YFinance provider, raw data NATS | Phase 2 |
| **4** | 1 week | Messaging | JWT/NKey auth, NATS core | Phase 1 |
| **5** | 1 week | Features | Indicators, sentiment engine | Phase 2,3,4 |
| **6** | 2 weeks | ML Engine | J48, XGBoost models | Phase 5 |
| **7** | 1 week | Paper Trading | Virtual account, execution | Phase 5,6 |
| **8** | 1 week | Subscription | Billing, JWT provisioning | Phase 4 |
| **9** | 1 week | Dashboard | Web UI, WebSocket | Phase 7,8 |
| **10** | 2 weeks | RL Pipeline | Gymnasium env, PPO | Phase 6 |
| **11** | 1 week | Feedback Loop | Auto-retraining, monitoring | Phase 6,7 |
| **12** | 2 weeks | Production | Load testing, deployment | All |

## Module Coupling Matrix

```
                 ┌───┐
                 │ 1 │ Foundation
                 └─┬─┘
           ┌───────┼────────┐
           ▼       ▼        ▼
      ┌───┐  ┌───┐  ┌─────┐
      │ 2 │  │ 4 │  │  3  │
      └─┬─┘  └─┬─┘  └──┬──┘  Database, NATS, Ingestion
         \     │     /    (can develop in parallel)
          \    │    /
           ▼   ▼   ▼
         ┌───┴───┴───┐
         │     5     │
         └─────┬─────┘  Features
               │
         ┌─────┴─────┐
         ▼           ▼
      ┌───┐       ┌───┐
      │ 6 │       │ 7 │  ML, Paper Trading
      └─┬─┘       └─┬─┘
        │           │
        └─────┬─────┘
              ▼
         ┌─────────┐
         │    8    │  Subscription
         └────┬────┘
              │
         ┌────┴─────┐
         ▼          ▼
      ┌───┐      ┌───┐
      │ 9 │      │10 │  Dashboard, RL
      └─┬─┘      └─┬─┘
        │          │
        └────┬─────┘
             ▼
        ┌────────┐
        │   11   │  Feedback Loop
        └───┬────┘
            │
            ▼
        ┌────────┐
        │   12   │  Production
        └────────┘
```

## Quick Start Commands

```bash
# Start development environment
docker-compose up -d

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=services --cov=libs

# Build for production
docker-compose -f docker-compose.prod.yml build

# Deploy to VPS
./scripts/deploy.sh

# Check logs
docker-compose logs -f ingestion
docker-compose logs -f ml-engine
```

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| TimescaleDB | 5432 | Database |
| NATS | 4222 | Messaging |
| NATS Monitor | 8222 | Monitoring |
| Redis | 6379 | Cache |
| API Gateway | 8000 | REST API |
| Dashboard | 3002 | Web UI |
| Grafana | 3001 | Metrics |
| Prometheus | 9090 | Metrics |
| Jaeger | 16686 | Tracing |

## NATS Subject Namespace

```
tradebase.<asset_class>.<symbol>.<stream_type>.<interval>

Examples:
- tradebase.forex.eurusd.raw.1m         (Basic tier)
- tradebase.forex.eurusd.features.1m   (Basic tier)
- tradebase.forex.eurusd.prediction.1m  (Premium tier)
- tradebase.public.papertrading.*        (Trial/Free)
```

## Tier Permissions

| Tier | Raw Data | Features | Predictions | Paper Trading |
|------|----------|----------|-------------|---------------|
| **Trial** | ❌ | ❌ | ❌ | ✅ (WebSocket) |
| **Basic** | ✅ | ✅ | ❌ | ❌ |
| **Premium** | ✅ | ✅ | ✅ | ❌ |

## Key Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Candle → NATS latency | <1ms | Tracing |
| Feature computation | <50ms | Tracing |
| ML prediction | <20ms | Tracing |
| NATS throughput | 10K+ connections | Load test |
| Model accuracy | >60% | Validation |
| System uptime | 99.9% | Monitoring |

## File Locations

```
tradebase/
├── services/           # Microservices
│   ├── ingestion/      # Data ingestion
│   ├── features/       # Feature calculation
│   ├── ml-engine/      # ML models
│   ├── paper-trading/  # Virtual trading
│   ├── subscription/   # Billing & auth
│   ├── api-gateway/    # FastAPI backend
│   └── dashboard/      # Web UI
├── libs/               # Shared libraries
│   ├── nats-client/    # NATS wrapper
│   ├── db-repo/        # DB abstraction
│   ├── indicators/     # Technical indicators
│   └── common/         # Utilities
├── infrastructure/     # Infra config
│   ├── docker/         # Compose files
│   ├── nats/           # NATS config
│   └── monitoring/     # Prometheus/Grafana
├── config/             # Environment configs
├── tests/              # Test suites
└── docs/              # Documentation
```

## Common Troubleshooting

### NATS Connection Issues
```bash
# Check NATS is running
docker-compose ps nats

# View NATS logs
docker-compose logs nats

# Test connection
telnet localhost 4222
```

### Database Issues
```bash
# Check TimescaleDB
docker-compose ps timescaledb

# Connect to DB
docker-compose exec timescaledb psql -U postgres -d tradebase

# Check hypertable status
\dt
SELECT * FROM timescaledb_information.hypertables;
```

### ML Model Not Loading
```bash
# Check model registry table
docker-compose exec timescaledb psql -U postgres -d tradebase
SELECT * FROM model_registry WHERE status = 'production';

# Verify model files
ls -la services/ml-engine/models/
```

## Development Workflow

1. **Start Phase 1**: Set up Docker environment
2. **Develop sequentially**: Each phase builds on previous
3. **Test each module**: Standalone testing before integration
4. **Commit frequently**: Small, focused commits
5. **Monitor metrics**: Check Grafana dashboards
6. **Review logs**: Use ELK for debugging

## Success Criteria per Phase

| Phase | Success Criteria |
|-------|------------------|
| 1 | `docker-compose up` runs all containers |
| 2 | Can insert/query market data |
| 3 | Ingestion running <100ms |
| 4 | JWT auth working, tier permissions enforced |
| 5 | All indicators compute correctly |
| 6 | Model accuracy >60% on validation |
| 7 | Paper trading P&L accurate |
| 8 | Can subscribe and receive JWT |
| 9 | Dashboard updates real-time |
| 10 | RL model trains without errors |
| 11 | Auto-retraining triggers correctly |
| 12 | System passes load tests |

## Deployment Checklist

- [ ] All tests passing
- [ ] Environment variables configured
- [ ] TLS certificates installed
- [ ] Database migrations run
- [ ] Models trained and deployed
- [ ] Monitoring dashboards configured
- [ ] Alert rules set up
- [ ] Backup schedule configured
- [ ] Documentation updated
- [ ] Runbook created

## Contact & Support

For issues or questions:
1. Check logs: `docker-compose logs <service>`
2. Check metrics: Grafana dashboard
3. Check documentation: `docs/`
4. Create GitHub issue with logs and metrics
