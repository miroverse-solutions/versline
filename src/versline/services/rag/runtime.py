from __future__ import annotations

import json
import os
import random
import time
import math
from contextlib import contextmanager
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Deque, Dict, Iterable, Optional, Tuple, TypeVar

from loguru import logger

T = TypeVar("T")

_PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]


@contextmanager
def scoped_proxy(proxy_url: Optional[str]):
    previous = {key: os.environ.get(key) for key in _PROXY_ENV_KEYS}
    try:
        if proxy_url:
            for key in _PROXY_ENV_KEYS:
                os.environ[key] = proxy_url
        else:
            for key in _PROXY_ENV_KEYS:
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class RateLimiter:
    def __init__(self, requests_per_minute: int = 0):
        self.requests_per_minute = max(0, int(requests_per_minute or 0))
        self._lock = Lock()
        self._last_request_ts = 0.0

    def wait(self) -> None:
        if self.requests_per_minute <= 0:
            return

        min_interval = 60.0 / float(self.requests_per_minute)
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_ts
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request_ts = time.monotonic()


class TokenRateLimiter:
    def __init__(self, tokens_per_minute: int = 0):
        self.tokens_per_minute = max(0, int(tokens_per_minute or 0))
        self._lock = Lock()
        self._events: Deque[Tuple[float, int, str]] = deque()
        self._window_total = 0
        self._sequence = 0

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._events and self._events[0][0] <= cutoff:
            _, tokens, _ = self._events.popleft()
            self._window_total -= tokens

    def _new_reservation_id(self) -> str:
        self._sequence += 1
        return f"res_{self._sequence}"

    def reserve(self, tokens: int) -> Optional[str]:
        if self.tokens_per_minute <= 0:
            return None

        requested = max(1, int(tokens or 0))
        requested = min(requested, self.tokens_per_minute)

        while True:
            with self._lock:
                now = time.monotonic()
                self._prune(now)

                if self._window_total + requested <= self.tokens_per_minute:
                    reservation_id = self._new_reservation_id()
                    self._events.append((now, requested, reservation_id))
                    self._window_total += requested
                    return reservation_id

                if not self._events:
                    sleep_for = 0.25
                else:
                    oldest_ts = self._events[0][0]
                    sleep_for = max(0.01, 60.0 - (now - oldest_ts))

            time.sleep(sleep_for)

    def finalize(self, reservation_id: Optional[str], actual_tokens: int, mode: str = "estimate_only") -> None:
        if self.tokens_per_minute <= 0:
            return
        if reservation_id is None:
            return
        if (mode or "estimate_only").lower() != "estimate_and_adjust":
            return

        actual = max(1, int(actual_tokens or 0))
        actual = min(actual, self.tokens_per_minute)

        with self._lock:
            for index, event in enumerate(self._events):
                ts, reserved, event_id = event
                if event_id != reservation_id:
                    continue

                delta = actual - reserved
                if delta == 0:
                    return

                self._events[index] = (ts, actual, event_id)
                self._window_total += delta
                return

    def wait(self, tokens: int) -> None:
        self.reserve(tokens)


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 1
    return max(1, int(math.ceil(len(text) / 4.0)))


def estimate_tokens_from_texts(texts: Iterable[str]) -> int:
    total = 0
    for text in texts:
        total += estimate_tokens_from_text(text)
    return max(1, total)


def retry_call(
    operation: Callable[[], T],
    *,
    max_retries: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    operation_name: str,
) -> T:
    attempts = max(1, int(max_retries))
    base_delay = max(0.0, float(base_delay_seconds))
    max_delay = max(base_delay, float(max_delay_seconds))

    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt >= attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jitter = random.uniform(0, max(0.05, delay * 0.15))
            wait_for = delay + jitter
            logger.warning(
                f"{operation_name} failed (attempt {attempt}/{attempts}): {error}. Retrying in {wait_for:.2f}s"
            )
            time.sleep(wait_for)

    if last_error is None:
        raise RuntimeError(f"{operation_name} failed")
    raise last_error


class ProgressStateStore:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as error:
            logger.warning(f"Failed to load RAG progress state: {error}")
        return {}

    def save(self, state: Dict[str, Any]) -> None:
        self.state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
