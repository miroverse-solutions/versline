"""Tests for versline.core.resources and ResourceSettings."""
import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch


class TestApplyResourceLimitsNoOp(unittest.TestCase):
    """When all limits are 0 / 0.0 nothing should be called."""

    def test_all_zero_values_are_no_ops(self):
        from versline.core.resources import apply_resource_limits

        with (
            patch("versline.core.resources._apply_ram_limit") as ram,
            patch("versline.core.resources._apply_cpu_limit") as cpu,
            patch("versline.core.resources._apply_gpu_limit") as gpu,
        ):
            apply_resource_limits(max_ram_mb=0, max_cpu_cores=0, max_gpu_vram_fraction=0.0)
            ram.assert_called_once_with(0)
            cpu.assert_called_once_with(0)
            gpu.assert_called_once_with(0.0)

    def test_positive_values_forwarded(self):
        from versline.core.resources import apply_resource_limits

        with (
            patch("versline.core.resources._apply_ram_limit") as ram,
            patch("versline.core.resources._apply_cpu_limit") as cpu,
            patch("versline.core.resources._apply_gpu_limit") as gpu,
        ):
            apply_resource_limits(max_ram_mb=2048, max_cpu_cores=4, max_gpu_vram_fraction=0.8)
            ram.assert_called_once_with(2048)
            cpu.assert_called_once_with(4)
            gpu.assert_called_once_with(0.8)


class TestApplyCpuLimit(unittest.TestCase):
    def test_zero_skips_affinity(self):
        from versline.core.resources import _apply_cpu_limit

        with patch("os.sched_setaffinity") as mock_aff:
            _apply_cpu_limit(0)
            mock_aff.assert_not_called()

    def test_negative_skips_affinity(self):
        from versline.core.resources import _apply_cpu_limit

        with patch("os.sched_setaffinity") as mock_aff:
            _apply_cpu_limit(-1)
            mock_aff.assert_not_called()

    def test_sets_affinity_to_requested_cores(self):
        from versline.core.resources import _apply_cpu_limit

        with (
            patch("os.cpu_count", return_value=8),
            patch("os.sched_setaffinity") as mock_aff,
        ):
            _apply_cpu_limit(4)
            mock_aff.assert_called_once_with(0, {0, 1, 2, 3})

    def test_clamps_to_available_cores(self):
        """Requesting more cores than available should silently clamp."""
        from versline.core.resources import _apply_cpu_limit

        with (
            patch("os.cpu_count", return_value=2),
            patch("os.sched_setaffinity") as mock_aff,
        ):
            _apply_cpu_limit(16)
            mock_aff.assert_called_once_with(0, {0, 1})

    def test_handles_missing_sched_setaffinity(self):
        """On platforms without sched_setaffinity (e.g. macOS) it should not raise."""
        from versline.core.resources import _apply_cpu_limit

        with patch.object(os, "sched_setaffinity", None, create=True):
            # Should not raise; AttributeError is caught internally.
            try:
                _apply_cpu_limit(2)
            except AttributeError:
                self.fail("_apply_cpu_limit raised AttributeError unexpectedly")

    def test_handles_permission_error(self):
        from versline.core.resources import _apply_cpu_limit

        with (
            patch("os.cpu_count", return_value=4),
            patch("os.sched_setaffinity", side_effect=PermissionError),
        ):
            # Must not propagate
            _apply_cpu_limit(2)


class TestApplyRamLimit(unittest.TestCase):
    def test_zero_skips_setrlimit(self):
        from versline.core.resources import _apply_ram_limit

        with patch.dict("sys.modules", {"resource": MagicMock()}):
            import resource as _r  # noqa: F401 (needed to prime the mock)
            with patch("sys.platform", "linux"):
                _r.setrlimit = MagicMock()
                _apply_ram_limit(0)
                _r.setrlimit.assert_not_called()

    @unittest.skipUnless(sys.platform == "linux", "RLIMIT_AS only available on Linux")
    def test_sets_rlimit_as_on_linux(self):
        from versline.core.resources import _apply_ram_limit

        mock_resource = MagicMock()
        mock_resource.RLIMIT_AS = 9  # the real value on Linux

        with patch.dict("sys.modules", {"resource": mock_resource}):
            with patch("sys.platform", "linux"):
                _apply_ram_limit(512)
                expected_bytes = 512 * 1024 * 1024
                mock_resource.setrlimit.assert_called_once_with(
                    mock_resource.RLIMIT_AS,
                    (expected_bytes, expected_bytes),
                )

    def test_non_linux_platform_skips(self):
        from versline.core.resources import _apply_ram_limit

        with patch("sys.platform", "darwin"):
            mock_resource = MagicMock()
            with patch.dict("sys.modules", {"resource": mock_resource}):
                _apply_ram_limit(1024)
                mock_resource.setrlimit.assert_not_called()

    @unittest.skipUnless(sys.platform == "linux", "Only applies on Linux")
    def test_exception_does_not_propagate(self):
        from versline.core.resources import _apply_ram_limit

        mock_resource = MagicMock()
        mock_resource.RLIMIT_AS = 9
        mock_resource.setrlimit.side_effect = ValueError("test error")

        with patch.dict("sys.modules", {"resource": mock_resource}):
            with patch("sys.platform", "linux"):
                _apply_ram_limit(512)  # should not raise


class TestApplyGpuLimit(unittest.TestCase):
    def test_zero_skips_torch(self):
        from versline.core.resources import _apply_gpu_limit

        with patch.dict("sys.modules", {"torch": None}):
            # No import-time error should occur; limit simply not applied
            _apply_gpu_limit(0.0)

    def test_negative_skips_torch(self):
        from versline.core.resources import _apply_gpu_limit

        with patch.dict("sys.modules", {"torch": None}):
            _apply_gpu_limit(-0.5)

    def test_torch_import_error_is_silent(self):
        """If torch is not installed the function should silently do nothing."""
        from versline.core.resources import _apply_gpu_limit

        with patch.dict("sys.modules", {"torch": None}):
            _apply_gpu_limit(0.8)

    def test_no_cuda_devices_skips(self):
        from versline.core.resources import _apply_gpu_limit

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            _apply_gpu_limit(0.8)
            mock_torch.cuda.set_per_process_memory_fraction.assert_not_called()

    def test_sets_fraction_on_all_devices(self):
        from versline.core.resources import _apply_gpu_limit

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 2
        with patch.dict("sys.modules", {"torch": mock_torch}):
            _apply_gpu_limit(0.7)
            mock_torch.cuda.set_per_process_memory_fraction.assert_has_calls(
                [call(0.7, device=0), call(0.7, device=1)]
            )

    def test_fraction_clamped_above_one(self):
        from versline.core.resources import _apply_gpu_limit

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        with patch.dict("sys.modules", {"torch": mock_torch}):
            _apply_gpu_limit(2.5)  # should be clamped to 1.0
            mock_torch.cuda.set_per_process_memory_fraction.assert_called_once_with(
                1.0, device=0
            )

    def test_fraction_clamped_to_minimum(self):
        from versline.core.resources import _apply_gpu_limit

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        with patch.dict("sys.modules", {"torch": mock_torch}):
            _apply_gpu_limit(0.001)  # below minimum 0.01, should be clamped to 0.01
            mock_torch.cuda.set_per_process_memory_fraction.assert_called_once_with(
                0.01, device=0
            )

    def test_exception_does_not_propagate(self):
        from versline.core.resources import _apply_gpu_limit

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.cuda.set_per_process_memory_fraction.side_effect = RuntimeError("gpu error")
        with patch.dict("sys.modules", {"torch": mock_torch}):
            _apply_gpu_limit(0.8)  # must not raise


class TestResourceSettings(unittest.TestCase):
    def tearDown(self):
        for key in [
            "VERSLINE_RESOURCE_MAX_RAM_MB",
            "VERSLINE_RESOURCE_MAX_CPU_CORES",
            "VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION",
        ]:
            os.environ.pop(key, None)

    def test_defaults_are_zero(self):
        from versline.config import ResourceSettings

        s = ResourceSettings()
        self.assertEqual(s.max_ram_mb, 0)
        self.assertEqual(s.max_cpu_cores, 0)
        self.assertAlmostEqual(s.max_gpu_vram_fraction, 0.0)

    def test_reads_from_env_vars(self):
        from versline.config import ResourceSettings

        os.environ["VERSLINE_RESOURCE_MAX_RAM_MB"] = "4096"
        os.environ["VERSLINE_RESOURCE_MAX_CPU_CORES"] = "4"
        os.environ["VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION"] = "0.75"

        s = ResourceSettings()
        self.assertEqual(s.max_ram_mb, 4096)
        self.assertEqual(s.max_cpu_cores, 4)
        self.assertAlmostEqual(s.max_gpu_vram_fraction, 0.75)

    def test_settings_includes_resource(self):
        from versline.config import Settings

        s = Settings()
        self.assertTrue(hasattr(s, "resource"))
        self.assertIsNotNone(s.resource)


if __name__ == "__main__":
    unittest.main()
