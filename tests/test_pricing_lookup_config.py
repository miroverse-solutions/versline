import os
import unittest
from unittest.mock import patch

from versline.config import settings
from versline.services.pricing import CostReport, TokenTracker, print_cost_report


class TestPricingLookupConfig(unittest.TestCase):
    def setUp(self):
        self._orig_proxy = settings.llm.proxy
        self._orig_user_api_key = settings.llm.avalai_user_api_key

    def tearDown(self):
        settings.llm.proxy = self._orig_proxy
        settings.llm.avalai_user_api_key = self._orig_user_api_key

    def _make_tracker(self):
        tracker = TokenTracker()
        tracker.add_avalai_request("req_123")
        return tracker

    def test_lookup_prefers_user_api_key_and_proxy_from_settings(self):
        settings.llm.avalai_user_api_key = "user-key"
        settings.llm.proxy = "socks5://127.0.0.1:10808"

        tracker = self._make_tracker()
        with patch(
            "versline.services.pricing.lookup_avalai_cost",
            return_value=CostReport(total_cost_usd=0.0, total_cost_irt=0.0, found=0),
        ) as lookup:
            print_cost_report(tracker, api_key="llm-key")

        lookup.assert_called_once()
        args, kwargs = lookup.call_args
        self.assertEqual(args[1], "user-key")
        self.assertEqual(kwargs.get("proxy"), "socks5://127.0.0.1:10808")

    def test_lookup_falls_back_to_passed_api_key(self):
        settings.llm.avalai_user_api_key = None
        settings.llm.proxy = None

        tracker = self._make_tracker()
        with patch(
            "versline.services.pricing.lookup_avalai_cost",
            return_value=CostReport(total_cost_usd=0.0, total_cost_irt=0.0, found=0),
        ) as lookup:
            print_cost_report(tracker, api_key="llm-key")

        lookup.assert_called_once()
        args, kwargs = lookup.call_args
        self.assertEqual(args[1], "llm-key")
        self.assertIsNone(kwargs.get("proxy"))

    def test_lookup_uses_env_user_api_key_when_settings_empty(self):
        settings.llm.avalai_user_api_key = None
        settings.llm.proxy = None

        tracker = self._make_tracker()
        with (
            patch.dict(os.environ, {"VERSLINE_LLM_AVALAI_USER_API_KEY": "env-user-key"}, clear=False),
            patch(
                "versline.services.pricing.lookup_avalai_cost",
                return_value=CostReport(total_cost_usd=0.0, total_cost_irt=0.0, found=0),
            ) as lookup,
        ):
            print_cost_report(tracker, api_key="llm-key")

        lookup.assert_called_once()
        args, _kwargs = lookup.call_args
        self.assertEqual(args[1], "env-user-key")


if __name__ == "__main__":
    unittest.main()
