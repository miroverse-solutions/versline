import unittest
from unittest.mock import patch

import requests

from versline.config import settings
from versline.services.transcription import AudioTranscriber


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON body")
        return self._json_data


class TestSttTimestampFallback(unittest.TestCase):
    def setUp(self):
        self.transcriber = AudioTranscriber()
        self.orig_endpoint = settings.llm.api_endpoint
        self.orig_api_key = settings.llm.api_key
        self.orig_timeout = settings.transcription.timestamp_timeout_seconds
        settings.llm.api_endpoint = "https://api.avalai.ir/v1"
        settings.llm.api_key = "test-key"
        settings.transcription.timestamp_timeout_seconds = 7

    def tearDown(self):
        settings.llm.api_endpoint = self.orig_endpoint
        settings.llm.api_key = self.orig_api_key
        settings.transcription.timestamp_timeout_seconds = self.orig_timeout

    def test_falls_back_to_srt_when_verbose_json_times_out(self):
        srt_body = """1
00:00:00,000 --> 00:00:01,500
سلام

2
00:00:01,500 --> 00:00:03,000
دنیا
"""

        calls = []

        def fake_post(url, headers, files, data, timeout, proxies=None):
            calls.append({"data": dict(data), "timeout": timeout, "url": url})
            if data.get("response_format") == "verbose_json":
                raise requests.exceptions.ReadTimeout("timed out")
            return _FakeResponse(
                status_code=200,
                text=srt_body,
                headers={"content-type": "text/plain"},
            )

        with patch("requests.post", side_effect=fake_post):
            result = self.transcriber.transcribe_chunk_via_stt_api(
                model_name="gpt-4o-transcribe",
                audio_path=__file__,
                max_retries=1,
                with_timestamps=True,
            )

        self.assertEqual(result.get("source"), "api_native_srt")
        self.assertEqual(len(result.get("segments", [])), 2)
        self.assertEqual(calls[0]["data"].get("response_format"), "verbose_json")
        self.assertEqual(calls[1]["data"].get("response_format"), "srt")
        # Code clamps timeout to at least 10s to avoid too-small values.
        self.assertEqual(calls[0]["timeout"], 10)

    def test_uses_verbose_json_segments_when_available(self):
        calls = []

        def fake_post(url, headers, files, data, timeout, proxies=None):
            calls.append(dict(data))
            return _FakeResponse(
                status_code=200,
                json_data={
                    "text": "hello",
                    "segments": [
                        {"start": 0, "end": 1.2, "text": "hello"},
                    ],
                    "duration": 1.2,
                    "language": "fa",
                },
            )

        with patch("requests.post", side_effect=fake_post):
            result = self.transcriber.transcribe_chunk_via_stt_api(
                model_name="gpt-4o-transcribe",
                audio_path=__file__,
                max_retries=1,
                with_timestamps=True,
            )

        self.assertEqual(result.get("source"), "api_native_verbose_json")
        self.assertEqual(len(result.get("segments", [])), 1)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
