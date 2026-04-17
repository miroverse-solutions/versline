"""Tests for versline.core.resources and ResourceSettings."""
import os
import pathlib
import signal
import sys
import threading
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


class TestCreateIsolatedCgroup(unittest.TestCase):
    """Tests for _try_create_isolated_cgroup — the isolated child cgroup approach."""

    def _make_parent_mock(self, path_str: str):
        """Return a MagicMock whose str() returns *path_str*."""
        m = MagicMock(spec=pathlib.Path)
        m.__str__ = MagicMock(return_value=path_str)
        return m

    def test_returns_false_when_no_cgroup_path(self):
        from versline.core.resources import _try_create_isolated_cgroup

        with patch("versline.core.resources._read_cgroup_path", return_value=None):
            self.assertFalse(_try_create_isolated_cgroup(4 * 1024 ** 3))

    def test_creates_child_cgroup_moves_pid_sets_memory_max(self):
        from versline.core.resources import _try_create_isolated_cgroup

        parent_str = "/sys/fs/cgroup/user.slice"
        parent = self._make_parent_mock(parent_str)
        parent.parent.__str__ = MagicMock(return_value="/sys/fs/cgroup")

        current = MagicMock(spec=pathlib.Path)
        current.parent = parent

        new_scope = MagicMock(spec=pathlib.Path)
        new_scope_procs = MagicMock(spec=pathlib.Path)
        new_scope_mem = MagicMock(spec=pathlib.Path)

        def scope_div(key):
            return {
                "cgroup.procs": new_scope_procs,
                "memory.max": new_scope_mem,
                "cgroup.subtree_control": MagicMock(spec=pathlib.Path),
            }.get(key, MagicMock(spec=pathlib.Path))

        new_scope.__truediv__ = lambda s, key: scope_div(key)
        parent.__truediv__ = lambda s, key: new_scope

        with (
            patch("versline.core.resources._read_cgroup_path", return_value=current),
            patch("atexit.register"),
        ):
            result = _try_create_isolated_cgroup(4 * 1024 * 1024 * 1024)

        new_scope.mkdir.assert_called()
        new_scope_procs.write_text.assert_called_with(str(os.getpid()))
        new_scope_mem.write_text.assert_called_with(str(4 * 1024 ** 3))
        self.assertTrue(result)

    def test_returns_false_when_mkdir_always_fails(self):
        from versline.core.resources import _try_create_isolated_cgroup

        parent = self._make_parent_mock("/sys/fs/cgroup/user.slice")
        # Parent's parent is outside /sys/fs/cgroup → loop stops
        outer = self._make_parent_mock("/sys/fs")
        outer.parent = outer
        parent.parent = outer

        new_scope = MagicMock(spec=pathlib.Path)
        new_scope.mkdir.side_effect = PermissionError
        parent.__truediv__ = lambda s, key: new_scope

        current = MagicMock(spec=pathlib.Path)
        current.parent = parent

        with patch("versline.core.resources._read_cgroup_path", return_value=current):
            result = _try_create_isolated_cgroup(4 * 1024 ** 3)

        self.assertFalse(result)

    def test_returns_false_when_proc_move_fails(self):
        from versline.core.resources import _try_create_isolated_cgroup

        parent = self._make_parent_mock("/sys/fs/cgroup/user.slice")
        outer = self._make_parent_mock("/sys/fs")
        outer.parent = outer
        parent.parent = outer

        new_scope = MagicMock(spec=pathlib.Path)
        new_scope_procs = MagicMock(spec=pathlib.Path)
        new_scope_procs.write_text.side_effect = PermissionError

        def scope_div(key):
            return {
                "cgroup.procs": new_scope_procs,
                "cgroup.subtree_control": MagicMock(spec=pathlib.Path),
            }.get(key, MagicMock(spec=pathlib.Path))

        new_scope.__truediv__ = lambda s, key: scope_div(key)
        parent.__truediv__ = lambda s, key: new_scope
        current = MagicMock(spec=pathlib.Path)
        current.parent = parent

        with patch("versline.core.resources._read_cgroup_path", return_value=current):
            result = _try_create_isolated_cgroup(4 * 1024 ** 3)

        self.assertFalse(result)

    def test_returns_false_when_memory_max_write_fails(self):
        from versline.core.resources import _try_create_isolated_cgroup

        parent = self._make_parent_mock("/sys/fs/cgroup/user.slice")
        outer = self._make_parent_mock("/sys/fs")
        outer.parent = outer
        parent.parent = outer

        new_scope = MagicMock(spec=pathlib.Path)
        new_scope_procs = MagicMock(spec=pathlib.Path)
        new_scope_mem = MagicMock(spec=pathlib.Path)
        new_scope_mem.write_text.side_effect = PermissionError

        def scope_div(key):
            return {
                "cgroup.procs": new_scope_procs,
                "memory.max": new_scope_mem,
                "cgroup.subtree_control": MagicMock(spec=pathlib.Path),
            }.get(key, MagicMock(spec=pathlib.Path))

        new_scope.__truediv__ = lambda s, key: scope_div(key)
        parent.__truediv__ = lambda s, key: new_scope
        current = MagicMock(spec=pathlib.Path)
        current.parent = parent

        with patch("versline.core.resources._read_cgroup_path", return_value=current):
            result = _try_create_isolated_cgroup(4 * 1024 ** 3)

        self.assertFalse(result)


class TestApplyRamLimit(unittest.TestCase):
    def test_zero_does_nothing(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("versline.core.resources._try_create_isolated_cgroup") as mock_cgroup,
            patch("threading.Thread") as mock_thread,
        ):
            _apply_ram_limit(0)
            mock_cgroup.assert_not_called()
            mock_thread.assert_not_called()

    def test_negative_does_nothing(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("versline.core.resources._try_create_isolated_cgroup") as mock_cgroup,
            patch("threading.Thread") as mock_thread,
        ):
            _apply_ram_limit(-1)
            mock_cgroup.assert_not_called()
            mock_thread.assert_not_called()

    def test_non_linux_skips(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "darwin"),
            patch("versline.core.resources._try_create_isolated_cgroup") as mock_cgroup,
            patch("threading.Thread") as mock_thread,
        ):
            _apply_ram_limit(4096)
            mock_cgroup.assert_not_called()
            mock_thread.assert_not_called()

    def test_uses_isolated_cgroup_when_available(self):
        """When cgroup succeeds, watchdog is disabled by default."""
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "linux"),
            patch("versline.core.resources._try_create_isolated_cgroup", return_value=True) as mock_cgroup,
            patch("threading.Thread") as mock_thread,
        ):
            _apply_ram_limit(4096)
            mock_cgroup.assert_called_once_with(4096 * 1024 * 1024)
            mock_thread.assert_not_called()

    def test_watchdog_can_run_alongside_cgroup_when_enabled(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "linux"),
            patch.dict("os.environ", {"VERSLINE_RESOURCE_RUN_WATCHDOG_WITH_CGROUP": "1"}, clear=False),
            patch("versline.core.resources._try_create_isolated_cgroup", return_value=True) as mock_cgroup,
            patch("threading.Thread") as mock_thread,
        ):
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            _apply_ram_limit(4096)
            mock_cgroup.assert_called_once_with(4096 * 1024 * 1024)
            mock_thread.assert_called_once()
            mock_t.start.assert_called_once()

    def test_falls_back_to_watchdog_when_cgroup_unavailable(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "linux"),
            patch("versline.core.resources._try_create_isolated_cgroup", return_value=False),
            patch("threading.Thread") as mock_thread,
        ):
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            _apply_ram_limit(4096)
            mock_thread.assert_called_once()
            call_kwargs = mock_thread.call_args[1]
            self.assertTrue(call_kwargs.get("daemon"))
            self.assertEqual(call_kwargs.get("name"), "versline-ram-watchdog")
            mock_t.start.assert_called_once()

    def test_watchdog_only_mode_skips_cgroup(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "linux"),
            patch.dict("os.environ", {"VERSLINE_RESOURCE_USE_CGROUP_HARD_LIMIT": "0"}),
            patch("versline.core.resources._try_create_isolated_cgroup") as mock_cgroup,
            patch("threading.Thread") as mock_thread,
        ):
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            _apply_ram_limit(4096)
            mock_cgroup.assert_not_called()
            mock_thread.assert_called_once()
            mock_t.start.assert_called_once()

    def test_custom_soft_trigger_percent_is_used(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "linux"),
            patch.dict("os.environ", {"VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT": "95"}, clear=False),
            patch("versline.core.resources._try_create_isolated_cgroup", return_value=False),
            patch("threading.Thread") as mock_thread,
        ):
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            _apply_ram_limit(4096)
            self.assertTrue(mock_thread.called)
            args = mock_thread.call_args[1].get("args")
            self.assertIsNotNone(args)
            self.assertEqual(args[0], 4096)
            self.assertAlmostEqual(args[1], 0.95)
            mock_t.start.assert_called_once()

    def test_invalid_soft_trigger_percent_falls_back_to_default(self):
        from versline.core.resources import _apply_ram_limit

        with (
            patch("sys.platform", "linux"),
            patch.dict("os.environ", {"VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT": "not-a-number"}, clear=False),
            patch("versline.core.resources._try_create_isolated_cgroup", return_value=False),
            patch("threading.Thread") as mock_thread,
        ):
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            _apply_ram_limit(4096)
            self.assertTrue(mock_thread.called)
            args = mock_thread.call_args[1].get("args")
            self.assertIsNotNone(args)
            self.assertEqual(args[0], 4096)
            self.assertAlmostEqual(args[1], 0.85)
            mock_t.start.assert_called_once()


class TestGetRssMb(unittest.TestCase):
    def test_parses_vmrss_from_proc_status(self):
        from versline.core.resources import _get_rss_mb

        fake_status = "VmPeak:\t  123456 kB\nVmRSS:\t   65536 kB\nVmData:\t   12345 kB\n"
        with patch("builtins.open", unittest.mock.mock_open(read_data=fake_status)):
            result = _get_rss_mb()
        self.assertEqual(result, 64)  # 65536 kB // 1024 = 64 MB

    def test_returns_zero_on_error(self):
        from versline.core.resources import _get_rss_mb

        with patch("builtins.open", side_effect=OSError("no proc")):
            result = _get_rss_mb()
        self.assertEqual(result, 0)

    def test_returns_zero_when_vmrss_missing(self):
        from versline.core.resources import _get_rss_mb

        fake_status = "VmPeak:\t  123456 kB\nVmData:\t   12345 kB\n"
        with patch("builtins.open", unittest.mock.mock_open(read_data=fake_status)):
            result = _get_rss_mb()
        self.assertEqual(result, 0)


class TestRssWatchdog(unittest.TestCase):
    def test_sends_sigterm_at_soft_limit(self):
        """Watchdog fires at 85% of the hard cap, not only at 100%."""
        from versline.core.resources import _rss_watchdog

        # 3500 MB > 85% of 4000 MB (3400), so SIGTERM should fire.
        with (
            patch("versline.core.resources._get_rss_mb", return_value=3500),
            patch("os.kill") as mock_kill,
            patch("time.sleep", side_effect=StopIteration),
        ):
            try:
                _rss_watchdog(limit_mb=4000, interval_seconds=0)
            except StopIteration:
                pass
            mock_kill.assert_called_with(os.getpid(), signal.SIGTERM)

    def test_no_sigterm_when_rss_under_soft_limit(self):
        from versline.core.resources import _rss_watchdog

        call_count = [0]

        def fake_sleep(_):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise StopIteration

        # 1000 MB < 85% of 4096 MB (3481), so no SIGTERM.
        with (
            patch("versline.core.resources._get_rss_mb", return_value=1000),
            patch("os.kill") as mock_kill,
            patch("time.sleep", side_effect=fake_sleep),
        ):
            try:
                _rss_watchdog(limit_mb=4096, interval_seconds=0)
            except StopIteration:
                pass
            mock_kill.assert_not_called()

    def test_internal_exception_does_not_exit_loop(self):
        """An exception inside the loop body must be swallowed without crashing."""
        from versline.core.resources import _rss_watchdog

        call_count = [0]

        def exploding_sleep(_):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise StopIteration

        with (
            patch("versline.core.resources._get_rss_mb", side_effect=RuntimeError("oops")),
            patch("os.kill") as mock_kill,
            patch("time.sleep", side_effect=exploding_sleep),
        ):
            try:
                _rss_watchdog(limit_mb=4096, interval_seconds=0)
            except StopIteration:
                pass
            mock_kill.assert_not_called()


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
    _RESOURCE_KEYS = [
        "VERSLINE_RESOURCE_MAX_RAM_MB",
        "VERSLINE_RESOURCE_MAX_CPU_CORES",
        "VERSLINE_RESOURCE_MAX_GPU_VRAM_FRACTION",
    ]

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in self._RESOURCE_KEYS}

    def tearDown(self):
        for k in self._RESOURCE_KEYS:
            os.environ.pop(k, None)
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_defaults_are_zero(self):
        from versline.config import ResourceSettings

        s = ResourceSettings(_env_file=None)
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
