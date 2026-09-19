import unittest

from shopify_client.http import HTTPResponse, request_with_retries

from .fakes import FakeTransport, SleepRecorder, json_response


class RequestWithRetriesTests(unittest.TestCase):
    def test_returns_immediately_on_success(self):
        transport = FakeTransport([json_response(200, {"ok": True})])
        sleep = SleepRecorder()

        response = request_with_retries(transport, "https://x/y", "GET", {}, None, sleep=sleep)

        self.assertEqual(response.status, 200)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(sleep.calls, [])

    def test_retries_on_429_using_retry_after_header(self):
        transport = FakeTransport(
            [
                HTTPResponse(status=429, headers={"Retry-After": "2"}, body=b"{}"),
                json_response(200, {"ok": True}),
            ]
        )
        sleep = SleepRecorder()

        response = request_with_retries(transport, "https://x/y", "GET", {}, None, sleep=sleep)

        self.assertEqual(response.status, 200)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(sleep.calls, [2.0])

    def test_gives_up_after_max_retries(self):
        transport = FakeTransport(
            [
                HTTPResponse(status=429, headers={}, body=b"{}"),
                HTTPResponse(status=429, headers={}, body=b"{}"),
            ]
        )
        sleep = SleepRecorder()

        response = request_with_retries(
            transport, "https://x/y", "GET", {}, None, max_retries=1, sleep=sleep
        )

        self.assertEqual(response.status, 429)
        self.assertEqual(len(transport.calls), 2)
        # Missing Retry-After falls back to the 1-second default.
        self.assertEqual(sleep.calls, [1.0])

    def test_malformed_retry_after_falls_back_to_default(self):
        transport = FakeTransport(
            [
                HTTPResponse(status=429, headers={"Retry-After": "not-a-number"}, body=b"{}"),
                json_response(200, {"ok": True}),
            ]
        )
        sleep = SleepRecorder()

        request_with_retries(transport, "https://x/y", "GET", {}, None, sleep=sleep)

        self.assertEqual(sleep.calls, [1.0])


if __name__ == "__main__":
    unittest.main()
