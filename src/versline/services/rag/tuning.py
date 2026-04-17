from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


_REMOTE_EMBED_PROVIDERS = {"openai", "openrouter", "avalai", "openaicompatible"}
_LOCAL_EMBED_PROVIDERS = {
    "fastembed",
    "flagembedding",
    "optimum-intel",
    "optimum_intel",
    "optimum",
    "openvino",
    "sentence-transformers",
    "sentence_transformers",
    "sentencetransformers",
    "sentence-transformer",
    "sentence",
}

_WATCHDOG_ONLY_FALSE_VALUES = {"0", "false", "no", "off"}
_WATCHDOG_ONLY_TRUE_VALUES = {"1", "true", "yes", "on"}
_OPENVINO_LIKE_PROVIDERS = {"optimum-intel", "optimum_intel", "optimum", "openvino"}


@dataclass(frozen=True)
class IngestTuningDecision:
    embedding_device: Optional[str]
    embedding_batch_size: Optional[int]
    ingestion_batch_size: Optional[int]
    profile: str


def _read_linux_available_ram_mb() -> Optional[int]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return max(1, int(parts[1]) // 1024)
    except Exception:
        return None
    return None


def _effective_ram_mb(*, max_ram_mb: int) -> Optional[int]:
    configured_limit = int(max_ram_mb or 0)
    available_ram = _read_linux_available_ram_mb()

    if configured_limit > 0 and available_ram is not None:
        return min(configured_limit, available_ram)
    if configured_limit > 0:
        return configured_limit
    return available_ram


def _cap_or_default(value: Optional[int], *, default: int, cap: int) -> int:
    if value is None:
        return default
    return min(max(1, int(value)), cap)


def _is_watchdog_only_mode() -> bool:
    raw = str(os.getenv("VERSLINE_RESOURCE_USE_CGROUP_HARD_LIMIT", "1")).strip().lower()
    if raw in _WATCHDOG_ONLY_FALSE_VALUES:
        return True
    if raw in _WATCHDOG_ONLY_TRUE_VALUES:
        return False
    return False


def _is_gpu_device(value: Optional[str]) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized.startswith("gpu")


def tune_ingest_settings(
    *,
    auto_tune: bool,
    low_memory: bool,
    embedding_provider: str,
    embedding_device: Optional[str],
    embedding_device_explicit: bool = False,
    embedding_batch_size: Optional[int],
    ingestion_batch_size: Optional[int],
    max_ram_mb: int,
) -> IngestTuningDecision:
    if not auto_tune and not low_memory:
        return IngestTuningDecision(
            embedding_device=embedding_device,
            embedding_batch_size=embedding_batch_size,
            ingestion_batch_size=ingestion_batch_size,
            profile="manual",
        )

    provider = (embedding_provider or "openai").strip().lower()
    ram_mb = _effective_ram_mb(max_ram_mb=max_ram_mb)
    is_local_provider = provider in _LOCAL_EMBED_PROVIDERS
    is_remote_provider = provider in _REMOTE_EMBED_PROVIDERS
    is_openvino_like_provider = provider in _OPENVINO_LIKE_PROVIDERS
    watchdog_only_mode = _is_watchdog_only_mode()

    if low_memory:
        return IngestTuningDecision(
            embedding_device=embedding_device or "cpu",
            embedding_batch_size=_cap_or_default(embedding_batch_size, default=1, cap=2),
            ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=4, cap=8),
            profile="low-memory",
        )

    if not is_local_provider:
        profile = "remote-default"
        if not is_remote_provider:
            profile = "provider-unknown"
        return IngestTuningDecision(
            embedding_device=embedding_device,
            embedding_batch_size=embedding_batch_size,
            ingestion_batch_size=ingestion_batch_size,
            profile=profile,
        )

    if ram_mb is None:
        return IngestTuningDecision(
            embedding_device=embedding_device,
            embedding_batch_size=_cap_or_default(embedding_batch_size, default=4, cap=8),
            ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=12, cap=24),
            profile="local-conservative",
        )

    if ram_mb <= 4096:
        return IngestTuningDecision(
            embedding_device=embedding_device or "cpu",
            embedding_batch_size=_cap_or_default(embedding_batch_size, default=1, cap=1),
            ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=2, cap=4),
            profile="local-tiny-ram",
        )

    if ram_mb <= 8192:
        return IngestTuningDecision(
            embedding_device=embedding_device or "cpu",
            embedding_batch_size=_cap_or_default(embedding_batch_size, default=2, cap=2),
            ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=6, cap=8),
            profile="local-low-ram",
        )

    if ram_mb <= 16384:
        preferred_device = embedding_device
        if preferred_device is None and is_openvino_like_provider:
            preferred_device = "cpu"
        elif (
            watchdog_only_mode
            and is_openvino_like_provider
            and not embedding_device_explicit
            and _is_gpu_device(preferred_device)
        ):
            # With watchdog-only enforcement and tight RAM caps, iGPU paths can
            # consume host RAM aggressively. Prefer CPU unless user explicitly
            # requested a GPU device on the CLI.
            preferred_device = "cpu"

        if watchdog_only_mode and is_openvino_like_provider:
            return IngestTuningDecision(
                embedding_device=preferred_device,
                embedding_batch_size=_cap_or_default(embedding_batch_size, default=2, cap=2),
                ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=8, cap=8),
                profile="local-watchdog-conservative",
            )

        return IngestTuningDecision(
            embedding_device=preferred_device,
            embedding_batch_size=_cap_or_default(embedding_batch_size, default=4, cap=4),
            ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=12, cap=16),
            profile="local-balanced-ram",
        )

    return IngestTuningDecision(
        embedding_device=embedding_device,
        embedding_batch_size=_cap_or_default(embedding_batch_size, default=8, cap=12),
        ingestion_batch_size=_cap_or_default(ingestion_batch_size, default=24, cap=32),
        profile="local-high-ram",
    )
