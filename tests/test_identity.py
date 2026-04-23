from unittest.mock import patch, MagicMock
from agent.acquisition.identity import synthesize_bio


def _mock_qwen_response(content: str):
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock


def test_synthesize_bio_returns_required_fields(monkeypatch):
    bio_json = '{"name_variants":["Test","Test Person"],"occupations":["CEO"],"orgs":["TestCorp"],"known_for":["Event1"],"disambiguation":"founder of TestCorp"}'

    with patch("agent.acquisition.identity.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_qwen_response(bio_json)

        result = synthesize_bio("Test Person", [{"url": "https://example.com", "content": "Test Person is CEO of TestCorp"}])

    assert "name_variants" in result
    assert "occupations" in result
    assert "orgs" in result
    assert "known_for" in result
    assert "disambiguation" in result


def test_synthesize_bio_fallback_on_error(monkeypatch):
    with patch("agent.acquisition.identity.openai.OpenAI") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = synthesize_bio("Fallback Person", [])

    assert result["name_variants"] == ["Fallback Person"]
    assert "disambiguation" in result
