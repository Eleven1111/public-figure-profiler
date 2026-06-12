# Public Figure Profiler

对任意有足够公开语料的人物进行**多框架**系统性认知与心理侧写分析。

- **工程化语料采集**：Tavily/SerpAPI/Brave 搜索 + 正文抓取 + YouTube 字幕 + 维基百科；强制采集批评性来源与行为事实类来源
- **十一个可插拔分析框架**：core、big5、loc、cit、lta、operational-code、motives、values-hierarchy、interests、ems、dark-triad
- **强制引证链条**：每条结论带 `[Snn]` 编号，对应报告末尾参考文献；分析后自动做引文真实性机器校验
- **结构化推理**：矛盾点走 ACH 竞争性假设矩阵；LTA 等维度有纯 Python 词频统计做客观锚点
- **言行三角验证**：言语结论对照可核实行为记录，背离条目强制进矛盾日志
- **综合心智模型**：全框架压缩为一页「决策函数」——核心驱动 × 价值排序 × 利益约束
- **人物档案库**：claims 注册表跨次合并 + 结论 diff + 可证伪预测台账（支持事后 resolve 校准命中率）

支持两种使用方式：
- **Claude Code Skill**：交互式，用户在场，随时调整
- **Hermes Agent CLI**：自主运行，无人值守，产出文件

---

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 采集 agent：自动采集公开语料时必需
export DASHSCOPE_API_KEY=sk_xxx

# 分析后端（二选一或都配置）
# Claude Code：确保 `claude -p "hello"` 可运行，可用 ANTHROPIC_API_KEY 或本机登录态
export ANTHROPIC_API_KEY=your_key_here
# Codex CLI：确保 `codex exec "hello"` 可运行，可用本机登录态或 OpenAI API 配置
export OPENAI_API_KEY=your_key_here

# 搜索引擎（可选；未设置则降级 DuckDuckGo 免 Key 模式）
export TAVILY_API_KEY=tvly_xxx            # 推荐，LLM-native
```

---

## CLI 使用

```bash
# 默认框架组合（core+big5+loc+cit），自动抓取语料
python -m agent.agent --person "Jensen Huang" --mode deep --purpose "投资尽调"

# 使用 Codex CLI 做分析
python -m agent.agent --person "Jensen Huang" --analysis-backend codex

# 同一份语料分别交给 Claude Code 和 Codex CLI 分析
python -m agent.agent --person "Sam Altman" --analysis-backend both

# 商业人物 preset（自动叠加 lta）
python -m agent.agent --person "任正非" --object-type business

# 政治人物 preset（叠加 lta + operational-code）
python -m agent.agent --person "Angela Merkel" --object-type political

# 显式指定框架组合
python -m agent.agent --person "Sam Altman" --mode deep \
  --frameworks core,big5,loc,cit,lta,operational-code

# 启用全部非伦理敏感框架
python -m agent.agent --person "Elon Musk" --frameworks all

# 启用全部 + dark-triad（需自己确认伦理门槛）
python -m agent.agent --person "Elon Musk" --frameworks all+dark-triad

# 附加本地语料（A 级）
python -m agent.agent --person "Sam Altman" --mode deep \
  --corpus ./interviews/altman_2024.txt

# 仅使用本地语料，跳过 Qwen 自动采集（不需要 DASHSCOPE_API_KEY）
python -m agent.agent --person "Sam Altman" --skip-acquisition \
  --corpus ./interviews/altman_2024.txt

# 指定分析模型
python -m agent.agent --person "李飞飞" --analysis-backend codex --codex-model gpt-5.3-codex
python -m agent.agent --person "李飞飞" --analysis-backend claude --claude-model claude-sonnet-4-6
```

---

## 分析框架

所有框架以独立 markdown 文件定义在 `references/frameworks/`，可单独启用。

| 代号 | 名称 | 来源 | 适用 |
|------|------|------|------|
| `core` | 三层认知与心理画像 | 自研综合 | **默认强制，永远第一个** |
| `big5` | Big Five / OCEAN 人格 | Costa & McCrae | 人格基线 |
| `loc` | Locus of Control 控制点 | Julian Rotter | 归因风格、成败解释 |
| `cit` | Critical Incident Technique 关键事件 | John Flanagan | 危机决策、拐点分析 |
| `lta` | Leadership Trait Analysis 领导特质 | Margaret Hermann | 领导者（商业/政治） |
| `operational-code` | 代码操作技术 | Alexander George | 政治/战略决策者 |
| `motives` | 三动机分析（nAch/nPow/nAff） | McClelland / Winter | 核心驱动：成就、控制还是归属 |
| `values-hierarchy` | 价值观层级（取舍验证） | Schwartz | 宣称性 vs 显示性价值排序 |
| `interests` | 利益结构图谱 | 自研（相关方+显示性偏好+激励） | 利益取向、激励拐点预测 |
| `ems` | Early Maladaptive Schemas 早期图式 | Jeffrey Young | **伦理高门槛**，≥4 引证 |
| `dark-triad` | 暗黑三联征 | Paulhus & Williams | **伦理极高门槛**，默认关闭，需 Big Five 交叉验证 |

### 对象类型预设

通过 `--object-type` 快速套用组合：

| Preset | 激活框架 |
|--------|---------|
| `general`（默认） | core + big5 + loc + cit + motives + values-hierarchy |
| `business` | general 基础 + lta + interests |
| `political` | general 基础 + lta + operational-code + interests |
| `scholar` | 同 general |
| `artist` | 同 general |

`--frameworks` 如果显式指定，会覆盖 `--object-type`。

---

## 语料质量分级

| 等级 | 类型 | 分析权重 |
|------|------|---------|
| A | 长篇未剪辑访谈、播客原稿、听证会证词、完整对谈转录 | 高 |
| B | 专题深访、圆桌发言、长篇媒体报道 | 中高 |
| C | 公开信、长文博客、Substack | 中 |
| D | 声明、PR 稿、演讲稿、维基百科 | 低（参考） |

**充分性判定**（由 `references/frameworks/core.md` 定义，按**独立来源数**计算——
转载/编译/同一采访的多平台分发自动归并为 1 个独立来源）：
- 充分：独立 A/B ≥3 篇且时间跨度 ≥2 年 → 正常执行
- 偏少：独立 A/B 1–2 篇 → 整体置信度上限「中」
- 不足：仅 C/D → 进入探索性草稿模式

---

## 输出

```
profiles/
├── jensen_huang_20260417.md              # Markdown 侧写报告（含参考文献章节）
├── jensen_huang_20260417.json            # JSON 结构化数据（Deep Mode）
├── jensen_huang_20260417.verification.md # 引文真实性校验报告（自动生成）
└── jensen_huang_20260417_corpus/         # 语料缓存
    ├── S01_a_grade.txt                   # 按 source_id 命名
    ├── S02_b_grade.txt
    ├── ...
    └── corpus_manifest.json              # 包含 source_id / url / grade / published_date

dossiers/                                 # 人物档案库（跨次分析沉淀）
└── jensen_huang/
    ├── dossier.json                      # 档案元信息 + 历次分析记录
    ├── claims.json                       # 结论注册表（跨次合并，带变更历史）
    ├── predictions.jsonl                 # 可证伪预测台账
    └── diffs/diff_20260601_0900.md       # 与上次分析的结论对比
```

报告结构（Deep Mode）：
- 先验申报 → 时间轴 → 言行三角验证 → 矛盾日志（ACH 矩阵）→ 各框架画像 →
  综合心智模型（决策函数 + 三条最高置信预测）→ 置信度总览 → 研究局限性 → **参考文献**

### 人物档案库 CLI

```bash
# 查看档案的结论与预测
python -m agent.dossier list --person "Jensen Huang"

# 预测应验/落空后判定（持续校准置信度的真实含义）
python -m agent.dossier resolve --person "Jensen Huang" --id P001 --outcome hit --note "已被新闻证实"

# 按置信度统计预测命中率
python -m agent.dossier calibration --person "Jensen Huang"
```

---

## 开发

```bash
# 跑全部测试（127 个）
pytest tests/ -v

# 仅 agent 主流程测试
pytest tests/test_agent.py -v

# 仅语料管道测试
pytest tests/test_corpus.py -v
```

---

## 环境变量一览

| 变量 | 作用 | 必需 |
|------|------|------|
| `DASHSCOPE_API_KEY` | Qwen 采集 agent 与相关性审计 | 自动采集必需；`--skip-acquisition` 可不需要 |
| `DASHSCOPE_BASE_URL` | DashScope OpenAI-compatible endpoint | 可选 |
| `DASHSCOPE_MODEL` | Qwen 采集模型 | 可选，默认 `qwen3.5-plus` |
| `ANTHROPIC_API_KEY` | Claude Code 分析后端 | 使用 `--analysis-backend claude` 且无本机登录态时必需 |
| `OPENAI_API_KEY` | Codex CLI 分析后端 | 使用 `--analysis-backend codex` 且无本机登录态时必需 |
| `TAVILY_API_KEY` | Tavily 搜索引擎 | 可选，未设置则降级 DuckDuckGo |

---

## 伦理声明

- 所有输出基于**公开表达**，不构成临床诊断
- 不推测私人生活、家庭关系、健康状况、童年经历
- EMS / Dark Triad 框架有强制伦理门槛和 disclaimer
- 所有引证必须带 `[Snn]` 编号，禁止模型自造 URL 或来源
