"""人物档案库测试。"""
import json

import pytest

from agent.dossier import (
    calibration_stats,
    extract_claims,
    extract_predictions,
    merge_claims,
    resolve_prediction,
    update_dossier,
)


REPORT_V1 = {
    "subject": "Test Person",
    "mode": "deep",
    "overall_confidence": "medium",
    "frameworks_enabled": ["core", "big5", "motives"],
    "frameworks": {
        "big5": {
            "findings": "高开放性、低外向性",
            "confidence": "medium",
            "source_ids": ["S01", "S02"],
        },
        "motives": {
            "findings": "主导动机为 nAch",
            "confidence": "high",
            "source_ids": ["S03"],
        },
    },
    "contradictions": [
        {"topic": "市值态度", "interpretation": "interest_driven"},
    ],
    "synthesis": {
        "core_drive": "nAch 主导，工匠型",
        "decision_function": "先验证小实验，按价值排序取舍",
        "top_predictions": [
            {
                "scenario": "遭遇监管调查",
                "behavior": "两周内亲自公开回应",
                "horizon": "12个月",
                "confidence": "high",
                "based_on": ["motives"],
            },
        ],
    },
}


def test_extract_claims_covers_frameworks_synthesis_contradictions():
    claims = extract_claims(REPORT_V1)
    keys = {c["key"] for c in claims}
    assert "framework:big5" in keys
    assert "framework:motives" in keys
    assert "synthesis:core_drive" in keys
    assert "contradiction:市值态度" in keys


def test_merge_claims_new_and_revision():
    merged, diff = merge_claims([], extract_claims(REPORT_V1), "20260101")
    assert all(c["status"] == "active" for c in merged)
    assert any(line.startswith("+ 新增") for line in diff)

    v2 = json.loads(json.dumps(REPORT_V1))
    v2["frameworks"]["big5"]["findings"] = "高开放性、中等外向性"
    merged2, diff2 = merge_claims(merged, extract_claims(v2), "20260601")
    assert any("~ 修订 [framework:big5]" in line for line in diff2)
    big5 = next(c for c in merged2 if c["key"] == "framework:big5")
    assert big5["claim"] == "高开放性、中等外向性"
    assert len(big5["history"]) == 1


def test_merge_claims_confidence_strengthened():
    merged, _ = merge_claims([], extract_claims(REPORT_V1), "20260101")
    v2 = json.loads(json.dumps(REPORT_V1))
    v2["frameworks"]["big5"]["confidence"] = "high"
    _, diff = merge_claims(merged, extract_claims(v2), "20260601")
    assert any("↑ 强化 [framework:big5]" in line for line in diff)


def test_update_dossier_writes_files_and_diff(tmp_path):
    d1 = update_dossier(
        person="Test Person", slug="test_person",
        report_json=REPORT_V1, date_str="20260101_0000", base_dir=tmp_path,
    )
    assert (d1 / "dossier.json").exists()
    assert (d1 / "claims.json").exists()
    preds = (d1 / "predictions.jsonl").read_text().strip().splitlines()
    assert len(preds) == 1
    assert json.loads(preds[0])["id"] == "P001"
    # 第一次运行不生成 diff
    assert not list((d1 / "diffs").glob("*.md"))

    v2 = json.loads(json.dumps(REPORT_V1))
    v2["frameworks"]["motives"]["confidence"] = "medium"
    d2 = update_dossier(
        person="Test Person", slug="test_person",
        report_json=v2, date_str="20260601_0000", base_dir=tmp_path,
    )
    diffs = list((d2 / "diffs").glob("*.md"))
    assert len(diffs) == 1
    assert "削弱" in diffs[0].read_text()
    # 预测继续追加且编号递增
    preds2 = (d2 / "predictions.jsonl").read_text().strip().splitlines()
    assert json.loads(preds2[-1])["id"] == "P002"


def test_resolve_and_calibration(tmp_path):
    d = update_dossier(
        person="Test Person", slug="test_person",
        report_json=REPORT_V1, date_str="20260101_0000", base_dir=tmp_path,
    )
    entry = resolve_prediction(d, "P001", "hit", note="verified by news")
    assert entry["status"] == "hit"
    stats = calibration_stats(d)
    assert stats["total"] == 1
    assert stats["hit_rate"]["high"] == 1.0

    with pytest.raises(ValueError):
        resolve_prediction(d, "P999", "hit")
    with pytest.raises(ValueError):
        resolve_prediction(d, "P001", "invalid")


def test_extract_predictions():
    preds = extract_predictions(REPORT_V1)
    assert len(preds) == 1
    assert preds[0]["confidence"] == "high"
    assert extract_predictions({}) == []
