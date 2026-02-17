"""Tests for error classification and retry logic."""

import asyncio
import pytest
from unittest.mock import MagicMock

from fidra.data.resilience import (
    ErrorCategory,
    classify_error,
    get_user_message,
    with_retry,
)
from fidra.data.repository import ConcurrencyError


class TestClassifyError:
    """Test error classification for retry decisions."""

    def test_concurrency_error_is_conflict(self):
        err = ConcurrencyError("version mismatch")
        assert classify_error(err) == ErrorCategory.CONFLICT

    def test_version_in_message_is_conflict(self):
        err = Exception("Version conflict: expected 2, found 3")
        assert classify_error(err) == ErrorCategory.CONFLICT

    def test_connection_refused_is_transient(self):
        err = ConnectionRefusedError("Connection refused")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_connection_reset_is_transient(self):
        err = ConnectionResetError("Connection reset by peer")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_timeout_error_is_transient(self):
        err = TimeoutError("Operation timed out")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_os_error_is_transient(self):
        err = OSError("Network is unreachable")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_connection_closed_message_is_transient(self):
        err = Exception("connection is closed")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_broken_pipe_is_transient(self):
        err = Exception("broken pipe")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_pool_closed_is_transient(self):
        err = Exception("pool is closed")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_auth_failure_is_permanent(self):
        err = Exception("password authentication failed for user")
        assert classify_error(err) == ErrorCategory.PERMANENT

    def test_permission_denied_is_permanent(self):
        err = Exception("permission denied for table transactions")
        assert classify_error(err) == ErrorCategory.PERMANENT

    def test_syntax_error_is_permanent(self):
        err = Exception("syntax error at or near SELECT")
        assert classify_error(err) == ErrorCategory.PERMANENT

    def test_already_exists_is_permanent(self):
        err = Exception("relation 'transactions' already exists")
        assert classify_error(err) == ErrorCategory.PERMANENT

    def test_unknown_error_defaults_to_transient(self):
        err = Exception("something completely unexpected")
        assert classify_error(err) == ErrorCategory.TRANSIENT


class TestGetUserMessage:
    """Test user-friendly error messages."""

    def test_conflict_message(self):
        err = ConcurrencyError("version mismatch")
        msg = get_user_message(err)
        assert "modified by another user" in msg

    def test_connection_message(self):
        err = ConnectionRefusedError("Connection refused")
        msg = get_user_message(err)
        assert "internet connection" in msg.lower() or "connect" in msg.lower()

    def test_timeout_message(self):
        err = TimeoutError("timeout")
        msg = get_user_message(err)
        assert "long to respond" in msg.lower() or "try again" in msg.lower()

    def test_auth_message(self):
        err = Exception("password authentication failed")
        msg = get_user_message(err)
        assert "authentication" in msg.lower() or "credentials" in msg.lower()


class TestWithRetry:
    """Test retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await with_retry(operation, max_retries=3, initial_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_transient_failure(self):
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection reset")
            return "ok"

        result = await with_retry(operation, max_retries=3, initial_delay=0.01)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_not_retried(self):
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            raise Exception("permission denied")

        with pytest.raises(Exception, match="permission denied"):
            await with_retry(operation, max_retries=3, initial_delay=0.01)

        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_conflict_error_not_retried(self):
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            raise ConcurrencyError("version conflict")

        with pytest.raises(ConcurrencyError):
            await with_retry(operation, max_retries=3, initial_delay=0.01)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            await with_retry(operation, max_retries=2, initial_delay=0.01)

        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        retries = []

        async def operation():
            raise ConnectionError("fail")

        def on_retry(attempt, delay, error):
            retries.append(attempt)

        with pytest.raises(ConnectionError):
            await with_retry(
                operation, max_retries=2, initial_delay=0.01, on_retry=on_retry,
            )

        assert retries == [1, 2]
