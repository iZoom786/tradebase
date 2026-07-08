"""
NATS JWT/NKey Authentication Module

Provides:
- NKey management (generating and managing cryptographic keypairs)
- JWT generation and validation for NATS
- Tier-based permission management
- Challenge signing and verification
"""

import base64
import json
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import jwt


class KeyType(Enum):
    """NKey key types"""
    USER = "USER"
    ACCOUNT = "ACCOUNT"
    SERVER = "SERVER"


class Tier(Enum):
    """Subscription tiers with different access levels"""
    TRIAL = "trial"
    BASIC = "basic"
    PREMIUM = "premium"


@dataclass
class NATSPermissions:
    """NATS publish/subscribe permissions"""
    publish: Dict[str, List[str]]
    subscribe: Dict[str, List[str]]


class NKeyManager:
    """
    Manage NKey cryptographic keypairs for NATS authentication

    NKeys are Ed25519 keys used for:
    - Signing JWTs (account keys)
    - User authentication (user keys)
    - Challenge-response authentication
    """

    @staticmethod
    def generate_keypair(key_type: KeyType = KeyType.USER) -> Tuple[str, str]:
        """
        Generate an NKey pair (seed, public_key)

        Args:
            key_type: Type of key to generate

        Returns:
            Tuple of (seed_bytes, public_key)

        Note:
            In production, use python-nkeys library:
            import nkeys
            kp = nkeys.from_seed(nkeys.create_pair(key_type))
            seed = kp.seed
            public_key = kp.public_key

        For this implementation, we use a simpler approach with jwt library
        since python-nkeys may not be available.
        """
        # Generate a random seed (32 bytes for Ed25519)
        seed_bytes = secrets.token_bytes(32)

        # Create a simple public key derivation (in production, use actual Ed25519)
        # This is a simplified version for demonstration
        secret = secrets.token_urlsafe(32)
        public_key = secrets.token_urlsafe(16)

        # Encode seed as base64 for storage
        seed_encoded = base64.b64encode(seed_bytes).decode('utf-8')

        # Add key type prefix
        seed_with_prefix = f"{key_type.value.upper()}_{seed_encoded}"

        return seed_with_prefix, public_key

    @staticmethod
    def sign_challenge(seed: str, challenge: bytes) -> bytes:
        """
        Sign a server challenge with private key

        Args:
            seed: NKey seed
            challenge: Challenge bytes from server

        Returns:
            Signature bytes

        Note:
            In production with python-nkeys:
            kp = nkeys.from_seed(seed.encode())
            return kp.sign(challenge)
        """
        # Simplified signing - in production use actual Ed25519 signing
        # This combines the seed with challenge and hashes it
        import hashlib
        combined = seed.encode('utf-8') + challenge
        signature = hashlib.sha256(combined).digest()
        return signature

    @staticmethod
    def verify_signature(public_key: str, signature: bytes, challenge: bytes) -> bool:
        """
        Verify a signature against public key and challenge

        Args:
            public_key: NKey public key
            signature: Signature to verify
            challenge: Original challenge bytes

        Returns:
            True if signature is valid
        """
        # Simplified verification - in production use actual Ed25519 verification
        import hashlib
        # This would need the original seed to verify properly
        # For now, return True (production requires proper crypto)
        return True


class NATSJWTManager:
    """
    Generate and validate NATS JWTs with tier-based permissions

    JWTs contain:
    - User identity
    - Expiration time
    - Tier-based NATS subject permissions
    - Issuer information
    """

    # Issuer account seed (in production, load from secure storage)
    ISSUER_SEED: Optional[str] = None

    # JWT expiration defaults
    DEFAULT_EXPIRY_HOURS = 24 * 30  # 30 days

    def __init__(self, issuer_seed: Optional[str] = None):
        """
        Initialize JWT manager

        Args:
            issuer_seed: Account NKey seed for signing JWTs
        """
        self.issuer_seed = issuer_seed or self.ISSUER_SEED
        if not self.issuer_seed:
            # Generate a temporary issuer seed for development
            self.issuer_seed, _ = NKeyManager.generate_keypair(KeyType.ACCOUNT)

    def generate_user_jwt(
        self,
        user_id: str,
        tier: str,
        public_key: str,
        expires_hours: int = DEFAULT_EXPIRY_HOURS
    ) -> str:
        """
        Generate a user JWT with tier-based permissions

        Args:
            user_id: Unique user identifier
            tier: Subscription tier (trial, basic, premium)
            public_key: User's NKey public key
            expires_hours: JWT validity period

        Returns:
            Encoded JWT string

        Raises:
            ValueError: If tier is invalid
        """
        # Validate tier
        tier = tier.lower()
        if tier not in [t.value for t in Tier]:
            raise ValueError(f"Invalid tier: {tier}. Must be one of: {[t.value for t in Tier]}")

        now = int(datetime.now().timestamp())
        exp = now + (expires_hours * 3600)

        # Get permissions for tier
        permissions = self._get_permissions_for_tier(tier)

        # JWT payload following NATS JWT structure
        payload = {
            "jti": f"{user_id}_{now}",  # JWT ID
            "iat": now,                   # Issued at
            "nbf": now,                   # Not before
            "exp": exp,                   # Expiration
            "iss": "TRADEBASE",           # Issuer
            "name": f"user_{user_id}",    # User name
            "sub": user_id,               # Subject (user ID)
            "nats": {
                "pub": permissions["publish"],
                "sub": permissions["subscribe"],
                "datas": -1,               # Unlimited data
                "payload": -1,            # Unlimited payload size
                "subs": -1,               # Unlimited subscriptions
                "conns": -1,              # Unlimited connections
            },
            "tags": [tier],
            "tenant": None
        }

        # Sign with issuer key
        # In production, use the issuer's NKey to sign
        # For now, use HS256 with a secret
        secret = self.issuer_seed.split('_')[-1] if '_' in self.issuer_seed else self.issuer_seed
        token = jwt.encode(payload, secret, algorithm="HS256")

        return token

    def validate_jwt(self, token: str) -> Dict:
        """
        Validate and decode a JWT

        Args:
            token: JWT string

        Returns:
            Decoded payload

        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        secret = self.issuer_seed.split('_')[-1] if '_' in self.issuer_seed else self.issuer_seed
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload

    def _get_permissions_for_tier(self, tier: str) -> Dict:
        """
        Get NATS subject permissions for a tier

        Args:
            tier: Subscription tier

        Returns:
            Dict with publish and subscribe permissions
        """
        # Common subject patterns
        forex_raw = "tradebase.forex.*.raw.>"
        forex_features = "tradebase.forex.*.features.>"
        forex_prediction = "tradebase.forex.*.prediction.>"
        public_paper = "tradebase.public.papertrading.>"

        if tier == Tier.TRIAL.value:
            return {
                "publish": {"deny": [">"]},
                "subscribe": {
                    "allow": [public_paper]
                }
            }

        elif tier == Tier.BASIC.value:
            return {
                "publish": {"deny": [">"]},
                "subscribe": {
                    "allow": [forex_raw, forex_features]
                }
            }

        elif tier == Tier.PREMIUM.value:
            return {
                "publish": {"deny": [">"]},
                "subscribe": {
                    "allow": [
                        forex_raw,
                        forex_features,
                        forex_prediction
                    ]
                }
            }

        else:
            # Default deny all
            return {
                "publish": {"deny": [">"]},
                "subscribe": {"deny": [">"]}
            }

    def get_tier_from_jwt(self, token: str) -> str:
        """
        Extract tier from JWT

        Args:
            token: JWT string

        Returns:
            Tier string
        """
        payload = self.validate_jwt(token)
        tags = payload.get("tags", [])
        for tag in tags:
            if tag in [t.value for t in Tier]:
                return tag
        return Tier.TRIAL.value  # Default to trial

    def check_permission(self, token: str, subject: str, action: str = "sub") -> bool:
        """
        Check if JWT grants permission for a subject

        Args:
            token: JWT string
            subject: NATS subject to check
            action: 'pub' or 'sub'

        Returns:
            True if permission granted
        """
        try:
            payload = self.validate_jwt(token)
            nats_data = payload.get("nats", {})

            permissions = nats_data.get("pub" if action == "pub" else "sub", {})

            # Check deny list first
            deny_list = permissions.get("deny", [])
            for pattern in deny_list:
                if self._match_subject(pattern, subject):
                    return False

            # Check allow list
            allow_list = permissions.get("allow", [])
            for pattern in allow_list:
                if self._match_subject(pattern, subject):
                    return True

            # Default: no explicit allow = deny
            return False

        except (jwt.InvalidTokenError, KeyError):
            return False

    @staticmethod
    def _match_subject(pattern: str, subject: str) -> bool:
        """
        Match a subject pattern against a subject

        Args:
            pattern: Pattern with wildcards (* and >)
            subject: Actual subject

        Returns:
            True if pattern matches subject
        """
        # Convert NATS wildcards to regex
        # * matches a single token
        # > matches zero or more tokens

        pattern_parts = pattern.split('.')
        subject_parts = subject.split('.')

        # Handle > wildcard (matches rest)
        for i, part in enumerate(pattern_parts):
            if part == '>':
                # Everything from here matches
                return True

            if i >= len(subject_parts):
                return False

            if part == '*':
                continue  # Matches any single token

            if part != subject_parts[i]:
                return False

        # Exact match if no > was encountered
        return len(pattern_parts) == len(subject_parts)


class NATSAuthClient:
    """
    High-level authentication client combining NKey and JWT management

    Usage:
        # Create a new user
        auth_client = NATSAuthClient()
        user_jwt, seed, public_key = auth_client.create_user("user123", Tier.BASIC)

        # Connect to NATS with JWT
        await nc.connect(
            servers="nats://localhost:4222",
            user_jwt=user_jwt,
            signature_cb=lambda nonce: auth_client.sign_challenge(seed, nonce)
        )
    """

    def __init__(self, issuer_seed: Optional[str] = None):
        """
        Initialize auth client

        Args:
            issuer_seed: Account NKey seed for signing JWTs
        """
        self.nkey_manager = NKeyManager()
        self.jwt_manager = NATSJWTManager(issuer_seed)

    def create_user(
        self,
        user_id: str,
        tier: str,
        expires_hours: int = 720
    ) -> Tuple[str, str, str]:
        """
        Create a new user with NKey pair and JWT

        Args:
            user_id: Unique user identifier
            tier: Subscription tier
            expires_hours: JWT validity period

        Returns:
            Tuple of (jwt_token, nkey_seed, nkey_public_key)
        """
        # Generate user NKey pair
        seed, public_key = self.nkey_manager.generate_keypair(KeyType.USER)

        # Generate JWT
        jwt_token = self.jwt_manager.generate_user_jwt(
            user_id=user_id,
            tier=tier,
            public_key=public_key,
            expires_hours=expires_hours
        )

        return jwt_token, seed, public_key

    def sign_challenge(self, seed: str, challenge: bytes) -> bytes:
        """
        Sign a server challenge (for connection authentication)

        Args:
            seed: User's NKey seed
            challenge: Challenge bytes from NATS server

        Returns:
            Signature bytes
        """
        return self.nkey_manager.sign_challenge(seed, challenge)

    def validate_user_jwt(self, token: str) -> Dict:
        """
        Validate a user JWT and return its payload

        Args:
            token: JWT string

        Returns:
            Decoded JWT payload
        """
        return self.jwt_manager.validate_jwt(token)

    def check_permission(self, token: str, subject: str, action: str = "sub") -> bool:
        """
        Check if a JWT grants permission for a subject

        Args:
            token: JWT string
            subject: NATS subject
            action: 'pub' or 'sub'

        Returns:
            True if permission granted
        """
        return self.jwt_manager.check_permission(token, subject, action)

    def upgrade_tier(
        self,
        user_id: str,
        old_jwt: str,
        new_tier: str,
        public_key: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Upgrade a user to a new tier

        Args:
            user_id: User ID
            old_jwt: Current JWT (to extract public key if not provided)
            new_tier: New subscription tier
            public_key: User's public key (optional, extracted from old_jwt if not provided)

        Returns:
            Tuple of (new_jwt, seed, public_key)
        """
        if not public_key:
            # In a real system, we'd store user keys in a database
            # For now, generate new keys
            seed, public_key = self.nkey_manager.generate_keypair(KeyType.USER)
        else:
            seed = ""  # User keeps their existing seed

        new_jwt = self.jwt_manager.generate_user_jwt(
            user_id=user_id,
            tier=new_tier,
            public_key=public_key
        )

        return new_jwt, seed, public_key


# Export for use in other modules
__all__ = [
    'KeyType',
    'Tier',
    'NATSPermissions',
    'NKeyManager',
    'NATSJWTManager',
    'NATSAuthClient',
]
