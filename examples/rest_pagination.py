"""Stream every product in a store, regardless of catalog size.

Usage:
    export SHOPIFY_STORE_DOMAIN=my-store.myshopify.com
    export SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
    python examples/rest_pagination.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shopify_client import ShopifyRESTClient  # noqa: E402


def main() -> None:
    shop = os.environ["SHOPIFY_STORE_DOMAIN"]
    token = os.environ["SHOPIFY_ADMIN_ACCESS_TOKEN"]
    client = ShopifyRESTClient(shop, token)

    count = 0
    for product in client.paginate("products.json", "products", params={"status": "active"}):
        count += 1
        print(f"{product['id']}\t{product['title']}")

    print(f"\n{count} active product(s) total", file=sys.stderr)


if __name__ == "__main__":
    main()
