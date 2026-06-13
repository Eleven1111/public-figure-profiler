# 分析框架索引（Framework Registry）

> 所有框架模块独立存在。通过 CLI `--frameworks` 参数激活或组合。
> 每个模块定义：触发条件、操作化指标（基于公开文本可观察）、最小引证要求、N/A 回退规则。

## 核心原则

1. **引证优先**：每条结论必须关联 ≥N 条原文引证（N 由各框架自定），达不到标 `N/A — 语料不足`。
2. **不做临床诊断**：心理学框架（EMS、Dark Triad）均以「倾向」「模式」措辞，禁止「诊断」「障碍」。
3. **引证可追溯**：每条引用必须带 `[Snn]` 来源编号，对应报告末尾的参考文献章节。
4. **跨情境验证**：同一结论需在 ≥2 个不同场合（播客/听证/深访/文章）被观察到才算「高置信」。

## 框架清单

| 模块 | 学派来源 | 核心问题 | 默认激活 | 最小引证/维度 |
|------|---------|----------|----------|---------------|
| [core.md](core.md) | 自建（行为编码 + 受众敏感度） | 行事风格 + 认知结构 + 心理表征 | ✓ | 2 |
| [big5.md](big5.md) | Costa & McCrae（OCEAN） | 五大人格基线，可量化 | ✓ | 3 |
| [loc.md](loc.md) | Julian Rotter | 控制点：成败归因于内/外？ | ✓ | 3 |
| [cit.md](cit.md) | John Flanagan | 关键事件技术：真实行为 > 自我陈述 | ✓ | 每事件 1 |
| [ems.md](ems.md) | Jeffrey Young | 早期适应不良图式：18 种持久认知情绪模式 | 可选 | 4（谨慎） |
| [lta.md](lta.md) | Margaret Hermann | 领导特质分析：7 特质 | 商业/政治领导人默认 | 3 |
| [operational-code.md](operational-code.md) | Alexander George | 代码操作：10 问信念系统 | 政治/外交对象默认 | 2 |
| [motives.md](motives.md) | McClelland / Winter | 三动机：驱动他的是成就、控制还是归属？ | ✓ | 3 |
| [values-hierarchy.md](values-hierarchy.md) | Schwartz 十价值环 | 价值层级：取舍时刻暴露的真实排序 | ✓ | 2（取舍时刻） |
| [interests.md](interests.md) | 自建（相关方 + 显示性偏好 + 激励） | 利益结构：此刻什么对他有利？ | 商业/政治默认 | 言+行各 1 |
| [depth.md](depth.md) | 心理动力学（去临床化） | 深层动力：身份支柱/核心恐惧/核心冲突——他为什么长成这样？ | ✓（最后执行） | 见框架内分维度门槛 |
| [dark-triad.md](dark-triad.md) | Paulhus & Williams | 自恋/马基雅维利/精神病态倾向 | 默认关（伦理敏感） | 5（极谨慎） |

## 对象类型 → 默认框架组合

| 对象类型 | 默认框架 |
|----------|---------|
| 企业家 / 商业领导人 | core + big5 + loc + cit + lta + motives + values-hierarchy + interests + depth |
| 政治家 / 国家领导人 | core + big5 + loc + cit + lta + operational-code + motives + values-hierarchy + interests + depth |
| 学者 / 思想家 | core + big5 + loc + cit + motives + values-hierarchy + depth |
| 艺术家 / 文化人物 | core + big5 + loc + cit + motives + values-hierarchy + depth |
| 通用 / 未分类 | core + big5 + loc + cit + motives + values-hierarchy + depth |

CLI 示例：
```bash
# 显式指定
--frameworks core,big5,loc,lta,cit,operational-code

# 使用默认组合（自动按对象类型推断）
--auto-frameworks

# 全量（慎用，输出冗长）
--frameworks all
```

## 引证体系（全框架通用）

- 每个来源分配唯一 `source_id`：`S01`, `S02`, ...
- 引证格式：`「原文」[S03, 2024-11-11, 播客]`
- 报告末尾必须有「## 参考文献」章节，列出所有 `source_id` 的完整元数据
- 禁止模型自造 URL；引用的 source_id 必须存在于语料清单
