"""定量语言标记测试。"""
from agent.analysis.markers import (
    count_markers,
    markers_summary,
    profile_corpus,
    profile_text,
)


HEDGED = "我觉得这可能是对的，某种程度上也许成立，通常如此但未必绝对。"
ABSOLUTIST = "毫无疑问这绝对正确，永远如此，所有人都同意，没有人反对，这是唯一的路。"


def test_count_markers_hedge_vs_absolutist():
    h = count_markers(HEDGED)
    a = count_markers(ABSOLUTIST)
    assert h["hedge"] > h["absolutist"]
    assert a["absolutist"] > a["hedge"]


def test_count_markers_english():
    text = " I think this might work, perhaps. Because of that, we will dominate and control the market. "
    c = count_markers(text)
    assert c["hedge"] >= 2
    assert c["power_verbs"] >= 2
    assert c["causal"] >= 1
    assert c["first_person_singular"] >= 1


def test_profile_text_density():
    p = profile_text(ABSOLUTIST)
    assert p.total_chars == len(ABSOLUTIST)
    assert p.density("absolutist") > 0


def test_profile_corpus_groups_by_stance():
    sources = [
        {"content": HEDGED, "stance": "first_person"},
        {"content": ABSOLUTIST, "stance": "neutral"},
    ]
    profiles = profile_corpus(sources)
    assert set(profiles) == {"first_person", "other"}
    assert profiles["first_person"].counts["hedge"] > 0


def test_user_file_counts_as_first_person():
    sources = [{"content": HEDGED, "origin": "user_file"}]
    profiles = profile_corpus(sources)
    assert "first_person" in profiles


def test_markers_summary_renders_table():
    sources = [{"content": HEDGED, "stance": "first_person"}]
    summary = markers_summary(sources)
    assert "定量语言标记" in summary
    assert "限定词" in summary
    assert "first_person" in summary


def test_markers_summary_empty_corpus():
    assert markers_summary([]) == ""
