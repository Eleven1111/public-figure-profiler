"""YouTube 字幕抽取（基于 youtube-transcript-api，无需 API Key）。"""

from __future__ import annotations

import re
import sys
from typing import Optional


def _extract_video_id(url: str) -> Optional[str]:
    """从 YouTube URL 提取 video_id。"""
    patterns = [
        r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        match = re.search(pat, url)
        if match:
            return match.group(1)
    return None


def fetch_youtube_transcript(url: str) -> Optional[str]:
    """从 YouTube URL 提取字幕文本（纯文字，不含时间戳）。

    失败时静默返回 None，由调用方决定降级策略。
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: WPS433
    except ImportError:
        print("      [youtube] 缺少 youtube-transcript-api", file=sys.stderr)
        return None

    video_id = _extract_video_id(url)
    if not video_id:
        return None

    try:
        fetched = YouTubeTranscriptApi().fetch(video_id)
        entries = fetched.to_raw_data()
        return " ".join(entry["text"] for entry in entries)
    except Exception as e:
        print(f"      [youtube] 字幕不可用 {video_id}: {type(e).__name__}", file=sys.stderr)
        return None
