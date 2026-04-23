"""Run analysis by spawning claude CLI as subprocess."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def run_analysis(
    prompt_text: str,
    model: str = "claude-sonnet-4-6",
    output_dir: Path | None = None,
    slug: str = "",
    date_str: str = "",
) -> tuple[str, str | None]:
    """Spawn claude CLI subprocess, capture output, write files.

    Returns (markdown, json_or_none).
    The prompt is passed via stdin so there's no shell argument length limit.
    """
    print(
        f"[analysis] Calling claude --model {model} (corpus {len(prompt_text):,} chars)",
        file=sys.stderr,
    )

    try:
        result = subprocess.run(
            ["claude", "--model", model, "-p"],
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "claude CLI not found. Install Claude Code: https://claude.ai/code"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after 10 minutes")

    if result.returncode != 0:
        err = result.stderr[:500]
        raise RuntimeError(f"claude CLI exited {result.returncode}: {err}")

    full_text = result.stdout
    markdown, json_data = _extract_json(full_text)

    if output_dir and slug and date_str:
        _write_outputs(Path(output_dir), slug, date_str, markdown, json_data)

    return markdown, json_data


def _extract_json(full_text: str) -> tuple[str, str | None]:
    json_match = re.search(r"```json\n(.*?)\n```", full_text, re.DOTALL)
    if not json_match:
        return full_text, None
    json_data = json_match.group(1)
    markdown = re.sub(r"```json\n.*?\n```", "", full_text, flags=re.DOTALL).strip()
    return markdown, json_data


def _write_outputs(
    out: Path, slug: str, date_str: str, markdown: str, json_data: str | None
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{slug}_{date_str}.md"
    md_path.write_text(markdown, encoding="utf-8")
    print(f"✓ Report : {md_path}", file=sys.stderr)

    if json_data:
        json_path = out / f"{slug}_{date_str}.json"
        json_path.write_text(json_data, encoding="utf-8")
        print(f"✓ JSON   : {json_path}", file=sys.stderr)
