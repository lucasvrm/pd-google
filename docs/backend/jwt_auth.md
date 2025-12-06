# JWT Authentication

This document describes the JWT authentication mechanism implemented in the `pd-google` backend service. It supports Supabase JWT tokens and provides backward compatibility for legacy header-based authentication.

## Configuration

To enable JWT verification, you must set the following environment variable:

- `SUPABASE_JWT_SECRET`: The JWT Secret from your Supabase project settings (Project Settings -> API -> JWT Settings -> JWT Secret).

## Implementation Details

The authentication logic is located in the `auth/` directory:

- `auth/jwt.py`: Handles low-level JWT decoding and verification.
- `auth/dependencies.py`: Provides the FastAPI dependency `get_current_user`.

### UserContext

The system uses a `UserContext` dataclass to represent the authenticated user:

```python
@dataclass
class UserContext:
    id: str                  # The user's UUID (sub claim)
    role: str                # The user's role (usually 'authenticated')
    email: Optional[str]     # User's email if present in token
    metadata: Optional[Dict] # Merged app_metadata and user_metadata
```

### Validation Flow (`get_current_user`)

1.  **Bearer Token Check**: The system first checks for an `Authorization: Bearer <token>` header.
    -   If found, it calls `verify_supabase_jwt(token)`.
    -   Validates signature using `HS256` and `SUPABASE_JWT_SECRET`.
    -   Checks expiration (`exp`).
    -   If valid, returns `UserContext`.
    -   If invalid/expired, raises `401 Unauthorized`.

2.  **Legacy Fallback**: If no Bearer token is present, it checks for `x-user-id` and `x-user-role` headers.
    -   If `x-user-id` is present, it creates a `UserContext` using these values.
    -   This ensures existing frontend code continues to work without changes.

3.  **Failure**: If neither are present, raises `401 Unauthorized`.

## Usage in FastAPI

To protect a route, inject the `get_current_user` dependency:

```python
from fastapi import APIRouter, Depends
from auth.dependencies import get_current_user
from auth.jwt import UserContext

router = APIRouter()

@router.get("/protected-route")
def protected_route(user: UserContext = Depends(get_current_user)):
    return {
        "message": f"Hello, user {user.id}",
        "role": user.role
    }
```

## Example Requests

### 1. Using JWT (Recommended)

```http
GET /some/path HTTP/1.1
Authorization: Bearer <SUPABASE_JWT_TOKEN>
```

### 2. Using Legacy Headers (Deprecated)

```http
GET /some/path HTTP/1.1
x-user-id: 123e4567-e89b-12d3-a456-426614174000
x-user-role: authenticated
```
