"""
Retry utility with exponential backoff for Google API calls.
Handles transient errors (5xx, timeouts) with retry, 
and fails immediately on permanent errors (4xx except 429).
"""

import time
import logging
from typing import Callable, TypeVar, Optional, Type, Tuple
from functools import wraps

logger = logging.getLogger("pipedesk_drive.retry")

T = TypeVar('T')


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""
    pass


def exponential_backoff_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 32.0,
    exponential_base: float = 2.0,
    transient_error_codes: Tuple[int, ...] = (429, 500, 502, 503, 504),
    retriable_exceptions: Tuple[Type[Exception], ...] = (ConnectionError, TimeoutError),
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 32.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        transient_error_codes: HTTP status codes to retry (default: 429, 5xx)
        retriable_exceptions: Exception types to retry (default: ConnectionError, TimeoutError)
    
    Returns:
        Decorated function that will retry on transient errors
    
    Raises:
        RetryExhausted: When all retry attempts are exhausted
        Original exception: For permanent errors (4xx except 429)
    
    Example:
        @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
        def call_google_api():
            return service.events().list(...).execute()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None
            func_name = getattr(func, '__name__', '<function>')
            
            for attempt in range(max_retries + 1):
                try:
                    # Try executing the function
                    return func(*args, **kwargs)
                    
                except retriable_exceptions as e:
                    # Network/connection errors - retry
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Retriable exception in {func_name} (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                        delay = min(delay * exponential_base, max_delay)
                        continue
                    else:
                        logger.error(
                            f"Max retries exhausted for {func_name} after {max_retries + 1} attempts. "
                            f"Last error: {e}"
                        )
                        raise RetryExhausted(
                            f"Failed after {max_retries + 1} attempts. Last error: {e}"
                        ) from e
                
                except Exception as e:
                    # Check if it's a Google API error with status code
                    error_str = str(e)
                    status_code = None
                    
                    # Extract status code from Google API errors
                    # Format: "HttpError 503 when requesting..."
                    if "HttpError" in error_str:
                        try:
                            parts = error_str.split()
                            for i, part in enumerate(parts):
                                if part == "HttpError" and i + 1 < len(parts):
                                    status_code = int(parts[i + 1])
                                    break
                        except (ValueError, IndexError):
                            pass
                    
                    # Check for sync token expired (410)
                    if "410" in error_str or "sync token is no longer valid" in error_str.lower():
                        # 410 Gone - sync token expired, don't retry but re-raise for special handling
                        logger.warning(f"Sync token expired (410) in {func_name}. Re-raising for special handling.")
                        raise
                    
                    # Check if it's a transient error
                    if status_code and status_code in transient_error_codes:
                        last_exception = e
                        if attempt < max_retries:
                            logger.warning(
                                f"Transient error {status_code} in {func_name} "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {e}. "
                                f"Retrying in {delay}s..."
                            )
                            time.sleep(delay)
                            delay = min(delay * exponential_base, max_delay)
                            continue
                        else:
                            logger.error(
                                f"Max retries exhausted for {func_name} after {max_retries + 1} attempts. "
                                f"Last error: {e}"
                            )
                            raise RetryExhausted(
                                f"Failed after {max_retries + 1} attempts. Last error: {e}"
                            ) from e
                    else:
                        # Permanent error (4xx except 429, 410) - fail immediately
                        if status_code and 400 <= status_code < 500:
                            logger.error(
                                f"Permanent client error {status_code} in {func_name}. "
                                f"Not retrying: {e}"
                            )
                        else:
                            logger.error(f"Unexpected error in {func_name}: {e}")
                        raise
            
            # This should not be reached, but just in case
            raise RetryExhausted(
                f"Failed after {max_retries + 1} attempts. Last error: {last_exception}"
            )
        
        return wrapper
    return decorator


def retry_on_transient_errors(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    *args,
    **kwargs
) -> T:
    """
    Function-based retry wrapper (alternative to decorator).
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        *args: Arguments to pass to func
        **kwargs: Keyword arguments to pass to func
    
    Returns:
        Result of func(*args, **kwargs)
    
    Example:
        result = retry_on_transient_errors(
            service.events().list,
            max_retries=3,
            calendarId='primary',
            timeMin=time_min
        )
    """
    decorated_func = exponential_backoff_retry(
        max_retries=max_retries,
        initial_delay=initial_delay
    )(func)
    return decorated_func(*args, **kwargs)
