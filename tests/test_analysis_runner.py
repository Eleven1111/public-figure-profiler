import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path
from agent.analysis.runner import run_analysis
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
            model="claude-sonnet-4-6",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
        )

    call_args = mock_run.call_args
    assert "claude" in call_args[0][0]
    assert "--model" in call_args[0][0]
    assert "claude-sonnet-4-6" in call_args[0][0]

def test_run_analysis_writes_output_file(tmp_path):
    mock_result = MagicMock()
    mock_result.stdout = "# Profile\n\nAnalysis text.\n"
    mock_result.returncode = 0

    with patch("agent.analysis.runner.subprocess.run", return_value=mock_result):
        run_analysis(
            prompt_text="Test prompt",
            model="claude-sonnet-4-6",
            output_dir=tmp_path,
            slug="test",
            date_str="20260423",
        )

    output_file = tmp_path / "test_20260423.md"
    assert output_file.exists()
    assert "Analysis text." in output_file.read_text()
