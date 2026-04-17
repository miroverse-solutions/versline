import unittest

from versline.services.rag.embedders import _normalize_torch_device


class TestNormalizeTorchDevice(unittest.TestCase):
    def test_cpu_aliases(self):
        self.assertEqual(_normalize_torch_device("CPU"), "cpu")
        self.assertEqual(_normalize_torch_device(" cpu "), "cpu")

    def test_gpu_aliases(self):
        self.assertEqual(_normalize_torch_device("GPU"), "cuda")
        self.assertEqual(_normalize_torch_device("gpu:0"), "cuda:0")
        self.assertEqual(_normalize_torch_device("cuda:1"), "cuda:1")

    def test_empty_and_none(self):
        self.assertIsNone(_normalize_torch_device(None))
        self.assertIsNone(_normalize_torch_device("  "))


if __name__ == "__main__":
    unittest.main()
