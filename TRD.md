# Technical Requirements Document (TRD)

## Project: Tradebase AI Platform Infrastructure
**Version:** 1.0.0  
**Date:** July 2026  
**Status:** Engineering Baseline  

---
## 0: fIRST GET LAST 1 YEAR DATA OF 1m cANDALS Get Kline data of last 3 minute candel  every minute and upsert in timescaledb , data ingession engine  Engine can be configured with yfinance , alpaca , metatraders MT5 . But we will create mvc WITH YFINANCE. 

## 1. System Architecture Overview
The Tradebase infrastructure leverages an event-driven design split into a high-throughput ingestion pipeline, a multi-model machine learning stack, an optimized time-series database layer, and a native NATS authentication core implementing JWT and NKey security parameters for all client levels.

---

## 2. Component Specifications & Technology Stack

### 2.1 Database Layer (TimescaleDB)
*   **Engine:** TimescaleDB.
*   **Hypertables:** 
    *   `market_features`: Stores 1-minute OHLCV, indicators, and time-decayed sentiment strengths. Uses a rolling 1-year data partition window.
    *   `paper_orders` & `trade_log`: Tracks simulated and actual execution fills, entries, exits, slippage, and PnL.
*   **Materialized Aggregates:** Automated continuous aggregates for 1-Hour and 4-Hour timeframe compressions.

### 2.2 Messaging Core & Access Control (NATS Server)
*   **Broker Engine:** Native NATS Server architecture operating as the single-source-of-truth real-time distribution cluster.
*   **Security & Gating Model:** Powered by **NATS Decentralized Security (NKeys & JWT Claims)**. 
    *   Clients use an isolated public/private signature pair (NKey).
    *   The platform Account Server issues signed user JWT tokens containing strict publish/subscribe permissions mapped to their payment status.
*   **Subject Hierarchy Template:**
    `tradebase.<asset_class>.<symbol>.<stream_type>.<interval>`
    *   *Example 1:* `tradebase.forex.eurusd.raw.1m` (Gated for Basic subscribers)
    *   *Example 2:* `tradebase.forex.eurusd.prediction.1m` (Gated for Premium subscribers)

### 2.3 Machine Learning & Analytics Engine
*   **Supervised Models:** Weka-based J48 (C4.5 Decision Tree implementation) and XGBoost classification networks. Running automated rolling walk-forward training validation over the weekend.
*   **Reinforcement Learning Pipeline (Future Integration):** Custom Python environment built via OpenAI/Farama **Gymnasium**. 
    *   *State Space:* 10-dimension array tracking technical features, time-decayed text sentiment vectors, and active position metrics.
    *   *Action Space:* Discrete outputs (`0: Hold/Flat`, `1: Long`, `2: Short`).
    *   *Algorithm:* Proximal Policy Optimization (PPO) via Stable-Baselines3.

---

## 3. Detailed Data Flow & API Specifications

### 3.1 1-Minute Core Event Data Packet
When a 1-minute candle closes, the pipeline generates and publishes the following unified payload structure over NATS subjects:

```json
{
  "timestamp": "2026-07-06T13:30:00Z",
  "symbol": "EURUSD",
  "interval": "1M",
  "open": 1.08210,
  "high": 1.08250,
  "low": 1.08205,
  "close": 1.08240,
  "metrics": {
    "rsi_15m": 58.4,
    "elder_impulse_1m": 1,
    "sentiment_hourly_strength": 0.421,
    "sentiment_weekly_strength": -0.082
  },
  "prediction": {
    "direction": "UP",
    "probability": 0.845
  }
}
## 4  -SOLUTION Should be DOCKER BASE, i will devploy on VPS with Dockployn throgh github.

## 5 NATS JWT Authentication Handshake Flow
Token Provisioning: Upon user subscription activation (FastAPI backend), the platform's system operator signs a user JWT containing permission claims:


JSON
{
  "jti": "jwt_unique_id_5678",
  "iat": 1783342800,
  "exp": 1783346400,
  "nats": {
    "pub": { "deny": [">"] },
    "sub": { "allow": ["tradebase.forex.eurusd.raw.1m"] }
  }
}
Network Boundary Authorization: When the client bot establishes a connection to nats://yourdomain.com:4222, it submits this JWT and signs a challenge using its local private NKey. NATS validates the token natively in the network layer. If a user tries to manually subscribe to tradebase.forex.eurusd.prediction.1m without the correct claim, the NATS server automatically drops the command with zero impact on the Python analytics layer.