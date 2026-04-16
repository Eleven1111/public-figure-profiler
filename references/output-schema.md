# 输出格式规范

## Markdown 报告模板（Deep Mode）

```markdown
# [人物名] 认知与心理画像

> 分析模式：Deep | 分析日期：YYYY-MM-DD
> 用语说明：所有结论均基于公开表达，使用「呈现出……倾向」等措辞，不构成临床诊断。

---

## 分析元信息

| 项目 | 内容 |
|------|------|
| 分析目的 | [用户指定目的] |
| 语料来源 | A级: N篇 / B级: N篇 / C级: N篇 / D级: N篇 |
| 语料时间跨度 | YYYY – YYYY |
| 整体置信度上限 | 高 / 中 / 低（受语料充分性影响） |

---

## 先验 vs 实际（偏差追踪）

| 分析前预设 | 验证结果 | 说明 |
|-----------|---------|------|
| [印象1] | ✓ 证实 / ✗ 推翻 / ~ 部分成立 | [引证或说明] |
| [印象2] | ... | ... |

---

## 认知转折点时间轴

- [年份]：[事件] → [认知/表达的具体变化]
- [年份]：[事件] → [变化]

若无明显转折点，注明「在现有语料范围内，核心表达保持一致」。

---

## 矛盾日志

> 矛盾点是最高诊断价值的信号，优先列出。

### 矛盾 1：[主题]
- **场合 A**（[年份]，面向[受众]）：「[原文引证]」
- **场合 B**（[年份]，面向[受众]）：「[原文引证]」
- **可能解释：** 情境策略 / 真实转变 / 自我矛盾
- **置信度：** 高/中/低

---

## 画像主体

### 人格与行事风格

**能量方向：** [内向倾向 / 外向倾向 / 情境依赖]

[分析内容，100-200字，含≥1条原文引证]

**风险偏好：** [求稳 / 中性 / 求险]

[分析内容]

**时间尺度：** [季度 / 年度 / 十年+]

[分析内容]

**决策模式：** [独断 / 集体 / 数据驱动 / 实验试错 / 混合]

[分析内容]

**置信度：** 高/中/低 | **引证数：** N

**行为预测：** 在[具体情境，如「面临监管压力时」]，此人倾向于……

---

### 认知结构

**主用世界模型：** [技术–经济 / 制度–博弈 / 道德–价值 / 混合]

[分析内容]

**不确定性处理：** [期望值思维 / 红线约束思维 / 混合]

[分析内容]

**因果推理密度：** [高因果密度 / 中等因果密度 / 低因果密度]

[分析内容]

**置信度：** 高/中/低 | **引证数：** N

**行为预测：** 在[情境]下，此人倾向于……

---

### 心理表征与叙事

**核心隐喻：**

| 隐喻 | 原文引证 | 心理解读 |
|------|---------|---------|
| [事物] 比作 [X] | 「[原文]」 | [这个比喻揭示了什么？] |

**自我角色定位：** [守门人 / 建设者 / 协调者 / 研究者 / 反对者]

[分析内容]

**核心价值词频：**

| 词 | 典型语境 | 推断的价值排序 |
|----|---------|--------------|
| [词] | [使用场景] | [优先于什么？] |

**置信度：** 高/中/低 | **引证数：** N

**行为预测：** ……

---

### 受众敏感度

**等级：** [高敏感 / 中等 / 低敏感 / 异常高敏感]

[跨受众对比分析]

**置信度：** 高/中/低

**行为预测：** ……

---

## 置信度总览

| 维度 | 置信度 | 引证数 | 说明 |
|------|--------|--------|------|
| 人格与行事风格 | 高/中/低 | N | |
| 认知结构 | 高/中/低 | N | |
| 心理表征与叙事 | 高/中/低 | N | |
| 受众敏感度 | 高/中/低 | N | |

---

## 研究局限性

- 所有结论仅基于公开表现，不反映私人情境
- 公开人物在镜头前有角色压力，需区分表演性表达与稳定特征
- [语料不足/语言限制/时间跨度等具体局限]
```

---

## Quick Mode 输出模板

```markdown
# [人物名] 快速侧写

> 分析模式：Quick | 基于 [N] 篇来源 | [日期]

## 核心发现 1：[标题]

[2-3句分析]

> 引证：「[原文]」——[来源，年份]

**行为预测：** 在[情境]下，此人会……

---

## 核心发现 2：[标题]

[2-3句分析]

> 引证：「[原文]」

**行为预测：** ……

---

## 核心发现 3：[标题]

[2-3句分析]

> 引证：「[原文]」

**行为预测：** ……

---

*完整侧写请使用 Deep Mode。置信度受语料数量影响，建议提供额外文字稿提升质量。*
```

---

## JSON Schema（Deep Mode）

```json
{
  "subject": "string — 人物全名",
  "analysis_date": "string — ISO8601 格式",
  "mode": "deep",
  "purpose": "string — 分析目的",
  "corpus": {
    "a_level": "number",
    "b_level": "number",
    "c_level": "number",
    "d_level": "number",
    "time_span": "string — 例：2019-2026"
  },
  "priors": ["string — 分析前的先验印象"],
  "inflection_points": [
    {
      "year": "number",
      "event": "string",
      "shift": "string — 认知/表达的具体变化"
    }
  ],
  "contradictions": [
    {
      "topic": "string",
      "statement_a": {
        "context": "string — 场合、年份、受众",
        "content": "string — 原文引证"
      },
      "statement_b": {
        "context": "string",
        "content": "string"
      },
      "interpretation": "situational_strategy | genuine_shift | self_contradiction"
    }
  ],
  "dimensions": {
    "personality": {
      "energy_direction": "introverted | extroverted | context_dependent",
      "risk_appetite": "conservative | neutral | aggressive",
      "time_horizon": "quarterly | annual | decade_plus",
      "decision_style": "autocratic | collective | data_driven | experimental | mixed",
      "findings": "string",
      "confidence": "high | medium | low",
      "evidence_count": "number",
      "prediction": "string"
    },
    "cognitive_structure": {
      "primary_model": "techno_economic | institutional_game | moral_value | mixed",
      "uncertainty_handling": "expected_value | red_line | mixed",
      "causal_density": "high | medium | low",
      "findings": "string",
      "confidence": "high | medium | low",
      "evidence_count": "number",
      "prediction": "string"
    },
    "psychological_representations": {
      "core_metaphors": [
        {
          "entity": "string — 被比喻的事物",
          "metaphor": "string — 比喻对象",
          "quote": "string — 原文",
          "interpretation": "string"
        }
      ],
      "self_role": "gatekeeper | builder | coordinator | researcher | opponent | mixed",
      "core_value_words": [
        {
          "word": "string",
          "context": "string",
          "priority_rank": "number — 相对排序"
        }
      ],
      "findings": "string",
      "confidence": "high | medium | low",
      "evidence_count": "number",
      "prediction": "string"
    },
    "audience_sensitivity": {
      "level": "high | medium | low | anomalously_high",
      "findings": "string",
      "confidence": "high | medium | low",
      "evidence_count": "number",
      "prediction": "string"
    }
  },
  "priors_validation": {
    "confirmed": ["string"],
    "refuted": ["string"],
    "new_findings": ["string"]
  },
  "overall_confidence": "high | medium | low",
  "corpus_adequacy": "sufficient | sparse | insufficient",
  "limitations": ["string"]
}
```
