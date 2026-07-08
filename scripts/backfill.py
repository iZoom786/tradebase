#!/usr/bin/env python3
"""
Historical Data Backfill CLI

Backfill historical market data from YFinance for specified symbols and date ranges.

Usage:
    # Backfill EURUSD for last 30 days
    python scripts/backfill.py --symbols EURUSD --days 30

    # Backfill multiple symbols for specific date range
    python scripts/backfill.py --symbols EURUSD,GBPUSD,USDJPY --start 2024-01-01 --end 2024-06-30

    # Backfill with 1-minute interval
    python scripts/backfill.py --symbols EURUSD --days 365 --interval 1m

    # Backfill with progress bar
    python scripts/backfill.py --symbols EURUSD --days 30 --progress
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ingestion.providers.yfinance import YFinanceProvider
from services.ingestion.controllers.ingestion_controller import IngestionController
from services.ingestion.views.data_publisher import DataPublisher
from libs.nats_client import NATSClient
from libs.db_repo import TimescaleDBRepository
from libs.common.config import IngestionConfig, NATSConfig, DatabaseConfig
from libs.common.observability import setup_logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Default symbols for backfill
DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose):
    """Historical data backfill CLI"""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.option('--symbols', '-s', default=','.join(DEFAULT_SYMBOLS),
              help=f'Comma-separated list of symbols (default: {",".join(DEFAULT_SYMBOLS)})')
@click.option('--days', '-d', type=int, default=30,
              help='Number of days to backfill (default: 30)')
@click.option('--interval', '-i', default='1d',
              type=click.Choice(['1m', '5m', '15m', '30m', '1h', '1d', '1w']),
              help='Data interval (default: 1d for backfill)')
@click.option('--start', type=click.DateTime(['%Y-%m-%d']),
              help='Start date (YYYY-MM-DD), overrides --days')
@click.option('--end', type=click.DateTime(['%Y-%m-%d']),
              help='End date (YYYY-MM-DD), default: today')
@click.option('--progress', '-p', is_flag=True, help='Show progress bar')
@click.option('--dry-run', is_flag=True, help='Fetch but don\'t store data')
@click.option('--skip-errors', is_flag=True, help='Continue on errors instead of stopping')
def backfill(symbols, days, interval, start, end, progress, dry_run, skip_errors):
    """
    Backfill historical market data

    Examples:
        # Backfill last 30 days for EURUSD
        python scripts/backfill.py backfill --symbols EURUSD --days 30

        # Backfill with custom date range
        python scripts/backfill.py backfill --symbols EURUSD,GBPUSD --start 2024-01-01 --end 2024-06-30

        # Backfill with progress bar
        python scripts/backfill.py backfill --symbols EURUSD --days 365 --progress
    """
    setup_logging()

    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(',')]

    # Calculate date range
    if start:
        start_date = start
    else:
        start_date = datetime.now() - timedelta(days=days)

    if end:
        end_date = end
    else:
        end_date = datetime.now()

    logger.info(
        "backfill_start",
        symbols=symbol_list,
        start=start_date.strftime('%Y-%m-%d'),
        end=end_date.strftime('%Y-%m-%d'),
        interval=interval
    )

    # Run async backfill
    asyncio.run(run_backfill(
        symbols=symbol_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        show_progress=progress,
        dry_run=dry_run,
        skip_errors=skip_errors
    ))


@cli.command()
@click.option('--symbols', '-s', default=','.join(DEFAULT_SYMBOLS),
              help='Comma-separated list of symbols')
@click.option('--days', '-d', type=int, default=7,
              help='Number of days to verify (default: 7)')
def verify(symbols, days):
    """
    Verify backfilled data exists in database

    Check if data exists for the specified date range.
    """
    setup_logging()

    symbol_list = [s.strip().upper() for s in symbols.split(',')]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    asyncio.run(run_verification(
        symbols=symbol_list,
        start_date=start_date,
        end_date=end_date
    ))


@cli.command()
@click.option('--symbol', '-s', required=True, help='Symbol to check')
@click.option('--interval', '-i', default='1d',
              type=click.Choice(['1m', '5m', '15m', '30m', '1h', '1d']),
              help='Data interval')
def gap(symbol, interval):
    """
    Find gaps in historical data

    Identify missing dates in the data.
    """
    setup_logging()

    asyncio.run(run_gap_analysis(
        symbol=symbol.upper(),
        interval=interval
    ))


async def run_backfill(
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    interval: str,
    show_progress: bool = False,
    dry_run: bool = False,
    skip_errors: bool = False
):
    """
    Run the backfill process

    Args:
        symbols: List of symbols to backfill
        start_date: Start date for backfill
        end_date: End date for backfill
        interval: Data interval
        show_progress: Show progress bar
        dry_run: Fetch but don't store
        skip_errors: Continue on errors
    """
    # Initialize components
    try:
        # Data provider
        provider = YFinanceProvider(symbols=symbols)
        logger.info("provider_initialized", provider=provider.provider_name)

        if not dry_run:
            # Database repository
            db_config = DatabaseConfig()
            repository = TimescaleDBRepository(db_config)
            await repository.connect()
            logger.info("database_connected")

            # NATS client (optional - we can skip publishing for backfill)
            # For now, we'll skip NATS for backfill to avoid publishing old data
            nats_client = None
        else:
            repository = None
            nats_client = None

        # Create controller
        controller = IngestionController(
            provider=provider,
            repository=repository,
            publisher=None  # Skip publisher for backfill
        )

    except Exception as e:
        logger.error("initialization_failed", error=str(e))
        click.echo(f"✗ Failed to initialize: {e}", err=True)
        return

    # Track statistics
    stats = {
        "total_symbols": len(symbols),
        "completed_symbols": 0,
        "failed_symbols": 0,
        "total_candles": 0,
        "start_time": datetime.now()
    }

    try:
        # Process each symbol
        for symbol in symbols:
            try:
                click.echo(f"\n{'='*60}")
                click.echo(f"Backfilling {symbol} from {start_date.date()} to {end_date.date()}")
                click.echo(f"{'='*60}")

                # Fetch historical data
                candles = await provider.fetch_historical(
                    symbol=symbol,
                    start=start_date,
                    end=end_date
                )

                if not candles:
                    click.echo(f"  ⚠ No data returned for {symbol}")
                    continue

                click.echo(f"  ✓ Fetched {len(candles)} candles")

                # Store data if not dry run
                if not dry_run and repository:
                    for candle in candles:
                        await repository.upsert(candle)

                    click.echo(f"  ✓ Stored {len(candles)} candles")
                    stats["total_candles"] += len(candles)

                # Update progress
                stats["completed_symbols"] += 1

                if show_progress:
                    progress = (stats["completed_symbols"] / stats["total_symbols"]) * 100
                    click.echo(f"  Progress: {progress:.1f}%")

            except Exception as e:
                stats["failed_symbols"] += 1
                logger.error("symbol_failed", symbol=symbol, error=str(e))

                if skip_errors:
                    click.echo(f"  ✗ Failed: {e} (skipping...)", err=True)
                    continue
                else:
                    click.echo(f"  ✗ Failed: {e}", err=True)
                    click.echo("\nStopping due to error. Use --skip-errors to continue.")
                    break

    finally:
        # Cleanup
        if repository:
            await repository.close()

    # Print summary
    elapsed = (datetime.now() - stats["start_time"]).total_seconds()
    click.echo(f"\n{'='*60}")
    click.echo("BACKFILL SUMMARY")
    click.echo(f"{'='*60}")
    click.echo(f"Symbols processed:  {stats['completed_symbols']}/{stats['total_symbols']}")
    click.echo(f"Failed symbols:     {stats['failed_symbols']}")
    if not dry_run:
        click.echo(f"Total candles:      {stats['total_candles']:,}")
    click.echo(f"Elapsed time:       {elapsed:.1f}s")
    click.echo(f"{'='*60}")


async def run_verification(
    symbols: List[str],
    start_date: datetime,
    end_date: datetime
):
    """Verify data exists for date range"""
    try:
        db_config = DatabaseConfig()
        repository = TimescaleDBRepository(db_config)
        await repository.connect()
    except Exception as e:
        click.echo(f"✗ Failed to connect to database: {e}", err=True)
        return

    try:
        click.echo(f"\nVerifying data from {start_date.date()} to {end_date.date()}")
        click.echo(f"{'='*60}")

        for symbol in symbols:
            try:
                # Query data
                data = await repository.query_range(symbol, start_date, end_date)
                count = len(data)

                # Check for gaps
                if count == 0:
                    status = "✗ MISSING"
                else:
                    # Calculate expected data points (1 day candles)
                    expected_days = (end_date - start_date).days + 1
                    if count >= expected_days * 0.9:  # 90% threshold
                        status = f"✓ OK ({count} points)"
                    else:
                        status = f"⚠ INCOMPLETE ({count}/{expected_days} points)"

                click.echo(f"  {symbol:10s}: {status}")

            except Exception as e:
                click.echo(f"  {symbol:10s}: ✗ ERROR - {e}")

        click.echo(f"{'='*60}")

    finally:
        await repository.close()


async def run_gap_analysis(symbol: str, interval: str):
    """Find gaps in historical data"""
    try:
        db_config = DatabaseConfig()
        repository = TimescaleDBRepository(db_config)
        await repository.connect()
    except Exception as e:
        click.echo(f"✗ Failed to connect to database: {e}", err=True)
        return

    try:
        # Get earliest and latest data
        earliest = await repository.query_range(
            symbol,
            datetime(2020, 1, 1),
            datetime.now()
        )

        if not earliest or len(earliest) == 0:
            click.echo(f"✗ No data found for {symbol}")
            return

        first_date = earliest[0].time.date()
        click.echo(f"\nAnalyzing {symbol} from {first_date} to present")
        click.echo(f"{'='*60}")

        # Check for gaps (simplified - just shows date range coverage)
        click.echo(f"  First record: {first_date}")
        click.echo(f"  Total records: {len(earliest)}")
        click.echo(f"{'='*60}")

        # TODO: Implement detailed gap analysis
        # This would check for missing dates in the sequence

    finally:
        await repository.close()


if __name__ == "__main__":
    cli()
