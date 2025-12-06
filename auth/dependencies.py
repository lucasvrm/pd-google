from fastapi import Header, HTTPException, Depends
from typing import Optional
from auth.jwt import verify_supabase_jwt, UserContext
import jwt
import logging

logger = logging.getLogger("pipedesk.auth")

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
) -> UserContext:
    """
    Dependency to get the current user.
    Prioritizes 'Authorization: Bearer <token>'.
    Falls back to 'x-user-id' and 'x-user-role' headers for legacy compatibility.
    """

    # 1. Try JWT Authentication
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                user_context = verify_supabase_jwt(token)
                if user_context is not None:
                    # JWT verification succeeded
                    return user_context
                # JWT secret not configured, log warning and fall through to legacy auth
                logger.warning("JWT token provided but SUPABASE_JWT_SECRET not configured, falling back to legacy authentication")
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired")
            except jwt.InvalidTokenError as e:
                raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected JWT Error: {e}")
                raise HTTPException(status_code=401, detail="Could not validate credentials")

    # 2. Fallback to Legacy Headers
    if x_user_id:
        # In legacy mode, we trust the gateway/frontend provided headers
        # This is temporary until full migration
        return UserContext(
            id=x_user_id,
            role=x_user_role or "authenticated"
        )

    # 3. No credentials provided
    raise HTTPException(
        status_code=401,
        detail="Not authenticated. Missing Authorization header or x-user-id header."
    )
