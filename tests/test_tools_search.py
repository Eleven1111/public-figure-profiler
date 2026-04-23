from unittest.mock import patch
from agent.acquisition.tools.search import (
    search_web, search_weibo, search_zhihu, search_bilibili,
    search_twitter, search_xiaohongshu, fetch_content,
)

def _fake_tavily(query, num_results):
    return [{"url": "https://example.com", "title": "T", "content": "content here", "published_date": ""}]

def test_search_web_returns_list(monkeypatch):
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=_fake_tavily):
        results = search_web("test person", num_results=3)
    assert isinstance(results, list)
    assert all("url" in r and "content" in r for r in results)

def test_search_weibo_adds_site_filter(monkeypatch):
    captured = []
    def fake_search(query, num_results):
        captured.append(query)
        return [{"url": "https://weibo.com/u/test", "title": "T", "content": "c", "published_date": ""}]

    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_weibo("张三", max_results=3)

    assert "site:weibo.com" in captured[0]

def test_search_zhihu_adds_site_filter(monkeypatch):
    captured = []
    def fake_search(query, num_results):
        captured.append(query)
        return []

    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_zhihu("李四", max_results=3)

    assert "zhihu.com" in captured[0]

def test_search_returns_empty_on_failure(monkeypatch):
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=Exception("timeout")):
        with patch("agent.acquisition.tools.search._ddg_search", side_effect=Exception("timeout")):
            results = search_web("test", num_results=3)
    assert results == []
