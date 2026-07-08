"""
Comprehensive test for JWT authentication flow with NATS

Tests:
1. JWT generation with different tiers
2. Permission checking for different tiers
3. Subject pattern matching
4. JWT validation
5. NATS resolver endpoint
"""

import asyncio
import pytest
from datetime import datetime, timedelta

from libs.nats_client.auth import (
    NATSAuthClient,
    NATSJWTManager,
    NKeyManager,
    Tier,
    KeyType
)
from libs.nats_client.client import NATSClient, NATSConnectionError
from libs.common.config import NATSConfig


class TestJWTGeneration:
    """Test JWT generation with different tiers"""

    def test_generate_user_jwt_trial(self):
        """Test generating JWT for trial tier"""
        auth_client = NATSAuthClient()

        user_id = "trial_user_123"
        jwt_token, seed, public_key = auth_client.create_user(
            user_id=user_id,
            tier=Tier.TRIAL.value,
            expires_hours=24
        )

        assert jwt_token is not None
        assert seed is not None
        assert public_key is not None

        # Verify JWT can be decoded
        payload = auth_client.validate_user_jwt(jwt_token)
        assert payload["sub"] == user_id
        assert "trial" in payload.get("tags", [])

    def test_generate_user_jwt_basic(self):
        """Test generating JWT for basic tier"""
        auth_client = NATSAuthClient()

        user_id = "basic_user_123"
        jwt_token, seed, public_key = auth_client.create_user(
            user_id=user_id,
            tier=Tier.BASIC.value,
            expires_hours=720
        )

        payload = auth_client.validate_user_jwt(jwt_token)
        assert payload["sub"] == user_id
        assert "basic" in payload.get("tags", [])

    def test_generate_user_jwt_premium(self):
        """Test generating JWT for premium tier"""
        auth_client = NATSAuthClient()

        user_id = "premium_user_123"
        jwt_token, seed, public_key = auth_client.create_user(
            user_id=user_id,
            tier=Tier.PREMIUM.value,
            expires_hours=720
        )

        payload = auth_client.validate_user_jwt(jwt_token)
        assert payload["sub"] == user_id
        assert "premium" in payload.get("tags", [])

    def test_invalid_tier_raises_error(self):
        """Test that invalid tier raises ValueError"""
        jwt_manager = NATSJWTManager()

        with pytest.raises(ValueError, match="Invalid tier"):
            jwt_manager.generate_user_jwt(
                user_id="user_123",
                tier="invalid_tier",
                public_key="test_key"
            )


class TestPermissions:
    """Test tier-based permissions"""

    @pytest.fixture
    def auth_client(self):
        """Create auth client with test issuer seed"""
        return NATSAuthClient()

    @pytest.fixture
    def trial_jwt(self, auth_client):
        """Create trial JWT"""
        jwt_token, _, _ = auth_client.create_user(
            user_id="trial_user",
            tier=Tier.TRIAL.value
        )
        return jwt_token

    @pytest.fixture
    def basic_jwt(self, auth_client):
        """Create basic JWT"""
        jwt_token, _, _ = auth_client.create_user(
            user_id="basic_user",
            tier=Tier.BASIC.value
        )
        return jwt_token

    @pytest.fixture
    def premium_jwt(self, auth_client):
        """Create premium JWT"""
        jwt_token, _, _ = auth_client.create_user(
            user_id="premium_user",
            tier=Tier.PREMIUM.value
        )
        return jwt_token

    def test_trial_permissions(self, auth_client, trial_jwt):
        """Test trial user can only access paper trading"""
        # Should allow paper trading
        assert auth_client.check_permission(
            trial_jwt,
            "tradebase.public.papertrading.eurusd",
            "sub"
        ) is True

        # Should deny raw data
        assert auth_client.check_permission(
            trial_jwt,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        ) is False

        # Should deny predictions
        assert auth_client.check_permission(
            trial_jwt,
            "tradebase.forex.eurusd.prediction.1m",
            "sub"
        ) is False

        # Should deny all publish
        assert auth_client.check_permission(
            trial_jwt,
            "tradebase.public.papertrading.eurusd",
            "pub"
        ) is False

    def test_basic_permissions(self, auth_client, basic_jwt):
        """Test basic user can access raw data and features"""
        # Should allow raw data
        assert auth_client.check_permission(
            basic_jwt,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        ) is True

        # Should allow features
        assert auth_client.check_permission(
            basic_jwt,
            "tradebase.forex.eurusd.features.1m",
            "sub"
        ) is True

        # Should deny predictions
        assert auth_client.check_permission(
            basic_jwt,
            "tradebase.forex.eurusd.prediction.1m",
            "sub"
        ) is False

        # Should deny paper trading (different tier)
        assert auth_client.check_permission(
            basic_jwt,
            "tradebase.public.papertrading.eurusd",
            "sub"
        ) is False

    def test_premium_permissions(self, auth_client, premium_jwt):
        """Test premium user can access everything"""
        # Should allow raw data
        assert auth_client.check_permission(
            premium_jwt,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        ) is True

        # Should allow features
        assert auth_client.check_permission(
            premium_jwt,
            "tradebase.forex.eurusd.features.1m",
            "sub"
        ) is True

        # Should allow predictions
        assert auth_client.check_permission(
            premium_jwt,
            "tradebase.forex.eurusd.prediction.1m",
            "sub"
        ) is True

        # Should still deny publish
        assert auth_client.check_permission(
            premium_jwt,
            "tradebase.forex.eurusd.raw.1m",
            "pub"
        ) is False


class TestSubjectMatching:
    """Test NATS subject pattern matching"""

    def test_wildcard_single(self):
        """Test single token wildcard (*)"""
        jwt_manager = NATSJWTManager()

        # * matches any single token
        assert jwt_manager._match_subject(
            "tradebase.forex.*.raw.1m",
            "tradebase.forex.eurusd.raw.1m"
        ) is True

        assert jwt_manager._match_subject(
            "tradebase.forex.*.raw.1m",
            "tradebase.forex.gbpusd.raw.1m"
        ) is True

        # * doesn't match multiple tokens
        assert jwt_manager._match_subject(
            "tradebase.*.raw.1m",
            "tradebase.forex.major.raw.1m"
        ) is False

    def test_wildcard_multi(self):
        """Test multi-token wildcard (>)"""
        jwt_manager = NATSJWTManager()

        # > matches zero or more tokens
        assert jwt_manager._match_subject(
            "tradebase.>",
            "tradebase.forex.eurusd.raw.1m"
        ) is True

        assert jwt_manager._match_subject(
            "tradebase.>",
            "tradebase.public.papertrading"
        ) is True

        assert jwt_manager._match_subject(
            "tradebase.>",
            "tradebase.a.b.c.d.e.f"
        ) is True

    def test_exact_match(self):
        """Test exact subject match"""
        jwt_manager = NATSJWTManager()

        assert jwt_manager._match_subject(
            "tradebase.forex.eurusd.raw.1m",
            "tradebase.forex.eurusd.raw.1m"
        ) is True

        assert jwt_manager._match_subject(
            "tradebase.forex.eurusd.raw.1m",
            "tradebase.forex.eurusd.raw.5m"
        ) is False

    def test_case_sensitive(self):
        """Test that matching is case sensitive"""
        jwt_manager = NATSJWTManager()

        assert jwt_manager._match_subject(
            "tradebase.forex.EURUSD.raw.1m",
            "tradebase.forex.eurusd.raw.1m"
        ) is False


class TestJWTValidation:
    """Test JWT validation and expiration"""

    def test_valid_jwt(self):
        """Test validating a valid JWT"""
        auth_client = NATSAuthClient()

        jwt_token, _, _ = auth_client.create_user(
            user_id="user_123",
            tier=Tier.BASIC.value
        )

        payload = auth_client.validate_user_jwt(jwt_token)
        assert payload is not None
        assert payload["sub"] == "user_123"

    def test_jwt_expiration(self):
        """Test JWT expiration"""
        auth_client = NATSAuthClient()

        # Create JWT that expires in 1 second
        jwt_token, _, _ = auth_client.create_user(
            user_id="user_123",
            tier=Tier.BASIC.value,
            expires_hours=0  # Expires immediately
        )

        # Wait for expiration
        import time
        time.sleep(2)

        # Should raise error for expired token
        import jwt
        with pytest.raises(jwt.ExpiredSignatureError):
            auth_client.validate_user_jwt(jwt_token)

    def test_invalid_jwt(self):
        """Test validating an invalid JWT"""
        auth_client = NATSAuthClient()

        with pytest.raises(Exception):
            auth_client.validate_user_jwt("invalid.jwt.token")


class TestTierUpgrade:
    """Test tier upgrade functionality"""

    def test_upgrade_trial_to_basic(self):
        """Test upgrading from trial to basic"""
        auth_client = NATSAuthClient()

        # Create trial user
        trial_jwt, seed, public_key = auth_client.create_user(
            user_id="user_123",
            tier=Tier.TRIAL.value
        )

        # Upgrade to basic
        basic_jwt, new_seed, new_public_key = auth_client.upgrade_tier(
            user_id="user_123",
            old_jwt=trial_jwt,
            new_tier=Tier.BASIC.value,
            public_key=public_key
        )

        # Verify new JWT has basic tier
        payload = auth_client.validate_user_jwt(basic_jwt)
        assert "basic" in payload.get("tags", [])

        # Verify basic permissions work
        assert auth_client.check_permission(
            basic_jwt,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        ) is True

    def test_upgrade_basic_to_premium(self):
        """Test upgrading from basic to premium"""
        auth_client = NATSAuthClient()

        # Create basic user
        basic_jwt, seed, public_key = auth_client.create_user(
            user_id="user_456",
            tier=Tier.BASIC.value
        )

        # Upgrade to premium
        premium_jwt, _, _ = auth_client.upgrade_tier(
            user_id="user_456",
            old_jwt=basic_jwt,
            new_tier=Tier.PREMIUM.value,
            public_key=public_key
        )

        # Verify new JWT has premium tier
        payload = auth_client.validate_user_jwt(premium_jwt)
        assert "premium" in payload.get("tags", [])

        # Verify premium permissions work
        assert auth_client.check_permission(
            premium_jwt,
            "tradebase.forex.eurusd.prediction.1m",
            "sub"
        ) is True


class TestNATSConnectionWithJWT:
    """Test NATS connection with JWT authentication"""

    @pytest.mark.asyncio
    async def test_nats_connection_without_jwt(self):
        """Test NATS connection without JWT (system user)"""
        # This test requires NATS to be running
        # Skip if NATS is not available
        try:
            config = NATSConfig(
                url="nats://localhost:4223"  # Non-TLS port for development
            )

            client = NATSClient(config)
            await client.connect()
            assert client.is_connected() is True
            await client.close()

        except NATSConnectionError:
            pytest.skip("NATS not available")

    @pytest.mark.asyncio
    async def test_nats_connection_with_jwt(self):
        """Test NATS connection with JWT authentication"""
        # This test requires NATS with JWT auth to be running
        try:
            # Create user JWT
            auth_client = NATSAuthClient()
            jwt_token, seed, _ = auth_client.create_user(
                user_id="test_user",
                tier=Tier.BASIC.value
            )

            # Connect to NATS with JWT
            config = NATSConfig(
                url="nats://localhost:4223"
            )

            client = NATSClient(
                config=config,
                user_jwt=jwt_token,
                user_seed=seed
            )

            await client.connect()
            assert client.is_connected() is True
            await client.close()

        except NATSConnectionError:
            pytest.skip("NATS with JWT auth not available")


class TestNATSResolver:
    """Test NATS JWT resolver endpoint"""

    @pytest.mark.asyncio
    async def test_resolver_valid_jwt(self):
        """Test resolver with valid JWT"""
        # This test requires the subscription service to be running
        import httpx

        try:
            # Create test JWT
            auth_client = NATSAuthClient()
            jwt_token, _, _ = auth_client.create_user(
                user_id="resolver_test_user",
                tier=Tier.BASIC.value
            )

            # Call resolver endpoint
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8002/nats/resolver",
                    json={"token": jwt_token},
                    timeout=5.0
                )

                assert response.status_code == 200
                data = response.json()

                assert "sub" in data
                assert "nats" in data
                assert data["sub"] == "resolver_test_user"

        except httpx.ConnectError:
            pytest.skip("Subscription service not available")

    @pytest.mark.asyncio
    async def test_resolver_invalid_jwt(self):
        """Test resolver with invalid JWT"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8002/nats/resolver",
                    json={"token": "invalid.jwt.token"},
                    timeout=5.0
                )

                assert response.status_code == 200
                data = response.json()
                assert "error" in data

        except httpx.ConnectError:
            pytest.skip("Subscription service not available")


# Integration test helper
class JWTAuthTestHelper:
    """Helper class for JWT authentication testing"""

    @staticmethod
    def create_test_user(tier: str = "basic") -> tuple[str, str, str]:
        """Create a test user with JWT"""
        auth_client = NATSAuthClient()
        return auth_client.create_user(
            user_id=f"test_{tier}_{datetime.now().timestamp()}",
            tier=tier
        )

    @staticmethod
    def verify_permissions(jwt_token: str, allowed_subjects: list, denied_subjects: list):
        """Verify JWT grants expected permissions"""
        auth_client = NATSAuthClient()

        for subject in allowed_subjects:
            assert auth_client.check_permission(jwt_token, subject, "sub"), \
                f"Should allow: {subject}"

        for subject in denied_subjects:
            assert not auth_client.check_permission(jwt_token, subject, "sub"), \
                f"Should deny: {subject}"
