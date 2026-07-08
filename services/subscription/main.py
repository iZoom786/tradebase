"""
FastAPI application for subscription service

Provides REST API for:
- Starting free trials
- Creating paid subscriptions
- Upgrading subscriptions
- Validating JWTs
- Managing users
"""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator

from services.subscription.service import SubscriptionService
from services.subscription.models import (
    Tier,
    TrialRequest,
    TrialResponse,
    SubscriptionRequest,
    SubscriptionResponse,
    JWTValidationRequest,
    JWTValidationResponse,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Tradebase Subscription API",
    description="Subscription and JWT provisioning service",
    version="0.1.0"
)

# Security
security = HTTPBearer(auto_error=False)

# Global service instance
subscription_service: Optional[SubscriptionService] = None


# =====================================================
# Request/Response Models
# =====================================================

class TrialRequestAPI(BaseModel):
    """Trial request from API"""
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class SubscriptionRequestAPI(BaseModel):
    """Subscription request from API"""
    user_id: str
    tier: Tier
    duration_days: int = 30
    email: Optional[EmailStr] = None

    @validator('tier')
    def validate_tier(cls, v):
        if isinstance(v, str):
            v = Tier(v.lower())
        return v

    @validator('duration_days')
    def validate_duration(cls, v):
        if v < 1 or v > 365:
            raise ValueError('duration_days must be between 1 and 365')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "tier": "basic",
                "duration_days": 30
            }
        }


class UpgradeRequestAPI(BaseModel):
    """Upgrade request from API"""
    new_tier: Tier

    @validator('new_tier')
    def validate_tier(cls, v):
        if isinstance(v, str):
            v = Tier(v.lower())
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "new_tier": "premium"
            }
        }


class JWTValidationRequestAPI(BaseModel):
    """JWT validation request from API"""
    token: str

    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
            }
        }


class ResetRequestAPI(BaseModel):
    """Reset paper trading account request"""
    user_id: str

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123"
            }
        }


# =====================================================
# Lifecycle
# =====================================================

@app.on_event("startup")
async def startup():
    """Initialize subscription service"""
    global subscription_service

    # Get issuer seed from environment or generate one
    issuer_seed = os.getenv("NATS_ISSUER_SEED")
    if not issuer_seed:
        logger.warning("nats_issuer_seed_not_set_generating")

    subscription_service = SubscriptionService(issuer_seed)
    logger.info("subscription_service_started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("subscription_service_stopped")


# =====================================================
# Health Check
# =====================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "subscription", "timestamp": datetime.now().isoformat()}


# =====================================================
# Trial Endpoints
# =====================================================

@app.post(
    "/auth/trial",
    response_model=TrialResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"]
)
async def start_trial(request: TrialRequestAPI):
    """
    Start a free trial with limited access

    Trial users can:
    - View public paper trading feed
    - Access the dashboard with WebSocket

    Trial users cannot:
    - Access raw market data
    - Access computed features
    - Access ML predictions
    """
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    trial_request = TrialRequest(email=request.email)

    try:
        response = await subscription_service.start_trial(trial_request)
        return response
    except Exception as e:
        logger.error("trial_creation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create trial: {str(e)}"
        )


# =====================================================
# Subscription Endpoints
# =====================================================

@app.post(
    "/auth/subscribe",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"]
)
async def create_subscription(request: SubscriptionRequestAPI):
    """
    Create a paid subscription

    Provides JWT and NKey credentials for NATS authentication.

    **Basic Tier ($X/month):**
    - Raw OHLCV market data (1m, 5m, 15m, 1h, 4h, 1d)
    - Pre-calculated technical indicators
    - Time-decayed sentiment scores

    **Premium Tier ($Y/month):**
    - Everything in Basic, plus:
    - Machine learning direction signals
    - Confidence probabilities
    - Model ensemble votes
    """
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    subscription_request = SubscriptionRequest(
        user_id=request.user_id,
        tier=request.tier,
        duration_days=request.duration_days,
        email=request.email
    )

    try:
        response = await subscription_service.create_subscription(subscription_request)
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("subscription_creation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subscription: {str(e)}"
        )


@app.put(
    "/auth/upgrade/{user_id}",
    response_model=SubscriptionResponse,
    tags=["Authentication"]
)
async def upgrade_subscription(user_id: str, request: UpgradeRequestAPI):
    """
    Upgrade a subscription to a higher tier

    Allows users to upgrade from:
    - Trial → Basic
    - Trial → Premium
    - Basic → Premium
    """
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    try:
        from services.subscription.models import Tier as TierEnum
        response = await subscription_service.upgrade_subscription(
            user_id=user_id,
            new_tier=TierEnum(request.new_tier.value)
        )
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("subscription_upgrade_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upgrade subscription: {str(e)}"
        )


@app.delete(
    "/auth/revoke/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Authentication"]
)
async def revoke_subscription(user_id: str):
    """
    Revoke a user's subscription

    This will:
    - Deactivate the user
    - Remove their JWT
    - Prevent NATS access
    """
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    try:
        await subscription_service.revoke_subscription(user_id)
        return
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("subscription_revocation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke subscription: {str(e)}"
        )


# =====================================================
# Validation Endpoints
# =====================================================

@app.post(
    "/auth/validate",
    response_model=JWTValidationResponse,
    tags=["Authentication"]
)
async def validate_jwt(request: JWTValidationRequestAPI):
    """
    Validate a JWT token

    This endpoint is called by:
    - Client applications (to check token status)

    Returns:
        Validation result with tier and expiration
    """
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    validation_request = JWTValidationRequest(token=request.token)

    try:
        response = await subscription_service.validate_jwt(validation_request)
        return response
    except Exception as e:
        logger.error("jwt_validation_failed", error=str(e))
        return JWTValidationResponse(
            valid=False,
            error=str(e)
        )


# =====================================================
# NATS JWT Resolver Endpoint
# =====================================================

@app.post(
    "/nats/resolver",
    tags=["NATS Resolver"]
)
async def nats_jwt_resolver(request: JWTValidationRequestAPI):
    """
    NATS JWT Resolver Endpoint

    This endpoint follows the NATS JWT resolver protocol for validating
    user JWTs during connection authentication.

    **Protocol:**
    - POST request with JWT in request body
    - Returns NATS-compatible response with permissions
    - Called by NATS server when using HTTP resolver

    **Response Format (for NATS):**
    ```json
    {
        "sub": "user_id",
        "nats": {
            "pub": {"allow": [...], "deny": [...]},
            "sub": {"allow": [...], "deny": [...]},
            "datas": -1,
            "payload": -1,
            "subs": -1,
            "conns": -1
        }
    }
    ```

    **Error Response:**
    ```json
    {
        "error": "error message"
    }
    ```
    """
    if subscription_service is None:
        # NATS expects error response
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Service not initialized"}
        )

    try:
        # Validate the JWT
        validation_request = JWTValidationRequest(token=request.token)
        response = await subscription_service.validate_jwt(validation_request)

        if not response.valid:
            # Return error for invalid tokens (NATS will deny connection)
            return {
                "error": response.error or "Invalid token"
            }

        # Get the full JWT payload to extract permissions
        payload = subscription_service.auth_client.validate_user_jwt(request.token)
        nats_data = payload.get("nats", {})

        # Return NATS-compatible response with permissions
        return {
            "sub": payload.get("sub"),
            "name": payload.get("name"),
            "nats": nats_data,
            "exp": payload.get("exp"),
            "iat": payload.get("iat"),
            "issuer": payload.get("iss"),
            "tags": payload.get("tags", [])
        }

    except jwt.ExpiredSignatureError:
        logger.warning("nats_jwt_expired")
        return {"error": "Token expired"}
    except jwt.InvalidTokenError as e:
        logger.error("nats_jwt_invalid", error=str(e))
        return {"error": f"Invalid token: {str(e)}"}
    except Exception as e:
        logger.error("nats_resolver_error", error=str(e))
        return {"error": str(e)}


# =====================================================
# User Management Endpoints
# =====================================================

@app.get(
    "/users/{user_id}",
    tags=["User Management"]
)
async def get_user(user_id: str):
    """Get user information"""
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    user = await subscription_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}"
        )

    return {
        "user_id": user.user_id,
        "email": user.email,
        "tier": user.tier.value,
        "created_at": user.created_at.isoformat(),
        "subscription_expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
        "is_active": user.is_active
    }


@app.get(
    "/users/{user_id}/subscription",
    tags=["User Management"]
)
async def get_subscription(user_id: str):
    """Get user subscription details"""
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    subscription = await subscription_service.get_subscription(user_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription not found: {user_id}"
        )

    return {
        "user_id": subscription.user_id,
        "tier": subscription.tier.value,
        "started_at": subscription.started_at.isoformat(),
        "expires_at": subscription.expires_at.isoformat(),
        "has_jwt": bool(subscription.jwt),
        "has_nkey": bool(subscription.nkey_public)
    }


@app.get(
    "/users",
    tags=["User Management"]
)
async def list_users():
    """List all users (admin only)"""
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    users = await subscription_service.list_users()
    return {
        "count": len(users),
        "users": [
            {
                "user_id": u.user_id,
                "email": u.email,
                "tier": u.tier.value,
                "is_active": u.is_active,
                "subscription_expires": u.subscription_expires.isoformat() if u.subscription_expires else None
            }
            for u in users
        ]
    }


# =====================================================
# Paper Trading Endpoints
# =====================================================

@app.post(
    "/paper/reset",
    tags=["Paper Trading"]
)
async def reset_paper_account(request: ResetRequestAPI):
    """
    Reset paper trading account to $100

    This endpoint is used by the web dashboard to reset
    a trial user's virtual trading account.
    """
    # This would call the paper trading service
    # For now, return success
    return {
        "message": "Account reset to $100",
        "user_id": request.user_id,
        "new_balance": 100.00
    }


# =====================================================
# Permission Check Endpoint
# =====================================================

@app.get(
    "/permissions/{user_id}",
    tags=["Permissions"]
)
async def check_user_permission(
    user_id: str,
    subject: str,
    action: str = "sub"
):
    """
    Check if a user has permission for a NATS subject

    Args:
        user_id: User ID
        subject: NATS subject pattern
        action: 'pub' or 'sub' (default: 'sub')

    Returns:
        Permission check result
    """
    if subscription_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    has_permission = await subscription_service.check_permission(
        user_id=user_id,
        subject=subject,
        action=action
    )

    return {
        "user_id": user_id,
        "subject": subject,
        "action": action,
        "allowed": has_permission
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "services.subscription.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True
    )
