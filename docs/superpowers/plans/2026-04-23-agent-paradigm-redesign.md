# Agent Paradigm Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sequential corpus→LLM workflow with a dual-orchestrator agent: Qwen 3.5 drives a tool-calling acquisition loop across 8+ platforms, then `claude` CLI subprocess performs the final psychological profiling analysis.

**Architecture:** Phase 0 — Qwen synthesizes a Bio identity anchor from initial search. Phase 1 — Qwen tool-calling loop (stopping when A/B ≥ 5 AND total ≥ 10, or iterations > 25). Phase 2 — `claude --model claude-sonnet-4-6 -p` subprocess receives full corpus via stdin and streams the report.

**Tech Stack:** Python 3.12, openai (Qwen OpenAI-compatible), yt-dlp, youtube-transcript-api, trafilatura, requests, claude CLI

---

## File Map

**New files to create:**
- `agent/acquisition/__init__.py`
- `agent/acquisition/artifacts.py` — ArtifactStore (SHA256, manifest, raw/, graded/)
- `agent/acquisition/identity.py` — Phase 0 Bio synthesis via Qwen
- `agent/acquisition/tools/__init__.py`
- `agent/acquisition/tools/search.py` — All search tools (web + 7 platform wrappers via Tavily)
- `agent/acquisition/tools/youtube.py` — YouTube transcript fetch + yt-dlp audio download
- `agent/acquisition/tools/podcast.py` — Podcast Index API search
- `agent/acquisition/tools/audio.py` — Qwen multimodal audio transcription
- `agent/acquisition/tools/quality.py` — check_relevance (Qwen scoring) + report_status
- `agent/acquisition/loop.py` — Qwen tool-calling agent main loop
- `agent/analysis/__init__.py`
- `agent/analysis/prompt.py` — Builds the full analysis prompt (system + frameworks + corpus)
- `agent/analysis/runner.py` — Spawns `claude` CLI subprocess
- `tests/test_artifacts.py`
- `tests/test_identity.py`
- `tests/test_tools_search.py`
- `tests/test_quality.py`
- `tests/test_loop.py`
- `tests/test_analysis_runner.py`

**Files to modify:**
- `agent/agent.py` — Full rewrite as dual-orchestrator entry point
- `agent/AGENT.md` — One-line update (corpus source description)
- `requirements.txt` — Add yt-dlp, podcastindex, httpx

**Files to keep unchanged:**
- `agent/corpus/grader.py` — Reused as-is (imported by acquisition)
- `agent/corpus/search.py` — Reused as-is (Tavily/DDG backend)
- `agent/corpus/fetcher.py` — Reused as-is
- `agent/corpus/youtube.py` — Reused as-is (existing transcript logic)
- `references/` — All framework docs unchanged

---

## Task 1: ArtifactStore — SHA256 audit trail

**Files:**
- Create: `agent/acquisition/__init__.py`
- Create: `agent/acquisition/artifacts.py`
- Create: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_artifacts.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/na/na/Claudecode/public-figure-profiler
python -m pytest tests/test_artifacts.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'agent.acquisition'`

- [ ] **Step 3: Create the package and implement ArtifactStore**

```python
# agent/acquisition/__init__.py
```

```python
# agent/acquisition/artifacts.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Artifact:
    source_id: str
    tool: str
    platform: str
    url: str
    title: str
    content: str
    grade: str  # A / B / C / D
    relevance_score: float
    word_count: int
    language: str
    published_date: str
    sha256: str = field(default="")
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ArtifactStore:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.raw_dir = run_dir / "raw"
        self.graded_dir = run_dir / "graded"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.graded_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts: list[Artifact] = []
        self._counter = 0

    def next_source_id(self) -> str:
        self._counter += 1
        return f"S{self._counter:02d}"

    def save(self, artifact: Artifact) -> None:
        content_bytes = artifact.content.encode("utf-8")
        artifact.sha256 = hashlib.sha256(content_bytes).hexdigest()

        raw_fname = f"{artifact.source_id}_{artifact.platform}_{artifact.tool}.txt"
        (self.raw_dir / raw_fname).write_bytes(content_bytes)

        if artifact.grade in ("A", "B", "C"):
            grade_fname = f"{artifact.source_id}_{artifact.grade}_grade.txt"
            (self.graded_dir / grade_fname).write_bytes(content_bytes)

        self.artifacts.append(artifact)
        self._flush_manifest()

    def log_trace(self, entry: dict) -> None:
        with (self.run_dir / "agent_trace.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def ab_count(self) -> int:
        return sum(1 for a in self.artifacts if a.grade in ("A", "B"))

    def graded_sources(self) -> list[Artifact]:
        return [a for a in self.artifacts if a.grade != "D"]

    def to_corpus_dicts(self) -> list[dict]:
        """Convert artifacts to the dict format expected by analysis/prompt.py."""
        result = []
        for a in self.graded_sources():
            result.append({
                "source_id": a.source_id,
                "grade": a.grade,
                "source": a.platform,
                "url": a.url,
                "title": a.title,
                "content": a.content,
                "published_date": a.published_date,
                "origin": a.tool,
                "word_count": a.word_count,
                "language": a.language,
            })
        return result

    def _flush_manifest(self) -> None:
        manifest = [asdict(a) for a in self.artifacts]
        (self.run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_artifacts.py -v
```
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/acquisition/__init__.py agent/acquisition/artifacts.py tests/test_artifacts.py
git commit -m "feat: add ArtifactStore with SHA256 audit trail"
```

---

## Task 2: Identity Anchor — Phase 0 Bio synthesis

**Files:**
- Create: `agent/acquisition/identity.py`
- Create: `tests/test_identity.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_identity.py
from unittest.mock import patch, MagicMock
from agent.acquisition.identity import synthesize_bio

def _mock_qwen_response(content: str):
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock

def test_synthesize_bio_returns_required_fields(monkeypatch):
    bio_json = '{"name_variants":["Test","Test Person"],"occupations":["CEO"],"orgs":["TestCorp"],"known_for":["Event1"],"disambiguation":"founder of TestCorp"}'
    
    with patch("agent.acquisition.identity.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_qwen_response(bio_json)
        
        result = synthesize_bio("Test Person", [{"url": "https://example.com", "content": "Test Person is CEO of TestCorp"}])
    
    assert "name_variants" in result
    assert "occupations" in result
    assert "orgs" in result
    assert "known_for" in result
    assert "disambiguation" in result

def test_synthesize_bio_fallback_on_error(monkeypatch):
    with patch("agent.acquisition.identity.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")
        
        result = synthesize_bio("Fallback Person", [])
    
    assert result["name_variants"] == ["Fallback Person"]
    assert "disambiguation" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_identity.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement identity.py**

```python
# agent/acquisition/identity.py
from __future__ import annotations

import json
import os
import sys

import openai


def synthesize_bio(person: str, search_results: list[dict]) -> dict:
    """Phase 0: call Qwen to extract a Bio identity anchor from initial search results.

    Returns a dict with: name_variants, occupations, orgs, known_for, disambiguation.
    Falls back to a minimal Bio if Qwen call fails.
    """
    snippets = "\n\n".join(
        f"来源: {r.get('url', '')}\n摘要: {r.get('content', r.get('snippet', ''))[:600]}"
        for r in search_results[:8]
    )

    prompt = f"""从以下搜索结果中提取"{person}"的身份信息，返回严格的 JSON 对象：

{snippets}

JSON 格式（所有字段必填，若无信息填空列表/空字符串）：
{{
  "name_variants": ["中文名", "英文名", "常用缩写或昵称"],
  "occupations": ["主要职业1", "职业2"],
  "orgs": ["所属组织1", "组织2"],
  "known_for": ["代表性事件或成就1", "事件2"],
  "disambiguation": "一句话区分同名人物的关键特征"
}}"""

    try:
        client = openai.OpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
        )
        response = client.chat.completions.create(
            model=os.environ.get("DASHSCOPE_MODEL", "qwen3.5-plus"),
            messages=[
                {"role": "system", "content": "你是信息提取专家，只返回 JSON，不加额外解释。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        bio = json.loads(response.choices[0].message.content)
        bio.setdefault("name_variants", [person])
        bio.setdefault("occupations", [])
        bio.setdefault("orgs", [])
        bio.setdefault("known_for", [])
        bio.setdefault("disambiguation", "")
        return bio

    except Exception as exc:
        print(f"[identity] Bio 合成失败（{exc}），使用最简 Bio", file=sys.stderr)
        return {
            "name_variants": [person],
            "occupations": [],
            "orgs": [],
            "known_for": [],
            "disambiguation": f"目标人物：{person}",
        }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_identity.py -v
```
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/acquisition/identity.py tests/test_identity.py
git commit -m "feat: add Phase 0 Bio synthesis via Qwen"
```

---

## Task 3: Search tools — web + 7 platform wrappers

**Files:**
- Create: `agent/acquisition/tools/__init__.py`
- Create: `agent/acquisition/tools/search.py`
- Create: `tests/test_tools_search.py`

All platform search tools use Tavily `site:` filtering. The web tool calls the existing `corpus/search.py` backend.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_search.py
from unittest.mock import patch
from agent.acquisition.tools.search import (
    search_web, search_weibo, search_zhihu, search_bilibili,
    search_twitter, search_xiaohongshu, fetch_content,
)

def _fake_tavily(query, max_results):
    return [{"url": "https://example.com", "title": "T", "content": "content here", "published_date": ""}]

def test_search_web_returns_list(monkeypatch):
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=_fake_tavily):
        results = search_web("test person", num_results=3)
    assert isinstance(results, list)
    assert all("url" in r and "content" in r for r in results)

def test_search_weibo_adds_site_filter(monkeypatch):
    captured = []
    def fake_search(query, num_results):
        captured.append(query)
        return [{"url": "https://weibo.com/u/test", "title": "T", "content": "c", "published_date": ""}]
    
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_weibo("张三", max_results=3)
    
    assert "site:weibo.com" in captured[0]

def test_search_zhihu_adds_site_filter(monkeypatch):
    captured = []
    def fake_search(query, num_results):
        captured.append(query)
        return []
    
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_zhihu("李四", max_results=3)
    
    assert "zhihu.com" in captured[0]

def test_search_returns_empty_on_failure(monkeypatch):
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=Exception("timeout")):
        with patch("agent.acquisition.tools.search._ddg_search", side_effect=Exception("timeout")):
            results = search_web("test", num_results=3)
    assert results == []
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/test_tools_search.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement search.py**

```python
# agent/acquisition/tools/__init__.py
```

```python
# agent/acquisition/tools/search.py
"""All search tools for the acquisition agent.

Web search uses the existing corpus/search.py Tavily/DDG backend.
Platform tools use Tavily with site: filters; fall back to DuckDuckGo.
"""
from __future__ import annotations

import os
import sys

import requests


# ── Tavily backend (reuses env var from corpus layer) ────────────────────────

def _tavily_search(query: str, num_results: int) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": num_results,
            "include_raw_content": True,
            "search_depth": "advanced",
        },
        timeout=20,
    )
    resp.raise_for_status()
    results = []
    for r in resp.json().get("results", []):
        results.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "content": r.get("raw_content") or r.get("content", ""),
            "published_date": r.get("published_date", ""),
        })
    return results


def _ddg_search(query: str, num_results: int) -> list[dict]:
    from duckduckgo_search import DDGS
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append({
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "content": r.get("body", ""),
                    "published_date": "",
                })
    except Exception as exc:
        print(f"[search] DDG failed: {exc}", file=sys.stderr)
    return results


def _search(query: str, num_results: int) -> list[dict]:
    """Try Tavily first; fall back to DuckDuckGo; return [] on all failures."""
    try:
        return _tavily_search(query, num_results)
    except Exception as exc:
        print(f"[search] Tavily failed ({exc}), falling back to DDG", file=sys.stderr)
    try:
        return _ddg_search(query, num_results)
    except Exception as exc:
        print(f"[search] DDG also failed ({exc})", file=sys.stderr)
    return []


# ── Public tool functions ─────────────────────────────────────────────────────

def search_web(query: str, num_results: int = 5) -> list[dict]:
    """General web search."""
    return _search(query, num_results)


def fetch_content(url: str) -> str:
    """Fetch and extract article text from a URL."""
    try:
        from trafilatura import fetch_url, extract
        raw = fetch_url(url)
        return extract(raw) or ""
    except Exception as exc:
        print(f"[fetch] Failed {url}: {exc}", file=sys.stderr)
        return ""


def search_weibo(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:weibo.com {query}", max_results)


def search_zhihu(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:zhihu.com {query}", max_results)


def search_bilibili(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:bilibili.com {query}", max_results)


def search_twitter(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"site:twitter.com OR site:x.com {query}", max_results)


def search_xiaohongshu(query: str, max_results: int = 5) -> list[dict]:
    return _search(f"小红书 {query}", max_results)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_tools_search.py -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/acquisition/tools/__init__.py agent/acquisition/tools/search.py tests/test_tools_search.py
git commit -m "feat: add search tools — web + 6 platform wrappers via Tavily"
```

---

## Task 4: YouTube + audio tools

**Files:**
- Create: `agent/acquisition/tools/youtube.py`
- Create: `agent/acquisition/tools/audio.py`

No dedicated tests for these (external CLI + API calls). Manual smoke test documented below.

- [ ] **Step 1: Implement youtube.py** — wraps the existing `corpus/youtube.py` logic and adds yt-dlp audio download

```python
# agent/acquisition/tools/youtube.py
"""YouTube transcript extraction and audio download."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def search_youtube(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube via yt-dlp and extract available transcripts."""
    cmd = [
        "yt-dlp",
        f"ytsearch{max_results}:{query}",
        "--print", "%(id)s\t%(title)s\t%(webpage_url)s",
        "--no-download",
        "--quiet",
        "--no-warnings",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"[youtube] yt-dlp failed: {exc}", file=sys.stderr)
        return []

    items = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        vid_id, title, url = parts[0], parts[1], parts[2]
        transcript = _get_transcript(vid_id)
        items.append({
            "url": url,
            "video_id": vid_id,
            "title": title,
            "content": transcript,
            "published_date": "",
        })
    return items


def _get_transcript(video_id: str) -> str:
    """Try youtube-transcript-api for subtitles; return empty string on failure."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        for lang in [["zh-Hans", "zh-Hant", "zh"], ["en"]]:
            try:
                segments = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
                return " ".join(s["text"] for s in segments)
            except Exception:
                continue
    except ImportError:
        pass
    return ""


def download_audio(url: str, max_duration_sec: int = 1800) -> Path | None:
    """Download audio from a video URL using yt-dlp (max 30 min).

    Returns path to the downloaded .mp3 file, or None on failure.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="profiler_audio_"))
    output_template = str(tmp_dir / "audio.%(ext)s")

    cmd = [
        "yt-dlp",
        url,
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "--match-filter", f"duration < {max_duration_sec}",
        "-o", output_template,
        "--quiet",
        "--no-warnings",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"[audio] download failed: {exc}", file=sys.stderr)
        return None

    mp3_files = list(tmp_dir.glob("*.mp3"))
    return mp3_files[0] if mp3_files else None
```

- [ ] **Step 2: Implement audio.py** — Qwen 3.5 multimodal transcription

```python
# agent/acquisition/tools/audio.py
"""Qwen 3.5 multimodal audio transcription."""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import openai


def transcribe_audio(audio_path: Path) -> str:
    """Send audio to Qwen 3.5 multimodal for transcription.

    Qwen 3.5 can process audio directly without a separate Whisper step.
    Returns the transcribed text, or empty string on failure.
    """
    if not audio_path or not audio_path.exists():
        return ""

    try:
        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
        client = openai.OpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )
        response = client.chat.completions.create(
            model=os.environ.get("DASHSCOPE_MODEL", "qwen3.5-plus"),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_b64, "format": "mp3"},
                        },
                        {
                            "type": "text",
                            "text": "请完整逐字转录这段音频，保留说话人的原话，不要总结或删减。",
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        print(f"[audio] transcription failed: {exc}", file=sys.stderr)
        return ""
```

- [ ] **Step 3: Smoke test (manual)**

```bash
# Verify yt-dlp is installed
yt-dlp --version

# Test transcript extraction for a public YouTube video
cd /Users/na/na/Claudecode/public-figure-profiler
python -c "
from agent.acquisition.tools.youtube import search_youtube
results = search_youtube('Dario Amodei interview 2024', max_results=2)
for r in results:
    print(r['title'], '|', len(r['content']), 'chars')
"
```
Expected: prints 2 video titles with character counts (may be 0 if no transcript).

- [ ] **Step 4: Commit**

```bash
git add agent/acquisition/tools/youtube.py agent/acquisition/tools/audio.py
git commit -m "feat: add YouTube search + yt-dlp audio download + Qwen transcription"
```

---

## Task 5: Podcast search tool

**Files:**
- Create: `agent/acquisition/tools/podcast.py`

- [ ] **Step 1: Implement podcast.py**

```python
# agent/acquisition/tools/podcast.py
"""Podcast search via Podcast Index API with Tavily fallback."""
from __future__ import annotations

import hashlib
import os
import sys
import time

import requests


def search_podcast(query: str, max_results: int = 5) -> list[dict]:
    """Search for podcast episodes mentioning the target person.

    Uses Podcast Index API if keys are set; otherwise falls back to Tavily.
    """
    api_key = os.environ.get("PODCAST_INDEX_KEY")
    api_secret = os.environ.get("PODCAST_INDEX_SECRET")

    if api_key and api_secret:
        try:
            return _podcast_index_search(query, max_results, api_key, api_secret)
        except Exception as exc:
            print(f"[podcast] Podcast Index failed ({exc}), falling back to Tavily", file=sys.stderr)

    # Fallback: Tavily/DDG web search for podcast episodes
    from .search import _search
    results = _search(f"podcast episode interview {query}", max_results)
    return [
        {
            "url": r["url"],
            "title": r["title"],
            "description": r["content"][:600],
            "audio_url": "",
            "published_date": r.get("published_date", ""),
        }
        for r in results
    ]


def _podcast_index_search(
    query: str, num: int, api_key: str, api_secret: str
) -> list[dict]:
    ts = int(time.time())
    auth_hash = hashlib.sha1(
        f"{api_key}{api_secret}{ts}".encode()
    ).hexdigest()

    resp = requests.get(
        "https://api.podcastindex.org/api/1.0/search/byterm",
        params={"q": query, "max": num, "fulltext": True},
        headers={
            "X-Auth-Date": str(ts),
            "X-Auth-Key": api_key,
            "Authorization": auth_hash,
            "User-Agent": "PublicFigureProfiler/2.0",
        },
        timeout=15,
    )
    resp.raise_for_status()
    feeds = resp.json().get("feeds", [])
    return [
        {
            "url": ep.get("link", ""),
            "title": ep.get("title", ""),
            "description": (ep.get("description", "") or "")[:600],
            "audio_url": ep.get("url", ""),
            "published_date": "",
        }
        for ep in feeds[:num]
    ]
```

- [ ] **Step 2: Quick smoke test**

```bash
python -c "
from agent.acquisition.tools.podcast import search_podcast
results = search_podcast('Sam Altman interview', max_results=3)
print(f'Found {len(results)} podcast results')
for r in results:
    print(' -', r['title'][:60])
"
```

- [ ] **Step 3: Commit**

```bash
git add agent/acquisition/tools/podcast.py
git commit -m "feat: add podcast search with Podcast Index API + Tavily fallback"
```

---

## Task 6: Quality control — check_relevance + report_status

**Files:**
- Create: `agent/acquisition/tools/quality.py`
- Create: `tests/test_quality.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_quality.py
from unittest.mock import patch, MagicMock
from agent.acquisition.tools.quality import check_relevance, report_status

BIO = {
    "name_variants": ["张三", "Zhang San"],
    "occupations": ["CEO"],
    "orgs": ["TestCorp"],
    "known_for": ["founded TestCorp"],
    "disambiguation": "founder of TestCorp",
}

def _mock_qwen(score):
    mock = MagicMock()
    mock.choices[0].message.content = f'{{"score": {score}, "reason": "test", "is_primary": true}}'
    return mock

def test_check_relevance_returns_score(monkeypatch):
    with patch("agent.acquisition.tools.quality.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_qwen(8.5)
        
        result = check_relevance(
            "张三创办了TestCorp，他说...张三认为...张三表示...",
            BIO, "张三"
        )
    
    assert "score" in result
    assert result["score"] == 8.5
    assert "mentions" in result

def test_check_relevance_fast_fail_on_no_mentions():
    result = check_relevance("完全不相关的内容，没有目标人名出现", BIO, "张三")
    assert result["score"] == 0.0

def test_report_status_returns_state():
    state = {"ab_count": 3, "total": 7, "iteration": 5}
    result = report_status(state)
    assert result["ab_count"] == 3
    assert result["should_stop"] is False

def test_report_status_triggers_stop():
    state = {"ab_count": 5, "total": 12, "iteration": 8}
    result = report_status(state)
    assert result["should_stop"] is True
    assert result["reason"] == "sufficient"
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/test_quality.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement quality.py**

```python
# agent/acquisition/tools/quality.py
"""Quality control tools: relevance scoring and loop status reporting."""
from __future__ import annotations

import json
import os
import sys

import openai


def check_relevance(text: str, bio: dict, person_name: str) -> dict:
    """Score how relevant text is to the target person.

    Two-stage filter:
    1. Fast-fail if person name appears fewer than 2 times (saves API calls).
    2. Qwen scores 0-10; returns dict with score, reason, mentions, is_primary.
    """
    name_variants = bio.get("name_variants", [person_name])
    mention_count = sum(text.count(name) for name in name_variants)

    if mention_count < 2:
        return {
            "score": 0.0,
            "mentions": mention_count,
            "reason": "too few name mentions",
            "is_primary": False,
        }

    bio_str = json.dumps(bio, ensure_ascii=False)
    snippet = text[:1200]

    try:
        client = openai.OpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )
        response = client.chat.completions.create(
            model=os.environ.get("DASHSCOPE_MODEL", "qwen3.5-plus"),
            messages=[
                {
                    "role": "system",
                    "content": "评估内容与目标人物的相关性，只返回 JSON，不加其他解释。",
                },
                {
                    "role": "user",
                    "content": (
                        f"判断以下内容是否真实描述了「{person_name}」的观点/行为/言论/经历。\n\n"
                        f"人物档案：{bio_str}\n\n"
                        f"内容（前1200字）：{snippet}\n\n"
                        "返回 JSON：{\"score\": 0-10整数, \"reason\": \"一句话说明\", \"is_primary\": true/false}\n"
                        "评分：10=直接引言/一手采访，8=详细第三方报道，6=提及该人但非主角，<6=噪音/无关"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        result["mentions"] = mention_count
        return result
    except Exception as exc:
        print(f"[quality] check_relevance failed: {exc}", file=sys.stderr)
        # Conservative: treat as low relevance if Qwen is unavailable
        return {"score": 4.0, "mentions": mention_count, "reason": "api_error", "is_primary": False}


def report_status(state: dict) -> dict:
    """Evaluate current acquisition state and determine if stopping criteria are met.

    state must contain: ab_count (int), total (int), iteration (int).
    Returns state dict augmented with should_stop (bool) and reason (str).
    """
    ab = state.get("ab_count", 0)
    total = state.get("total", 0)
    iteration = state.get("iteration", 0)

    if ab >= 5 and total >= 10:
        return {**state, "should_stop": True, "reason": "sufficient"}
    if iteration >= 25:
        return {**state, "should_stop": True, "reason": "max_iterations"}
    return {**state, "should_stop": False, "reason": "continue"}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_quality.py -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/acquisition/tools/quality.py tests/test_quality.py
git commit -m "feat: add check_relevance (Qwen scoring) and report_status tools"
```

---

## Task 7: Acquisition loop — Qwen tool-calling agent

**Files:**
- Create: `agent/acquisition/loop.py`
- Create: `tests/test_loop.py`

This is the core of the acquisition agent. It sends the person info + tool definitions to Qwen, executes whatever tools Qwen calls, runs check_relevance on each returned content, saves passing artifacts, and loops until stopping conditions are met.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_loop.py
import json
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from agent.acquisition.artifacts import ArtifactStore
from agent.acquisition.loop import AcquisitionLoop

BIO = {
    "name_variants": ["Test Person"],
    "occupations": ["CEO"],
    "orgs": ["TestCo"],
    "known_for": ["Thing"],
    "disambiguation": "CEO of TestCo",
}

def _make_tool_call(name: str, args: dict, call_id: str = "call_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc

def _make_qwen_response(tool_calls=None, content=None):
    msg = MagicMock()
    msg.tool_calls = tool_calls or []
    msg.content = content or ""
    resp = MagicMock()
    resp.choices[0].message = msg
    return resp

def test_loop_stops_when_no_tool_calls(tmp_path):
    store = ArtifactStore(tmp_path)
    loop = AcquisitionLoop("Test Person", BIO, store)
    
    with patch("agent.acquisition.loop.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        # Qwen immediately returns no tool calls (done)
        mock_client.chat.completions.create.return_value = _make_qwen_response()
        
        result = loop.run(max_iterations=5, min_ab=5, min_total=10)
    
    assert isinstance(result, list)

def test_loop_executes_search_web_tool(tmp_path):
    store = ArtifactStore(tmp_path)
    loop = AcquisitionLoop("Test Person", BIO, store)
    
    search_tc = _make_tool_call("search_web", {"query": "Test Person interview"})
    
    with patch("agent.acquisition.loop.openai.OpenAI") as MockClient, \
         patch("agent.acquisition.loop.search_web", return_value=[
             {"url": "https://ex.com", "title": "T", "content": "Test Person said...Test Person is...Test Person thinks...", "published_date": ""}
         ]) as mock_search, \
         patch("agent.acquisition.loop.check_relevance", return_value={"score": 8.0, "mentions": 3, "is_primary": True}):
        
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        # First call: search_web tool call; second call: stop
        mock_client.chat.completions.create.side_effect = [
            _make_qwen_response(tool_calls=[search_tc]),
            _make_qwen_response(),
        ]
        
        loop.run(max_iterations=5, min_ab=5, min_total=10)
    
    mock_search.assert_called_once_with(query="Test Person interview", num_results=5)

def test_loop_skips_low_relevance_content(tmp_path):
    store = ArtifactStore(tmp_path)
    loop = AcquisitionLoop("Test Person", BIO, store)
    
    search_tc = _make_tool_call("search_web", {"query": "test"})
    
    with patch("agent.acquisition.loop.openai.OpenAI") as MockClient, \
         patch("agent.acquisition.loop.search_web", return_value=[
             {"url": "https://noise.com", "title": "Noise", "content": "unrelated content", "published_date": ""}
         ]), \
         patch("agent.acquisition.loop.check_relevance", return_value={"score": 2.0, "mentions": 0}):
        
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            _make_qwen_response(tool_calls=[search_tc]),
            _make_qwen_response(),
        ]
        
        loop.run(max_iterations=5, min_ab=5, min_total=10)
    
    assert store.ab_count() == 0
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/test_loop.py -v 2>&1 | head -15
```

- [ ] **Step 3: Implement loop.py**

```python
# agent/acquisition/loop.py
"""Qwen 3.5 tool-calling acquisition agent main loop."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import openai

from .artifacts import Artifact, ArtifactStore
from .tools.search import (
    search_web, fetch_content,
    search_weibo, search_zhihu, search_bilibili,
    search_twitter, search_xiaohongshu,
)
from .tools.youtube import search_youtube, download_audio
from .tools.audio import transcribe_audio
from .tools.podcast import search_podcast
from .tools.quality import check_relevance, report_status
from ..corpus.grader import grade_source


TOOL_DEFINITIONS = [
    {"type": "function", "function": {
        "name": "search_web",
        "description": "用 Tavily 搜索目标人物的网页内容，返回标题+摘要列表",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索词，包含人名+关键词"},
            "num_results": {"type": "integer", "default": 5, "description": "返回数量"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_youtube",
        "description": "在 YouTube 搜索目标人物的视频并提取字幕文本",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_podcast",
        "description": "在播客数据库搜索目标人物的访谈节目",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_weibo",
        "description": "在微博搜索目标人物的原创内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_zhihu",
        "description": "在知乎搜索目标人物的回答和文章",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_bilibili",
        "description": "在 B站搜索目标人物的视频内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_twitter",
        "description": "搜索目标人物的 Twitter/X 内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_xiaohongshu",
        "description": "在小红书搜索目标人物的内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_content",
        "description": "抓取指定 URL 的完整正文内容",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "download_audio",
        "description": "下载 YouTube 或播客音频（最长30分钟），返回本地文件路径",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "transcribe_audio",
        "description": "用 Qwen 多模态模型转录音频文件为文字",
        "parameters": {"type": "object", "properties": {
            "audio_path": {"type": "string", "description": "download_audio 返回的本地路径"},
        }, "required": ["audio_path"]},
    }},
    {"type": "function", "function": {
        "name": "report_status",
        "description": "报告当前采集进度，让系统决定是否达到停止条件",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "当前进展的简要描述"},
        }, "required": ["message"]},
    }},
]

_TOOL_DISPATCH = {
    "search_web": lambda args, ctx: search_web(**args),
    "search_youtube": lambda args, ctx: search_youtube(**args),
    "search_podcast": lambda args, ctx: search_podcast(**args),
    "search_weibo": lambda args, ctx: search_weibo(**args),
    "search_zhihu": lambda args, ctx: search_zhihu(**args),
    "search_bilibili": lambda args, ctx: search_bilibili(**args),
    "search_twitter": lambda args, ctx: search_twitter(**args),
    "search_xiaohongshu": lambda args, ctx: search_xiaohongshu(**args),
    "fetch_content": lambda args, ctx: {"content": fetch_content(**args)},
    "download_audio": lambda args, ctx: _handle_download_audio(args, ctx),
    "transcribe_audio": lambda args, ctx: _handle_transcribe_audio(args, ctx),
    "report_status": lambda args, ctx: report_status({
        "ab_count": ctx["store"].ab_count(),
        "total": len(ctx["store"].artifacts),
        "iteration": ctx["iteration"],
    }),
}


class AcquisitionLoop:
    def __init__(self, person: str, bio: dict, store: ArtifactStore) -> None:
        self.person = person
        self.bio = bio
        self.store = store
        self.iteration = 0

    def run(
        self,
        max_iterations: int = 25,
        min_ab: int = 5,
        min_total: int = 10,
        skip_audio: bool = False,
    ) -> list[dict]:
        """Run the Qwen acquisition loop. Returns corpus dicts for analysis."""
        client = openai.OpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )

        bio_str = json.dumps(self.bio, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": self._system_prompt(bio_str)},
            {"role": "user", "content": f"请开始采集「{self.person}」的公开资料。"},
        ]

        ctx = {"store": self.store, "iteration": 0, "skip_audio": skip_audio, "audio_paths": {}}

        while self.iteration < max_iterations:
            response = client.chat.completions.create(
                model=os.environ.get("DASHSCOPE_MODEL", "qwen3.5-plus"),
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (msg.tool_calls or [])
            ]})

            if not msg.tool_calls:
                print(f"[loop] Qwen finished after {self.iteration} iterations", file=sys.stderr)
                break

            tool_results = []
            stop_now = False
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                ctx["iteration"] = self.iteration

                if skip_audio and tool_name in ("download_audio", "transcribe_audio"):
                    tool_output = {"skipped": "audio disabled"}
                else:
                    tool_output = self._execute_and_save(tool_name, args, ctx)

                if tool_name == "report_status" and tool_output.get("should_stop"):
                    stop_now = True
                    print(
                        f"[loop] Stop: {tool_output['reason']} "
                        f"(A/B={self.store.ab_count()}, total={len(self.store.artifacts)})",
                        file=sys.stderr,
                    )

                tool_results.append({
                    "tool_call_id": tc.id,
                    "role": "tool",
                    "content": json.dumps(tool_output, ensure_ascii=False, default=str),
                })

            messages.extend(tool_results)
            self.iteration += 1

            if stop_now:
                break

        return self.store.to_corpus_dicts()

    def _execute_and_save(self, tool_name: str, args: dict, ctx: dict) -> dict | list:
        """Execute a tool and auto-save any returned content as artifacts."""
        dispatch_fn = _TOOL_DISPATCH.get(tool_name)
        if not dispatch_fn:
            return {"error": f"unknown tool: {tool_name}"}

        try:
            raw_result = dispatch_fn(args, ctx)
        except Exception as exc:
            print(f"[loop] Tool {tool_name} failed: {exc}", file=sys.stderr)
            return {"error": str(exc)}

        self.store.log_trace({
            "iteration": self.iteration,
            "tool": tool_name,
            "input": args,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Auto-save content from search results
        if isinstance(raw_result, list):
            self._process_result_list(raw_result, tool_name)
        elif isinstance(raw_result, dict) and "content" in raw_result:
            self._process_single_content(raw_result, tool_name, args.get("url", ""))

        return raw_result

    def _process_result_list(self, results: list[dict], tool_name: str) -> None:
        for item in results:
            content = item.get("content") or item.get("transcript") or item.get("description", "")
            if not content or len(content) < 100:
                continue
            self._try_save(
                content=content,
                tool=tool_name,
                url=item.get("url", ""),
                title=item.get("title", ""),
                published_date=item.get("published_date", ""),
            )

    def _process_single_content(self, result: dict, tool_name: str, url: str) -> None:
        content = result.get("content", "")
        if content and len(content) >= 100:
            self._try_save(content=content, tool=tool_name, url=url, title="", published_date="")

    def _try_save(
        self, content: str, tool: str, url: str, title: str, published_date: str
    ) -> None:
        rel = check_relevance(content, self.bio, self.person)
        if rel.get("score", 0) < 6:
            return

        source_id = self.store.next_source_id()
        grade_sig = grade_source({
            "url": url,
            "content": content,
            "title": title,
        })
        artifact = Artifact(
            source_id=source_id,
            tool=tool,
            platform=_platform_from_tool(tool),
            url=url,
            title=title,
            content=content,
            grade=grade_sig.grade,
            relevance_score=rel.get("score", 0),
            word_count=len(content.split()),
            language="zh" if any("一" <= c <= "鿿" for c in content[:100]) else "en",
            published_date=published_date,
        )
        self.store.save(artifact)
        print(
            f"[loop] Saved {source_id} ({grade_sig.grade}) from {tool}: {title[:50] or url[:50]}",
            file=sys.stderr,
        )

    def _system_prompt(self, bio_str: str) -> str:
        return f"""你是一个专业的信息采集 agent，负责为公开人物心理侧写分析系统性地收集一手资料。

目标人物：{self.person}
身份锚点（用于过滤噪音，避免混入同名人）：
{bio_str}

采集策略（按优先级）：
1. 高价值（A 级）：YouTube/B站长篇访谈字幕、播客原稿、听证会证词
2. 中价值（B 级）：知乎长文、深度媒体报道、专访
3. 覆盖（C 级）：微博、Twitter/X、小红书内容
4. 跨语言：同时搜索中文和英文

每采集 4-5 个来源后，调用 report_status 报告进度。
当 A/B 级来源 ≥ 5 条 且总数 ≥ 10 条时，report_status 会通知停止。
请不要重复搜索已经覆盖的角度，遇到无结果的平台立即换下一个。"""


def _platform_from_tool(tool: str) -> str:
    mapping = {
        "search_web": "web",
        "search_youtube": "youtube",
        "search_podcast": "podcast",
        "search_weibo": "weibo",
        "search_zhihu": "zhihu",
        "search_bilibili": "bilibili",
        "search_twitter": "twitter",
        "search_xiaohongshu": "xiaohongshu",
        "fetch_content": "web",
        "transcribe_audio": "audio",
    }
    return mapping.get(tool, "unknown")


def _handle_download_audio(args: dict, ctx: dict) -> dict:
    from pathlib import Path
    path = download_audio(args["url"])
    if path:
        ctx["audio_paths"][args["url"]] = str(path)
        return {"audio_path": str(path), "success": True}
    return {"audio_path": None, "success": False}


def _handle_transcribe_audio(args: dict, ctx: dict) -> dict:
    from pathlib import Path
    path = Path(args["audio_path"])
    text = transcribe_audio(path)
    return {"content": text, "success": bool(text)}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_loop.py -v
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/acquisition/loop.py tests/test_loop.py
git commit -m "feat: implement Qwen tool-calling acquisition agent loop"
```

---

## Task 8: Analysis runner — claude CLI subprocess

**Files:**
- Create: `agent/analysis/__init__.py`
- Create: `agent/analysis/prompt.py`
- Create: `agent/analysis/runner.py`
- Create: `tests/test_analysis_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analysis_runner.py
import subprocess
from unittest.mock import patch, MagicMock
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
        result = run_analysis(
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
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/test_analysis_runner.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement prompt.py**

```python
# agent/analysis/__init__.py
```

```python
# agent/analysis/prompt.py
"""Build the full analysis prompt passed to claude CLI."""
from __future__ import annotations


def build_prompt(
    person: str,
    purpose: str,
    mode: str,
    frameworks: list[str],
    corpus_sources: list[dict],
    adequacy: str,
    agent_md: str,
    framework_docs: str,
    output_schema: str,
) -> str:
    """Assemble system + user content into a single stdin prompt for claude -p."""
    adequacy_notes = {
        "sufficient": "",
        "sparse": "\n⚠️ 语料偏少（A/B级来源不足3篇），整体置信度上限为「中」。",
        "insufficient": (
            "\n⚠️ 语料不足（仅有C/D级来源），"
            "所有结论置信度最高为「低」，以探索性草稿模式输出。"
        ),
    }

    corpus_lines = []
    for s in corpus_sources:
        meta = [
            f"等级: {s.get('grade', '?')}",
            f"来源: {s.get('source') or s.get('url', '用户提供')}",
        ]
        if s.get("published_date"):
            meta.append(f"发布: {s['published_date']}")
        if s.get("origin"):
            meta.append(f"工具: {s['origin']}")
        if s.get("title"):
            meta.append(f"标题: {s['title']}")
        header = f"[{s['source_id']} | " + " | ".join(meta) + "]"
        corpus_lines.append(f"{header}\n{s['content']}")

    corpus_text = "\n\n---\n\n".join(corpus_lines)
    framework_list = ", ".join(frameworks)

    system_block = f"""{agent_md}

---

# 本次激活的分析框架

{framework_docs}

---

# 输出格式规范

{output_schema}"""

    user_block = (
        f"请对以下公开人物进行{'完整' if mode == 'deep' else '快速'}心理侧写分析。\n\n"
        f"**分析目标：** {person}\n"
        f"**分析目的：** {purpose}\n"
        f"**分析模式：** {mode.upper()} MODE\n"
        f"**本次激活框架：** {framework_list}"
        f"{adequacy_notes[adequacy]}\n\n"
        f"**已收集语料（共 {len(corpus_sources)} 篇，已预分配 source_id）：**\n\n"
        f"{corpus_text if corpus_sources else '（无语料，无法分析）'}\n\n"
        "请严格按照 AGENT.md 中的 Step 0 → Step 7 流程执行。\n"
        "报告正文中每条引证必须带 [Snn] 编号，并在末尾输出「## 参考文献」章节。\n"
        "Deep Mode 另外追加一个 ```json ... ``` 代码块（符合 output-schema.md）。"
    )

    return f"<system>\n{system_block}\n</system>\n\n<user>\n{user_block}\n</user>"
```

- [ ] **Step 4: Implement runner.py**

```python
# agent/analysis/runner.py
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
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_analysis_runner.py -v
```
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add agent/analysis/__init__.py agent/analysis/prompt.py agent/analysis/runner.py tests/test_analysis_runner.py
git commit -m "feat: add Claude Code CLI analysis runner with prompt builder"
```

---

## Task 9: Rewrite agent.py — dual-orchestrator entry point

**Files:**
- Modify: `agent/agent.py` (full rewrite)
- Modify: `agent/AGENT.md` (one line)

- [ ] **Step 1: Update AGENT.md** — change one line in the opening paragraph

Read current AGENT.md first line:
```
语料由外部工程化管道提前构建好并作为输入注入
```
Change to:
```
语料由 Acquisition Agent（Qwen 3.5）自主采集并经相关性审计，以 graded/ 目录中的语料注入
```

```bash
# Verify the line exists
grep -n "外部工程化管道" /Users/na/na/Claudecode/public-figure-profiler/agent/AGENT.md
```

- [ ] **Step 2: Apply the AGENT.md change**

In `agent/AGENT.md`, find the line containing `外部工程化管道` and update it. Use the Edit tool to replace exactly.

- [ ] **Step 3: Rewrite agent.py**

```python
# agent/agent.py
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

from .acquisition.artifacts import ArtifactStore
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
    slug = re.sub(r"[^\w\s一-鿿-]", "", slug)
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

    # ── User-provided corpus (A grade, skip acquisition loop for these) ──────
    for corpus_path in args.corpus:
        p = Path(corpus_path)
        if not p.exists():
            print(f"Warning: corpus file not found: {p}", file=sys.stderr)
            continue
        content = p.read_text(encoding="utf-8")
        from .acquisition.artifacts import Artifact
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
```

- [ ] **Step 4: Verify CLI help works**

```bash
cd /Users/na/na/Claudecode/public-figure-profiler
python -m agent.agent --help
```
Expected: prints help without import errors.

- [ ] **Step 5: Commit**

```bash
git add agent/agent.py agent/AGENT.md
git commit -m "feat: rewrite agent.py as dual-orchestrator (Phase 0/1/2)"
```

---

## Task 10: Update requirements.txt + run full test suite

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements.txt**

```
# LLM clients
openai>=1.0.0,<2.0.0

# Web search + content extraction
requests>=2.31.0,<3.0.0
trafilatura>=1.12.0,<3.0.0
ddgs>=9.0.0

# YouTube
yt-dlp>=2024.12.0
youtube-transcript-api>=0.6.0,<2.0.0

# Podcast
podcastindex>=1.2.0

# Testing
pytest>=8.0.0,<10.0.0
pytest-mock>=3.12.0,<4.0.0
```

Note: `anthropic` package is removed — analysis now uses `claude` CLI. `beautifulsoup4` and `openai-whisper` are removed (no longer needed).

- [ ] **Step 2: Install new deps**

```bash
cd /Users/na/na/Claudecode/public-figure-profiler
source .venv/bin/activate
pip install yt-dlp podcastindex
pip uninstall -y anthropic openai-whisper assemblyai 2>/dev/null || true
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: all tests pass (test_artifacts, test_identity, test_tools_search, test_quality, test_loop, test_analysis_runner).

- [ ] **Step 4: Smoke test end-to-end (optional but recommended)**

```bash
DASHSCOPE_API_KEY="sk-sp-289ef966bb4040cdb893e1767811dca5" \
DASHSCOPE_BASE_URL="https://coding.dashscope.aliyuncs.com/v1" \
DASHSCOPE_MODEL="qwen3.5-plus" \
TAVILY_API_KEY="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" \
python -m agent.agent \
  --person "Sam Altman" \
  --mode quick \
  --skip-audio \
  --max-iterations 5 \
  --min-ab-sources 2 \
  --purpose "test run"
```
Expected: runs Phase 0 (Bio), Phase 1 (acquisition ~5 iterations), Phase 2 (claude analysis), writes profile to `./profiles/`.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: update requirements — add yt-dlp/podcastindex, remove anthropic SDK"
```

---

## Self-Review Against Spec

**Spec Section → Plan Task:**

| Spec Requirement | Covered In |
|---|---|
| Phase 0 Bio synthesis (Qwen) | Task 2 |
| 14 tools (search × 8, fetch, download_audio, transcribe, check_relevance, save_artifact, report_status) | Tasks 3–6 + loop.py auto-save handles save_artifact internally |
| Tool-calling loop with stopping conditions (A/B ≥ 5, total ≥ 10, max 25) | Task 7 |
| Two-pass noise filter (check_relevance ≥ 6 + mentions ≥ 2) | Task 6 |
| SHA256 audit trail + manifest.json + agent_trace.jsonl | Task 1 |
| claude CLI subprocess (sonnet-4-6) | Task 8 |
| `--identity` override | Task 9 |
| `--skip-audio` flag | Task 7, Task 9 |
| User corpus (`--corpus`) injected as A-grade | Task 9 |
| Twitter/Xiaohongshu Tavily fallback | Task 3 |
| Podcast Index with Tavily fallback | Task 5 |
| AGENT.md update | Task 9 |
| requirements.txt updated | Task 10 |

**No placeholders found.** All steps include actual code.

**Type consistency check:** `ArtifactStore.to_corpus_dicts()` returns `list[dict]` in Task 1; `build_prompt(corpus_sources=list[dict])` in Task 8 accepts same type. `run_analysis()` returns `tuple[str, str | None]` used correctly in Task 9. All method signatures consistent across tasks.
