# JWT Authentication & TLS Setup Guide

This guide covers the setup and usage of JWT authentication and TLS certificates for NATS in the Tradebase platform.

## Overview

The Tradebase platform uses **JWT/NKey authentication** for securing NATS connections and **TLS** for encrypted communication. This setup provides:

- **Tier-based access control**: Trial, Basic, and Premium tiers with different permissions
- **Secure connections**: TLS encryption for all NATS traffic
- **User provisioning**: Automated JWT generation and NKey management
- **Token validation**: JWT resolver endpoint for real-time validation

## Quick Start

### 1. Generate TLS Certificates (Development)

For **development**, use the provided scripts to generate self-signed certificates:

```bash
# On Linux/macOS
cd scripts
bash generate-nats-certs.sh

# On Windows
cd scripts
powershell -ExecutionPolicy Bypass -File generate-nats-certs.ps1
```

This creates certificates in `infrastructure/nats/certs/`:
- `ca.crt` - CA certificate (trust this in your browser/system)
- `server.crt` / `server.key` - Server certificate and key
- `client.crt` / `client.key` - Client certificate and key (for mTLS)

### 2. Configure Environment Variables

Copy the example environment file and update values:

```bash
cp .env.example .env
```

Update the following variables in `.env`:

```bash
# NATS System User (for internal services)
NATS_SYSTEM_USER=system_internal
NATS_SYSTEM_PASSWORD=your_secure_password_here

# JWT Issuer Seed (generate a secure random string)
JWT_ISSUER_SEED=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Enable TLS (optional, for development)
NATS_TLS_ENABLED=false
```

### 3. Start Services with JWT Auth

```bash
# Start all services
docker-compose up -d

# Check NATS logs
docker-compose logs -f nats
```

### 4. Test JWT Authentication

```bash
# Create a trial user
curl -X POST http://localhost:8002/auth/trial \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Response includes JWT
{
  "user_id": "...",
  "tier": "trial",
  "jwt": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "websocket_url": "wss://tradebase.com/trail"
}
```

## Architecture

### JWT Authentication Flow

```
┌─────────────┐                     ┌──────────────┐
│   Client    │                     │ Subscription │
│  Application│                     │   Service    │
└──────┬──────┘                     └──────┬───────┘
       │                                   │
       │ 1. Request subscription          │
       ├──────────────────────────────────►│
       │                                   │
       │ 2. Return JWT + NKey              │
       │◄──────────────────────────────────┤
       │                                   │
       │ 3. Connect to NATS with JWT       │
       │    ┌─────────────────┐            │
       │    │   NATS Server   │            │
       │    └────────┬────────┘            │
       │             │                     │
       │ 4. Validate JWT                  │
       ├────────────────────────────────────►│
       │             │                     │
       │ 5. Return permissions            │
       │◄──────────────────────────────────┤
       │             │                     │
       │ 6. Connection allowed/denied      │
       │◄─────────────────────────────────┘
```

### TLS Configuration

NATS TLS is configured in `infrastructure/nats/nats_jwt_auth.conf`:

```nginx
tls {
    cert_file: /etc/nats/certs/server.crt
    key_file: /etc/nats/certs/server.key
    ca_file: /etc/nats/certs/ca.crt
    verify: false
    min_version: "1.2"
}
```

## Tier Permissions

### Trial Tier

- **Allowed subjects**:
  - `tradebase.public.papertrading.*`
- **Denied subjects**:
  - All publish operations
  - Raw market data
  - Features
  - Predictions

### Basic Tier

- **Allowed subjects**:
  - `tradebase.forex.*.raw.*`
  - `tradebase.forex.*.features.*`
- **Denied subjects**:
  - All publish operations
  - Predictions
  - Paper trading

### Premium Tier

- **Allowed subjects**:
  - `tradebase.>` (all subjects)
- **Denied subjects**:
  - All publish operations

## API Usage

### Create Trial User

```bash
curl -X POST http://localhost:8002/auth/trial \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

**Response:**
```json
{
  "user_id": "uuid-here",
  "tier": "trial",
  "jwt": "eyJ0eXAi...",
  "websocket_url": "wss://tradebase.com/trial",
  "expires_at": "2026-08-06T00:00:00Z"
}
```

### Create Basic Subscription

```bash
curl -X POST http://localhost:8002/auth/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "tier": "basic",
    "duration_days": 30,
    "email": "user@example.com"
  }'
```

**Response:**
```json
{
  "user_id": "user-123",
  "tier": "basic",
  "jwt": "eyJ0eXAi...",
  "nkey_seed": "SUAB...",
  "nkey_public": "UAA...",
  "expires_at": "2026-08-06T00:00:00Z",
  "nats_url": "nats://tradebase.com:4222"
}
```

### Create Premium Subscription

```bash
curl -X POST http://localhost:8002/auth/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-456",
    "tier": "premium",
    "duration_days": 30
  }'
```

### Upgrade Subscription

```bash
curl -X PUT http://localhost:8002/auth/upgrade/user-123 \
  -H "Content-Type: application/json" \
  -d '{"new_tier": "premium"}'
```

### Validate JWT

```bash
curl -X POST http://localhost:8002/auth/validate \
  -H "Content-Type: application/json" \
  -d '{"token": "eyJ0eXAi..."}'
```

**Response:**
```json
{
  "valid": true,
  "tier": "basic",
  "user_id": "user-123",
  "expires_at": "2026-08-06T00:00:00Z"
}
```

### Check Permissions

```bash
curl "http://localhost:8002/permissions/user-123?subject=tradebase.forex.eurusd.raw.1m&action=sub"
```

**Response:**
```json
{
  "user_id": "user-123",
  "subject": "tradebase.forex.eurusd.raw.1m",
  "action": "sub",
  "allowed": true
}
```

## Client Connection Examples

### Python Client with JWT

```python
import asyncio
import nats
from libs.nats_client.client import NATSClient
from libs.nats_client.auth import NATSAuthClient

# Create user and get JWT
auth_client = NATSAuthClient()
jwt_token, nkey_seed, public_key = auth_client.create_user(
    user_id="my-user",
    tier="basic"
)

# Connect to NATS with JWT
config = NATSConfig(url="nats://localhost:4222")
client = NATSClient(
    config=config,
    user_jwt=jwt_token,
    user_seed=nkey_seed
)

await client.connect()

# Subscribe to allowed subject
async def on_message(msg):
    print(f"Received: {msg.data.decode()}")

await client.subscribe(
    "tradebase.forex.eurusd.raw.1m",
    cb=on_message
)
```

### Python Client with TLS

```python
# For TLS connections
config = NATSConfig(
    url="nats://localhost:4222",
    tls_enabled=True,
    ca_cert="./infrastructure/nats/certs/ca.crt",
    client_cert="./infrastructure/nats/certs/client.crt",
    client_key="./infrastructure/nats/certs/client.key"
)

client = NATSClient(config=config)
await client.connect()
```

### WebSocket Client (JavaScript)

```javascript
// Trial user connects via WebSocket
const trialJwt = "eyJ0eXAi...";

const nc = await NATS.connect({
  servers: "wss://tradebase.com:8080",
  userJWT: trialJwt
});

// Subscribe to paper trading feed
const sub = nc.subscribe("tradebase.public.papertrading.*", {
  callback: (err, msg) => {
    if (err) {
      console.error("Error:", err);
      return;
    }
    console.log("Trade update:", msg.data);
  }
});
```

## Testing

### Run JWT Authentication Tests

```bash
# Run all JWT auth tests
pytest tests/test_nats_client/test_jwt_auth_flow.py -v

# Run specific test
pytest tests/test_nats_client/test_jwt_auth_flow.py::TestPermissions::test_trial_permissions -v

# Run with coverage
pytest tests/test_nats_client/test_jwt_auth_flow.py -v --cov=libs/nats_client
```

### Test Permission Matrix

```python
from tests.test_nats_client.test_jwt_auth_flow import JWTAuthTestHelper

# Create users for each tier
trial_jwt, _, _ = JWTAuthTestHelper.create_test_user("trial")
basic_jwt, _, _ = JWTAuthTestHelper.create_test_user("basic")
premium_jwt, _, _ = JWTAuthTestHelper.create_test_user("premium")

# Verify trial permissions
JWTAuthTestHelper.verify_permissions(
    trial_jwt,
    allowed_subjects=["tradebase.public.papertrading.eurusd"],
    denied_subjects=[
        "tradebase.forex.eurusd.raw.1m",
        "tradebase.forex.eurusd.features.1m",
        "tradebase.forex.eurusd.prediction.1m"
    ]
)
```

## Production Considerations

### 1. Use a Proper CA

In production, use certificates from a trusted CA like Let's Encrypt:

```bash
# Use certbot for Let's Encrypt
certbot certonly --standalone -d nats.tradebase.com
```

### 2. Secure JWT Issuer Seed

Store the JWT issuer seed securely:

```bash
# Use AWS Secrets Manager, HashiCorp Vault, etc.
export JWT_ISSUER_SEED=$(aws secretsmanager get-secret-value \
  --secret-id tradebase/jwt-issuer-seed \
  --query SecretString --output text)
```

### 3. Enable TLS Verification

Update NATS config for production:

```nginx
tls {
    verify: true
    verify_and_map: true
}
```

### 4. Use NATS Account Server

For production, deploy a NATS Account Server for JWT resolution:

```yaml
# docker-compose.prod.yml
account-server:
  image: natsio/account-server:latest
  ports:
    - "9090:9090"
  volumes:
    - ./infrastructure/nats/accounts:/data
```

### 5. Monitor JWT Expiration

Implement cleanup for expired subscriptions:

```bash
# Run daily
curl -X POST http://localhost:8002/subscriptions/cleanup-expired
```

## Troubleshooting

### NATS Connection Failed

**Problem:** Cannot connect to NATS with JWT

**Solutions:**
1. Check NATS is running: `docker-compose ps nats`
2. Check JWT is valid: `curl http://localhost:8002/auth/validate -d '{"token":"..."}'`
3. Check NATS logs: `docker-compose logs nats`
4. Verify tier permissions

### TLS Handshake Failed

**Problem:** TLS connection fails

**Solutions:**
1. Verify certificates exist: `ls infrastructure/nats/certs/`
2. Check certificate permissions
3. Re-generate certificates if needed
4. Trust CA certificate on your system

### Permission Denied

**Problem:** Cannot subscribe to subject

**Solutions:**
1. Check tier permissions matrix
2. Verify subject format matches allowed patterns
3. Check JWT hasn't expired
4. Test with permission check endpoint

## References

- [NATS JWT Authentication](https://docs.nats.io/running-a-nats-service/configuration/securing_nats/auth_intro/jwt)
- [NATS TLS](https://docs.nats.io/running-a-nats-service/configuration/securing_nats/tls)
- [Python NKeys](https://github.com/nats-io/nkeys.py)

## Summary

- ✅ JWT authentication configured with tier-based permissions
- ✅ TLS certificates setup guide provided
- ✅ NATS resolver endpoint created
- ✅ Client connection examples provided
- ✅ Comprehensive test suite added
