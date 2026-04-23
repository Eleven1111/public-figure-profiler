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
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

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
