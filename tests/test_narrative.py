"""Step 7.5 特稿生成测试。"""
from pathlib import Path

from agent.analysis.narrative import (
    BANNED_TERMS,
    build_narrative_prompt,
    write_narrative,
)

TECH_MD = """# 黄某 心理侧写（技术版）

## 深层动力分析
生成机制：原初情境 → 核心张力 → 补偿策略 → 行为输出
身份支柱：判断正确

## 综合心智模型
决策函数：当面对不确定性时……

## 参考文献
- [S01] 某访谈 | A级
"""

TEMPLATE = "# 特稿模版\n零黑话红线：术语不得进正文。"


def test_build_prompt_includes_template_and_report():
    p = build_narrative_prompt(
        person="黄某",
        purpose="投资尽调",
        technical_markdown=TECH_MD,
        narrative_template=TEMPLATE,
        technical_filename="huang_20260101.md",
    )
    assert "黄某" in p
    assert "投资尽调" in p
    assert "零黑话红线" in p          # 模版被嵌入
    assert "判断正确" in p            # 技术报告被嵌入
    assert "huang_20260101.md" in p   # 指引读者查技术版


def test_build_prompt_lists_banned_terms():
    p = build_narrative_prompt(
        person="X", purpose="y",
        technical_markdown=TECH_MD, narrative_template=TEMPLATE,
    )
    # 几个核心黑话词必须出现在红线清单里
    for term in ["生成机制", "身份支柱", "置信度", "nAch"]:
        assert term in p
    assert all(t in BANNED_TERMS for t in ["引擎", "残差", "决定性货币"])


def test_build_prompt_verification_note_conditional():
    with_note = build_narrative_prompt(
        person="X", purpose="y",
        technical_markdown=TECH_MD, narrative_template=TEMPLATE,
        verification_summary="共 5 条引证，通过率 20%",
    )
    assert "20%" in with_note
    assert "不得直接加引号" in with_note

    without = build_narrative_prompt(
        person="X", purpose="y",
        technical_markdown=TECH_MD, narrative_template=TEMPLATE,
    )
    assert "不得直接加引号" not in without


def test_write_narrative_filename_and_content(tmp_path: Path):
    path = write_narrative(tmp_path, "huang", "20260101_1200", "# 标题\n正文内容")
    assert path.name == "huang_20260101_1200.特稿.md"
    assert path.read_text(encoding="utf-8").startswith("# 标题")
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_write_narrative_with_suffix(tmp_path: Path):
    path = write_narrative(tmp_path, "huang", "20260101_1200", "正文", output_suffix="codex")
    assert path.name == "huang_20260101_1200_codex.特稿.md"
