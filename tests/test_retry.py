"""
Tests for retry utility with exponential backoff.
"""

import pytest
import time
from unittest.mock import Mock
from utils.retry import exponential_backoff_retry, RetryExhausted, retry_on_transient_errors


def test_retry_success_on_first_attempt():
    """Test that function succeeds on first attempt without retry."""
    mock_func = Mock(return_value="success")
    decorated = exponential_backoff_retry()(mock_func)
    
    result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 1


def test_retry_success_after_transient_error():
    """Test that function succeeds after transient error with retry."""
    mock_func = Mock(side_effect=[
        Exception("HttpError 503 when requesting..."),
        "success"
    ])
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    
    result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_exhausted_after_max_retries():
    """Test that RetryExhausted is raised after max retries."""
    mock_func = Mock(side_effect=Exception("HttpError 503 when requesting..."))
    
    decorated = exponential_backoff_retry(max_retries=2, initial_delay=0.1)(mock_func)
    
    with pytest.raises(RetryExhausted) as exc_info:
        decorated()
    
    assert "Failed after 3 attempts" in str(exc_info.value)
    assert mock_func.call_count == 3  # initial + 2 retries


def test_retry_permanent_error_no_retry():
    """Test that permanent errors (4xx except 429) are not retried."""
    mock_func = Mock(side_effect=Exception("HttpError 404 when requesting..."))
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    
    with pytest.raises(Exception) as exc_info:
        decorated()
    
    assert "HttpError 404" in str(exc_info.value)
    assert mock_func.call_count == 1  # No retries


def test_retry_410_sync_token_expired():
    """Test that 410 errors (sync token expired) are re-raised without retry."""
    mock_func = Mock(side_effect=Exception("HttpError 410 sync token is no longer valid"))
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    
    with pytest.raises(Exception) as exc_info:
        decorated()
    
    assert "410" in str(exc_info.value)
    assert mock_func.call_count == 1  # No retries for 410


def test_retry_429_rate_limit():
    """Test that 429 (rate limit) errors are retried."""
    mock_func = Mock(side_effect=[
        Exception("HttpError 429 when requesting..."),
        "success"
    ])
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    
    result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_connection_error():
    """Test that connection errors are retried."""
    mock_func = Mock(side_effect=[
        ConnectionError("Connection refused"),
        "success"
    ])
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    
    result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_timeout_error():
    """Test that timeout errors are retried."""
    mock_func = Mock(side_effect=[
        TimeoutError("Request timed out"),
        "success"
    ])
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    
    result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_exponential_backoff_timing():
    """Test that delays follow exponential backoff pattern."""
    mock_func = Mock(side_effect=[
        Exception("HttpError 503 when requesting..."),
        Exception("HttpError 503 when requesting..."),
        "success"
    ])
    
    start_time = time.time()
    decorated = exponential_backoff_retry(
        max_retries=3,
        initial_delay=0.1,
        exponential_base=2.0
    )(mock_func)
    
    result = decorated()
    elapsed = time.time() - start_time
    
    # Should have delays: 0.1s + 0.2s = 0.3s minimum
    assert result == "success"
    assert mock_func.call_count == 3
    assert elapsed >= 0.3  # At least the sum of delays


def test_retry_max_delay_cap():
    """Test that delay is capped at max_delay."""
    mock_func = Mock(side_effect=[
        Exception("HttpError 503 when requesting..."),
        Exception("HttpError 503 when requesting..."),
        Exception("HttpError 503 when requesting..."),
        "success"
    ])
    
    start_time = time.time()
    decorated = exponential_backoff_retry(
        max_retries=4,
        initial_delay=1.0,
        max_delay=2.0,
        exponential_base=10.0  # Would cause large delays without cap
    )(mock_func)
    
    result = decorated()
    elapsed = time.time() - start_time
    
    # Delays: 1s, 2s (capped), 2s (capped), 2s (capped) = 7s total minimum
    # But with our cap of 2.0, it should be: 1s + 2s + 2s = 5s
    assert result == "success"
    assert mock_func.call_count == 4
    assert elapsed >= 5.0
    assert elapsed < 10.0  # Should not reach exponential growth


def test_retry_function_based_wrapper():
    """Test the function-based retry wrapper."""
    mock_func = Mock(side_effect=[
        Exception("HttpError 503 when requesting..."),
        "success"
    ])
    
    result = retry_on_transient_errors(
        mock_func,
        max_retries=3,
        initial_delay=0.1
    )
    
    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_with_args_and_kwargs():
    """Test that decorated functions preserve args and kwargs."""
    def test_func(a, b, c=None):
        if c == "fail":
            raise Exception("HttpError 503 when requesting...")
        return f"{a}-{b}-{c}"
    
    mock_func = Mock(side_effect=test_func)
    decorated = exponential_backoff_retry(max_retries=2, initial_delay=0.1)(mock_func)
    
    # This should succeed
    result = decorated("arg1", "arg2", c="success")
    assert result == "arg1-arg2-success"
    
    # This should retry and then fail
    mock_func.side_effect = test_func
    with pytest.raises(RetryExhausted):
        decorated("arg1", "arg2", c="fail")


def test_retry_500_errors():
    """Test that 500 errors are retried."""
    mock_func = Mock(side_effect=[
        Exception("HttpError 500 Internal Server Error"),
        "success"
    ])
    
    decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
    result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_502_503_504_errors():
    """Test that 502, 503, 504 errors are retried."""
    for status_code in [502, 503, 504]:
        mock_func = Mock(side_effect=[
            Exception(f"HttpError {status_code} when requesting..."),
            "success"
        ])
        
        decorated = exponential_backoff_retry(max_retries=3, initial_delay=0.1)(mock_func)
        result = decorated()
        
        assert result == "success"
        assert mock_func.call_count == 2


def test_retry_preserves_function_name():
    """Test that decorator preserves original function name and docstring."""
    def original_func():
        """Original docstring."""
        return "result"
    
    decorated = exponential_backoff_retry()(original_func)
    
    assert decorated.__name__ == "original_func"
    assert decorated.__doc__ == "Original docstring."
