import json
import unittest

from shopify_client.graphql import ShopifyGraphQLClient
from shopify_client.http import HTTPResponse, ShopifyAPIError, ShopifyRateLimitError

from .fakes import FakeTransport, SleepRecorder, json_response


def cost_extensions(currently_available, restore_rate=50.0, maximum_available=1000.0):
    return {
        "cost": {
            "requestedQueryCost": 10,
            "actualQueryCost": 10,
            "throttleStatus": {
                "maximumAvailable": maximum_available,
                "currentlyAvailable": currently_available,
                "restoreRate": restore_rate,
            },
        }
    }


def make_client(transport, sleep=None):
    return ShopifyGraphQLClient(
        "test-shop.myshopify.com",
        "shpat_test",
        transport=transport,
        sleep=sleep or SleepRecorder(),
    )


class ShopifyGraphQLClientTests(unittest.TestCase):
    def test_query_sends_auth_header_and_body(self):
        transport = FakeTransport(
            [json_response(200, {"data": {"shop": {"name": "Test"}}, "extensions": cost_extensions(900)})]
        )
        client = make_client(transport)

        payload = client.query("query { shop { name } }")

        self.assertEqual(payload["data"]["shop"]["name"], "Test")
        call = transport.calls[0]
        self.assertEqual(call.headers["X-Shopify-Access-Token"], "shpat_test")
        sent = json.loads(call.body.decode("utf-8"))
        self.assertEqual(sent["query"], "query { shop { name } }")

    def test_records_throttle_status_from_extensions(self):
        transport = FakeTransport(
            [json_response(200, {"data": {}, "extensions": cost_extensions(432, restore_rate=50)})]
        )
        client = make_client(transport)

        client.query("query { shop { name } }")

        status = client.last_throttle_status
        self.assertEqual(status.currently_available, 432)
        self.assertEqual(status.restore_rate, 50)
        self.assertEqual(status.maximum_available, 1000)

    def test_waits_before_next_query_when_bucket_is_low(self):
        transport = FakeTransport(
            [
                json_response(200, {"data": {}, "extensions": cost_extensions(10, restore_rate=50)}),
                json_response(200, {"data": {}, "extensions": cost_extensions(900, restore_rate=50)}),
            ]
        )
        sleep = SleepRecorder()
        client = make_client(transport, sleep=sleep)

        client.query("query { a }")
        self.assertEqual(sleep.calls, [])  # nothing to wait for yet on the first call

        client.query("query { b }")
        # buffer is 50, bucket was at 10 with restore_rate 50 -> (50-10)/50 = 0.8s
        self.assertEqual(sleep.calls, [0.8])

    def test_retries_on_throttled_error_then_succeeds(self):
        transport = FakeTransport(
            [
                json_response(
                    429,
                    {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]},
                ),
                json_response(200, {"data": {"shop": {"name": "Test"}}, "extensions": cost_extensions(900)}),
            ]
        )
        sleep = SleepRecorder()
        client = make_client(transport, sleep=sleep)

        payload = client.query("query { shop { name } }", max_retries=1)

        self.assertEqual(payload["data"]["shop"]["name"], "Test")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(sleep.calls), 1)

    def test_raises_rate_limit_error_after_exhausting_retries(self):
        throttled = json_response(
            429, {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
        )
        transport = FakeTransport([throttled, throttled])
        client = make_client(transport)

        with self.assertRaises(ShopifyRateLimitError):
            client.query("query { shop { name } }", max_retries=1)

    def test_raises_api_error_on_non_throttling_errors(self):
        transport = FakeTransport(
            [json_response(200, {"errors": [{"message": "Field 'bogus' doesn't exist"}], "data": None})]
        )
        client = make_client(transport)

        with self.assertRaises(ShopifyAPIError):
            client.query("query { bogus }")

    def test_server_error_raises_shopify_api_error(self):
        transport = FakeTransport([HTTPResponse(status=500, headers={}, body=b"internal error")])
        client = make_client(transport)

        with self.assertRaises(ShopifyAPIError):
            client.query("query { shop { name } }")


if __name__ == "__main__":
    unittest.main()
