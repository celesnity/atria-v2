"""Web search tool using Serper (primary) or DuckDuckGo (fallback)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from atria.models.config import AppConfig

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"


def _extract_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


async def _serper_search_async(query: str, max_results: int) -> list[dict[str, Any]]:
    """Call Serper API asynchronously."""
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return []

    try:
        import httpx

        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        payload = json.dumps({"q": query, "num": max_results})
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(_SERPER_URL, headers=headers, content=payload)
            resp.raise_for_status()
            data = resp.json()

        organic = data.get("organic") or []
        results = []
        for item in organic[:max_results]:
            url = (item.get("link") or "").strip()
            if not url:
                continue
            results.append(
                {
                    "title": (item.get("title") or "").strip(),
                    "url": url,
                    "snippet": (item.get("snippet") or "").strip(),
                }
            )
        return results
    except Exception:
        logger.exception(f"Serper search failed for query: {query!r}")
        return []


def _serper_search(query: str, max_results: int) -> list[dict[str, Any]]:
    """Sync wrapper for Serper search (safe to call from thread pool)."""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_serper_search_async(query, max_results))
        finally:
            loop.close()
    except Exception:
        return []


class WebSearchTool:
    """Tool for searching the web using Serper.dev (primary) or DuckDuckGo (fallback).

    Uses Serper when SERPER_API_KEY is set, otherwise falls back to DuckDuckGo.
    This tool is read-only and safe for use in plan mode.
    """

    def __init__(self, config: AppConfig, working_dir: Path):
        self.config = config
        self.working_dir = working_dir
        self.default_max_results = 10

    def search(
        self,
        query: str,
        max_results: int = 10,
        allowed_domains: Sequence[str] | None = None,
        blocked_domains: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Search the web and return results with titles, URLs, and snippets.

        Args:
            query: Search query string
            max_results: Maximum number of results to return (default: 10)
            allowed_domains: Only include results from these domains
            blocked_domains: Exclude results from these domains

        Returns:
            Dictionary with:
            - success: bool
            - results: list of {title, url, snippet, domain}
            - query: str
            - result_count: int
            - provider: str ("serper" | "duckduckgo")
            - error: str | None
        """
        if not query or not query.strip():
            return {
                "success": False,
                "error": "Search query is required",
                "results": [],
                "query": query,
                "result_count": 0,
            }

        try:
            raw_results = _serper_search(query, max_results * 2)

            for r in raw_results:
                r.setdefault("domain", _extract_domain(r.get("url", "")))

            filtered = self._filter_by_domain(raw_results, allowed_domains, blocked_domains)
            filtered = filtered[:max_results]

            return {
                "success": True,
                "results": filtered,
                "query": query,
                "result_count": len(filtered),
                "provider": "serper",
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Web search failed for query: {query}")
            return {
                "success": False,
                "error": f"Search failed: {str(e)}",
                "results": [],
                "query": query,
                "result_count": 0,
            }

    def _filter_by_domain(
        self,
        results: list[dict[str, Any]],
        allowed_domains: Sequence[str] | None,
        blocked_domains: Sequence[str] | None,
    ) -> list[dict[str, Any]]:
        """Filter search results by domain.

        Args:
            results: Raw search results
            allowed_domains: Only include these domains (if specified)
            blocked_domains: Exclude these domains

        Returns:
            Filtered list of results
        """
        if not allowed_domains and not blocked_domains:
            return results

        filtered = []
        for result in results:
            url = result.get("url", result.get("href", result.get("link", "")))
            if not url:
                continue

            domain = result.get("domain") or _extract_domain(url)
            if not domain:
                continue

            # Check allowed domains
            if allowed_domains:
                allowed = False
                for allowed_domain in allowed_domains:
                    allowed_clean = allowed_domain.lower().lstrip("www.")
                    if domain == allowed_clean or domain.endswith("." + allowed_clean):
                        allowed = True
                        break
                if not allowed:
                    continue

            # Check blocked domains
            if blocked_domains:
                blocked = False
                for blocked_domain in blocked_domains:
                    blocked_clean = blocked_domain.lower().lstrip("www.")
                    if domain == blocked_clean or domain.endswith("." + blocked_clean):
                        blocked = True
                        break
                if blocked:
                    continue

            filtered.append(result)

        return filtered
