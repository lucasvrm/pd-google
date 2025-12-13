from fastapi import Header, HTTPException, Depends
from typing import Optional, List, Callable
from auth.jwt import verify_supabase_jwt, UserContext
import jwt
import logging

logger = logging.getLogger("pipedesk.auth")

# Role hierarchy: higher index = more privileges
# This defines which roles can access which endpoints
# Note: Some roles have variants (e.g., 'new_business' and 'newbusiness') for backward
# compatibility with different naming conventions used in various parts of the system.
ROLE_HIERARCHY = {
    "admin": 100,
    "superadmin": 100,       # Variant of admin
    "super_admin": 100,      # Variant of admin
    "manager": 75,
    "analyst": 50,
    "new_business": 50,      # Preferred format
    "newbusiness": 50,       # Legacy format - kept for compatibility
    "sales": 50,
    "authenticated": 25,
    "viewer": 10,
    "client": 10,
    "customer": 10,
    "reader": 10,
}

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
                logger.error("JWT validation failed: Token has expired")
                raise HTTPException(status_code=401, detail="Token has expired")
            except jwt.InvalidSignatureError as e:
                logger.error(f"JWT validation failed: Signature verification failed - {e}")
                raise HTTPException(status_code=401, detail="Invalid token: Signature verification failed")
            except jwt.InvalidAudienceError as e:
                logger.error(f"JWT validation failed: Audience mismatch - {e}")
                raise HTTPException(status_code=401, detail="Invalid token: Audience mismatch")
            except jwt.DecodeError as e:
                logger.error(f"JWT validation failed: Token decode error - {e}")
                raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            except jwt.InvalidTokenError as e:
                logger.error(f"JWT validation failed: Invalid token - {e}")
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


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
) -> Optional[UserContext]:
    """
    Best-effort variant of get_current_user.
    Returns None when no credentials are provided, otherwise enforces the same validation.
    """
    if not authorization and not x_user_id:
        return None

    return await get_current_user(
        authorization=authorization,
        x_user_id=x_user_id,
        x_user_role=x_user_role,
    )


def _check_role_access(user_role: str, required_roles: List[str]) -> bool:
    """
    Check if the user's role satisfies the required roles.
    
    If required_roles is empty, any authenticated user is allowed.
    Otherwise, the user must have one of the required roles OR a role
    with higher privilege level in the hierarchy.
    
    Args:
        user_role: The user's current role
        required_roles: List of roles that are allowed to access the resource
        
    Returns:
        True if access is granted, False otherwise
    """
    if not required_roles:
        return True
    
    user_role_lower = user_role.lower() if user_role else ""
    user_level = ROLE_HIERARCHY.get(user_role_lower, 0)
    
    # Check if user has one of the required roles directly
    for required_role in required_roles:
        required_role_lower = required_role.lower()
        if user_role_lower == required_role_lower:
            return True
        
        # Also check if user has higher privilege than required
        required_level = ROLE_HIERARCHY.get(required_role_lower, 0)
        if user_level >= required_level and user_level > 0:
            return True
    
    return False


def get_current_user_with_role(required_roles: List[str]) -> Callable:
    """
    Factory function that creates a dependency to get the current user
    and validate they have one of the required roles.
    
    This implements RBAC (Role-Based Access Control) by checking the user's
    role against a list of allowed roles. The check also considers role
    hierarchy - a user with admin role can access endpoints requiring manager.
    
    Usage:
        @router.delete("/some-endpoint")
        def delete_something(
            current_user: UserContext = Depends(get_current_user_with_role(["admin", "manager"]))
        ):
            # Only admin or manager can access this
            pass
    
    Args:
        required_roles: List of roles that are allowed to access the endpoint.
                       Common values: ["admin"], ["admin", "manager"], etc.
                       
    Returns:
        A FastAPI dependency that returns UserContext if authorized,
        or raises HTTPException 403 if not authorized.
        
    Raises:
        HTTPException 401: If user is not authenticated
        HTTPException 403: If user doesn't have required role
    """
    async def _get_user_with_role_check(
        current_user: UserContext = Depends(get_current_user)
    ) -> UserContext:
        if not _check_role_access(current_user.role, required_roles):
            logger.warning(
                f"Access denied: user {current_user.id} with role '{current_user.role}' "
                f"attempted to access endpoint requiring one of {required_roles}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role(s): {', '.join(required_roles)}. "
                       f"Your role: {current_user.role}"
            )
        return current_user
    
    return _get_user_with_role_check


# Convenience dependencies for common role requirements
async def require_admin(
    current_user: UserContext = Depends(get_current_user_with_role(["admin", "superadmin", "super_admin"]))
) -> UserContext:
    """
    Dependency that requires admin-level access.
    Use for sensitive operations like user management, system configuration, etc.
    """
    return current_user


async def require_manager_or_above(
    current_user: UserContext = Depends(get_current_user_with_role(["admin", "superadmin", "super_admin", "manager"]))
) -> UserContext:
    """
    Dependency that requires manager-level access or above.
    Use for team management, approval workflows, destructive operations.
    """
    return current_user


async def require_writer_or_above(
    current_user: UserContext = Depends(
        get_current_user_with_role(["admin", "superadmin", "super_admin", "manager", "analyst", "new_business", "newbusiness", "sales"])
    )
) -> UserContext:
    """
    Dependency that requires write access (sales/analyst level or above).
    Use for creating, updating, or deleting resources.
    """
    return current_user
