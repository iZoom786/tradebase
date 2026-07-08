"""
Enhanced Ingestion Controller (v2.0)

Features:
- 3-row per minute fetching for robustness
- Resume/backfill on service interruption
- State tracking for recovery
- Gap detection and repair
- Batch upsert for performance
"""

import asyncio
import logging
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal

from opentelemetry import trace

from ..providers import DataProvider
from ..views import DataPublisher
from libs.db_repo import Repository

logger = logging.getLogger(__name__)


class IngestionControllerV2:
    """
    Enhanced ingestion controller with resume capability

    Key Features:
    1. Fetches 3 recent candles every minute (buffer, completed, forming)
    2. Stores only the completed candle(s)
    3. Tracks state for resume on interruption
    4. Auto-backfills gaps on resume
    5. Batch upsert for better performance
    """

    def __init__(
        self,
        provider: DataProvider,
        repository: Repository,
        publisher: DataPublisher,
        rows_per_minute: int = 3
    ):
        """
        Initialize enhanced controller

        Args:
            provider: Data provider instance
            repository: Database repository
            publisher: NATS publisher
            rows_per_minute: Number of rows to fetch per minute (default: 3)
        """
        self.provider = provider
        self.repository = repository
        self.publisher = publisher
        self.rows_per_minute = rows_per_minute
        self._running = False
        self._symbols: List[str] = []
        self.tracer = trace.get_tracer(__name__)

    async def ingest_latest(self, symbol: str) -> dict:
        """
        Fetch and store the latest 3 rows, store the completed ones

        Strategy:
        1. Fetch N recent candles (default: 3)
        2. Identify which candles are complete
        3. Upsert only complete candles
        4. Publish to NATS

        Args:
            symbol: Trading symbol to ingest

        Returns:
            Dict with ingestion statistics
        """
        with self.tracer.start_as_current_span("ingest_latest_v2") as span:
            span.set_attribute("symbol", symbol)

            stats = {
                "symbol": symbol,
                "fetched": 0,
                "upserted": 0,
                "published": 0,
                "errors": 0,
                "timestamp": datetime.now().isoformat()
            }

            try:
                # Fetch N recent candles
                candles = await self.provider.fetch_latest_n_candles(
                    symbol,
                    count=self.rows_per_minute
                )
                stats["fetched"] = len(candles)

                if not candles:
                    logger.warning("no_data_fetched", symbol=symbol)
                    return stats

                # Filter for complete candles only
                # The last candle is still forming, so we skip it
                now = datetime.now()
                current_minute = now.replace(second=0, microsecond=0)

                complete_candles = []
                for candle in candles:
                    # Check if candle time is at least 1 minute old
                    candle_time = candle.time
                    if candle_time < current_minute:
                        complete_candles.append(candle)

                logger.debug(
                    "filtered_candles",
                    symbol=symbol,
                    total=len(candles),
                    complete=len(complete_candles)
                )

                # Batch upsert complete candles
                if complete_candles:
                    # Upsert in batch for performance
                    for candle in complete_candles:
                        await self.repository.upsert(candle)
                        stats["upserted"] += 1

                        # Publish to NATS
                        await self.publisher.publish_raw(candle)
                        stats["published"] += 1

                    # Update ingestion state
                    latest_candle = complete_candles[-1]
                    await self._update_ingestion_state(
                        symbol,
                        latest_candle.time,
                        latest_candle.timekey
                    )

                    logger.info(
                        "ingestion_complete",
                        symbol=symbol,
                        upserted=stats["upserted"],
                        latest_time=latest_candle.time.isoformat()
                    )

                span.set_attribute("success", True)
                return stats

            except Exception as e:
                logger.error("ingestion_failed", symbol=symbol, error=str(e))
                stats["errors"] = 1
                stats["error_message"] = str(e)

                # Update error count in state
                await self.repository.increment_error_count(symbol, str(e))

                span.set_attribute("error", str(e))
                span.set_attribute("success", False)
                raise

    async def backfill_historical(
        self,
        symbol: str,
        days: int = 365,
        batch_size: int = 1000,
        resume: bool = True
    ) -> dict:
        """
        Backfill historical data with resume capability

        Strategy:
        1. Check ingestion state to find where to resume
        2. Fetch data in batches
        3. Update state periodically for resume capability
        4. Handle interruptions gracefully

        Args:
            symbol: Trading symbol
            days: Number of days to backfill (default: 1 year)
            batch_size: Records per batch
            resume: Resume from last checkpoint if interrupted

        Returns:
            Dict with backfill statistics
        """
        with self.tracer.start_as_current_span("backfill_historical_v2") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("days", days)

            stats = {
                "symbol": symbol,
                "days_requested": days,
                "fetched": 0,
                "upserted": 0,
                "skipped": 0,
                "errors": 0,
                "start_time": datetime.now().isoformat(),
                "resumed": False,
                "gaps_filled": 0
            }

            try:
                end = datetime.now()
                start = end - timedelta(days=days)

                # Check if we should resume
                last_backfill_time = None
                if resume:
                    state = await self.repository.get_ingestion_state(symbol)
                    if state and state.get("last_backfill_time"):
                        last_backfill_time = state["last_backfill_time"]
                        stats["resumed"] = True
                        # Resume from where we left off
                        start = last_backfill_time + timedelta(minutes=1)
                        logger.info(
                            "resuming_backfill",
                            symbol=symbol,
                            from_time=start.isoformat()
                        )

                logger.info(
                    "backfill_start",
                    symbol=symbol,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    resumed=stats["resumed"]
                )

                # Check for gaps first
                gaps = await self.repository.detect_gaps(symbol, "1m", gap_threshold_minutes=5)
                if gaps:
                    logger.info("gaps_detected", symbol=symbol, count=len(gaps))
                    stats["gaps_detected"] = len(gaps)

                # Fetch and backfill data in batches
                # Note: YFinance has limits on historical data
                # We need to fetch in smaller chunks
                total_upserted = 0
                current_start = start

                while current_start < end:
                    # Calculate batch end (max 7 days per batch for YFinance)
                    batch_end = min(
                        current_start + timedelta(days=7),
                        end
                    )

                    # Fetch batch
                    candles = await self.provider.fetch_historical(
                        symbol,
                        current_start,
                        batch_end
                    )

                    if candles:
                        # Batch upsert
                        for candle in candles:
                            try:
                                await self.repository.upsert(candle)
                                total_upserted += 1
                            except Exception as e:
                                stats["skipped"] += 1
                                logger.debug(
                                    "backfill_skip",
                                    symbol=symbol,
                                    time=candle.time.isoformat(),
                                    error=str(e)
                                )

                        # Update state periodically
                        latest_in_batch = candles[-1]
                        await self.repository.update_ingestion_state(
                            symbol=symbol,
                            last_backfill_time=latest_in_batch.time,
                            last_backfill_timekey=latest_in_batch.timekey
                        )

                    stats["fetched"] += len(candles) if candles else 0
                    stats["upserted"] = total_upserted

                    # Move to next batch
                    current_start = batch_end + timedelta(minutes=1)

                    # Small delay to avoid overwhelming the API
                    await asyncio.sleep(0.5)

                # Mark backfill as complete
                await self.repository.update_ingestion_state(
                    symbol=symbol,
                    last_backfill_time=end,
                    backfill_complete=True
                )

                stats["end_time"] = datetime.now().isoformat()
                logger.info(
                    "backfill_complete",
                    symbol=symbol,
                    **stats
                )

                span.set_attribute("success", True)
                span.set_attribute("count", stats["upserted"])
                return stats

            except Exception as e:
                logger.error("backfill_failed", symbol=symbol, error=str(e))
                stats["errors"] += 1
                stats["error_message"] = str(e)

                await self.repository.increment_error_count(symbol, str(e))

                span.set_attribute("error", str(e))
                span.set_attribute("success", False)
                raise

    async def backfill_gaps(
        self,
        symbol: str,
        gap_threshold_minutes: int = 5
    ) -> dict:
        """
        Detect and fill gaps in data

        Args:
            symbol: Trading symbol
            gap_threshold_minutes: Minimum gap to fill

        Returns:
            Dict with gap filling statistics
        """
        with self.tracer.start_as_current_span("backfill_gaps") as span:
            span.set_attribute("symbol", symbol)

            stats = {
                "symbol": symbol,
                "gaps_detected": 0,
                "gaps_filled": 0,
                "records_filled": 0,
                "errors": 0
            }

            try:
                # Detect gaps
                gaps = await self.repository.detect_gaps(
                    symbol,
                    "1m",
                    gap_threshold_minutes
                )

                stats["gaps_detected"] = len(gaps)

                if not gaps:
                    logger.info("no_gaps_detected", symbol=symbol)
                    return stats

                logger.info("gaps_detected", symbol=symbol, count=len(gaps))

                # Fill each gap
                for gap in gaps:
                    try:
                        gap_start = gap["gap_start"]
                        gap_end = gap["gap_end"]

                        # Fetch data for gap period
                        candles = await self.provider.fetch_historical(
                            symbol,
                            gap_start,
                            gap_end
                        )

                        # Upsert gap data
                        for candle in candles:
                            await self.repository.upsert(candle)
                            stats["records_filled"] += 1

                        stats["gaps_filled"] += 1
                        logger.info(
                            "gap_filled",
                            symbol=symbol,
                            gap_start=gap_start.isoformat(),
                            gap_end=gap_end.isoformat(),
                            records=len(candles)
                        )

                    except Exception as e:
                        logger.error(
                            "gap_fill_failed",
                            symbol=symbol,
                            gap=gap,
                            error=str(e)
                        )
                        stats["errors"] += 1

                span.set_attribute("success", True)
                return stats

            except Exception as e:
                logger.error("gap_detection_failed", symbol=symbol, error=str(e))
                stats["errors"] = 1
                span.set_attribute("error", str(e))
                span.set_attribute("success", False)
                raise

    async def run(self, symbols: List[str]) -> None:
        """
        Continuous ingestion loop with resume capability

        Runs every minute, fetches 3 rows, stores complete ones.
        Automatically resumes from last checkpoint on restart.

        Args:
            symbols: List of symbols to ingest
        """
        self._running = True
        self._symbols = symbols

        logger.info("ingestion_started_v2", symbols=symbols, mode="3_row_per_minute")

        while self._running:
            try:
                # Calculate delay to next minute's 5th second
                now = datetime.now()
                next_run = now.replace(second=5, microsecond=0)
                if now.second >= 5:
                    next_run += timedelta(minutes=1)

                delay = (next_run - now).total_seconds()

                if delay > 0:
                    await asyncio.sleep(delay)

                # Fetch all symbols concurrently
                tasks = [self.ingest_latest(s) for s in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                total_upserted = 0
                total_errors = 0

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        total_errors += 1
                        logger.error(
                            "ingestion_error",
                            symbol=symbols[i],
                            error=str(result)
                        )
                    else:
                        total_upserted += result.get("upserted", 0)

                logger.info(
                    "batch_complete",
                    symbols=len(symbols),
                    total_upserted=total_upserted,
                    total_errors=total_errors
                )

            except Exception as e:
                logger.error("ingestion_loop_error", error=str(e))
                await asyncio.sleep(60)  # Wait before retry

    def stop(self) -> None:
        """Stop the ingestion loop"""
        self._running = False
        logger.info("ingestion_stopped")

    async def _update_ingestion_state(
        self,
        symbol: str,
        time: datetime,
        timekey: int
    ) -> None:
        """Update ingestion state after successful ingestion"""
        try:
            await self.repository.update_ingestion_state(
                symbol=symbol,
                last_ingest_time=time,
                last_ingest_timekey=timekey
            )
        except Exception as e:
            logger.warning("failed_to_update_state", symbol=symbol, error=str(e))


class GapRepairManager:
    """
    Manages gap detection and repair

    Scans for gaps in historical data and fills them automatically.
    """

    def __init__(self, repository: Repository, controller: IngestionControllerV2):
        self.repository = repository
        self.controller = controller

    async def scan_and_repair(
        self,
        symbols: List[str],
        gap_threshold_minutes: int = 5
    ) -> dict:
        """
        Scan all symbols for gaps and repair them

        Args:
            symbols: List of symbols to scan
            gap_threshold_minutes: Minimum gap to consider

        Returns:
            Summary of repair operations
        """
        summary = {
            "symbols_scanned": len(symbols),
            "total_gaps_found": 0,
            "total_gaps_filled": 0,
            "total_records_filled": 0,
            "symbols_with_gaps": [],
            "errors": 0
        }

        for symbol in symbols:
            try:
                result = await self.controller.backfill_gaps(symbol, gap_threshold_minutes)

                if result["gaps_detected"] > 0:
                    summary["symbols_with_gaps"].append(symbol)
                    summary["total_gaps_found"] += result["gaps_detected"]
                    summary["total_gaps_filled"] += result["gaps_filled"]
                    summary["total_records_filled"] += result["records_filled"]

            except Exception as e:
                logger.error("gap_repair_failed", symbol=symbol, error=str(e))
                summary["errors"] += 1

        logger.info("gap_repair_summary", **summary)
        return summary
