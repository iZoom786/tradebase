"""
YFinance data provider implementation
"""

import asyncio
from typing import List
from datetime import datetime, timedelta
from decimal import Decimal

import yfinance as yf

from .base import DataProvider
from ..models import MarketData


class YFinanceProvider(DataProvider):
    """
    YFinance provider for forex, crypto, and stock data

    IMPORTANT: Data Strategy
    ------------------------
    - Only 1-minute (1m) candles are fetched from YFinance
    - Fetches 3 recent candles every minute to ensure we get the completed one
    - Higher timeframes (5m, 15m, 30m, 1h, 4h, 1d, 1w) are generated via TimescaleDB
     materialized views with auto-refresh policies
    - This reduces API calls and ensures data consistency across timeframes

    Free API with good coverage for major forex pairs.
    """

    def __init__(self, symbols: List[str]):
        """
        Initialize YFinance provider

        Args:
            symbols: List of trading symbols (e.g., ['EURUSD=X', 'GBPUSD=X'])
        """
        self.symbols = symbols
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
        Fetch the most recent completed 1-minute candle

        Data Strategy:
        --------------
        - Fetches 3 recent candles from YFinance every minute
        - Uses the second-to-last (completed) candle
        - First candle is buffer, last is forming, second is complete
        - All higher timeframes derived from 1m via TimescaleDB materialized views

        Note: YFinance returns the current forming candle as well.
        We need the second-to-last row for the completed candle.
        """
        loop = asyncio.get_event_loop()

        def _fetch():
            ticker = self._tickers.get(symbol)
            if not ticker:
                raise ValueError(f"Symbol {symbol} not initialized")

            # Fetch last 3 minutes for buffer: [previous, completed, forming]
            # We use the second-to-last (completed) candle
            data = ticker.history(period="1d", interval="1m")

            if data is None or len(data) < 2:
                raise ValueError(f"Insufficient data for {symbol}")

            # Get the second-to-last (completed) candle
            # Last candle is still forming, second one is complete
            latest = data.iloc[-2]

            return MarketData(
                time=datetime.fromtimestamp(latest.name.timestamp()),
                symbol=symbol,
                interval="1m",
                open=Decimal(str(latest['Open'])),
                high=Decimal(str(latest['High'])),
                low=Decimal(str(latest['Low'])),
                close=Decimal(str(latest['Close'])),
                volume=int(latest['Volume']) if 'Volume' in latest else 0
            )

        return await loop.run_in_executor(None, _fetch)

    async def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> List[MarketData]:
        """
        Fetch historical data for backfill

        Note: YFinance limits historical data retrieval.
        For intraday data, typically last 60 days.
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
                    volume=int(row['Volume']) if 'Volume' in row else 0
                ))

            return candles

        return await loop.run_in_executor(None, _fetch)

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
