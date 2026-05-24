import os
import unittest
from unittest.mock import MagicMock, patch

from versline.config import settings
from versline.services.pricing import CostReport, TokenTracker, print_cost_report


class TestPricingLookupConfig(unittest.TestCase):
    def setUp(self):
        self._orig_proxy = settings.llm.proxy
        self._orig_api_key = settings.llm.api_key

    def tearDown(self):
        settings.llm.proxy = self._orig_proxy
        settings.llm.api_key = self._orig_api_key

    def _make_tracker(self):
        tracker = TokenTracker()
        tracker.add_avalai_request("019ac4a0-a8f4-7041-845f-3ea8f15dcf1a")
        return tracker

    def _make_tracker_with_invalid_id(self):
        tracker = TokenTracker()
        tracker.add_avalai_request("req_123")
        return tracker

    def test_lookup_uses_passed_api_key_and_proxy_from_settings(self):
        settings.llm.api_key = "settings-key"
        settings.llm.proxy = "socks5://127.0.0.1:10808"

        tracker = self._make_tracker()
        with patch(
            "versline.services.pricing.lookup_avalai_cost",
            return_value=CostReport(total_cost_usd=0.0, total_cost_irt=0.0, found=0),
        ) as lookup:
            print_cost_report(tracker, api_key="llm-key")

        lookup.assert_called_once()
        args, kwargs = lookup.call_args
        self.assertEqual(args[1], "llm-key")
        self.assertEqual(kwargs.get("proxy"), "socks5://127.0.0.1:10808")

    def test_lookup_falls_back_to_settings_api_key(self):
        settings.llm.api_key = "settings-key"
        settings.llm.proxy = None

        tracker = self._make_tracker()
        with patch(
            "versline.services.pricing.lookup_avalai_cost",
            return_value=CostReport(total_cost_usd=0.0, total_cost_irt=0.0, found=0),
        ) as lookup:
            print_cost_report(tracker)

        lookup.assert_called_once()
        args, kwargs = lookup.call_args
        self.assertEqual(args[1], "settings-key")
        self.assertIsNone(kwargs.get("proxy"))

    def test_lookup_uses_proxy_from_env_when_not_in_settings(self):
        settings.llm.api_key = "settings-key"
        settings.llm.proxy = None

        tracker = self._make_tracker()
        with (
            patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9999"}, clear=False),
            patch(
                "versline.services.pricing.lookup_avalai_cost",
                return_value=CostReport(total_cost_usd=0.0, total_cost_irt=0.0, found=0),
            ) as lookup,
        ):
            print_cost_report(tracker)

        lookup.assert_called_once()
        _args, kwargs = lookup.call_args
        self.assertEqual(kwargs.get("proxy"), "http://127.0.0.1:9999")

    def test_lookup_skipped_for_non_uuid_request_ids(self):
        settings.llm.api_key = "settings-key"
        settings.llm.proxy = None

        tracker = self._make_tracker_with_invalid_id()
        with patch("versline.services.pricing.lookup_avalai_cost") as lookup:
            print_cost_report(tracker)

        lookup.assert_not_called()

    def test_invalid_ids_are_shown_in_report(self):
        settings.llm.api_key = "settings-key"
        settings.llm.proxy = None

        tracker = TokenTracker()
        tracker.add_avalai_request("req_123")
        tracker.add_avalai_request("req_456")

        with (
            patch("versline.services.pricing.lookup_avalai_cost") as lookup,
            patch("versline.services.pricing.Table") as table_cls,
            patch("versline.services.pricing.Console") as console_cls,
        ):
            table = MagicMock()
            table_cls.return_value = table
            console = MagicMock()
            console_cls.return_value = console

            print_cost_report(tracker)

        lookup.assert_not_called()
        table.add_row.assert_any_call("AvalAI Cost", "Unavailable (no valid UUID request ID)")
        table.add_row.assert_any_call("AvalAI Invalid IDs", "req_123, req_456")

    def test_composite_request_id_is_parsed_into_valid_ids(self):
        from versline.services.pricing import _split_uuid_ids

        composite = "019e5b0f-c2d2-7440-b275-f94a0543c3ae,6d6d7d4419bd28dd7367cf39f7e8e8a5"
        valid, invalid = _split_uuid_ids([composite])

        self.assertEqual(
            valid,
            [
                "019e5b0f-c2d2-7440-b275-f94a0543c3ae",
                "6d6d7d44-19bd-28dd-7367-cf39f7e8e8a5",
            ],
        )
        self.assertEqual(invalid, [])

    def test_tracker_add_avalai_request_canonicalizes_composite_header(self):
        tracker = TokenTracker()
        tracker.add_avalai_request("019e5b0f-c2d2-7440-b275-f94a0543c3ae,6d6d7d4419bd28dd7367cf39f7e8e8a5")

        self.assertEqual(
            tracker.avalai_request_ids,
            [
                "019e5b0f-c2d2-7440-b275-f94a0543c3ae",
                "6d6d7d44-19bd-28dd-7367-cf39f7e8e8a5",
            ],
        )


if __name__ == "__main__":
    unittest.main()
