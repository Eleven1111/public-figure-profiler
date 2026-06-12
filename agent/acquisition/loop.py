"""Qwen 3.5 tool-calling acquisition agent main loop."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import openai

from .artifacts import Artifact, ArtifactStore
from .tools.search import (
    search_web, fetch_content,
    search_weibo, search_zhihu, search_bilibili,
    search_twitter, search_xiaohongshu,
)
from .tools.youtube import search_youtube, download_audio
from .tools.audio import transcribe_audio
from .tools.podcast import search_podcast
from .tools.quality import check_relevance, report_status
from ..corpus.grader import classify_stance, grade_source


TOOL_DEFINITIONS = [
    {"type": "function", "function": {
        "name": "search_web",
        "description": "用 Tavily 搜索目标人物的网页内容，返回标题+摘要列表",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索词，包含人名+关键词"},
            "num_results": {"type": "integer", "default": 5, "description": "返回数量"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_youtube",
        "description": "在 YouTube 搜索目标人物的视频并提取字幕文本",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_podcast",
        "description": "在播客数据库搜索目标人物的访谈节目",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 3},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_weibo",
        "description": "在微博搜索目标人物的原创内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_zhihu",
        "description": "在知乎搜索目标人物的回答和文章",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_bilibili",
        "description": "在 B站搜索目标人物的视频内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_twitter",
        "description": "搜索目标人物的 Twitter/X 内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_xiaohongshu",
        "description": "在小红书搜索目标人物的内容",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_content",
        "description": "抓取指定 URL 的完整正文内容",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "download_audio",
        "description": "下载 YouTube 或播客音频（最长30分钟），返回本地文件路径",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "transcribe_audio",
        "description": "用 Qwen 多模态模型转录音频文件为文字",
        "parameters": {"type": "object", "properties": {
            "audio_path": {"type": "string", "description": "download_audio 返回的本地路径"},
        }, "required": ["audio_path"]},
    }},
    {"type": "function", "function": {
        "name": "report_status",
        "description": "报告当前采集进度，让系统决定是否达到停止条件",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "当前进展的简要描述"},
        }, "required": ["message"]},
    }},
]

_TOOL_DISPATCH = {
    "search_web": lambda args, ctx: search_web(query=args["query"], num_results=args.get("num_results", 5)),
    "search_youtube": lambda args, ctx: search_youtube(**args),
    "search_podcast": lambda args, ctx: search_podcast(**args),
    "search_weibo": lambda args, ctx: search_weibo(**args),
    "search_zhihu": lambda args, ctx: search_zhihu(**args),
    "search_bilibili": lambda args, ctx: search_bilibili(**args),
    "search_twitter": lambda args, ctx: search_twitter(**args),
    "search_xiaohongshu": lambda args, ctx: search_xiaohongshu(**args),
    "fetch_content": lambda args, ctx: {"content": fetch_content(**args)},
    "download_audio": lambda args, ctx: _handle_download_audio(args, ctx),
    "transcribe_audio": lambda args, ctx: _handle_transcribe_audio(args, ctx),
    "report_status": lambda args, ctx: report_status({
        "ab_count": ctx["store"].ab_count(),
        "total": len(ctx["store"].artifacts),
        "iteration": ctx["iteration"],
        "critical_count": sum(
            1 for a in ctx["store"].artifacts if a.stance == "critical"
        ),
    }),
}


class AcquisitionLoop:
    def __init__(self, person: str, bio: dict, store: ArtifactStore) -> None:
        self.person = person
        self.bio = bio
        self.store = store
        self.iteration = 0

    def run(
        self,
        max_iterations: int = 25,
        min_ab: int = 5,
        min_total: int = 10,
        skip_audio: bool = False,
    ) -> list[dict]:
        """Run the Qwen acquisition loop. Returns corpus dicts for analysis."""
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required for the acquisition agent. "
                "Set it before running automatic acquisition, or use "
                "--skip-acquisition with one or more --corpus files."
            )

        client = openai.OpenAI(
            api_key=api_key,
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com/v1",
            ),
        )

        bio_str = json.dumps(self.bio, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": self._system_prompt(bio_str)},
            {"role": "user", "content": f"请开始采集「{self.person}」的公开资料。"},
        ]

        ctx = {"store": self.store, "iteration": 0, "skip_audio": skip_audio, "audio_paths": {}}

        while self.iteration < max_iterations:
            response = client.chat.completions.create(
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (msg.tool_calls or [])
            ]})

            if not msg.tool_calls:
                print(f"[loop] Qwen finished after {self.iteration} iterations", file=sys.stderr)
                break

            tool_results = []
            stop_now = False
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                ctx["iteration"] = self.iteration

                if skip_audio and tool_name in ("download_audio", "transcribe_audio"):
                    tool_output = {"skipped": "audio disabled"}
                else:
                    tool_output = self._execute_and_save(tool_name, args, ctx)

                if tool_name == "report_status" and tool_output.get("should_stop"):
                    stop_now = True
                    print(
                        f"[loop] Stop: {tool_output['reason']} "
                        f"(A/B={self.store.ab_count()}, total={len(self.store.artifacts)})",
                        file=sys.stderr,
                    )

                tool_results.append({
                    "tool_call_id": tc.id,
                    "role": "tool",
                    "content": json.dumps(tool_output, ensure_ascii=False, default=str),
                })

            messages.extend(tool_results)
            self.iteration += 1

            if stop_now:
                break

        return self.store.to_corpus_dicts()

    def _execute_and_save(self, tool_name: str, args: dict, ctx: dict) -> dict | list:
        """Execute a tool and auto-save any returned content as artifacts."""
        dispatch_fn = _TOOL_DISPATCH.get(tool_name)
        if not dispatch_fn:
            return {"error": f"unknown tool: {tool_name}"}

        try:
            raw_result = dispatch_fn(args, ctx)
        except Exception as exc:
            print(f"[loop] Tool {tool_name} failed: {exc}", file=sys.stderr)
            return {"error": str(exc)}

        self.store.log_trace({
            "iteration": self.iteration,
            "tool": tool_name,
            "input": args,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if isinstance(raw_result, list):
            self._process_result_list(raw_result, tool_name)
        elif isinstance(raw_result, dict) and "content" in raw_result:
            self._process_single_content(raw_result, tool_name, args.get("url", ""))

        return raw_result

    def _process_result_list(self, results: list[dict], tool_name: str) -> None:
        for item in results:
            content = item.get("content") or item.get("transcript") or item.get("description", "")
            if not content or len(content) < 100:
                continue
            self._try_save(
                content=content,
                tool=tool_name,
                url=item.get("url", ""),
                title=item.get("title", ""),
                published_date=item.get("published_date", ""),
            )

    def _process_single_content(self, result: dict, tool_name: str, url: str) -> None:
        content = result.get("content", "")
        if content and len(content) >= 100:
            self._try_save(content=content, tool=tool_name, url=url, title="", published_date="")

    def _try_save(
        self, content: str, tool: str, url: str, title: str, published_date: str
    ) -> None:
        rel = check_relevance(content, self.bio, self.person)
        if rel.get("score", 0) < 6:
            return

        source_id = self.store.next_source_id()
        grade_sig = grade_source({
            "url": url,
            "content": content,
            "title": title,
        })
        artifact = Artifact(
            source_id=source_id,
            tool=tool,
            platform=_platform_from_tool(tool),
            url=url,
            title=title,
            content=content,
            grade=grade_sig.grade,
            stance=classify_stance(content, title),
            relevance_score=rel.get("score", 0),
            word_count=len(content.split()),
            language="zh" if any("一" <= c <= "鿿" for c in content[:100]) else "en",
            published_date=published_date,
        )
        self.store.save(artifact)
        print(
            f"[loop] Saved {source_id} ({grade_sig.grade}) from {tool}: {title[:50] or url[:50]}",
            file=sys.stderr,
        )

    def _system_prompt(self, bio_str: str) -> str:
        return f"""你是一个专业的信息采集 agent，负责为公开人物心理侧写分析系统性地收集一手资料。

目标人物：{self.person}
身份锚点（用于过滤噪音，避免混入同名人）：
{bio_str}

采集策略（按优先级）：
1. 高价值（A 级）：YouTube/B站长篇访谈字幕、播客原稿、听证会证词
2. 中价值（B 级）：知乎长文、深度媒体报道、专访
3. 覆盖（C 级）：微博、Twitter/X、小红书内容
4. 跨语言：同时搜索中文和英文

**对抗性语料配额（强制）：** 至少采集 2 条批评性/对立方来源——
做空报告、诉讼/监管文件、离职员工或竞争对手的评价、深度质疑报道。
搜索词示例：「{self.person} 争议」「{self.person} 质疑 批评」
「{self.person} lawsuit controversy criticism」。
本人叙事和友好媒体的语料天然有美化偏差，批评性来源是矛盾分析的关键证据。

**行为事实采集（强制）：** 除言论语料外，至少采集 2 条记录**可核实行为**的来源——
融资/退出/减持时机、重大人事决策、诉讼结果、捐赠、股权变动、组织调整的新闻报道。
言行对照是侧写分析的核心证据，只有言论没有行为记录会严重削弱报告可信度。

每采集 4-5 个来源后，调用 report_status 报告进度。
当 A/B 级来源 ≥ 5 条 且总数 ≥ 10 条且已有批评性来源时，report_status 会通知停止。
请不要重复搜索已经覆盖的角度，遇到无结果的平台立即换下一个。"""


def _platform_from_tool(tool: str) -> str:
    mapping = {
        "search_web": "web",
        "search_youtube": "youtube",
        "search_podcast": "podcast",
        "search_weibo": "weibo",
        "search_zhihu": "zhihu",
        "search_bilibili": "bilibili",
        "search_twitter": "twitter",
        "search_xiaohongshu": "xiaohongshu",
        "fetch_content": "web",
        "transcribe_audio": "audio",
    }
    return mapping.get(tool, "unknown")


def _handle_download_audio(args: dict, ctx: dict) -> dict:
    from pathlib import Path
    path = download_audio(args["url"])
    if path:
        ctx["audio_paths"][args["url"]] = str(path)
        return {"audio_path": str(path), "success": True}
    return {"audio_path": None, "success": False}


def _handle_transcribe_audio(args: dict, ctx: dict) -> dict:
    from pathlib import Path
    path = Path(args["audio_path"])
    text = transcribe_audio(path)
    return {"content": text, "success": bool(text)}
