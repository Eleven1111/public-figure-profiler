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
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
            ),
        )
        response = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
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
