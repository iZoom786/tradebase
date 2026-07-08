"""
Enhanced YFinance data provider implementation (v2.0)

Features:
- Fetch N recent candles (default: 3)
- Better handling of incomplete candles
- Timekey generation support
"""

import asyncio
from typing import List
from datetime import datetime, timedelta
from decimal import Decimal

import yfinance as yf

from .base import DataProvider
from ..models.market_data_v2 import MarketData


class YFinanceProviderV2(DataProvider):
    """
    Enhanced YFinance provider for forex, crypto, and stock data

    Data Strategy:
    --------------
    - Fetches N recent candles (default: 3) every minute
    - Returns candles: [previous, completed, forming] for N=3
    - Only completed candles (time < current minute) should be stored
    - All higher timeframes derived from 1m via TimescaleDB materialized views

    Candle Selection:
    ---------------
    When fetching N=3 candles:
    - candles[2] (last): Still forming, DO NOT STORE
    - candles[1]: Complete candle, STORE THIS
    - candles[0]: Previous candle, STORE THIS (for redundancy)
    """

    def __init__(self, symbols: List[str], default_rows: int = 3):
        """
        Initialize YFinance provider

        Args:
            symbols: List of trading symbols (e.g., ['EURUSD', 'GBPUSD'])
            default_rows: Number of rows to fetch per minute (default: 3)
        """
        self.symbols = symbols
        self.default_rows = default_rows
        self._tickers = {}
        self._initialize_tickers()

    def _initialize_tickers(self):
        """Initialize ticker objects for all symbols"""
        for symbol in self.symbols:
            # YFinance uses '=X' suffix for forex
            yf_symbol = symbol if '=X' in symbol else f"{symbol}=X"
            self._tickers[symbol] = yf.Ticker(yf_symbol)

    @property
    def provider_name(self) -> str:
        return "yfinance"

    @property
    def supported_intervals(self) -> List[str]:
        return ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"]

    async def fetch_latest_candle(self, symbol: str) -> MarketData:
        """
        Fetch the most recent completed 1-minute candle (legacy method)

        Note: This fetches only 1 completed candle.
        Use fetch_latest_n_candles() for better reliability.
        """
        candles = await self.fetch_latest_n_candles(symbol, count=2)
        if len(candles) >= 2:
            return candles[-2]  # Return the completed candle (second to last)
        elif candles:
            return candles[-1]
        raise ValueError(f"No data available for {symbol}")

    async def fetch_latest_n_candles(
        self,
        symbol: str,
        count: int = 3
    ) -> List[MarketData]:
        """
        Fetch the N most recent 1-minute candles

        Args:
            symbol: Trading symbol
            count: Number of candles to fetch (default: 3)

        Returns:
            List of MarketData objects, oldest to newest
            Last candle in list is the currently forming one

        Example for count=3:
            Returns: [candle_T-2, candle_T-1, candle_T]
            - candle_T: Still forming (current minute)
            - candle_T-1: Complete (previous minute) - STORE THIS
            - candle_T-2: Complete (2 minutes ago) - STORE THIS
        """
        loop = asyncio.get_event_loop()

        def _fetch():
            ticker = self._tickers.get(symbol)
            if not ticker:
                raise ValueError(f"Symbol {symbol} not initialized")

            # Fetch last N+1 minutes to ensure we get N complete candles
            # We add buffer to account for the forming candle
            period = f"{count + 1}m"

            data = ticker.history(period="1d", interval="1m")

            if data is None or len(data) == 0:
                raise ValueError(f"No data available for {symbol}")

            # Get the last N candles
            # If we have fewer than N, return what we have
            available = min(len(data), count)
            start_idx = len(data) - available

            candles = []
            for i in range(start_idx, len(data)):
                row = data.iloc[i]

                candles.append(MarketData(
                    time=datetime.fromtimestamp(row.name.timestamp()),
                    symbol=symbol,
                    interval="1m",
                    open=Decimal(str(row['Open'])),
                    high=Decimal(str(row['High'])),
                    low=Decimal(str(row['Low'])),
                    close=Decimal(str(row['Close'])),
                    volume=int(row['Volume']) if 'Volume' in row and row['Volume'] else 0
                ))

            return candles

        return await loop.run_in_executor(None, _fetch)

    async def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> List[MarketData]:
        """
        Fetch historical data for backfill

        Note: YFree API limits:
        - Intraday data: Last 60-730 days depending on interval
        - Daily data: Much longer history available
        - For 1m data, typically last 60 days on free tier

        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime

        Returns:
            List of MarketData, oldest to newest
        """
        loop = asyncio.get_event_loop()

        def _fetch():
            ticker = self._tickers.get(symbol)
            if not ticker:
                raise ValueError(f"Symbol {symbol} not initialized")

            data = ticker.history(
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d'),
                interval="1m"
            )

            if data is None or len(data) == 0:
                return []

            candles = []
            for timestamp, row in data.iterrows():
                candles.append(MarketData(
                    time=datetime.fromtimestamp(timestamp.timestamp()),
                    symbol=symbol,
                    interval="1m",
                    open=Decimal(str(row['Open'])),
                    high=Decimal(str(row['High'])),
                    low=Decimal(str(row['Low'])),
                    close=Decimal(str(row['Close'])),
                    volume=int(row['Volume']) if 'Volume' in row and row['Volume'] else 0
                ))

            return candles

        return await loop.run_in_executor(None, _fetch)

    async def fetch_historical_chunked(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        chunk_days: int = 7
    ) -> List[MarketData]:
        """
        Fetch historical data in chunks to work around API limits

        YFinance limits free API to ~60 days of 1m data.
        This method chunks the request into smaller periods.

        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime
            chunk_days: Days per chunk (default: 7)

        Returns:
            Combined list of MarketData from all chunks
        """
        all_candles = []
        current_start = start

        while current_start < end:
            chunk_end = min(
                current_start + timedelta(days=chunk_days),
                end
            )

            logger.info(
                "fetching_chunk",
                symbol=symbol,
                chunk_start=current_start.strftime('%Y-%m-%d'),
                chunk_end=chunk_end.strftime('%Y-%m-%d')
            )

            candles = await self.fetch_historical(symbol, current_start, chunk_end)
            all_candles.extend(candles)

            # Move to next chunk
            current_start = chunk_end + timedelta(minutes=1)

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        logger.info(
            "chunked_fetch_complete",
            symbol=symbol,
            total_candles=len(all_candles)
        )

        return all_candles

    async def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol is valid"""
        try:
            loop = asyncio.get_event_loop()

            def _validate():
                yf_symbol = symbol if '=X' in symbol else f"{symbol}=X"
                ticker = yf.Ticker(yf_symbol)
                info = ticker.info
                return bool(info.get('regularMarketPrice') or info.get('previousClose'))

            return await loop.run_in_executor(None, _validate)
        except Exception:
            return False

    async def get_available_intervals(self, symbol: str) -> List[str]:
        """
        Get available intervals for a symbol

        Returns intervals that actually return data for this symbol.
        """
        available = []

        for interval in self.supported_intervals:
            try:
                ticker = self._tickers.get(symbol)
                if ticker:
                    data = ticker.history(period="5d", interval=interval)
                    if data is not None and len(data) > 0:
                        available.append(interval)
            except Exception:
                pass

        return available
