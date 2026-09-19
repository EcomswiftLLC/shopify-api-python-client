"""A lightweight, dependency-free Python client for the Shopify Admin API."""

from .graphql import ShopifyGraphQLClient, ThrottleStatus
from .http import ShopifyAPIError, ShopifyRateLimitError
from .rest import ShopifyRESTClient

__version__ = "1.0.0"

__all__ = [
    "ShopifyRESTClient",
    "ShopifyGraphQLClient",
    "ThrottleStatus",
    "ShopifyAPIError",
    "ShopifyRateLimitError",
    "__version__",
]
