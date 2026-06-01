"""Unit tests for agent.py core utilities (dual-orchestrator CLI)."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent import (
    DEFAULT_FRAMEWORKS,
    OBJECT_TYPE_PRESETS,
    assess_corpus_adequacy,
    load_framework_docs,
    make_slug,
    resolve_analysis_model,
    resolve_frameworks,
    selected_analysis_backends,
)


# ── slug 工具 ───────────────────────────────────────────────────────────────


class TestMakeSlug:
    def test_english_name(self):
        assert make_slug("Dario Amodei") == "dario_amodei"

    def test_chinese_name_passthrough(self):
        result = make_slug("任正非")
        assert len(result) > 0
        assert "/" not in result
        assert " " not in result

    def test_multiple_spaces_collapsed(self):
        assert make_slug("Sam  Altman") == "sam_altman"

    def test_leading_trailing_stripped(self):
        assert make_slug("  Jensen Huang  ") == "jensen_huang"


# ── 语料充分性 ─────────────────────────────────────────────────────────────


class TestAssessCorpusAdequacy:
    def test_sufficient_with_3_ab_sources(self):
        sources = [{"grade": "A"}, {"grade": "A"}, {"grade": "B"}]
        assert assess_corpus_adequacy(sources) == "sufficient"

    def test_sparse_with_1_ab_source(self):
        sources = [{"grade": "B"}, {"grade": "C"}, {"grade": "D"}]
        assert assess_corpus_adequacy(sources) == "sparse"

    def test_insufficient_with_only_cd(self):
        assert assess_corpus_adequacy([{"grade": "C"}, {"grade": "D"}]) == "insufficient"

    def test_empty_corpus(self):
        assert assess_corpus_adequacy([]) == "insufficient"

    def test_exactly_3_ab_is_sufficient(self):
        sources = [{"grade": "A"}, {"grade": "B"}, {"grade": "A"}]
        assert assess_corpus_adequacy(sources) == "sufficient"

    def test_2_ab_is_sparse(self):
        assert assess_corpus_adequacy([{"grade": "A"}, {"grade": "B"}]) == "sparse"


# ── 框架选择器 ─────────────────────────────────────────────────────────────


class TestResolveFrameworks:
    def test_default_when_nothing_passed(self):
        assert resolve_frameworks(None, None) == DEFAULT_FRAMEWORKS

    def test_explicit_list(self):
        result = resolve_frameworks("core,big5,loc,lta", None)
        assert result == ["core", "big5", "loc", "lta"]

    def test_core_always_first(self):
        result = resolve_frameworks("lta,operational-code,core,big5", None)
        assert result[0] == "core"

    def test_all_excludes_dark_triad(self):
        result = resolve_frameworks("all", None)
        assert "dark-triad" not in result
        assert "core" in result
        assert "ems" in result

    def test_all_plus_dark_triad_includes_it(self):
        result = resolve_frameworks("all+dark-triad", None)
        assert "dark-triad" in result

    def test_unknown_framework_raises(self):
        with pytest.raises(ValueError, match="未知框架"):
            resolve_frameworks("core,fake_framework", None)

    def test_object_type_business_preset(self):
        result = resolve_frameworks(None, "business")
        assert result == OBJECT_TYPE_PRESETS["business"]

    def test_object_type_political_includes_operational_code(self):
        result = resolve_frameworks(None, "political")
        assert "operational-code" in result
        assert "lta" in result

    def test_explicit_overrides_object_type(self):
        result = resolve_frameworks("core", "political")
        assert result == ["core"]

    def test_case_insensitive(self):
        result = resolve_frameworks("CORE,Big5,LoC", None)
        assert result == ["core", "big5", "loc"]

    def test_unknown_object_type_raises(self):
        with pytest.raises(ValueError, match="未知 object_type"):
            resolve_frameworks(None, "astronaut")


class TestLoadFrameworkDocs:
    def test_loads_existing_framework(self, tmp_path):
        fw_dir = tmp_path / "references" / "frameworks"
        fw_dir.mkdir(parents=True)
        (fw_dir / "core.md").write_text("CORE CONTENT", encoding="utf-8")

        result = load_framework_docs(["core"], tmp_path)
        assert "CORE CONTENT" in result
        assert "框架：core" in result

    def test_multiple_frameworks_concatenated(self, tmp_path):
        fw_dir = tmp_path / "references" / "frameworks"
        fw_dir.mkdir(parents=True)
        (fw_dir / "core.md").write_text("CORE", encoding="utf-8")
        (fw_dir / "big5.md").write_text("BIG5", encoding="utf-8")

        result = load_framework_docs(["core", "big5"], tmp_path)
        assert "CORE" in result
        assert "BIG5" in result
        assert result.index("CORE") < result.index("BIG5")

    def test_missing_framework_file_skipped(self, tmp_path, capsys):
        fw_dir = tmp_path / "references" / "frameworks"
        fw_dir.mkdir(parents=True)
        (fw_dir / "core.md").write_text("CORE", encoding="utf-8")

        result = load_framework_docs(["core", "missing"], tmp_path)
        assert "CORE" in result
        captured = capsys.readouterr()
        assert "missing" in captured.err.lower()


class TestAnalysisBackendSelection:
    def test_single_backend_selection(self):
        assert selected_analysis_backends("claude") == ["claude"]
        assert selected_analysis_backends("codex") == ["codex"]

    def test_both_backend_selection(self):
        assert selected_analysis_backends("both") == ["claude", "codex"]

    def test_default_claude_model(self):
        assert resolve_analysis_model("claude", None, None, None) == "claude-sonnet-4-6"

    def test_codex_uses_cli_default_without_model(self):
        assert resolve_analysis_model("codex", None, None, None) is None

    def test_generic_model_applies_to_single_backend(self):
        assert resolve_analysis_model("codex", "gpt-test", None, None) == "gpt-test"

    def test_backend_specific_model_wins(self):
        assert resolve_analysis_model("claude", "generic", "sonnet", None) == "sonnet"
        assert resolve_analysis_model("codex", "generic", None, "gpt-test") == "gpt-test"


class TestSkipAcquisitionRequiresCorpus:
    """`--skip-acquisition` without `--corpus` (or `--identity`) is a footgun:
    the run reaches '没有任何可用语料' after Phase 0 and exits. Catch it at
    arg-parse time so the user gets a fast, clear error instead."""

    def _run_main(self, args, monkeypatch):
        from agent import agent as agent_mod
        monkeypatch.setattr(sys, "argv", ["agent.py", *args])
        return agent_mod.main()

    def test_skip_acquisition_without_corpus_errors(self, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run_main(
                ["--person", "Sam Altman", "--skip-acquisition"],
                monkeypatch,
            )
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "--skip-acquisition" in captured.err
        assert "--corpus" in captured.err

    def test_skip_acquisition_with_corpus_does_not_error_at_parse(
        self, monkeypatch, tmp_path, capsys
    ):
        corpus = tmp_path / "c.txt"
        corpus.write_text("local content", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "agent.py", "--person", "x",
            "--skip-acquisition", "--corpus", str(corpus),
            "--analysis-backend", "claude",
        ])
        # We don't want to actually call claude — patch the runner.
        from unittest.mock import patch as _patch
        with _patch("agent.agent.run_analysis") as mock_run:
            mock_run.return_value = ("md", None)
            from agent import agent as agent_mod
            agent_mod.main()
        # If we got here, parse-time validation accepted the combo.
