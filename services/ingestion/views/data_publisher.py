"""
NATS data publisher - publishes market data to NATS subjects
"""

import json
import logging
from typing import Optional
from datetime import datetime

from ..models import MarketData

logger = logging.getLogger(__name__)


class DataPublisher:
    """
    Publish market data to NATS

    Follows the subject naming convention:
    tradebase.<asset_class>.<symbol>.<stream_type>.<interval>
    """

    def __init__(self, nats_client):
        """
        Initialize publisher

        Args:
            nats_client: Connected NATS client instance
        """
        self.nc = nats_client

    async def publish_raw(self, data: MarketData) -> None:
        """
        Publish raw OHLCV data

        Subject: tradebase.{asset_class}.{symbol}.raw.{interval}
        """
        asset_class = self._get_asset_class(data.symbol)
        subject = f"tradebase.{asset_class}.{data.symbol.lower()}.raw.{data.interval.lower()}"

        payload = {
            "timestamp": data.time.isoformat(),
            "symbol": data.symbol,
            "interval": data.interval,
            "open": float(data.open),
            "high": float(data.high),
            "low": float(data.low),
            "close": float(data.close),
            "volume": data.volume
        }

        await self.nc.publish(subject, json.dumps(payload).encode())
        logger.info("published_raw", subject=subject, time=data.time, symbol=data.symbol)

    async def publish_features(
        self,
        symbol: str,
        interval: str,
        features: dict,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Publish computed features

        Subject: tradebase.{asset_class}.{symbol}.features.{interval}
        """
        asset_class = self._get_asset_class(symbol)
        subject = f"tradebase.{asset_class}.{symbol.lower()}.features.{interval.lower()}"

        payload = {
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "symbol": symbol,
            "interval": interval,
            "features": features
        }

        await self.nc.publish(subject, json.dumps(payload).encode())
        logger.info("published_features", subject=subject, symbol=symbol)

    async def publish_prediction(
        self,
        symbol: str,
        prediction: dict,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Publish ML prediction

        Subject: tradebase.{asset_class}.{symbol}.prediction.{interval}
        """
        asset_class = self._get_asset_class(symbol)
        subject = f"tradebase.{asset_class}.{symbol.lower()}.prediction.1m"

        payload = {
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "symbol": symbol,
            "prediction": prediction
        }

        await self.nc.publish(subject, json.dumps(payload).encode())
        logger.info("published_prediction", subject=subject, symbol=symbol)

    def _get_asset_class(self, symbol: str) -> str:
        """
        Determine asset class from symbol

        Simple heuristic:
        - 6 characters (3 base + 3 quote) = forex
        - Everything else = other
        """
        if len(symbol) == 6 and symbol[:3].isalpha() and symbol[3:].isalpha():
            return "forex"
        elif any(x in symbol.upper() for x in ["BTC", "ETH", "SOL"]):
            return "crypto"
        return "other"
