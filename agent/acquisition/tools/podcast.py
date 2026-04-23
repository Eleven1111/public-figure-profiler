"""Podcast search via Podcast Index API with Tavily fallback."""
from __future__ import annotations

import hashlib
import os
import sys
import time

import requests


def search_podcast(query: str, max_results: int = 5) -> list[dict]:
    """Search for podcast episodes mentioning the target person.

    Uses Podcast Index API if keys are set; otherwise falls back to Tavily.
    """
    api_key = os.environ.get("PODCAST_INDEX_KEY")
    api_secret = os.environ.get("PODCAST_INDEX_SECRET")

    if api_key and api_secret:
        try:
            return _podcast_index_search(query, max_results, api_key, api_secret)
        except Exception as exc:
            print(f"[podcast] Podcast Index failed ({exc}), falling back to Tavily", file=sys.stderr)

    # Fallback: Tavily/DDG web search for podcast episodes
    from .search import _search
    results = _search(f"podcast episode interview {query}", max_results)
    return [
        {
            "url": r["url"],
            "title": r["title"],
            "description": r["content"][:600],
            "audio_url": "",
            "published_date": r.get("published_date", ""),
        }
        for r in results
    ]


def _podcast_index_search(
    query: str, num: int, api_key: str, api_secret: str
) -> list[dict]:
    ts = int(time.time())
    auth_hash = hashlib.sha1(
        f"{api_key}{api_secret}{ts}".encode()
    ).hexdigest()

    resp = requests.get(
        "https://api.podcastindex.org/api/1.0/search/byterm",
        params={"q": query, "max": num, "fulltext": True},
        headers={
            "X-Auth-Date": str(ts),
            "X-Auth-Key": api_key,
            "Authorization": auth_hash,
            "User-Agent": "PublicFigureProfiler/2.0",
        },
        timeout=15,
    )
    resp.raise_for_status()
    feeds = resp.json().get("feeds", [])
    return [
        {
            "url": ep.get("link", ""),
            "title": ep.get("title", ""),
            "description": (ep.get("description", "") or "")[:600],
            "audio_url": ep.get("url", ""),
            "published_date": "",
        }
        for ep in feeds[:num]
    ]
