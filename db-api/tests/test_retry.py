"""Tests for retry module."""

import pytest
from unittest.mock import MagicMock, patch
import time

from dbapi_cdc.retry import is_retryable, retry


class TestIsRetryable:
    def test_connection_refused(self):
        err = Exception("Connection refused by server")
        assert is_retryable(err) is True

    def test_timeout(self):
        err = Exception("Connection timed out")
        assert is_retryable(err) is True

    def test_network_unreachable(self):
        err = Exception("Network is unreachable")
        assert is_retryable(err) is True

    def test_not_retryable(self):
        err = Exception("Invalid SQL syntax")
        assert is_retryable(err) is False

    def test_permission_denied(self):
        err = Exception("Permission denied")
        assert is_retryable(err) is False


class TestRetryDecorator:
    def test_success_first_try(self):
        mock_fn = MagicMock(return_value="success")
        decorated = retry(max_attempts=3)(mock_fn)

        result = decorated()

        assert result == "success"
        assert mock_fn.call_count == 1

    def test_success_after_retry(self):
        mock_fn = MagicMock(side_effect=[
            Exception("Connection timed out"),
            "success",
        ])
        decorated = retry(max_attempts=3, delay=0.01)(mock_fn)

        result = decorated()

        assert result == "success"
        assert mock_fn.call_count == 2

    def test_max_retries_exceeded(self):
        mock_fn = MagicMock(side_effect=Exception("Connection timed out"))
        decorated = retry(max_attempts=3, delay=0.01)(mock_fn)

        with pytest.raises(Exception, match="Connection timed out"):
            decorated()

        assert mock_fn.call_count == 3

    def test_non_retryable_error(self):
        mock_fn = MagicMock(side_effect=Exception("Invalid SQL"))
        decorated = retry(max_attempts=3, delay=0.01)(mock_fn)

        with pytest.raises(Exception, match="Invalid SQL"):
            decorated()

        assert mock_fn.call_count == 1

    def test_preserves_function_args(self):
        mock_fn = MagicMock(return_value="ok")
        decorated = retry(max_attempts=3)(mock_fn)

        decorated("arg1", key="value")

        mock_fn.assert_called_once_with("arg1", key="value")

    def test_backoff(self):
        call_times = []

        def track_time():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise Exception("Connection timed out")
            return "success"

        decorated = retry(max_attempts=3, delay=0.1, backoff=2.0)(track_time)
        result = decorated()

        assert result == "success"
        assert len(call_times) == 3

        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        assert delay1 >= 0.09
        assert delay2 >= 0.18
