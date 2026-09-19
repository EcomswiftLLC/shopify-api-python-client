"""GraphQL Admin API client with proactive, cost-aware throttle pacing.

Every GraphQL Admin response carries the current state of the leaky bucket
under ``extensions.cost.throttleStatus`` (``maximumAvailable``,
``currentlyAvailable``, ``restoreRate`` — verified against the 2025-10 docs).
This client remembers the last observed bucket state and, before sending the
*next* query, sleeps just long enough for the bucket to refill past a safety
buffer if it looks low. That is the mechanism Shopify's own rate-limit docs
recommend, and it avoids ever needing to guess a query's exact cost up front.

As a defensive fallback (not the primary mechanism, since the exact error
code isn't guaranteed to stay stable across API versions) it also retries
when a response's ``errors[].extensions.code`` mentions throttling or cost.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .http import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    ShopifyAPIError,
    ShopifyRateLimitError,
    Transport,
    request_with_retries,
    safe_json,
    urllib_transport,
)

DEFAULT_API_VERSION = "2025-10"
DEFAULT_MIN_AVAILABLE_BUFFER = 50.0
_THROTTLE_ERROR_CODES = {"THROTTLED", "MAX_COST_EXCEEDED"}


@dataclass
class ThrottleStatus:
    maximum_available: float
    currently_available: float
    restore_rate: float


class ShopifyGraphQLClient:
    def __init__(
        self,
        shop: str,
        access_token: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport = urllib_transport,
        min_available_buffer: float = DEFAULT_MIN_AVAILABLE_BUFFER,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not shop or not access_token:
            raise ValueError("shop and access_token are required")
        self.shop = shop
        self.access_token = access_token
        self.api_version = api_version
        self.timeout = timeout
        self.transport = transport
        self.min_available_buffer = min_available_buffer
        self.sleep = sleep
        self._last_throttle: Optional[ThrottleStatus] = None

    @property
    def last_throttle_status(self) -> Optional[ThrottleStatus]:
        return self._last_throttle

    def _url(self) -> str:
        return f"https://{self.shop}/admin/api/{self.api_version}/graphql.json"

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        *,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Run a query or mutation, waiting out the bucket first if it looks low."""
        self._wait_for_capacity()
        attempt = 0
        while True:
            body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
            response = request_with_retries(
                self.transport,
                self._url(),
                "POST",
                self._headers(),
                body,
                timeout=self.timeout,
                max_retries=0,  # 429s here are handled by the throttle loop below
                sleep=self.sleep,
            )
            if response.status >= 500:
                raise ShopifyAPIError(
                    f"GraphQL request failed with HTTP {response.status}",
                    status=response.status,
                    body=safe_json(response.body),
                )
            payload = response.json() or {}
            self._record_throttle_status(payload)

            if response.status == 429 or _is_throttled(payload):
                if attempt >= max_retries:
                    raise ShopifyRateLimitError(
                        "GraphQL query still throttled after retries",
                        status=response.status,
                        body=payload,
                    )
                self.sleep(max(self._seconds_until_available(), 0.5))
                attempt += 1
                continue

            if payload.get("errors") and payload.get("data") is None:
                raise ShopifyAPIError("GraphQL query returned errors", body=payload["errors"])

            return payload

    def _wait_for_capacity(self) -> None:
        status = self._last_throttle
        if status is None or status.currently_available >= self.min_available_buffer:
            return
        wait_seconds = self._seconds_until_available()
        if wait_seconds <= 0:
            return
        self.sleep(wait_seconds)
        # Optimistic local update so back-to-back calls don't all sleep the
        # same amount before a real response corrects the estimate.
        status.currently_available = min(
            status.maximum_available,
            status.currently_available + wait_seconds * status.restore_rate,
        )

    def _seconds_until_available(self) -> float:
        status = self._last_throttle
        if status is None or status.restore_rate <= 0:
            return 1.0
        deficit = max(self.min_available_buffer - status.currently_available, 0.0)
        return deficit / status.restore_rate

    def _record_throttle_status(self, payload: Dict[str, Any]) -> None:
        cost = (payload.get("extensions") or {}).get("cost")
        if not cost:
            return
        throttle = cost.get("throttleStatus") or {}
        if not throttle:
            return
        self._last_throttle = ThrottleStatus(
            maximum_available=float(throttle.get("maximumAvailable", 0)),
            currently_available=float(throttle.get("currentlyAvailable", 0)),
            restore_rate=float(throttle.get("restoreRate", 0)) or 1.0,
        )


def _is_throttled(payload: Dict[str, Any]) -> bool:
    errors: List[Dict[str, Any]] = payload.get("errors") or []
    for error in errors:
        code = str((error.get("extensions") or {}).get("code") or "").upper()
        if code in _THROTTLE_ERROR_CODES:
            return True
    return False
