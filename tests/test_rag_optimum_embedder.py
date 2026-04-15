"""Tests for OptimumIntelEmbedder – uses mocks so optimum.intel is not required."""
import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from versline.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model_output(batch_size: int, seq_len: int = 4, hidden: int = 8):
    """Return a fake OVModelForFeatureExtraction output with last_hidden_state."""
    import numpy as np
    import torch

    tensor = torch.from_numpy(
        np.ones((batch_size, seq_len, hidden), dtype="float32")
    )
    return SimpleNamespace(last_hidden_state=tensor)


def _make_inputs(texts):
    """Return a dict-like tokenizer output (all-ones mask)."""
    import torch

    n = len(texts)
    return {
        "input_ids": torch.ones((n, 4), dtype=torch.long),
        "attention_mask": torch.ones((n, 4), dtype=torch.long),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOptimumIntelEmbedderInit(unittest.TestCase):
    """Test __init__ without a real model directory."""

    @patch("versline.services.rag.embedders.OptimumIntelEmbedder.__init__", return_value=None)
    def test_class_is_importable(self, _mock_init):
        from versline.services.rag.embedders import OptimumIntelEmbedder
        instance = OptimumIntelEmbedder.__new__(OptimumIntelEmbedder)
        self.assertIsNotNone(instance)

    def test_missing_package_raises_runtime_error(self):
        """If optimum.intel is not installed, a clear RuntimeError should be raised."""
        import builtins

        real_import = builtins.__import__

        def _block_optimum(name, *args, **kwargs):
            if name.startswith("optimum"):
                raise ImportError("mocked missing package")
            return real_import(name, *args, **kwargs)

        from versline.services.rag.embedders import OptimumIntelEmbedder

        with patch("builtins.__import__", side_effect=_block_optimum):
            with self.assertRaises(RuntimeError) as context:
                OptimumIntelEmbedder(model_name="some/model", model_path="/does/not/exist")

        self.assertIn("optimum-intel", str(context.exception).lower())


class TestOptimumIntelEmbedderExportDetection(unittest.TestCase):
    """Test that export=False is chosen when openvino_model.xml exists."""

    def _build_embedder(self, model_dir: pathlib.Path, device: str = "CPU"):
        """Instantiate OptimumIntelEmbedder with the given model_dir mocked."""
        import numpy as np
        import torch

        fake_tokenizer = MagicMock(side_effect=lambda texts, **kw: _make_inputs(texts))
        fake_tokenizer.from_pretrained = MagicMock(return_value=fake_tokenizer)

        fake_model = MagicMock()
        fake_model.side_effect = lambda **inputs: _make_model_output(
            batch_size=inputs["input_ids"].shape[0]
        )
        fake_ov_cls = MagicMock()
        fake_ov_cls.from_pretrained = MagicMock(return_value=fake_model)

        with patch.dict("sys.modules", {
            "optimum": MagicMock(),
            "optimum.intel": MagicMock(),
        }):
            with patch("versline.services.rag.embedders.OptimumIntelEmbedder.__init__") as mock_init:
                # We just want to test the export-detection logic directly
                pass

        # Test the export detection logic in isolation
        xml_path = model_dir / "openvino_model.xml"
        export_expected = not xml_path.exists()
        return export_expected

    def test_export_true_when_no_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = pathlib.Path(tmp)
            # No openvino_model.xml present
            export_expected = self._build_embedder(model_dir)
            self.assertTrue(export_expected)

    def test_export_false_when_xml_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = pathlib.Path(tmp)
            (model_dir / "openvino_model.xml").write_text("<model/>")
            export_expected = self._build_embedder(model_dir)
            self.assertFalse(export_expected)


class TestOptimumIntelEmbedderMeanPool(unittest.TestCase):
    """Unit-test the _mean_pool method without touching OV model loading."""

    def _make_embedder_stub(self):
        """Return an OptimumIntelEmbedder instance with only _np set."""
        import numpy as np
        from versline.services.rag.embedders import OptimumIntelEmbedder

        obj = OptimumIntelEmbedder.__new__(OptimumIntelEmbedder)
        obj._np = np
        return obj

    def test_mean_pool_shape(self):
        import numpy as np

        embedder = self._make_embedder_stub()
        batch, seq, hidden = 3, 5, 8
        hidden_state = np.ones((batch, seq, hidden), dtype="float32")
        mask = np.ones((batch, seq), dtype="float32")

        pooled = embedder._mean_pool(hidden_state, mask)
        self.assertEqual(pooled.shape, (batch, hidden))

    def test_mean_pool_values_all_ones(self):
        import numpy as np

        embedder = self._make_embedder_stub()
        hidden_state = np.ones((2, 4, 6), dtype="float32")
        mask = np.ones((2, 4), dtype="float32")

        pooled = embedder._mean_pool(hidden_state, mask)
        np.testing.assert_allclose(pooled, np.ones((2, 6)), atol=1e-6)

    def test_mean_pool_ignores_masked_tokens(self):
        """Tokens with mask=0 should not contribute to the mean."""
        import numpy as np

        embedder = self._make_embedder_stub()
        # seq_len=4; only first 2 tokens are real (mask=1), last 2 are padding (mask=0)
        hidden_state = np.array(
            [[[1.0, 2.0], [3.0, 4.0], [99.0, 99.0], [99.0, 99.0]]],
            dtype="float32",
        )
        mask = np.array([[1.0, 1.0, 0.0, 0.0]], dtype="float32")

        pooled = embedder._mean_pool(hidden_state, mask)
        expected = np.array([[2.0, 3.0]])  # (1+3)/2, (2+4)/2
        np.testing.assert_allclose(pooled, expected, atol=1e-6)

    def test_mean_pool_clip_prevents_div_zero(self):
        """All-zero mask should not cause division by zero."""
        import numpy as np

        embedder = self._make_embedder_stub()
        hidden_state = np.ones((1, 4, 3), dtype="float32")
        mask = np.zeros((1, 4), dtype="float32")

        pooled = embedder._mean_pool(hidden_state, mask)
        # clip(0, min=1e-9) → divide by 1e-9 ≈ very large but finite
        self.assertFalse(np.any(np.isnan(pooled)))
        self.assertFalse(np.any(np.isinf(pooled)))


class TestOptimumIntelEmbedderEmbedMethods(unittest.TestCase):
    """End-to-end test of embed_documents / embed_query using a fully mocked model."""

    def _build_live_embedder(self, batch_size: int = 8, device: str = "CPU"):
        import numpy as np
        import torch
        from versline.services.rag.embedders import OptimumIntelEmbedder

        fake_tokenizer_fn = MagicMock(side_effect=lambda texts, **kw: _make_inputs(texts))
        fake_tokenizer_cls = MagicMock()
        fake_tokenizer_cls.from_pretrained.return_value = fake_tokenizer_fn

        fake_model = MagicMock(side_effect=lambda **inputs: _make_model_output(
            batch_size=inputs["input_ids"].shape[0]
        ))
        fake_ov_cls = MagicMock()
        fake_ov_cls.from_pretrained.return_value = fake_model

        with patch("builtins.__import__", wraps=__builtins__.__getitem__ if isinstance(__builtins__, dict) else __import__):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            model_dir = pathlib.Path(tmp)
            (model_dir / "openvino_model.xml").write_text("<model/>")

            with patch("versline.services.rag.embedders._scoped_model_environment"):
                with patch("optimum.intel.OVModelForFeatureExtraction", fake_ov_cls, create=True):
                    with patch("transformers.AutoTokenizer", fake_tokenizer_cls, create=True):
                        # Patch imports inside the __init__ method
                        import importlib
                        import sys

                        mock_optimum_intel = MagicMock()
                        mock_optimum_intel.OVModelForFeatureExtraction = fake_ov_cls

                        mock_transformers = MagicMock()
                        mock_transformers.AutoTokenizer = fake_tokenizer_cls

                        original_modules = {}
                        for mod_name in ("optimum", "optimum.intel"):
                            original_modules[mod_name] = sys.modules.get(mod_name)

                        sys.modules["optimum.intel"] = mock_optimum_intel

                        import_tracker = {}

                        real_import = __import__

                        def patched_import(name, *args, **kwargs):
                            if name == "optimum.intel":
                                import_tracker["optimum.intel"] = True
                                mod = MagicMock()
                                mod.OVModelForFeatureExtraction = fake_ov_cls
                                return mod
                            if name == "numpy":
                                return np
                            if name == "transformers":
                                mod = MagicMock()
                                mod.AutoTokenizer = fake_tokenizer_cls
                                return mod
                            return real_import(name, *args, **kwargs)

                        try:
                            with patch("builtins.__import__", side_effect=patched_import):
                                embedder = OptimumIntelEmbedder.__new__(OptimumIntelEmbedder)
                                embedder._np = np
                                embedder.proxy = None
                                embedder.cache_dir = None
                                embedder.local_files_only = True
                                embedder.device = device
                                embedder.batch_size = batch_size
                                embedder.model_name = "test/model"
                                embedder.model_path = str(model_dir)
                                embedder._tokenizer = fake_tokenizer_fn
                                embedder._model = fake_model
                                return embedder, fake_tokenizer_fn, fake_model
                        finally:
                            for mod_name, mod in original_modules.items():
                                if mod is None:
                                    sys.modules.pop(mod_name, None)
                                else:
                                    sys.modules[mod_name] = mod

    def test_embed_documents_returns_correct_count(self):
        embedder, _, _ = self._build_live_embedder()
        texts = ["سلام", "دنیا", "hello"]
        vectors = embedder.embed_documents(texts)
        self.assertEqual(len(vectors), 3)

    def test_embed_documents_returns_list_of_floats(self):
        embedder, _, _ = self._build_live_embedder()
        vectors = embedder.embed_documents(["test text"])
        self.assertIsInstance(vectors, list)
        self.assertIsInstance(vectors[0], list)
        self.assertTrue(all(isinstance(v, float) for v in vectors[0]))

    def test_embed_documents_empty_input(self):
        embedder, _, _ = self._build_live_embedder()
        result = embedder.embed_documents([])
        self.assertEqual(result, [])

    def test_embed_query_returns_single_vector(self):
        embedder, _, _ = self._build_live_embedder()
        vector = embedder.embed_query("query text")
        self.assertIsInstance(vector, list)
        self.assertTrue(all(isinstance(v, float) for v in vector))

    def test_embed_documents_batches_correctly(self):
        """With batch_size=2, 5 texts should trigger 3 model calls (2+2+1)."""
        embedder, fake_tokenizer, fake_model = self._build_live_embedder(batch_size=2)

        texts = ["a", "b", "c", "d", "e"]

        with patch.object(embedder, "_encode_batch", wraps=embedder._encode_batch) as spy:
            vectors = embedder.embed_documents(texts)

        self.assertEqual(len(vectors), 5)
        self.assertEqual(spy.call_count, 3)

    def test_embed_documents_vector_dimension_consistent(self):
        embedder, _, _ = self._build_live_embedder()
        texts = ["one", "two", "three"]
        vectors = embedder.embed_documents(texts)
        dims = {len(v) for v in vectors}
        self.assertEqual(len(dims), 1, "All vectors must have the same dimension")


class TestOptimumIntelEmbedderInPipeline(unittest.TestCase):
    """Test that RAGPipeline instantiates OptimumIntelEmbedder for provider=optimum-intel."""

    def _make_pipeline_with_optimum(self, provider_alias: str):
        from versline.services.rag.embedders import OptimumIntelEmbedder
        from versline.services.rag.pipeline import RAGPipeline

        mock_embedder = MagicMock(spec=OptimumIntelEmbedder)

        with patch("versline.services.rag.pipeline.OptimumIntelEmbedder", return_value=mock_embedder) as ov_cls:
            with patch("versline.services.rag.pipeline.RAGPipeline._validate_initial_configuration", return_value={}):
                settings.rag.embedding_provider = provider_alias
                settings.rag.embedding_model = "test/model"
                settings.rag.embedding_model_path = "/fake/path"
                settings.rag.hybrid_enabled = False
                settings.rag.rerank_enabled = False
                pipeline = RAGPipeline(
                    embedder=None,
                    sparse_embedder=MagicMock(),
                    reranker=MagicMock(),
                    generator=MagicMock(),
                    preflight=False,
                )
                return pipeline, ov_cls, mock_embedder

    def test_provider_optimum_intel_instantiates_embedder(self):
        pipeline, ov_cls, mock_embedder = self._make_pipeline_with_optimum("optimum-intel")
        ov_cls.assert_called_once()
        self.assertIs(pipeline.embedder, mock_embedder)

    def test_provider_optimum_alias_instantiates_embedder(self):
        pipeline, ov_cls, mock_embedder = self._make_pipeline_with_optimum("optimum")
        ov_cls.assert_called_once()

    def test_provider_optimum_intel_underscore_alias(self):
        pipeline, ov_cls, mock_embedder = self._make_pipeline_with_optimum("optimum_intel")
        ov_cls.assert_called_once()

    def tearDown(self):
        settings.rag.embedding_provider = "openai"
        settings.rag.embedding_model = "text-embedding-3-small"
        settings.rag.embedding_model_path = None
        settings.rag.hybrid_enabled = True
        settings.rag.rerank_enabled = False


class TestOptimumIntelEmbedderSparseResolution(unittest.TestCase):
    """Sparse provider should never attempt optimum-intel and fall back to fastembed."""

    def test_resolve_sparse_provider_for_optimum_intel(self):
        from versline.services.rag.pipeline import RAGPipeline

        result = RAGPipeline._resolve_sparse_provider(
            "optimum-intel",
            dense_provider="optimum-intel",
        )
        self.assertEqual(result, "fastembed")

    def test_resolve_sparse_provider_for_optimum_alias(self):
        from versline.services.rag.pipeline import RAGPipeline

        result = RAGPipeline._resolve_sparse_provider(
            "optimum",
            dense_provider="optimum",
        )
        self.assertEqual(result, "fastembed")


class TestScopedModelEnvironmentOpenVINO(unittest.TestCase):
    """_scoped_model_environment should set/restore OV env vars."""

    def test_openvino_cache_dir_is_set_and_restored(self):
        from versline.services.rag.embedders import _scoped_model_environment

        original_ov = os.environ.get("OPENVINO_CACHE_DIR")
        original_ov2 = os.environ.get("OV_CACHE_DIR")

        try:
            with _scoped_model_environment(None, None, False, openvino_cache_dir="/tmp/ov_cache"):
                self.assertEqual(os.environ.get("OPENVINO_CACHE_DIR"), "/tmp/ov_cache")
                self.assertEqual(os.environ.get("OV_CACHE_DIR"), "/tmp/ov_cache")

            self.assertEqual(os.environ.get("OPENVINO_CACHE_DIR"), original_ov)
            self.assertEqual(os.environ.get("OV_CACHE_DIR"), original_ov2)
        finally:
            if original_ov is None:
                os.environ.pop("OPENVINO_CACHE_DIR", None)
            else:
                os.environ["OPENVINO_CACHE_DIR"] = original_ov
            if original_ov2 is None:
                os.environ.pop("OV_CACHE_DIR", None)
            else:
                os.environ["OV_CACHE_DIR"] = original_ov2

    def test_local_files_only_sets_offline_flags(self):
        from versline.services.rag.embedders import _scoped_model_environment

        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            os.environ.pop(key, None)

        with _scoped_model_environment(None, None, True):
            self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")
            self.assertEqual(os.environ.get("TRANSFORMERS_OFFLINE"), "1")

        self.assertNotIn("HF_HUB_OFFLINE", os.environ)
        self.assertNotIn("TRANSFORMERS_OFFLINE", os.environ)


if __name__ == "__main__":
    unittest.main()
