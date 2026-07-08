"""
Tests for NATS client JWT/NKey authentication
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from libs.nats_client.client import NATSClient, NATSConnectionError
from libs.nats_client.auth import NATSAuthClient
from libs.common.config import NATSConfig


class TestNATSClientAuth:
    """Test NATS client authentication"""

    @pytest.fixture
    def nats_config(self):
        """Create NATS config"""
        return NATSConfig()

    @pytest.fixture
    def auth_credentials(self):
        """Create JWT and seed for testing"""
        auth_client = NATSAuthClient()
        jwt_token, seed, _ = auth_client.create_user(
            user_id="test_user",
            tier="basic"
        )
        return jwt_token, seed

    @pytest.mark.asyncio
    async def test_connect_without_auth(self, nats_config):
        """Test connecting without JWT authentication"""
        client = NATSClient(nats_config)

        with patch('nats.connect') as mock_connect:
            mock_nc = AsyncMock()
            mock_nc.connected_server_id = "test_server"
            mock_nc.jetstream = MagicMock(return_value=AsyncMock())

            mock_connect.return_value = mock_nc

            await client.connect()

            # Verify connect was called without JWT options
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args[1]
            assert "user_jwt" not in call_kwargs
            assert "signature_cb" not in call_kwargs

    @pytest.mark.asyncio
    async def test_connect_with_jwt_auth(self, nats_config, auth_credentials):
        """Test connecting with JWT authentication"""
        jwt_token, seed = auth_credentials
        client = NATSClient(
            nats_config,
            user_jwt=jwt_token,
            user_seed=seed
        )

        with patch('nats.connect') as mock_connect:
            mock_nc = AsyncMock()
            mock_nc.connected_server_id = "test_server"
            mock_nc.jetstream = MagicMock(return_value=AsyncMock())

            mock_connect.return_value = mock_nc

            await client.connect()

            # Verify connect was called with JWT options
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs["user_jwt"] == jwt_token
            assert "signature_cb" in call_kwargs

    @pytest.mark.asyncio
    async def test_sign_challenge(self, nats_config, auth_credentials):
        """Test challenge signing callback"""
        jwt_token, seed = auth_credentials
        client = NATSClient(
            nats_config,
            user_jwt=jwt_token,
            user_seed=seed
        )

        # Test signing a challenge
        challenge = b"test_server_nonce"
        signature = client._sign_challenge(challenge)

        assert signature is not None
        assert isinstance(signature, bytes)

    @pytest.mark.asyncio
    async def test_connection_failure(self, nats_config):
        """Test connection failure handling"""
        client = NATSClient(nats_config)

        with patch('nats.connect', side_effect=Exception("Connection refused")):
            with pytest.raises(NATSConnectionError):
                await client.connect()

    @pytest.mark.asyncio
    async def test_already_connected(self, nats_config):
        """Test connecting when already connected"""
        client = NATSClient(nats_config)

        with patch('nats.connect') as mock_connect:
            mock_nc = AsyncMock()
            mock_nc.connected_server_id = "test_server"
            mock_nc.jetstream = MagicMock(return_value=AsyncMock())
            mock_nc.is_closed = False

            mock_connect.return_value = mock_nc

            await client.connect()
            client._connected = True

            # Try connecting again
            await client.connect()

            # Should not call connect again
            assert mock_connect.call_count == 1


class TestNATSClientAuthenticatedOperations:
    """Test NATS operations with authentication"""

    @pytest.fixture
    async def authenticated_client(self):
        """Create an authenticated NATS client"""
        config = NATSConfig()
        auth_client = NATSAuthClient()
        jwt_token, seed, _ = auth_client.create_user(
            user_id="test_user",
            tier="premium"
        )

        client = NATSClient(
            config,
            user_jwt=jwt_token,
            user_seed=seed
        )

        # Mock the actual NATS connection
        with patch('nats.connect') as mock_connect:
            mock_nc = AsyncMock()
            mock_nc.connected_server_id = "test_server"
            mock_nc.is_closed = False
            mock_nc.jetstream = MagicMock(return_value=AsyncMock())
            mock_nc.publish = AsyncMock()

            mock_connect.return_value = mock_nc

            await client.connect()
            return client

    @pytest.mark.asyncio
    async def test_publish_with_auth(self, authenticated_client):
        """Test publishing with JWT authentication"""
        await authenticated_client.publish(
            subject="tradebase.forex.eurusd.raw.1m",
            payload=b'{"test": "data"}'
        )

        # Verify publish was called
        assert authenticated_client.nc.publish.called

    @pytest.mark.asyncio
    async def test_subscribe_with_auth(self, authenticated_client):
        """Test subscribing with JWT authentication"""
        async def callback(msg):
            pass

        with patch.object(authenticated_client.nc, 'subscribe') as mock_sub:
            mock_sub.return_value = MagicMock(id=123)

            await authenticated_client.subscribe(
                subject="tradebase.forex.>",
                cb=callback
            )

            # Verify subscribe was called
            mock_sub.assert_called_once()

    @pytest.mark.asyncio
    async def test_jetstream_operations_with_auth(self, authenticated_client):
        """Test JetStream operations with JWT authentication"""
        # Test creating a stream
        await authenticated_client.create_stream(
            stream_name="test_stream",
            subjects=["tradebase.forex.>"]
        )

        # Verify stream creation was attempted
        assert authenticated_client.js.add_stream.called

    @pytest.mark.asyncio
    async def test_close_connection(self, authenticated_client):
        """Test closing authenticated connection"""
        await authenticated_client.close()

        # Verify connection was closed
        assert authenticated_client.nc.close.called
        assert authenticated_client._connected is False
