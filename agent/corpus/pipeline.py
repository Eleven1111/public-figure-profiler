"""语料采集管道编排器。

流程：
  1. 加载用户提供的本地语料（标 A 级）
  2. 生成搜索查询 → 多引擎搜索
  3. 抓取每条 URL 的正文（trafilatura）
  4. YouTube 视频字幕 / 维基百科背景
  5. 去重
  6. 评级
  7. 筛选与截断（max_sources、grade_filter）
  8. 分配 source_id（S01, S02, ...）
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .dedupe import dedupe_sources
from .fetcher import fetch_article
from .grader import grade_all
from .search import build_search_queries, multi_query_search
from .wikipedia import fetch_wikipedia_summary
from .youtube import fetch_youtube_transcript


@dataclass
class CorpusPipelineConfig:
    """管道配置。"""

    person: str
    languages: list[str] = field(default_factory=lambda: ["en", "zh"])
    max_sources: int = 20
    max_per_query: int = 5
    enable_web_search: bool = True
    enable_wikipedia: bool = True
    user_corpus_paths: list[str] = field(default_factory=list)
    youtube_urls: list[str] = field(default_factory=list)
    min_content_chars: int = 400  # 低于此字数的页面丢弃（垃圾/404/trapped）


def _load_user_corpus(paths: list[str]) -> list[dict]:
    """加载用户提供的本地语料文件，默认 A 级。"""
    sources = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            print(f"      [user] 文件不存在: {path}", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8")
        sources.append(
            {
                "grade": "A",
                "source": str(p),
                "url": "",
                "title": p.name,
                "content": text,
                "word_count": len(text.split()),
                "origin": "user_file",
                "published_date": "",
            }
        )
    return sources


def _collect_from_web(config: CorpusPipelineConfig) -> list[dict]:
    """执行搜索 + 抓取，返回 source 列表。"""
    if not config.enable_web_search:
        return []

    queries = build_search_queries(config.person, config.languages)
    print(f"      [search] 构造 {len(queries)} 条查询...", file=sys.stderr)

    results = multi_query_search(queries, max_per_query=config.max_per_query)
    print(f"      [search] 获得 {len(results)} 条候选 URL", file=sys.stderr)

    sources: list[dict] = []
    for idx, r in enumerate(results):
        if len(sources) >= config.max_sources * 2:
            break  # 预留一倍冗余给后续去重/评级过滤
        print(f"      [fetch] {idx + 1}/{len(results)} {r.url[:80]}", file=sys.stderr)
        article = fetch_article(r.url)
        if not article or len(article.content) < config.min_content_chars:
            continue
        sources.append(
            {
                "grade": "",  # 稍后评级
                "source": article.url,
                "url": article.url,
                "title": article.title or r.title,
                "content": article.content,
                "word_count": len(article.content.split()),
                "origin": "web_search",
                "published_date": article.published_date or r.published_date,
                "author": article.author,
                "site_name": article.site_name,
                "language": article.language,
                "extractor": article.extractor,
                "search_snippet": r.snippet,
                "search_provider": r.provider,
            }
        )
    return sources


def _collect_from_youtube(urls: list[str]) -> list[dict]:
    """抓取 YouTube 字幕。"""
    sources = []
    for url in urls:
        transcript = fetch_youtube_transcript(url)
        if not transcript:
            print(f"      [youtube] 跳过 {url[:60]}", file=sys.stderr)
            continue
        sources.append(
            {
                "grade": "",  # 稍后评级（会按长度分 A/B/C）
                "source": url,
                "url": url,
                "title": f"YouTube transcript: {url}",
                "content": transcript,
                "word_count": len(transcript.split()),
                "origin": "youtube",
                "published_date": "",
            }
        )
    return sources


def _collect_from_wikipedia(person: str, languages: list[str]) -> list[dict]:
    """抓取维基百科背景（D 级参考）。"""
    sources = []
    for lang in languages:
        wiki = fetch_wikipedia_summary(person, lang=lang)
        if not wiki:
            continue
        sources.append(
            {
                "grade": "D",  # 维基百科固定 D 级
                "source": wiki.url,
                "url": wiki.url,
                "title": wiki.title,
                "content": wiki.extract,
                "word_count": len(wiki.extract.split()),
                "origin": "wikipedia",
                "published_date": "",
                "language": lang,
            }
        )
    return sources


def _assign_source_ids(sources: list[dict]) -> None:
    """按 A→B→C→D 排序后分配 S01, S02, ... 编号（in-place）。"""
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    sources.sort(key=lambda s: (grade_order.get(s.get("grade", "D"), 4), -s.get("word_count", 0)))
    for idx, s in enumerate(sources, start=1):
        s["source_id"] = f"S{idx:02d}"


def _filter_relevant(sources: list[dict], person: str) -> list[dict]:
    """过滤掉内容中不包含目标人物姓名的文章。

    用于剔除 Tavily/搜索引擎返回的通用内容（如「访谈技巧」教程等）。
    用户上传的语料（origin=user_file）和维基百科（origin=wikipedia）不过滤。
    """
    # 生成姓名变体：全名 + 各字 token（中文姓名按字拆；英文按 token 拆）
    name_variants: list[str] = [person.strip().lower()]
    # 中文姓名：取前两字/后两字作为子串
    if len(person) >= 2:
        name_variants.append(person[:2].lower())
        name_variants.append(person[-2:].lower())
    # 英文姓名：取各 token
    for tok in person.split():
        if len(tok) > 1:
            name_variants.append(tok.lower())

    def _is_relevant(s: dict) -> bool:
        # 用户文件和维基百科直接保留
        if s.get("origin") in ("user_file", "wikipedia"):
            return True
        haystack = (
            (s.get("title") or "") + " " + (s.get("content") or "")
        ).lower()
        return any(v in haystack for v in name_variants)

    kept = [s for s in sources if _is_relevant(s)]
    dropped = len(sources) - len(kept)
    if dropped:
        print(f"[corpus] 相关性过滤: 剔除 {dropped} 篇无关文章", file=sys.stderr)
    return kept


def _truncate_to_budget(sources: list[dict], max_sources: int) -> list[dict]:
    """按等级优先级保留前 N 个（A 优先，然后 B/C/D）。"""
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    sorted_sources = sorted(
        sources,
        key=lambda s: (grade_order.get(s.get("grade", "D"), 4), -s.get("word_count", 0)),
    )
    return sorted_sources[:max_sources]


def build_corpus(config: CorpusPipelineConfig) -> list[dict]:
    """构建完整语料清单。

    Returns:
        list[dict] — 每个 dict 包含：
          source_id, grade, source (URL or path), title, content, word_count,
          origin, published_date, ...
    """
    all_sources: list[dict] = []

    print("[corpus] 加载用户语料...", file=sys.stderr)
    user_sources = _load_user_corpus(config.user_corpus_paths)
    all_sources.extend(user_sources)
    print(f"         用户语料 {len(user_sources)} 篇", file=sys.stderr)

    if config.youtube_urls:
        print(f"[corpus] 抓取 YouTube 字幕 ({len(config.youtube_urls)} 条)...", file=sys.stderr)
        yt = _collect_from_youtube(config.youtube_urls)
        all_sources.extend(yt)
        print(f"         YouTube 成功 {len(yt)} 条", file=sys.stderr)

    if config.enable_web_search:
        print("[corpus] 工程化搜索 + 抓取...", file=sys.stderr)
        web = _collect_from_web(config)
        all_sources.extend(web)
        print(f"         Web 抓取 {len(web)} 条", file=sys.stderr)

    if config.enable_wikipedia:
        print("[corpus] 维基百科背景...", file=sys.stderr)
        wiki = _collect_from_wikipedia(config.person, config.languages)
        all_sources.extend(wiki)
        print(f"         Wiki {len(wiki)} 条", file=sys.stderr)

    print(f"[corpus] 原始总数: {len(all_sources)}", file=sys.stderr)

    # 去重
    all_sources = dedupe_sources(all_sources)
    print(f"[corpus] 去重后: {len(all_sources)}", file=sys.stderr)

    # 相关性过滤（剔除不含目标人物姓名的文章）
    all_sources = _filter_relevant(all_sources, config.person)

    # 评级（未评级的才评级，已有 grade 的跳过）
    all_sources = grade_all(all_sources)

    # 截断到预算
    all_sources = _truncate_to_budget(all_sources, config.max_sources)

    # 分配 source_id
    _assign_source_ids(all_sources)

    grade_counts = {g: 0 for g in ("A", "B", "C", "D")}
    for s in all_sources:
        grade_counts[s.get("grade", "D")] = grade_counts.get(s.get("grade", "D"), 0) + 1
    print(
        f"[corpus] 最终: {len(all_sources)} 篇 "
        f"(A:{grade_counts['A']}/B:{grade_counts['B']}/"
        f"C:{grade_counts['C']}/D:{grade_counts['D']})",
        file=sys.stderr,
    )

    return all_sources
