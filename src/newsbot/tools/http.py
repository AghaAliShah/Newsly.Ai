"""Shared retry logic for the tools that hit an external HTTP API.

Retries network errors, 5xx, and 429 (all transient) — a non-429 4xx means
the request itself is wrong (bad model slug, bad token, bad channel) and
retrying it 3 times just burns time while hiding the actual error message,
so those fail fast with the real response body instead. 429 honors the
server's Retry-After header when present, since a fixed backoff guess is
worse than just being told how long to wait.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    service_name: str,
    json_payload: dict | None = None,
    params: dict | None = None,
    max_retries: int = 2,
    timeout: int = 15,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        wait = 2**attempt
        try:
            response = requests.request(
                method, url, json=json_payload, params=params, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            return response
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and status != 429 and status < 500:
                raise RuntimeError(
                    f"{service_name} rejected the request ({status}): {exc.response.text}"
                ) from exc
            last_error = exc
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(wait, float(retry_after))
                    except ValueError:
                        pass
        except requests.RequestException as exc:
            last_error = exc

        if attempt < max_retries:
            logger.warning("%s request failed (%s), retrying in %ss", service_name, last_error, wait)
            time.sleep(wait)

    raise RuntimeError(f"{service_name} API failed after {max_retries + 1} attempts") from last_error
