"""
Tests for JWT defensive coding enhancements.

These tests verify that the JWT authentication system properly handles edge cases,
missing configuration, and unexpected errors with appropriate logging and error handling.
"""

import pytest
import logging
from unittest.mock import MagicMock, patch, Mock
from fastapi import HTTPException
import jwt as pyjwt

from auth.jwt import verify_supabase_jwt, UserContext
from auth.dependencies import get_current_user


class TestJWTDefensiveCoding:
    """Test defensive coding in JWT authentication"""

    @patch('auth.jwt.config')
    @patch('auth.jwt.logger')
    def test_missing_jwt_secret_logs_critical(self, mock_logger, mock_config):
        """Test that missing JWT secret logs a CRITICAL message"""
        # Setup: No JWT secret configured
        mock_config.SUPABASE_JWT_SECRET = None
        
        # Execute
        result = verify_supabase_jwt("some.token.here")
        
        # Verify: Should return None (fallback to legacy auth)
        assert result is None
        
        # Verify: Should log CRITICAL message
        mock_logger.critical.assert_called_once()
        critical_call = mock_logger.critical.call_args[0][0]
        assert "FATAL" in critical_call
        assert "SUPABASE_JWT_SECRET" in critical_call
        
        # Verify: Should also log WARNING about fallback
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "JWT authentication is disabled" in warning_call

    @patch('auth.jwt.config')
    @patch('auth.jwt.logger')
    def test_empty_jwt_secret_logs_critical(self, mock_logger, mock_config):
        """Test that empty JWT secret logs a CRITICAL message"""
        # Setup: Empty JWT secret
        mock_config.SUPABASE_JWT_SECRET = "   "  # whitespace only
        
        # Execute
        result = verify_supabase_jwt("some.token.here")
        
        # Verify: Should return None (fallback to legacy auth)
        assert result is None
        
        # Verify: Should log CRITICAL message
        mock_logger.critical.assert_called_once()
        assert "FATAL" in mock_logger.critical.call_args[0][0]

    @patch('auth.jwt.config')
    @patch('auth.jwt.logger')
    @patch('auth.jwt.jwt.decode')
    def test_unexpected_exception_during_decode_logs_error(self, mock_decode, mock_logger, mock_config):
        """Test that unexpected exceptions during jwt.decode are properly logged"""
        # Setup: Valid secret but jwt.decode raises unexpected error
        mock_config.SUPABASE_JWT_SECRET = "test-secret-key-12345"
        mock_decode.side_effect = ValueError("Unexpected error from jwt library")
        
        # Execute & Verify: Should raise the exception
        with pytest.raises(ValueError, match="Unexpected error"):
            verify_supabase_jwt("some.token.here")
        
        # Verify: Should log error with "JWT Decode Crash"
        error_logged = False
        for call in mock_logger.error.call_args_list:
            if call[0] and "JWT Decode Crash" in str(call[0][0]):
                error_logged = True
                break
        assert error_logged, "Expected 'JWT Decode Crash' to be logged"
        
        # Verify: Should log full exception traceback
        mock_logger.exception.assert_called_once()

    @patch('auth.jwt.config')
    @patch('auth.jwt.logger')
    @patch('auth.jwt.jwt.decode')
    def test_expired_signature_error_logged(self, mock_decode, mock_logger, mock_config):
        """Test that ExpiredSignatureError is properly logged"""
        # Setup: Valid secret but token is expired
        mock_config.SUPABASE_JWT_SECRET = "test-secret-key-12345"
        mock_decode.side_effect = pyjwt.ExpiredSignatureError("Token expired")
        
        # Execute & Verify: Should raise the exception
        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_supabase_jwt("expired.token.here")
        
        # Verify: Should log error message
        error_logged = False
        for call in mock_logger.error.call_args_list:
            if call[0] and "Token has expired" in str(call[0][0]):
                error_logged = True
                break
        assert error_logged, "Expected expired token error to be logged"


class TestDependenciesDefensiveCoding:
    """Test defensive coding in auth dependencies"""

    @pytest.mark.asyncio
    @patch('auth.dependencies.verify_supabase_jwt')
    @patch('auth.dependencies.logger')
    async def test_unexpected_jwt_error_logs_full_traceback(self, mock_logger, mock_verify):
        """Test that unexpected JWT errors log full traceback in dependencies"""
        # Setup: verify_supabase_jwt raises unexpected error
        mock_verify.side_effect = RuntimeError("Unexpected runtime error")
        
        # Execute & Verify: Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer fake.token.here")
        
        # Verify: Should be a 401 error
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail
        
        # Verify: Should log error message with str(e)
        error_logged = False
        for call in mock_logger.error.call_args_list:
            if call[0] and "Unexpected JWT Error" in str(call[0][0]):
                error_logged = True
                break
        assert error_logged, "Expected 'Unexpected JWT Error' to be logged"
        
        # Verify: Should log full exception traceback
        exception_logged = False
        for call in mock_logger.exception.call_args_list:
            if call[0] and "Full traceback" in str(call[0][0]):
                exception_logged = True
                break
        assert exception_logged, "Expected full traceback to be logged"

    @pytest.mark.asyncio
    @patch('auth.dependencies.verify_supabase_jwt')
    @patch('auth.dependencies.logger')
    async def test_expired_token_returns_401(self, mock_logger, mock_verify):
        """Test that expired JWT token returns 401 with proper error message"""
        # Setup: verify_supabase_jwt raises ExpiredSignatureError
        mock_verify.side_effect = pyjwt.ExpiredSignatureError("Token expired")
        
        # Execute & Verify: Should raise HTTPException with 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer expired.token.here")
        
        # Verify: Should be a 401 error with proper message
        assert exc_info.value.status_code == 401
        assert "Token has expired" in exc_info.value.detail
        
        # Verify: Error should be logged
        error_logged = False
        for call in mock_logger.error.call_args_list:
            if call[0] and "Token has expired" in str(call[0][0]):
                error_logged = True
                break
        assert error_logged

    @pytest.mark.asyncio
    @patch('auth.dependencies.verify_supabase_jwt')
    async def test_legacy_auth_fallback_when_jwt_secret_missing(self, mock_verify):
        """Test that legacy auth works when JWT secret is not configured"""
        # Setup: verify_supabase_jwt returns None (JWT secret not configured)
        mock_verify.return_value = None
        
        # Execute: Try with JWT token but fall back to legacy headers
        result = await get_current_user(
            authorization="Bearer fake.token.here",
            x_user_id="user-123",
            x_user_role="admin"
        )
        
        # Verify: Should fall back to legacy auth
        assert result is not None
        assert result.id == "user-123"
        assert result.role == "admin"

    @pytest.mark.asyncio
    @patch('auth.dependencies.verify_supabase_jwt')
    async def test_no_credentials_returns_401(self, mock_verify):
        """Test that missing credentials returns 401"""
        # Execute & Verify: Should raise HTTPException with 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None, x_user_id=None, x_user_role=None)
        
        # Verify: Should be a 401 error
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail


class TestJWTValidToken:
    """Test JWT with valid configuration"""

    @patch('auth.jwt.config')
    @patch('auth.jwt.jwt.decode')
    def test_valid_jwt_token_returns_user_context(self, mock_decode, mock_config):
        """Test that valid JWT token returns proper UserContext"""
        # Setup: Valid secret and valid token
        mock_config.SUPABASE_JWT_SECRET = "test-secret-key-12345"
        mock_decode.return_value = {
            "sub": "user-uuid-123",
            "role": "authenticated",
            "email": "test@example.com",
            "app_metadata": {"provider": "email"},
            "user_metadata": {"name": "Test User"}
        }
        
        # Execute
        result = verify_supabase_jwt("valid.jwt.token")
        
        # Verify: Should return UserContext with proper data
        assert result is not None
        assert isinstance(result, UserContext)
        assert result.id == "user-uuid-123"
        assert result.role == "authenticated"
        assert result.email == "test@example.com"
        assert result.metadata is not None
        assert result.metadata["provider"] == "email"
        assert result.metadata["name"] == "Test User"

    @patch('auth.jwt.config')
    @patch('auth.jwt.jwt.decode')
    def test_jwt_token_missing_sub_raises_error(self, mock_decode, mock_config):
        """Test that JWT token without 'sub' claim raises error"""
        # Setup: Valid secret but token missing 'sub' claim
        mock_config.SUPABASE_JWT_SECRET = "test-secret-key-12345"
        mock_decode.return_value = {
            "role": "authenticated",
            "email": "test@example.com"
        }
        
        # Execute & Verify: Should raise InvalidTokenError
        with pytest.raises(pyjwt.InvalidTokenError, match="missing 'sub' claim"):
            verify_supabase_jwt("invalid.token.nosub")
