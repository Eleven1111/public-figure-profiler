"""语料去重：URL 规范化 + 内容哈希 + 近似相似度。"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse


def canonical_url(url: str) -> str:
    """URL 规范化：去除 fragment、tracking 参数，统一 scheme。"""
    if not url:
        return ""
    try:
        p = urlparse(url.strip().lower())
    except Exception:
        return url

    path = p.path.rstrip("/")
    scheme = "https" if p.scheme in ("http", "https") else p.scheme
    netloc = p.netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]

    query_parts = []
    for pair in p.query.split("&"):
        if not pair:
            continue
        key = pair.split("=", 1)[0]
        if key.startswith("utm_") or key in {"ref", "source", "fbclid", "gclid"}:
            continue
        query_parts.append(pair)
    query = "&".join(query_parts)

    return urlunparse((scheme, netloc, path, "", query, ""))


def content_hash(text: str, prefix_chars: int = 2000) -> str:
    """对文章前 N 个字符做 SHA-1（整篇文章哈希开销大，前缀足够判重复）。"""
    normalized = re.sub(r"\s+", " ", text.strip())[:prefix_chars]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _shingles(text: str, k: int = 7) -> set[str]:
    """生成字符 k-gram 集合（用于 Jaccard 相似度）。"""
    normalized = re.sub(r"\s+", "", text)[:3000]
    if len(normalized) < k:
        return {normalized}
    return {normalized[i : i + k] for i in range(len(normalized) - k + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union) if union else 0.0


def dedupe_sources(
    sources: list[dict],
    jaccard_threshold: float = 0.75,
) -> list[dict]:
    """多阶段去重。

    阶段：
      1. 基于 canonical URL 去重
      2. 基于 content hash（前 2000 字 SHA1）去重
      3. 基于 Jaccard 相似度（>0.75 视为重复）合并
    """
    if not sources:
        return []

    stage1: list[dict] = []
    seen_urls: set[str] = set()
    for s in sources:
        url = canonical_url(s.get("source", "") or s.get("url", ""))
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        stage1.append(s)

    stage2: list[dict] = []
    seen_hashes: set[str] = set()
    for s in stage1:
        content = s.get("content", "")
        if not content:
            stage2.append(s)
            continue
        h = content_hash(content)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        stage2.append(s)

    stage3: list[dict] = []
    shingle_cache: list[tuple[set[str], dict]] = []
    for s in stage2:
        content = s.get("content", "")
        if not content or len(content) < 500:
            stage3.append(s)
            continue
        current = _shingles(content)

        duplicate = False
        for existing, _ in shingle_cache:
            if _jaccard(current, existing) >= jaccard_threshold:
                duplicate = True
                break
        if duplicate:
            continue
        shingle_cache.append((current, s))
        stage3.append(s)

    return stage3
