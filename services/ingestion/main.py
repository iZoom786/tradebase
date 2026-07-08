"""
Main entry point for ingestion service

Validates configuration on startup and provides clear error messages
for invalid configuration.

Supports two modes:
1. One-time ingestion: Run once and exit
2. Scheduled ingestion: Run continuously with scheduler
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pydantic import ValidationError

from services.ingestion.controllers import IngestionControllerV2
from services.ingestion.controllers.scheduler import (
    IngestionScheduler,
    PresetSchedulers,
    create_default_scheduler
)
from services.ingestion.config import Config, get_config
from services.ingestion.providers import YFinanceProviderV2
from services.ingestion.views import DataPublisher
from libs.common.observability import setup_logging, setup_tracing
from libs.nats_client import NATSClient, NATSConnectionError
from libs.db_repo.timescaledb_v2 import TimescaleDBRepository

logger = logging.getLogger(__name__)


def validate_config() -> Config:
    """
    Validate and load configuration

    Returns:
        Validated configuration

    Exits:
        If configuration is invalid
    """
    try:
        config = get_config()
        config.validate()

        logger.info(
            "config_loaded",
            provider=config.ingestion.provider.value,
            symbols=config.ingestion.symbols,
            interval=config.ingestion.interval.value
        )

        return config

    except ValidationError as e:
        logger.error("config_validation_failed")

        print("\n" + "=" * 60)
        print("CONFIGURATION VALIDATION FAILED")
        print("=" * 60)

        for error in e.errors():
            loc = " -> ".join(str(x) for x in error['loc'])
            print(f"\n✗ {loc}")
            print(f"  {error['msg']}")
            if 'input' in error:
                print(f"  Received: {error['input']}")

        print("\n" + "=" * 60)
        print("\nPlease fix the configuration errors above.")
        print("Check your environment variables or .env file.")
        sys.exit(1)

    except Exception as e:
        logger.error("config_load_error", error=str(e))
        print(f"\n✗ Failed to load configuration: {e}")
        sys.exit(1)


async def main():
    """Main entry point with configuration validation"""
    # Step 1: Validate configuration
    config = validate_config()

    # Step 2: Setup observability
    setup_logging()
    setup_tracing(
        service_name="ingestion",
        jaeger_endpoint=config.obs.jaeger_endpoint
    )

    # Check if running in scheduler mode
    scheduler_enabled = os.getenv("INGESTION_SCHEDULER_ENABLED", "false").lower() == "true"
    run_once = os.getenv("INGESTION_RUN_ONCE", "false").lower() == "true"

    logger.info(
        "ingestion_starting",
        config=config.to_dict(),
        scheduler_enabled=scheduler_enabled,
        run_once=run_once
    )

    # Step 3: Initialize components
    try:
        # Initialize data provider (v2 with 3-row fetching)
        provider = YFinanceProviderV2(symbols=config.ingestion.symbols, default_rows=3)
        logger.info("provider_initialized", provider=provider.provider_name)

        # Initialize NATS client
        nats_client = NATSClient(config.nats)
        await nats_client.connect()
        logger.info("nats_connected")

        # Initialize database repository (v2 with timekey support)
        repository = TimescaleDBRepository(config.db)
        await repository.connect()
        logger.info("database_connected")

        # Initialize publisher
        publisher = DataPublisher(nats_client)
        logger.info("publisher_initialized")

        # Initialize controller (v2 with resume capability)
        controller = IngestionControllerV2(
            provider=provider,
            repository=repository,
            publisher=publisher,
            rows_per_minute=3
        )
        logger.info("controller_initialized_v2")

    except NATSConnectionError as e:
        logger.error("nats_connection_failed", error=str(e))
        print(f"\n✗ Failed to connect to NATS: {e}")
        print(f"  Ensure NATS is running at {config.nats.url}")
        sys.exit(1)

    except Exception as e:
        logger.error("initialization_failed", error=str(e))
        print(f"\n✗ Failed to initialize service: {e}")
        sys.exit(1)

    # Step 4: Initialize scheduler if enabled
    scheduler = None
    if scheduler_enabled:
        scheduler = create_default_scheduler(controller)
        logger.info("scheduler_initialized")

    # Step 5: Setup signal handling
    def signal_handler():
        logger.info("shutdown_signal_received")
        controller.stop()
        if scheduler:
            scheduler.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda s, f: signal_handler())

    # Step 6: Run ingestion
    try:
        if run_once:
            # Run once and exit
            logger.info("ingestion_run_once", symbols=config.ingestion.symbols)
            for symbol in config.ingestion.symbols:
                await controller.ingest_latest(symbol)
            logger.info("ingestion_complete")

        elif scheduler_enabled and scheduler:
            # Start scheduler and run continuously
            logger.info(
                "ingestion_scheduler_mode",
                symbols=config.ingestion.symbols
            )
            scheduler.start()

            # Keep running until shutdown signal
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("ingestion_cancelled")

        else:
            # Legacy continuous mode (run in loop)
            logger.info(
                "ingestion_running",
                symbols=config.ingestion.symbols,
                interval=config.ingestion.interval.value
            )
            await controller.run(symbols=config.ingestion.symbols)

    except Exception as e:
        logger.error("ingestion_fatal_error", error=str(e))
        raise

    finally:
        logger.info("ingestion_shutting_down")
        if scheduler and scheduler.is_running():
            scheduler.stop()
        await nats_client.close()
        await repository.close()
        logger.info("ingestion_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ingestion_interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error("ingestion_crashed", error=str(e))
        sys.exit(1)
