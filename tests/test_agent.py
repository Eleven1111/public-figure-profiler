"""Unit tests for agent.py core utilities."""

import json
import tempfile
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent import make_slug, load_user_corpus, assess_corpus_adequacy


class TestMakeSlug:
    def test_english_name(self):
        assert make_slug("Dario Amodei") == "dario_amodei"

    def test_chinese_name_passthrough(self):
        # 中文字符保留，仅做安全处理
        result = make_slug("任正非")
        assert len(result) > 0
        assert "/" not in result
        assert " " not in result

    def test_special_characters_removed(self):
        assert make_slug("Mary O'Brien Jr.") == "mary_obrien_jr"

    def test_multiple_spaces_collapsed(self):
        assert make_slug("Sam  Altman") == "sam_altman"

    def test_leading_trailing_stripped(self):
        assert make_slug("  Jensen Huang  ") == "jensen_huang"


class TestLoadUserCorpus:
    def test_loads_text_file(self, tmp_path):
        corpus_file = tmp_path / "interview.txt"
        corpus_file.write_text("This is an interview transcript.", encoding="utf-8")

        sources = load_user_corpus([str(corpus_file)])

        assert len(sources) == 1
        assert sources[0]["content"] == "This is an interview transcript."
        assert sources[0]["grade"] == "A"
        assert sources[0]["word_count"] == 5

    def test_missing_file_skipped_with_warning(self, capsys):
        sources = load_user_corpus(["/nonexistent/path.txt"])
        assert sources == []
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "warning" in captured.err.lower()

    def test_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("Content A", encoding="utf-8")
        f2.write_text("Content B", encoding="utf-8")

        sources = load_user_corpus([str(f1), str(f2)])
        assert len(sources) == 2

    def test_empty_paths_list(self):
        assert load_user_corpus([]) == []


class TestAssessCorpusAdequacy:
    def test_sufficient_with_3_ab_sources(self):
        sources = [
            {"grade": "A"}, {"grade": "A"}, {"grade": "B"},
        ]
        assert assess_corpus_adequacy(sources) == "sufficient"

    def test_sparse_with_1_ab_source(self):
        sources = [{"grade": "B"}, {"grade": "C"}, {"grade": "D"}]
        assert assess_corpus_adequacy(sources) == "sparse"

    def test_insufficient_with_only_cd(self):
        sources = [{"grade": "C"}, {"grade": "D"}]
        assert assess_corpus_adequacy(sources) == "insufficient"

    def test_empty_corpus(self):
        assert assess_corpus_adequacy([]) == "insufficient"

    def test_exactly_3_ab_is_sufficient(self):
        sources = [{"grade": "A"}, {"grade": "B"}, {"grade": "A"}]
        assert assess_corpus_adequacy(sources) == "sufficient"

    def test_2_ab_is_sparse(self):
        sources = [{"grade": "A"}, {"grade": "B"}]
        assert assess_corpus_adequacy(sources) == "sparse"


class TestFetchYoutubeTranscript:
    def _make_fetched_mock(self, mocker, raw_data):
        """Helper: create a mock FetchedTranscript that returns raw_data."""
        fetched_mock = mocker.MagicMock()
        fetched_mock.to_raw_data.return_value = raw_data
        return fetched_mock

    def test_valid_youtube_url(self, mocker):
        raw_data = [
            {"text": "Hello world", "start": 0.0, "duration": 2.0},
            {"text": "This is a test", "start": 2.0, "duration": 3.0},
        ]
        fetched_mock = self._make_fetched_mock(mocker, raw_data)
        mocker.patch(
            "agent.agent.YouTubeTranscriptApi.fetch",
            return_value=fetched_mock,
        )

        from agent.agent import fetch_youtube_transcript
        result = fetch_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert result == "Hello world This is a test"

    def test_youtu_be_short_url(self, mocker):
        raw_data = [{"text": "Short URL works", "start": 0.0, "duration": 1.0}]
        fetched_mock = self._make_fetched_mock(mocker, raw_data)
        mocker.patch(
            "agent.agent.YouTubeTranscriptApi.fetch",
            return_value=fetched_mock,
        )

        from agent.agent import fetch_youtube_transcript
        result = fetch_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")

        assert result == "Short URL works"

    def test_non_youtube_url_returns_none(self):
        from agent.agent import fetch_youtube_transcript
        result = fetch_youtube_transcript("https://example.com/not-youtube")
        assert result is None

    def test_api_failure_returns_none(self, mocker):
        mocker.patch(
            "agent.agent.YouTubeTranscriptApi.fetch",
            side_effect=Exception("Transcript not available"),
        )

        from agent.agent import fetch_youtube_transcript
        result = fetch_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is None


class TestBuildSystemPrompt:
    def test_combines_three_sections(self):
        from agent.agent import build_system_prompt

        result = build_system_prompt(
            agent_md="AGENT INSTRUCTIONS",
            codebook="CODEBOOK CONTENT",
            output_schema="OUTPUT SCHEMA",
        )

        assert "AGENT INSTRUCTIONS" in result
        assert "CODEBOOK CONTENT" in result
        assert "OUTPUT SCHEMA" in result

    def test_sections_separated(self):
        from agent.agent import build_system_prompt

        result = build_system_prompt("A", "B", "C")
        # 三个部分之间应有分隔
        assert result.index("A") < result.index("B") < result.index("C")


class TestWriteOutputs:
    def test_writes_markdown_file(self, tmp_path):
        from agent.agent import write_outputs

        write_outputs(
            output_dir=str(tmp_path),
            slug="test_person",
            date_str="20260415",
            markdown="# Test Report\n\nContent here.",
            json_data=None,
            sources=[],
        )

        md_file = tmp_path / "test_person_20260415.md"
        assert md_file.exists()
        assert md_file.read_text() == "# Test Report\n\nContent here."

    def test_writes_json_file_when_provided(self, tmp_path):
        from agent.agent import write_outputs

        json_str = '{"subject": "Test Person"}'
        write_outputs(
            output_dir=str(tmp_path),
            slug="test_person",
            date_str="20260415",
            markdown="# Report",
            json_data=json_str,
            sources=[],
        )

        json_file = tmp_path / "test_person_20260415.json"
        assert json_file.exists()
        assert json_file.read_text() == json_str

    def test_no_json_file_when_none(self, tmp_path):
        from agent.agent import write_outputs

        write_outputs(
            output_dir=str(tmp_path),
            slug="p",
            date_str="20260415",
            markdown="# R",
            json_data=None,
            sources=[],
        )

        assert not (tmp_path / "p_20260415.json").exists()

    def test_creates_corpus_manifest(self, tmp_path):
        from agent.agent import write_outputs

        sources = [
            {"grade": "A", "source": "https://example.com", "content": "text", "word_count": 1},
        ]
        write_outputs(
            output_dir=str(tmp_path),
            slug="p",
            date_str="20260415",
            markdown="# R",
            json_data=None,
            sources=sources,
        )

        corpus_dir = tmp_path / "p_20260415_corpus"
        assert corpus_dir.exists()
        manifest = json.loads((corpus_dir / "corpus_manifest.json").read_text())
        assert len(manifest) == 1
        assert manifest[0]["grade"] == "A"

    def test_creates_output_dir_if_not_exists(self, tmp_path):
        from agent.agent import write_outputs

        new_dir = tmp_path / "new" / "nested" / "dir"
        write_outputs(
            output_dir=str(new_dir),
            slug="p",
            date_str="20260415",
            markdown="# R",
            json_data=None,
            sources=[],
        )

        assert (new_dir / "p_20260415.md").exists()


class TestExtractJsonFromResponse:
    def test_extracts_json_block(self):
        from agent.agent import extract_json_from_response

        text = 'Some analysis text.\n\n```json\n{"subject": "Test"}\n```\n\nMore text.'
        markdown, json_data = extract_json_from_response(text)

        assert json_data == '{"subject": "Test"}'
        assert "```json" not in markdown
        assert "Some analysis text." in markdown

    def test_no_json_block_returns_none(self):
        from agent.agent import extract_json_from_response

        text = "Analysis without JSON block."
        markdown, json_data = extract_json_from_response(text)

        assert json_data is None
        assert markdown == "Analysis without JSON block."


# ── 多 Provider API 集成测试 ───────────────────────────────────────────────


class TestBuildUserMessage:
    """build_user_message 应与 API 无关，只做字符串组装。"""

    def test_contains_person_name(self):
        from agent.agent import build_user_message

        msg = build_user_message("Jensen Huang", "投资尽调", "deep", [], "insufficient")
        assert "Jensen Huang" in msg

    def test_contains_purpose(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "竞争对手研究", "deep", [], "sufficient")
        assert "竞争对手研究" in msg

    def test_deep_mode_label(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "Y", "deep", [], "sufficient")
        assert "DEEP MODE" in msg

    def test_quick_mode_label(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "Y", "quick", [], "sufficient")
        assert "QUICK MODE" in msg

    def test_sparse_adequacy_warning(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "Y", "deep", [], "sparse")
        assert "语料偏少" in msg

    def test_insufficient_adequacy_warning(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "Y", "deep", [], "insufficient")
        assert "探索性草稿" in msg

    def test_sufficient_no_warning(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "Y", "deep", [], "sufficient")
        assert "语料偏少" not in msg
        assert "探索性草稿" not in msg

    def test_corpus_sources_included(self):
        from agent.agent import build_user_message

        sources = [{"grade": "A", "source": "https://example.com", "content": "transcript text"}]
        msg = build_user_message("X", "Y", "deep", sources, "sufficient")
        assert "transcript text" in msg
        assert "等级: A" in msg

    def test_empty_corpus_placeholder(self):
        from agent.agent import build_user_message

        msg = build_user_message("X", "Y", "deep", [], "insufficient")
        assert "WebSearch" in msg


class TestCallAnthropicAPI:
    """call_anthropic 应正确调用 Anthropic SDK 并返回文本。"""

    def test_returns_text_from_response(self, mocker):
        from agent.agent import call_anthropic

        mock_response = mocker.MagicMock()
        mock_response.content = [mocker.MagicMock(text="Analysis result")]
        mock_client = mocker.MagicMock()
        mock_client.messages.create.return_value = mock_response
        mocker.patch("agent.agent.anthropic.Anthropic", return_value=mock_client)

        result = call_anthropic("system", "user msg", "claude-opus-4-6")

        assert result == "Analysis result"

    def test_passes_correct_model(self, mocker):
        from agent.agent import call_anthropic

        mock_response = mocker.MagicMock()
        mock_response.content = [mocker.MagicMock(text="ok")]
        mock_client = mocker.MagicMock()
        mock_client.messages.create.return_value = mock_response
        mocker.patch("agent.agent.anthropic.Anthropic", return_value=mock_client)

        call_anthropic("sys", "usr", "claude-haiku-4-5-20251001")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"

    def test_passes_system_and_user(self, mocker):
        from agent.agent import call_anthropic

        mock_response = mocker.MagicMock()
        mock_response.content = [mocker.MagicMock(text="ok")]
        mock_client = mocker.MagicMock()
        mock_client.messages.create.return_value = mock_response
        mocker.patch("agent.agent.anthropic.Anthropic", return_value=mock_client)

        call_anthropic("MY SYSTEM", "MY USER", "claude-opus-4-6")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == "MY SYSTEM"
        assert call_kwargs.kwargs["messages"][0]["content"] == "MY USER"


class TestCallOpenAICompatibleAPI:
    """call_openai_compatible 应正确调用 OpenAI SDK，支持官方和自定义 base_url。"""

    def _make_mock_openai(self, mocker, text="OpenAI result"):
        mock_message = mocker.MagicMock()
        mock_message.content = text
        mock_choice = mocker.MagicMock()
        mock_choice.message = mock_message
        mock_response = mocker.MagicMock()
        mock_response.choices = [mock_choice]
        mock_client = mocker.MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    def test_returns_text_from_response(self, mocker):
        from agent.agent import call_openai_compatible

        mock_client = self._make_mock_openai(mocker, "Result text")
        mock_openai_cls = mocker.patch("agent.agent.openai.OpenAI", return_value=mock_client)

        result = call_openai_compatible("system", "user", "gpt-4o", "sk-test")

        assert result == "Result text"

    def test_passes_base_url_to_client(self, mocker):
        from agent.agent import call_openai_compatible

        mock_client = self._make_mock_openai(mocker)
        mock_openai_cls = mocker.patch("agent.agent.openai.OpenAI", return_value=mock_client)

        call_openai_compatible(
            "sys", "usr", "deepseek-chat", "sk-key",
            base_url="https://api.deepseek.com/v1"
        )

        mock_openai_cls.assert_called_once_with(
            api_key="sk-key",
            base_url="https://api.deepseek.com/v1"
        )

    def test_no_base_url_passes_none(self, mocker):
        from agent.agent import call_openai_compatible

        mock_client = self._make_mock_openai(mocker)
        mock_openai_cls = mocker.patch("agent.agent.openai.OpenAI", return_value=mock_client)

        call_openai_compatible("sys", "usr", "gpt-4o", "sk-key")

        mock_openai_cls.assert_called_once_with(api_key="sk-key", base_url=None)

    def test_system_and_user_in_messages(self, mocker):
        from agent.agent import call_openai_compatible

        mock_client = self._make_mock_openai(mocker)
        mocker.patch("agent.agent.openai.OpenAI", return_value=mock_client)

        call_openai_compatible("SYS", "USR", "gpt-4o", "key")

        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "SYS"}
        assert messages[1] == {"role": "user", "content": "USR"}


class TestRunAnalysisProviderDispatch:
    """run_analysis 应根据 provider 分发到正确的调用函数。"""

    def test_anthropic_provider_calls_call_anthropic(self, mocker):
        from agent.agent import run_analysis

        mock_call = mocker.patch(
            "agent.agent.call_anthropic", return_value="# Report\n```json\n{}\n```"
        )
        mocker.patch("agent.agent.build_user_message", return_value="user msg")

        run_analysis(
            person="X", purpose="Y", mode="deep",
            corpus_sources=[], adequacy="sufficient",
            system_prompt="sys", provider="anthropic",
        )

        mock_call.assert_called_once()

    def test_openai_provider_calls_call_openai_compatible(self, mocker):
        from agent.agent import run_analysis

        mock_call = mocker.patch(
            "agent.agent.call_openai_compatible", return_value="# Report"
        )
        mocker.patch("agent.agent.build_user_message", return_value="user msg")
        mocker.patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})

        run_analysis(
            person="X", purpose="Y", mode="quick",
            corpus_sources=[], adequacy="sufficient",
            system_prompt="sys", provider="openai",
        )

        mock_call.assert_called_once()
        _, kwargs = mock_call.call_args
        assert kwargs.get("base_url") is None

    def test_compatible_provider_passes_base_url(self, mocker):
        from agent.agent import run_analysis

        mock_call = mocker.patch(
            "agent.agent.call_openai_compatible", return_value="# Report"
        )
        mocker.patch("agent.agent.build_user_message", return_value="user msg")

        run_analysis(
            person="X", purpose="Y", mode="quick",
            corpus_sources=[], adequacy="sufficient",
            system_prompt="sys", provider="compatible",
            model="deepseek-chat",
            api_key="sk-ds",
            base_url="https://api.deepseek.com/v1",
        )

        mock_call.assert_called_once()
        _, kwargs = mock_call.call_args
        assert kwargs["base_url"] == "https://api.deepseek.com/v1"
        assert kwargs["api_key"] == "sk-ds"

    def test_default_anthropic_model_used_when_model_not_specified(self, mocker):
        from agent.agent import run_analysis, DEFAULT_MODELS

        mock_call = mocker.patch(
            "agent.agent.call_anthropic", return_value="# Report"
        )
        mocker.patch("agent.agent.build_user_message", return_value="msg")

        run_analysis(
            person="X", purpose="Y", mode="deep",
            corpus_sources=[], adequacy="sufficient",
            system_prompt="sys", provider="anthropic",
        )

        _, kwargs = mock_call.call_args
        assert kwargs["model"] == DEFAULT_MODELS["anthropic"]

    def test_compatible_provider_raises_without_model(self, mocker):
        from agent.agent import run_analysis

        mocker.patch("agent.agent.build_user_message", return_value="msg")

        with pytest.raises(ValueError, match="--model"):
            run_analysis(
                person="X", purpose="Y", mode="deep",
                corpus_sources=[], adequacy="sufficient",
                system_prompt="sys", provider="compatible",
                # no model specified — should raise
            )

    def test_unknown_provider_raises(self, mocker):
        from agent.agent import run_analysis

        mocker.patch("agent.agent.build_user_message", return_value="msg")

        with pytest.raises(ValueError, match="未知 provider"):
            run_analysis(
                person="X", purpose="Y", mode="deep",
                corpus_sources=[], adequacy="sufficient",
                system_prompt="sys", provider="unknown_provider",
                model="some-model",
            )
