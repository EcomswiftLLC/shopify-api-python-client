"""``spc`` — a small command-line client for the Shopify Admin API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from .graphql import ShopifyGraphQLClient
from .http import ShopifyAPIError
from .rest import ShopifyRESTClient

SHOP_QUERY = """
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


def _client_config(args: argparse.Namespace) -> Tuple[str, str, str]:
    shop = args.shop or os.environ.get("SHOPIFY_STORE_DOMAIN")
    token = args.token or os.environ.get("SHOPIFY_ADMIN_ACCESS_TOKEN")
    version = args.api_version or os.environ.get("SHOPIFY_API_VERSION") or "2025-10"
    if not shop or not token:
        raise SystemExit(
            "Set SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_ACCESS_TOKEN "
            "(or pass --shop/--token)."
        )
    return shop, token, version


def cmd_shop(args: argparse.Namespace) -> int:
    shop, token, version = _client_config(args)
    client = ShopifyGraphQLClient(shop, token, api_version=version)
    payload = client.query(SHOP_QUERY)
    data = (payload.get("data") or {}).get("shop") or {}
    if args.format == "json":
        print(json.dumps(data, indent=2))
    else:
        print(f"Name:   {data.get('name')}")
        print(f"Domain: {data.get('myshopifyDomain')}")
        print(f"Plan:   {(data.get('plan') or {}).get('displayName')}")
    return 0


def cmd_products_list(args: argparse.Namespace) -> int:
    shop, token, version = _client_config(args)
    client = ShopifyRESTClient(shop, token, api_version=version)
    params: Dict[str, Any] = {}
    if args.query:
        params["title"] = args.query
    products: List[Dict[str, Any]] = []
    for product in client.paginate("products.json", "products", params=params, limit=args.limit):
        products.append(product)
        if args.format == "table":
            print(f"{product.get('id')}\t{product.get('status')}\t{product.get('title')}")
    if args.format == "json":
        print(json.dumps(products, indent=2))
    print(f"# {len(products)} product(s)", file=sys.stderr)
    return 0


def cmd_graphql(args: argparse.Namespace) -> int:
    shop, token, version = _client_config(args)
    client = ShopifyGraphQLClient(shop, token, api_version=version)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as handle:
            query = handle.read()
    elif args.query:
        query = args.query
    else:
        query = sys.stdin.read()
    variables = json.loads(args.variables) if args.variables else None
    payload = client.query(query, variables)
    print(json.dumps(payload, indent=2))
    return 0 if not payload.get("errors") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spc", description="A small CLI for the Shopify Admin API.")
    parser.add_argument("--shop", help="my-store.myshopify.com (or set SHOPIFY_STORE_DOMAIN)")
    parser.add_argument("--token", help="Admin API access token (or set SHOPIFY_ADMIN_ACCESS_TOKEN)")
    parser.add_argument("--api-version", help="e.g. 2025-10 (or set SHOPIFY_API_VERSION)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    shop_parser = subparsers.add_parser("shop", help="Print basic shop info")
    shop_parser.add_argument("--format", choices=["table", "json"], default="table")
    shop_parser.set_defaults(func=cmd_shop)

    products_parser = subparsers.add_parser("products", help="Work with products")
    products_sub = products_parser.add_subparsers(dest="products_command", required=True)
    list_parser = products_sub.add_parser("list", help="List products (paginated)")
    list_parser.add_argument("--query", help="Filter by title (REST `title` param)")
    list_parser.add_argument("--limit", type=int, help="Stop after N products")
    list_parser.add_argument("--format", choices=["table", "json"], default="table")
    list_parser.set_defaults(func=cmd_products_list)

    graphql_parser = subparsers.add_parser("graphql", help="Run a raw GraphQL query")
    graphql_parser.add_argument("query", nargs="?", help="Inline query (omit to use --file or stdin)")
    graphql_parser.add_argument("--file", help="Read the query from a .graphql file")
    graphql_parser.add_argument("--variables", help="JSON-encoded variables object")
    graphql_parser.set_defaults(func=cmd_graphql)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ShopifyAPIError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
