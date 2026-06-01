"""维基百科背景资料抓取。

作用：为人物提供基础背景（出生年、职位、关键事件），定位为 D 级（参考用）。
不依赖外部 SDK，直接调用 MediaWiki Action API。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class WikiSummary:
    title: str
    extract: str
    url: str
    lang: str


WIKI_LANG_MAP = {
    "zh": "zh.wikipedia.org",
    "en": "en.wikipedia.org",
}

_WIKI_HEADERS = {
    "User-Agent": "public-figure-profiler/1.0 (research tool; contact: research@example.com) python-requests",
    "Accept": "application/json",
}


def fetch_wikipedia_summary(person: str, lang: str = "en") -> Optional[WikiSummary]:
    """获取维基百科页面的 extract（纯文本摘要）。"""
    domain = WIKI_LANG_MAP.get(lang, "en.wikipedia.org")
    try:
        # Step 1: 搜索最匹配的条目标题
        search_resp = requests.get(
            f"https://{domain}/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": person,
                "srlimit": 1,
                "utf8": 1,
            },
            headers=_WIKI_HEADERS,
            timeout=20,
        )
        search_resp.raise_for_status()
        hits = search_resp.json().get("query", {}).get("search", [])
        if not hits:
            return None
        title = hits[0]["title"]

        # Step 2: 拉取 extract
        extract_resp = requests.get(
            f"https://{domain}/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exlimit": 1,
                "explaintext": 1,
                "titles": title,
                "utf8": 1,
            },
            headers=_WIKI_HEADERS,
            timeout=20,
        )
        extract_resp.raise_for_status()
        pages = extract_resp.json().get("query", {}).get("pages", {})
        if not pages:
            return None
        page = next(iter(pages.values()))
        extract = page.get("extract", "")
        if len(extract) < 100:
            return None

        return WikiSummary(
            title=title,
            extract=extract,
            url=f"https://{domain}/wiki/{title.replace(' ', '_')}",
            lang=lang,
        )
    except Exception as e:
        print(f"      [wikipedia] {lang} 失败: {e}", file=sys.stderr)
        return None
