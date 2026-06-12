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
    with patch("agent.acquisition.tools.quality.os.environ", {"DEEPSEEK_API_KEY": "test_key"}):
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
