# CI/CD Pipeline Guide

## Overview

The Tradebase platform uses GitHub Actions for continuous integration and deployment. All code changes are automatically tested, and successful builds are deployed to staging/production.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CI/CD FLOW                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Developer Push/PR                                                      │
│  ┌────────────────┐                                                      │
│  │  Code Change   │                                                      │
│  └────────┬───────┘                                                      │
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    CI Pipeline (ci.yml)                           │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  1. Code Quality (Black, Ruff, MyPy)                           │   │
│  │  2. Tests (pytest with coverage)                                │   │
│  │  3. Security Scan (Bandit, Safety)                              │   │
│  │  4. Docker Build Validation                                     │   │
│  │  5. Configuration Validation                                    │   │
│  │  6. Docker Compose Validation                                  │   │
│  └────────────────────┬────────────────────────────────────────────┘   │
│                       │                                                    │
│           ┌───────────┴───────────┐                                    │
│           │  All Checks Pass?     │                                    │
│           └───────┬───────┬───────┘                                    │
│                   │       │                                            │
│            No:    │       │    Yes:                                    │
│                   ▼       ▼                                            │
│              ┌─────┐  ┌────────────────┐                               │
│              │ FAIL│  │ Build & Push   │                               │
│              └─────┘  │ Docker Images  │                               │
│                       └───────┬────────┘                               │
│                               │                                        │
│               ┌───────────────┼───────────────┐                        │
│               │               │               │                        │
│               ▼               ▼               ▼                        │
│         ┌─────────┐     ┌─────────┐     ┌─────────┐                   │
│         │ PR Only │     │  Main   │     │ Manual  │                   │
│         │         │     │  Branch │     │Trigger │                   │
│         └─────────┘     └────┬────┘     └────┬────┘                   │
│                              │               │                          │
│                              ▼               ▼                          │
│                    ┌──────────────────────────────┐                       │
│                    │     Deploy Pipeline         │                       │
│                    │     (deploy.yml)            │                       │
│                    ├──────────────────────────────┤                       │
│                    │ 1. Tag Release             │                       │
│                    │ 2. Deploy to Staging       │                       │
│                    │ 3. Health Checks           │                       │
│                    │ 4. Deploy to Production*    │                       │
│                    │ 5. Monitoring              │                       │
│                    │ 6. Notification            │                       │
│                    └──────────────────────────────┘                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

* Production deploy requires manual approval
```

## GitHub Workflows

### 1. CI Pipeline ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))

**Triggers:**
- Pull requests to `main` or `develop` branches
- Push to `main` or `develop` branches
- Manual workflow dispatch

**Jobs:**

| Job | Purpose | Tools |
|-----|---------|-------|
| **code-quality** | Format, lint, type check | Black, Ruff, MyPy |
| **test** | Unit & integration tests | pytest, pytest-cov |
| **security** | Security vulnerability scan | Bandit, Safety |
| **docker** | Build validation | docker/build-push |
| **config-validation** | Config schema validation | Pydantic |
| **compose-validation** | Docker Compose validation | docker-compose |

**Success Criteria:**
- All tests pass with >70% coverage
- No security vulnerabilities
- Docker images build successfully
- Configuration validates

### 2. CD Pipeline ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml))

**Triggers:**
- Push to `main` branch (automatic deploy to staging)
- Manual workflow dispatch (staging or production)

**Jobs:**

| Job | Purpose |
|-----|---------|
| **build** | Build and push Docker images to registry |
| **tag** | Create git tag and GitHub release |
| **deploy-staging** | Deploy to staging environment |
| **deploy-production** | Deploy to production (requires approval) |
| **notify** | Send Slack notifications |

## Pre-commit Hooks ([`.pre-commit-config.yaml`](.pre-commit-config.yaml))

Before committing code, pre-commit runs:

| Hook | Check |
|------|-------|
| **trailing-whitespace** | Remove trailing whitespace |
| **black** | Python formatting |
| **ruff** | Python linting |
| **mypy** | Type checking |
| **bandit** | Security linting |
| **hadolint** | Dockerfile linting |
| **shellcheck** | Shell script linting |
| **yamllint** | YAML linting |

**Install:**
```bash
pip install pre-commit
pre-commit install
```

**Run manually:**
```bash
pre-commit run --all-files
```

## Docker Build Strategy

### Multi-stage Build

```dockerfile
# Stage 1: Builder (compile + dependencies)
FROM python:3.11-slim AS builder
# ... build steps

# Stage 2: Runtime (minimal image)
FROM python:3.11-slim
# ... copy from builder
```

### Image Tagging

| Tag | When Used | Example |
|-----|-----------|---------|
| `latest` | Main branch | `tradebase/ingestion:latest` |
| `v1.0.0` | Release | `tradebase/ingestion:v1.0.0` |
| `main-abc123` | Branch commit | `tradebase/ingestion:main-abc123` |
| `test` | CI build | `tradebase/ingestion:test` |

## Environments

### Development
```bash
docker-compose up
```

### Staging
```bash
docker-compose -f docker-compose.staging.yml up -d
```

### Production
```bash
docker-compose -f docker-compose.prod.yml up -d
```

| Environment | URL | Purpose |
|-------------|-----|---------|
| **Development** | localhost | Local development |
| **Staging** | staging.tradebase.com | Pre-production testing |
| **Production** | tradebase.com | Live platform |

## Secrets Required

### For CI (.github/workflows/ci.yml)
- None required (uses public services)

### For CD (.github/workflows/deploy.yml)

| Secret | Description | Example |
|--------|-------------|---------|
| `STAGING_HOST` | Staging server hostname | `staging.tradebase.com` |
| `STAGING_USER` | SSH username | `ubuntu` |
| `STAGING_SSH_KEY` | SSH private key | `-----BEGIN RSA PRIVATE KEY-----` |
| `STAGING_PORT` | SSH port | `22` |
| `PRODUCTION_HOST` | Production hostname | `tradebase.com` |
| `PRODUCTION_USER` | SSH username | `ubuntu` |
| `PRODUCTION_SSH_KEY` | SSH private key | `-----BEGIN RSA PRIVATE KEY-----` |
| `PRODUCTION_PORT` | SSH port | `22` |
| `SLACK_WEBHOOK` | Slack webhook URL | `https://hooks.slack.com/...` |

### For Application Services

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_PASSWORD` | Database password | `postgres` |
| `GRAFANA_PASSWORD` | Grafana admin password | `admin` |
| `NKEY_SEED` | NATS NKey seed | Generated |

## Deployment Process

### Staging Deployment (Automatic)

1. **Trigger**: Push to `main` branch
2. **Build**: Docker images built and pushed
3. **Deploy**: Deployed via SSH to staging server
4. **Health Check**: Services verified
5. **Notification**: Slack status update

### Production Deployment (Manual)

1. **Trigger**: Manual workflow dispatch
2. **Approval**: Requires GitHub approval
3. **Backup**: Database backup created
4. **Deploy**: Zero-downtime deployment
5. **Monitor**: 5-minute monitoring period
6. **Rollback**: Automatic on failure

## Rollback Procedure

If deployment fails:

```bash
# SSH to server
ssh production

# Navigate to project
cd /opt/tradebase

# Restore previous version
git checkout <previous-commit>

# Restart services
docker-compose -f docker-compose.prod.yml up -d --force-recreate

# Verify
docker-compose ps
curl https://api.tradebase.com/health
```

## Monitoring

### CI Pipeline Status

Check in GitHub Actions tab:
- [Tradebase CI](https://github.com/your-org/tradebase/actions)

### Deployment Status

Check in Grafana:
- [Staging Dashboard](https://staging.tradebase.com/grafana)
- [Production Dashboard](https://tradebase.com/grafana)

### Alerts

Alerts sent to Slack for:
- CI pipeline failures
- Deployment failures
- Health check failures
- Performance degradation

## Best Practices

### For Developers

1. **Run pre-commit locally** before pushing
2. **Write tests** for new features
3. **Update documentation** for API changes
4. **Use semantic commits** (feat:, fix:, docs:)
5. **Create PRs** for review before merging

### For Releases

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md**
3. **Create release branch**
4. **Test in staging** thoroughly
5. **Manual deploy** to production

## Troubleshooting

### CI Pipeline Fails

```bash
# Check code quality
make black
make ruff
make mypy

# Run tests locally
pytest tests/ -v

# Validate configs
python scripts/validate-config.py
```

### Deployment Fails

```bash
# Check server logs
ssh staging
docker-compose logs -f ingestion

# Check service health
curl http://staging.tradebase.com/health

# Restart services
docker-compose restart ingestion
```

### Docker Build Fails

```bash
# Clean docker cache
docker system prune -af

# Rebuild without cache
docker-compose build --no-cache

# Check disk space
df -h
```

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [Pre-commit Documentation](https://pre-commit.com/)
- [TimescaleDB Deployment](https://docs.timescale.com/timescaledb/latest/how-to-guides/deployment/)
