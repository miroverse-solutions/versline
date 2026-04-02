import os
import time
import unittest
from unittest.mock import patch

from versline.services.rag.runtime import TokenRateLimiter, RateLimiter, retry_call, scoped_proxy


class TestRAGRuntime(unittest.TestCase):
    def test_scoped_proxy_clears_and_restores(self):
        os.environ["HTTP_PROXY"] = "http://old-proxy:8080"
        os.environ["HTTPS_PROXY"] = "http://old-proxy:8080"

        with scoped_proxy(None):
            self.assertNotIn("HTTP_PROXY", os.environ)
            self.assertNotIn("HTTPS_PROXY", os.environ)

        self.assertEqual(os.environ.get("HTTP_PROXY"), "http://old-proxy:8080")
        self.assertEqual(os.environ.get("HTTPS_PROXY"), "http://old-proxy:8080")

    def test_retry_call_retries_then_succeeds(self):
        counter = {"value": 0}

        def operation():
            counter["value"] += 1
            if counter["value"] < 3:
                raise RuntimeError("temporary error")
            return "ok"

        result = retry_call(
            operation,
            max_retries=4,
            base_delay_seconds=0.01,
            max_delay_seconds=0.02,
            operation_name="test_operation",
        )

        self.assertEqual(result, "ok")
        self.assertEqual(counter["value"], 3)

    def test_rate_limiter_waits_when_enabled(self):
        limiter = RateLimiter(requests_per_minute=1200)
        start = time.monotonic()
        limiter.wait()
        limiter.wait()
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.04)

    def test_token_rate_limiter_waits_when_enabled(self):
        limiter = TokenRateLimiter(tokens_per_minute=60)
        clock = {"value": 0.0}

        def fake_monotonic():
            return clock["value"]

        def fake_sleep(seconds):
            clock["value"] += seconds

        with patch("versline.services.rag.runtime.time.monotonic", side_effect=fake_monotonic):
            with patch("versline.services.rag.runtime.time.sleep", side_effect=fake_sleep) as sleep_mock:
                limiter.wait(60)
                limiter.wait(1)
                self.assertGreaterEqual(sleep_mock.call_count, 1)

    def test_token_rate_limiter_finalize_adjust_mode(self):
        limiter = TokenRateLimiter(tokens_per_minute=100)
        reservation_id = limiter.reserve(20)
        limiter.finalize(reservation_id, actual_tokens=35, mode="estimate_and_adjust")
        self.assertEqual(limiter._window_total, 35)

    def test_token_rate_limiter_finalize_estimate_only_mode(self):
        limiter = TokenRateLimiter(tokens_per_minute=100)
        reservation_id = limiter.reserve(20)
        limiter.finalize(reservation_id, actual_tokens=35, mode="estimate_only")
        self.assertEqual(limiter._window_total, 20)


if __name__ == "__main__":
    unittest.main()
