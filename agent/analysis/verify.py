"""引文真实性校验：报告中的每条「原文」[Snn] 回查语料原文。

把反幻觉从 prompt 约束升级为可执行的硬校验：
  1. 从报告 markdown 提取所有 「引文」[Snn] / "quote" [Snn] 形态的引证
  2. 对每条引证做归一化 shingle 匹配，检查是否真实出现在对应 source 的原文里
  3. 输出逐条校验结果与汇总统计；未验证引文一律点名

匹配采用字符 n-gram 覆盖率而非精确子串：报告常对原文做轻微删节、
标点调整或繁简转换，精确匹配会大量误报。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# 「引文」[S01] 或 「引文」[S01, 2024, 播客]；同时兼容英文引号
_CITATION_RE = re.compile(
    r"[「\"“]([^「」\"“”]{6,500})[」\"”]\s*\[(S\d{2})(?:[,，][^\]]*)?\]"
)

_MIN_QUOTE_CHARS = 8
_SHINGLE_K = 6
_VERIFIED_THRESHOLD = 0.7
_PARTIAL_THRESHOLD = 0.4


@dataclass
class QuoteCheck:
    quote: str
    source_id: str
    coverage: float
    status: str  # verified / partial / unverified / unknown_source


@dataclass
class VerificationReport:
    checks: list[QuoteCheck] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.checks)

    def count(self, status: str) -> int:
        return sum(1 for c in self.checks if c.status == status)

    @property
    def pass_rate(self) -> float:
        if not self.checks:
            return 1.0
        ok = self.count("verified") + self.count("partial")
        return ok / len(self.checks)

    def to_markdown(self) -> str:
        lines = [
            "# 引文真实性校验报告",
            "",
            f"- 引证总数：{self.total}",
            f"- ✅ 已验证（覆盖率 ≥ {_VERIFIED_THRESHOLD:.0%}）：{self.count('verified')}",
            f"- 🟡 部分匹配（{_PARTIAL_THRESHOLD:.0%} – {_VERIFIED_THRESHOLD:.0%}）：{self.count('partial')}",
            f"- ❌ 未验证（疑似改写或幻觉）：{self.count('unverified')}",
            f"- ⚠️ 来源编号不存在：{self.count('unknown_source')}",
            f"- 通过率：{self.pass_rate:.1%}",
            "",
        ]
        problems = [
            c for c in self.checks if c.status in ("unverified", "unknown_source")
        ]
        if problems:
            lines.append("## 需人工复核的引证")
            lines.append("")
            for c in problems:
                label = "来源不存在" if c.status == "unknown_source" else f"覆盖率 {c.coverage:.0%}"
                lines.append(f"- [{c.source_id}] {label}：「{c.quote[:120]}」")
        else:
            lines.append("全部引证均通过校验。")
        return "\n".join(lines) + "\n"


def _normalize(text: str) -> str:
    """去空白和全部标点后用于匹配：报告引用常增删标点，匹配只看实词字符。"""
    return re.sub(r"[^\w一-鿿]+", "", text).lower()


def _shingles(text: str, k: int = _SHINGLE_K) -> set[str]:
    if len(text) < k:
        return {text} if text else set()
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def quote_coverage(quote: str, source_content: str) -> float:
    """引文 n-gram 在原文 n-gram 集合中的覆盖率（0–1）。"""
    q = _normalize(quote)
    if len(q) < _MIN_QUOTE_CHARS:
        return 1.0  # 过短引文无法可靠判定，放行
    q_shingles = _shingles(q)
    if not q_shingles:
        return 0.0
    s_shingles = _shingles(_normalize(source_content))
    hit = sum(1 for sh in q_shingles if sh in s_shingles)
    return hit / len(q_shingles)


def extract_citations(markdown: str) -> list[tuple[str, str]]:
    """返回 (quote, source_id) 列表。"""
    return [(m.group(1), m.group(2)) for m in _CITATION_RE.finditer(markdown)]


def verify_report(markdown: str, corpus_sources: list[dict]) -> VerificationReport:
    """对报告全文做引文校验。corpus_sources 需含 source_id 与 content。"""
    contents = {s["source_id"]: s.get("content", "") for s in corpus_sources}
    report = VerificationReport()
    for quote, sid in extract_citations(markdown):
        if sid not in contents:
            report.checks.append(QuoteCheck(quote, sid, 0.0, "unknown_source"))
            continue
        cov = quote_coverage(quote, contents[sid])
        if cov >= _VERIFIED_THRESHOLD:
            status = "verified"
        elif cov >= _PARTIAL_THRESHOLD:
            status = "partial"
        else:
            status = "unverified"
        report.checks.append(QuoteCheck(quote, sid, cov, status))
    return report
