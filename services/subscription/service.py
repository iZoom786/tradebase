"""
Subscription service for managing users and provisioning JWTs
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import uuid

from libs.nats_client.auth import NATSAuthClient, Tier
from services.subscription.models import (
    User,
    Subscription,
    SubscriptionRequest,
    SubscriptionResponse,
    TrialRequest,
    TrialResponse,
    JWTValidationRequest,
    JWTValidationResponse,
    Tier as TierEnum
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    Manage subscriptions and JWT provisioning

    In production, user data would be stored in TimescaleDB.
    For now, we use an in-memory store.
    """

    def __init__(self, issuer_seed: Optional[str] = None):
        """
        Initialize subscription service

        Args:
            issuer_seed: Account NKey seed for signing JWTs
        """
        self.auth_client = NATSAuthClient(issuer_seed)
        self.users: Dict[str, User] = {}
        self.subscriptions: Dict[str, Subscription] = {}

        logger.info("subscription_service_initialized")

    async def start_trial(self, request: TrialRequest) -> TrialResponse:
        """
        Start a free trial with limited access

        Args:
            request: Trial request with email

        Returns:
            Trial response with credentials
        """
        user_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(days=30)

        # Create user
        user = User(
            user_id=user_id,
            email=request.email,
            created_at=now,
            tier=TierEnum.TRIAL,
            subscription_expires=expires_at
        )
        self.users[user_id] = user

        # Generate trial JWT (no NKey for trial users)
        jwt_token, seed, public_key = self.auth_client.create_user(
            user_id=user_id,
            tier=Tier.TRIAL.value,
            expires_hours=24 * 30  # 30 days
        )

        # Store subscription
        subscription = Subscription(
            user_id=user_id,
            tier=TierEnum.TRIAL,
            started_at=now,
            expires_at=expires_at,
            jwt=jwt_token,
            nkey_seed=seed,
            nkey_public=public_key
        )
        self.subscriptions[user_id] = subscription

        logger.info("trial_created", user_id=user_id, email=request.email)

        return TrialResponse(
            user_id=user_id,
            tier=TierEnum.TRIAL.value,
            jwt=jwt_token,
            websocket_url="wss://tradebase.com/trial",
            expires_at=expires_at
        )

    async def create_subscription(
        self,
        request: SubscriptionRequest
    ) -> SubscriptionResponse:
        """
        Create a paid subscription

        Args:
            request: Subscription request

        Returns:
            Subscription response with credentials

        Raises:
            ValueError: If tier is invalid
        """
        user_id = request.user_id
        tier = request.tier
        now = datetime.now()
        expires_at = now + timedelta(days=request.duration_days)

        # Check if user exists
        if user_id not in self.users:
            # Create new user
            self.users[user_id] = User(
                user_id=user_id,
                email=request.email or f"{user_id}@tradebase.com",
                created_at=now,
                tier=tier,
                subscription_expires=expires_at
            )
        else:
            # Update existing user
            user = self.users[user_id]
            user.tier = tier
            user.subscription_expires = expires_at

        # Generate JWT and NKey pair
        jwt_token, seed, public_key = self.auth_client.create_user(
            user_id=user_id,
            tier=tier.value,
            expires_hours=request.duration_days * 24
        )

        # Store subscription
        subscription = Subscription(
            user_id=user_id,
            tier=tier,
            started_at=now,
            expires_at=expires_at,
            jwt=jwt_token,
            nkey_seed=seed,
            nkey_public=public_key
        )
        self.subscriptions[user_id] = subscription

        logger.info(
            "subscription_created",
            user_id=user_id,
            tier=tier.value,
            expires_at=expires_at.isoformat()
        )

        return SubscriptionResponse(
            user_id=user_id,
            tier=tier.value,
            jwt=jwt_token,
            nkey_seed=seed,
            nkey_public=public_key,
            expires_at=expires_at,
            nats_url="nats://tradebase.com:4222"
        )

    async def upgrade_subscription(
        self,
        user_id: str,
        new_tier: TierEnum
    ) -> SubscriptionResponse:
        """
        Upgrade a user to a higher tier

        Args:
            user_id: User ID
            new_tier: New subscription tier

        Returns:
            Updated subscription response

        Raises:
            ValueError: If user not found or tier is invalid
        """
        if user_id not in self.users:
            raise ValueError(f"User not found: {user_id}")

        user = self.users[user_id]
        old_tier = user.tier

        # Only allow upgrades
        tier_order = [TierEnum.TRIAL, TierEnum.BASIC, TierEnum.PREMIUM]
        if tier_order.index(new_tier) <= tier_order.index(old_tier):
            raise ValueError(f"Can only upgrade to a higher tier")

        # Get existing subscription
        subscription = self.subscriptions.get(user_id)
        if not subscription:
            raise ValueError(f"Subscription not found for user: {user_id}")

        # Generate new JWT with higher tier
        jwt_token, seed, public_key = self.auth_client.upgrade_tier(
            user_id=user_id,
            old_jwt=subscription.jwt,
            new_tier=new_tier.value,
            public_key=subscription.nkey_public
        )

        # Update subscription
        subscription.tier = new_tier
        subscription.jwt = jwt_token
        subscription.expires_at = user.subscription_expires or (
            datetime.now() + timedelta(days=30)
        )

        # Update user
        user.tier = new_tier

        logger.info(
            "subscription_upgraded",
            user_id=user_id,
            old_tier=old_tier.value,
            new_tier=new_tier.value
        )

        return SubscriptionResponse(
            user_id=user_id,
            tier=new_tier.value,
            jwt=jwt_token,
            nkey_seed=seed or subscription.nkey_seed,
            nkey_public=public_key,
            expires_at=subscription.expires_at,
            nats_url="nats://tradebase.com:4222"
        )

    async def validate_jwt(self, request: JWTValidationRequest) -> JWTValidationResponse:
        """
        Validate a JWT token

        Args:
            request: Validation request with token

        Returns:
            Validation response
        """
        try:
            payload = self.auth_client.validate_user_jwt(request.token)

            # Extract information
            user_id = payload.get("sub")
            exp = payload.get("exp")
            tier = self.auth_client.jwt_manager.get_tier_from_jwt(request.token)

            # Check expiration
            if exp:
                expires_at = datetime.fromtimestamp(exp)
                if datetime.now() > expires_at:
                    return JWTValidationResponse(
                        valid=False,
                        error="Token expired"
                    )

            return JWTValidationResponse(
                valid=True,
                tier=tier,
                user_id=user_id,
                expires_at=datetime.fromtimestamp(exp) if exp else None
            )

        except Exception as e:
            logger.error("jwt_validation_failed", error=str(e))
            return JWTValidationResponse(
                valid=False,
                error=str(e)
            )

    async def revoke_subscription(self, user_id: str) -> None:
        """
        Revoke a user's subscription

        Args:
            user_id: User ID

        Raises:
            ValueError: If user not found
        """
        if user_id not in self.users:
            raise ValueError(f"User not found: {user_id}")

        # Deactivate user
        user = self.users[user_id]
        user.is_active = False

        # Remove subscription
        if user_id in self.subscriptions:
            del self.subscriptions[user_id]

        logger.info("subscription_revoked", user_id=user_id)

    async def get_user(self, user_id: str) -> Optional[User]:
        """
        Get user by ID

        Args:
            user_id: User ID

        Returns:
            User object or None
        """
        return self.users.get(user_id)

    async def get_subscription(self, user_id: str) -> Optional[Subscription]:
        """
        Get subscription by user ID

        Args:
            user_id: User ID

        Returns:
            Subscription object or None
        """
        return self.subscriptions.get(user_id)

    async def check_permission(
        self,
        user_id: str,
        subject: str,
        action: str = "sub"
    ) -> bool:
        """
        Check if user has permission for a subject

        Args:
            user_id: User ID
            subject: NATS subject
            action: 'pub' or 'sub'

        Returns:
            True if permission granted
        """
        subscription = self.subscriptions.get(user_id)
        if not subscription:
            return False

        return self.auth_client.check_permission(
            subscription.jwt,
            subject,
            action
        )

    async def list_users(self) -> list[User]:
        """
        List all users

        Returns:
            List of users
        """
        return list(self.users.values())

    async def cleanup_expired_subscriptions(self) -> int:
        """
        Remove expired subscriptions

        Returns:
            Number of subscriptions removed
        """
        now = datetime.now()
        removed = 0

        for user_id, subscription in list(self.subscriptions.items()):
            if subscription.expires_at < now:
                # Deactivate user
                if user_id in self.users:
                    self.users[user_id].is_active = False

                # Remove subscription
                del self.subscriptions[user_id]
                removed += 1

        if removed > 0:
            logger.info("expired_subscriptions_cleaned", count=removed)

        return removed
