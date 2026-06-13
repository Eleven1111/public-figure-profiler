"""Step 7.5 — 特稿版（纽约客风格人物特稿）生成。

特稿是技术版报告的**叙事化翻译**，不是另一次分析：输入为已完成的技术
markdown 报告，输出为零黑话、面向普通读者的人物特稿。两版结论必须一致。
"""
from __future__ import annotations

from pathlib import Path

# 正文严禁出现的方法论/心理学术语（用于 prompt 内的红线提示）
BANNED_TERMS = [
    "生成机制", "引擎", "回推检验", "残差", "决定性货币", "双重身位",
    "核心张力", "补偿策略", "强化循环", "身份支柱", "防御", "核心冲突",
    "归因", "ACH", "置信度", "nAch", "nPow", "Big Five", "大五",
    "框架", "维度", "编码", "图式", "控制点", "操作码",
]


def build_narrative_prompt(
    person: str,
    purpose: str,
    technical_markdown: str,
    narrative_template: str,
    verification_summary: str = "",
    technical_filename: str = "",
    technical_json: str = "",
) -> str:
    """组装特稿生成 prompt。

    输入是已完成的技术报告（结论来源），不重新喂语料——强制"翻译"而非"重析"。
    technical_json 为可选兜底：当 markdown 叙事被截断时，结构化 JSON 仍保留全部
    结论，作为补充素材附在 prompt 末尾。
    """
    banned = "、".join(BANNED_TERMS)
    verify_note = (
        f"\n\n**引文校验提示：** {verification_summary}\n"
        "凡未通过校验的引语，正文一律不得直接加引号引用，只能意译复述。"
        if verification_summary
        else ""
    )
    tech_ref = technical_filename or "技术版报告"

    system_block = f"""你是一位为《纽约客》（The New Yorker）撰写人物特稿的资深作者。
你将拿到一份关于「{person}」的、已完成的技术性心理分析报告，
你的任务是把它改写成一篇面向普通读者的人物特稿。

这是**翻译与再叙事**，不是重新分析：所有结论、成因判断、预测都已在技术报告里给出，
你只负责让它们以《纽约客》的笔法被普通人读懂、读进去——不得引入技术报告中没有的新结论。

请严格遵循下面这份特稿写作模版的全部要求，尤其是「零黑话」红线。

---

{narrative_template}"""

    user_block = f"""# 任务

把下面这份关于「{person}」的技术分析报告，改写成一篇《纽约客》风格的人物特稿。

**分析目的（供你把握重点）：** {purpose}

## 绝对红线（违反即失败）

1. **正文零黑话**：下列术语及其同类**严禁出现在正文任何位置**——
   {banned}。
   不是"翻译得通俗些"，而是让这些概念**化进故事、让读者自己悟到**，
   却从头到尾不知道它们有名字。
2. **成因分析是灵魂，但必须被故事消化**：技术报告里那条贯穿性的成因线索
   （这个人为什么会变成这样）是全文的高潮，但它要通过一个个具体事例
   自然浮现，让读者在某一刻产生"原来他一辈子都在做同一件事"的顿悟，
   而**不能**被一句"他的核心机制是……"直接点破。
3. **方法论全部进文末附注**：证伪条件、证据等级、置信度分层、来源评分——
   正文一个字都不许提，全部移到文末"关于这篇文章"。
   正文负责"让人信、让人懂"，附注负责"对得起严谨"。
4. **不虚构**：不得编造技术报告中没有的场景细节（天气、神态、未记录的对话）。
   只能复述报告中有据的事实。{verify_note}

## 结构与笔法

- 用一个"言行错位"或反常细节开篇，埋下"为什么"的钩子
- 把成年后的关键行为一条条接回那个原点，让读者自己看出那条线
- 用"时间点"检验那条线（他为什么偏偏在那个时刻做那件事）——这是最有说服力的一击
- 写出这条线的代价（他的盲区、那道解不开的结）
- 收尾用他自己的一句原话或比喻，回扣开篇
- 可读性优先：小标题能省则省，自然段落群即可，不必凑节数

## 文末附注（固定四块）

正文后用 `---` 分隔，标题用平实措辞（如"关于这篇文章"），包含：
核心假设的地位（为何可信：一条线索贯穿多个行为 + 命中时间点）、
它会怎样被证伪（1 条具体可观察的反证条件）、
证据与置信度（哪些是事实/哪些是推断/最大资料缺口）、
主要资料来源 + 指引读者查技术版 `{tech_ref}`（注明文中复述为意译）。

直接输出特稿全文（Markdown），不要任何前言或解释。

---

# 技术分析报告（你的素材来源）

{technical_markdown}"""

    if technical_json:
        user_block += (
            "\n\n---\n\n"
            "# 结构化结论（补充素材）\n\n"
            "下面是同一份分析的结构化数据。若上方叙事报告有缺失或截断，"
            "以此处的结论为准；但**不要**把字段名、英文键、数值评分写进特稿正文。\n\n"
            f"```json\n{technical_json}\n```"
        )

    return f"<system>\n{system_block}\n</system>\n\n<user>\n{user_block}\n</user>"


def write_narrative(
    output_dir: Path,
    slug: str,
    date_str: str,
    narrative_text: str,
    output_suffix: str = "",
) -> Path:
    """写出 <slug>_<date><suffix>.特稿.md。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{output_suffix}" if output_suffix else ""
    path = output_dir / f"{slug}_{date_str}{suffix}.特稿.md"
    path.write_text(narrative_text.strip() + "\n", encoding="utf-8")
    return path
