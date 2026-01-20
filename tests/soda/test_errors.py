"""Tests for soda error handling and retry logic.

These tests verify the error classification and retry behavior.
"""

import pytest
import time
from unittest.mock import Mock, patch

from soda.errors import (
    RetryHandler,
    is_transient_error,
    TransientError,
    FatalError,
    MaxRetriesExhaustedError,
)


class TestIsTransientError:
    """Test error classification function."""

    def test_timeout_is_transient(self):
        """WHEN a TimeoutError occurs THEN it is classified as transient."""
        error = TimeoutError("Connection timed out")
        assert is_transient_error(error) is True

    def test_connection_error_is_transient(self):
        """WHEN a ConnectionError occurs THEN it is classified as transient."""
        error = ConnectionError("Connection refused")
        assert is_transient_error(error) is True

    def test_rate_limit_error_is_transient(self):
        """WHEN a rate limit error (429) occurs THEN it is classified as transient."""
        # Simulate rate limit via TransientError
        error = TransientError("Rate limit exceeded", status_code=429)
        assert is_transient_error(error) is True

    def test_5xx_server_error_is_transient(self):
        """WHEN a 5xx server error occurs THEN it is classified as transient."""
        for status in [500, 502, 503, 504]:
            error = TransientError(f"Server error {status}", status_code=status)
            assert is_transient_error(error) is True, f"Status {status} should be transient"

    def test_invalid_api_key_is_fatal(self):
        """WHEN an invalid API key error occurs THEN it is classified as fatal."""
        error = FatalError("Invalid API key", status_code=401)
        assert is_transient_error(error) is False

    def test_403_is_fatal(self):
        """WHEN a 403 error occurs THEN it is classified as fatal."""
        error = FatalError("Forbidden", status_code=403)
        assert is_transient_error(error) is False

    def test_permission_denied_is_fatal(self):
        """WHEN a PermissionError occurs THEN it is classified as fatal."""
        error = PermissionError("Permission denied")
        assert is_transient_error(error) is False

    def test_fatal_error_is_not_transient(self):
        """WHEN a FatalError is raised THEN it is classified as fatal."""
        error = FatalError("Critical failure")
        assert is_transient_error(error) is False

    def test_unknown_error_is_transient(self):
        """WHEN an unknown error occurs THEN it is classified as transient (retry)."""
        error = RuntimeError("Some unexpected error")
        assert is_transient_error(error) is True

    def test_value_error_is_transient(self):
        """WHEN a ValueError occurs THEN it is classified as transient by default."""
        error = ValueError("Invalid value")
        assert is_transient_error(error) is True


class TestTransientError:
    """Test TransientError exception class."""

    def test_create_with_message(self):
        """WHEN creating TransientError THEN message is set."""
        error = TransientError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"

    def test_create_with_status_code(self):
        """WHEN creating TransientError with status_code THEN it is preserved."""
        error = TransientError("Server error", status_code=503)
        assert error.status_code == 503

    def test_create_with_original_error(self):
        """WHEN creating TransientError with original_error THEN it is preserved."""
        original = ConnectionError("Connection reset")
        error = TransientError("Connection failed", original_error=original)
        assert error.original_error is original


class TestFatalError:
    """Test FatalError exception class."""

    def test_create_with_message(self):
        """WHEN creating FatalError THEN message is set."""
        error = FatalError("Invalid API key")
        assert str(error) == "Invalid API key"

    def test_create_with_status_code(self):
        """WHEN creating FatalError with status_code THEN it is preserved."""
        error = FatalError("Forbidden", status_code=403)
        assert error.status_code == 403


class TestMaxRetriesExhaustedError:
    """Test MaxRetriesExhaustedError exception class."""

    def test_create_with_message_and_attempts(self):
        """WHEN creating MaxRetriesExhaustedError THEN message and attempts are set."""
        original = TransientError("Server error", status_code=500)
        error = MaxRetriesExhaustedError(
            message="Max retries exhausted after 3 attempts",
            attempts=3,
            last_error=original
        )
        assert error.attempts == 3
        assert error.last_error is original
        assert "3 attempts" in str(error)


class TestRetryHandler:
    """Test RetryHandler class."""

    def test_successful_execution_no_retry(self):
        """WHEN function succeeds THEN it returns immediately without retry."""
        handler = RetryHandler()
        func = Mock(return_value="success")

        result = handler.execute_with_retry(func)

        assert result == "success"
        assert func.call_count == 1

    def test_transient_error_retries(self):
        """WHEN transient error occurs THEN it retries up to max_attempts."""
        handler = RetryHandler(base_delay=0.01)  # Fast for tests
        func = Mock(side_effect=TransientError("Rate limit"))

        with pytest.raises(MaxRetriesExhaustedError) as exc_info:
            handler.execute_with_retry(func, max_attempts=3)

        assert func.call_count == 3
        assert exc_info.value.attempts == 3

    def test_fatal_error_halts_immediately(self):
        """WHEN fatal error occurs THEN it halts immediately without retry."""
        handler = RetryHandler()
        func = Mock(side_effect=FatalError("Invalid API key", status_code=401))

        with pytest.raises(FatalError) as exc_info:
            handler.execute_with_retry(func, max_attempts=3)

        assert func.call_count == 1
        assert exc_info.value.status_code == 401

    def test_recovery_after_transient_error(self):
        """WHEN transient error occurs then succeeds THEN returns success."""
        handler = RetryHandler(base_delay=0.01)
        func = Mock(side_effect=[
            TransientError("Rate limit"),
            TransientError("Rate limit"),
            "success"
        ])

        result = handler.execute_with_retry(func, max_attempts=3)

        assert result == "success"
        assert func.call_count == 3

    def test_exponential_backoff(self):
        """WHEN retrying THEN backoff increases exponentially."""
        handler = RetryHandler(base_delay=0.1)
        func = Mock(side_effect=TransientError("Error"))
        delays = []

        original_sleep = time.sleep
        def mock_sleep(seconds):
            delays.append(seconds)

        with patch('time.sleep', mock_sleep):
            with pytest.raises(MaxRetriesExhaustedError):
                handler.execute_with_retry(func, max_attempts=4)

        # Verify exponential increase (with some jitter tolerance)
        # Base delay is 0.1, so: ~0.1, ~0.2, ~0.4
        assert len(delays) == 3  # 4 attempts = 3 delays
        assert delays[0] >= 0.05  # base * 0.5 (jitter)
        assert delays[1] > delays[0]  # Should increase
        assert delays[2] > delays[1]  # Should increase more

    def test_unknown_error_treated_as_transient(self):
        """WHEN unknown error occurs THEN it is treated as transient and retried."""
        handler = RetryHandler(base_delay=0.01)
        func = Mock(side_effect=RuntimeError("Unexpected error"))

        with pytest.raises(MaxRetriesExhaustedError) as exc_info:
            handler.execute_with_retry(func, max_attempts=2)

        assert func.call_count == 2
        assert exc_info.value.attempts == 2

    def test_connection_error_treated_as_transient(self):
        """WHEN ConnectionError occurs THEN it is treated as transient."""
        handler = RetryHandler(base_delay=0.01)
        func = Mock(side_effect=[
            ConnectionError("Connection refused"),
            "success"
        ])

        result = handler.execute_with_retry(func, max_attempts=3)

        assert result == "success"
        assert func.call_count == 2

    def test_timeout_error_treated_as_transient(self):
        """WHEN TimeoutError occurs THEN it is treated as transient."""
        handler = RetryHandler(base_delay=0.01)
        func = Mock(side_effect=[
            TimeoutError("Request timed out"),
            "success"
        ])

        result = handler.execute_with_retry(func, max_attempts=3)

        assert result == "success"
        assert func.call_count == 2

    def test_permission_error_is_fatal(self):
        """WHEN PermissionError occurs THEN it is treated as fatal."""
        handler = RetryHandler()
        func = Mock(side_effect=PermissionError("Permission denied"))

        with pytest.raises(PermissionError):
            handler.execute_with_retry(func, max_attempts=3)

        assert func.call_count == 1

    def test_error_context_preserved(self):
        """WHEN max retries exhausted THEN error includes full context."""
        handler = RetryHandler(base_delay=0.01)
        original_error = TransientError("Rate limit exceeded", status_code=429)
        func = Mock(side_effect=original_error)

        with pytest.raises(MaxRetriesExhaustedError) as exc_info:
            handler.execute_with_retry(func, max_attempts=3)

        error = exc_info.value
        assert error.attempts == 3
        assert error.last_error is original_error
        assert "Rate limit exceeded" in str(error.last_error)

    def test_default_max_attempts_is_3(self):
        """WHEN max_attempts not specified THEN default is 3."""
        handler = RetryHandler(base_delay=0.01)
        func = Mock(side_effect=TransientError("Error"))

        with pytest.raises(MaxRetriesExhaustedError):
            handler.execute_with_retry(func)

        assert func.call_count == 3

    def test_custom_max_attempts(self):
        """WHEN custom max_attempts specified THEN it is respected."""
        handler = RetryHandler(base_delay=0.01)
        func = Mock(side_effect=TransientError("Error"))

        with pytest.raises(MaxRetriesExhaustedError):
            handler.execute_with_retry(func, max_attempts=5)

        assert func.call_count == 5

    def test_max_delay_cap(self):
        """WHEN backoff would exceed max_delay THEN it is capped."""
        handler = RetryHandler(base_delay=1.0, max_delay=2.0, jitter=0.0)  # No jitter for predictable test
        func = Mock(side_effect=TransientError("Error"))
        delays = []

        with patch('time.sleep', lambda s: delays.append(s)):
            with pytest.raises(MaxRetriesExhaustedError):
                handler.execute_with_retry(func, max_attempts=10)

        # Without jitter, all delays should be <= max_delay
        for delay in delays:
            assert delay <= 2.0  # max_delay without jitter
