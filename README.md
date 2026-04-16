# Public Figure Profiler

对任意有足够公开语料的人物进行系统性认知与心理侧写分析。

支持两种使用方式：
- **Claude Code Skill**：交互式，用户在场，随时调整
- **Hermes Agent CLI**：自主运行，无人值守，产出文件

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## CLI 使用

```bash
# 快速侧写（3个核心发现）
python -m agent.agent --person "Jensen Huang" --mode quick

# 完整侧写（报告 + JSON）
python -m agent.agent --person "任正非" --mode deep --purpose "竞争对手研究"

# 附加自有语料
python -m agent.agent --person "Sam Altman" --mode deep \
  --corpus ./interviews/altman_2024.txt \
  --corpus ./interviews/altman_2023.txt

# 从 YouTube 提取字幕作为语料
python -m agent.agent --person "Sam Altman" --mode deep \
  --youtube "https://www.youtube.com/watch?v=VIDEO_ID"

# 指定输出目录
python -m agent.agent --person "Satya Nadella" --mode deep --output-dir ./my_profiles
```

## 输出

```
profiles/
├── jensen_huang_20260415.md        # Markdown 侧写报告
├── jensen_huang_20260415.json      # JSON 结构化数据（Deep Mode）
└── jensen_huang_20260415_corpus/   # 语料缓存
    ├── source_01_a_grade.txt
    └── corpus_manifest.json
```

## 语料质量分级

| 等级 | 类型 | 分析权重 |
|------|------|---------|
| A | 长篇未剪辑访谈、播客原稿、听证会证词 | 高 |
| B | 专题深访、圆桌发言 | 中高 |
| C | 公开信、长文博客 | 中 |
| D | 声明、PR 稿 | 低（参考） |

## 开发

```bash
pytest tests/ -v
```

## 分析框架

见 `references/codebook.md`。三层框架：人格与行事风格、认知结构、心理表征与叙事，
外加受众敏感度维度。所有结论必须有原始文本引证；置信度精确分级。
