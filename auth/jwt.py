import os
import jwt
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger("pipedesk.auth.jwt")

@dataclass
class UserContext:
    id: str
    role: str
    email: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

def verify_supabase_jwt(token: str) -> Optional[UserContext]:
    """
    Verifies a Supabase JWT token and returns the user context.

    Args:
        token: The JWT token string (without 'Bearer ' prefix)

    Returns:
        Optional[UserContext]: A UserContext dataclass containing the user ID and role if verification succeeds,
                               or None if JWT secret is not configured (allowing fallback to legacy auth).

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid (bad signature, etc).
    """
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        logger.warning("SUPABASE_JWT_SECRET is not configured. JWT authentication is disabled.")
        return None

    # Debug log: show last 4 characters of the secret for verification (never log full secret)
    logger.debug(f"DEBUG: Attempting to decode token with secret ending in ...{secret[-4:]}")

    try:
        # Supabase uses HS256 by default
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False}  # Supabase aud is usually 'authenticated', but can vary.
        )
    except jwt.ExpiredSignatureError as e:
        logger.error(f"JWT Error: Token has expired. Details: {e}")
        raise
    except jwt.InvalidAudienceError as e:
        logger.error(f"JWT Error: Audience mismatch. Details: {e}")
        raise
    except jwt.InvalidSignatureError as e:
        logger.error(f"JWT Error: Signature verification failed. Details: {e}")
        raise
    except jwt.DecodeError as e:
        logger.error(f"JWT Error: Token decode failed. Details: {e}")
        raise
    except jwt.InvalidTokenError as e:
        logger.error(f"JWT Error: Invalid token. Details: {e}")
        raise

    # Extract standard claims
    user_id = payload.get("sub")
    if not user_id:
        raise jwt.InvalidTokenError("Token missing 'sub' claim")

    # Extract role. Supabase puts the role in the 'role' claim (e.g. 'authenticated', 'service_role')
    role = payload.get("role", "authenticated")

    # Extract email and metadata if available (useful for context)
    email = payload.get("email")
    app_metadata = payload.get("app_metadata", {})
    user_metadata = payload.get("user_metadata", {})

    # Merge metadata for convenience
    metadata = {**app_metadata, **user_metadata}

    return UserContext(
        id=user_id,
        role=role,
        email=email,
        metadata=metadata
    )
