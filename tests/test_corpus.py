"""单元测试：语料采集管道的纯函数层。

不测试网络调用（fetcher / wikipedia / youtube），仅测试可确定性的逻辑：
  - dedupe（URL 规范化、内容哈希、Jaccard 相似度）
  - grader（启发式评级）
  - search.build_search_queries（查询生成）
  - pipeline（source_id 分配、预算截断）
"""

from __future__ import annotations

import pytest

from agent.corpus.dedupe import (
    canonical_url,
    content_hash,
    dedupe_sources,
)
from agent.corpus.grader import grade_source, grade_all
from agent.corpus.pipeline import (
    _assign_source_ids,
    _truncate_to_budget,
)
from agent.corpus.search import build_search_queries


# ── canonical_url ────────────────────────────────────────────────────────────


class TestCanonicalUrl:
    def test_strips_www(self):
        assert canonical_url("https://www.example.com/a") == "https://example.com/a"

    def test_strips_trailing_slash(self):
        assert canonical_url("https://example.com/a/") == "https://example.com/a"

    def test_lowercases(self):
        assert canonical_url("HTTPS://EXAMPLE.COM/A") == "https://example.com/a"

    def test_removes_utm_params(self):
        u = canonical_url("https://example.com/a?utm_source=x&q=1")
        assert "utm_" not in u
        assert "q=1" in u

    def test_removes_tracking_fields(self):
        u = canonical_url("https://example.com/a?fbclid=xx&gclid=yy&ref=z")
        assert "fbclid" not in u
        assert "gclid" not in u
        assert "ref=" not in u

    def test_empty_returns_empty(self):
        assert canonical_url("") == ""


# ── content_hash ─────────────────────────────────────────────────────────────


class TestContentHash:
    def test_same_text_same_hash(self):
        assert content_hash("hello world") == content_hash("hello world")

    def test_whitespace_normalized(self):
        assert content_hash("hello  world") == content_hash("hello world")
        assert content_hash("hello\n\nworld") == content_hash("hello world")

    def test_different_text_different_hash(self):
        assert content_hash("apple") != content_hash("banana")


# ── dedupe_sources ───────────────────────────────────────────────────────────


class TestDedupeSources:
    def test_empty_input(self):
        assert dedupe_sources([]) == []

    def test_url_dedup(self):
        sources = [
            {"source": "https://example.com/a", "content": "one"},
            {"source": "https://www.example.com/a", "content": "different content here"},
        ]
        result = dedupe_sources(sources)
        assert len(result) == 1

    def test_content_hash_dedup(self):
        sources = [
            {"source": "https://a.com/x", "content": "identical content " * 50},
            {"source": "https://b.com/y", "content": "identical content " * 50},
        ]
        result = dedupe_sources(sources)
        assert len(result) == 1

    def test_jaccard_dedup(self):
        base = "The quick brown fox jumps over the lazy dog. " * 50
        similar = base + " Extra sentence."
        sources = [
            {"source": "https://a.com/1", "content": base},
            {"source": "https://b.com/2", "content": similar},
        ]
        result = dedupe_sources(sources)
        assert len(result) == 1

    def test_different_content_kept(self):
        sources = [
            {"source": "https://a.com/1", "content": "Apples are red fruits grown on trees worldwide. " * 50},
            {"source": "https://b.com/2", "content": "Python is a programming language used for data science. " * 50},
        ]
        result = dedupe_sources(sources)
        assert len(result) == 2

    def test_short_content_skips_jaccard(self):
        sources = [
            {"source": "https://a.com/1", "content": "short text a"},
            {"source": "https://b.com/2", "content": "short text b"},
        ]
        result = dedupe_sources(sources)
        assert len(result) == 2


# ── grader ──────────────────────────────────────────────────────────────────


class TestGrader:
    def test_wikipedia_always_d(self):
        s = {"source": "https://en.wikipedia.org/wiki/X", "content": "long content " * 2000}
        assert grade_source(s).grade == "D"

    def test_user_specified_a_preserved(self):
        s = {"grade": "A", "source": "/local/file.txt", "content": "x"}
        assert grade_source(s).grade == "A"

    def test_long_youtube_is_a(self):
        s = {
            "source": "https://youtube.com/watch?v=abc",
            "content": "x" * 15000,
        }
        assert grade_source(s).grade == "A"

    def test_short_youtube_is_c(self):
        s = {
            "source": "https://youtube.com/watch?v=abc",
            "content": "x" * 1000,
        }
        assert grade_source(s).grade == "C"

    def test_testimony_in_title_is_a(self):
        s = {
            "source": "https://congress.gov/whatever",
            "title": "Congressional Testimony on AI",
            "content": "x" * 1000,
        }
        assert grade_source(s).grade == "A"

    def test_quality_media_long_is_b(self):
        s = {
            "source": "https://newyorker.com/magazine/article",
            "content": "x" * 10000,
        }
        assert grade_source(s).grade == "B"

    def test_minimal_content_is_d(self):
        s = {"source": "https://unknown.com/a", "content": "too short"}
        assert grade_source(s).grade == "D"

    def test_grade_all_writes_back(self):
        sources = [
            {"source": "https://en.wikipedia.org/wiki/X", "content": "x"},
            {"source": "https://unknown.com/long", "content": "a " * 5000},
        ]
        grade_all(sources)
        assert sources[0]["grade"] == "D"
        assert "grade_reason" in sources[0]
        assert sources[1]["grade"] in ("B", "C", "D")


# ── build_search_queries ────────────────────────────────────────────────────


class TestBuildSearchQueries:
    def test_english_generates_english_queries(self):
        qs = build_search_queries("Dario Amodei", ["en"])
        assert any("podcast transcript" in q for q in qs)
        assert all('"Dario Amodei"' in q for q in qs)

    def test_chinese_generates_chinese_queries(self):
        qs = build_search_queries("任正非", ["zh"])
        assert any("访谈全文" in q for q in qs)
        assert all('"任正非"' in q for q in qs)

    def test_both_languages_merges(self):
        qs = build_search_queries("Elon Musk", ["en", "zh"])
        has_en = any("podcast" in q for q in qs)
        has_zh = any("访谈" in q for q in qs)
        assert has_en and has_zh

    def test_empty_languages_empty_queries(self):
        assert build_search_queries("X", []) == []


# ── pipeline helpers ────────────────────────────────────────────────────────


class TestAssignSourceIds:
    def test_sequential_numbering(self):
        sources = [
            {"grade": "B", "word_count": 100},
            {"grade": "A", "word_count": 200},
            {"grade": "D", "word_count": 50},
        ]
        _assign_source_ids(sources)
        ids = [s["source_id"] for s in sources]
        assert ids == ["S01", "S02", "S03"]

    def test_a_grade_first(self):
        sources = [
            {"grade": "D", "word_count": 100},
            {"grade": "A", "word_count": 200},
            {"grade": "B", "word_count": 150},
        ]
        _assign_source_ids(sources)
        # After sort A goes first
        assert sources[0]["grade"] == "A"
        assert sources[0]["source_id"] == "S01"
        assert sources[-1]["grade"] == "D"

    def test_longer_content_first_within_grade(self):
        sources = [
            {"grade": "A", "word_count": 100, "title": "short"},
            {"grade": "A", "word_count": 500, "title": "long"},
        ]
        _assign_source_ids(sources)
        assert sources[0]["title"] == "long"
        assert sources[0]["source_id"] == "S01"

    def test_zero_pad_format(self):
        sources = [{"grade": "A", "word_count": 100} for _ in range(3)]
        _assign_source_ids(sources)
        for s in sources:
            assert s["source_id"].startswith("S0")
            assert len(s["source_id"]) == 3


class TestTruncateToBudget:
    def test_keeps_a_grade_preferentially(self):
        sources = [
            {"grade": "D", "word_count": 500},
            {"grade": "B", "word_count": 200},
            {"grade": "A", "word_count": 300},
            {"grade": "C", "word_count": 100},
        ]
        result = _truncate_to_budget(sources, max_sources=2)
        grades = [s["grade"] for s in result]
        assert "A" in grades
        assert "B" in grades
        assert "D" not in grades

    def test_no_truncation_when_under_budget(self):
        sources = [{"grade": "A", "word_count": 100}]
        result = _truncate_to_budget(sources, max_sources=10)
        assert len(result) == 1

    def test_empty_input(self):
        assert _truncate_to_budget([], max_sources=5) == []
