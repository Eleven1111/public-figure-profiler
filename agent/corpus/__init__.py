"""语料采集工程化管道。

子模块：
  search    — 多引擎搜索（Tavily / SerpAPI / Brave）
  fetcher   — 网页正文抽取（trafilatura）
  youtube   — YouTube 字幕抽取
  wikipedia — 维基百科背景资料
  dedupe    — 去重与相似度合并
  grader    — LLM 语料二次评级
  pipeline  — 管道编排
"""

from .pipeline import build_corpus, CorpusPipelineConfig
from .search import web_search, SearchResult
from .fetcher import fetch_article, Article
from .youtube import fetch_youtube_transcript
from .wikipedia import fetch_wikipedia_summary
from .dedupe import dedupe_sources
from .grader import grade_source

__all__ = [
    "build_corpus",
    "CorpusPipelineConfig",
    "web_search",
    "SearchResult",
    "fetch_article",
    "Article",
    "fetch_youtube_transcript",
    "fetch_wikipedia_summary",
    "dedupe_sources",
    "grade_source",
]
