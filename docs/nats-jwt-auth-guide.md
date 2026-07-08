# NATS JWT/NKey Authentication Guide

**Phase 4 Implementation** | Version 1.0.0 | July 2026

---

## Overview

The Tradebase platform implements NATS JWT/NKey authentication to provide tiered access control for real-time market data and predictions. This system ensures:

- **Secure Access:** Only authorized users can connect to NATS
- **Tier Permissions:** Subscription levels control data access
- **Cryptographic Security:** Ed25519 NKeys for signing
- **Scalability:** Authentication handled at the broker boundary

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Authentication Flow                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. User requests subscription                                    │
│     └─ POST /auth/subscribe                                        │
│                                                                     │
│  2. Subscription Service generates credentials                     │
│     ├─ User NKey pair (seed + public_key)                         │
│     └─ JWT signed with Account NKey                                │
│                                                                     │
│  3. Client connects to NATS                                        │
│     ├─ Presents JWT                                                │
│     ├─ Signs server challenge with NKey                            │
│     └─ Connection granted if JWT valid                             │
│                                                                     │
│  4. Client subscribes to subjects                                 │
│     ├─ NATS checks JWT permissions                                 │
│     └─ Allow/deny based on tier                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tier Permissions

### Trial Tier (Free)

**Access:** Public paper trading feed only

| Subject Pattern | Allow | Deny |
|----------------|-------|------|
| `tradebase.public.papertrading.>` | ✅ | |
| `>` | | ❌ |

**Use Case:** Web visitors tracking platform performance

### Basic Tier ($X/month)

**Access:** Raw OHLCV data + Technical indicators

| Subject Pattern | Allow | Deny |
|----------------|-------|------|
| `tradebase.forex.*.raw.>` | ✅ | |
| `tradebase.forex.*.features.>` | ✅ | |
| `tradebase.forex.*.prediction.>` | | ❌ |
| `>` (publish) | | ❌ |

**Use Case:** Algorithmic traders building their own models

### Premium Tier ($Y/month)

**Access:** All data including ML predictions

| Subject Pattern | Allow | Deny |
|----------------|-------|------|
| `tradebase.>` | ✅ | |
| `>` (publish) | | ❌ |

**Use Case:** Traders wanting turnkey signals

---

## Client Connection Examples

### Python Client

```python
import asyncio
import nats
from libs.nats_client.client import NATSClient
from libs.common.config import NATSConfig

async def connect_with_jwt():
    # Configuration
    config = NATSConfig(
        url="nats://tradebase.com:4222"
    )

    # Your credentials (from subscription service)
    user_jwt = "eyJ0eXAiOiJKV1QiLCJhbGc..."
    user_seed = "USER_SEED_HERE"

    # Create client with JWT
    client = NATSClient(
        config,
        user_jwt=user_jwt,
        user_seed=user_seed
    )

    # Connect
    await client.connect()

    # Subscribe to allowed subjects
    async def on_message(msg):
        print(f"Received: {msg.data.decode()}")

    await client.subscribe(
        "tradebase.forex.eurusd.raw.1m",
        on_message
    )

    # Keep connection alive
    await asyncio.sleep(60)

asyncio.run(connect_with_jwt())
```

### JavaScript/TypeScript Client

```typescript
import { connect, NatsConnection } from 'nats.ws';

async function connectWithJWT() {
    // Your credentials
    const userJWT = "eyJ0eXAiOiJKV1QiLCJhbGc...";
    const userSeed = "USER_SEED_HERE";

    // Connect
    const nc = await connect({
        servers: "wss://tradebase.com",
        userJWT: userJWT,
        nkeySeed: userSeed,
    });

    // Subscribe
    const sub = nc.subscribe("tradebase.forex.eurusd.raw.1m");

    (async () => {
        for await (const msg of sub) {
            console.log(`Received: ${new TextDecoder().decode(msg.data)}`);
        }
    })();
}
```

### Go Client

```go
package main

import (
    "fmt"
    "github.com/nats-io/nats.go"
)

func main() {
    // Your credentials
    userJWT := "eyJ0eXAiOiJKV1QiLCJhbGc..."
    userSeed := []byte("USER_SEED_HERE")

    // Connect
    nc, err := nats.Connect(
        "nats://tradebase.com:4222",
        nats.UserJWT(userJWT),
        nats.UserSeed(userSeed),
    )
    if err != nil {
        panic(err)
    }
    defer nc.Close()

    // Subscribe
    sub, err := nc.Subscribe("tradebase.forex.eurusd.raw.1m", func(msg *nats.Msg) {
        fmt.Printf("Received: %s\n", msg.Data)
    })
    if err != nil {
        panic(err)
    }

    // Keep connection alive
    select {}
}
```

---

## API Endpoints

### Start Trial

```bash
POST /auth/trial
Content-Type: application/json

{
    "email": "user@example.com"
}

# Response (201 Created)
{
    "user_id": "uuid-here",
    "tier": "trial",
    "jwt": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "websocket_url": "wss://tradebase.com/trial",
    "expires_at": "2026-08-06T00:00:00Z"
}
```

### Create Subscription

```bash
POST /auth/subscribe
Content-Type: application/json

{
    "user_id": "user_123",
    "tier": "basic",
    "duration_days": 30
}

# Response (201 Created)
{
    "user_id": "user_123",
    "tier": "basic",
    "jwt": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "nkey_seed": "USER_BASE64_SEED...",
    "nkey_public": "PUBLIC_KEY...",
    "expires_at": "2026-08-06T00:00:00Z",
    "nats_url": "nats://tradebase.com:4222"
}
```

### Upgrade Subscription

```bash
PUT /auth/upgrade/{user_id}
Content-Type: application/json

{
    "new_tier": "premium"
}

# Response (200 OK)
{
    "user_id": "user_123",
    "tier": "premium",
    "jwt": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "nkey_seed": "USER_BASE64_SEED...",
    "nkey_public": "PUBLIC_KEY...",
    "expires_at": "2026-09-05T00:00:00Z",
    "nats_url": "nats://tradebase.com:4222"
}
```

### Validate JWT

```bash
POST /auth/validate
Content-Type: application/json

{
    "token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}

# Response (200 OK)
{
    "valid": true,
    "tier": "basic",
    "user_id": "user_123",
    "expires_at": "2026-08-06T00:00:00Z"
}
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_ISSUER_SEED` | Account NKey seed for signing JWTs | Auto-generated |
| `JWT_DEFAULT_EXPIRY_HOURS` | JWT validity period | 720 (30 days) |
| `JWT_ENABLE_RESOLVER` | Enable JWT resolver endpoint | true |
| `SUBSCRIPTION_API_PORT` | Subscription service port | 8002 |

### NATS Server Configuration

Located at `infrastructure/nats/nats_jwt.conf`:

```nginx
# JWT/NKey authentication enabled
authorization {
    timeout: 2s
    default_permissions = {
        publish: "deny"
        subscribe: "deny"
    }
    system_account = "SYSTEM"
}

# Tier-based accounts
operator {
    accounts = {
        TRIAL: { ... }    # Paper trading only
        BASIC: { ... }   # Raw data + features
        PREMIUM: { ... } # All data
    }
}
```

---

## Security Best Practices

### 1. Seed Storage

**Never commit NKey seeds to git!**

```bash
# .env file (git-ignored)
JWT_ISSUER_SEED=ACCOUNT_BASE64_SEED_HERE
```

### 2. JWT Expiration

- **Trial:** 30 days
- **Paid:** 30-90 days (configurable)
- Auto-renewal via API

### 3. TLS in Production

Enable TLS for all NATS connections in production:

```nginx
tls {
    cert_file: /etc/nats/certs/server.crt
    key_file: /etc/nats/certs/server.key
    ca_file: /etc/nats/certs/ca.crt
    verify: true
}
```

### 4. Rate Limiting

Implement API rate limiting:

- Trial: 100 requests/hour
- Basic: 1000 requests/hour
- Premium: Unlimited

---

## Troubleshooting

### Connection Refused

```
NATSConnectionError: Failed to connect to NATS: Connection refused
```

**Solutions:**
1. Check NATS server is running: `docker-compose ps nats`
2. Verify URL: `nats://localhost:4222`
3. Check firewall rules

### Authentication Failed

```
Authentication failed: Invalid JWT
```

**Solutions:**
1. Verify JWT hasn't expired
2. Check JWT signature with validation endpoint
3. Ensure user is active: `GET /users/{user_id}`

### Permission Denied

```
Permissions violation: publish denied
```

**Solutions:**
1. Check tier permissions
2. Verify subject pattern matches allowed list
3. Ensure action (pub/sub) is correct

### Expired JWT

```bash
# Refresh JWT via API
curl -X POST http://localhost:8002/auth/subscribe \
    -H "Content-Type: application/json" \
    -d '{"user_id": "user_123", "tier": "basic", "duration_days": 30}'
```

---

## Testing

### Test JWT Generation

```python
from libs.nats_client.auth import NATSAuthClient

# Create auth client
auth = NATSAuthClient()

# Generate user credentials
jwt, seed, public_key = auth.create_user(
    user_id="test_user",
    tier="premium"
)

print(f"JWT: {jwt[:50]}...")
print(f"Seed: {seed[:50]}...")
print(f"Public Key: {public_key}")
```

### Test Permission Check

```python
from libs.nats_client.auth import NATSAuthClient

auth = NATSAuthClient()
jwt, _, _ = auth.create_user("test_user", "basic")

# Check permissions
allowed = auth.check_permission(
    jwt,
    "tradebase.forex.eurusd.raw.1m",
    "sub"
)

print(f"Allowed: {allowed}")  # True for basic
```

### Run Full Test Suite

```bash
# Run all authentication tests
pytest tests/test_subscription/test_auth.py -v

# Run NATS client tests
pytest tests/test_nats_client/test_client_auth.py -v
```

---

## Migration from Simple Auth

### Before (No Auth)

```python
client = NATSClient(config)
await client.connect()
```

### After (JWT Auth)

```python
# Get credentials from subscription service
jwt, seed, _ = auth_client.create_user(user_id, tier)

# Connect with JWT
client = NATSClient(config, user_jwt=jwt, user_seed=seed)
await client.connect()
```

---

## References

- [NATS JWT Authentication](https://docs.nats.io/nats-concepts/jwt)
- [NKeys Documentation](https://docs.nats.io/nats-concepts/nkey)
- [Subject Pattern Matching](https://docs.nats.io/nats-concepts/subjects)
- [Python NATS Client](https://github.com/nats-io/nats.py)

---

**Phase 4 Status:** ✅ Complete

**Next Phase:** Phase 5 - Feature Calculation Pipeline
