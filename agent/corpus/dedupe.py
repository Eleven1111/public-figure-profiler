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


def mark_syndication(
    sources: list[dict],
    jaccard_threshold: float = 0.45,
) -> list[dict]:
    """同源传播检测：转载/编译/同一采访的多平台分发归入同一 independent_id。

    与 dedupe_sources 不同，本函数不删除任何来源，只写回两个字段：
      independent_id — 独立来源组编号（如 I01）；同组来源在充分性判定中只算 1 个
      syndication_of — 若为转载，指向组内第一个出现的 source_id；原创为空

    阈值低于去重阈值（0.45 vs 0.75）：转载常有删改、编译、加按语，
    相似度达不到"重复"标准但仍是同一信息源。
    """
    counter = 0
    groups: list[tuple[set[str], str, str]] = []  # (shingles, independent_id, first_sid)
    for s in sources:
        content = s.get("content", "")
        current = _shingles(content) if content and len(content) >= 500 else set()

        matched = None
        if current:
            for existing, ind_id, first_sid in groups:
                if _jaccard(current, existing) >= jaccard_threshold:
                    matched = (ind_id, first_sid)
                    break

        if matched:
            s["independent_id"] = matched[0]
            s["syndication_of"] = matched[1]
        else:
            counter += 1
            ind_id = f"I{counter:02d}"
            s["independent_id"] = ind_id
            s["syndication_of"] = ""
            if current:
                groups.append((current, ind_id, s.get("source_id", "")))
            else:
                groups.append((set(), ind_id, s.get("source_id", "")))
    return sources


def independent_ab_count(sources: list[dict]) -> int:
    """独立 A/B 级来源数：同一 independent_id 组内只取最高等级计 1 次。"""
    best: dict[str, str] = {}
    for s in sources:
        ind = s.get("independent_id") or s.get("source_id", "")
        grade = s.get("grade", "D")
        if ind not in best or "ABCD".index(grade) < "ABCD".index(best[ind]):
            best[ind] = grade
    return sum(1 for g in best.values() if g in ("A", "B"))


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
