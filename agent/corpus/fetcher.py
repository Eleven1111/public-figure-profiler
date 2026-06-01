"""网页正文抽取：优先 trafilatura（全自动），失败时降级到 requests + BS4。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36 public-figure-profiler"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}


@dataclass
class Article:
    """抽取后的文章结构。"""

    url: str
    title: str
    content: str
    author: str = ""
    published_date: str = ""
    site_name: str = ""
    language: str = ""
    extractor: str = ""


def _fetch_html(url: str, timeout: int = 25) -> Optional[str]:
    """带 UA 拉取 HTML，超时/错误返回 None。"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code >= 400:
            return None
        # 尝试尊重 encoding（中文站经常误判）
        if resp.encoding and resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        print(f"      [fetch] HTTP 失败 {url[:60]}: {e}", file=sys.stderr)
        return None


def _extract_with_trafilatura(html: str, url: str) -> Optional[Article]:
    """使用 trafilatura 抽取正文和元数据。"""
    try:
        import trafilatura  # noqa: WPS433
        from trafilatura.metadata import extract_metadata  # noqa: WPS433
    except ImportError:
        return None

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
        url=url,
    )
    if not text or len(text) < 200:
        return None

    try:
        meta = extract_metadata(html)
    except Exception:
        meta = None

    return Article(
        url=url,
        title=(meta.title if meta and meta.title else ""),
        content=text,
        author=(meta.author if meta and meta.author else ""),
        published_date=(meta.date if meta and meta.date else ""),
        site_name=(meta.sitename if meta and meta.sitename else ""),
        language=(meta.language if meta and meta.language else ""),
        extractor="trafilatura",
    )


def _extract_with_bs4(html: str, url: str) -> Optional[Article]:
    """BS4 降级：简单提取 <article> 或最长 <p> 堆。"""
    try:
        from bs4 import BeautifulSoup  # noqa: WPS433
    except ImportError:
        return None

    soup = BeautifulSoup(html, "html.parser")

    for bad in soup(["script", "style", "nav", "footer", "header", "aside"]):
        bad.decompose()

    title_el = soup.find("title")
    title = title_el.get_text(strip=True) if title_el else ""

    article_el = soup.find("article")
    if article_el:
        text = article_el.get_text("\n", strip=True)
    else:
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) > 40)

    if len(text) < 200:
        return None

    return Article(
        url=url,
        title=title,
        content=text,
        extractor="bs4",
    )


def fetch_article(url: str) -> Optional[Article]:
    """主入口：获取 URL 的文章正文。

    流程：trafilatura → BS4 → None
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    html = _fetch_html(url)
    if not html:
        return None

    article = _extract_with_trafilatura(html, url)
    if article:
        return article

    return _extract_with_bs4(html, url)
