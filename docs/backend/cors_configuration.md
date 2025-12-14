# CORS Configuration

This document describes the CORS (Cross-Origin Resource Sharing) configuration for the PipeDesk Google API backend.

## Overview

The backend uses FastAPI's `CORSMiddleware` to handle CORS preflight requests and add appropriate headers to responses. This allows the frontend at `https://pipedesk.vercel.app` to make API calls to the backend at `https://google-api-xwhd.onrender.com`.

## Configuration

### Environment Variable

CORS origins are configured via the `CORS_ORIGINS` environment variable:

```bash
CORS_ORIGINS=https://pipedesk.vercel.app,http://localhost:5173,http://localhost:3000
```

### Default Origins

If `CORS_ORIGINS` is not set, the following default origins are allowed:

- `https://pipedesk.vercel.app` (Production frontend)
- `http://localhost:5173` (Vite default dev server)
- `http://localhost:3000` (Common dev server port)
- `http://localhost:8080` (Alternative dev server port)
- `http://127.0.0.1:5173`
- `http://127.0.0.1:3000`
- `http://127.0.0.1:8080`

### Allowed Methods

All standard HTTP methods are allowed:
- GET
- POST
- PUT
- PATCH
- DELETE
- OPTIONS
- HEAD

### Allowed Headers

All headers are allowed, including:
- `Content-Type`
- `Authorization` (for JWT tokens)
- Custom headers

### Credentials

`Access-Control-Allow-Credentials: true` is enabled, allowing cookies and authorization headers to be sent with requests.

## Verifying CORS with curl

### Test Preflight Request

```bash
# Test preflight for /api/drive/items from production frontend
curl -X OPTIONS \
  -H "Origin: https://pipedesk.vercel.app" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Content-Type, Authorization" \
  -v https://google-api-xwhd.onrender.com/api/drive/items 2>&1 | grep -i "access-control"
```

Expected response headers:
```
< access-control-allow-origin: https://pipedesk.vercel.app
< access-control-allow-credentials: true
< access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
< access-control-allow-headers: Content-Type, Authorization
< access-control-max-age: 600
```

### Test Preflight for Calendar API

```bash
curl -X OPTIONS \
  -H "Origin: https://pipedesk.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type, Authorization" \
  -v https://google-api-xwhd.onrender.com/api/calendar/events 2>&1 | grep -i "access-control"
```

### Test Actual Request with Origin Header

```bash
curl -X GET \
  -H "Origin: https://pipedesk.vercel.app" \
  -v https://google-api-xwhd.onrender.com/ 2>&1 | grep -i "access-control"
```

## Troubleshooting

### Error: CORS blocks requests from frontend

1. **Check Origin Header**: Ensure the frontend is sending the correct `Origin` header
2. **Check CORS_ORIGINS env var**: Verify the production URL is in the allowed origins list
3. **Check Preflight Response**: Use the curl commands above to verify preflight works

### Error: Preflight returns 400/403

1. **Origin not in allowed list**: Add the origin to `CORS_ORIGINS`
2. **Wildcard with credentials**: You cannot use `*` for origins when `allow_credentials=True`

### Error: Authorization header not allowed

This should not happen with the current configuration since `allow_headers=["*"]` is set. If it does:

1. Check that the middleware is added before routes
2. Verify no other middleware is stripping headers

## Testing

Run the CORS tests:

```bash
USE_MOCK_DRIVE=true python -m pytest tests/test_cors.py -v
```

The test suite covers:
- Production frontend origin (`https://pipedesk.vercel.app`)
- Localhost development origins
- Rejection of unauthorized origins
- Preflight with Authorization header
- All HTTP methods
- Calendar API endpoints

## Implementation Details

The CORS middleware is configured in `main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware
from config import config

# Parse CORS origins from config (comma-separated string)
origins = [origin.strip() for origin in config.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The middleware:
1. Intercepts OPTIONS preflight requests
2. Returns 200 with appropriate CORS headers
3. Adds CORS headers to actual requests from allowed origins
