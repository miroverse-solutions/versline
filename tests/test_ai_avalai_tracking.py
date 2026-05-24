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


class TestAIAvalaiTracking(unittest.TestCase):
    @patch("versline.services.ai.configure_openai", autospec=True)
    def test_send_openai_tracks_avalai_request_id(self, configure_openai_mock):
        configure_openai_mock.return_value = _FakeOpenAIClient()

        client = AIClient(provider="avalai", model="dummy", api_key="k")
        questions, _cost = client._send_openai("context", "batch")

        self.assertEqual(questions, [])
        self.assertIn("req_test_123", client.tracker.avalai_request_ids)


if __name__ == "__main__":
    unittest.main()
