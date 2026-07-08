"""
Pytest configuration and fixtures
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator

from services.ingestion.models import MarketData
from libs.common.config import DatabaseConfig, NATSConfig


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_market_data() -> MarketData:
    """Sample market data for testing"""
    return MarketData(
        time=datetime(2026, 7, 6, 13, 30, 0),
        symbol="EURUSD",
        interval="1m",
        open=Decimal("1.08210"),
        high=Decimal("1.08250"),
        low=Decimal("1.08205"),
        close=Decimal("1.08240"),
        volume=1000,
    )


@pytest.fixture
def sample_market_data_list() -> list[MarketData]:
    """Generate list of market data points"""
    base_time = datetime(2026, 7, 6, 13, 0, 0)
    data_points = []

    for i in range(100):
        time = base_time + timedelta(minutes=i)
        base_price = Decimal("1.08200")
        offset = Decimal(str(i * 0.00010))

        data_points.append(MarketData(
            time=time,
            symbol="EURUSD",
            interval="1m",
            open=base_price + offset,
            high=base_price + offset + Decimal("0.00020"),
            low=base_price + offset - Decimal("0.00010"),
            close=base_price + offset + Decimal("0.00015"),
            volume=1000 + i * 10,
        ))

    return data_points


@pytest.fixture
async def database_config() -> DatabaseConfig:
    """Database configuration for testing"""
    return DatabaseConfig(
        host="localhost",
        port=5432,
        database="tradebase_test",
        user="postgres",
        password="postgres",
        pool_size=5,
    )


@pytest.fixture
async def nats_config() -> NATSConfig:
    """NATS configuration for testing"""
    return NATSConfig(
        url="nats://localhost:4222",
        max_reconnect=3,
        ping_interval=30,
    )
