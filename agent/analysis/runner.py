"""Run analysis by spawning an analysis CLI as subprocess."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal


AnalysisBackend = Literal["claude", "codex"]

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def run_analysis(
    prompt_text: str,
    backend: AnalysisBackend = "claude",
    model: str | None = None,
    output_dir: Path | None = None,
    slug: str = "",
    date_str: str = "",
    output_suffix: str = "",
) -> tuple[str, str | None]:
    """Spawn an analysis CLI subprocess, capture output, write files.

    Returns (markdown, json_or_none).
    The prompt is passed via stdin so there's no shell argument length limit.
    """
    if backend == "claude":
        full_text = _run_claude(prompt_text, model or DEFAULT_CLAUDE_MODEL)
    elif backend == "codex":
        full_text = _run_codex(prompt_text, model)
    else:
        raise ValueError(f"unsupported analysis backend: {backend}")

    markdown, json_data = _extract_json(full_text)

    if output_dir and slug and date_str:
        _write_outputs(
            Path(output_dir),
            slug,
            date_str,
            markdown,
            json_data,
            output_suffix,
            raw_text=full_text,
        )

    return markdown, json_data


def _run_claude(prompt_text: str, model: str) -> str:
    """Run Claude Code in non-interactive print mode."""
    print(
        f"[analysis] Calling claude --model {model} (corpus {len(prompt_text):,} chars)",
        file=sys.stderr,
    )

    try:
        result = subprocess.run(
            [
                "claude",
                "--model",
                model,
                "--mcp-config",
                '{"mcpServers":{}}',
                "--strict-mcp-config",
                "--disable-slash-commands",
                "--no-session-persistence",
                "-p",
            ],
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "claude CLI not found. Install Claude Code: https://claude.ai/code"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after 30 minutes")

    if result.returncode != 0:
        err = result.stderr[:500] or result.stdout[:500]
        raise RuntimeError(f"claude CLI exited {result.returncode}: {err}")

    return result.stdout


def _run_codex(prompt_text: str, model: str | None) -> str:
    """Run Codex CLI non-interactively and return its final message."""
    model_label = model or "default"
    print(
        f"[analysis] Calling codex exec --model {model_label} "
        f"(corpus {len(prompt_text):,} chars)",
        file=sys.stderr,
    )

    output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="profiler_codex_", suffix=".md", delete=False
        ) as tmp:
            output_path = Path(tmp.name)

        cmd = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.append("-")

        result = subprocess.run(
            cmd,
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except FileNotFoundError:
        raise RuntimeError("codex CLI not found. Install and authenticate Codex CLI.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("codex CLI timed out after 30 minutes")

    if result.returncode != 0:
        if output_path and output_path.exists():
            output_path.unlink(missing_ok=True)
        err = result.stderr[:500] or result.stdout[:500]
        raise RuntimeError(f"codex CLI exited {result.returncode}: {err}")

    if output_path and output_path.exists():
        try:
            final_text = output_path.read_text(encoding="utf-8").strip()
        finally:
            output_path.unlink(missing_ok=True)
        if final_text:
            return final_text

    return result.stdout


_JSON_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _extract_json(full_text: str) -> tuple[str, str | None]:
    """Pull the largest valid JSON fenced block out of the LLM output.

    The LLM occasionally emits multiple ```json fences (e.g. a small example
    block in addition to the final structured payload). Picking the largest
    parseable block — and removing only that one match from the markdown —
    keeps the narrative intact even when the model misorders sections.
    If no fenced block parses as JSON, return the text unchanged.
    """
    matches = list(_JSON_FENCE.finditer(full_text))
    best: re.Match[str] | None = None
    best_payload: str | None = None
    for m in matches:
        payload = m.group(1)
        try:
            json.loads(payload)
        except ValueError:
            continue
        if best is None or len(payload) > len(best_payload or ""):
            best = m
            best_payload = payload

    if best is None:
        return full_text, None

    markdown = (full_text[: best.start()] + full_text[best.end():]).strip()
    return markdown, best_payload


def _write_outputs(
    out: Path,
    slug: str,
    date_str: str,
    markdown: str,
    json_data: str | None,
    output_suffix: str = "",
    raw_text: str | None = None,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    suffix = f"_{output_suffix}" if output_suffix else ""

    if raw_text is not None:
        raw_path = out / f"{slug}_{date_str}{suffix}.raw.txt"
        raw_path.write_text(raw_text, encoding="utf-8")

    md_path = out / f"{slug}_{date_str}{suffix}.md"
    md_path.write_text(markdown, encoding="utf-8")
    print(f"✓ Report : {md_path}", file=sys.stderr)

    if raw_text and len(markdown) < 1024 and len(raw_text) > 4 * 1024:
        print(
            f"⚠️  markdown 报告异常短（{len(markdown)}B）但原始输出 "
            f"{len(raw_text):,}B，建议查阅 {md_path.with_suffix('.raw.txt').name} "
            "判断是否模型未按格式输出。",
            file=sys.stderr,
        )

    if json_data:
        json_path = out / f"{slug}_{date_str}{suffix}.json"
        json_path.write_text(json_data, encoding="utf-8")
        print(f"✓ JSON   : {json_path}", file=sys.stderr)
