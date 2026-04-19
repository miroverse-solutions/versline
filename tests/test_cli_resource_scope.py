import os
import unittest
from unittest.mock import patch

from versline import cli
from versline.config import settings


class TestCliResourceScope(unittest.TestCase):
    def setUp(self):
        self._orig_embedding_provider = settings.rag.embedding_provider
        self._orig_rerank_provider = settings.rag.rerank_provider
        self._orig_rerank_enabled = settings.rag.rerank_enabled

    def tearDown(self):
        settings.rag.embedding_provider = self._orig_embedding_provider
        settings.rag.rerank_provider = self._orig_rerank_provider
        settings.rag.rerank_enabled = self._orig_rerank_enabled

    def test_non_rag_command_does_not_apply_limits(self):
        with (
            patch("versline.cli.sys.argv", ["versline", "transcribe", "input.m4a"]),
            patch("versline.cli.configure_logging"),
            patch("versline.cli.apply_resource_limits") as apply_limits,
        ):
            cli.main(verbose=False, env_file=None)

        apply_limits.assert_not_called()

    def test_local_rag_ingest_applies_limits_and_sets_soft_trigger(self):
        settings.rag.embedding_provider = "optimum-intel"

        with (
            patch("versline.cli.sys.argv", ["versline", "rag", "ingest", "docs.md"]),
            patch("versline.cli.configure_logging"),
            patch("versline.cli.apply_resource_limits") as apply_limits,
            patch.dict(os.environ, {}, clear=True),
        ):
            cli.main(verbose=False, env_file=None)
            self.assertEqual(os.environ.get("VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT"), "95")

        apply_limits.assert_called_once()

    def test_rag_ingest_remote_override_skips_limits(self):
        settings.rag.embedding_provider = "optimum-intel"

        with (
            patch(
                "versline.cli.sys.argv",
                [
                    "versline",
                    "rag",
                    "ingest",
                    "docs.md",
                    "--embedding-provider",
                    "avalai",
                ],
            ),
            patch("versline.cli.configure_logging"),
            patch("versline.cli.apply_resource_limits") as apply_limits,
            patch.dict(os.environ, {}, clear=True),
        ):
            cli.main(verbose=False, env_file=None)
            self.assertIsNone(os.environ.get("VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT"))

        apply_limits.assert_not_called()


if __name__ == "__main__":
    unittest.main()
