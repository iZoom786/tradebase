"""
Abstract repository interface for database operations
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from services.ingestion.models import MarketData


class Repository(ABC):
    """
    Abstract base repository for market data storage

    All database implementations must implement these core operations.
    Uses async/await pattern for non-blocking database operations.
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish database connection pool

        Should be called before any other operations.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close database connection pool

        Should be called during shutdown.
        """
        pass

    @abstractmethod
    async def upsert(self, data: MarketData) -> None:
        """
        Insert or update market data

        Uses ON CONFLICT to handle duplicate timestamps gracefully.

        Args:
            data: MarketData instance to store
        """
        pass

    @abstractmethod
    async def query_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m"
    ) -> List[MarketData]:
        """
        Query market data for a time range

        Args:
            symbol: Trading symbol
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            interval: Time interval (default: "1m")

        Returns:
            List of MarketData points, ordered by time ascending
        """
        pass

    @abstractmethod
    async def get_latest(
        self,
        symbol: str,
        interval: str = "1m"
    ) -> Optional[MarketData]:
        """
        Get the most recent data point for a symbol

        Args:
            symbol: Trading symbol
            interval: Time interval

        Returns:
            Latest MarketData or None if no data exists
        """
        pass

    @abstractmethod
    async def execute(self, sql: str, *args) -> None:
        """
        Execute arbitrary SQL

        Used for migrations, custom queries, etc.

        Args:
            sql: SQL query string
            *args: Query parameters
        """
        pass

    @abstractmethod
    async def fetchone(self, sql: str, *args) -> Optional[dict]:
        """
        Fetch single row from SQL query

        Args:
            sql: SQL query string
            *args: Query parameters

        Returns:
            Row as dict or None
        """
        pass

    @abstractmethod
    async def fetchall(self, sql: str, *args) -> List[dict]:
        """
        Fetch all rows from SQL query

        Args:
            sql: SQL query string
            *args: Query parameters

        Returns:
            List of rows as dicts
        """
        pass
