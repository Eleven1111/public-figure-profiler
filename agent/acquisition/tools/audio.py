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
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com/v1",
            ),
        )
        response = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
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
