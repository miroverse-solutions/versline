import atexit
import os
import pathlib
import signal
import sys
import threading
import time
from loguru import logger


def apply_resource_limits(
    max_ram_mb: int = 0,
    max_cpu_cores: int = 0,
    max_gpu_vram_fraction: float = 0.0,
) -> None:
    """Apply OS-level resource limits to the current process.

    Args:
        max_ram_mb: Maximum physical RAM in MB. 0 = unlimited.
            Creates an isolated cgroup v2 child scope for this process and sets
            memory.max there (kernel-enforced, fires synchronously on allocation).
            Falls back to an RSS watchdog thread if cgroup delegation is unavailable.
        max_cpu_cores: Maximum CPU cores to use via affinity. 0 = unlimited.
        max_gpu_vram_fraction: Max fraction of GPU VRAM per device (0.0–1.0). 0.0 = unlimited.
    """
    _apply_ram_limit(max_ram_mb)
    _apply_cpu_limit(max_cpu_cores)
    _apply_gpu_limit(max_gpu_vram_fraction)


# ---------------------------------------------------------------------------
# RAM helpers
# ---------------------------------------------------------------------------

def _read_cgroup_path() -> "pathlib.Path | None":
    """Return the resolved cgroup v2 directory for the current process, or None."""
    try:
        with open("/proc/self/cgroup") as f:
            for line in f:
                line = line.strip()
                if line.startswith("0::"):
                    rel = line[3:].lstrip("/")
                    cgroup_dir = pathlib.Path("/sys/fs/cgroup") / rel
                    if cgroup_dir.is_dir():
                        return cgroup_dir
    except Exception:
        pass
    return None


def _cleanup_cgroup(cgroup_path: pathlib.Path) -> None:
    """Remove the versline-owned cgroup on process exit (best-effort)."""
    try:
        cgroup_path.rmdir()
    except OSError:
        pass


def _try_create_isolated_cgroup(limit_bytes: int) -> bool:
    """Create an isolated child cgroup for this process and set memory.max.

    The current process's cgroup is often shared with the parent application
    (e.g. VS Code / Chromium). Writing memory.max there would kill unrelated
    processes when the limit is hit.  Instead we:

    1. Walk up from the current cgroup to find a parent where we can mkdir.
    2. Create ``versline-<pid>`` as a sibling/child of the current scope.
    3. Enable the memory controller in that parent's subtree_control.
    4. Move this process into the new, isolated cgroup.
    5. Write memory.max on the new cgroup (only versline is affected).
    6. Register an atexit handler to rmdir the cgroup after exit.
    """
    current = _read_cgroup_path()
    if current is None:
        logger.debug("[resource] cgroup v2 path not found; cgroup limit skipped.")
        return False

    root = pathlib.Path("/sys/fs/cgroup")
    root_str = str(root)
    pid_str = str(os.getpid())
    new_name = f"versline-{os.getpid()}"

    # Start from parent of current leaf scope and walk toward root.
    # We avoid pathlib comparison operators (<, >) because they can fail in
    # edge-case environments; use string prefix check instead.
    parent = current.parent
    for _depth in range(15):
        try:
            parent_str = str(parent)
        except Exception:
            break
        if not parent_str.startswith(root_str):
            break

        new_scope = parent / new_name
        # 1. Try to mkdir the new scope.
        try:
            new_scope.mkdir(exist_ok=True)
        except (PermissionError, OSError):
            try:
                next_p = parent.parent
            except Exception:
                break
            if next_p == parent:
                break
            parent = next_p
            continue

        # 2. Best-effort: enable memory controller in the parent's subtree.
        try:
            (parent / "cgroup.subtree_control").write_text("+memory")
        except (PermissionError, OSError, FileNotFoundError):
            pass  # may already be enabled, or not needed

        # 3. Move this PID into the new cgroup.
        try:
            (new_scope / "cgroup.procs").write_text(pid_str)
        except (PermissionError, OSError) as exc:
            logger.debug(f"[resource] cgroup move failed at {new_scope}: {exc}")
            try:
                new_scope.rmdir()
            except OSError:
                pass
            try:
                next_p = parent.parent
            except Exception:
                break
            if next_p == parent:
                break
            parent = next_p
            continue

        # 4. Set memory limit on the isolated cgroup.
        try:
            (new_scope / "memory.max").write_text(str(limit_bytes))
        except (PermissionError, OSError) as exc:
            logger.debug(f"[resource] memory.max write failed on {new_scope}: {exc}")
            return False

        atexit.register(_cleanup_cgroup, new_scope)
        logger.info(
            f"[resource] Isolated cgroup: {new_scope},"
            f" memory.max={limit_bytes // (1024 * 1024)} MB"
        )
        return True

    logger.debug("[resource] Could not create an isolated cgroup; falling back to watchdog.")
    return False


def _get_rss_mb() -> int:
    """Return the process Resident Set Size (physical RAM) in MB via /proc/self/status."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def _parse_soft_trigger_ratio_from_env(default_ratio: float = 0.85) -> float:
    raw = str(os.getenv("VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT", "")).strip()
    if not raw:
        return default_ratio
    try:
        pct = float(raw)
    except ValueError:
        logger.warning(
            "[resource] Invalid VERSLINE_RESOURCE_RAM_SOFT_TRIGGER_PCT; "
            f"expected numeric percent, got {raw!r}. Falling back to {default_ratio * 100:.1f}%."
        )
        return default_ratio

    # Keep a sensible safety envelope while allowing advanced users
    # to move the trigger close to hard limit when needed.
    pct = max(50.0, min(100.0, pct))
    return pct / 100.0


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _rss_watchdog(limit_mb: int, soft_trigger_ratio: float = 0.85, interval_seconds: float = 0.5) -> None:
    """Daemon thread: sends SIGTERM when RSS reaches soft_trigger_ratio *limit_mb*.

    Triggering below 100 % gives the process time to shut down cleanly before the
    kernel's OOM killer picks it (or a sibling process) as a victim.
    """
    ratio = max(0.5, min(1.0, float(soft_trigger_ratio)))
    soft_limit_mb = max(1, int(limit_mb * ratio))
    while True:
        try:
            rss_mb = _get_rss_mb()
            if rss_mb >= soft_limit_mb:
                logger.error(
                    f"[resource] RSS {rss_mb} MB >= soft limit {soft_limit_mb} MB"
                    f" (hard cap {limit_mb} MB) — sending SIGTERM to prevent OOM."
                )
                os.kill(os.getpid(), signal.SIGTERM)
                return
        except Exception:
            pass
        time.sleep(interval_seconds)


def _apply_ram_limit(max_ram_mb: int) -> None:
    if max_ram_mb <= 0:
        return
    if sys.platform != "linux":
        logger.warning("[resource] RAM limit is only supported on Linux; skipping.")
        return

    limit_bytes = max_ram_mb * 1024 * 1024

    raw_cgroup_toggle = str(os.getenv("VERSLINE_RESOURCE_USE_CGROUP_HARD_LIMIT", "1")).strip().lower()
    use_cgroup_hard_limit = raw_cgroup_toggle not in {"0", "false", "no", "off"}
    soft_trigger_ratio = _parse_soft_trigger_ratio_from_env(default_ratio=0.85)
    soft_trigger_pct = int(round(soft_trigger_ratio * 100))

    # Prefer kernel-enforced cgroup v2 limit in an isolated scope so that
    # only the versline process is affected when the limit is hit.
    cgroup_ok = _try_create_isolated_cgroup(limit_bytes) if use_cgroup_hard_limit else False

    # When cgroup hard limit is active, the kernel already enforces memory.max
    # synchronously on allocation. Keep watchdog disabled by default in this
    # mode to avoid premature SIGTERM during short-lived model init spikes.
    run_watchdog_with_cgroup = _parse_bool_env(
        "VERSLINE_RESOURCE_RUN_WATCHDOG_WITH_CGROUP",
        default=False,
    )
    should_run_watchdog = (not cgroup_ok) or run_watchdog_with_cgroup

    if should_run_watchdog:
        t = threading.Thread(
            target=_rss_watchdog,
            args=(max_ram_mb, soft_trigger_ratio),
            daemon=True,
            name="versline-ram-watchdog",
        )
        t.start()
        if cgroup_ok:
            logger.info(
                f"[resource] RAM watchdog started alongside cgroup: hard cap={max_ram_mb} MB,"
                f" soft SIGTERM at {soft_trigger_pct}%, cgroup SIGKILL at 100%"
            )
        elif use_cgroup_hard_limit:
            logger.info(
                f"[resource] RAM watchdog started: hard cap={max_ram_mb} MB,"
                f" soft trigger={soft_trigger_pct}%, polling every 0.5 s"
            )
        else:
            logger.info(
                f"[resource] RAM watchdog started in watchdog-only mode: hard cap={max_ram_mb} MB,"
                f" soft trigger={soft_trigger_pct}%, polling every 0.5 s"
            )
    elif cgroup_ok:
        logger.info(
            f"[resource] cgroup hard limit active without watchdog: hard cap={max_ram_mb} MB"
        )


def _apply_cpu_limit(max_cpu_cores: int) -> None:
    if max_cpu_cores <= 0:
        return
    try:
        available = os.cpu_count() or 1
        cores = min(max_cpu_cores, available)
        os.sched_setaffinity(0, set(range(cores)))
        logger.info(f"[resource] CPU affinity limited to {cores} core(s) (of {available} available)")
    except AttributeError:
        logger.warning("[resource] os.sched_setaffinity is not available on this platform; CPU core limit skipped.")
    except PermissionError:
        logger.warning("[resource] Permission denied when setting CPU affinity; CPU core limit skipped.")
    except Exception as exc:
        logger.warning(f"[resource] Failed to set CPU affinity: {exc}")


def _apply_gpu_limit(max_gpu_vram_fraction: float) -> None:
    if max_gpu_vram_fraction <= 0.0:
        return
    fraction = min(1.0, max(0.01, max_gpu_vram_fraction))
    try:
        import torch  # noqa: PLC0415

        if not torch.cuda.is_available():
            logger.debug("[resource] No CUDA devices found; GPU VRAM limit skipped.")
            return
        for device_index in range(torch.cuda.device_count()):
            torch.cuda.set_per_process_memory_fraction(fraction, device=device_index)
        logger.info(
            f"[resource] GPU VRAM limit set to {fraction * 100:.0f}% per device "
            f"({torch.cuda.device_count()} device(s))"
        )
    except ImportError:
        logger.debug("[resource] PyTorch not installed; GPU VRAM limit skipped.")
    except Exception as exc:
        logger.warning(f"[resource] Failed to set GPU VRAM limit: {exc}")
