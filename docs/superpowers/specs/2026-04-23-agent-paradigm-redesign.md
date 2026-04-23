# Public Figure Profiler — Agent Paradigm Redesign

**Date:** 2026-04-23  
**Status:** Approved  
**Scope:** Full architecture overhaul from Workflow to True Agent pattern

---

## 1. 核心问题与目标

### 现状问题

当前实现是 **Workflow（工作流）范式**：代码预设好每一步，顺序调用 pipeline，最后传给 LLM 做一次性分析。LLM 不控制采集过程，不能动态调整策略，无法响应"我搜不到这个人的播客，换 Bilibili"。

### 目标

重构为 **True Agent 范式**：

- **采集层**：LLM（Qwen 3.5）驱动工具调用循环，自主决定下一步搜哪个平台、要不要下载音频、结果是否满足要求
- **分析层**：Claude claude-opus-4-7 接收完整语料，执行深度心理侧写，带 adaptive thinking + prompt caching + streaming
- **双 orchestrator**：采集用 Qwen（便宜、多模态、够用），分析用 Claude（最强推理）

---

## 2. 整体架构

```
CLI Entry: python -m agent.agent --person "X" [options]
│
├─ Phase 0: Identity Anchor
│   └─ 快速 Web 搜索 → Qwen 合成 Bio（姓名/职业/组织/关键事件）
│       └─ 作为相关性过滤基准（避免混入同名噪音）
│
├─ Phase 1: Acquisition Agent Loop (Qwen 3.5)
│   ├─ 工具集（14 个工具，覆盖所有平台）
│   ├─ Qwen 自主决定调用顺序和策略
│   ├─ 每次工具调用结果立刻持久化到 artifacts/
│   └─ 停止条件：A/B 级 ≥ 5 且总计 ≥ 10，或迭代 > 25 次
│
└─ Phase 2: Analysis Agent (Claude claude-opus-4-7)
    ├─ System prompt: AGENT.md + frameworks + schema（prompt cached）
    ├─ thinking: {"type": "adaptive"} + output_config: {"effort": "xhigh"}
    ├─ streaming output（实时打印到终端）
    └─ 输出：Markdown 报告 + JSON profile + 参考文献
```

---

## 3. 采集 Agent 工具集（14 个工具）

Qwen 3.5 的工具调用循环，每个工具执行后自动 save_artifact。

### 3.1 搜索类工具（8 个）

| 工具名 | 平台 | 返回 |
|--------|------|------|
| `search_web` | Tavily（主）/ DuckDuckGo（备）| 标题、URL、摘要列表 |
| `search_youtube` | YouTube Data API / yt-dlp | 视频 ID、标题、描述、字幕文本 |
| `search_podcast` | Podcast Index API（免费）+ Spotify | 节目标题、集数 URL、描述 |
| `search_weibo` | 微博移动端接口 | 帖子文本、评论数、转发数 |
| `search_zhihu` | 知乎搜索 | 回答/文章标题 + 摘要 |
| `search_bilibili` | B站搜索 API | 视频标题、描述、字幕（CC） |
| `search_twitter` | Twitter/X（通过 Tavily 或 nitter 镜像）| 推文文本、转推数、时间 |
| `search_xiaohongshu` | 小红书（通过 Tavily 或公开搜索）| 笔记标题 + 摘要 |

**降级策略：** Twitter/X 和小红书直接爬取受平台限制，优先用 Tavily 的全网搜索结果（含这两个平台的公开内容）；若 Tavily 未覆盖，用 DuckDuckGo site: 过滤。全部失败时工具返回空列表而非报错，Qwen 自动跳过并换平台。

### 3.2 获取类工具（3 个）

| 工具名 | 功能 |
|--------|------|
| `fetch_content` | 抓取任意 URL 正文（trafilatura）|
| `download_audio` | yt-dlp 下载 YouTube/B站/播客音频片段（最长 30 min）|
| `transcribe_audio` | Qwen 3.5 多模态直接理解音频（无需独立 Whisper）|

### 3.3 质控工具（2 个）

| 工具名 | 功能 |
|--------|------|
| `check_relevance` | 传入文本 + Bio → Qwen 打分 0-10，≥6 为有效，同时检查全文提及人名次数 ≥ 3 |
| `save_artifact` | 将一条语料写入 artifacts/，记录 SHA256 + 元信息 |

### 3.4 流控工具（1 个）

| 工具名 | 功能 |
|--------|------|
| `report_status` | Qwen 报告当前采集进度（A/B 数量、已迭代次数），触发停止判断 |

---

## 4. Identity Anchor（混合模式）

Phase 0 自动合成身份基准，无需用户手填：

```
1. search_web("${person} 简介 职位 组织" + "${person} biography career")
2. Qwen 从结果中提取 → Bio JSON:
   {
     "name_variants": ["张三", "Zhang San", "ZS"],
     "occupations": ["企业家", "投资人"],
     "orgs": ["某公司", "某基金"],
     "known_for": ["关键事件1", "关键事件2"],
     "disambiguation": "区分同名人物的关键特征"
   }
3. Bio 注入到每次 check_relevance 调用中作为过滤基准
```

用户可通过 `--identity` 覆盖（JSON 字符串或文件路径），跳过 Phase 0。

---

## 5. 停止条件与循环上限

```python
# Acquisition agent 在每次 report_status 后评估
def should_stop(state):
    ab_count = len([s for s in state.artifacts if s.grade in ("A", "B")])
    total = len(state.artifacts)
    iterations = state.iteration_count
    
    if ab_count >= 5 and total >= 10:
        return True, "sufficient"
    if iterations >= 25:
        return True, "max_iterations"
    if state.consecutive_failures >= 5:
        return True, "exhausted"
    return False, None
```

---

## 6. Artifact 本地审计结构

每次运行产出完整审计树：

```
artifacts/
└── {slug}_{timestamp}/
    ├── manifest.json          # 所有 artifact 索引 + SHA256
    ├── bio_anchor.json        # Phase 0 合成的 Bio
    ├── agent_trace.jsonl      # 完整工具调用记录（input → output → relevance_score）
    ├── raw/                   # 原始抓取内容（按 source_id）
    │   ├── S01_web_tavily.txt
    │   ├── S02_youtube_transcript.txt
    │   ├── S03_podcast_audio.mp3
    │   ├── S04_podcast_transcription.txt
    │   └── ...
    └── graded/                # 评级后的有效语料
        ├── S01_A_grade.txt
        ├── S02_B_grade.txt
        └── corpus_manifest.json
```

`agent_trace.jsonl` 格式（每行一次工具调用）：

```json
{
  "iteration": 3,
  "tool": "search_podcast",
  "input": {"query": "张三 播客 2024"},
  "output_summary": "找到 3 条结果",
  "artifacts_created": ["S04"],
  "relevance_scores": {"S04": 8.5},
  "timestamp": "2026-04-23T10:32:01Z"
}
```

---

## 7. Claude 分析层（Phase 2）

### 7.1 模型与参数

```python
client = anthropic.Anthropic()

with client.messages.stream(
    model="claude-opus-4-7",
    max_tokens=16384,
    thinking={"type": "adaptive"},
    output_config={"effort": "xhigh"},
    system=[
        {   # AGENT.md — 静态，强制 cache
            "type": "text",
            "text": agent_md_content,
            "cache_control": {"type": "ephemeral"}
        },
        {   # 框架文档 — 静态，强制 cache
            "type": "text",
            "text": framework_docs,
            "cache_control": {"type": "ephemeral"}
        },
        {   # 输出 schema — 静态，强制 cache
            "type": "text",
            "text": output_schema,
            "cache_control": {"type": "ephemeral"}
        },
    ],
    messages=[{"role": "user", "content": user_message}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    
    final = stream.get_final_message()
```

### 7.2 Prompt Cache 收益

| 内容块 | 约 tokens | 每次调用节省 |
|--------|-----------|-------------|
| AGENT.md | ~2,000 | ✓ |
| 框架文档（4-8个） | ~6,000-10,000 | ✓ |
| output-schema.md | ~1,000 | ✓ |
| **合计** | **~9,000-13,000** | **~$0.04-0.07/次** |

Cache TTL = 5 分钟（Anthropic ephemeral）。同一个人的多次 quick/deep 分析会命中缓存。

### 7.3 AGENT.md 更新

当前 AGENT.md 第一行注明"语料由外部工程化管道构建好并注入"，在新范式下改为：

> 语料由 Acquisition Agent（Qwen 3.5）自主采集并审计，以 graded/ 目录中的语料注入；你的任务是**读语料 → 编码 → 产出报告**。

---

## 8. 文件结构变更

```
public-figure-profiler/
├── agent/
│   ├── agent.py              # [REWRITE] 双 orchestrator 入口
│   ├── AGENT.md              # [UPDATE] 一行描述更新
│   ├── acquisition/          # [NEW] 采集 agent 模块
│   │   ├── __init__.py
│   │   ├── loop.py           # Qwen 工具调用主循环
│   │   ├── tools/            # 每个工具一个文件
│   │   │   ├── search_web.py
│   │   │   ├── search_youtube.py
│   │   │   ├── search_podcast.py
│   │   │   ├── search_weibo.py
│   │   │   ├── search_zhihu.py
│   │   │   ├── search_bilibili.py
│   │   │   ├── search_twitter.py
│   │   │   ├── search_xiaohongshu.py
│   │   │   ├── fetch_content.py
│   │   │   ├── download_audio.py
│   │   │   ├── transcribe_audio.py
│   │   │   ├── check_relevance.py
│   │   │   ├── save_artifact.py
│   │   │   └── report_status.py
│   │   ├── identity.py       # Phase 0 Bio 合成
│   │   ├── grader.py         # A/B/C/D 评级逻辑（从 corpus/ 迁移）
│   │   └── artifacts.py      # Artifact 存储 + manifest + SHA256
│   ├── analysis/             # [NEW] 分析 agent 模块
│   │   ├── __init__.py
│   │   ├── prompt.py         # System prompt 构建（cache-aware）
│   │   └── runner.py         # Claude streaming 调用
│   └── corpus/               # [KEEP] 保留原 Web corpus pipeline（作为 search_web 后端）
│       ├── pipeline.py
│       ├── search.py
│       └── ...
├── references/               # [UNCHANGED]
├── profiles/                 # [UNCHANGED] 最终报告输出
├── artifacts/                # [NEW] 审计日志根目录（gitignore）
└── requirements.txt          # [UPDATE] 新增依赖
```

---

## 9. 新增 CLI 参数

```
新增：
  --identity FILE/JSON     覆盖自动 Bio 合成（跳过 Phase 0）
  --max-iterations N       采集 agent 最大迭代次数（默认 25）
  --min-ab-sources N       A/B 级最低数量门槛（默认 5）
  --skip-audio             跳过音频下载和转录（只做文字内容）
  --platforms LIST         限制平台（默认 all）
                           可选：web,youtube,podcast,weibo,zhihu,bilibili,twitter,xiaohongshu
  --artifacts-dir DIR      审计目录（默认 ./artifacts）
  --no-cache               禁用 prompt caching（调试用）

已有（保留）：
  --person, --purpose, --mode, --frameworks, --object-type
  --corpus（用户手动提供语料，直接进入 graded/）
  --output-dir, --max-output-tokens
```

---

## 10. 新增依赖

```
# requirements.txt 新增
yt-dlp>=2024.12.0         # 音频下载（YouTube/B站/播客）
podcastindex>=1.2.0       # Podcast Index API
httpx>=0.27.0             # 异步 HTTP 客户端
```

**Qwen 调用**：沿用现有 `openai` 库（OpenAI-compatible）

---

## 11. 环境变量

```bash
# 现有（保留）
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...

# 新增（Qwen acquisition agent）
DASHSCOPE_API_KEY=sk-sp-289ef966bb4040cdb893e1767811dca5
DASHSCOPE_BASE_URL=https://coding.dashscope.aliyuncs.com/v1

# 可选
PODCAST_INDEX_KEY=...       # Podcast Index API（免费申请）
PODCAST_INDEX_SECRET=...
YOUTUBE_API_KEY=...         # YouTube Data API v3（非必须，yt-dlp 可替代）
```

---

## 12. 运行示例

```bash
# 默认运行（全平台自动采集）
python -m agent.agent --person "Dario Amodei" --mode deep --purpose "投资尽调"

# 只用文字内容，跳过音频
python -m agent.agent --person "任正非" --skip-audio --object-type business

# 指定平台 + 手动提供语料
python -m agent.agent --person "李飞飞" \
    --platforms web,youtube,bilibili \
    --corpus my_notes.txt \
    --mode deep

# 使用已知 identity 跳过 Phase 0
python -m agent.agent --person "Obama" \
    --identity '{"name_variants":["Obama","Barack Obama"],"occupations":["politician"]}'
```

---

## 13. 实施阶段

| 阶段 | 内容 | 输出 |
|------|------|------|
| **P1** | Artifact 存储层 + grader 迁移 | `acquisition/artifacts.py`, `acquisition/grader.py` |
| **P2** | Identity anchor（Phase 0）| `acquisition/identity.py` |
| **P3** | 工具实现（搜索 4 个）| web, youtube, podcast, zhihu |
| **P4** | 工具实现（中文平台 3 个）| weibo, bilibili, xiaohongshu |
| **P5** | 音频工具 | download_audio, transcribe_audio |
| **P6** | check_relevance + save_artifact + report_status | 质控 + 流控工具 |
| **P7** | Qwen 工具调用主循环 | `acquisition/loop.py` |
| **P8** | Claude 分析层重构（caching + streaming）| `analysis/runner.py` |
| **P9** | agent.py 双 orchestrator 入口 | 主入口重写 |
| **P10** | 测试 + 文档更新 | pytest + README |

---

## 14. 关键约束

1. **工具是 Qwen 自主调用的**，不是 Python 代码硬编码顺序。如果某平台无结果，Qwen 自动换策略。
2. **所有采集结果本地留痕**：任何通过 save_artifact 写入的内容包含 SHA256，可验证真实抓取。
3. **Claude 只做分析**：不调用工具，不联网，只接受 graded/ 语料。
4. **prompt caching 必须开启**：system 中三个静态块都加 `cache_control`，分析成本降低 ~40%。
5. **噪音过滤两道门**：① check_relevance ≥ 6 分；② 全文提及目标人名 ≥ 3 次。
