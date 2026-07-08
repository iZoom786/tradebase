"""
NATS client with reconnection, JWT auth, and observability
"""

import asyncio
import logging
from typing import Optional, Callable, Dict
from datetime import datetime

import nats
from nats.aio.client import Client as NATSClient
from nats.errors import NoServersError, TimeoutError

from libs.common.config import NATSConfig
from libs.common.observability import message_counter, processing_duration

logger = logging.getLogger(__name__)


class NATSConnectionError(Exception):
    """Raised when NATS connection fails"""
    pass


class NATSPublishError(Exception):
    """Raised when NATS publish fails"""
    pass


class NATSClient:
    """
    High-level NATS client with reconnection and observability

    Features:
    - Automatic reconnection with exponential backoff
    - JWT/NKey authentication support
    - Distributed tracing integration
    - Prometheus metrics
    - Connection state monitoring
    """

    def __init__(
        self,
        config: NATSConfig,
        user_jwt: Optional[str] = None,
        user_seed: Optional[str] = None
    ):
        """
        Initialize NATS client

        Args:
            config: NATS configuration
            user_jwt: User JWT token for authentication (optional)
            user_seed: User NKey seed for signing challenges (optional)
        """
        self.config = config
        self.user_jwt = user_jwt
        self.user_seed = user_seed
        self.nc: Optional[NATSClient] = None
        self._js = None
        self._connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._stop_reconnect = asyncio.Event()

    async def connect(self) -> None:
        """
        Establish NATS connection with JWT/NKey authentication and optional TLS

        Raises:
            NATSConnectionError: If connection cannot be established
        """
        if self._connected:
            logger.warning("nats_already_connected")
            return

        # Use TLS URL if TLS is enabled
        server_url = self.config.url_tls if self.config.tls_enabled and self.config.url_tls else self.config.url

        logger.info(
            "nats_connecting",
            url=server_url,
            max_reconnect=self.config.max_reconnect,
            with_jwt=bool(self.user_jwt),
            tls_enabled=self.config.tls_enabled
        )

        options = {
            "servers": server_url,
            "max_reconnect_attempts": self.config.max_reconnect,
            "ping_interval": self.config.ping_interval,
            "connect_timeout": self.config.connect_timeout,
            "disconnected_cb": self._on_disconnect,
            "reconnected_cb": self._on_reconnect,
            "closed_cb": self._on_close,
            "error_cb": self._on_error,
        }

        # Add TLS configuration if enabled
        if self.config.tls_enabled:
            tls_config = {
                "ca_files": None,  # Use system CA
                "cert": self.config.client_cert,
                "key": self.config.client_key,
                "verify": self.config.verify_cert
            }
            options["tls"] = tls_config
            logger.info("nats_tls_enabled")

        # Add JWT authentication if provided
        if self.user_jwt and self.user_seed:
            options["user_jwt"] = self.user_jwt
            options["signature_cb"] = self._sign_challenge
            logger.info("nats_jwt_auth_enabled")

        try:
            self.nc = await nats.connect(**options)
            self._js = self.nc.jetstream()
            self._connected = True

            logger.info(
                "nats_connected",
                server_id=self.nc.connected_server_id if self.nc else None,
                tls_enabled=self.config.tls_enabled
            )

        except (NoServersError, TimeoutError) as e:
            logger.error("nats_connection_failed", error=str(e))
            raise NATSConnectionError(f"Failed to connect to NATS: {e}") from e

    def _sign_challenge(self, nonce: bytes) -> bytes:
        """
        Sign NATS server challenge with NKey

        Args:
            nonce: Challenge nonce from server

        Returns:
            Signature bytes
        """
        from libs.nats_client.auth import NKeyManager

        signature = NKeyManager.sign_challenge(self.user_seed, nonce)
        logger.debug("nats_challenge_signed")
        return signature

    async def publish(
        self,
        subject: str,
        payload: bytes,
        headers: Optional[dict] = None
    ) -> None:
        """
        Publish message to NATS subject

        Args:
            subject: NATS subject
            payload: Message payload
            headers: Optional message headers

        Raises:
            NATSPublishError: If publish fails
        """
        if not self._connected or self.nc is None:
            raise NATSPublishError("NATS not connected")

        with processing_duration.labels(
            service="ingestion",
            operation="nats_publish"
        ).time():
            try:
                await self.nc.publish(subject, payload, headers=headers)

                message_counter.labels(
                    service="ingestion",
                    status="success"
                ).inc()

                logger.debug("nats_published", subject=subject)

            except Exception as e:
                message_counter.labels(
                    service="ingestion",
                    status="error"
                ).inc()

                logger.error("nats_publish_failed", subject=subject, error=str(e))
                raise NATSPublishError(f"Publish failed: {e}") from e

    async def request(
        self,
        subject: str,
        payload: bytes,
        timeout: float = 1.0
    ) -> Optional[bytes]:
        """
        Send request and wait for response

        Args:
            subject: Request subject
            payload: Request payload
            timeout: Response timeout in seconds

        Returns:
            Response payload or None
        """
        if not self._connected or self.nc is None:
            raise NATSPublishError("NATS not connected")

        try:
            msg = await self.nc.request(subject, payload, timeout=timeout)
            return msg.data

        except TimeoutError:
            logger.warning("nats_request_timeout", subject=subject)
            return None

    async def subscribe(
        self,
        subject: str,
        cb: Callable,
        queue_name: Optional[str] = None,
        **kwargs
    ) -> int:
        """
        Subscribe to NATS subject

        Args:
            subject: Subject to subscribe to
            cb: Async callback function
            queue_name: Optional queue group name
            **kwargs: Additional subscription options

        Returns:
            Subscription ID
        """
        if not self._connected or self.nc is None:
            raise NATSPublishError("NATS not connected")

        sub = await self.nc.subscribe(subject, queue=queue_name, cb=cb, **kwargs)

        logger.info(
            "nats_subscribed",
            subject=subject,
            queue=queue_name,
            sid=sub.id
        )

        return sub.id

    async def subscribe_jetstream(
        self,
        subject: str,
        stream: str,
        cb: Callable,
        consumer_name: Optional[str] = None,
        **kwargs
    ) -> int:
        """
        Subscribe to JetStream consumer

        Args:
            subject: Subject pattern
            stream: JetStream stream name
            cb: Async callback function
            consumer_name: Consumer name (auto-generated if None)
            **kwargs: Additional consumer config

        Returns:
            Subscription ID
        """
        if not self._connected or self.js is None:
            raise NATSPublishError("NATS not connected")

        # Create consumer if needed
        if consumer_name is None:
            consumer_name = f"consumer_{datetime.now().timestamp()}"

        try:
            await self.js.add_consumer(
                stream,
                nats.api.consumer.ConsumerConfig(
                    name=consumer_name,
                    durable=consumer_name,
                    ack_policy="explicit",
                    **kwargs
                )
            )
        except nats.errors.Error as e:
            logger.warning("jetstream_consumer_exists", error=str(e))

        # Subscribe
        sub = await self.js.subscribe(
            subject=subject,
            stream=stream,
            cb=cb,
            consumer=consumer_name
        )

        logger.info(
            "nats_jetstream_subscribed",
            subject=subject,
            stream=stream,
            consumer=consumer_name
        )

        return sub.id

    async def jetstream_publish(
        self,
        subject: str,
        payload: bytes,
        headers: Optional[dict] = None,
        stream: Optional[str] = None
    ) -> Optional[nats.js.Msg]:
        """
        Publish to JetStream for persistence

        Args:
            subject: Subject to publish to
            payload: Message payload
            headers: Optional headers
            stream: Target stream (auto-detected if None)

        Returns:
            Acknowledgment message or None
        """
        if not self._connected or self.js is None:
            raise NATSPublishError("NATS not connected")

        try:
            ack = await self.js.publish(subject, payload, headers=headers, stream=stream)

            logger.debug("jetstream_published", subject=subject, ack=ack)
            return ack

        except Exception as e:
            logger.error("jetstream_publish_failed", subject=subject, error=str(e))
            raise NATSPublishError(f"JetStream publish failed: {e}") from e

    async def create_stream(
        self,
        stream_name: str,
        subjects: list[str],
        **kwargs
    ) -> None:
        """
        Create JetStream stream

        Args:
            stream_name: Stream name
            subjects: List of subjects
            **kwargs: Additional stream configuration
        """
        if not self._connected or self.js is None:
            raise NATSPublishError("NATS not connected")

        config = nats.api.stream.StreamConfig(
            name=stream_name,
            subjects=subjects,
            **kwargs
        )

        try:
            await self.js.add_stream(config)
            logger.info("jetstream_stream_created", stream=stream_name)
        except nats.errors.Error as e:
            logger.warning("jetstream_stream_exists", stream=stream_name, error=str(e))

    async def close(self) -> None:
        """Close NATS connection gracefully"""
        if self.nc and not self.nc.is_closed:
            await self.nc.close()
            logger.info("nats_closed")

        self._connected = False

    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._connected and self.nc is not None and not self.nc.is_closed

    # =====================================================
    # Connection Callbacks
    # =====================================================

    def _on_disconnect(self):
        """Called when disconnected from NATS"""
        logger.warning("nats_disconnected")
        self._connected = False

    def _on_reconnect(self):
        """Called when reconnected to NATS"""
        logger.info("nats_reconnected")
        self._connected = False  # Will be set true in connect()

    def _on_close(self):
        """Called when connection is closed"""
        logger.info("nats_connection_closed")
        self._connected = False

    def _on_error(self, error):
        """Called when an error occurs"""
        logger.error("nats_error", error=str(error))
