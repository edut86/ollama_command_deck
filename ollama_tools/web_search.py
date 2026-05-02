"""Configurable web search helpers."""

from __future__ import annotations

import json
import os
from html import unescape
from html.parser import HTMLParser
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchConfigError(RuntimeError):
    pass


def search_web(query: str, count: int = 5) -> list[SearchResult]:
    if not query.strip():
        raise ValueError("Search query is empty.")
    if os.environ.get("SEARXNG_URL"):
        return _search_searxng(query, count)
    if os.environ.get("BRAVE_SEARCH_API_KEY"):
        return _search_brave(query, count)
    if os.environ.get("DISABLE_DUCKDUCKGO_FALLBACK", "").lower() in {"1", "true", "yes"}:
        raise SearchConfigError("Set SEARXNG_URL or BRAVE_SEARCH_API_KEY to enable internet search.")
    if _is_news_query(query):
        news_results = _search_google_news_rss(query, count)
        if news_results:
            return news_results
    return _search_duckduckgo_html(query, count)


def _search_searxng(query: str, count: int) -> list[SearchResult]:
    base = os.environ["SEARXNG_URL"].rstrip("/")
    params = urllib.parse.urlencode({"q": query, "format": "json"})
    with urllib.request.urlopen(f"{base}/search?{params}", timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    results = []
    for item in data.get("results", [])[:count]:
        results.append(SearchResult(item.get("title", ""), item.get("url", ""), item.get("content", "")))
    return results


def _search_brave(query: str, count: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query, "count": count})
    request = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"],
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    results = []
    for item in data.get("web", {}).get("results", [])[:count]:
        results.append(SearchResult(item.get("title", ""), item.get("url", ""), item.get("description", "")))
    return results


def _is_news_query(query: str) -> bool:
    lowered = query.lower()
    return any(word in lowered for word in ("news", "headline", "headlines", "breaking", "today"))


def _search_google_news_rss(query: str, count: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    request = urllib.request.Request(
        f"https://news.google.com/rss/search?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()

    root = ET.fromstring(data)
    results: list[SearchResult] = []
    for item in root.findall("./channel/item")[:count]:
        title = item.findtext("title", default="").strip()
        url = item.findtext("link", default="").strip()
        source = item.findtext("source", default="").strip()
        published = item.findtext("pubDate", default="").strip()
        parts = []
        if source:
            parts.append(f"Source: {source}")
        if published:
            parts.append(f"Published: {published}")
        if title and url:
            results.append(SearchResult(title=title, url=url, snippet="; ".join(parts)))
    return results


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._current_url = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._pending_snippet_index: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = set(attrs_dict.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            self._current_url = _clean_duckduckgo_url(attrs_dict.get("href", ""))
            self._current_title = []
            self._current_snippet = []
            self._pending_snippet_index = None
        elif "result__snippet" in classes and self.results:
            self._in_snippet = True
            self._pending_snippet_index = len(self.results) - 1
            self._current_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            title = unescape("".join(self._current_title)).strip()
            if title and self._current_url:
                self.results.append(SearchResult(title=title, url=self._current_url, snippet=""))
            self._in_title = False
            self._current_url = ""
            self._current_title = []
        elif self._in_snippet and tag in {"a", "div"}:
            snippet = unescape("".join(self._current_snippet)).strip()
            if snippet and self._pending_snippet_index is not None:
                current = self.results[self._pending_snippet_index]
                self.results[self._pending_snippet_index] = SearchResult(current.title, current.url, snippet)
            self._in_snippet = False
            self._pending_snippet_index = None
            self._current_snippet = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)


def _clean_duckduckgo_url(raw_url: str) -> str:
    url = unescape(raw_url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return url


def _search_duckduckgo_html(query: str, count: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
    request = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="ignore")
    parser = _DuckDuckGoHTMLParser()
    parser.feed(html)
    return parser.results[:count]
