"""Run a raw GraphQL query and inspect the cost/throttle extension Shopify returns.

Usage:
    export SHOPIFY_STORE_DOMAIN=my-store.myshopify.com
    export SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
    python examples/graphql_shop_info.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shopify_client import ShopifyGraphQLClient  # noqa: E402

QUERY = """
query ShopInfo {
  shop {
    name
    myshopifyDomain
    plan {
      displayName
    }
  }
}
"""


def main() -> None:
    shop = os.environ["SHOPIFY_STORE_DOMAIN"]
    token = os.environ["SHOPIFY_ADMIN_ACCESS_TOKEN"]
    client = ShopifyGraphQLClient(shop, token)

    payload = client.query(QUERY)
    print(payload["data"]["shop"])

    status = client.last_throttle_status
    if status:
        print(
            f"\nbucket: {status.currently_available:.0f}/{status.maximum_available:.0f} "
            f"points, restoring {status.restore_rate:.0f}/s",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
