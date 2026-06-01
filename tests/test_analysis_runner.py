import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path
from agent.analysis.runner import run_analysis, _extract_json
from agent.analysis.prompt import build_prompt

def test_build_prompt_includes_person_and_corpus():
    sources = [
        {"source_id": "S01", "grade": "A", "source": "youtube", "url": "https://yt.com",
         "title": "Interview", "content": "He said interesting things.", "published_date": "2024-01-01",
         "origin": "search_youtube", "word_count": 4, "language": "en"}
    ]
    prompt = build_prompt(
        person="Test Person",
        purpose="research",
        mode="deep",
        frameworks=["core", "big5"],
        corpus_sources=sources,
        adequacy="sufficient",
        agent_md="# AGENT\nDo analysis.",
        framework_docs="## core\nsome framework",
        output_schema="## Schema\noutput format",
    )
    assert "Test Person" in prompt
    assert "S01" in prompt
    assert "# AGENT" in prompt

def test_run_analysis_calls_claude_cli(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = "# Profile\n\nAnalysis text.\n"
    mock_result.returncode = 0

    with patch("agent.analysis.runner.subprocess.run", return_value=mock_result) as mock_run:
        run_analysis(
            prompt_text="Test prompt",
            backend="claude",
            model="claude-sonnet-4-6",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
        )

    call_args = mock_run.call_args
    assert "claude" in call_args[0][0]
    assert "--model" in call_args[0][0]
    assert "claude-sonnet-4-6" in call_args[0][0]

def test_run_analysis_calls_codex_cli(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = "# Profile\n\nCodex analysis.\n"
    mock_result.returncode = 0

    with patch("agent.analysis.runner.subprocess.run", return_value=mock_result) as mock_run:
        run_analysis(
            prompt_text="Test prompt",
            backend="codex",
            model="gpt-test",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
        )

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert cmd[:2] == ["codex", "exec"]
    assert "--model" in cmd
    assert "gpt-test" in cmd
    assert "--output-last-message" in cmd

def test_run_analysis_writes_output_file(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = "# Profile\n\nAnalysis text.\n"
    mock_result.returncode = 0

    with patch("agent.analysis.runner.subprocess.run", return_value=mock_result):
        run_analysis(
            prompt_text="Test prompt",
            backend="claude",
            model="claude-sonnet-4-6",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
        )

    output_file = tmp_path / "test_20260423.md"
    assert output_file.exists()
    assert "Analysis text." in output_file.read_text()

def test_run_analysis_writes_backend_suffix(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = "# Profile\n\nAnalysis text.\n"
    mock_result.returncode = 0

    with patch("agent.analysis.runner.subprocess.run", return_value=mock_result):
        run_analysis(
            prompt_text="Test prompt",
            backend="claude",
            model="claude-sonnet-4-6",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
            output_suffix="claude",
        )

    output_file = tmp_path / "test_20260423_claude.md"
    assert output_file.exists()


# ── _extract_json edge cases ──────────────────────────────────────────────────

def test_extract_json_basic_prose_then_json():
    text = (
        "# Report\n\nNarrative paragraph one.\n\n"
        "```json\n"
        '{"summary": "ok", "score": 1}\n'
        "```\n"
    )
    markdown, json_data = _extract_json(text)
    assert "Narrative paragraph one." in markdown
    assert "```json" not in markdown
    assert json_data is not None
    import json as _json
    assert _json.loads(json_data) == {"summary": "ok", "score": 1}


def test_extract_json_keeps_trailing_prose_when_json_first():
    text = (
        "```json\n"
        '{"a": 1}\n'
        "```\n\n"
        "---\n\n"
        "**结尾摘要：** 后续叙事。\n"
    )
    markdown, json_data = _extract_json(text)
    assert "结尾摘要" in markdown
    assert "```json" not in markdown
    import json as _json
    assert _json.loads(json_data) == {"a": 1}


def test_extract_json_picks_largest_valid_block_when_multiple():
    """When the LLM emits an example block plus a final report block, keep the
    largest valid JSON and preserve the rest of the prose (incl. example fences)."""
    text = (
        "# Report\n\n"
        "示例：\n"
        "```json\n"
        '{"example": true}\n'
        "```\n\n"
        "正文段落 …\n\n"
        "最终结构化数据：\n"
        "```json\n"
        '{"final": true, "items": [1, 2, 3, 4, 5]}\n'
        "```\n"
    )
    markdown, json_data = _extract_json(text)
    import json as _json
    parsed = _json.loads(json_data)
    assert parsed.get("final") is True
    assert "正文段落" in markdown
    # The largest block was removed; example block preserved as part of markdown
    assert '"example"' in markdown


def test_extract_json_ignores_invalid_json_block():
    """If the only ```json fence contains invalid JSON, do NOT truncate markdown."""
    text = (
        "# Report\n\n实际叙事内容很多。\n\n"
        "```json\n"
        '{"truncated":\n'  # invalid (incomplete)
        "```\n"
    )
    markdown, json_data = _extract_json(text)
    assert json_data is None
    # Markdown must not be empty — contain original prose
    assert "实际叙事内容很多" in markdown


def test_extract_json_no_json_block_returns_full_text():
    text = "# Report\n\nJust prose, no fences.\n"
    markdown, json_data = _extract_json(text)
    assert json_data is None
    assert markdown == text


def test_run_analysis_writes_raw_stdout_for_forensics(tmp_path):
    """Always preserve raw LLM stdout next to the .md so we can debug truncation."""
    raw = (
        "```json\n"
        '{"a": 1}\n'
        "```\n\n"
        "---\n\n"
        "**摘要：** xxx\n"
    )
    mock_result = MagicMock()
    mock_result.stdout = raw
    mock_result.returncode = 0
    with patch("agent.analysis.runner.subprocess.run", return_value=mock_result):
        run_analysis(
            prompt_text="Test prompt",
            backend="claude",
            model="claude-sonnet-4-6",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
        )
    raw_file = tmp_path / "test_20260423.raw.txt"
    assert raw_file.exists()
    assert raw_file.read_text() == raw
