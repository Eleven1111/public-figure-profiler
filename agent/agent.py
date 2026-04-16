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
