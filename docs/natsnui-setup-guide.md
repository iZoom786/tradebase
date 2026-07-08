# NATS Web UI Setup Guide - natsnui.app

## Overview

[natsnui.app](https://natsnui.app/) is a web-based UI for managing and monitoring NATS servers. It connects directly to your running NATS server's monitoring endpoint.

---

## Using natsnui.app with Tradebase

### Step 1: Ensure NATS is Running

```bash
# Check NATS status
docker-compose ps nats

# If not running, start it
docker-compose up -d nats
```

### Step 2: Access natsnui.app

1. Open your browser and go to: https://natsnui.app/

### Step 3: Connect to Your NATS Server

On the natsnui.app connection screen, enter the following:

| Field | Value |
|-------|-------|
| **Server URL** | `ws://localhost:4222` (for local development) |
| **or Monitor URL** | `http://localhost:8222` (for monitoring only) |
| **Username** | `system_internal` (default) |
| **Password** | `system_internal_password` (default) |

> **Note:** If you're accessing from a different machine, replace `localhost` with your server's IP address.

### Step 4: Explore the UI

Once connected, you can:
- **View Connections:** See active client connections
- **Monitor JetStream:** View streams, consumers, and messages
- **Inspect Messages:** Browse messages in streams
- **Manage Subscriptions:** View active subscriptions
- **Server Metrics:** Monitor server health and performance

---

## Alternative: Self-Hosted NATS UI Options

If you prefer a self-hosted solution embedded in Docker:

### Option 1: Enable NATS Built-in Monitoring (Already Enabled)

Your NATS server already has monitoring enabled on port 8222:

```bash
# Access monitoring endpoint
curl http://localhost:8222/varz
```

### Option 2: Use NATS Top Tool

The `nats-top` tool provides a terminal-based UI:

```bash
# Install NATS CLI
go install github.com/nats-io/natscli/nats@latest

# Run nats-top
nats top -s localhost:4222
```

### Option 3: Custom Grafana Dashboard

Since you already have Grafana running, you can add NATS metrics:

1. Prometheus is already configured to scrape NATS metrics
2. Import a NATS dashboard in Grafana:
   - Go to http://localhost:3001
   - Click "+" → "Import"
   - Search for "NATS" dashboards on Grafana.com

---

## Current NATS Configuration

| Setting | Value |
|---------|-------|
| Client Port | `4222` |
| Monitor Port | `8222` |
| WebSocket Port | `8080` |
| Username | `system_internal` (configurable via `NATS_SYSTEM_USER`) |
| Password | `system_internal_password` (configurable via `NATS_SYSTEM_PASSWORD`) |
| JetStream | Enabled |

---

## Connection Examples

### From Local Machine

```
ws://localhost:4222
```

### From Remote Machine

```
ws://YOUR_SERVER_IP:4222
```

### Using Basic Auth

```
ws://system_internal:system_internal_password@localhost:4222
```

---

## Troubleshooting

### Connection Refused

```bash
# Check if NATS is running
docker-compose ps nats

# Check NATS logs
docker-compose logs nats
```

### Authentication Failed

Verify your credentials match the environment variables in `docker-compose.yml`:

```yaml
- NATS_SYSTEM_USER=${NATS_SYSTEM_USER:-system_internal}
- NATS_SYSTEM_PASSWORD=${NATS_SYSTEM_PASSWORD:-system_internal_password}
```

### WebSocket Connection Issues

If WebSocket fails, try using the monitor URL instead:

```
http://localhost:8222
```

---

## Security Notes

⚠️ **For Development Only:** The current setup uses basic authentication over unencrypted connections.

For production:
1. Enable TLS (see [JWT Auth & TLS Guide](jwt-auth-tls-guide.md))
2. Use strong passwords via environment variables
3. Restrict monitor port access behind a firewall
4. Use JWT-based authentication for applications

---

## Quick Reference

| Task | Command/URL |
|------|-------------|
| Start NATS | `docker-compose up -d nats` |
| Check NATS Status | `docker-compose ps nats` |
| View NATS Logs | `docker-compose logs -f nats` |
| natsnui.app | https://natsnui.app/ |
| NATS Monitoring | http://localhost:8222/varz |
| Grafana | http://localhost:3001 |

---

**Last Updated:** 2026-07-07
