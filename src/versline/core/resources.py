import os
import sys
from loguru import logger


def apply_resource_limits(
    max_ram_mb: int = 0,
    max_cpu_cores: int = 0,
    max_gpu_vram_fraction: float = 0.0,
) -> None:
    """Apply OS-level resource limits to the current process.

    Args:
        max_ram_mb: Maximum virtual memory in MB. 0 = unlimited.
        max_cpu_cores: Maximum CPU cores to use via affinity. 0 = unlimited.
        max_gpu_vram_fraction: Max fraction of GPU VRAM per device (0.0–1.0). 0.0 = unlimited.
    """
    _apply_ram_limit(max_ram_mb)
    _apply_cpu_limit(max_cpu_cores)
    _apply_gpu_limit(max_gpu_vram_fraction)


def _apply_ram_limit(max_ram_mb: int) -> None:
    if max_ram_mb <= 0:
        return
    if sys.platform != "linux":
        logger.warning("RAM limiting via RLIMIT_AS is only supported on Linux; skipping.")
        return
    try:
        import resource  # noqa: PLC0415 (stdlib, Linux only)

        limit_bytes = max_ram_mb * 1024 * 1024
        # Soft and hard limit both set to the requested value.
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        logger.info(f"[resource] RAM (virtual address space) limit set to {max_ram_mb} MB")
    except Exception as exc:
        logger.warning(f"[resource] Failed to set RAM limit: {exc}")


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
