"""
Retry utilities for transient failures.
"""

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_ERRORS = (
    "connection refused",
    "connection reset",
    "connection timed out",
    "timeout expired",
    "network is unreachable",
    "temporary failure",
    "too many connections",
    "server closed the connection",
    "ssl connection has been closed",
    "could not connect to server",
)


def is_retryable(error: Exception) -> bool:
    """Check if an error is retryable."""
    msg = str(error).lower()
    return any(phrase in msg for phrase in RETRYABLE_ERRORS)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 30.0,
) -> Callable:
    """
    Decorator for retrying functions on transient failures.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        max_delay: Maximum delay between retries
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt == max_attempts or not is_retryable(e):
                        raise

                    fn_name = getattr(func, "__name__", "function")
                    log.warning(
                        f"{fn_name} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay = min(current_delay * backoff, max_delay)

            raise last_error  # Should never reach here

        return wrapper
    return decorator
