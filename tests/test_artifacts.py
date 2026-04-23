import json
import hashlib
from pathlib import Path
import pytest
from agent.acquisition.artifacts import Artifact, ArtifactStore

def test_save_creates_raw_file(tmp_path):
    store = ArtifactStore(tmp_path)
    art = Artifact(
        source_id="S01", tool="search_web", platform="web",
        url="https://example.com", title="Test", content="Hello world" * 50,
        grade="B", relevance_score=8.0, word_count=100,
        language="en", published_date="2024-01-01",
    )
    store.save(art)
    raw_files = list((tmp_path / "raw").iterdir())
    assert len(raw_files) == 1
    assert raw_files[0].read_text() == art.content

def test_save_computes_sha256(tmp_path):
    store = ArtifactStore(tmp_path)
    content = "test content"
    art = Artifact("S01", "search_web", "web", "", "", content, "C", 7.0, 2, "en", "")
    store.save(art)
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert art.sha256 == expected

def test_manifest_written(tmp_path):
    store = ArtifactStore(tmp_path)
    art = Artifact("S01", "search_web", "web", "", "", "content", "A", 9.0, 1, "en", "")
    store.save(art)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest) == 1
    assert manifest[0]["source_id"] == "S01"

def test_next_source_id_increments(tmp_path):
    store = ArtifactStore(tmp_path)
    assert store.next_source_id() == "S01"
    assert store.next_source_id() == "S02"
    assert store.next_source_id() == "S03"

def test_ab_count(tmp_path):
    store = ArtifactStore(tmp_path)
    for grade in ["A", "B", "C", "D", "A"]:
        sid = store.next_source_id()
        store.save(Artifact(sid, "t", "p", "", "", "x" * 100, grade, 7.0, 10, "en", ""))
    assert store.ab_count() == 3

def test_log_trace_appends_jsonl(tmp_path):
    store = ArtifactStore(tmp_path)
    store.log_trace({"iteration": 1, "tool": "search_web"})
    store.log_trace({"iteration": 2, "tool": "search_youtube"})
    lines = (tmp_path / "agent_trace.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["tool"] == "search_web"
