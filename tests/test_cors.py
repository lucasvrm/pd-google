"""
Tests for CORS configuration.

This tests that the CORS middleware is configured correctly and allows
requests from the expected origins.
"""

import pytest
from fastapi.testclient import TestClient
import os

# Required HTTP methods for API operations
REQUIRED_HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def test_cors_allows_production_frontend():
    """Test that CORS allows requests from production frontend"""
    # Import after setting environment to ensure config is loaded correctly
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Simulate a preflight request from production frontend
    response = client.options(
        "/api/drive/items",
        headers={
            "Origin": "https://pipedesk.vercel.app",
            "Access-Control-Request-Method": "GET",
        }
    )
    
    # CORS preflight should be handled by middleware before route handlers
    # FastAPI returns 200 for valid OPTIONS requests
    assert response.status_code == 200
    
    # Check that CORS headers are present
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "https://pipedesk.vercel.app"


def test_cors_allows_localhost():
    """Test that CORS allows requests from localhost"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Simulate a preflight request from localhost
    response = client.options(
        "/api/drive/items",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        }
    )
    
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unauthorized_origin():
    """Test that CORS rejects requests from unauthorized origins"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Simulate a preflight request from an unauthorized origin
    response = client.options(
        "/api/drive/items",
        headers={
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        }
    )
    
    # Request should be rejected (no CORS header or different origin)
    # The response might be 200 but without the CORS headers
    # OR FastAPI might return an error
    # We check that it doesn't return the malicious origin in the header
    if "access-control-allow-origin" in response.headers:
        assert response.headers["access-control-allow-origin"] != "https://malicious-site.com"


def test_cors_custom_origins_from_env():
    """Test that CORS_ORIGINS environment variable is respected"""
    # This test verifies that the CORS_ORIGINS configuration can be customized
    # We can't easily test this in the same process due to module caching,
    # but we can verify the default includes the production URL
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from config import config
    
    # Verify that the default CORS_ORIGINS includes production frontend
    assert "https://pipedesk.vercel.app" in config.CORS_ORIGINS
    # Verify that it's comma-separated and can be split
    origins = [o.strip() for o in config.CORS_ORIGINS.split(",")]
    assert len(origins) >= 1
    assert "https://pipedesk.vercel.app" in origins


def test_cors_headers_on_actual_request():
    """Test that CORS headers are present on actual GET request"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Make an actual GET request to root endpoint (no auth required)
    response = client.get(
        "/",
        headers={
            "Origin": "https://pipedesk.vercel.app"
        }
    )
    
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "https://pipedesk.vercel.app"


def test_cors_preflight_with_authorization_header():
    """Test that CORS preflight allows Authorization header"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Simulate a preflight request with Authorization header (common for JWT auth)
    response = client.options(
        "/api/drive/items",
        headers={
            "Origin": "https://pipedesk.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        }
    )
    
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "https://pipedesk.vercel.app"
    assert "access-control-allow-headers" in response.headers
    # Check that Authorization is in the allowed headers
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


def test_cors_preflight_calendar_events():
    """Test that CORS preflight works for calendar/events endpoint"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Test preflight for POST to calendar/events (creating events)
    response = client.options(
        "/api/calendar/events",
        headers={
            "Origin": "https://pipedesk.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        }
    )
    
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "https://pipedesk.vercel.app"
    assert "access-control-allow-credentials" in response.headers
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_allows_all_required_methods():
    """Test that CORS preflight allows all HTTP methods needed for quick actions"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    for method in REQUIRED_HTTP_METHODS:
        response = client.options(
            "/api/drive/items",
            headers={
                "Origin": "https://pipedesk.vercel.app",
                "Access-Control-Request-Method": method,
            }
        )
        
        assert response.status_code == 200, f"Preflight failed for method {method}"
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        assert method in allowed_methods, f"Method {method} not in allowed methods: {allowed_methods}"


def test_cors_allows_localhost_3000():
    """Test that CORS allows requests from localhost:3000 (common dev port)"""
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    from main import app
    
    client = TestClient(app)
    
    # Simulate a preflight request from localhost:3000
    response = client.options(
        "/api/drive/items",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
    )
    
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


# ------------------------------------------------------------
# CORS Origin Normalization Tests
# ------------------------------------------------------------

def test_normalize_cors_origins_basic():
    """Test basic origin normalization"""
    from config import normalize_cors_origins
    
    result = normalize_cors_origins("https://example.com, http://localhost:3000")
    assert result == ["https://example.com", "http://localhost:3000"]


def test_normalize_cors_origins_with_whitespace():
    """Test origin normalization with extra whitespace"""
    from config import normalize_cors_origins
    
    result = normalize_cors_origins("  https://example.com  ,   http://localhost:3000   ")
    assert result == ["https://example.com", "http://localhost:3000"]


def test_normalize_cors_origins_with_quotes():
    """Test origin normalization with quoted entries"""
    from config import normalize_cors_origins
    
    # Double quotes
    result = normalize_cors_origins('"https://example.com", "http://localhost:3000"')
    assert result == ["https://example.com", "http://localhost:3000"]
    
    # Single quotes
    result = normalize_cors_origins("'https://example.com', 'http://localhost:3000'")
    assert result == ["https://example.com", "http://localhost:3000"]


def test_normalize_cors_origins_with_trailing_slashes():
    """Test origin normalization removes trailing slashes"""
    from config import normalize_cors_origins
    
    result = normalize_cors_origins("https://example.com/, http://localhost:3000/")
    assert result == ["https://example.com", "http://localhost:3000"]
    
    # Multiple trailing slashes
    result = normalize_cors_origins("https://example.com///")
    assert result == ["https://example.com"]


def test_normalize_cors_origins_filters_empty_entries():
    """Test origin normalization filters out empty entries"""
    from config import normalize_cors_origins
    
    result = normalize_cors_origins("https://example.com, , ,  , http://localhost:3000")
    assert result == ["https://example.com", "http://localhost:3000"]


def test_normalize_cors_origins_empty_string():
    """Test origin normalization with empty string"""
    from config import normalize_cors_origins
    
    result = normalize_cors_origins("")
    assert result == []


def test_normalize_cors_origins_combined_edge_cases():
    """Test origin normalization with combined edge cases"""
    from config import normalize_cors_origins
    
    # Combines: whitespace, quotes, trailing slashes, and empty entries
    result = normalize_cors_origins('  "https://example.com/"  , \'http://localhost:3000/\' , ,  ')
    assert result == ["https://example.com", "http://localhost:3000"]
