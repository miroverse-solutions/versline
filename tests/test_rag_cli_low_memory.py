import unittest
from unittest.mock import patch

from versline.services.rag.tuning import tune_ingest_settings


class TestIngestTuning(unittest.TestCase):
    @patch("versline.services.rag.tuning._read_linux_available_ram_mb", return_value=3200)
    def test_low_memory_profile_is_strict(self, _mock_ram):
        decision = tune_ingest_settings(
            auto_tune=True,
            low_memory=True,
            embedding_provider="optimum-intel",
            embedding_device=None,
            embedding_batch_size=12,
            ingestion_batch_size=32,
            max_ram_mb=0,
        )

        self.assertEqual(decision.profile, "low-memory")
        self.assertEqual(decision.embedding_device, "cpu")
        self.assertEqual(decision.embedding_batch_size, 2)
        self.assertEqual(decision.ingestion_batch_size, 8)

    @patch("versline.services.rag.tuning._read_linux_available_ram_mb", return_value=3200)
    def test_auto_tune_local_provider_uses_small_batches(self, _mock_ram):
        decision = tune_ingest_settings(
            auto_tune=True,
            low_memory=False,
            embedding_provider="optimum-intel",
            embedding_device=None,
            embedding_batch_size=None,
            ingestion_batch_size=None,
            max_ram_mb=0,
        )

        self.assertEqual(decision.profile, "local-tiny-ram")
        self.assertEqual(decision.embedding_device, "cpu")
        self.assertEqual(decision.embedding_batch_size, 1)
        self.assertEqual(decision.ingestion_batch_size, 2)

    @patch("versline.services.rag.tuning._read_linux_available_ram_mb", return_value=3200)
    def test_manual_mode_keeps_values(self, _mock_ram):
        decision = tune_ingest_settings(
            auto_tune=False,
            low_memory=False,
            embedding_provider="optimum-intel",
            embedding_device="cuda",
            embedding_batch_size=12,
            ingestion_batch_size=32,
            max_ram_mb=0,
        )

        self.assertEqual(decision.profile, "manual")
        self.assertEqual(decision.embedding_device, "cuda")
        self.assertEqual(decision.embedding_batch_size, 12)
        self.assertEqual(decision.ingestion_batch_size, 32)

    @patch("versline.services.rag.tuning._read_linux_available_ram_mb", return_value=30000)
    def test_remote_provider_keeps_defaults(self, _mock_ram):
        decision = tune_ingest_settings(
            auto_tune=True,
            low_memory=False,
            embedding_provider="openai",
            embedding_device=None,
            embedding_batch_size=None,
            ingestion_batch_size=None,
            max_ram_mb=0,
        )

        self.assertEqual(decision.profile, "remote-default")
        self.assertIsNone(decision.embedding_device)
        self.assertIsNone(decision.embedding_batch_size)
        self.assertIsNone(decision.ingestion_batch_size)

    @patch("versline.services.rag.tuning._read_linux_available_ram_mb", return_value=30000)
    @patch.dict("os.environ", {"VERSLINE_RESOURCE_USE_CGROUP_HARD_LIMIT": "0"}, clear=False)
    def test_watchdog_mode_uses_conservative_openvino_profile(self, _mock_ram):
        decision = tune_ingest_settings(
            auto_tune=True,
            low_memory=False,
            embedding_provider="optimum-intel",
            embedding_device="GPU",
            embedding_device_explicit=False,
            embedding_batch_size=None,
            ingestion_batch_size=None,
            max_ram_mb=16384,
        )

        self.assertEqual(decision.profile, "local-watchdog-conservative")
        self.assertEqual(decision.embedding_device, "cpu")
        self.assertEqual(decision.embedding_batch_size, 2)
        self.assertEqual(decision.ingestion_batch_size, 8)

    @patch("versline.services.rag.tuning._read_linux_available_ram_mb", return_value=30000)
    @patch.dict("os.environ", {"VERSLINE_RESOURCE_USE_CGROUP_HARD_LIMIT": "0"}, clear=False)
    def test_watchdog_mode_keeps_explicit_gpu_device(self, _mock_ram):
        decision = tune_ingest_settings(
            auto_tune=True,
            low_memory=False,
            embedding_provider="optimum-intel",
            embedding_device="GPU",
            embedding_device_explicit=True,
            embedding_batch_size=None,
            ingestion_batch_size=None,
            max_ram_mb=16384,
        )

        self.assertEqual(decision.profile, "local-watchdog-conservative")
        self.assertEqual(decision.embedding_device, "GPU")
        self.assertEqual(decision.embedding_batch_size, 2)
        self.assertEqual(decision.ingestion_batch_size, 8)


if __name__ == "__main__":
    unittest.main()
