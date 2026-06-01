import json
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
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

    with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test_key"}), \
         patch("agent.acquisition.loop.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_qwen_response()

        result = loop.run(max_iterations=5, min_ab=5, min_total=10)

    assert isinstance(result, list)

def test_loop_executes_search_web_tool(tmp_path):
    store = ArtifactStore(tmp_path)
    loop = AcquisitionLoop("Test Person", BIO, store)

    search_tc = _make_tool_call("search_web", {"query": "Test Person interview"})

    with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test_key"}), \
         patch("agent.acquisition.loop.openai.OpenAI") as MockClient, \
         patch("agent.acquisition.loop.search_web", return_value=[
             {"url": "https://ex.com", "title": "T", "content": "Test Person said...Test Person is...Test Person thinks...", "published_date": ""}
         ]) as mock_search, \
         patch("agent.acquisition.loop.check_relevance", return_value={"score": 8.0, "mentions": 3, "is_primary": True}):

        mock_client = MagicMock()
        MockClient.return_value = mock_client
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

    with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test_key"}), \
         patch("agent.acquisition.loop.openai.OpenAI") as MockClient, \
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

def test_loop_fails_fast_without_dashscope_key(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    store = ArtifactStore(tmp_path)
    loop = AcquisitionLoop("Test Person", BIO, store)

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        loop.run(max_iterations=1)
