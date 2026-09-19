# shopify-api-python-client

A lightweight Python client for the Shopify Admin REST and GraphQL APIs — cursor pagination, cost-aware GraphQL throttle pacing, and 429 retry, with **zero runtime dependencies**.

**Free audit for your own store while you're here:** [audit.ecomswiftllc.com](https://audit.ecomswiftllc.com/?utm_source=github&utm_medium=repo&utm_campaign=shopify-api-python-client) checks SEO, speed, CRO and AI-visibility in one pass.

We kept reaching for a Python script against the Admin API and reaching for `requests` + hand-rolled pagination + a `while True: try/except 429` loop every time. This is that boilerplate, written once: a REST client that follows the `Link` header for you, a GraphQL client that reads the `extensions.cost.throttleStatus` Shopify already sends back and paces itself before you ever see a 429, and a small `spc` CLI on top for quick lookups from a terminal.

## Example

```
$ export SHOPIFY_STORE_DOMAIN=my-store.myshopify.com
$ export SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxx

$ spc shop
Name:   My Store
Domain: my-store.myshopify.com
Plan:   Basic Shopify

$ spc products list --limit 3
8890123456789   active  Canvas Tote Bag
8890123456790   active  Ceramic Mug
8890123456791   draft   Linen Napkin Set
# 3 product(s)

$ spc graphql 'query { shop { name currencyCode } }'
{
  "data": {
    "shop": {
      "name": "My Store",
      "currencyCode": "USD"
    }
  },
  "extensions": {
    "cost": {
      "requestedQueryCost": 1,
      "actualQueryCost": 1,
      "throttleStatus": {
        "maximumAvailable": 1000,
        "currentlyAvailable": 999,
        "restoreRate": 50
      }
    }
  }
}
```

(Illustrative output — your store's data and IDs will differ.)

```python
from shopify_client import ShopifyRESTClient, ShopifyGraphQLClient

rest = ShopifyRESTClient("my-store.myshopify.com", "shpat_xxx")
for product in rest.paginate("products.json", "products", params={"status": "active"}):
    print(product["title"])

gql = ShopifyGraphQLClient("my-store.myshopify.com", "shpat_xxx")
payload = gql.query("query { shop { name } }")
print(payload["data"]["shop"]["name"])
```

## Features

- **REST client** (`ShopifyRESTClient`) — `get`/`post`/`put`/`delete` over any Admin REST path, with auth headers and JSON encode/decode handled for you.
- **Cursor pagination that doesn't fight the API.** `paginate()` follows the `Link: <url>; rel="next"` header Shopify's REST API returns — it never guesses or constructs the next URL itself, which is what breaks when Shopify changes cursor internals.
- **GraphQL client** (`ShopifyGraphQLClient`) with **proactive, cost-aware throttling.** Every GraphQL response carries the current leaky-bucket state under `extensions.cost.throttleStatus`. This client remembers it and sleeps *before* the next query if the bucket looks low, instead of firing a query and hoping — the mechanism Shopify's own rate-limit docs describe.
- **429 retry with `Retry-After`.** The REST client retries automatically, honoring the server's requested wait.
- **A small CLI (`spc`)** for `shop`, `products list` (paginated), and `graphql` (run any raw query/mutation from the command line or a `.graphql` file) — useful for one-off lookups without writing a script.
- **Pluggable transport.** Every client takes an optional `transport` callable, so you can swap in `requests`, `httpx`, or a test double without touching client logic. The default uses only `urllib` from the standard library.
- **Zero runtime dependencies.** No `requests`, no SDK. The whole thing is stdlib.

## Installation

```bash
pip install shopify-api-python-client
```

The published PyPI package is not live yet; until it is, clone this repo and either run `pip install -e .` for the `spc` command and importable package, or just copy the `shopify_client/` directory into your project — it has no dependencies to bring along.

Requires Python 3.9+.

### Getting an access token

1. In your store admin: **Settings → Apps and sales channels → Develop apps → Create an app.**
2. Under **Configuration → Admin API integration**, grant the scopes you need (e.g. `read_products` to list products).
3. Install the app and copy the **Admin API access token** (`shpat_...`).
4. Export it together with your store domain:

```bash
export SHOPIFY_STORE_DOMAIN=my-store.myshopify.com
export SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Usage

### CLI

```
spc shop                          Print the shop's name, domain and plan
spc products list                 List products (follows Link-header pagination)
spc graphql <query>                Run a raw GraphQL query or mutation
```

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--shop` / `--token` / `--api-version` | all | override the env vars for one call |
| `--format table\|json` | `shop`, `products list` | output shape |
| `--query <text>` | `products list` | filter by title (REST `title` param) |
| `--limit <n>` | `products list` | stop after n products |
| `--file <path>` | `graphql` | read the query from a `.graphql` file instead of an argument |
| `--variables <json>` | `graphql` | JSON-encoded variables object |

```bash
# Everything active, as JSON, capped at 50
spc products list --query "active" --limit 50 --format json

# Run a mutation from a file with variables
spc graphql --file mutations/tag_product.graphql --variables '{"id": "gid://shopify/Product/1", "tags": ["sale"]}'
```

### As a library

```python
from shopify_client import ShopifyRESTClient, ShopifyGraphQLClient, ShopifyAPIError, ShopifyRateLimitError

rest = ShopifyRESTClient("my-store.myshopify.com", "shpat_xxx", api_version="2025-10")

# Pagination is a generator — nothing is fetched until you iterate it.
titles = [p["title"] for p in rest.paginate("products.json", "products", limit=500)]

gql = ShopifyGraphQLClient("my-store.myshopify.com", "shpat_xxx")
try:
    payload = gql.query("mutation { productCreate(input: {title: \"Test\"}) { product { id } } }")
except ShopifyRateLimitError:
    print("still throttled after retries — back off and try again later")
except ShopifyAPIError as error:
    print(f"request failed: {error} (status={error.status})")

# Inspect the bucket yourself if you're pipelining many calls.
status = gql.last_throttle_status
if status:
    print(status.currently_available, "/", status.maximum_available)
```

Runnable versions of these live in [`examples/`](examples): [`rest_pagination.py`](examples/rest_pagination.py), [`graphql_shop_info.py`](examples/graphql_shop_info.py), and [`graphql_cost_aware_loop.py`](examples/graphql_cost_aware_loop.py) (a tight GraphQL loop that never trips the rate limit on its own).

## What it does NOT do

- **No automatic API-version negotiation.** You pass `--api-version` / `api_version=`; it defaults to `2025-10` but doesn't discover or upgrade it for you.
- **No resource-specific helpers.** There's no `client.products.create(...)` — you pass the REST path or GraphQL document yourself, same as `curl`. This is a transport layer, not an ORM.
- **The GraphQL throttle pacing is proactive, not perfect.** It reacts to the *last* response's bucket state, so a sudden burst of high-cost queries can still get a 429/`THROTTLED` back — which is why `query()` also retries with backoff on that response, up to `max_retries`.
- **No OAuth flow.** Bring your own Admin API access token (custom app or public app install) — this client doesn't handle the install/authorize dance.
- **No bulk operations (`bulkOperationRunQuery`) helper.** For exports beyond a few thousand records, Shopify's own bulk operations API is the right tool; this client only issues synchronous queries.
- **No webhook handling.** If you need that, our [`shopify-webhook-toolkit`](https://github.com/EcomswiftLLC/shopify-webhook-toolkit) covers HMAC verification and local webhook development.
- **Not run against a live store by us in CI.** The GraphQL cost/throttle shape was validated against the 2025-10 Admin schema docs and the 23 tests exercise the retry, pagination and throttle logic against stubbed HTTP responses — no network calls in the test suite. Try it against a development store first.

## FAQ

**Why not just use `requests`?**
You can — pass a `transport` callable that wraps `requests` and every method still works. This exists for people who don't want a dependency for what is, underneath, one HTTP call at a time.

**Does it handle GraphQL bulk operations?**
No — `bulkOperationRunQuery` is an async job (poll a URL, download a JSONL file), which is a different enough shape that it belongs in its own tool rather than bolted onto a synchronous client.

**What happens if I hit the rate limit anyway?**
For REST, a 429 is retried automatically using the `Retry-After` header. For GraphQL, `query()` retries on a throttled response with backoff up to `max_retries`, then raises `ShopifyRateLimitError` so you can decide what to do (queue it, skip it, alert).

**Can I point it at a different API version?**
Yes — `ShopifyRESTClient(shop, token, api_version="2026-01")` or `--api-version 2026-01` on the CLI.

If you're building something bigger against the Admin API and want a second pair of eyes on your store itself, our [free Shopify tools](https://www.ecomswiftllc.com/free-tools) and the [store audit](https://audit.ecomswiftllc.com/?utm_source=github&utm_medium=repo&utm_campaign=shopify-api-python-client) (SEO, speed, CRO, AI visibility) are a good place to start.

## Related Shopify tools

- [`shopify-webhook-toolkit`](https://github.com/EcomswiftLLC/shopify-webhook-toolkit) — verify, log and replay Shopify webhooks locally.
- [`shopify-metafields-manager`](https://github.com/Ecom-Swift-LLC/shopify-metafields-manager) — export, bulk-import and audit Shopify metafields.
- [`shopify-order-export-cli`](https://github.com/Ecom-Swift-LLC/shopify-order-export-cli) — export Shopify orders to CSV/JSON and get a revenue/customer report.
- [`shopify-store-audit-toolkit`](https://github.com/EcomswiftLLC/shopify-store-audit-toolkit) — CLI that audits a live store's SEO, structured data and performance signals.
- [`shopify-audit-mcp`](https://github.com/EcomswiftLLC/shopify-audit-mcp) — the same audit as a tool for Claude, Cursor and other MCP clients.

## Contributing

Issues and PRs welcome — especially resource-specific convenience wrappers (products, orders, customers), an async transport example (`httpx.AsyncClient` / `aiohttp`), and a `bulkOperationRunQuery` helper.

## Roadmap

- Publish to PyPI.
- An async variant of both clients behind the same `transport` seam.
- A thin `BulkOperation` helper that submits a query, polls, and streams the resulting JSONL.

## License

MIT © Ecom Swift LLC

## Need help?

This project is maintained by **Ecom Swift LLC**, a Shopify Partner.

- 🛍️ Shopify Partner Directory: https://www.shopify.com/partners/directory/partner/waowy
- ✉️ Email: support@ecomswiftllc.com
- 💬 WhatsApp: https://wa.me/16312511767

---

Want someone to build against the Admin API for you, or just check your store's health? [Get a free store audit](https://audit.ecomswiftllc.com/?utm_source=github&utm_medium=repo&utm_campaign=shopify-api-python-client) (SEO, speed, CRO, AI visibility) or browse our other [free Shopify tools](https://www.ecomswiftllc.com/free-tools). We're **Ecom Swift LLC**, a Shopify Partner Agency — [www.ecomswiftllc.com](https://www.ecomswiftllc.com).
