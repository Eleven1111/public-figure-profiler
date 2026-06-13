"""P1 证据层测试：同源传播检测、独立来源计数、stance 分类、对抗配额。"""
from agent.acquisition.tools.quality import report_status
from agent.agent import assess_corpus_adequacy, resolve_frameworks
from agent.corpus.dedupe import independent_ab_count, mark_syndication
from agent.corpus.grader import classify_stance


BASE_TEXT = (
    "黄峥在接受采访时表示，简单和常识的力量是他最重要的认知基石。"
    "他回忆起与段永平共进午餐的经历，认为那顿饭让他理解了本分的含义。"
    "在谈到拼多多的发展时，他强调错位竞争的重要性，认为与淘宝争夺的是"
    "同一批用户的不同场景。他还提到活着是创业的第一要务，选择比努力更重要，"
    "在正确的道路上前行哪怕慢一点也没有关系。" * 5
)


def _syndicated_copy() -> str:
    # 模拟转载：加编者按 + 删一句
    return "【编者按】本文转载自原刊。\n" + BASE_TEXT[:len(BASE_TEXT) // 2] + BASE_TEXT[len(BASE_TEXT) // 2 + 50:]


def test_mark_syndication_groups_reprints():
    sources = [
        {"source_id": "S01", "grade": "A", "content": BASE_TEXT},
        {"source_id": "S02", "grade": "B", "content": _syndicated_copy()},
        {"source_id": "S03", "grade": "B", "content": "完全不同的另一篇关于公司治理结构与董事会运作机制的长篇深度报道。" * 20},
    ]
    mark_syndication(sources)
    assert sources[0]["independent_id"] == sources[1]["independent_id"]
    assert sources[1]["syndication_of"] == "S01"
    assert sources[2]["independent_id"] != sources[0]["independent_id"]
    assert sources[2]["syndication_of"] == ""


def test_independent_ab_count_collapses_groups():
    sources = [
        {"source_id": "S01", "grade": "A", "independent_id": "I01"},
        {"source_id": "S02", "grade": "B", "independent_id": "I01"},
        {"source_id": "S03", "grade": "B", "independent_id": "I02"},
        {"source_id": "S04", "grade": "D", "independent_id": "I03"},
    ]
    assert independent_ab_count(sources) == 2


def test_adequacy_uses_independent_count():
    # 3 篇 A/B 但其中两篇互为转载 → 独立只有 2 → sparse
    sources = [
        {"source_id": "S01", "grade": "A", "content": BASE_TEXT},
        {"source_id": "S02", "grade": "A", "content": _syndicated_copy()},
        {"source_id": "S03", "grade": "B", "content": "另一篇完全不同主题的深度报道，讨论供应链与农业科技投入的细节。" * 20},
    ]
    assert assess_corpus_adequacy(sources) == "sparse"


def test_classify_stance_critical():
    text = "该公司遭遇做空机构发布报告，多名投资者提起诉讼，监管部门已介入调查。"
    assert classify_stance(text) == "critical"


def test_classify_stance_first_person():
    assert classify_stance("我认为这件事的本质是常识。本文为访谈实录。") == "first_person"


def test_classify_stance_neutral():
    assert classify_stance("公司今日发布了新产品，定价九十九元。") == "neutral"


def test_report_status_holds_for_missing_critical():
    state = {"ab_count": 6, "total": 12, "iteration": 5, "critical_count": 0}
    out = report_status(state)
    assert out["should_stop"] is False
    assert out["reason"] == "missing_critical_sources"


def test_report_status_stops_with_critical():
    state = {"ab_count": 6, "total": 12, "iteration": 5, "critical_count": 2}
    assert report_status(state)["should_stop"] is True


def test_report_status_escape_hatch_after_iteration_12():
    state = {"ab_count": 6, "total": 12, "iteration": 13, "critical_count": 0}
    out = report_status(state)
    assert out["should_stop"] is True
    assert out["reason"] == "sufficient"


def test_report_status_backwards_compatible_without_critical():
    state = {"ab_count": 6, "total": 12, "iteration": 5}
    assert report_status(state)["should_stop"] is True


def test_new_frameworks_registered():
    assert resolve_frameworks("motives,values-hierarchy,interests", None) == [
        "motives", "values-hierarchy", "interests",
    ]
    business = resolve_frameworks(None, "business")
    assert "interests" in business and "motives" in business and "depth" in business
    all_fw = resolve_frameworks("all", None)
    assert "values-hierarchy" in all_fw and "depth" in all_fw and "dark-triad" not in all_fw
    assert "depth" in resolve_frameworks(None, None)
