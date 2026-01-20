"""Error handling infrastructure for Soda agents.

This module provides error classification and retry logic for agent invocations.
Transient errors (rate limits, timeouts, connection errors, 5xx) are retried
with exponential backoff. Fatal errors (invalid API key, 401, 403) halt immediately.
"""

import asyncio
import random
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


# =============================================================================
# Exception Classes
# =============================================================================


class SodaError(Exception):
    """Base exception for all Soda errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


class TransientError(SodaError):
    """Error that is transient and can be retried.

    Examples: rate limits (429), server errors (5xx), timeouts, connection errors.
    """

    pass


class FatalError(SodaError):
    """Error that is fatal and should halt immediately.

    Examples: invalid API key (401), forbidden (403), permission denied.
    """

    pass


class MaxRetriesExhaustedError(SodaError):
    """Error raised when max retry attempts have been exhausted."""

    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


# =============================================================================
# Error Classification
# =============================================================================

# HTTP status codes that are transient (retryable)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

# HTTP status codes that are fatal (non-retryable)
FATAL_STATUS_CODES = {401, 403}

# Python exception types that are always fatal
FATAL_EXCEPTION_TYPES = (
    PermissionError,
)


def is_transient_error(error: Exception) -> bool:
    """Classify error as transient (retry) or fatal (halt).

    Args:
        error: The exception to classify.

    Returns:
        True if the error is transient and should be retried,
        False if the error is fatal and should halt immediately.

    Classification rules:
        - FatalError: Always fatal
        - TransientError: Always transient
        - PermissionError: Fatal
        - TimeoutError, ConnectionError: Transient
        - SodaError with status_code:
            - 429, 5xx: Transient
            - 401, 403: Fatal
        - Unknown errors: Treated as transient (retry)
    """
    # Explicit FatalError is always fatal
    if isinstance(error, FatalError):
        return False

    # Explicit TransientError is always transient
    if isinstance(error, TransientError):
        return True

    # Python built-in fatal errors
    if isinstance(error, FATAL_EXCEPTION_TYPES):
        return False

    # Python built-in transient errors
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    # Check status code on SodaError subclasses
    if isinstance(error, SodaError) and error.status_code is not None:
        if error.status_code in FATAL_STATUS_CODES:
            return False
        if error.status_code in TRANSIENT_STATUS_CODES:
            return True

    # Unknown errors are treated as transient (retry)
    return True


# =============================================================================
# Retry Handler
# =============================================================================


class RetryHandler:
    """Handles retry logic with exponential backoff for transient errors.

    Attributes:
        base_delay: Initial delay in seconds between retries.
        max_delay: Maximum delay in seconds (caps exponential growth).
        jitter: Random jitter factor (0-1) to add to delays.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: float = 0.5,
    ):
        """Initialize the retry handler.

        Args:
            base_delay: Initial delay in seconds between retries.
            max_delay: Maximum delay in seconds.
            jitter: Random jitter factor (0-1) to add to delays.
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def execute_with_retry(
        self,
        func: Callable[[], T],
        max_attempts: int = 3,
    ) -> T:
        """Execute function with exponential backoff retry on transient errors.

        Args:
            func: The function to execute.
            max_attempts: Maximum number of attempts before giving up.

        Returns:
            The return value of the function if successful.

        Raises:
            FatalError: If a fatal error occurs (halts immediately).
            MaxRetriesExhaustedError: If max_attempts are exhausted.
            Exception: If a fatal exception type is raised (e.g., PermissionError).
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return func()
            except Exception as e:
                last_error = e

                # Check if error is fatal - halt immediately
                if not is_transient_error(e):
                    raise

                # Transient error - retry if we have attempts left
                if attempt >= max_attempts:
                    raise MaxRetriesExhaustedError(
                        message=f"Max retries exhausted after {max_attempts} attempts",
                        attempts=max_attempts,
                        last_error=last_error,
                    )

                # Calculate delay with exponential backoff and jitter
                delay = self._calculate_delay(attempt)
                time.sleep(delay)

        # This should never be reached, but satisfy type checker
        raise MaxRetriesExhaustedError(
            message=f"Max retries exhausted after {max_attempts} attempts",
            attempts=max_attempts,
            last_error=last_error,
        )

    async def execute_with_retry_async(
        self,
        func: Callable[[], Awaitable[T]],
        max_attempts: int = 3,
    ) -> T:
        """Execute async function with exponential backoff retry on transient errors.

        Args:
            func: The async function to execute.
            max_attempts: Maximum number of attempts before giving up.

        Returns:
            The return value of the function if successful.

        Raises:
            FatalError: If a fatal error occurs (halts immediately).
            MaxRetriesExhaustedError: If max_attempts are exhausted.
            Exception: If a fatal exception type is raised (e.g., PermissionError).
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await func()
            except Exception as e:
                last_error = e

                # Check if error is fatal - halt immediately
                if not is_transient_error(e):
                    raise

                # Transient error - retry if we have attempts left
                if attempt >= max_attempts:
                    raise MaxRetriesExhaustedError(
                        message=f"Max retries exhausted after {max_attempts} attempts",
                        attempts=max_attempts,
                        last_error=last_error,
                    )

                # Calculate delay with exponential backoff and jitter
                delay = self._calculate_delay(attempt)
                await asyncio.sleep(delay)

        # This should never be reached, but satisfy type checker
        raise MaxRetriesExhaustedError(
            message=f"Max retries exhausted after {max_attempts} attempts",
            attempts=max_attempts,
            last_error=last_error,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number.

        Uses exponential backoff with jitter: delay = base_delay * 2^(attempt-1)

        Args:
            attempt: The current attempt number (1-indexed).

        Returns:
            The delay in seconds.
        """
        # Exponential backoff: base * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter (random factor between 1-jitter and 1+jitter)
        jitter_factor = 1.0 + (random.random() * 2 - 1) * self.jitter
        delay = delay * jitter_factor

        return delay
