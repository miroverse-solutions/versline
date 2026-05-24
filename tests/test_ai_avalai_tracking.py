import unittest
from types import SimpleNamespace
from unittest.mock import patch

from versline.services.ai import AIClient


class _FakeRawResponse:
    def __init__(self, parsed, request_id="req_test_123"):
        self._parsed = parsed
        self.headers = {"x-request-id": request_id}

    def parse(self):
        return self._parsed


class _FakeOpenAIClient:
    def __init__(self):
        completion_parsed = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=7),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"questions": []}'))],
        )
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                with_raw_response=SimpleNamespace(
                    create=lambda **kwargs: _FakeRawResponse(completion_parsed)
                )
            )
        )


class _FakeRetryOpenAIClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        index = self.calls if self.calls < len(self._responses) else len(self._responses) - 1
        self.calls += 1
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=7),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._responses[index]))],
        )


class TestAIAvalaiTracking(unittest.TestCase):
    @patch("versline.services.ai.configure_openai", autospec=True)
    def test_send_openai_tracks_avalai_request_id(self, configure_openai_mock):
        configure_openai_mock.return_value = _FakeOpenAIClient()

        client = AIClient(provider="avalai", model="dummy", api_key="k")
        questions, _cost = client._send_openai("context", "batch")

        self.assertEqual(questions, [])
        self.assertIn("req_test_123", client.tracker.avalai_request_ids)

    @patch("versline.services.ai.configure_openai", autospec=True)
    @patch("versline.services.ai.time.sleep", autospec=True)
    def test_send_with_retry_retries_after_json_parse_failure(self, _sleep_mock, configure_openai_mock):
        fake_client = _FakeRetryOpenAIClient([
            "not json",
            '{"questions": [{"question": "Recovered"}]}',
        ])
        configure_openai_mock.return_value = fake_client

        client = AIClient(provider="openai", model="dummy", api_key="k")
        questions, _cost = client.send_with_retry("context", "prompt", batch_info="Batch 2 of 15 (Slides)")

        self.assertEqual(fake_client.calls, 2)
        self.assertEqual(questions, [{"question": "Recovered"}])

    @patch("versline.services.ai.configure_openai", autospec=True)
    @patch("versline.services.ai.time.sleep", autospec=True)
    def test_send_with_retry_returns_empty_after_exhausting_parse_retries(self, _sleep_mock, configure_openai_mock):
        fake_client = _FakeRetryOpenAIClient(["not json"])
        configure_openai_mock.return_value = fake_client

        client = AIClient(provider="openai", model="dummy", api_key="k")
        questions, _cost = client.send_with_retry("context", "prompt", batch_info="Batch 2 of 15 (Slides)")

        self.assertEqual(fake_client.calls, 3)
        self.assertEqual(questions, [])


if __name__ == "__main__":
    unittest.main()
