"""引文真实性校验测试。"""
from agent.analysis.verify import (
    extract_citations,
    quote_coverage,
    verify_report,
)


CORPUS = [
    {
        "source_id": "S01",
        "content": "我认为简单和常识的力量是最重要的，这顿饭对我最大的意义可能让我意识到简单和常识的力量。活着是创业的第一要务。",
    },
    {
        "source_id": "S02",
        "content": "He said the company would focus on long-term value, not quarterly metrics, because real moats take a decade to build.",
    },
]


def test_extract_citations_cn_and_meta():
    md = "结论一「简单和常识的力量」[S01, 2016, 博客]，结论二「不存在的引文片段」[S02]。"
    cites = extract_citations(md)
    assert ("简单和常识的力量", "S01") in cites
    assert ("不存在的引文片段", "S02") in cites


def test_quote_coverage_verbatim_high():
    assert quote_coverage("这顿饭对我最大的意义可能让我意识到简单和常识的力量", CORPUS[0]["content"]) > 0.9


def test_quote_coverage_fabricated_low():
    assert quote_coverage("我们要不惜一切代价赢得这场战争的全面胜利", CORPUS[0]["content"]) < 0.3


def test_quote_coverage_tolerates_punctuation_changes():
    quote = "活着，是创业的第一要务"  # 原文无逗号
    assert quote_coverage(quote, CORPUS[0]["content"]) >= 0.7


def test_verify_report_statuses():
    md = (
        "「活着是创业的第一要务」[S01, 2016, 博客]\n"
        "「彻底虚构的一段从未出现过的引文内容啊」[S01]\n"
        "「任意引文指向不存在的来源编号」[S99]\n"
    )
    report = verify_report(md, CORPUS)
    assert report.total == 3
    assert report.count("verified") == 1
    assert report.count("unverified") == 1
    assert report.count("unknown_source") == 1
    assert "S99" in report.to_markdown()


def test_verify_report_empty_md():
    report = verify_report("没有任何引证的报告", CORPUS)
    assert report.total == 0
    assert report.pass_rate == 1.0
