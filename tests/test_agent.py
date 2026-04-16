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
