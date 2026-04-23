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
