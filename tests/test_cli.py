import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from shopify_client import cli


class FakeGraphQLClient:
    def __init__(self, shop, token, api_version=None):
        self.shop = shop
        self.token = token

    def query(self, query, variables=None):
        return {
            "data": {
                "shop": {
                    "name": "Test Shop",
                    "myshopifyDomain": "test-shop.myshopify.com",
                    "plan": {"displayName": "Basic Shopify"},
                }
            }
        }


class FakeRESTClient:
    def __init__(self, shop, token, api_version=None):
        self.shop = shop
        self.token = token

    def paginate(self, path, key, params=None, limit=None):
        products = [
            {"id": 1, "title": "Shirt", "status": "active"},
            {"id": 2, "title": "Hat", "status": "draft"},
        ]
        for product in products[:limit] if limit else products:
            yield product


class CLIEnvMixin:
    def setUp(self):
        self._env_patch = patch.dict(
            os.environ,
            {"SHOPIFY_STORE_DOMAIN": "test-shop.myshopify.com", "SHOPIFY_ADMIN_ACCESS_TOKEN": "shpat_test"},
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)


class ShopCommandTests(CLIEnvMixin, unittest.TestCase):
    @patch("shopify_client.cli.ShopifyGraphQLClient", FakeGraphQLClient)
    def test_shop_table_output(self):
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = cli.main(["shop"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Test Shop", out.getvalue())
        self.assertIn("Basic Shopify", out.getvalue())

    @patch("shopify_client.cli.ShopifyGraphQLClient", FakeGraphQLClient)
    def test_shop_json_output(self):
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["shop", "--format", "json"])
        parsed = json.loads(out.getvalue())
        self.assertEqual(parsed["name"], "Test Shop")


class ProductsCommandTests(CLIEnvMixin, unittest.TestCase):
    @patch("shopify_client.cli.ShopifyRESTClient", FakeRESTClient)
    def test_products_list_table(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = cli.main(["products", "list"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Shirt", out.getvalue())
        self.assertIn("Hat", out.getvalue())
        self.assertIn("2 product(s)", err.getvalue())

    @patch("shopify_client.cli.ShopifyRESTClient", FakeRESTClient)
    def test_products_list_respects_limit(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            cli.main(["products", "list", "--limit", "1"])
        self.assertIn("Shirt", out.getvalue())
        self.assertNotIn("Hat", out.getvalue())
        self.assertIn("1 product(s)", err.getvalue())


class ConfigTests(unittest.TestCase):
    def test_missing_credentials_raises_system_exit(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                cli.main(["shop"])


if __name__ == "__main__":
    unittest.main()
