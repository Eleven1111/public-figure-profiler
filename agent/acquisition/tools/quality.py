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
