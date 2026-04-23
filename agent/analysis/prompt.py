"""Build the full analysis prompt passed to claude CLI."""
from __future__ import annotations


def build_prompt(
    person: str,
    purpose: str,
    mode: str,
    frameworks: list[str],
    corpus_sources: list[dict],
    adequacy: str,
    agent_md: str,
    framework_docs: str,
    output_schema: str,
) -> str:
    """Assemble system + user content into a single stdin prompt for claude -p."""
    adequacy_notes = {
        "sufficient": "",
        "sparse": "\n⚠️ 语料偏少（A/B级来源不足3篇），整体置信度上限为「中」。",
        "insufficient": (
            "\n⚠️ 语料不足（仅有C/D级来源），"
            "所有结论置信度最高为「低」，以探索性草稿模式输出。"
        ),
    }

    corpus_lines = []
    for s in corpus_sources:
        meta = [
            f"等级: {s.get('grade', '?')}",
            f"来源: {s.get('source') or s.get('url', '用户提供')}",
        ]
        if s.get("published_date"):
            meta.append(f"发布: {s['published_date']}")
        if s.get("origin"):
            meta.append(f"工具: {s['origin']}")
        if s.get("title"):
            meta.append(f"标题: {s['title']}")
        header = f"[{s['source_id']} | " + " | ".join(meta) + "]"
        corpus_lines.append(f"{header}\n{s['content']}")

    corpus_text = "\n\n---\n\n".join(corpus_lines)
    framework_list = ", ".join(frameworks)

    system_block = f"""{agent_md}

---

# 本次激活的分析框架

{framework_docs}

---

# 输出格式规范

{output_schema}"""

    user_block = (
        f"请对以下公开人物进行{'完整' if mode == 'deep' else '快速'}心理侧写分析。\n\n"
        f"**分析目标：** {person}\n"
        f"**分析目的：** {purpose}\n"
        f"**分析模式：** {mode.upper()} MODE\n"
        f"**本次激活框架：** {framework_list}"
        f"{adequacy_notes[adequacy]}\n\n"
        f"**已收集语料（共 {len(corpus_sources)} 篇，已预分配 source_id）：**\n\n"
        f"{corpus_text if corpus_sources else '（无语料，无法分析）'}\n\n"
        "请严格按照 AGENT.md 中的 Step 0 → Step 7 流程执行。\n"
        "报告正文中每条引证必须带 [Snn] 编号，并在末尾输出「## 参考文献」章节。\n"
        "Deep Mode 另外追加一个 ```json ... ``` 代码块（符合 output-schema.md）。"
    )

    return f"<system>\n{system_block}\n</system>\n\n<user>\n{user_block}\n</user>"
