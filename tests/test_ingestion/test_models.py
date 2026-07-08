"""
Tests for ingestion data models
"""

import pytest
from datetime import datetime
from decimal import Decimal

from services.ingestion.models import MarketData


class TestMarketData:
    """Test MarketData model"""

    def test_creation(self):
        """Test creating market data"""
        data = MarketData(
            time=datetime(2026, 7, 6, 13, 30, 0),
            symbol="EURUSD",
            interval="1m",
            open=Decimal("1.08210"),
            high=Decimal("1.08250"),
            low=Decimal("1.08205"),
            close=Decimal("1.08240"),
            volume=1000,
        )

        assert data.symbol == "EURUSD"
        assert data.interval == "1m"
        assert data.close == Decimal("1.08240")

    def test_to_dict(self):
        """Test serialization to dictionary"""
        data = MarketData(
            time=datetime(2026, 7, 6, 13, 30, 0),
            symbol="EURUSD",
            interval="1m",
            open=Decimal("1.08210"),
            high=Decimal("1.08250"),
            low=Decimal("1.08205"),
            close=Decimal("1.08240"),
            volume=1000,
        )

        result = data.to_dict()

        assert result["symbol"] == "EURUSD"
        assert result["open"] == 1.08210
        assert result["close"] == 1.08240
        assert "timestamp" in result

    def test_from_dict(self):
        """Test deserialization from dictionary"""
        input_data = {
            "timestamp": "2026-07-06T13:30:00",
            "symbol": "EURUSD",
            "interval": "1m",
            "open": 1.08210,
            "high": 1.08250,
            "low": 1.08205,
            "close": 1.08240,
            "volume": 1000,
        }

        data = MarketData.from_dict(input_data)

        assert data.symbol == "EURUSD"
        assert data.close == Decimal("1.08240")
        assert isinstance(data.close, Decimal)

    def test_immutability(self):
        """Test that MarketData is immutable"""
        data = MarketData(
            time=datetime(2026, 7, 6, 13, 30, 0),
            symbol="EURUSD",
            interval="1m",
            open=Decimal("1.08210"),
            high=Decimal("1.08250"),
            low=Decimal("1.08205"),
            close=Decimal("1.08240"),
            volume=1000,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            data.symbol = "GBPUSD"
