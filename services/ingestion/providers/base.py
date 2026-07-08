"""
Abstract base class for data providers
"""

from abc import ABC, abstractmethod
from typing import List
from datetime import datetime

from ..models import MarketData


class DataProvider(ABC):
    """
    Abstract base for all market data providers

    All providers must implement:
    - fetch_latest_candle: Get most recent completed candle
    - fetch_historical: Backfill historical data
    - validate_symbol: Check if symbol is supported
    """

    @abstractmethod
    async def fetch_latest_candle(self, symbol: str) -> MarketData:
        """
        Get the most recent completed candle

        Args:
            symbol: Trading symbol (e.g., 'EURUSD')

        Returns:
            MarketData for the completed candle
        """
        pass

    @abstractmethod
    async def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> List[MarketData]:
        """
        Backfill historical data

        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime

        Returns:
            List of MarketData points
        """
        pass

    @abstractmethod
    async def validate_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is supported by this provider

        Args:
            symbol: Trading symbol to validate

        Returns:
            True if symbol is valid and supported
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier"""
        pass

    @property
    @abstractmethod
    def supported_intervals(self) -> List[str]:
        """List of supported time intervals"""
        pass
