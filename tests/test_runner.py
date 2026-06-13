"""runner 输出解析测试：JSON 信封解析 + 截断诊断 + 向后兼容。"""
import json

import pytest

from agent.analysis.runner import _extract_json, _parse_claude_json_envelope


def test_envelope_extracts_result():
    env = json.dumps({"type": "result", "is_error": False,
                      "stop_reason": "end_turn", "result": "完整报告正文"})
    assert _parse_claude_json_envelope(env) == "完整报告正文"


def test_envelope_raises_on_error():
    env = json.dumps({"is_error": True, "subtype": "error_max_turns", "result": ""})
    with pytest.raises(RuntimeError, match="错误信封"):
        _parse_claude_json_envelope(env)


def test_envelope_warns_on_truncation(capsys):
    env = json.dumps({"is_error": False, "stop_reason": "max_tokens",
                      "result": "被截断的正文"})
    out = _parse_claude_json_envelope(env)
    assert out == "被截断的正文"
    assert "stop_reason=max_tokens" in capsys.readouterr().err


def test_envelope_falls_back_to_raw_text():
    # 旧版 CLI 直接输出纯文本（非 JSON）→ 原样返回
    plain = "# 报告标题\n这是纯文本输出，不是 JSON 信封"
    assert _parse_claude_json_envelope(plain) == plain


def test_envelope_falls_back_when_no_result_field():
    # 是 JSON 但不是预期信封结构 → 原样返回
    other = json.dumps({"foo": "bar"})
    assert _parse_claude_json_envelope(other) == other


def test_extract_json_still_works_on_envelope_result():
    # 解析出的 result 文本里仍是 markdown + ```json``` 块，_extract_json 负责再拆
    result_text = "# 报告\n正文\n\n```json\n{\"a\": 1}\n```"
    md, js = _extract_json(result_text)
    assert "正文" in md and "```json" not in md
    assert json.loads(js) == {"a": 1}
