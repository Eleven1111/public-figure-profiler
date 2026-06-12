"""定量语言标记：对语料做纯 Python 词频统计，为 LLM 分析提供客观锚点。

Hermann LTA 原版是定量方法（标记词频率对常模），LLM 印象式打分会丢失这一层。
本模块在 prompt 注入前对全部语料计算：
  - 限定词密度（hedge）vs 绝对化词密度（absolutist）→ 概念复杂度 CC 的客观锚点
  - 第一人称单数 vs 复数比例 → 自信心 SC / 任务-群体聚焦的锚点
  - 权力动词密度 → nPow 锚点
  - 因果连词密度 → 因果推理密度的锚点
  - 不信任词密度 → DIS 锚点

只统计**本人第一人称语料**（stance=first_person 或用户提供）时最准确；
混入第三方报道会稀释信号，故按 stance 分组输出。
LLM 拿到数字后负责解释，不再负责计数。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


_MARKER_SETS: dict[str, list[str]] = {
    "hedge": [
        # 中文
        "可能", "或许", "也许", "某种程度", "一定程度", "通常", "往往", "大概",
        "未必", "不一定", "相对来说", "在某些情况", "倾向于", "似乎",
        # 英文
        " might ", " maybe ", " perhaps ", " probably ", " somewhat ",
        " to some extent ", " in some cases ", " it depends ", " arguably ",
        " tend to ", " likely ",
    ],
    "absolutist": [
        "绝对", "永远", "总是", "从来", "毫无疑问", "必然", "一定是", "所有人",
        "没有人", "不可能", "完全错误", "唯一",
        " always ", " never ", " absolutely ", " definitely ", " undoubtedly ",
        " everyone ", " no one ", " impossible ", " certainly ", " the only ",
    ],
    "power_verbs": [
        "控制", "主导", "支配", "征服", "战胜", "压制", "击败", "说服", "影响力",
        "掌控", "统治", "碾压", "赢得",
        " control ", " dominate ", " conquer ", " defeat ", " crush ",
        " persuade ", " influence ", " win ", " beat ",
    ],
    "causal": [
        "因为", "所以", "因此", "由于", "导致", "从而", "由此", "如果", "那么",
        "意味着", "结果是",
        " because ", " therefore ", " thus ", " hence ", " leads to ",
        " results in ", " if ", " then ", " consequently ", " so that ",
    ],
    "distrust": [
        "阴谋", "背后", "别有用心", "真实意图", "居心", "暗中", "欺骗", "出卖",
        "背叛", "不可信",
        " conspiracy ", " hidden agenda ", " real intention ", " betray ",
        " deceive ", " can't trust ", " behind my back ",
    ],
    "first_person_singular": [
        "我认为", "我觉得", "我决定", "我相信", "我的判断", "我会", "我要", "我说",
        " i think ", " i believe ", " i decided ", " i will ", " my view ",
        " in my opinion ", " i'm convinced ",
    ],
    "first_person_plural": [
        "我们认为", "我们觉得", "我们决定", "我们相信", "我们会", "我们要",
        "团队", "大家一起",
        " we think ", " we believe ", " we decided ", " we will ", " our team ",
        " together we ",
    ],
}


@dataclass
class MarkerProfile:
    """每千字标记密度。"""
    total_chars: int
    counts: dict[str, int] = field(default_factory=dict)

    def density(self, key: str) -> float:
        if self.total_chars <= 0:
            return 0.0
        return self.counts.get(key, 0) / self.total_chars * 1000


def count_markers(text: str) -> dict[str, int]:
    # 标点替换为空格再首尾加空格：英文标记词依赖空格边界（" perhaps "），
    # 否则 "work, perhaps." 这类紧邻标点的出现会被漏计
    lower = " " + re.sub(r"[^\w一-鿿]+", " ", text.lower()) + " "
    return {
        key: sum(lower.count(marker.lower()) for marker in markers)
        for key, markers in _MARKER_SETS.items()
    }


def profile_text(text: str) -> MarkerProfile:
    return MarkerProfile(total_chars=len(text), counts=count_markers(text))


def profile_corpus(sources: list[dict]) -> dict[str, MarkerProfile]:
    """按 stance 分组统计：first_person 组是核心信号，other 组仅供对照。"""
    groups: dict[str, list[str]] = {"first_person": [], "other": []}
    for s in sources:
        key = "first_person" if s.get("stance") == "first_person" or s.get(
            "origin"
        ) == "user_file" else "other"
        groups[key].append(s.get("content", ""))

    return {
        name: profile_text("\n".join(texts))
        for name, texts in groups.items()
        if texts
    }


_LABELS = {
    "hedge": "限定词（hedge）",
    "absolutist": "绝对化词",
    "power_verbs": "权力动词",
    "causal": "因果连词",
    "distrust": "不信任词",
    "first_person_singular": "第一人称单数主张（我认为/I think）",
    "first_person_plural": "第一人称复数主张（我们/we）",
}


def markers_summary(sources: list[dict]) -> str:
    """生成注入 prompt 的客观标记摘要。"""
    profiles = profile_corpus(sources)
    if not profiles:
        return ""

    lines = [
        "# 定量语言标记（程序统计，非模型估计）",
        "",
        "以下为语料的标记词密度（每千字出现次数）。这是客观计数结果，",
        "请将其作为 LTA 概念复杂度/自信心/权力需求、core 因果推理密度等维度的锚点：",
        "结论与数字矛盾时必须解释原因，不得忽略。",
        "first_person 组（本人第一人称语料）是核心信号；other 组（第三方报道）仅供对照，",
        "其中的标记词反映的是记者而非本人的语言。",
        "",
        "| 标记 | " + " | ".join(profiles.keys()) + " |",
        "|------|" + "---|" * len(profiles),
    ]
    for key, label in _LABELS.items():
        row = [f"{p.density(key):.2f}" for p in profiles.values()]
        lines.append(f"| {label} | " + " | ".join(row) + " |")

    fp = profiles.get("first_person")
    if fp:
        hedge, absolutist = fp.density("hedge"), fp.density("absolutist")
        if hedge or absolutist:
            ratio = hedge / absolutist if absolutist else float("inf")
            lines.append("")
            lines.append(
                f"限定词/绝对化比值（first_person）：{ratio:.2f} "
                "（>2 提示高概念复杂度，<0.8 提示教条化倾向，仅为锚点非结论）"
            )
    return "\n".join(lines)
