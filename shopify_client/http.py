"""Low-level HTTP transport shared by the REST and GraphQL clients.

Stdlib only (``urllib``) so the package has zero runtime dependencies. The
transport is injected as a plain callable so tests can swap in a fake one
instead of hitting the network or mocking ``urllib`` internals.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional

USER_AGENT = (
    "shopify-api-python-client/1.0 "
    "(+https://github.com/EcomswiftLLC/shopify-api-python-client)"
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_AFTER_SECONDS = 1.0


class ShopifyAPIError(Exception):
    """Raised for a REST/GraphQL error that isn't rate limiting."""

    def __init__(self, message: str, *, status: Optional[int] = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class ShopifyRateLimitError(ShopifyAPIError):
    """Raised when a request is still being throttled after all retries."""


@dataclass
class HTTPResponse:
    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    def header(self, name: str) -> Optional[str]:
        target = name.lower()
        for key, value in self.headers.items():
            if key.lower() == target:
                return value
        return None


# (url, method, headers, body-bytes-or-None, timeout) -> HTTPResponse
Transport = Callable[[str, str, Mapping[str, str], Optional[bytes], float], HTTPResponse]


def urllib_transport(
    url: str,
    method: str,
    headers: Mapping[str, str],
    data: Optional[bytes],
    timeout: float,
) -> HTTPResponse:
    """Default transport: stdlib ``urllib``, no third-party dependency."""
    request = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HTTPResponse(
                status=response.status,
                headers=dict(response.headers.items()),
                body=response.read(),
            )
    except urllib.error.HTTPError as error:
        body = error.read()
        error_headers = dict(error.headers.items()) if error.headers else {}
        return HTTPResponse(status=error.code, headers=error_headers, body=body)


def request_with_retries(
    transport: Transport,
    url: str,
    method: str,
    headers: Mapping[str, str],
    data: Optional[bytes],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    sleep: Callable[[float], None] = lambda seconds: None,
) -> HTTPResponse:
    """Issue a request, retrying on HTTP 429 using the ``Retry-After`` header.

    This covers REST's documented rate-limit signal. The GraphQL client layers
    its own cost-aware pacing on top of this (see ``graphql.py``) because
    GraphQL throttling is reported inside a 200 response body, not via 429.
    """
    attempt = 0
    while True:
        response = transport(url, method, headers, data, timeout)
        if response.status != 429 or attempt >= max_retries:
            return response
        sleep(_parse_retry_after(response))
        attempt += 1


def _parse_retry_after(response: HTTPResponse) -> float:
    value = response.header("Retry-After")
    if value is None:
        return DEFAULT_RETRY_AFTER_SECONDS
    try:
        return max(float(value), 0.1)
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS


def safe_json(body: bytes) -> Any:
    """Best-effort JSON decode for error bodies that might not be JSON at all."""
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")
