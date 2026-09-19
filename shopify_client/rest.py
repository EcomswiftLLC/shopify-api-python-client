"""REST Admin API client with Link-header pagination and 429 retry."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Iterator, Mapping, Optional
from urllib.parse import urlencode

from .http import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    ShopifyAPIError,
    Transport,
    request_with_retries,
    safe_json,
    urllib_transport,
)

DEFAULT_API_VERSION = "2025-10"

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')


class ShopifyRESTClient:
    """A thin wrapper over the Shopify Admin REST API.

    Handles auth headers, JSON encode/decode, HTTP 429 retry (via
    ``request_with_retries``), and cursor-based pagination through the
    ``Link`` response header. Does not know about any particular resource —
    pass whatever path and body Shopify's REST docs specify.
    """

    def __init__(
        self,
        shop: str,
        access_token: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        transport: Transport = urllib_transport,
        sleep=time.sleep,
    ) -> None:
        if not shop or not access_token:
            raise ValueError("shop and access_token are required")
        self.shop = shop
        self.access_token = access_token
        self.api_version = api_version
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport
        self.sleep = sleep

    def _url(self, path: str, params: Optional[Mapping[str, Any]] = None) -> str:
        clean_path = path.lstrip("/")
        url = f"https://{self.shop}/admin/api/{self.api_version}/{clean_path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _request(self, method: str, path: str, *, params=None, json_body=None):
        url = self._url(path, params)
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        response = request_with_retries(
            self.transport,
            url,
            method,
            self._headers(),
            data,
            timeout=self.timeout,
            max_retries=self.max_retries,
            sleep=self.sleep,
        )
        if response.status >= 400:
            raise ShopifyAPIError(
                f"{method} {path} failed with HTTP {response.status}",
                status=response.status,
                body=safe_json(response.body),
            )
        return response

    def get(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params).json()

    def post(self, path: str, json_body: Optional[Mapping[str, Any]] = None) -> Any:
        return self._request("POST", path, json_body=json_body).json()

    def put(self, path: str, json_body: Optional[Mapping[str, Any]] = None) -> Any:
        return self._request("PUT", path, json_body=json_body).json()

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path).json()

    def paginate(
        self,
        path: str,
        collection_key: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        limit: Optional[int] = None,
        page_size: int = 250,
    ) -> Iterator[Dict[str, Any]]:
        """Yield individual resources across every page.

        Follows the ``Link: <url>; rel="next"`` header Shopify's REST API
        uses for cursor-based pagination — ``page_info`` params are opaque,
        so this never constructs a "next page" URL itself, it only follows
        the one the API hands back.
        """
        request_params: Dict[str, Any] = dict(params or {})
        request_params.setdefault("limit", page_size)
        url: Optional[str] = self._url(path, request_params)
        yielded = 0
        while url:
            response = request_with_retries(
                self.transport,
                url,
                "GET",
                self._headers(),
                None,
                timeout=self.timeout,
                max_retries=self.max_retries,
                sleep=self.sleep,
            )
            if response.status >= 400:
                raise ShopifyAPIError(
                    f"GET {path} failed with HTTP {response.status}",
                    status=response.status,
                    body=safe_json(response.body),
                )
            payload = response.json() or {}
            for item in payload.get(collection_key, []):
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            url = _next_link(response.header("Link"))


def _next_link(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None
    for url, rel in _LINK_RE.findall(link_header):
        if rel == "next":
            return url
    return None
