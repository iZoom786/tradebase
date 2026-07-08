"""
Ingestion controller - orchestrates data fetching and publishing
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta

from opentelemetry import trace

from ..providers import DataProvider
from ..views import DataPublisher
from libs.db_repo import Repository

logger = logging.getLogger(__name__)


class IngestionController:
    """
    Orchestrates data ingestion from provider to NATS

    Responsibilities:
    - Fetch candles from provider
    - Store in database
    - Publish to NATS
    - Handle errors and retries
    """

    def __init__(
        self,
        provider: DataProvider,
        repository: Repository,
        publisher: DataPublisher
    ):
        self.provider = provider
        self.repository = repository
        self.publisher = publisher
        self._running = False
        self._symbols: List[str] = []
        self.tracer = trace.get_tracer(__name__)

    async def ingest_latest(self, symbol: str) -> None:
        """
        Fetch and publish the latest completed candle

        Args:
            symbol: Trading symbol to ingest
        """
        with self.tracer.start_as_current_span("ingest_latest") as span:
            span.set_attribute("symbol", symbol)

            try:
                # Fetch from provider
                candle = await self.provider.fetch_latest_candle(symbol)
                logger.info("candle_fetched", symbol=symbol, time=candle.time)

                # Store in database
                await self.repository.upsert(candle)

                # Publish to NATS
                await self.publisher.publish_raw(candle)

                logger.info("candle_published", symbol=symbol, time=candle.time)
                span.set_attribute("success", True)

            except Exception as e:
                logger.error("ingestion_failed", symbol=symbol, error=str(e))
                span.set_attribute("error", str(e))
                span.set_attribute("success", False)
                raise

    async def backfill_historical(self, symbol: str, days: int = 365) -> int:
        """
        Backfill historical data for a symbol

        Args:
            symbol: Trading symbol
            days: Number of days to backfill

        Returns:
            Number of candles backfilled
        """
        with self.tracer.start_as_current_span("backfill_historical") as span:
            end = datetime.now()
            start = end - timedelta(days=days)

            logger.info("backfill_start", symbol=symbol, start=start, end=end)

            candles = await self.provider.fetch_historical(symbol, start, end)

            count = 0
            for candle in candles:
                try:
                    await self.repository.upsert(candle)
                    count += 1
                except Exception as e:
                    logger.warning("backfill_skip", symbol=symbol, time=candle.time, error=str(e))

            logger.info("backfill_complete", symbol=symbol, count=count)
            span.set_attribute("count", count)

            return count

    async def run(self, symbols: List[str]) -> None:
        """
        Continuous ingestion loop

        Runs every minute at second 5 to ensure candle is closed.

        Args:
            symbols: List of symbols to ingest
        """
        self._running = True
        self._symbols = symbols

        logger.info("ingestion_started", symbols=symbols)

        while self._running:
            try:
                # Calculate delay to next minute's 5th second
                now = datetime.now()
                next_run = now.replace(second=5, microsecond=0)
                if now.second >= 5:
                    from datetime import timedelta
                    next_run += timedelta(minutes=1)

                delay = (next_run - now).total_seconds()
                await asyncio.sleep(delay)

                # Fetch all symbols concurrently
                tasks = [self.ingest_latest(s) for s in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                successes = sum(1 for r in results if not isinstance(r, Exception))
                errors = [r for r in results if isinstance(r, Exception)]

                logger.info(
                    "batch_complete",
                    successes=successes,
                    total=len(symbols),
                    errors=len(errors)
                )

            except Exception as e:
                logger.error("ingestion_loop_error", error=str(e))
                await asyncio.sleep(60)  # Wait before retry

    def stop(self) -> None:
        """Stop the ingestion loop"""
        self._running = False
        logger.info("ingestion_stopped")
