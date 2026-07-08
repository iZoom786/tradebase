"""
Configuration management using Pydantic Settings
"""

from typing import Optional
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    """TimescaleDB configuration"""

    host: str = "localhost"
    port: int = 5432
    database: str = "tradebase"
    user: str = "postgres"
    password: str = "postgres"
    pool_size: int = 20

    class Config:
        env_prefix = "DB_"


class NATSConfig(BaseSettings):
    """NATS configuration"""

    url: str = "nats://localhost:4222"
    url_tls: Optional[str] = "tls://localhost:4222"  # TLS connection URL
    max_reconnect: int = 10
    ping_interval: int = 60
    connect_timeout: int = 5

    # JWT/NKey Authentication
    user_jwt: Optional[str] = None  # User JWT token (for external clients)
    user_seed: Optional[str] = None  # User NKey seed (for signing challenges)

    # TLS Configuration
    tls_enabled: bool = False  # Enable TLS
    ca_cert: Optional[str] = None  # Path to CA certificate
    client_cert: Optional[str] = None  # Path to client certificate (for mTLS)
    client_key: Optional[str] = None  # Path to client private key (for mTLS)
    verify_cert: bool = True  # Verify server certificate

    class Config:
        env_prefix = "NATS_"


class JWTConfig(BaseSettings):
    """JWT/NKey authentication configuration"""

    issuer_seed: Optional[str] = None  # Account NKey seed for signing JWTs
    default_expiry_hours: int = 720  # 30 days
    enable_resolver: bool = True  # Enable JWT resolver endpoint

    class Config:
        env_prefix = "JWT_"


class SubscriptionConfig(BaseSettings):
    """Subscription service configuration"""

    api_port: int = 8002
    default_trial_days: int = 30
    max_subscription_days: int = 365
    min_subscription_days: int = 1

    class Config:
        env_prefix = "SUBSCRIPTION_"


class FeatureConfig(BaseSettings):
    """Feature calculation configuration"""

    enabled_indicators: list[str] = [
        "rsi",
        "elder",
        "bollinger",
        "atr"
    ]
    cache_ttl_seconds: int = 300
    lookback_bars: int = 100

    class Config:
        env_prefix = "FEATURE_"


class MLConfig(BaseSettings):
    """Machine learning configuration"""

    model_path: str = "models/"
    retrain_interval_hours: int = 168  # Weekly
    validation_split: float = 0.2
    early_stopping_rounds: int = 50

    class Config:
        env_prefix = "ML_"


class IngestionConfig(BaseSettings):
    """Ingestion service configuration"""

    provider: str = "yfinance"
    symbols: list[str] = ["EURUSD", "GBPUSD", "USDJPY"]
    interval: str = "1m"
    backfill_days: int = 365

    class Config:
        env_prefix = "INGESTION_"


class ObservabilityConfig(BaseSettings):
    """Observability configuration"""

    jaeger_endpoint: Optional[str] = "http://localhost:16686"
    prometheus_port: int = 9090
    log_level: str = "INFO"

    class Config:
        env_prefix = "OBS_"
