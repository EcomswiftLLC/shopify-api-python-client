import json
import unittest

from shopify_client.http import HTTPResponse, ShopifyAPIError
from shopify_client.rest import ShopifyRESTClient

from .fakes import FakeTransport, json_response


def make_client(transport):
    return ShopifyRESTClient("test-shop.myshopify.com", "shpat_test", transport=transport)


class ShopifyRESTClientTests(unittest.TestCase):
    def test_requires_shop_and_token(self):
        with self.assertRaises(ValueError):
            ShopifyRESTClient("", "token")
        with self.assertRaises(ValueError):
            ShopifyRESTClient("shop.myshopify.com", "")

    def test_get_sends_auth_header_and_decodes_json(self):
        transport = FakeTransport([json_response(200, {"shop": {"name": "Test Shop"}})])
        client = make_client(transport)

        result = client.get("shop.json")

        self.assertEqual(result, {"shop": {"name": "Test Shop"}})
        call = transport.calls[0]
        self.assertEqual(call.method, "GET")
        self.assertTrue(call.url.startswith("https://test-shop.myshopify.com/admin/api/2025-10/shop.json"))
        self.assertEqual(call.headers["X-Shopify-Access-Token"], "shpat_test")

    def test_post_sends_json_body(self):
        transport = FakeTransport([json_response(201, {"product": {"id": 1}})])
        client = make_client(transport)

        result = client.post("products.json", json_body={"product": {"title": "Shirt"}})

        self.assertEqual(result["product"]["id"], 1)
        sent_body = json.loads(transport.calls[0].body.decode("utf-8"))
        self.assertEqual(sent_body, {"product": {"title": "Shirt"}})

    def test_error_status_raises_with_body(self):
        transport = FakeTransport([json_response(404, {"errors": "Not Found"})])
        client = make_client(transport)

        with self.assertRaises(ShopifyAPIError) as ctx:
            client.get("products/999999.json")

        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(ctx.exception.body, {"errors": "Not Found"})

    def test_paginate_follows_link_header_across_pages(self):
        page_two_url = "https://test-shop.myshopify.com/admin/api/2025-10/products.json?page_info=abc123"
        transport = FakeTransport(
            [
                HTTPResponse(
                    status=200,
                    headers={"Link": f'<{page_two_url}>; rel="next"'},
                    body=json.dumps({"products": [{"id": 1}, {"id": 2}]}).encode("utf-8"),
                ),
                HTTPResponse(
                    status=200,
                    headers={},
                    body=json.dumps({"products": [{"id": 3}]}).encode("utf-8"),
                ),
            ]
        )
        client = make_client(transport)

        products = list(client.paginate("products.json", "products"))

        self.assertEqual([p["id"] for p in products], [1, 2, 3])
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[1].url, page_two_url)

    def test_paginate_stops_at_limit_without_fetching_next_page(self):
        page_two_url = "https://test-shop.myshopify.com/admin/api/2025-10/products.json?page_info=abc123"
        transport = FakeTransport(
            [
                HTTPResponse(
                    status=200,
                    headers={"Link": f'<{page_two_url}>; rel="next"'},
                    body=json.dumps({"products": [{"id": 1}, {"id": 2}]}).encode("utf-8"),
                ),
            ]
        )
        client = make_client(transport)

        products = list(client.paginate("products.json", "products", limit=1))

        self.assertEqual([p["id"] for p in products], [1])
        self.assertEqual(len(transport.calls), 1)

    def test_paginate_raises_on_error_mid_pagination(self):
        transport = FakeTransport([json_response(500, {"errors": "boom"})])
        client = make_client(transport)

        with self.assertRaises(ShopifyAPIError):
            list(client.paginate("products.json", "products"))


if __name__ == "__main__":
    unittest.main()
