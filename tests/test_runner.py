"""runner 输出解析测试：stream-json 拼接 + 多块还原 + 向后兼容。"""
import json

import pytest

from agent.analysis.runner import _collect_stream_json, _extract_json


def _line(obj: dict) -> str:
    return json.dumps(obj)


def test_stream_concatenates_all_assistant_text_blocks():
    # 模拟多轮续写：报告被分成 3 个 assistant 消息块
    lines = [
        _line({"type": "system", "subtype": "init"}),
        _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "# 报告\n开头部分"}]}}),
        _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "中间部分"}]}}),
        _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "结尾 ```json\n{}\n```"}]}}),
        _line({"type": "result", "is_error": False}),
    ]
    out = _collect_stream_json("\n".join(lines))
    assert out == "# 报告\n开头部分中间部分结尾 ```json\n{}\n```"
    assert out.startswith("# 报告")  # 开头未丢失


def test_stream_ignores_non_text_blocks():
    lines = [
        _line({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "x"},
            {"type": "text", "text": "正文"},
        ]}}),
    ]
    assert _collect_stream_json("\n".join(lines)) == "正文"


def test_stream_raises_on_error_result():
    lines = [
        _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "部分"}]}}),
        _line({"type": "result", "is_error": True, "subtype": "error_max_turns"}),
    ]
    with pytest.raises(RuntimeError, match="错误结果"):
        _collect_stream_json("\n".join(lines))


def test_stream_falls_back_to_raw_text():
    # 旧版 CLI 输出纯文本（非 stream-json）→ 原样返回
    plain = "# 报告标题\n这是纯文本输出，不是 stream-json"
    assert _collect_stream_json(plain) == plain


def test_stream_skips_blank_and_garbage_lines():
    lines = [
        "",
        "not json at all",
        _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "A"}]}}),
        "   ",
        _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "B"}]}}),
    ]
    assert _collect_stream_json("\n".join(lines)) == "AB"


def test_extract_json_still_works_on_collected_result():
    # 拼接出的完整文本里仍是 markdown + ```json``` 块，_extract_json 负责再拆
    result_text = "# 报告\n正文\n\n```json\n{\"a\": 1}\n```"
    md, js = _extract_json(result_text)
    assert "正文" in md and "```json" not in md
    assert json.loads(js) == {"a": 1}
