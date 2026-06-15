"""All search tools for the acquisition agent.

Web search uses Tavily (with DuckDuckGo fallback).
Platform tools use Tavily with site: filters.
"""
from __future__ import annotations

import os
import sys

import requests


def _tavily_search(
    query: str,
    num_results: int,
    topic: str | None = None,
    time_range: str | None = None,
) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set")
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": num_results,
        "include_raw_content": True,
        "search_depth": "advanced",
    }
    # 时效性检索：topic=news 让 Tavily 按时间排序，time_range 限定窗口
    if topic:
        payload["topic"] = topic
    if time_range:
        payload["time_range"] = time_range
    resp = requests.post(
        "https://api.tavily.com/search",
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    results = []
    for r in resp.json().get("results", []):
        results.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "content": r.get("raw_content") or r.get("content", ""),
            "published_date": r.get("published_date", ""),
        })
    return results


def _ddg_search(query: str, num_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError(
            "DuckDuckGo fallback requires the ddgs package. "
            "Run `pip install -r requirements.txt` or set TAVILY_API_KEY."
        ) from exc

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append({
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "content": r.get("body", ""),
                    "published_date": "",
                })
    except Exception as exc:
        print(f"[search] DDG failed: {exc}", file=sys.stderr)
    return results


def _search(
    query: str,
    num_results: int,
    topic: str | None = None,
    time_range: str | None = None,
) -> list[dict]:
    """Try Tavily first; fall back to DuckDuckGo; return [] on all failures."""
    try:
        return _tavily_search(query, num_results, topic=topic, time_range=time_range)
    except Exception as exc:
        print(f"[search] Tavily failed ({exc}), falling back to DDG", file=sys.stderr)
    try:
        return _ddg_search(query, num_results)
    except Exception as exc:
        print(f"[search] DDG also failed ({exc})", file=sys.stderr)
    return []


def search_web(query: str, num_results: int = 5) -> list[dict]:
    """General web search."""
    return _search(query, num_results)


def search_recent(query: str, num_results: int = 5, time_range: str = "month") -> list[dict]:
    """时效性检索：抓取最新动态（官方公告、新发布、近期新闻）。

    使用 Tavily topic=news + time_range 窗口，结果按时间而非相关性排序。
    time_range ∈ {day, week, month, year}。
    """
    return _search(query, num_results, topic="news", time_range=time_range)


def fetch_content(url: str) -> str:
    """Fetch and extract article text from a URL."""
    try:
        from trafilatura import fetch_url, extract
        raw = fetch_url(url)
        return extract(raw) or ""
    except Exception as exc:
        print(f"[fetch] Failed {url}: {exc}", file=sys.stderr)
        return ""


def search_weibo(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:weibo.com {query}", max_results)


def search_zhihu(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:zhihu.com {query}", max_results)


def search_bilibili(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:bilibili.com {query}", max_results)


def search_twitter(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:twitter.com OR site:x.com {query}", max_results)


def search_xiaohongshu(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"小红书 {query}", max_results)
