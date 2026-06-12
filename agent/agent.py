#!/usr/bin/env python3
"""Public Figure Profiler — Dual-Orchestrator Agent CLI.

Phase 0: Qwen 3.5 synthesizes a Bio identity anchor from initial web search.
Phase 1: Qwen 3.5 drives a tool-calling acquisition loop across 8+ platforms.
Phase 2: Claude Code and/or Codex CLI performs the psychological analysis.

Usage:
  python -m agent.agent --person "Dario Amodei" --mode deep --purpose "投资尽调"
  python -m agent.agent --person "任正非" --skip-audio --object-type business
  python -m agent.agent --person "李飞飞" --analysis-backend codex
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
from .analysis.markers import markers_summary
from .analysis.prompt import build_prompt
from .analysis.runner import DEFAULT_CLAUDE_MODEL, AnalysisBackend, run_analysis
from .analysis.verify import verify_report
from .corpus.dedupe import independent_ab_count, mark_syndication
from .dossier import update_dossier


ALL_FRAMEWORKS = [
    "core", "big5", "loc", "cit", "lta", "operational-code",
    "motives", "values-hierarchy", "interests",
    "ems", "dark-triad",
]
DEFAULT_FRAMEWORKS = ["core", "big5", "loc", "cit", "motives", "values-hierarchy"]
ANALYSIS_BACKENDS = ("claude", "codex", "both")
OBJECT_TYPE_PRESETS: dict[str, list[str]] = {
    "business": [
        "core", "big5", "loc", "cit", "lta",
        "motives", "values-hierarchy", "interests",
    ],
    "political": [
        "core", "big5", "loc", "cit", "lta", "operational-code",
        "motives", "values-hierarchy", "interests",
    ],
    "scholar": DEFAULT_FRAMEWORKS,
    "artist": DEFAULT_FRAMEWORKS,
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
    """充分性按独立来源数判定：转载/同源分发只算 1 个独立来源。"""
    mark_syndication(sources)
    ab_count = independent_ab_count(sources)
    if ab_count >= 3:
        return "sufficient"
    if ab_count >= 1:
        return "sparse"
    return "insufficient"


def selected_analysis_backends(raw: str) -> list[AnalysisBackend]:
    """Resolve CLI backend selection into concrete backends."""
    if raw == "both":
        return ["claude", "codex"]
    if raw == "claude":
        return ["claude"]
    if raw == "codex":
        return ["codex"]
    raise ValueError(f"unsupported analysis backend: {raw}")


def resolve_analysis_model(
    backend: AnalysisBackend,
    generic_model: str | None,
    claude_model: str | None,
    codex_model: str | None,
    multi_backend: bool = False,
) -> str | None:
    """Return the model to pass to a backend CLI."""
    if backend == "claude":
        return (
            claude_model
            or (None if multi_backend else generic_model)
            or DEFAULT_CLAUDE_MODEL
        )
    if backend == "codex":
        return codex_model or (None if multi_backend else generic_model)
    raise ValueError(f"unsupported analysis backend: {backend}")


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
    parser.add_argument(
        "--skip-acquisition",
        action="store_true",
        help="跳过 Qwen 采集循环，仅使用 --corpus 提供的本地语料",
    )
    parser.add_argument("--skip-audio", action="store_true", help="跳过音频下载和转录")
    parser.add_argument(
        "--corpus", action="append", default=[], metavar="FILE",
        help="手动提供语料文件（A 级，可多次）",
    )

    # Analysis
    parser.add_argument(
        "--analysis-backend",
        choices=ANALYSIS_BACKENDS,
        default="claude",
        help="分析后端：claude、codex，或 both 分别运行两者",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="单一分析后端的模型名；both 模式请使用 --claude-model/--codex-model",
    )
    parser.add_argument("--claude-model", default=None, help="Claude Code 分析模型")
    parser.add_argument("--codex-model", default=None, help="Codex CLI 分析模型")
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

    if args.analysis_backend == "both" and args.model:
        parser.error("both 模式下请使用 --claude-model 和/或 --codex-model，不要使用 --model")

    if args.skip_acquisition and not args.corpus:
        parser.error(
            "--skip-acquisition 必须搭配 --corpus 至少一份本地语料文件 "
            "（否则没有任何可分析的内容）。例：--skip-acquisition --corpus ./interview.txt"
        )

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
    elif args.skip_acquisition:
        bio = {
            "name_variants": [args.person],
            "occupations": [],
            "orgs": [],
            "known_for": [],
            "disambiguation": f"目标人物：{args.person}",
        }
        print("[phase0] 跳过采集，使用最简 Bio", file=sys.stderr)
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
    if args.skip_acquisition:
        print("[phase1] 跳过采集 agent，仅使用本地语料", file=sys.stderr)
        corpus_sources = store.to_corpus_dicts()
    else:
        print(f"[phase1] 启动采集 agent（max_iterations={args.max_iterations}）...", file=sys.stderr)
        loop = AcquisitionLoop(args.person, bio, store)
        try:
            corpus_sources = loop.run(
                max_iterations=args.max_iterations,
                min_ab=args.min_ab_sources,
                min_total=10,
                skip_audio=args.skip_audio,
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(2)

    if not corpus_sources:
        print("Error: 没有任何可用语料，终止分析。", file=sys.stderr)
        sys.exit(2)

    adequacy = assess_corpus_adequacy(corpus_sources)
    ab_count = sum(1 for s in corpus_sources if s.get("grade") in ("A", "B"))
    ind_ab = independent_ab_count(corpus_sources)
    syndicated = sum(1 for s in corpus_sources if s.get("syndication_of"))
    print(
        f"[corpus] 充分性: {adequacy} (独立A/B={ind_ab}, 原始A/B={ab_count}, "
        f"转载/同源={syndicated}, 总={len(corpus_sources)})",
        file=sys.stderr,
    )

    # ── Phase 2: CLI analysis ────────────────────────────────────────────────
    agent_md = agent_md_path.read_text(encoding="utf-8")
    output_schema = schema_path.read_text(encoding="utf-8")
    framework_docs = load_framework_docs(frameworks, base)

    markers_block = markers_summary(corpus_sources)

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
        markers_block=markers_block,
    )

    backends = selected_analysis_backends(args.analysis_backend)
    multi_backend = len(backends) > 1
    for backend in backends:
        model = resolve_analysis_model(
            backend=backend,
            generic_model=args.model,
            claude_model=args.claude_model,
            codex_model=args.codex_model,
            multi_backend=multi_backend,
        )
        model_label = model or "default"
        print(
            f"[phase2] 调用 {backend} 分析后端（model={model_label}, "
            f"语料 {len(prompt):,} chars）...",
            file=sys.stderr,
        )

        suffix = backend if multi_backend else ""
        markdown, json_data = run_analysis(
            prompt_text=prompt,
            backend=backend,
            model=model,
            output_dir=Path(args.output_dir),
            slug=slug,
            date_str=date_str,
            output_suffix=suffix,
        )

        # ── Phase 2.5: 引文真实性校验 ────────────────────────────────────────
        verification = verify_report(markdown, corpus_sources)
        suffix_part = f"_{suffix}" if suffix else ""
        verify_path = (
            Path(args.output_dir) / f"{slug}_{date_str}{suffix_part}.verification.md"
        )
        verify_path.write_text(verification.to_markdown(), encoding="utf-8")
        print(
            f"[verify] 引证 {verification.total} 条，通过率 {verification.pass_rate:.1%} "
            f"(未验证 {verification.count('unverified')}, "
            f"来源不存在 {verification.count('unknown_source')}) → {verify_path}",
            file=sys.stderr,
        )

        # ── Phase 3: 人物档案库沉淀 ──────────────────────────────────────────
        if json_data:
            try:
                dossier_dir = update_dossier(
                    person=args.person,
                    slug=slug,
                    report_json=json.loads(json_data),
                    date_str=date_str,
                    backend_suffix=suffix,
                )
                print(f"[dossier] 档案已更新: {dossier_dir}/", file=sys.stderr)
            except Exception as exc:
                print(f"[dossier] 档案更新失败（不影响报告）: {exc}", file=sys.stderr)

    print(f"✓ Artifacts: {run_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
