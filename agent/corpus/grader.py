"""语料评级：先用规则快速定级，再（可选）用 LLM 二次校准。

等级定义（参考 core.md）：
  A 级 — 长篇未剪辑访谈、播客原稿、听证会证词、完整对谈转录
  B 级 — 专题深访、圆桌发言、长篇媒体报道
  C 级 — 公开信、长文博客、Substack
  D 级 — 声明、PR 稿、演讲稿、新闻摘录、维基百科
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


# ── 基于域名和长度的启发式规则 ────────────────────────────────────────────────


A_GRADE_HINTS = {
    # 播客文字稿专业站点
    "lexfridman.com",
    "huberman",
    "tim.blog",
    "dwarkeshpatel.com",
    # YouTube 字幕（如果是完整对话）视内容长度
}

B_GRADE_HINTS = {
    "newyorker.com",
    "theatlantic.com",
    "wired.com",
    "ft.com",
    "economist.com",
    "bloomberg.com",
    "technologyreview.com",
    "latepost.com",
    "36kr.com",
    "huxiu.com",
    "sohu.com/a",
    "caixin.com",
}

C_GRADE_HINTS = {
    "substack.com",
    "medium.com",
    "blog",
    "personal",
}

D_GRADE_HINTS = {
    "wikipedia.org",
    "prnewswire",
    "businesswire",
    "reuters.com/article",
    "apnews.com",
}


@dataclass
class GradeSignal:
    grade: str  # A / B / C / D
    reason: str


# ── 立场分类（对抗性语料识别）──────────────────────────────────────────────

_CRITICAL_MARKERS = [
    # 中文
    "做空", "起诉", "诉讼", "指控", "质疑", "争议", "丑闻", "调查报告",
    "维权", "举报", "处罚", "罚款", "监管约谈", "离职员工", "批评",
    "翻车", "塌房", "造假", "欺诈", "失信",
    # 英文
    "lawsuit", "sued", "fraud", "scandal", "controversy", "criticism",
    "critics", "whistleblower", "short seller", "short-seller", "sec filing",
    "investigation", "allegation", "accused", "fined", "settlement",
]

_FIRSTPERSON_MARKERS = [
    "我认为", "我觉得", "我们的", "我说", "采访", "访谈", "对话",
    "transcript", "interview", "q&a", "shareholder letter", "股东信", "公开信",
]


def classify_stance(content: str, title: str = "") -> str:
    """启发式立场分类：critical / first_person / neutral。

    critical 来源是言行对照和矛盾分析的关键证据，
    采集配额要求每次至少 2 条（见 acquisition loop system prompt）。
    """
    text = (title + " " + content[:3000]).lower()
    critical_hits = sum(1 for m in _CRITICAL_MARKERS if m in text)
    if critical_hits >= 2:
        return "critical"
    if any(m in text for m in _FIRSTPERSON_MARKERS):
        return "first_person"
    return "neutral"


def _heuristic_grade(url: str, content: str, title: str = "") -> GradeSignal:
    """基于域名、URL 路径和内容长度的规则评级。"""
    u = (url or "").lower()
    t = (title or "").lower()
    word_count = len(content.split()) if content else 0
    char_count = len(content) if content else 0

    # 维基百科固定 D 级
    if "wikipedia.org" in u:
        return GradeSignal("D", "wikipedia/background")

    # YouTube 字幕：按长度分
    if "youtube.com" in u or "youtu.be" in u:
        if char_count >= 12000:
            return GradeSignal("A", "long youtube transcript")
        if char_count >= 4000:
            return GradeSignal("B", "medium youtube transcript")
        return GradeSignal("C", "short youtube transcript")

    # 听证会/法庭证词（关键词）
    if re.search(
        r"(congressional|senate hearing|testimony|听证会|证词)", t + " " + u, re.I
    ):
        return GradeSignal("A", "testimony/hearing")

    # 「transcript」「全文」「实录」
    if re.search(r"(transcript|全文|实录|完整对话)", t + " " + u, re.I) and char_count > 4000:
        return GradeSignal("A", "transcript/long")

    # 基于域名的专业访谈站点
    for hint in A_GRADE_HINTS:
        if hint in u:
            if char_count >= 8000:
                return GradeSignal("A", f"domain:{hint}")
            return GradeSignal("B", f"domain:{hint} (short)")

    for hint in B_GRADE_HINTS:
        if hint in u:
            if char_count >= 6000:
                return GradeSignal("B", f"quality media:{hint}")
            return GradeSignal("C", f"quality media:{hint} (short)")

    for hint in D_GRADE_HINTS:
        if hint in u:
            return GradeSignal("D", f"PR/wire:{hint}")

    # 默认按长度分
    if char_count >= 8000:
        return GradeSignal("B", "long article")
    if char_count >= 2000:
        return GradeSignal("C", "medium article")
    if word_count >= 100:
        return GradeSignal("D", "short snippet")

    return GradeSignal("D", "minimal content")


def grade_source(source: dict) -> GradeSignal:
    """对单个语料源评级。

    source 应包含：source/url、content、title（可选）。
    """
    if source.get("grade") in ("A", "B", "C", "D"):
        # 用户手动指定的等级优先（A 级用户语料）
        return GradeSignal(source["grade"], "user-specified")

    return _heuristic_grade(
        url=source.get("source", "") or source.get("url", ""),
        content=source.get("content", ""),
        title=source.get("title", ""),
    )


def grade_all(sources: list[dict]) -> list[dict]:
    """批量评级，写回 source['grade'] 和 source['grade_reason']。"""
    for s in sources:
        sig = grade_source(s)
        s["grade"] = sig.grade
        s["grade_reason"] = sig.reason
    return sources
