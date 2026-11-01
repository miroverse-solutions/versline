"""Chunk-level resume state for long, sequential LLM jobs (translate, summarize)."""
import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

WORK_DIR = Path("work_dir")


class ChunkResume:
    """Persists finished chunk results so an interrupted run continues where it stopped.

    The state file is keyed by a signature of everything that affects the result (source text and
    settings), so a changed input or setting starts fresh instead of reusing stale chunks.
    """

    def __init__(self, command: str, file_path: str, text: str, settings_parts: list, enabled: bool = True):
        self.enabled = enabled
        signature = hashlib.sha1(
            json.dumps([text, settings_parts], ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()[:12]
        source_key = hashlib.sha1(str(Path(file_path).resolve()).encode("utf-8")).hexdigest()[:8]
        stem = Path(file_path).stem
        self.path = WORK_DIR / f"{stem}-{source_key}" / f"{command}_progress_{signature}.json"
        self._results: Dict[str, str] = {}

    def load(self) -> Dict[int, str]:
        if not self.enabled or not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._results = {str(k): v for k, v in data.get("chunks", {}).items()}
        except (OSError, ValueError) as exc:
            logger.warning(f"Ignoring unreadable progress file {self.path}: {exc}")
            self._results = {}
        if self._results:
            logger.info(f"Resuming {self.path.parent.name}: {len(self._results)} chunk(s) already done")
        return {int(k): v for k, v in self._results.items()}

    def save(self, index: int, result: str) -> None:
        if not self.enabled:
            return
        self._results[str(index)] = result
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"chunks": self._results}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning(f"Could not save progress to {self.path}: {exc}")

    def clear(self) -> None:
        self._results = {}
        try:
            self.path.unlink(missing_ok=True)
            self.path.parent.rmdir()
        except OSError:
            pass
