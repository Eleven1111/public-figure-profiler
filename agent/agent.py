#!/usr/bin/env python3
"""Public Figure Profiler — Dual-Orchestrator Agent CLI.

Phase 0: Qwen 3.5 synthesizes a Bio identity anchor from initial web search.
Phase 1: Qwen 3.5 drives a tool-calling acquisition loop across 8+ platforms.
Phase 2: claude CLI (claude-sonnet-4-6) performs the psychological analysis.

Usage:
  python -m agent.agent --person "Dario Amodei" --mode deep --purpose "投资尽调"
  python -m agent.agent --person "任正非" --skip-audio --object-type business
  python -m agent.agent --person "李飞飞" --platforms web,youtube,bilibili
  python -m agent.agent --person "Obama" --identity '{"name_variants":["Obama"]}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from .acquisition.artifacts import ArtifactStore, Artifact
from .acquisition.identity import synthesize_bio
from .acquisition.loop import AcquisitionLoop
from .acquisition.tools.search import search_web
from .analysis.prompt import build_prompt
from .analysis.runner import run_analysis


ALL_FRAMEWORKS = [
    "core", "big5", "loc", "cit", "lta", "operational-code", "ems", "dark-triad",
]
DEFAULT_FRAMEWORKS = ["core", "big5", "loc", "cit"]
OBJECT_TYPE_PRESETS: dict[str, list[str]] = {
    "business": ["core", "big5", "loc", "cit", "lta"],
    "political": ["core", "big5", "loc", "cit", "lta", "operational-code"],
    "scholar": ["core", "big5", "loc", "cit"],
    "artist": ["core", "big5", "loc", "cit"],
    "general": DEFAULT_FRAMEWORKS,
}


def resolve_frameworks(raw: str | None, object_type: str | None) -> list[str]:
    if raw:
        token = raw.strip().lower()
        if token == "all":
            return [f for f in ALL_FRAMEWORKS if f != "dark-triad"]
        if token == "all+dark-triad":
            return list(ALL_FRAMEWORKS)
        requested = [f.strip() for f in token.split(",") if f.strip()]
        invalid = [f for f in requested if f not in ALL_FRAMEWORKS]
        if invalid:
            raise ValueError(f"未知框架：{invalid}。支持：{ALL_FRAMEWORKS}")
        ordered = []
        if "core" in requested:
            ordered.append("core")
        for f in requested:
            if f != "core" and f not in ordered:
                ordered.append(f)
        return ordered
    if object_type:
        preset = OBJECT_TYPE_PRESETS.get(object_type.lower())
        if preset is None:
            raise ValueError(f"未知 object_type: {object_type}")
        return list(preset)
    return list(DEFAULT_FRAMEWORKS)


def make_slug(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^\w\s一-鿿]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug.strip("_")


def assess_corpus_adequacy(sources: list[dict]) -> str:
    ab_count = sum(1 for s in sources if s.get("grade") in ("A", "B"))
    if ab_count >= 3:
        return "sufficient"
    if ab_count >= 1:
        return "sparse"
    return "insufficient"


def load_framework_docs(frameworks: list[str], base_dir: Path) -> str:
    fw_dir = base_dir / "references" / "frameworks"
    chunks = []
    for fw in frameworks:
        path = fw_dir / f"{fw}.md"
        if not path.exists():
            print(f"Warning: framework file missing: {path}", file=sys.stderr)
            continue
        chunks.append(f"## 框架：{fw}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(chunks)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Public Figure Profiler — Dual-Orchestrator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--person", required=True, help="分析对象姓名")
    parser.add_argument("--purpose", default="general research", help="分析目的")
    parser.add_argument("--mode", choices=["quick", "deep"], default="deep")
    parser.add_argument("--frameworks", default=None, metavar="LIST")
    parser.add_argument("--object-type", choices=list(OBJECT_TYPE_PRESETS), default=None)

    # Identity override
    parser.add_argument(
        "--identity", default=None, metavar="JSON_OR_FILE",
        help="跳过 Phase 0，直接提供 Bio JSON 字符串或文件路径",
    )

    # Acquisition controls
    parser.add_argument("--max-iterations", type=int, default=25)
    parser.add_argument("--min-ab-sources", type=int, default=5)
    parser.add_argument("--skip-audio", action="store_true", help="跳过音频下载和转录")
    parser.add_argument(
        "--corpus", action="append", default=[], metavar="FILE",
        help="手动提供语料文件（A 级，可多次）",
    )

    # Analysis
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Claude 模型")
    parser.add_argument("--output-dir", default="./profiles")
    parser.add_argument("--artifacts-dir", default="./artifacts")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    agent_md_path = base / "agent" / "AGENT.md"
    schema_path = base / "references" / "output-schema.md"

    for p in [agent_md_path, schema_path]:
        if not p.exists():
            print(f"Error: required file not found: {p}", file=sys.stderr)
            sys.exit(1)

    try:
        frameworks = resolve_frameworks(args.frameworks, args.object_type)
    except ValueError as e:
        parser.error(str(e))

    print(f"[init] 激活框架: {', '.join(frameworks)}", file=sys.stderr)

    slug = make_slug(args.person)
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    run_dir = Path(args.artifacts_dir) / f"{slug}_{date_str}"
    store = ArtifactStore(run_dir)

    # ── Phase 0: Identity anchor ─────────────────────────────────────────────
    if args.identity:
        try:
            if Path(args.identity).exists():
                bio = json.loads(Path(args.identity).read_text())
            else:
                bio = json.loads(args.identity)
        except Exception as e:
            parser.error(f"--identity 解析失败: {e}")
        print("[phase0] 使用用户提供的 Bio", file=sys.stderr)
    else:
        print(f"[phase0] 合成 {args.person} 的 Bio 身份锚点...", file=sys.stderr)
        init_results = search_web(f"{args.person} biography career", num_results=5)
        init_results += search_web(f"{args.person} 简介 职业", num_results=5)
        bio = synthesize_bio(args.person, init_results)

    bio_path = run_dir / "bio_anchor.json"
    bio_path.write_text(json.dumps(bio, ensure_ascii=False, indent=2))
    print(f"[phase0] Bio: {bio.get('disambiguation', '')}", file=sys.stderr)

    # ── User-provided corpus (A grade) ────────────────────────────────────────
    for corpus_path in args.corpus:
        p = Path(corpus_path)
        if not p.exists():
            print(f"Warning: corpus file not found: {p}", file=sys.stderr)
            continue
        content = p.read_text(encoding="utf-8")
        sid = store.next_source_id()
        store.save(Artifact(
            source_id=sid, tool="user_file", platform="user",
            url="", title=p.name, content=content,
            grade="A", relevance_score=10.0, word_count=len(content.split()),
            language="zh" if any("一" <= c <= "鿿" for c in content[:100]) else "en",
            published_date="",
        ))

    # ── Phase 1: Qwen acquisition agent loop ─────────────────────────────────
    print(f"[phase1] 启动采集 agent（max_iterations={args.max_iterations}）...", file=sys.stderr)
    loop = AcquisitionLoop(args.person, bio, store)
    corpus_sources = loop.run(
        max_iterations=args.max_iterations,
        min_ab=args.min_ab_sources,
        min_total=10,
        skip_audio=args.skip_audio,
    )

    if not corpus_sources:
        print("Error: 没有任何可用语料，终止分析。", file=sys.stderr)
        sys.exit(2)

    adequacy = assess_corpus_adequacy(corpus_sources)
    ab_count = sum(1 for s in corpus_sources if s.get("grade") in ("A", "B"))
    print(
        f"[corpus] 充分性: {adequacy} (A/B={ab_count}, 总={len(corpus_sources)})",
        file=sys.stderr,
    )

    # ── Phase 2: Claude analysis ──────────────────────────────────────────────
    agent_md = agent_md_path.read_text(encoding="utf-8")
    output_schema = schema_path.read_text(encoding="utf-8")
    framework_docs = load_framework_docs(frameworks, base)

    prompt = build_prompt(
        person=args.person,
        purpose=args.purpose,
        mode=args.mode,
        frameworks=frameworks,
        corpus_sources=corpus_sources,
        adequacy=adequacy,
        agent_md=agent_md,
        framework_docs=framework_docs,
        output_schema=output_schema,
    )

    print(
        f"[phase2] 调用 claude --model {args.model}（语料 {len(prompt):,} chars）...",
        file=sys.stderr,
    )

    run_analysis(
        prompt_text=prompt,
        model=args.model,
        output_dir=Path(args.output_dir),
        slug=slug,
        date_str=date_str,
    )

    print(f"✓ Artifacts: {run_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
