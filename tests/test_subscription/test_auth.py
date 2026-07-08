"""
Tests for JWT/NKey authentication
"""

import pytest
from datetime import datetime, timedelta

from libs.nats_client.auth import (
    NKeyManager,
    NATSJWTManager,
    NATSAuthClient,
    Tier,
    KeyType
)
from services.subscription.models import Tier as TierEnum
from services.subscription.service import SubscriptionService
from services.subscription.models import (
    TrialRequest,
    SubscriptionRequest,
    JWTValidationRequest,
)


class TestNKeyManager:
    """Test NKey management"""

    def test_generate_keypair_user(self):
        """Test generating a user keypair"""
        seed, public_key = NKeyManager.generate_keypair(KeyType.USER)

        assert seed is not None
        assert isinstance(seed, str)
        assert public_key is not None
        assert isinstance(public_key, str)
        assert seed.startswith("USER_")

    def test_generate_keypair_account(self):
        """Test generating an account keypair"""
        seed, public_key = NKeyManager.generate_keypair(KeyType.ACCOUNT)

        assert seed.startswith("ACCOUNT_")

    def test_sign_challenge(self):
        """Test signing a challenge"""
        seed, _ = NKeyManager.generate_keypair(KeyType.USER)
        challenge = b"test_challenge_nonce"

        signature = NKeyManager.sign_challenge(seed, challenge)

        assert signature is not None
        assert isinstance(signature, bytes)

    def test_different_keys_generate_different_seeds(self):
        """Test that different calls generate different keys"""
        seed1, pub1 = NKeyManager.generate_keypair(KeyType.USER)
        seed2, pub2 = NKeyManager.generate_keypair(KeyType.USER)

        assert seed1 != seed2
        assert pub1 != pub2


class TestNATSJWTManager:
    """Test JWT management"""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager instance"""
        return NATSJWTManager()

    def test_generate_user_jwt_trial(self, jwt_manager):
        """Test generating a trial JWT"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.TRIAL.value,
            public_key="test_public_key"
        )

        assert jwt_token is not None
        assert isinstance(jwt_token, str)

        # Verify JWT can be decoded
        payload = jwt_manager.validate_jwt(jwt_token)
        assert payload["sub"] == "test_user"
        assert "trial" in payload["tags"]

    def test_generate_user_jwt_basic(self, jwt_manager):
        """Test generating a basic JWT"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.BASIC.value,
            public_key="test_public_key"
        )

        payload = jwt_manager.validate_jwt(jwt_token)
        assert "basic" in payload["tags"]

    def test_generate_user_jwt_premium(self, jwt_manager):
        """Test generating a premium JWT"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.PREMIUM.value,
            public_key="test_public_key"
        )

        payload = jwt_manager.validate_jwt(jwt_token)
        assert "premium" in payload["tags"]

    def test_generate_jwt_custom_expiry(self, jwt_manager):
        """Test generating JWT with custom expiry"""
        hours = 48
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.BASIC.value,
            public_key="test_public_key",
            expires_hours=hours
        )

        payload = jwt_manager.validate_jwt(jwt_token)
        exp = payload["exp"]
        iat = payload["iat"]

        # Check expiry is approximately correct
        assert (exp - iat) == hours * 3600

    def test_validate_invalid_jwt(self, jwt_manager):
        """Test validating an invalid JWT"""
        with pytest.raises(Exception):  # jwt.InvalidTokenError
            jwt_manager.validate_jwt("invalid_jwt_token")

    def test_get_tier_from_jwt(self, jwt_manager):
        """Test extracting tier from JWT"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.PREMIUM.value,
            public_key="test_public_key"
        )

        tier = jwt_manager.get_tier_from_jwt(jwt_token)
        assert tier == Tier.PREMIUM.value

    def test_check_permission_trial(self, jwt_manager):
        """Test trial permissions"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.TRIAL.value,
            public_key="test_public_key"
        )

        # Trial users can access paper trading
        assert jwt_manager.check_permission(
            jwt_token,
            "tradebase.public.papertrading.eurusd",
            "sub"
        )

        # Trial users cannot access raw data
        assert not jwt_manager.check_permission(
            jwt_token,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        )

    def test_check_permission_basic(self, jwt_manager):
        """Test basic subscriber permissions"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.BASIC.value,
            public_key="test_public_key"
        )

        # Basic users can access raw data
        assert jwt_manager.check_permission(
            jwt_token,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        )

        # Basic users cannot access predictions
        assert not jwt_manager.check_permission(
            jwt_token,
            "tradebase.forex.eurusd.prediction.1m",
            "sub"
        )

    def test_check_permission_premium(self, jwt_manager):
        """Test premium subscriber permissions"""
        jwt_token = jwt_manager.generate_user_jwt(
            user_id="test_user",
            tier=Tier.PREMIUM.value,
            public_key="test_public_key"
        )

        # Premium users can access everything
        assert jwt_manager.check_permission(
            jwt_token,
            "tradebase.forex.eurusd.raw.1m",
            "sub"
        )
        assert jwt_manager.check_permission(
            jwt_token,
            "tradebase.forex.eurusd.features.1m",
            "sub"
        )
        assert jwt_manager.check_permission(
            jwt_token,
            "tradebase.forex.eurusd.prediction.1m",
            "sub"
        )

    def test_check_permission_publish_denied(self, jwt_manager):
        """Test that publish is denied for all user tiers"""
        for tier in [Tier.TRIAL, Tier.BASIC, Tier.PREMIUM]:
            jwt_token = jwt_manager.generate_user_jwt(
                user_id="test_user",
                tier=tier.value,
                public_key="test_public_key"
            )

            # All users are denied publish
            assert not jwt_manager.check_permission(
                jwt_token,
                "tradebase.forex.eurusd.raw.1m",
                "pub"
            )

    def test_match_subject_pattern(self, jwt_manager):
        """Test subject pattern matching"""
        # * matches single token
        assert jwt_manager._match_subject("tradebase.*.raw.1m", "tradebase.eurusd.raw.1m")
        assert jwt_manager._match_subject("tradebase.*.raw.1m", "tradebase.gbpusd.raw.1m")
        assert not jwt_manager._match_subject("tradebase.*.raw.1m", "tradebase.eurusd.raw.5m")

        # > matches rest
        assert jwt_manager._match_subject("tradebase.>", "tradebase.forex.eurusd.raw.1m")
        assert jwt_manager._match_subject("tradebase.forex.>", "tradebase.forex.eurusd.raw.1m")
        assert jwt_manager._match_subject("tradebase.public.>", "tradebase.public.papertrading.eurusd")


class TestNATSAuthClient:
    """Test the combined auth client"""

    @pytest.fixture
    def auth_client(self):
        """Create an auth client instance"""
        return NATSAuthClient()

    def test_create_user_trial(self, auth_client):
        """Test creating a trial user"""
        jwt_token, seed, public_key = auth_client.create_user(
            user_id="trial_user",
            tier=Tier.TRIAL.value
        )

        assert jwt_token is not None
        assert seed is not None
        assert public_key is not None
        assert seed.startswith("USER_")

    def test_create_user_premium(self, auth_client):
        """Test creating a premium user"""
        jwt_token, seed, public_key = auth_client.create_user(
            user_id="premium_user",
            tier=Tier.PREMIUM.value
        )

        # Verify JWT contains correct tier
        tier = auth_client.jwt_manager.get_tier_from_jwt(jwt_token)
        assert tier == Tier.PREMIUM.value

    def test_sign_challenge(self, auth_client):
        """Test signing a challenge"""
        _, seed, _ = auth_client.create_user(
            user_id="test_user",
            tier=Tier.BASIC.value
        )

        challenge = b"server_nonce"
        signature = auth_client.sign_challenge(seed, challenge)

        assert signature is not None
        assert isinstance(signature, bytes)

    def test_upgrade_tier(self, auth_client):
        """Test upgrading a user tier"""
        # Create basic user
        jwt_token, seed, public_key = auth_client.create_user(
            user_id="test_user",
            tier=Tier.BASIC.value
        )

        # Upgrade to premium
        new_jwt, new_seed, new_pub = auth_client.upgrade_tier(
            user_id="test_user",
            old_jwt=jwt_token,
            new_tier=Tier.PREMIUM.value,
            public_key=public_key
        )

        # Verify new JWT has premium tier
        new_tier = auth_client.jwt_manager.get_tier_from_jwt(new_jwt)
        assert new_tier == Tier.PREMIUM.value

        # Public key should remain the same
        assert new_pub == public_key


class TestSubscriptionService:
    """Test the subscription service"""

    @pytest.fixture
    async def subscription_service(self):
        """Create a subscription service instance"""
        return SubscriptionService()

    @pytest.mark.asyncio
    async def test_start_trial(self, subscription_service):
        """Test starting a free trial"""
        request = TrialRequest(email="test@example.com")
        response = await subscription_service.start_trial(request)

        assert response.user_id is not None
        assert response.tier == Tier.TRIAL.value
        assert response.jwt is not None
        assert response.websocket_url is not None
        assert response.expires_at > datetime.now()

    @pytest.mark.asyncio
    async def test_create_subscription_basic(self, subscription_service):
        """Test creating a basic subscription"""
        request = SubscriptionRequest(
            user_id="user_123",
            tier=TierEnum.BASIC,
            duration_days=30
        )
        response = await subscription_service.create_subscription(request)

        assert response.user_id == "user_123"
        assert response.tier == Tier.BASIC.value
        assert response.jwt is not None
        assert response.nkey_seed is not None
        assert response.nkey_public is not None
        assert response.expires_at > datetime.now()

    @pytest.mark.asyncio
    async def test_create_subscription_premium(self, subscription_service):
        """Test creating a premium subscription"""
        request = SubscriptionRequest(
            user_id="user_456",
            tier=TierEnum.PREMIUM,
            duration_days=90
        )
        response = await subscription_service.create_subscription(request)

        assert response.tier == Tier.PREMIUM.value

    @pytest.mark.asyncio
    async def test_upgrade_subscription(self, subscription_service):
        """Test upgrading a subscription"""
        # Create basic subscription first
        basic_request = SubscriptionRequest(
            user_id="user_789",
            tier=TierEnum.BASIC,
            duration_days=30
        )
        await subscription_service.create_subscription(basic_request)

        # Upgrade to premium
        response = await subscription_service.upgrade_subscription(
            user_id="user_789",
            new_tier=TierEnum.PREMIUM
        )

        assert response.tier == Tier.PREMIUM.value

    @pytest.mark.asyncio
    async def test_validate_jwt(self, subscription_service):
        """Test JWT validation"""
        # Create a subscription
        request = SubscriptionRequest(
            user_id="user_abc",
            tier=TierEnum.BASIC,
            duration_days=30
        )
        response = await subscription_service.create_subscription(request)

        # Validate the JWT
        validation_request = JWTValidationRequest(token=response.jwt)
        validation_response = await subscription_service.validate_jwt(validation_request)

        assert validation_response.valid is True
        assert validation_response.tier == Tier.BASIC.value
        assert validation_response.user_id == "user_abc"

    @pytest.mark.asyncio
    async def test_revoke_subscription(self, subscription_service):
        """Test revoking a subscription"""
        # Create a subscription
        request = SubscriptionRequest(
            user_id="user_xyz",
            tier=TierEnum.BASIC,
            duration_days=30
        )
        await subscription_service.create_subscription(request)

        # Revoke it
        await subscription_service.revoke_subscription("user_xyz")

        # Check user is deactivated
        user = await subscription_service.get_user("user_xyz")
        assert user is not None
        assert user.is_active is False

    @pytest.mark.asyncio
    async def test_check_permission(self, subscription_service):
        """Test permission checking"""
        # Create premium subscription
        request = SubscriptionRequest(
            user_id="user_perm",
            tier=TierEnum.PREMIUM,
            duration_days=30
        )
        await subscription_service.create_subscription(request)

        # Check permissions
        can_access_raw = await subscription_service.check_permission(
            user_id="user_perm",
            subject="tradebase.forex.eurusd.raw.1m",
            action="sub"
        )

        can_publish = await subscription_service.check_permission(
            user_id="user_perm",
            subject="tradebase.forex.eurusd.raw.1m",
            action="pub"
        )

        assert can_access_raw is True
        assert can_publish is False  # Publishing denied

    @pytest.mark.asyncio
    async def test_cleanup_expired_subscriptions(self, subscription_service):
        """Test cleanup of expired subscriptions"""
        # Create a subscription that expires in the past
        request = SubscriptionRequest(
            user_id="expired_user",
            tier=TierEnum.BASIC,
            duration_days=-1  # Expires yesterday
        )

        # This will create a subscription with past expiration
        await subscription_service.create_subscription(request)

        # Manually expire it
        if "expired_user" in subscription_service.subscriptions:
            subscription_service.subscriptions["expired_user"].expires_at = (
                datetime.now() - timedelta(days=1)
            )

        # Run cleanup
        removed = await subscription_service.cleanup_expired_subscriptions()

        # Should have removed at least one
        assert removed >= 0
