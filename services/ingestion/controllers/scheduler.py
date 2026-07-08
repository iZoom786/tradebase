"""
Ingestion Scheduler - Automated periodic data fetching

Uses APScheduler to trigger ingestion at regular intervals.
Supports multiple scheduling strategies:
1. Interval-based (every N seconds/minutes)
2. Cron-based (specific time patterns)
3. Market-hour-aware (only during trading hours)
"""

import asyncio
import logging
from datetime import datetime, time
from typing import List, Optional, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from services.ingestion.controllers.ingestion_controller import IngestionController

logger = logging.getLogger(__name__)


class MarketHours:
    """Define trading hours for different markets"""

    # Forex market hours (UTC) - 24/5 market
    FOREX_OPEN = time(hour=0, minute=0)  # Sunday 10pm EST / Monday 2am UTC
    FOREX_CLOSE = time(hour=23, minute=59)  # Friday 10pm EST / Friday 23:59 UTC

    # Crypto market hours - 24/7
    CRYPTO_OPEN = time(hour=0, minute=0)
    CRYPTO_CLOSE = time(hour=23, minute=59)

    # Stock market hours (UTC) - 9:30am-4pm EST
    STOCK_OPEN = time(hour=13, minute=30)  # 9:30am EST = 1:30pm UTC (standard time)
    STOCK_CLOSE = time(hour=20, minute=0)  # 4:00pm EST = 8:00pm UTC (standard time)


class IngestionScheduler:
    """
    Scheduler for automated periodic ingestion

    Features:
    - Interval-based scheduling
    - Cron-based scheduling
    - Market hours filtering
    - Multiple symbol groups
    - Health monitoring
    """

    def __init__(
        self,
        controller: IngestionController,
        scheduler: Optional[AsyncIOScheduler] = None
    ):
        """
        Initialize scheduler

        Args:
            controller: Ingestion controller instance
            scheduler: Optional pre-configured scheduler
        """
        self.controller = controller
        self.scheduler = scheduler or AsyncIOScheduler(
            timezone='UTC',
            job_defaults={
                'coalesce': True,  # Combine missed jobs
                'max_instances': 1,  # Prevent overlapping
                'misfire_grace_time': 300  # 5 minutes grace
            }
        )
        self._jobs = {}

    def add_interval_job(
        self,
        symbols: List[str],
        interval_seconds: int,
        job_id: Optional[str] = None,
        market_hours_filter: Optional[Callable[[datetime], bool]] = None
    ) -> str:
        """
        Add interval-based ingestion job

        Args:
            symbols: List of symbols to ingest
            interval_seconds: Interval between runs
            job_id: Unique job identifier (auto-generated if None)
            market_hours_filter: Optional function to filter by market hours

        Returns:
            Job ID
        """
        if job_id is None:
            job_id = f"interval_{len(self._jobs)}_{datetime.now().timestamp()}"

        async def run_job():
            """Run ingestion for all symbols"""
            try:
                logger.info("scheduler_job_starting", job_id=job_id, symbols=symbols)
                await self._ingest_symbols(symbols)
                logger.info("scheduler_job_complete", job_id=job_id)
            except Exception as e:
                logger.error("scheduler_job_failed", job_id=job_id, error=str(e))

        # Create trigger
        trigger = IntervalTrigger(seconds=interval_seconds)

        # Add market hours filter if provided
        if market_hours_filter:
            # Store filter with job
            job = self.scheduler.add_job(
                run_job,
                trigger=trigger,
                id=job_id,
                name=f"Ingest {', '.join(symbols)} every {interval_seconds}s"
            )
            # We'll check market hours in the job itself
        else:
            job = self.scheduler.add_job(
                run_job,
                trigger=trigger,
                id=job_id,
                name=f"Ingest {', '.join(symbols)} every {interval_seconds}s"
            )

        self._jobs[job_id] = job
        logger.info(
            "scheduler_job_added",
            job_id=job_id,
            interval=interval_seconds,
            symbols=symbols
        )

        return job_id

    def add_cron_job(
        self,
        symbols: List[str],
        cron_expression: str,
        job_id: Optional[str] = None,
        market_hours_filter: Optional[Callable[[datetime], bool]] = None
    ) -> str:
        """
        Add cron-based ingestion job

        Args:
            symbols: List of symbols to ingest
            cron_expression: Cron expression (e.g., "*/5 * * * *")
            job_id: Unique job identifier
            market_hours_filter: Optional function to filter by market hours

        Returns:
            Job ID
        """
        if job_id is None:
            job_id = f"cron_{len(self._jobs)}_{datetime.now().timestamp()}"

        async def run_job():
            """Run ingestion for all symbols"""
            try:
                logger.info("scheduler_cron_starting", job_id=job_id, symbols=symbols)
                await self._ingest_symbols(symbols)
                logger.info("scheduler_cron_complete", job_id=job_id)
            except Exception as e:
                logger.error("scheduler_cron_failed", job_id=job_id, error=str(e))

        # Parse cron expression
        # Format: minute hour day month day_of_week
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4]
        )

        job = self.scheduler.add_job(
            run_job,
            trigger=trigger,
            id=job_id,
            name=f"Ingest {', '.join(symbols)} cron: {cron_expression}"
        )

        self._jobs[job_id] = job
        logger.info(
            "scheduler_cron_added",
            job_id=job_id,
            cron=cron_expression,
            symbols=symbols
        )

        return job_id

    def add_market_hours_job(
        self,
        symbols: List[str],
        interval_seconds: int,
        market: str = "forex",
        job_id: Optional[str] = None
    ) -> str:
        """
        Add job that only runs during market hours

        Args:
            symbols: List of symbols to ingest
            interval_seconds: Interval between runs during market hours
            market: Market type (forex, crypto, stock)
            job_id: Unique job identifier

        Returns:
            Job ID
        """
        if job_id is None:
            job_id = f"market_hours_{market}_{len(self._jobs)}_{datetime.now().timestamp()}"

        # Get market hours
        if market.lower() == "forex":
            open_time = MarketHours.FOREX_OPEN
            close_time = MarketHours.FOREX_CLOSE
        elif market.lower() == "crypto":
            open_time = MarketHours.CRYPTO_OPEN
            close_time = MarketHours.CRYPTO_CLOSE
        elif market.lower() == "stock":
            open_time = MarketHours.STOCK_OPEN
            close_time = MarketHours.STOCK_CLOSE
        else:
            raise ValueError(f"Unknown market: {market}")

        async def run_job():
            """Run ingestion only during market hours"""
            now = datetime.utcnow()

            # Check if current time is within market hours
            current_time = now.time()
            is_market_open = open_time <= current_time <= close_time

            # For forex, also check weekday (Mon-Fri)
            if market.lower() == "forex":
                is_weekday = now.weekday() < 5  # 0=Monday, 6=Sunday
                is_market_open = is_market_open and is_weekday

            if is_market_open:
                try:
                    logger.info(
                        "scheduler_market_hours_ingest",
                        job_id=job_id,
                        symbols=symbols,
                        market=market
                    )
                    await self._ingest_symbols(symbols)
                except Exception as e:
                    logger.error(
                        "scheduler_market_hours_failed",
                        job_id=job_id,
                        error=str(e)
                    )
            else:
                logger.debug(
                    "scheduler_market_closed",
                    job_id=job_id,
                    market=market
                )

        trigger = IntervalTrigger(seconds=interval_seconds)

        job = self.scheduler.add_job(
            run_job,
            trigger=trigger,
            id=job_id,
            name=f"Ingest {', '.join(symbols)} during {market} hours"
        )

        self._jobs[job_id] = job
        logger.info(
            "scheduler_market_hours_job_added",
            job_id=job_id,
            market=market,
            interval=interval_seconds,
            symbols=symbols
        )

        return job_id

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job

        Args:
            job_id: Job to remove

        Returns:
            True if job was removed, False if not found
        """
        job = self._jobs.pop(job_id, None)
        if job:
            job.remove()
            logger.info("scheduler_job_removed", job_id=job_id)
            return True
        return False

    def start(self) -> None:
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("scheduler_started", jobs_count=len(self._jobs))
        else:
            logger.warning("scheduler_already_running")

    def stop(self) -> None:
        """Stop the scheduler gracefully"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self.scheduler.running

    def get_jobs(self) -> dict:
        """Get all scheduled jobs"""
        return {
            job_id: {
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job_id, job in self._jobs.items()
        }

    async def _ingest_symbols(self, symbols: List[str]) -> None:
        """
        Ingest data for multiple symbols concurrently

        Args:
            symbols: List of symbols to ingest
        """
        # Create tasks for each symbol
        tasks = [
            self.controller.ingest_latest(symbol)
            for symbol in symbols
        ]

        # Run concurrently and gather results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log results
        successes = sum(1 for r in results if not isinstance(r, Exception))
        errors = len(results) - successes

        logger.info(
            "scheduler_batch_complete",
            successes=successes,
            errors=errors,
            total=len(symbols)
        )

        if errors > 0:
            error_details = [
                f"{symbol}: {str(r)}"
                for symbol, r in zip(symbols, results)
                if isinstance(r, Exception)
            ]
            logger.warning("scheduler_batch_errors", errors=error_details)


class PresetSchedulers:
    """
    Pre-configured scheduler presets for common use cases

    Presets:
    - forex_1min: Ingest major forex pairs every minute
    - crypto_1min: Ingest crypto pairs every minute (24/7)
    - daily_backfill: Daily backfill at 2 AM UTC
    - hourly_update: Hourly data refresh
    """

    @staticmethod
    def forex_1min(scheduler: IngestionScheduler) -> str:
        """
        Schedule forex 1-minute ingestion (market hours only)

        Mon-Fri, 24 hours (forex is 24/5 market)
        """
        symbols = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
        return scheduler.add_market_hours_job(
            symbols=symbols,
            interval_seconds=60,
            market="forex",
            job_id="forex_1min"
        )

    @staticmethod
    def crypto_1min(scheduler: IngestionScheduler) -> str:
        """
        Schedule crypto 1-minute ingestion (24/7)

        Crypto markets never close
        """
        symbols = ["BTCUSD", "ETHUSD", "BTCUSDT", "ETHUSDT"]
        return scheduler.add_interval_job(
            symbols=symbols,
            interval_seconds=60,
            job_id="crypto_1min"
        )

    @staticmethod
    def hourly_update(scheduler: IngestionScheduler) -> str:
        """
        Schedule hourly data refresh

        Runs at the top of every hour
        """
        symbols = ["EURUSD", "GBPUSD", "USDJPY"]
        return scheduler.add_cron_job(
            symbols=symbols,
            cron_expression="0 * * * *",  # Every hour at minute 0
            job_id="hourly_update"
        )

    @staticmethod
    def daily_backfill(scheduler: IngestionScheduler) -> str:
        """
        Schedule daily backfill job

        Runs at 2 AM UTC every day
        """
        symbols = ["EURUSD", "GBPUSD", "USDJPY"]
        return scheduler.add_cron_job(
            symbols=symbols,
            cron_expression="0 2 * * *",  # 2:00 AM every day
            job_id="daily_backfill"
        )


# Convenience function for quick setup
def create_default_scheduler(controller: IngestionController) -> IngestionScheduler:
    """
    Create scheduler with default forex 1-minute job

    Args:
        controller: Ingestion controller instance

    Returns:
        Configured scheduler
    """
    scheduler = IngestionScheduler(controller)
    PresetSchedulers.forex_1min(scheduler)
    return scheduler
