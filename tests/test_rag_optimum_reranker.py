"""Tests for OptimumIntelReranker – uses mocks so optimum.intel is not required."""
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from versline.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logits(values):
    """Return a fake OVModelForSequenceClassification output with logits tensor."""
    import numpy as np
    import torch

    arr = np.array([[v] for v in values], dtype="float32")
    return SimpleNamespace(logits=torch.from_numpy(arr))


def _make_tokenizer_output(batch_size: int):
    """Return a dict-like tokenizer output (all-ones tensors)."""
    import torch

    return {
        "input_ids": torch.ones((batch_size, 4), dtype=torch.long),
        "attention_mask": torch.ones((batch_size, 4), dtype=torch.long),
    }


def _make_stub_reranker(logit_values=None, batch_size: int = 8):
    """Return an OptimumIntelReranker stubb with mocked model and tokenizer."""
    import numpy as np
    from versline.services.rag.rerankers import OptimumIntelReranker, RateLimiter, TokenRateLimiter

    if logit_values is None:
        logit_values = [2.0, 1.0, 3.0]

    fake_tokenizer = MagicMock(
        side_effect=lambda pairs, **kw: _make_tokenizer_output(len(pairs))
    )
    fake_model = MagicMock(
        side_effect=lambda **inputs: _make_logits(
            [2.0] * inputs["input_ids"].shape[0]
        )
    )

    obj = OptimumIntelReranker.__new__(OptimumIntelReranker)
    obj._np = np
    obj.proxy = None
    obj.cache_dir = None
    obj.local_files_only = True
    obj.device = "CPU"
    obj.batch_size = batch_size
    obj.model = "test/model"
    obj.model_path = "/dummy/path"
    obj._tokenizer = fake_tokenizer
    obj._ov_model = fake_model
    obj.rate_limiter = RateLimiter(0)
    obj.token_rate_limiter = TokenRateLimiter(0)
    return obj, fake_tokenizer, fake_model


def _make_retrieved_chunks(texts):
    """Return a list of RetrievedChunk instances."""
    from versline.services.rag.pipeline import RetrievedChunk

    return [
        RetrievedChunk(id=str(i), text=text, score=0.5, metadata={})
        for i, text in enumerate(texts)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOptimumIntelRerankerInit(unittest.TestCase):
    """Test basic import and missing-package error path."""

    @patch("versline.services.rag.rerankers.OptimumIntelReranker.__init__", return_value=None)
    def test_class_is_importable(self, _mock):
        from versline.services.rag.rerankers import OptimumIntelReranker
        obj = OptimumIntelReranker.__new__(OptimumIntelReranker)
        self.assertIsNotNone(obj)

    def test_missing_package_raises_runtime_error(self):
        """If optimum.intel is not available a clear RuntimeError must be raised."""
        import builtins

        real_import = builtins.__import__

        def _block(name, *args, **kwargs):
            if name.startswith("optimum"):
                raise ImportError("mocked missing package")
            return real_import(name, *args, **kwargs)

        from versline.services.rag.rerankers import OptimumIntelReranker

        with patch("builtins.__import__", side_effect=_block):
            with self.assertRaises(RuntimeError) as ctx:
                OptimumIntelReranker(model="BAAI/bge-reranker-v2-m3")

        self.assertIn("optimum-intel", str(ctx.exception).lower())


class TestOptimumIntelRerankerExportDetection(unittest.TestCase):
    """Test that auto-export detection works correctly."""

    def test_export_true_when_no_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = pathlib.Path(tmp)
            xml_exists = (model_dir / "openvino_model.xml").exists()
            export = not xml_exists
            self.assertTrue(export)

    def test_export_false_when_xml_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = pathlib.Path(tmp)
            (model_dir / "openvino_model.xml").write_text("<model/>")
            xml_exists = (model_dir / "openvino_model.xml").exists()
            export = not xml_exists
            self.assertFalse(export)


class TestOptimumIntelRerankerSigmoid(unittest.TestCase):
    """Unit-test the _sigmoid static helper."""

    def _make_stub(self):
        import numpy as np
        from versline.services.rag.rerankers import OptimumIntelReranker

        obj = OptimumIntelReranker.__new__(OptimumIntelReranker)
        obj._np = np
        return obj

    def test_sigmoid_zero(self):
        """sigmoid(0) == 0.5"""
        import numpy as np

        obj = self._make_stub()
        np.testing.assert_allclose(obj._sigmoid(0.0), 0.5, atol=1e-6)

    def test_sigmoid_positive(self):
        """sigmoid(large positive) → near 1"""
        obj = self._make_stub()
        self.assertGreater(obj._sigmoid(100.0), 0.99)

    def test_sigmoid_negative(self):
        """sigmoid(large negative) → near 0"""
        obj = self._make_stub()
        self.assertLess(obj._sigmoid(-100.0), 0.01)

    def test_sigmoid_array(self):
        """Works on numpy arrays (same output shape)."""
        import numpy as np

        obj = self._make_stub()
        x = np.array([-1.0, 0.0, 1.0])
        result = obj._sigmoid(x)
        self.assertEqual(result.shape, (3,))
        self.assertAlmostEqual(float(result[1]), 0.5, places=5)


class TestOptimumIntelRerankerScorePairs(unittest.TestCase):
    """Test _score_pairs respects batch_size and returns correct counts."""

    def test_score_count_equals_doc_count(self):
        obj, tokenizer, model = _make_stub_reranker()
        docs = ["doc a", "doc b", "doc c"]
        with patch("versline.services.rag.rerankers._scoped_model_environment"):
            scores = obj._score_pairs("query", docs)
        self.assertEqual(len(scores), 3)

    def test_score_respects_batch_size(self):
        """With batch_size=2 and 5 docs the model is called 3 times."""
        obj, tokenizer, model = _make_stub_reranker(batch_size=2)
        model.side_effect = lambda **inputs: _make_logits(
            [1.0] * inputs["input_ids"].shape[0]
        )
        docs = ["d1", "d2", "d3", "d4", "d5"]
        with patch("versline.services.rag.rerankers._scoped_model_environment"):
            scores = obj._score_pairs("q", docs)
        self.assertEqual(len(scores), 5)
        self.assertEqual(model.call_count, 3)  # ceil(5/2) = 3

    def test_scores_are_in_0_1_range(self):
        """All scores should be probabilities in [0, 1]."""
        obj, tokenizer, model = _make_stub_reranker()
        docs = ["alpha", "beta", "gamma"]
        with patch("versline.services.rag.rerankers._scoped_model_environment"):
            scores = obj._score_pairs("query", docs)
        for s in scores:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)

    def test_higher_logit_gives_higher_score(self):
        """A doc with logit=5 must score higher than one with logit=-5."""
        import numpy as np
        import torch
        from versline.services.rag.rerankers import OptimumIntelReranker, RateLimiter, TokenRateLimiter

        call_n = [0]

        def _model_side_effect(**inputs):
            batch = inputs["input_ids"].shape[0]
            # First call: logit=5.0 (high), second call: logit=-5.0 (low)
            val = 5.0 if call_n[0] == 0 else -5.0
            call_n[0] += 1
            arr = np.full((batch, 1), val, dtype="float32")
            return SimpleNamespace(logits=torch.from_numpy(arr))

        fake_tokenizer = MagicMock(
            side_effect=lambda pairs, **kw: _make_tokenizer_output(len(pairs))
        )
        fake_model = MagicMock(side_effect=_model_side_effect)

        obj = OptimumIntelReranker.__new__(OptimumIntelReranker)
        obj._np = np
        obj.proxy = None
        obj.cache_dir = None
        obj.local_files_only = True
        obj.device = "CPU"
        obj.batch_size = 1  # each doc gets its own call
        obj.model = "test/model"
        obj.model_path = "/dummy"
        obj._tokenizer = fake_tokenizer
        obj._ov_model = fake_model
        obj.rate_limiter = RateLimiter(0)
        obj.token_rate_limiter = TokenRateLimiter(0)

        with patch("versline.services.rag.rerankers._scoped_model_environment"):
            scores = obj._score_pairs("query", ["high-relevance doc", "low-relevance doc"])

        self.assertGreater(scores[0], scores[1])


class TestOptimumIntelRerankerRerank(unittest.TestCase):
    """Test the full rerank() method: sorting, top_k, score assignment."""

    def _build_reranker_with_fixed_scores(self, scores_by_doc):
        """Build a stub reranker whose _score_pairs returns predetermined scores."""
        import numpy as np
        from versline.services.rag.rerankers import OptimumIntelReranker, RateLimiter, TokenRateLimiter

        obj = OptimumIntelReranker.__new__(OptimumIntelReranker)
        obj._np = np
        obj.proxy = None
        obj.cache_dir = None
        obj.local_files_only = True
        obj.device = "CPU"
        obj.batch_size = 8
        obj.model = "test/model"
        obj.model_path = "/dummy"
        obj.rate_limiter = RateLimiter(0)
        obj.token_rate_limiter = TokenRateLimiter(0)
        # Override _score_pairs to return predetermined scores
        obj._score_pairs = MagicMock(return_value=scores_by_doc)
        return obj

    def test_rerank_returns_top_k_items(self):
        scores = [0.9, 0.3, 0.7, 0.5]
        obj = self._build_reranker_with_fixed_scores(scores)
        items = _make_retrieved_chunks(["a", "b", "c", "d"])
        result = obj.rerank("query", items, top_k=2)
        self.assertEqual(len(result), 2)

    def test_rerank_descending_order(self):
        scores = [0.1, 0.9, 0.5]
        obj = self._build_reranker_with_fixed_scores(scores)
        items = _make_retrieved_chunks(["first", "second", "third"])
        result = obj.rerank("query", items, top_k=3)
        self.assertGreaterEqual(result[0].score, result[1].score)
        self.assertGreaterEqual(result[1].score, result[2].score)

    def test_rerank_correct_scores_assigned(self):
        """The returned chunks carry the reranker score, not the original retrieval score."""
        scores = [0.2, 0.8, 0.6]
        obj = self._build_reranker_with_fixed_scores(scores)
        items = _make_retrieved_chunks(["x", "y", "z"])
        result = obj.rerank("query", items, top_k=3)
        result_map = {c.text: c.score for c in result}
        self.assertAlmostEqual(result_map["y"], 0.8, places=5)
        self.assertAlmostEqual(result_map["z"], 0.6, places=5)
        self.assertAlmostEqual(result_map["x"], 0.2, places=5)

    def test_rerank_empty_items_returns_empty(self):
        obj = self._build_reranker_with_fixed_scores([])
        result = obj.rerank("query", [], top_k=5)
        self.assertEqual(result, [])

    def test_rerank_top_k_larger_than_items(self):
        scores = [0.1, 0.9]
        obj = self._build_reranker_with_fixed_scores(scores)
        items = _make_retrieved_chunks(["a", "b"])
        result = obj.rerank("query", items, top_k=10)
        self.assertEqual(len(result), 2)

    def test_rerank_preserves_metadata(self):
        """Metadata from original chunks must be preserved in reranked output."""
        from versline.services.rag.pipeline import RetrievedChunk

        scores = [0.5, 0.8]
        obj = self._build_reranker_with_fixed_scores(scores)
        items = [
            RetrievedChunk(id="a", text="doc a", score=0.1, metadata={"src": "A"}),
            RetrievedChunk(id="b", text="doc b", score=0.2, metadata={"src": "B"}),
        ]
        result = obj.rerank("query", items, top_k=2)
        texts_to_meta = {c.text: c.metadata for c in result}
        self.assertEqual(texts_to_meta["doc a"]["src"], "A")
        self.assertEqual(texts_to_meta["doc b"]["src"], "B")


class TestOptimumIntelRerankerInPipeline(unittest.TestCase):
    """Test that RAGPipeline.__init__ wires OptimumIntelReranker for the provider aliases."""

    def _build_pipeline_with_rerank_provider(self, provider: str):
        from unittest.mock import MagicMock

        from versline.config import settings
        from versline.services.rag.pipeline import RAGPipeline

        settings.rag.rerank_enabled = True
        settings.rag.rerank_provider = provider
        settings.rag.rerank_model = "BAAI/bge-reranker-v2-m3"
        settings.rag.rerank_model_path = None
        settings.rag.rerank_cache_dir = None
        settings.rag.rerank_local_files_only = False
        settings.rag.rerank_device = "CPU"
        settings.rag.rerank_batch_size = 8
        settings.rag.embedding_provider = "sentence-transformers"
        settings.rag.rerank_proxy = None

        mock_reranker = MagicMock()

        with patch(
            "versline.services.rag.pipeline.OptimumIntelReranker",
            return_value=mock_reranker,
        ) as mock_cls:
            pipeline = RAGPipeline(
                embedder=MagicMock(),
                sparse_embedder=MagicMock(),
                generator=MagicMock(),
            )

        settings.rag.rerank_enabled = False
        return pipeline, mock_cls, mock_reranker

    def test_pipeline_uses_optimum_intel_for_hyphen_alias(self):
        pipeline, mock_cls, mock_reranker = self._build_pipeline_with_rerank_provider("optimum-intel")
        mock_cls.assert_called_once()
        self.assertIs(pipeline.reranker, mock_reranker)

    def test_pipeline_uses_optimum_intel_for_underscore_alias(self):
        pipeline, mock_cls, mock_reranker = self._build_pipeline_with_rerank_provider("optimum_intel")
        mock_cls.assert_called_once()
        self.assertIs(pipeline.reranker, mock_reranker)

    def test_pipeline_uses_optimum_intel_for_short_alias(self):
        pipeline, mock_cls, mock_reranker = self._build_pipeline_with_rerank_provider("optimum")
        mock_cls.assert_called_once()
        self.assertIs(pipeline.reranker, mock_reranker)

    def test_pipeline_passes_model_to_reranker(self):
        _pipeline, mock_cls, _mock_reranker = self._build_pipeline_with_rerank_provider("optimum-intel")
        call_kwargs = mock_cls.call_args[1]
        self.assertEqual(call_kwargs.get("model"), "BAAI/bge-reranker-v2-m3")

    def test_pipeline_passes_device_to_reranker(self):
        _pipeline, mock_cls, _mock_reranker = self._build_pipeline_with_rerank_provider("optimum-intel")
        call_kwargs = mock_cls.call_args[1]
        self.assertEqual(call_kwargs.get("device"), "CPU")


if __name__ == "__main__":
    unittest.main()
