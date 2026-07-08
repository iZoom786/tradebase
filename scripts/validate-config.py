#!/usr/bin/env python3
"""
Configuration validation CLI tool

Validates ingestion service configuration and provides helpful error messages.

Usage:
    python scripts/validate-config.py
    INGESTION_SYMBOLS=EURUSD,GBPUSD python scripts/validate-config.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import ValidationError


def print_section(title: str) -> None:
    """Print section header"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def print_success(msg: str) -> None:
    """Print success message"""
    print(f"✓ {msg}")


def print_error(msg: str) -> None:
    """Print error message"""
    print(f"✗ {msg}")


def print_warning(msg: str) -> None:
    """Print warning message"""
    print(f"⚠ {msg}")


def validate_configuration() -> int:
    """
    Validate all configuration sections

    Returns:
        Exit code (0 = success, 1 = error)
    """
    exit_code = 0

    try:
        from services.ingestion.config import (
            Config,
            DatabaseConfig,
            NATSConfig,
            ObservabilityConfig,
            IngestionConfig
        )

        print_section("TRADEBASE INGESTION SERVICE - CONFIGURATION VALIDATION")

        # Validate Database Configuration
        print("\n[1/4] Database Configuration")
        try:
            db_config = DatabaseConfig()
            print_success(f"Host: {db_config.host}:{db_config.port}")
            print_success(f"Database: {db_config.database}")
            print_success(f"User: {db_config.user}")
            print_success(f"Pool Size: {db_config.pool_size}")
        except ValidationError as e:
            exit_code = 1
            for error in e.errors():
                print_error(f"{error['loc'][0]}: {error['msg']}")

        # Validate NATS Configuration
        print("\n[2/4] NATS Configuration")
        try:
            nats_config = NATSConfig()
            print_success(f"URL: {nats_config.url}")
            print_success(f"Max Reconnect: {nats_config.max_reconnect}")
            print_success(f"JetStream: {nats_config.jetstream_enabled}")
        except ValidationError as e:
            exit_code = 1
            for error in e.errors():
                print_error(f"{error['loc'][0]}: {error['msg']}")

        # Validate Observability Configuration
        print("\n[3/4] Observability Configuration")
        try:
            obs_config = ObservabilityConfig()
            print_success(f"Log Level: {obs_config.log_level.value}")
            print_success(f"Prometheus Port: {obs_config.prometheus_port}")
            print_success(f"Tracing: {obs_config.enable_tracing}")
            print_success(f"Metrics: {obs_config.enable_metrics}")
        except ValidationError as e:
            exit_code = 1
            for error in e.errors():
                print_error(f"{error['loc'][0]}: {error['msg']}")

        # Validate Ingestion Configuration
        print("\n[4/4] Ingestion Configuration")
        try:
            ingestion_config = IngestionConfig()
            print_success(f"Provider: {ingestion_config.provider.value}")
            print_success(f"Symbols: {', '.join(ingestion_config.symbols)}")
            print_success(f"Interval: {ingestion_config.interval.value}")
            print_success(f"Backfill Days: {ingestion_config.backfill_days}")
            print_success(f"Asset Class: {ingestion_config.asset_class.value}")
        except ValidationError as e:
            exit_code = 1
            for error in e.errors():
                print_error(f"{error['loc'][0]}: {error['msg']}")

        # Full configuration validation
        print("\n" + "-" * 60)
        try:
            config = Config.from_env()
            print_success("All configuration sections validated successfully")
        except ValidationError as e:
            exit_code = 1
            print_error("Full configuration validation failed:")
            for error in e.errors():
                loc = " -> ".join(str(x) for x in error['loc'])
                print_error(f"  {loc}: {error['msg']}")

        # Summary
        print_section("SUMMARY")
        if exit_code == 0:
            print_success("Configuration is valid!")
            print("\nEnvironment variables loaded:")
            env_vars = {k: v for k, v in os.environ.items()
                       if k.startswith(("DB_", "NATS_", "OBS_", "INGESTION_"))}
            if env_vars:
                for k, v in sorted(env_vars.items()):
                    # Mask sensitive values
                    if "PASSWORD" in k or "SECRET" in k:
                        v = "***"
                    print(f"  {k}={v}")
            else:
                print_warning("No environment variables set - using defaults")
        else:
            print_error("Configuration validation failed!")
            print("\nPlease check the errors above and update your environment.")
            print("\nExample configuration:")
            print("  DB_HOST=localhost")
            print("  NATS_URL=nats://localhost:4222")
            print("  INGESTION_SYMBOLS=EURUSD,GBPUSD,USDJPY")

        print_section("")
        return exit_code

    except ImportError as e:
        print_error(f"Failed to import configuration module: {e}")
        return 1
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1


def main():
    """Entry point"""
    sys.exit(validate_configuration())


if __name__ == "__main__":
    main()
