"""人物档案库：把一次性报告沉淀为可追踪、可校准的长期档案。

dossiers/<slug>/
├── dossier.json        # 档案元信息 + 历次分析记录
├── claims.json         # 稳定结论注册表（按框架），跨次合并，带变更历史
├── predictions.jsonl   # 可证伪预测台账，支持事后 resolve 校准
└── diffs/diff_<date>.md  # 与上一次分析的结论对比

CLI:
  python -m agent.dossier list --person <name>
  python -m agent.dossier resolve --person <name> --id P01 --outcome hit|miss|void [--note "..."]
  python -m agent.dossier calibration --person <name>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DOSSIER_DIR = Path("./dossiers")

_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def _slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^\w\s一-鿿]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug.strip("_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return default
    return default


def _dump_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── claims 提取与合并 ──────────────────────────────────────────────────────────


def extract_claims(report_json: dict) -> list[dict]:
    """从报告 JSON 抽取结论条目：每个框架一条 + synthesis 关键字段。"""
    claims: list[dict] = []
    frameworks = report_json.get("frameworks") or {}
    for fw_name, fw in frameworks.items():
        if not isinstance(fw, dict):
            continue
        findings = fw.get("findings") or fw.get("decision_function") or ""
        if not findings:
            # 无 findings 字段的框架（如 core/cit）：序列化关键内容做摘要
            findings = json.dumps(
                {k: v for k, v in fw.items() if k not in ("source_ids",)},
                ensure_ascii=False,
            )[:600]
        claims.append({
            "key": f"framework:{fw_name}",
            "claim": findings,
            "confidence": fw.get("confidence", "medium"),
            "source_ids": fw.get("source_ids", []),
        })

    synthesis = report_json.get("synthesis") or {}
    for key in ("core_drive", "decision_function", "interest_constraints"):
        if synthesis.get(key):
            claims.append({
                "key": f"synthesis:{key}",
                "claim": str(synthesis[key]),
                "confidence": report_json.get("overall_confidence", "medium"),
                "source_ids": [],
            })

    for c in report_json.get("contradictions") or []:
        topic = c.get("topic", "")
        if topic:
            claims.append({
                "key": f"contradiction:{topic}",
                "claim": c.get("interpretation", ""),
                "confidence": "medium",
                "source_ids": [],
            })
    return claims


def merge_claims(
    existing: list[dict], new_claims: list[dict], date_str: str
) -> tuple[list[dict], list[str]]:
    """合并新结论进注册表，返回 (merged, diff_lines)。"""
    by_key = {c["key"]: c for c in existing}
    diff_lines: list[str] = []

    for nc in new_claims:
        key = nc["key"]
        old = by_key.get(key)
        if old is None:
            by_key[key] = {
                **nc,
                "first_seen": date_str,
                "last_confirmed": date_str,
                "status": "active",
                "history": [],
            }
            diff_lines.append(f"+ 新增 [{key}]：{nc['claim'][:120]}")
            continue

        changed = False
        old_conf = _CONF_ORDER.get(old.get("confidence", "medium"), 1)
        new_conf = _CONF_ORDER.get(nc.get("confidence", "medium"), 1)
        if nc["claim"].strip() != old["claim"].strip():
            diff_lines.append(
                f"~ 修订 [{key}]：\n    旧：{old['claim'][:120]}\n    新：{nc['claim'][:120]}"
            )
            changed = True
        elif new_conf > old_conf:
            diff_lines.append(
                f"↑ 强化 [{key}]：置信度 {old.get('confidence')} → {nc.get('confidence')}"
            )
            changed = True
        elif new_conf < old_conf:
            diff_lines.append(
                f"↓ 削弱 [{key}]：置信度 {old.get('confidence')} → {nc.get('confidence')}"
            )
            changed = True

        if changed:
            old.setdefault("history", []).append({
                "date": old["last_confirmed"],
                "claim": old["claim"],
                "confidence": old.get("confidence"),
            })
            old["claim"] = nc["claim"]
            old["confidence"] = nc.get("confidence", "medium")
        old["last_confirmed"] = date_str
        old["source_ids"] = nc.get("source_ids", old.get("source_ids", []))

    stale = [k for k in by_key if k not in {c["key"] for c in new_claims}]
    for k in stale:
        if by_key[k].get("status") == "active":
            diff_lines.append(f"? 本次未覆盖 [{k}]（保留，未确认）")

    return list(by_key.values()), diff_lines


# ── 预测台账 ──────────────────────────────────────────────────────────────────


def extract_predictions(report_json: dict) -> list[dict]:
    synthesis = report_json.get("synthesis") or {}
    return [p for p in synthesis.get("top_predictions") or [] if isinstance(p, dict)]


def append_predictions(
    ledger_path: Path, predictions: list[dict], date_str: str
) -> int:
    existing_count = 0
    if ledger_path.exists():
        existing_count = sum(
            1 for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    added = 0
    with ledger_path.open("a", encoding="utf-8") as f:
        for i, p in enumerate(predictions, start=1):
            entry = {
                "id": f"P{existing_count + i:03d}",
                "run": date_str,
                "scenario": p.get("scenario", ""),
                "behavior": p.get("behavior", ""),
                "horizon": p.get("horizon", ""),
                "confidence": p.get("confidence", "medium"),
                "based_on": p.get("based_on", []),
                "created": _now(),
                "status": "open",
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            added += 1
    return added


def _read_ledger(ledger_path: Path) -> list[dict]:
    if not ledger_path.exists():
        return []
    return [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_ledger(ledger_path: Path, entries: list[dict]) -> None:
    with ledger_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def resolve_prediction(
    dossier_dir: Path, pred_id: str, outcome: str, note: str = ""
) -> dict:
    if outcome not in ("hit", "miss", "void"):
        raise ValueError("outcome 必须是 hit / miss / void")
    ledger_path = dossier_dir / "predictions.jsonl"
    entries = _read_ledger(ledger_path)
    target = next((e for e in entries if e["id"] == pred_id), None)
    if target is None:
        raise ValueError(f"未找到预测 {pred_id}")
    target["status"] = outcome
    target["resolved_at"] = _now()
    if note:
        target["resolution_note"] = note
    _write_ledger(ledger_path, entries)
    return target


def calibration_stats(dossier_dir: Path) -> dict:
    """按置信度统计预测命中率，用于校准「高置信」的真实含义。"""
    entries = _read_ledger(dossier_dir / "predictions.jsonl")
    stats: dict[str, dict[str, int]] = {}
    for e in entries:
        conf = e.get("confidence", "medium")
        bucket = stats.setdefault(conf, {"open": 0, "hit": 0, "miss": 0, "void": 0})
        bucket[e.get("status", "open")] = bucket.get(e.get("status", "open"), 0) + 1
    result = {"by_confidence": stats, "total": len(entries)}
    for conf, b in stats.items():
        resolved = b["hit"] + b["miss"]
        result.setdefault("hit_rate", {})[conf] = (
            b["hit"] / resolved if resolved else None
        )
    return result


# ── 主入口 ────────────────────────────────────────────────────────────────────


def update_dossier(
    person: str,
    slug: str,
    report_json: dict,
    date_str: str,
    backend_suffix: str = "",
    base_dir: Path = DEFAULT_DOSSIER_DIR,
) -> Path:
    """分析完成后调用：合并 claims、落库预测、生成 diff。返回档案目录。"""
    dossier_dir = base_dir / slug
    (dossier_dir / "diffs").mkdir(parents=True, exist_ok=True)

    meta_path = dossier_dir / "dossier.json"
    meta = _load_json(meta_path, {"person": person, "slug": slug, "created": _now(), "runs": []})
    meta["updated"] = _now()
    meta["runs"].append({
        "date": date_str,
        "backend": backend_suffix or "default",
        "mode": report_json.get("mode", ""),
        "frameworks": report_json.get("frameworks_enabled", []),
    })
    _dump_json(meta_path, meta)

    claims_path = dossier_dir / "claims.json"
    existing = _load_json(claims_path, [])
    is_first_run = not existing
    merged, diff_lines = merge_claims(existing, extract_claims(report_json), date_str)
    _dump_json(claims_path, merged)

    n_preds = append_predictions(
        dossier_dir / "predictions.jsonl", extract_predictions(report_json), date_str
    )

    if not is_first_run:
        diff_md = [
            f"# {person} 结论变更 — {date_str}",
            "",
            f"> 本次新预测入账：{n_preds} 条",
            "",
        ]
        diff_md.extend(diff_lines if diff_lines else ["（与上次分析无结论变化）"])
        (dossier_dir / "diffs" / f"diff_{date_str}.md").write_text(
            "\n".join(diff_md) + "\n", encoding="utf-8"
        )

    return dossier_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="人物档案库 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出档案的 claims 与预测")
    p_list.add_argument("--person", required=True)
    p_list.add_argument("--dossier-dir", default=str(DEFAULT_DOSSIER_DIR))

    p_resolve = sub.add_parser("resolve", help="判定一条预测的结果")
    p_resolve.add_argument("--person", required=True)
    p_resolve.add_argument("--id", required=True)
    p_resolve.add_argument("--outcome", required=True, choices=["hit", "miss", "void"])
    p_resolve.add_argument("--note", default="")
    p_resolve.add_argument("--dossier-dir", default=str(DEFAULT_DOSSIER_DIR))

    p_cal = sub.add_parser("calibration", help="按置信度统计预测命中率")
    p_cal.add_argument("--person", required=True)
    p_cal.add_argument("--dossier-dir", default=str(DEFAULT_DOSSIER_DIR))

    args = parser.parse_args()
    dossier_dir = Path(args.dossier_dir) / _slugify(args.person)
    if not dossier_dir.exists():
        print(f"档案不存在: {dossier_dir}", file=sys.stderr)
        sys.exit(1)

    if args.cmd == "list":
        claims = _load_json(dossier_dir / "claims.json", [])
        preds = _read_ledger(dossier_dir / "predictions.jsonl")
        print(f"## Claims ({len(claims)})")
        for c in claims:
            print(f"- [{c['key']}] ({c.get('confidence')}, {c.get('status')}) {c['claim'][:100]}")
        print(f"\n## Predictions ({len(preds)})")
        for p in preds:
            print(f"- {p['id']} [{p['status']}] ({p.get('confidence')}) {p.get('scenario','')[:60]} → {p.get('behavior','')[:60]}")
    elif args.cmd == "resolve":
        entry = resolve_prediction(dossier_dir, args.id, args.outcome, args.note)
        print(f"✓ {entry['id']} → {entry['status']}")
    elif args.cmd == "calibration":
        print(json.dumps(calibration_stats(dossier_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
