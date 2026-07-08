"""
Subscription service data models
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class Tier(str, Enum):
    """Subscription tiers"""
    TRIAL = "trial"
    BASIC = "basic"
    PREMIUM = "premium"


@dataclass
class User:
    """User account"""
    user_id: str
    email: str
    created_at: datetime
    tier: Tier = Tier.TRIAL
    subscription_expires: Optional[datetime] = None
    nkey_public: Optional[str] = None
    is_active: bool = True


@dataclass
class Subscription:
    """User subscription"""
    user_id: str
    tier: Tier
    started_at: datetime
    expires_at: datetime
    jwt: Optional[str] = None
    nkey_seed: Optional[str] = None
    nkey_public: Optional[str] = None


@dataclass
class SubscriptionRequest:
    """Request to create/update subscription"""
    user_id: str
    tier: Tier
    duration_days: int = 30
    email: Optional[str] = None


@dataclass
class SubscriptionResponse:
    """Response with subscription credentials"""
    user_id: str
    tier: str
    jwt: str
    nkey_seed: str
    nkey_public: str
    expires_at: datetime
    nats_url: str


@dataclass
class TrialRequest:
    """Request to start free trial"""
    email: str


@dataclass
class TrialResponse:
    """Response with trial credentials"""
    user_id: str
    tier: str
    jwt: str
    websocket_url: str
    expires_at: datetime


@dataclass
class JWTValidationRequest:
    """Request to validate JWT"""
    token: str


@dataclass
class JWTValidationResponse:
    """Response with JWT validation result"""
    valid: bool
    tier: Optional[str] = None
    user_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None
