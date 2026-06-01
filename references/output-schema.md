# 输出格式规范

> 所有引证必须带 `[Snn]` 来源编号，对应报告末尾的**参考文献**章节。
> 禁止模型自造 URL；source_id 必须来自当次分析的语料清单。

---

## Markdown 报告模板（Deep Mode）

```markdown
# [人物名] 认知与心理画像

> 分析模式：Deep | 分析日期：YYYY-MM-DD
> 用语说明：所有结论均基于公开表达，使用「呈现出……倾向」等措辞，不构成临床诊断。
> 启用框架：core, big5, loc, cit, lta, operational-code（示例）

---

## 分析元信息

| 项目 | 内容 |
|------|------|
| 分析目的 | [用户指定目的] |
| 语料来源 | A级: N篇 / B级: N篇 / C级: N篇 / D级: N篇 |
| 语料时间跨度 | YYYY – YYYY |
| 启用的分析框架 | core + big5 + loc + cit + ... |
| 整体置信度上限 | 高 / 中 / 低（受语料充分性影响） |

---

## 先验 vs 实际（偏差追踪）

| 分析前预设 | 验证结果 | 说明 |
|-----------|---------|------|
| [印象1] | ✓ 证实 / ✗ 推翻 / ~ 部分成立 | 「…」[S02] |
| [印象2] | ... | ... |

---

## 认知转折点时间轴

- [年份]：[事件] → [认知/表达的具体变化]，依据「…」[S04]
- [年份]：[事件] → [变化]，依据「…」[S07]

若无明显转折点，注明「在现有语料范围内，核心表达保持一致」。

---

## 矛盾日志

> 矛盾点是最高诊断价值的信号，优先列出。

### 矛盾 1：[主题]
- **场合 A**（[年份]，面向[受众]）：「[原文引证]」[S03]
- **场合 B**（[年份]，面向[受众]）：「[原文引证]」[S08]
- **可能解释：** 情境策略 / 真实转变 / 自我矛盾
- **置信度：** 高/中/低

---

## 画像主体

> 下列各节按启用的框架依次展开。每节末尾必须有**行为预测**。

### §1 人格与行事风格（core）

（按 core.md 的 Layer 1 输出）

### §2 认知结构（core）

（按 core.md 的 Layer 2 输出）

### §3 心理表征与叙事（core）

（按 core.md 的 Layer 3 输出）

### §4 受众敏感度（core）

（按 core.md 的受众敏感度维度输出）

### §5 Big Five 人格基线（big5）

（按 big5.md 模板）

### §6 控制点画像（loc）

（按 loc.md 模板）

### §7 关键事件分析（cit）

（按 cit.md 模板）

### §8 领导特质分析（lta，按激活框架）

（按 lta.md 模板）

### §9 代码操作分析（operational-code，按激活框架）

（按 operational-code.md 模板）

### §10 早期适应不良图式倾向（ems，按激活框架）

（按 ems.md 模板）

### §11 暗黑三联征倾向（dark-triad，按激活框架）

（按 dark-triad.md 模板，需通过伦理门槛）

---

## 置信度总览

| 维度 / 框架 | 置信度 | 引证数 | 说明 |
|-------------|--------|--------|------|
| 人格与行事风格 | 高/中/低 | N | |
| Big Five | 高/中/低 | N | |
| 控制点 | 高/中/低 | N | |
| 关键事件 | 高/中/低 | N | |
| ...（按启用框架） | | | |

---

## 研究局限性

- 所有结论仅基于公开表现，不反映私人情境
- 公开人物在镜头前有角色压力，需区分表演性表达与稳定特征
- [语料不足/语言限制/时间跨度等具体局限]
- [若启用 EMS 或 Dark Triad，重申"不构成临床诊断"]

---

## 参考文献

> 以下为本次分析引用的全部来源。每条带唯一 `Snn` 编号，正文引证用 `[Snn]` 回指。
> 格式：`[Snn] 标题. 发布者/作者. 发布日期 | 等级 | 来源 URL/路径 | 抓取日期`

- [S01] *长文标题*. 作者/出版方. 2024-11-11 | A级 | https://example.com/interview | 抓取于 2026-04-17
- [S02] ... 

（按 source_id 顺序列出所有语料）
```

---

## Quick Mode 输出模板

```markdown
# [人物名] 快速侧写

> 分析模式：Quick | 基于 [N] 篇来源 | [日期]
> 启用框架：core + big5（快速模式默认仅 2 个框架）

## 核心发现 1：[标题]

[2-3句分析]

> 引证：「[原文]」[S02, 2024, 播客]

**行为预测：** 在[情境]下，此人会……

---

## 核心发现 2-5 ...

---

## 参考文献

- [S01] ...
- [S02] ...

*完整侧写请使用 Deep Mode。*
```

---

## JSON Schema（Deep Mode）

```json
{
  "subject": "string — 人物全名",
  "analysis_date": "string — ISO8601 格式",
  "mode": "deep",
  "purpose": "string — 分析目的",
  "frameworks_enabled": ["core", "big5", "loc", "cit", "lta", "operational-code"],
  "corpus": {
    "a_level": "number",
    "b_level": "number",
    "c_level": "number",
    "d_level": "number",
    "time_span": "string — 例：2019-2026",
    "total_sources": "number"
  },
  "priors": ["string — 分析前的先验印象"],
  "inflection_points": [
    {
      "year": "number",
      "event": "string",
      "shift": "string",
      "source_ids": ["S04"]
    }
  ],
  "contradictions": [
    {
      "topic": "string",
      "statement_a": {
        "context": "string",
        "content": "string",
        "source_id": "S03"
      },
      "statement_b": {
        "context": "string",
        "content": "string",
        "source_id": "S08"
      },
      "interpretation": "situational_strategy | genuine_shift | self_contradiction"
    }
  ],
  "frameworks": {
    "core": {
      "personality": { "energy_direction": "...", "...": "..." },
      "cognitive_structure": { "...": "..." },
      "psychological_representations": { "...": "..." },
      "audience_sensitivity": { "...": "..." }
    },
    "big5": {
      "openness": "high|medium|low",
      "conscientiousness": "...",
      "extraversion": "...",
      "agreeableness": "...",
      "neuroticism": "...",
      "findings": "string",
      "source_ids": ["S02", "S04"],
      "confidence": "high|medium|low"
    },
    "loc": {
      "work_achievement": "strong_internal|internal|context_dependent|external|strong_external",
      "interpersonal": "...",
      "sociopolitical": "...",
      "overall": "...",
      "attribution_bias": "self_serving | stable_internal | stable_external",
      "findings": "string",
      "source_ids": ["..."],
      "confidence": "..."
    },
    "cit": {
      "critical_incidents": [
        {
          "title": "string",
          "date": "YYYY-MM-DD",
          "situation": "string",
          "tension": "string",
          "action": "string (原文引证)",
          "result": "string",
          "reflection": "string",
          "signal": "string",
          "source_ids": ["S04"]
        }
      ],
      "cross_event_patterns": ["string"],
      "behavior_prediction": "string"
    },
    "lta": {
      "need_for_power": "high|medium|low",
      "belief_in_control": "...",
      "conceptual_complexity": "...",
      "self_confidence": "...",
      "task_vs_affective": "task|balanced|affective",
      "distrust_of_others": "...",
      "ingroup_bias": "...",
      "leadership_type": "challenge_constraints|respect_constraints|mixed",
      "findings": "string",
      "source_ids": ["..."],
      "confidence": "..."
    },
    "operational_code": {
      "philosophical": {
        "p1_nature": "conflict|harmony|mixed",
        "p2_optimism": "optimistic|pessimistic|conditional",
        "p3_predictability": "high|medium|low",
        "p4_driving_force": "individual|group|system|chance",
        "p5_control_over_history": "high|medium|low"
      },
      "instrumental": {
        "i1_best_approach": "string",
        "i2_efficiency_vs_prudence": "efficiency|prudence|balanced",
        "i3_risk": "active|avoid|diversify",
        "i4_timing": "preemptive|wait|reactive",
        "i5_means_ranking": ["string"]
      },
      "source_ids": ["..."],
      "confidence": "..."
    },
    "ems": {
      "observed_schemas": [
        {
          "schema": "entitlement_grandiosity",
          "domain": "impaired_limits",
          "confidence": "high|medium|low",
          "source_ids": ["S02", "S05", "S08", "S11"],
          "cross_context_count": "number"
        }
      ],
      "stable_schemas": ["..."],
      "situational_schemas": ["..."],
      "disclaimer": "不构成临床诊断"
    },
    "dark_triad": {
      "enabled": "true|false",
      "narcissism": "grandiose|vulnerable|mixed|low|N/A",
      "machiavellianism": "high|medium|low|N/A",
      "psychopathy": "signal|none|N/A",
      "bigfive_crosscheck": "consistent|partial|inconsistent",
      "source_ids": ["..."],
      "ethical_note": "string"
    }
  },
  "priors_validation": {
    "confirmed": ["string"],
    "refuted": ["string"],
    "new_findings": ["string"]
  },
  "overall_confidence": "high|medium|low",
  "corpus_adequacy": "sufficient|sparse|insufficient",
  "limitations": ["string"],
  "sources": [
    {
      "source_id": "S01",
      "title": "string",
      "url_or_path": "string",
      "grade": "A|B|C|D",
      "published_date": "YYYY-MM-DD|unknown",
      "accessed_date": "YYYY-MM-DD",
      "origin": "user_file|web_search|youtube|wikipedia",
      "word_count": "number",
      "language": "zh|en|other"
    }
  ]
}
```
