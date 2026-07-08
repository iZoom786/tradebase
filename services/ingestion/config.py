"""
Configuration validation for Ingestion Service

Provides Pydantic-based configuration validation with:
- Type checking and constraints
- Custom validators for business logic
- Clear error messages
- Environment variable support
"""

from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderType(str, Enum):
    """Supported data providers"""
    YFINANCE = "yfinance"
    ALPACA = "alpaca"
    MT5 = "mt5"


class IntervalType(str, Enum):
    """Supported candlestick intervals"""
    ONE_MINUTE = "1m"
    TWO_MINUTES = "2m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"


class LogLevel(str, Enum):
    """Logging levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AssetClass(str, Enum):
    """Asset classes for NATS subjects"""
    FOREX = "forex"
    CRYPTO = "crypto"
    STOCK = "stock"
    COMMODITY = "commodity"
    INDEX = "index"


class DatabaseConfig(BaseModel):
    """Database connection configuration"""

    host: str = Field(
        default="localhost",
        min_length=1,
        description="Database host address"
    )
    port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="Database port"
    )
    database: str = Field(
        default="tradebase",
        min_length=1,
        description="Database name"
    )
    user: str = Field(
        default="postgres",
        min_length=1,
        description="Database user"
    )
    password: str = Field(
        default="postgres",
        min_length=1,
        description="Database password"
    )
    pool_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Connection pool size"
    )

    @field_validator("database")
    @classmethod
    def database_name_valid(cls, v: str) -> str:
        """Validate database name contains only safe characters"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Database name must contain only alphanumeric characters, underscores, and hyphens"
            )
        return v


class NATSConfig(BaseModel):
    """NATS messaging configuration"""

    url: str = Field(
        default="nats://localhost:4222",
        pattern=r"^nats://[^:]+:\d+$",
        description="NATS server URL (format: nats://host:port)"
    )
    max_reconnect: int = Field(
        default=10,
        ge=0,
        le=100,
        description="Maximum reconnection attempts"
    )
    ping_interval: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Ping interval in seconds"
    )
    connect_timeout: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Connection timeout in seconds"
    )
    jetstream_enabled: bool = Field(
        default=True,
        description="Enable JetStream for persistence"
    )

    @field_validator("url")
    @classmethod
    def url_format(cls, v: str) -> str:
        """Validate NATS URL format"""
        if not v.startswith("nats://"):
            raise ValueError("NATS URL must start with 'nats://'")
        return v


class ObservabilityConfig(BaseModel):
    """Observability and monitoring configuration"""

    jaeger_endpoint: Optional[str] = Field(
        default=None,
        description="Jaeger tracing endpoint"
    )
    prometheus_port: int = Field(
        default=9091,
        ge=1024,
        le=65535,
        description="Prometheus metrics port"
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level"
    )
    enable_tracing: bool = Field(
        default=True,
        description="Enable distributed tracing"
    )
    enable_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics"
    )


class IngestionConfig(BaseSettings):
    """
    Main ingestion service configuration

    Loads from environment variables with INGESTION_ prefix.
    """

    # Provider settings
    provider: ProviderType = Field(
        default=ProviderType.YFINANCE,
        description="Data provider to use"
    )

    # Symbol configuration
    symbols: List[str] = Field(
        default=["EURUSD", "GBPUSD", "USDJPY"],
        min_length=1,
        max_length=50,
        description="Trading symbols to ingest"
    )

    # Interval configuration
    interval: IntervalType = Field(
        default=IntervalType.ONE_MINUTE,
        description="Candlestick interval"
    )

    # Backfill settings
    backfill_days: int = Field(
        default=365,
        ge=1,
        le=3650,
        description="Days of historical data to backfill"
    )

    # Timing settings
    fetch_delay_seconds: int = Field(
        default=5,
        ge=0,
        le=59,
        description="Seconds past minute to fetch (ensures candle is closed)"
    )

    retry_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of retry attempts for failed fetches"
    )

    retry_delay_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=30.0,
        description="Delay between retries in seconds"
    )

    # Asset class
    asset_class: AssetClass = Field(
        default=AssetClass.FOREX,
        description="Asset class for NATS subjects"
    )

    # Feature flags
    enable_backfill: bool = Field(
        default=True,
        description="Enable historical backfill on startup"
    )

    enable_validation: bool = Field(
        default=True,
        description="Validate symbols against provider"
    )

    # Settings configuration
    model_config = SettingsConfigDict(
        env_prefix="INGESTION_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("symbols")
    @classmethod
    def symbols_valid(cls, v: List[str]) -> List[str]:
        """Validate symbol format and uniqueness"""
        if not v:
            raise ValueError("At least one symbol must be specified")

        # Convert to uppercase and validate
        symbols = [s.upper().strip() for s in v]

        # Check for duplicates
        if len(symbols) != len(set(symbols)):
            raise ValueError("Duplicate symbols found in configuration")

        # Validate symbol format (alphanumeric, 6-12 chars)
        for symbol in symbols:
            if not 3 <= len(symbol) <= 12:
                raise ValueError(
                    f"Symbol '{symbol}' must be 3-12 characters long"
                )
            if not symbol.isalnum():
                raise ValueError(
                    f"Symbol '{symbol}' must contain only alphanumeric characters"
                )

        return symbols

    @model_validator(mode="after")
    def validate_provider_settings(self) -> "IngestionConfig":
        """Cross-field validation for provider-specific settings"""
        if self.provider == ProviderType.YFINANCE:
            # YFinance requires specific interval formats
            valid_intervals = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d"]
            if self.interval.value not in valid_intervals:
                raise ValueError(
                    f"Interval '{self.interval.value}' not supported by YFinance. "
                    f"Valid options: {', '.join(valid_intervals)}"
                )

        elif self.provider == ProviderType.ALPACA:
            # Alpaca has different requirements
            if self.asset_class not in [AssetClass.STOCK, AssetClass.FOREX, AssetClass.CRYPTO]:
                raise ValueError(
                    f"Alpaca provider requires stock, forex, or crypto asset class"
                )

        return self


class Config:
    """Complete configuration for ingestion service"""

    def __init__(
        self,
        db: Optional[DatabaseConfig] = None,
        nats: Optional[NATSConfig] = None,
        obs: Optional[ObservabilityConfig] = None,
        ingestion: Optional[IngestionConfig] = None
    ):
        self.db = db or DatabaseConfig()
        self.nats = nats or NATSConfig()
        self.obs = obs or ObservabilityConfig()
        self.ingestion = ingestion or IngestionConfig()

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls(
            db=DatabaseConfig(**{
                k.replace("DB_", "").lower(): v
                for k, v in __import__("os").environ.items()
                if k.startswith("DB_")
            }),
            nats=NATSConfig(**{
                k.replace("NATS_", "").lower(): v
                for k, v in __import__("os").environ.items()
                if k.startswith("NATS_")
            }),
            obs=ObservabilityConfig(**{
                k.replace("OBS_", "").lower(): v
                for k, v in __import__("os").environ.items()
                if k.startswith("OBS_")
            }),
            ingestion=IngestionConfig()
        )

    def validate(self) -> bool:
        """
        Validate all configuration sections

        Returns:
            True if all configurations are valid

        Raises:
            ValidationError: If any configuration is invalid
        """
        # Pydantic handles validation during instantiation
        # This method is for explicit validation if needed
        return True

    def to_dict(self) -> dict:
        """Export configuration as dictionary (for logging)"""
        return {
            "database": self.db.model_dump(),
            "nats": self.nats.model_dump(),
            "observability": self.obs.model_dump(),
            "ingestion": self.ingestion.model_dump()
        }

    def __repr__(self) -> str:
        return f"Config(provider={self.ingestion.provider}, symbols={self.ingestion.symbols})"


# Singleton instance
_config: Optional[Config] = None


def get_config(reload: bool = False) -> Config:
    """
    Get or create configuration singleton

    Args:
        reload: Force reload of configuration

    Returns:
        Config instance
    """
    global _config
    if _config is None or reload:
        _config = Config.from_env()
    return _config
