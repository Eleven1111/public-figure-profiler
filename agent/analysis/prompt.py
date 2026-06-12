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
    markers_block: str = "",
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

    MAX_TOTAL_CHARS = 150_000
    PER_SOURCE_LIMITS = {"A": 25_000, "B": 15_000, "C": 3_000, "D": 1_000}

    sorted_sources = sorted(
        corpus_sources,
        key=lambda s: "ABCD".index(s.get("grade", "D")),
    )

    corpus_lines = []
    total_chars = 0
    for s in sorted_sources:
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
        if s.get("stance") and s["stance"] != "neutral":
            meta.append(f"立场: {s['stance']}")
        if s.get("syndication_of"):
            meta.append(f"同源转载自: {s['syndication_of']}（引证时算同一独立来源）")
        header = f"[{s['source_id']} | " + " | ".join(meta) + "]"
        content = s["content"]
        limit = PER_SOURCE_LIMITS.get(s.get("grade", "D"), 1_000)
        if len(content) > limit:
            content = content[:limit] + "\n[...截断...]"
        remaining = MAX_TOTAL_CHARS - total_chars
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining] + "\n[...总量上限截断...]"
        total_chars += len(content)
        corpus_lines.append(f"{header}\n{content}")

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
        + (f"{markers_block}\n\n" if markers_block else "")
        +
        "请严格按照 AGENT.md 中的 Step 0 → Step 7 流程执行。\n\n"
        "**输出结构（强制，不可省略或合并）：**\n"
        "1. **先输出完整 Markdown 叙事报告** — 严格遵循 output-schema.md 中的「Markdown 报告模板（Deep Mode）」，"
        "包含所有章节：分析元信息、先验 vs 实际、认知转折点时间轴、矛盾日志、"
        "画像主体（§1–§N，按启用框架逐节展开，每节有原文引证 [Snn] 和行为预测）、"
        "置信度总览、研究局限性、参考文献。每一节都必须有实质内容，不得用「见 JSON」替代。\n"
        "2. **报告写完后**，在最末尾追加一个 ```json ... ``` 代码块（符合 output-schema.md 的 JSON Schema）。\n\n"
        "JSON 是报告的结构化副本，不能替代叙事报告本身。"
    )

    return f"<system>\n{system_block}\n</system>\n\n<user>\n{user_block}\n</user>"
