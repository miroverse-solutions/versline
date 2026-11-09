"""SHA-256 hashing (checkable with ``sha256sum`` or PowerShell ``Get-FileHash``)."""
from __future__ import annotations

import hashlib
from typing import Callable, Optional

from versline.services.organize.normalize import fs_path

PARTIAL_BYTES = 64 * 1024
CHUNK_BYTES = 1024 * 1024


def partial_hash(path, size: int) -> str:
    """SHA-256 of the size plus the first and last 64 KB. Only used to rule out non-duplicates cheaply."""
    digest = hashlib.sha256(str(size).encode("ascii") + b"|")
    with open(fs_path(path), "rb") as handle:
        digest.update(handle.read(PARTIAL_BYTES))
        if size > PARTIAL_BYTES:
            handle.seek(max(PARTIAL_BYTES, size - PARTIAL_BYTES))
            digest.update(handle.read(PARTIAL_BYTES))
    return digest.hexdigest()


def full_hash(path, on_bytes: Optional[Callable[[int], None]] = None) -> str:
    digest = hashlib.sha256()
    with open(fs_path(path), "rb") as handle:
        while True:
            block = handle.read(CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
            if on_bytes:
                on_bytes(len(block))
    return digest.hexdigest()
