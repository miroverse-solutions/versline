from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import httpx

from versline.config import settings
from versline.services.rag.base import BaseWebSearcher, WebSearchResult
from versline.services.rag.runtime import RateLimiter, retry_call, scoped_proxy


class WebSearchRegistry:
    def __init__(self):
        self._factories: Dict[str, Callable[..., BaseWebSearcher]] = {}

    def register(self, provider: str, factory: Callable[..., BaseWebSearcher]) -> None:
        key = provider.strip().lower()
        if not key:
            raise ValueError("Web search provider key must be non-empty")
        self._factories[key] = factory

    def create(self, provider: str, **kwargs) -> BaseWebSearcher:
        key = provider.strip().lower()
        if key not in self._factories:
            raise KeyError(f"Web search provider '{provider}' is not registered")
        return self._factories[key](**kwargs)


class DuckDuckGoWebSearcher(BaseWebSearcher):
    def __init__(
        self,
        endpoint: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.endpoint = endpoint or "https://api.duckduckgo.com/"
        self.proxy = proxy
        self.timeout_seconds = int(timeout_seconds or 15)
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_web_search_rpm)

    def _extract_related_topics(self, payload: Dict[str, Any]) -> List[WebSearchResult]:
        items: List[WebSearchResult] = []

        def _push(topic: Dict[str, Any], rank: int) -> None:
            text = str(topic.get("Text", "") or "").strip()
            url = str(topic.get("FirstURL", "") or "").strip()
            if not text or not url:
                return
            items.append(
                WebSearchResult(
                    title=text.split(" - ")[0].strip(),
                    url=url,
                    snippet=text,
                    score=max(0.0, 1.0 - (rank * 0.05)),
                    metadata={"provider": "duckduckgo"},
                )
            )

        rank = 0
        for topic in payload.get("RelatedTopics", []) or []:
            if isinstance(topic, dict) and isinstance(topic.get("Topics"), list):
                for nested in topic.get("Topics") or []:
                    rank += 1
                    if isinstance(nested, dict):
                        _push(nested, rank)
            elif isinstance(topic, dict):
                rank += 1
                _push(topic, rank)

        return items

    def search(self, query: str, top_k: int = 5, **kwargs) -> List[WebSearchResult]:
        if not query.strip():
            return []

        self.rate_limiter.wait()

        def operation() -> List[WebSearchResult]:
            with scoped_proxy(self.proxy):
                with (httpx.Client(proxy=self.proxy) if self.proxy else httpx.Client()) as client:
                    response = client.get(
                        self.endpoint,
                        params={
                            "q": query,
                            "format": "json",
                            "no_redirect": 1,
                            "no_html": 1,
                            "skip_disambig": 0,
                        },
                        timeout=self.timeout_seconds,
                    )
            response.raise_for_status()
            payload = response.json()

            results: List[WebSearchResult] = []
            abstract_text = str(payload.get("AbstractText", "") or "").strip()
            abstract_url = str(payload.get("AbstractURL", "") or "").strip()
            heading = str(payload.get("Heading", "") or "").strip()
            if abstract_text and abstract_url:
                results.append(
                    WebSearchResult(
                        title=heading or abstract_text[:80],
                        url=abstract_url,
                        snippet=abstract_text,
                        score=1.0,
                        metadata={"provider": "duckduckgo"},
                    )
                )

            results.extend(self._extract_related_topics(payload))
            return results[: max(1, int(top_k or 1))]

        return retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="web_search_request",
        )


class TavilyWebSearcher(BaseWebSearcher):
    def __init__(
        self,
        api_key: str,
        endpoint: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key
        self.endpoint = endpoint or "https://api.tavily.com/search"
        self.proxy = proxy
        self.timeout_seconds = int(timeout_seconds or 15)
        self.rate_limiter = rate_limiter or RateLimiter(settings.rag.rate_limit_web_search_rpm)

    def search(self, query: str, top_k: int = 5, **kwargs) -> List[WebSearchResult]:
        if not query.strip():
            return []

        self.rate_limiter.wait()

        def operation() -> List[WebSearchResult]:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max(1, int(top_k or 1)),
            }
            with scoped_proxy(self.proxy):
                with (httpx.Client(proxy=self.proxy) if self.proxy else httpx.Client()) as client:
                    response = client.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()

            results: List[WebSearchResult] = []
            for index, item in enumerate(data.get("results", []) or []):
                if not isinstance(item, dict):
                    continue
                results.append(
                    WebSearchResult(
                        title=str(item.get("title", "") or "").strip(),
                        url=str(item.get("url", "") or "").strip(),
                        snippet=str(item.get("content", "") or "").strip(),
                        score=float(item.get("score", 1.0 - (index * 0.05)) or 0.0),
                        metadata={"provider": "tavily"},
                    )
                )
            return results

        return retry_call(
            operation,
            max_retries=settings.rag.retry_max_retries,
            base_delay_seconds=settings.rag.retry_base_delay_seconds,
            max_delay_seconds=settings.rag.retry_max_delay_seconds,
            operation_name="web_search_request",
        )


def build_default_web_search_registry() -> WebSearchRegistry:
    registry = WebSearchRegistry()
    registry.register("duckduckgo", lambda **kwargs: DuckDuckGoWebSearcher(**kwargs))
    registry.register("tavily", lambda **kwargs: TavilyWebSearcher(**kwargs))
    return registry
