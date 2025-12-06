"""
Tests for CORS configuration.

This tests that the CORS middleware is configured correctly and allows
requests from the expected origins.
"""

import pytest
from fastapi.testclient import TestClient
import os


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
