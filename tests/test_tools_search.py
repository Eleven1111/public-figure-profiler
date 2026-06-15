from unittest.mock import patch
from agent.acquisition.tools.search import (
    search_web, search_recent, search_weibo, search_zhihu, search_bilibili,
    search_twitter, search_xiaohongshu, fetch_content,
)


def _fake_tavily(query, num_results, topic=None, time_range=None):
    return [{"url": "https://example.com", "title": "T", "content": "content here", "published_date": ""}]


def test_search_web_returns_list():
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=_fake_tavily):
        results = search_web("test person", num_results=3)
    assert isinstance(results, list)
    assert all("url" in r and "content" in r for r in results)


def test_search_weibo_adds_site_filter():
    captured = []
    def fake_search(query, num_results, topic=None, time_range=None):
        captured.append(query)
        return [{"url": "https://weibo.com/u/test", "title": "T", "content": "c", "published_date": ""}]

    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_weibo("张三", max_results=3)

    assert "site:weibo.com" in captured[0]


def test_search_zhihu_adds_site_filter():
    captured = []
    def fake_search(query, num_results, topic=None, time_range=None):
        captured.append(query)
        return []

    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_zhihu("李四", max_results=3)

    assert "zhihu.com" in captured[0]


def test_search_returns_empty_on_failure():
    with patch("agent.acquisition.tools.search._tavily_search", side_effect=Exception("timeout")):
        with patch("agent.acquisition.tools.search._ddg_search", side_effect=Exception("timeout")):
            results = search_web("test", num_results=3)
    assert results == []


def test_search_recent_passes_news_topic_and_time_range():
    captured = {}
    def fake_search(query, num_results, topic=None, time_range=None):
        captured["topic"] = topic
        captured["time_range"] = time_range
        return [{"url": "https://anthropic.com/news/x", "title": "Announcement",
                 "content": "latest", "published_date": "2026-06-10"}]

    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        results = search_recent("Anthropic announcement", num_results=4, time_range="week")

    assert captured["topic"] == "news"
    assert captured["time_range"] == "week"
    assert results[0]["published_date"] == "2026-06-10"


def test_search_recent_defaults_to_month():
    captured = {}
    def fake_search(query, num_results, topic=None, time_range=None):
        captured["time_range"] = time_range
        return []

    with patch("agent.acquisition.tools.search._tavily_search", side_effect=fake_search):
        search_recent("Dario Amodei essay")

    assert captured["time_range"] == "month"


def test_tavily_search_builds_news_payload():
    sent = {}
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"results": []}
    def fake_post(url, json, timeout):
        sent.update(json)
        return _Resp()

    with patch("agent.acquisition.tools.search.requests.post", side_effect=fake_post):
        with patch.dict("os.environ", {"TAVILY_API_KEY": "k"}):
            from agent.acquisition.tools.search import _tavily_search
            _tavily_search("q", 5, topic="news", time_range="month")

    assert sent["topic"] == "news"
    assert sent["time_range"] == "month"


def test_tavily_search_omits_time_params_when_unset():
    sent = {}
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"results": []}
    def fake_post(url, json, timeout):
        sent.update(json)
        return _Resp()

    with patch("agent.acquisition.tools.search.requests.post", side_effect=fake_post):
        with patch.dict("os.environ", {"TAVILY_API_KEY": "k"}):
            from agent.acquisition.tools.search import _tavily_search
            _tavily_search("q", 5)

    assert "topic" not in sent
    assert "time_range" not in sent
