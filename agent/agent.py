#!/usr/bin/env python3
"""
Public Figure Profiler — Hermes Agent CLI

对任意公开人物进行心理侧写分析。
混合语料获取：用户提供 → WebSearch/WebFetch → YouTube 转录 → 音频转录（可选）。
支持多 LLM 后端：Anthropic、OpenAI、任意 OpenAI 兼容平台。

用法：
  python -m agent.agent --person "Dario Amodei" --mode deep --purpose "投资尽调"
  python -m agent.agent --person "任正非" --mode quick --corpus interview.txt
  python -m agent.agent --person "Jensen Huang" --provider openai --model gpt-4o
  python -m agent.agent --person "李飞飞" --provider compatible \
      --base-url https://api.deepseek.com/v1 --model deepseek-chat
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import openai
from youtube_transcript_api import YouTubeTranscriptApi


# ── 常量 ────────────────────────────────────────────────────────────────────

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-6",
    "openai": "gpt-4o",
    # "compatible" 无内置默认，用户必须通过 --model 指定
}

# ── 语料工具函数 ─────────────────────────────────────────────────────────────


def make_slug(name: str) -> str:
    """将人名转为文件系统安全的 slug。

    规则：转小写，去除特殊字符，空格/连字符替换为下划线。
    中文字符保留（Unicode 安全）。
    """
    slug = name.strip().lower()
    # 去除非字母数字、非中文、非空格的字符
    slug = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", slug)
    # 合并连续空格/连字符为单个下划线
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug.strip("_")


def load_user_corpus(paths: list[str]) -> list[dict]:
    """加载用户提供的语料文件。

    用户提供的语料默认评为 A 级（已经过用户筛选，信息密度高）。
    """
    sources = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            print(f"Warning: corpus file not found: {path}", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8")
        sources.append(
            {
                "grade": "A",
                "source": str(p),
                "content": text,
                "word_count": len(text.split()),
            }
        )
    return sources


def assess_corpus_adequacy(sources: list[dict]) -> str:
    """评估语料充分性。

    Returns:
        "sufficient"    A/B 级来源 ≥3 篇
        "sparse"        A/B 级来源 1-2 篇
        "insufficient"  无 A/B 级来源
    """
    ab_count = sum(1 for s in sources if s.get("grade") in ("A", "B"))
    if ab_count >= 3:
        return "sufficient"
    elif ab_count >= 1:
        return "sparse"
    else:
        return "insufficient"


def fetch_youtube_transcript(url: str) -> str | None:
    """从 YouTube URL 提取字幕文本。

    使用 youtube-transcript-api（无需 API Key）。
    提取失败时静默返回 None，由调用方决定降级策略。
    """
    try:
        match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
        if not match:
            return None

        video_id = match.group(1)
        fetched = YouTubeTranscriptApi().fetch(video_id)
        entries = fetched.to_raw_data()
        return " ".join(entry["text"] for entry in entries)
    except Exception:
        return None


# ── 提示词构建 ───────────────────────────────────────────────────────────────


_COMPACT_SYSTEM_PROMPT = """\
你是专业的公开人物认知与心理分析助手，基于公开资料对目标人物进行侧写分析。

核心规范：
- Step 0：先写出你对该人物的既有印象（≤5条），分析完后说明哪些被证实/推翻
- 每个结论必须附原始文本引证（直接引用原文，不接受裸形容词）
- 跨情境一致出现的才算稳定特征；矛盾点是最高信号密度的材料
- 置信度：高（≥3个跨情境引证）/ 中（1-2个）/ 低（推断）
- 使用「在公开表达中呈现出……倾向」，不做临床诊断，不推测私人生活
- 每个维度末尾必须给出行为预测：「在[具体情境]下，此人倾向于[具体行为]，因为[认知逻辑]」

Quick Mode：给出3个核心发现 + 行为预测
Deep Mode：完整报告（人格与行事风格 / 认知结构 / 心理表征与叙事 / 受众敏感度）+ 末尾输出 ```json ... ``` 结构化数据
"""


def build_system_prompt(agent_md: str, codebook: str, output_schema: str) -> str:
    """将三个指令文件合并为完整 system prompt（全量模式）。"""
    return f"""{agent_md}

---

## 分析框架参考（codebook.md）

{codebook}

---

## 输出格式规范（output-schema.md）

{output_schema}
"""


def build_compact_system_prompt() -> str:
    """返回精简版 system prompt（~200 tokens），适配小 context 模型。"""
    return _COMPACT_SYSTEM_PROMPT


def build_user_message(
    person: str,
    purpose: str,
    mode: str,
    corpus_sources: list[dict],
    adequacy: str,
) -> str:
    """构建分析请求的用户消息，与具体 LLM API 无关。"""
    adequacy_notes = {
        "sufficient": "",
        "sparse": "\n⚠️ 语料偏少（A/B级来源不足3篇），整体置信度上限为「中」。",
        "insufficient": (
            "\n⚠️ 语料不足（仅有C/D级来源），"
            "所有结论置信度最高为「低」，以探索性草稿模式输出。"
        ),
    }

    corpus_text = "\n\n---\n\n".join(
        f"[来源 {i + 1} | 等级: {s['grade']} | {s.get('source', '用户提供')}]\n{s['content']}"
        for i, s in enumerate(corpus_sources)
    )

    return (
        f"请对以下公开人物进行{'完整' if mode == 'deep' else '快速'}心理侧写分析。\n\n"
        f"**分析目标：** {person}\n"
        f"**分析目的：** {purpose}\n"
        f"**分析模式：** {mode.upper()} MODE"
        f"{adequacy_notes[adequacy]}\n\n"
        f"**已收集语料（共 {len(corpus_sources)} 篇）：**\n\n"
        f"{corpus_text if corpus_sources else '（无预置语料，请通过 WebSearch/WebFetch 自行获取）'}\n\n"
        "请严格按照 AGENT.md 中的 Step 0 → Step 7 流程执行，输出完整报告。\n"
        "在报告末尾，输出一个 ```json ... ``` 代码块，包含符合 output-schema.md 的结构化数据。"
    )


# ── LLM API 调用层 ───────────────────────────────────────────────────────────


def call_anthropic(system_prompt: str, user_message: str, model: str) -> str:
    """调用 Anthropic API，返回原始响应文本。

    API Key 从环境变量 ANTHROPIC_API_KEY 读取。
    """
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def call_openai_compatible(
    system_prompt: str,
    user_message: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
) -> str:
    """调用 OpenAI 或 OpenAI 兼容 API，返回原始响应文本。

    base_url=None  →  OpenAI 官方端点
    base_url 传值  →  任意兼容平台，如：
      DeepSeek:    https://api.deepseek.com/v1
      月之暗面:    https://api.moonshot.cn/v1
      通义千问:    https://dashscope.aliyuncs.com/compatible-mode/v1
      零一万物:    https://api.lingyiwanwu.com/v1
      Groq:        https://api.groq.com/openai/v1
    """
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def run_analysis(
    person: str,
    purpose: str,
    mode: str,
    corpus_sources: list[dict],
    adequacy: str,
    system_prompt: str,
    provider: str = "anthropic",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str | None]:
    """调用 LLM API 执行分析，返回 (markdown, json_or_none)。

    provider:
        "anthropic"  — Anthropic SDK（默认）；API Key: ANTHROPIC_API_KEY
        "openai"     — OpenAI 官方 API；API Key: OPENAI_API_KEY
        "compatible" — 任意 OpenAI 兼容平台；需提供 --base-url；
                       API Key 优先取 --api-key，其次取 PROFILER_API_KEY
    """
    effective_model = model or DEFAULT_MODELS.get(provider)
    if not effective_model:
        raise ValueError(
            f"--model 未指定。provider='{provider}' 无内置默认模型，请通过 --model 指定。"
        )

    user_message = build_user_message(person, purpose, mode, corpus_sources, adequacy)

    if provider == "anthropic":
        full_text = call_anthropic(
            system_prompt=system_prompt,
            user_message=user_message,
            model=effective_model,
        )
    elif provider in ("openai", "compatible"):
        env_key = "OPENAI_API_KEY" if provider == "openai" else "PROFILER_API_KEY"
        effective_key = api_key or os.environ.get(env_key, "")
        full_text = call_openai_compatible(
            system_prompt=system_prompt,
            user_message=user_message,
            model=effective_model,
            api_key=effective_key,
            base_url=base_url,
        )
    else:
        raise ValueError(f"未知 provider: {provider!r}，支持：anthropic / openai / compatible")

    return extract_json_from_response(full_text)


# ── 输出写入 ─────────────────────────────────────────────────────────────────


def extract_json_from_response(full_text: str) -> tuple[str, str | None]:
    """从模型输出中提取 JSON 代码块。

    Returns:
        (markdown_without_json, json_string_or_none)
    """
    json_match = re.search(r"```json\n(.*?)\n```", full_text, re.DOTALL)
    if not json_match:
        return full_text, None

    json_data = json_match.group(1)
    markdown = re.sub(r"```json\n.*?\n```", "", full_text, flags=re.DOTALL).strip()
    return markdown, json_data


def write_outputs(
    output_dir: str,
    slug: str,
    date_str: str,
    markdown: str,
    json_data: str | None,
    sources: list[dict],
) -> None:
    """将分析结果写入磁盘。

    输出：
      {output_dir}/{slug}_{date_str}.md
      {output_dir}/{slug}_{date_str}.json  （若有 JSON）
      {output_dir}/{slug}_{date_str}_corpus/  （语料缓存）
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md_path = out / f"{slug}_{date_str}.md"
    md_path.write_text(markdown, encoding="utf-8")

    if json_data is not None:
        json_path = out / f"{slug}_{date_str}.json"
        json_path.write_text(json_data, encoding="utf-8")

    # 语料缓存目录
    corpus_dir = out / f"{slug}_{date_str}_corpus"
    corpus_dir.mkdir(exist_ok=True)

    manifest = []
    for i, s in enumerate(sources):
        fname = f"source_{i + 1:02d}_{s['grade'].lower()}_grade.txt"
        (corpus_dir / fname).write_text(s.get("content", ""), encoding="utf-8")
        manifest.append(
            {
                "file": fname,
                "grade": s.get("grade", ""),
                "source": s.get("source", ""),
                "word_count": s.get("word_count", 0),
            }
        )

    (corpus_dir / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✓ Report : {md_path}", file=sys.stderr)
    if json_data is not None:
        print(f"✓ JSON   : {out / f'{slug}_{date_str}.json'}", file=sys.stderr)
    print(f"✓ Corpus : {corpus_dir}/", file=sys.stderr)


# ── CLI 入口 ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Public Figure Profiler — 公开人物心理侧写",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用 Anthropic（默认）
  python -m agent.agent --person "Jensen Huang" --mode deep --purpose "竞争对手研究"

  # 使用 OpenAI
  python -m agent.agent --person "Sam Altman" --provider openai --model gpt-4o

  # 使用 DeepSeek（兼容模式）
  python -m agent.agent --person "李飞飞" --provider compatible \\
      --base-url https://api.deepseek.com/v1 --model deepseek-chat

  # 附加自有语料 + YouTube 字幕
  python -m agent.agent --person "任正非" --mode deep \\
      --corpus speech.txt --youtube "https://youtube.com/watch?v=VIDEO_ID"
        """,
    )
    parser.add_argument("--person", required=True, help="分析对象的姓名（中英文均可）")
    parser.add_argument("--purpose", default="general research", help="分析目的")
    parser.add_argument(
        "--mode", choices=["quick", "deep"], default="deep", help="分析深度"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai", "compatible"],
        default="anthropic",
        help="LLM 后端（默认：anthropic）",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="模型名称（覆盖默认；compatible 模式下必填）",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        metavar="URL",
        help="OpenAI 兼容平台的 API 基础 URL（provider=compatible 时使用）",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help="API Key（可选；默认从对应环境变量读取）",
    )
    parser.add_argument(
        "--corpus",
        action="append",
        default=[],
        metavar="FILE",
        help="额外语料文件路径（可多次指定）",
    )
    parser.add_argument(
        "--output-dir", default="./profiles", help="输出目录（默认：./profiles）"
    )
    parser.add_argument(
        "--youtube",
        action="append",
        default=[],
        metavar="URL",
        help="YouTube 视频 URL，自动提取字幕作为语料（可多次指定）",
    )
    parser.add_argument(
        "--transcribe",
        choices=["whisper", "assemblyai"],
        help="音频转录后端（可选）",
    )
    parser.add_argument(
        "--compact-prompt",
        action="store_true",
        help="使用精简版系统提示词（~200 tokens），适配小 context 模型（如 Groq 免费层）",
    )

    args = parser.parse_args()

    # compatible 模式强制要求 --base-url
    if args.provider == "compatible" and not args.base_url:
        parser.error("--provider compatible 需要同时指定 --base-url")

    # compatible 模式强制要求 --model
    if args.provider == "compatible" and not args.model:
        parser.error("--provider compatible 需要同时指定 --model")

    # 路径定位
    base = Path(__file__).parent.parent
    agent_md_path = base / "agent" / "AGENT.md"
    codebook_path = base / "references" / "codebook.md"
    schema_path = base / "references" / "output-schema.md"

    for p in [agent_md_path, codebook_path, schema_path]:
        if not p.exists():
            print(f"Error: required file not found: {p}", file=sys.stderr)
            sys.exit(1)

    if args.compact_prompt:
        system_prompt = build_compact_system_prompt()
        print("      [精简提示词模式，~200 tokens]", file=sys.stderr)
    else:
        agent_md = agent_md_path.read_text(encoding="utf-8")
        codebook = codebook_path.read_text(encoding="utf-8")
        output_schema = schema_path.read_text(encoding="utf-8")
        system_prompt = build_system_prompt(agent_md, codebook, output_schema)

    # 语料收集
    print("[1/3] 加载用户提供的语料...", file=sys.stderr)
    sources = load_user_corpus(args.corpus)

    # YouTube 字幕提取
    if args.youtube:
        print(f"      提取 {len(args.youtube)} 个 YouTube 视频字幕...", file=sys.stderr)
        for url in args.youtube:
            transcript = fetch_youtube_transcript(url)
            if transcript:
                sources.append({
                    "grade": "A",
                    "source": url,
                    "content": transcript,
                    "word_count": len(transcript.split()),
                })
                print(f"      ✓ {url[:60]}...", file=sys.stderr)
            else:
                print(f"      ✗ 无法提取字幕：{url[:60]}", file=sys.stderr)

    adequacy = assess_corpus_adequacy(sources)
    ab_count = sum(1 for s in sources if s.get("grade") in ("A", "B"))
    print(
        f"[2/3] 语料状态: {adequacy}（A/B级: {ab_count}篇，共 {len(sources)} 篇）",
        file=sys.stderr,
    )

    if adequacy == "insufficient" and not sources:
        print(
            "      → 无预置语料，agent 将通过 WebSearch 自行获取。",
            file=sys.stderr,
        )

    # 执行分析
    slug = make_slug(args.person)
    date_str = datetime.now().strftime("%Y%m%d")

    provider_label = args.provider
    model_label = args.model or DEFAULT_MODELS.get(args.provider, "?")
    print(f"[3/3] 调用 {provider_label} / {model_label} 执行分析...", file=sys.stderr)

    markdown, json_data = run_analysis(
        person=args.person,
        purpose=args.purpose,
        mode=args.mode,
        corpus_sources=sources,
        adequacy=adequacy,
        system_prompt=system_prompt,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
    )

    write_outputs(
        output_dir=args.output_dir,
        slug=slug,
        date_str=date_str,
        markdown=markdown,
        json_data=json_data,
        sources=sources,
    )


if __name__ == "__main__":
    main()
