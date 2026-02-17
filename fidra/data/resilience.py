"""Resilience layer for cloud database operations.

Provides retry logic, error classification, and user-friendly error messages
for handling transient network failures gracefully.
"""

import asyncio
import logging
from enum import Enum
from functools import wraps
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorCategory(Enum):
    """Classification of database errors for retry decisions."""

    TRANSIENT = "transient"  # Network issues, timeouts - safe to retry
    PERMANENT = "permanent"  # Auth errors, syntax errors - don't retry
    CONFLICT = "conflict"  # Version mismatch - needs resolution


# asyncpg error types that are transient (safe to retry)
TRANSIENT_ERROR_TYPES = (
    "ConnectionRefusedError",
    "ConnectionResetError",
    "TimeoutError",
    "asyncio.TimeoutError",
    "OSError",
    "ConnectionDoesNotExistError",
    "InterfaceError",
    "InterfaceWarning",
    "TooManyConnectionsError",
)

# asyncpg error messages indicating transient issues
TRANSIENT_ERROR_MESSAGES = (
    "connection is closed",
    "connection was closed",
    "timeout",
    "network",
    "connection refused",
    "connection reset",
    "broken pipe",
    "no route to host",
    "connection timed out",
    "pool is closed",
    "cannot perform operation",
)

# Error messages indicating permanent failures
PERMANENT_ERROR_MESSAGES = (
    "authentication failed",
    "password authentication failed",
    "permission denied",
    "access denied",
    "invalid password",
    "syntax error",
    "does not exist",
    "already exists",
    "violates",
    "invalid input",
)


def classify_error(exception: Exception) -> ErrorCategory:
    """Classify an exception to determine retry behavior.

    Args:
        exception: The exception to classify

    Returns:
        ErrorCategory indicating whether to retry, fail, or resolve conflict
    """
    error_type = type(exception).__name__
    error_msg = str(exception).lower()

    # Check for version conflict (custom error)
    if "ConcurrencyError" in error_type or "version" in error_msg:
        return ErrorCategory.CONFLICT

    # Check error type name
    for transient_type in TRANSIENT_ERROR_TYPES:
        if transient_type in error_type:
            return ErrorCategory.TRANSIENT

    # Check error message for transient indicators
    for indicator in TRANSIENT_ERROR_MESSAGES:
        if indicator in error_msg:
            return ErrorCategory.TRANSIENT

    # Check error message for permanent indicators
    for indicator in PERMANENT_ERROR_MESSAGES:
        if indicator in error_msg:
            return ErrorCategory.PERMANENT

    # Default: assume transient for unknown errors (safer to retry)
    # But log it so we can add explicit handling
    logger.warning(f"Unknown error type {error_type}: {exception}")
    return ErrorCategory.TRANSIENT


def get_user_message(exception: Exception) -> str:
    """Get a user-friendly error message for an exception.

    Args:
        exception: The exception to describe

    Returns:
        Human-readable error message
    """
    error_msg = str(exception).lower()
    category = classify_error(exception)

    if category == ErrorCategory.CONFLICT:
        return (
            "This record was modified by another user. "
            "Please refresh and try again."
        )

    # Connection issues
    if any(x in error_msg for x in ("connection", "network", "refused", "reset")):
        return (
            "Unable to connect to the server. "
            "Please check your internet connection."
        )

    # Timeout
    if "timeout" in error_msg:
        return (
            "The server took too long to respond. "
            "Please try again."
        )

    # Authentication
    if any(x in error_msg for x in ("authentication", "password", "permission")):
        return (
            "Authentication failed. "
            "Please check your server credentials in Settings."
        )

    # Pool exhausted
    if "too many connections" in error_msg or "pool" in error_msg:
        return (
            "Server is busy. "
            "Please wait a moment and try again."
        )

    # Generic fallback
    if category == ErrorCategory.PERMANENT:
        return f"Operation failed: {exception}"

    return "A temporary error occurred. Please try again."


async def with_retry(
    operation: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    on_retry: Optional[Callable[[int, float, Exception], None]] = None,
) -> T:
    """Execute an async operation with exponential backoff retry.

    Args:
        operation: Async callable to execute
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay between retries in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 10.0)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        on_retry: Optional callback(attempt, delay, error) called before each retry

    Returns:
        Result of the operation

    Raises:
        Exception: The last exception if all retries fail, or immediately
                   for permanent errors
    """
    last_exception: Optional[Exception] = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as e:
            last_exception = e
            category = classify_error(e)

            # Don't retry permanent errors or conflicts
            if category in (ErrorCategory.PERMANENT, ErrorCategory.CONFLICT):
                logger.error(f"Permanent error (no retry): {e}")
                raise

            # Check if we have retries left
            if attempt >= max_retries:
                logger.error(f"Max retries ({max_retries}) exceeded: {e}")
                raise

            # Log and notify
            logger.warning(
                f"Transient error (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.1f}s: {e}"
            )

            if on_retry:
                on_retry(attempt + 1, delay, e)

            # Wait before retry
            await asyncio.sleep(delay)

            # Increase delay for next attempt (with cap)
            delay = min(delay * backoff_factor, max_delay)

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop completed without result or exception")


def retry_on_transient(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
):
    """Decorator to add retry logic to async functions.

    Args:
        max_retries: Maximum retry attempts
        initial_delay: Initial delay between retries
        max_delay: Maximum delay between retries

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await with_retry(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
            )
        return wrapper
    return decorator


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_error: Exception, attempts: int):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts
