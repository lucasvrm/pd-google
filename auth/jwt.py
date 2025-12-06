import os
import jwt
from dataclasses import dataclass
from typing import Optional, Dict, Any

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
        UserContext: A dataclass containing the user ID and role, or None if JWT secret is not configured.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid (bad signature, etc).
    """
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        # JWT authentication is not configured, return None to allow fallback to legacy auth
        return None

    # Supabase uses HS256 by default
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_aud": False} # Supabase aud is usually 'authenticated', but can vary.
                                      # We can verify it if we knew the expected value.
                                      # Commonly it is "authenticated" but let's be lenient or check specific config if needed.
    )

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
