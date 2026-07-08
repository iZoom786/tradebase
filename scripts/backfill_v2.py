#!/usr/bin/env python3
"""
Enhanced Backfill CLI (v2.0)

Features:
- 1-year historical backfill with resume capability
- Gap detection and repair
- State tracking for interruption recovery
- Materialized view manual refresh
- Batch processing for performance

Usage:
    # Backfill last 365 days for EURUSD
    python scripts/backfill_v2.py backfill --symbols EURUSD --days 365

    # Resume interrupted backfill
    python scripts/backfill_v2.py backfill --symbols EURUSD --resume

    # Detect and fill gaps
    python scripts/backfill_v2.py gap --symbols EURUSD

    # Refresh materialized views
    python scripts/backfill_v2.py refresh

    # Show backfill status
    python scripts/backfill_v2.py status --symbols EURUSD
"""

import asyncio
import argparse
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ingestion.providers.yfinance_v2 import YFinanceProviderV2
from services.ingestion.controllers.ingestion_controller_v2 import IngestionControllerV2, GapRepairManager
from services.ingestion.views import DataPublisher
from libs.db_repo.timescaledb_v2 import TimescaleDBRepository
from libs.nats_client import NATSClient
from libs.common.config import DatabaseConfig, NATSConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackfillCLI:
    """Enhanced backfill CLI"""

    def __init__(self):
        self.repository = None
        self.nats_client = None
        self.publisher = None
        self.controller = None

    async def initialize(self):
        """Initialize components"""
        # Initialize database
        db_config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="tradebase",
            user="postgres",
            password="postgres"
        )
        self.repository = TimescaleDBRepository(db_config)
        await self.repository.connect()
        logger.info("✓ Database connected")

        # Initialize NATS (optional for backfill)
        try:
            nats_config = NATSConfig(
                url="nats://localhost:4222"
            )
            self.nats_client = NATSClient(nats_config)
            await self.nats_client.connect()
            logger.info("✓ NATS connected")

            self.publisher = DataPublisher(self.nats_client)
        except Exception as e:
            logger.warning(f"NATS connection failed (continuing without NATS): {e}")
            self.publisher = None

    async def shutdown(self):
        """Shutdown components"""
        if self.nats_client:
            await self.nats_client.close()
        if self.repository:
            await self.repository.close()

    async def cmd_backfill(self, args):
        """
        Run historical backfill

        Supports:
        - 1-year backfill
        - Resume on interruption
        - Batch processing
        - State tracking
        """
        logger.info("=" * 60)
        logger.info("BACKFILL MODE")
        logger.info("=" * 60)

        # Initialize provider
        provider = YFinanceProviderV2(
            symbols=args.symbols,
            default_rows=3
        )

        # Initialize controller
        controller = IngestionControllerV2(
            provider=provider,
            repository=self.repository,
            publisher=self.publisher
        )

        # Determine start point
        days = args.days or 365

        # Check if resuming
        resume = args.resume or False

        # Backfill each symbol
        results = {}
        for symbol in args.symbols:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Processing: {symbol}")
            logger.info(f"{'=' * 60}")

            try:
                result = await controller.backfill_historical(
                    symbol=symbol,
                    days=days,
                    batch_size=args.batch_size or 1000,
                    resume=resume
                )
                results[symbol] = result

                # Print summary
                print(f"\n✓ {symbol} Backfill Summary:")
                print(f"  - Requested: {result['days_requested']} days")
                print(f"  - Fetched: {result['fetched']} candles")
                print(f"  - Upserted: {result['upserted']} records")
                print(f"  - Skipped: {result['skipped']} duplicates")
                print(f"  - Errors: {result['errors']}")
                if result.get('resumed'):
                    print(f"  - Resumed from: {result.get('resumed')}")

            except Exception as e:
                logger.error(f"Backfill failed for {symbol}: {e}")
                results[symbol] = {"error": str(e)}

        # Refresh materialized views after backfill
        if not args.no_refresh:
            logger.info("\n" + "=" * 60)
            logger.info("REFRESHING MATERIALIZED VIEWS")
            logger.info("=" * 60)

            refresh_results = await self.repository.refresh_continuous_aggregates()
            for result in refresh_results:
                status = "✓" if result["status"] == "success" else "✗"
                print(f"{status} {result['view']}: {result['status']}")

        # Print final summary
        print("\n" + "=" * 60)
        print("BACKFILL COMPLETE")
        print("=" * 60)
        for symbol, result in results.items():
            if "error" not in result:
                print(f"✓ {symbol}: {result['upserted']} records upserted")
            else:
                print(f"✗ {symbol}: {result['error']}")

    async def cmd_gap(self, args):
        """Detect and fill gaps in data"""
        logger.info("=" * 60)
        logger.info("GAP DETECTION & REPAIR")
        logger.info("=" * 60)

        # Initialize
        provider = YFinanceProviderV2(symbols=args.symbols)
        controller = IngestionControllerV2(
            provider=provider,
            repository=self.repository,
            publisher=self.publisher
        )

        gap_manager = GapRepairManager(self.repository, controller)

        # Scan and repair gaps
        summary = await gap_manager.scan_and_repair(
            symbols=args.symbols,
            gap_threshold_minutes=args.threshold or 5
        )

        # Print summary
        print(f"\n✓ Symbols scanned: {summary['symbols_scanned']}")
        print(f"  Total gaps found: {summary['total_gaps_found']}")
        print(f"  Total gaps filled: {summary['total_gaps_filled']}")
        print(f"  Total records filled: {summary['total_records_filled']}")

        if summary['symbols_with_gaps']:
            print(f"\nSymbols with gaps: {', '.join(summary['symbols_with_gaps'])}")

        # Refresh views after gap repair
        if not args.no_refresh:
            logger.info("\nRefreshing materialized views...")
            await self.repository.refresh_continuous_aggregates()

    async def cmd_status(self, args):
        """Show backfill status for symbols"""
        logger.info("=" * 60)
        logger.info("BACKFILL STATUS")
        logger.info("=" * 60)

        for symbol in args.symbols:
            # Get ingestion state
            state = await self.repository.get_ingestion_state(symbol)

            # Get data statistics
            count = await self.repository.get_data_count(symbol)
            data_range = await self.repository.get_data_range(symbol)

            # Detect gaps
            gaps = await self.repository.detect_gaps(symbol)

            print(f"\n{'=' * 60}")
            print(f"Symbol: {symbol}")
            print(f"{'=' * 60}")
            print(f"Total records: {count}")

            if data_range:
                start, end = data_range
                print(f"Data range: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
                days = (end - start).days
                print(f"Days covered: {days}")
            else:
                print("Data range: No data")

            if state:
                print(f"\nIngestion State:")
                print(f"  - Backfill complete: {state.get('backfill_complete', False)}")
                if state.get('last_backfill_time'):
                    print(f"  - Last backfill: {state['last_backfill_time']}")
                if state.get('last_ingest_time'):
                    print(f"  - Last ingest: {state['last_ingest_time']}")
                print(f"  - Error count: {state.get('error_count', 0)}")
                if state.get('last_error'):
                    print(f"  - Last error: {state['last_error']}")

            print(f"\nGaps detected: {len(gaps)}")
            if gaps:
                print("Recent gaps:")
                for gap in gaps[:5]:
                    print(f"  - {gap['gap_start']} to {gap['gap_end']} ({gap['gap_minutes']} min)")

    async def cmd_refresh(self, args):
        """Refresh materialized views manually"""
        logger.info("=" * 60)
        logger.info("REFRESHING MATERIALIZED VIEWS")
        logger.info("=" * 60)

        results = await self.repository.refresh_continuous_aggregates()

        print("\nRefresh Results:")
        for result in results:
            status = "✓" if result["status"] == "success" else "✗"
            print(f"{status} {result['view']}: {result['status']}")
            if result.get("error"):
                print(f"  Error: {result['error']}")

    async def cmd_verify(self, args):
        """Verify backfilled data"""
        logger.info("=" * 60)
        logger.info("DATA VERIFICATION")
        logger.info("=" * 60)

        for symbol in args.symbols:
            # Get last few records
            end = datetime.now()
            start = end - timedelta(days=args.days or 7)

            records = await self.repository.query_range(
                symbol=symbol,
                start=start,
                end=end,
                interval="1m"
            )

            print(f"\n{symbol}:")
            print(f"  Records in last {args.days or 7} days: {len(records)}")

            if records:
                # Show sample of records
                print(f"  Sample records (first 3):")
                for record in records[:3]:
                    print(f"    - {record.time}: O={record.open} H={record.high} L={record.low} C={record.close}")

                # Check for duplicates (same timekey)
                timekeys = {}
                duplicates = 0
                for record in records:
                    if record.timekey in timekeys:
                        duplicates += 1
                    else:
                        timekeys[record.timekey] = True

                if duplicates > 0:
                    print(f"  ⚠ Duplicates found: {duplicates}")
                else:
                    print(f"  ✓ No duplicates")

    async def run(self):
        """Main entry point"""
        parser = argparse.ArgumentParser(
            description="Enhanced Backfill CLI (v2.0)",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Backfill last 365 days
  python scripts/backfill_v2.py backfill --symbols EURUSD,GBPUSD --days 365

  # Resume interrupted backfill
  python scripts/backfill_v2.py backfill --symbols EURUSD --resume

  # Detect and fill gaps
  python scripts/backfill_v2.py gap --symbols EURUSD --threshold 5

  # Check status
  python scripts/backfill_v2.py status --symbols EURUSD

  # Refresh materialized views
  python scripts/backfill_v2.py refresh
            """
        )

        parser.add_argument(
            '--symbols',
            type=str,
            help='Comma-separated list of symbols'
        )

        subparsers = parser.add_subparsers(dest='command', help='Commands')

        # Backfill command
        backfill_parser = subparsers.add_parser('backfill', help='Run historical backfill')
        backfill_parser.add_argument('--symbols', required=True, help='Symbols to backfill')
        backfill_parser.add_argument('--days', type=int, default=365, help='Days to backfill (default: 365)')
        backfill_parser.add_argument('--batch-size', type=int, default=1000, help='Batch size (default: 1000)')
        backfill_parser.add_argument('--resume', action='store_true', help='Resume from last checkpoint')
        backfill_parser.add_argument('--no-refresh', action='store_true', help='Skip materialized view refresh')

        # Gap command
        gap_parser = subparsers.add_parser('gap', help='Detect and fill gaps')
        gap_parser.add_argument('--symbols', required=True, help='Symbols to check')
        gap_parser.add_argument('--threshold', type=int, default=5, help='Gap threshold in minutes (default: 5)')
        gap_parser.add_argument('--no-refresh', action='store_true', help='Skip materialized view refresh')

        # Status command
        status_parser = subparsers.add_parser('status', help='Show backfill status')
        status_parser.add_argument('--symbols', required=True, help='Symbols to check')

        # Refresh command
        refresh_parser = subparsers.add_parser('refresh', help='Refresh materialized views')

        # Verify command
        verify_parser = subparsers.add_parser('verify', help='Verify backfilled data')
        verify_parser.add_argument('--symbols', required=True, help='Symbols to verify')
        verify_parser.add_argument('--days', type=int, default=7, help='Days to verify (default: 7)')

        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return

        await self.initialize()

        try:
            if args.command == 'backfill':
                await self.cmd_backfill(args)
            elif args.command == 'gap':
                await self.cmd_gap(args)
            elif args.command == 'status':
                await self.cmd_status(args)
            elif args.command == 'refresh':
                await self.cmd_refresh(args)
            elif args.command == 'verify':
                await self.cmd_verify(args)
        finally:
            await self.shutdown()


async def main():
    cli = BackfillCLI()
    await cli.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(0)
