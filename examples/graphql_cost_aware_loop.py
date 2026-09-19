"""Run many GraphQL queries in a row without tripping the rate limit.

The client sleeps on its own before a query if the last response showed the
bucket running low, so a tight loop like this doesn't need any manual
throttling code. Useful as a starting point for a bulk relabeling or
tagging script.

Usage:
    export SHOPIFY_STORE_DOMAIN=my-store.myshopify.com
    export SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx
    python examples/graphql_cost_aware_loop.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shopify_client import ShopifyGraphQLClient  # noqa: E402

PRODUCT_TITLES_QUERY = """
query ProductTitles($cursor: String) {
  products(first: 50, after: $cursor) {
    edges {
      cursor
      node {
        id
        title
      }
    }
    pageInfo {
      hasNextPage
    }
  }
}
"""


def main() -> None:
    shop = os.environ["SHOPIFY_STORE_DOMAIN"]
    token = os.environ["SHOPIFY_ADMIN_ACCESS_TOKEN"]
    client = ShopifyGraphQLClient(shop, token)

    cursor = None
    total = 0
    while True:
        payload = client.query(PRODUCT_TITLES_QUERY, {"cursor": cursor})
        connection = payload["data"]["products"]
        for edge in connection["edges"]:
            total += 1
            cursor = edge["cursor"]
        if not connection["pageInfo"]["hasNextPage"]:
            break

    print(f"{total} product(s) scanned", file=sys.stderr)


if __name__ == "__main__":
    main()
