#!/usr/bin/env python3
"""
Public Figure Profiler — Hermes Agent CLI

对任意公开人物进行心理侧写分析。
混合语料获取：用户提供 → WebSearch/WebFetch → YouTube 转录 → 音频转录（可选）。

用法：
  python -m agent.agent --person "Dario Amodei" --mode deep --purpose "投资尽调"
  python -m agent.agent --person "任正非" --mode quick --corpus interview.txt
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from youtube_transcript_api import YouTubeTranscriptApi


# ── 工具函数 ────────────────────────────────────────────────────────────────


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


def build_system_prompt(agent_md: str, codebook: str, output_schema: str) -> str:
    """将三个指令文件合并为 system prompt。"""
    return f"""{agent_md}

---

## 分析框架参考（codebook.md）

{codebook}

---

## 输出格式规范（output-schema.md）

{output_schema}
"""


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
