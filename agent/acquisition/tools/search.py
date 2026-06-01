"""All search tools for the acquisition agent.

Web search uses Tavily (with DuckDuckGo fallback).
Platform tools use Tavily with site: filters.
"""
from __future__ import annotations

import os
import sys

import requests


def _tavily_search(query: str, num_results: int) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": num_results,
            "include_raw_content": True,
            "search_depth": "advanced",
        },
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


def _search(query: str, num_results: int) -> list[dict]:
    """Try Tavily first; fall back to DuckDuckGo; return [] on all failures."""
    try:
        return _tavily_search(query, num_results)
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
