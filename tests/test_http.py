from unittest.mock import Mock, patch

import pytest
import requests

from newsbot.tools.http import request_with_retry


def _http_error(status: int, headers: dict | None = None) -> requests.HTTPError:
    response = Mock()
    response.status_code = status
    response.text = f"error {status}"
    response.headers = headers or {}
    return requests.HTTPError(response=response)


@patch("newsbot.tools.http.time.sleep")  # don't actually wait during tests
@patch("newsbot.tools.http.requests.request")
def test_429_is_retried_not_raised_immediately(mock_request, mock_sleep):
    rate_limited_response = Mock(raise_for_status=Mock(side_effect=_http_error(429, {"Retry-After": "5"})))
    success_response = Mock(raise_for_status=Mock())
    mock_request.side_effect = [rate_limited_response, success_response]

    result = request_with_retry("POST", "https://example.com", headers={}, service_name="Test")

    assert result is success_response
    mock_sleep.assert_called_once_with(5.0)  # honored Retry-After instead of guessing


@patch("newsbot.tools.http.requests.request")
def test_404_fails_fast_without_retry(mock_request):
    mock_request.return_value = Mock(raise_for_status=Mock(side_effect=_http_error(404)))

    with pytest.raises(RuntimeError, match="rejected the request \\(404\\)"):
        request_with_retry("POST", "https://example.com", headers={}, service_name="Test")

    assert mock_request.call_count == 1  # no wasted retries on a permanent error
