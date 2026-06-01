"""多引擎搜索：Tavily / SerpAPI / Brave / DuckDuckGo。

环境变量优先级：
  TAVILY_API_KEY    → 使用 Tavily（推荐，LLM-native，免费 1000/月）
  SERPAPI_API_KEY   → 使用 SerpAPI
  BRAVE_API_KEY     → 使用 Brave Search
  （无）            → 降级到 DuckDuckGo HTML（无需 Key，但噪音大、限流严）

用户可通过 PROFILER_SEARCH_PROVIDER 环境变量强制指定。
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import requests


@dataclass
class SearchResult:
    """单条搜索结果（跨引擎统一格式）。"""

    url: str
    title: str
    snippet: str = ""
    published_date: str = ""
    provider: str = ""
    raw: dict = field(default_factory=dict)


class SearchError(RuntimeError):
    """搜索引擎调用失败。"""


# ── 各引擎实现 ───────────────────────────────────────────────────────────────


def _search_tavily(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    """Tavily AI Search API（推荐）。

    返回结果已按 LLM 相关性排序，包含 snippet 和日期。
    """
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "include_raw_content": False,
            "search_depth": "advanced",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", []):
        results.append(
            SearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("content", ""),
                published_date=item.get("published_date", ""),
                provider="tavily",
                raw=item,
            )
        )
    return results


def _search_serpapi(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    """SerpAPI（Google 搜索代理）。"""
    resp = requests.get(
        "https://serpapi.com/search",
        params={
            "q": query,
            "api_key": api_key,
            "num": max_results,
            "engine": "google",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("organic_results", [])[:max_results]:
        results.append(
            SearchResult(
                url=item.get("link", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                published_date=item.get("date", ""),
                provider="serpapi",
                raw=item,
            )
        )
    return results


def _search_brave(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    """Brave Search API。"""
    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results},
        headers={
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("web", {}).get("results", [])[:max_results]:
        results.append(
            SearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("description", ""),
                published_date=item.get("page_age", ""),
                provider="brave",
                raw=item,
            )
        )
    return results


def _search_duckduckgo(query: str, max_results: int) -> list[SearchResult]:
    """DuckDuckGo 降级方案，优先用 ddgs 包，不可用则报错。

    安装：pip install ddgs
    """
    try:
        from ddgs import DDGS  # noqa: WPS433
    except ImportError:
        raise SearchError(
            "DuckDuckGo 降级模式需要 ddgs 包，请运行：pip install ddgs\n"
            "或设置 TAVILY_API_KEY / SERPAPI_API_KEY / BRAVE_API_KEY 使用官方 API。"
        )

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    SearchResult(
                        url=r.get("href", ""),
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        published_date=r.get("published", ""),
                        provider="duckduckgo",
                        raw=r,
                    )
                )
    except Exception as e:
        raise SearchError(f"DuckDuckGo 搜索失败: {e}")
    return results


# ── 公共入口 ─────────────────────────────────────────────────────────────────


def _select_provider() -> tuple[str, Optional[str]]:
    """按环境变量选择搜索引擎，返回 (provider_name, api_key)。"""
    forced = os.environ.get("PROFILER_SEARCH_PROVIDER", "").strip().lower()
    if forced:
        key_map = {
            "tavily": os.environ.get("TAVILY_API_KEY"),
            "serpapi": os.environ.get("SERPAPI_API_KEY"),
            "brave": os.environ.get("BRAVE_API_KEY"),
            "duckduckgo": None,
        }
        return forced, key_map.get(forced)

    if tavily := os.environ.get("TAVILY_API_KEY"):
        return "tavily", tavily
    if serpapi := os.environ.get("SERPAPI_API_KEY"):
        return "serpapi", serpapi
    if brave := os.environ.get("BRAVE_API_KEY"):
        return "brave", brave
    return "duckduckgo", None


def web_search(query: str, max_results: int = 8) -> list[SearchResult]:
    """统一搜索入口，按环境变量选择引擎。

    Args:
        query: 搜索关键词
        max_results: 返回条数（默认 8）

    Returns:
        SearchResult 列表，按引擎相关性排序

    失败时返回空列表（不抛异常，便于管道继续运行其他源）。
    """
    provider, api_key = _select_provider()

    try:
        if provider == "tavily" and api_key:
            return _search_tavily(query, max_results, api_key)
        if provider == "serpapi" and api_key:
            return _search_serpapi(query, max_results, api_key)
        if provider == "brave" and api_key:
            return _search_brave(query, max_results, api_key)
        return _search_duckduckgo(query, max_results)
    except Exception as e:
        print(f"      [search] {provider} 失败: {e}", file=sys.stderr)
        return []


def multi_query_search(
    queries: list[str],
    max_per_query: int = 5,
    sleep_between: float = 0.3,
) -> list[SearchResult]:
    """对多个查询串执行搜索并合并去重（基于 URL）。"""
    seen_urls: set[str] = set()
    merged: list[SearchResult] = []
    for q in queries:
        results = web_search(q, max_per_query)
        for r in results:
            if not r.url or r.url in seen_urls:
                continue
            seen_urls.add(r.url)
            merged.append(r)
        time.sleep(sleep_between)
    return merged


def build_search_queries(person: str, languages: list[str]) -> list[str]:
    """根据人名生成分层搜索查询串。

    按信号质量排序：A 级（全文稿/长篇访谈）在前。
    """
    queries: list[str] = []
    name = person.strip()
    name_quoted = f'"{name}"'

    if "en" in languages:
        queries.extend(
            [
                f'{name_quoted} podcast transcript full interview',
                f'{name_quoted} interview transcript long-form',
                f'{name_quoted} congressional testimony OR senate hearing',
                f'{name_quoted} essay OR letter OR "open letter"',
                f'{name_quoted} profile The New Yorker OR The Atlantic',
                f'{name_quoted} "in his own words" OR "in her own words"',
            ]
        )

    if "zh" in languages:
        queries.extend(
            [
                f'{name_quoted} 访谈全文 OR 对话实录',
                f'{name_quoted} 演讲全文 OR 深度访谈',
                f'{name_quoted} 内部讲话 OR 公开课 全文',
                f'{name_quoted} 专访 site:latepost.com OR site:36kr.com OR site:huxiu.com',
                f'{name_quoted} 自述 OR 回应',
            ]
        )

    return queries
