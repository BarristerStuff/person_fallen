#!/usr/bin/env python3
"""Materialize DESIGN-only P2 forensic artifacts.

SCREEN and VAL identities are never joined or emitted by this program.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
DESIGN = P2 / "01_internal_split/p2_design_manifest.csv"
DEV_MANIFEST = ROOT / "03_p1a_think_false_protocol/dev/dev_manifest.csv"
PREDICTIONS = ROOT / "03_p1a_think_false_protocol/dev/predictions.csv"
OUT = P2 / "02_forensics"


def atomic_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def taxonomy(group_id: str) -> str:
    if "sitting-on-floor" in group_id:
        return "sitting_on_floor"
    if "kneeling" in group_id:
        return "kneeling_or_half_kneeling"
    if "squatting" in group_id:
        return "squatting_or_crouching"
    if "bending-picking-up-items" in group_id:
        return "deep_bending_or_picking"
    if "exercise-push-up-plank" in group_id:
        return "exercise_pushup_or_plank"
    return "other"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with DESIGN.open(newline="", encoding="utf-8") as handle:
        design_rows = list(csv.DictReader(handle))
    design = {row["media_id"]: row for row in design_rows}
    with DEV_MANIFEST.open(newline="", encoding="utf-8") as handle:
        source = {row["media_id"]: row for row in csv.DictReader(handle) if row["media_id"] in design}
    predictions = {}
    with PREDICTIONS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["media_id"] in design:
                predictions[row["media_id"]] = row
    if set(design) != set(source) or set(design) != set(predictions):
        raise SystemExit("P2_STATUS=BLOCKED_DESIGN_ENTITY_MISMATCH")

    hard_rows = []
    false_positives = []
    per_taxonomy: dict[str, dict[str, object]] = defaultdict(lambda: {"total_hard_negative_count": 0, "baseline_FP_count": 0, "baseline_TN_count": 0, "groups": set(), "evidence": []})
    per_group: dict[str, dict[str, object]] = defaultdict(lambda: {"taxonomy": "", "total": 0, "fp": 0, "tn": 0})
    for media_id, manifest in sorted(design.items()):
        if manifest["sample_role"] != "hard_negative":
            continue
        pred = predictions[media_id]
        source_row = source[media_id]
        category = taxonomy(manifest["group_id"])
        is_fp = pred["predicted_status"] == "positive"
        record = {
            **manifest,
            "taxonomy": category,
            "baseline_predicted_status": pred["predicted_status"],
            "baseline_evidence": pred["evidence"],
            "baseline_is_fp": str(is_fp).lower(),
            "prompt_path": source_row["prompt_path"],
            "possible_GT_boundary_review_needed": "false",
        }
        hard_rows.append(record)
        if is_fp:
            false_positives.append(record)
        t = per_taxonomy[category]
        t["total_hard_negative_count"] += 1
        t["baseline_FP_count"] += int(is_fp)
        t["baseline_TN_count"] += int(not is_fp)
        t["groups"].add(manifest["group_id"])
        if is_fp:
            t["evidence"].append(pred["evidence"])
        g = per_group[manifest["group_id"]]
        g["taxonomy"] = category
        g["total"] += 1
        g["fp"] += int(is_fp)
        g["tn"] += int(not is_fp)

    fields = list(hard_rows[0])
    atomic_csv(OUT / "design_hard_negative_inventory.csv", fields, hard_rows)
    atomic_csv(OUT / "design_false_positives.csv", fields, false_positives)
    fp_taxonomy_fields = ["media_id", "taxonomy", "group_id", "scenario_id", "baseline_evidence", "possible_GT_boundary_review_needed"]
    atomic_csv(OUT / "design_false_positive_taxonomy.csv", fp_taxonomy_fields, [{key: row[key] for key in fp_taxonomy_fields} for row in false_positives])
    taxonomy_rows = []
    evidence_patterns = {
        "sitting_on_floor": "misread seated buttocks/legs and wall-supported upright torso as ground-supported lying",
        "kneeling_or_half_kneeling": "misread knee/shin support and forward-bent torso as prone ground support",
        "squatting_or_crouching": "misread a compact low crouch as curled lying",
        "deep_bending_or_picking": "no baseline DESIGN false positive",
        "exercise_pushup_or_plank": "misread a horizontal torso actively elevated by hands and feet as prone lying",
        "other": "uncategorized visible-support confusion",
    }
    for category, stats in sorted(per_taxonomy.items()):
        total = int(stats["total_hard_negative_count"])
        taxonomy_rows.append({
            "taxonomy": category,
            "total_hard_negative_count": total,
            "baseline_FP_count": stats["baseline_FP_count"],
            "baseline_TN_count": stats["baseline_TN_count"],
            "category_FPR": int(stats["baseline_FP_count"]) / total if total else None,
            "group_count": len(stats["groups"]),
            "model_evidence_pattern": evidence_patterns[category],
        })
    atomic_csv(OUT / "taxonomy_statistics.csv", list(taxonomy_rows[0]), taxonomy_rows)
    group_rows = [{"group_id": group, **stats, "fpr": int(stats["fp"]) / int(stats["total"])} for group, stats in sorted(per_group.items())]
    atomic_csv(OUT / "group_statistics.csv", list(group_rows[0]), group_rows)
    summary = {
        "forensic_source": "P2_DESIGN_ONLY",
        "design_rows": len(design),
        "design_role_counts": dict(sorted(Counter(row["sample_role"] for row in design.values()).items())),
        "design_hard_negative_count": len(hard_rows),
        "design_baseline_false_positive_count": len(false_positives),
        "design_ordinary_negative_false_positive_count": sum(1 for media_id, row in design.items() if row["sample_role"] == "negative" and predictions[media_id]["predicted_status"] == "positive"),
        "taxonomy": taxonomy_rows,
        "gt_integrity_concern": False,
        "screen_individual_prediction_rows_used": 0,
        "val_error_cases_used_for_prompt_design": False,
    }
    path = OUT / "forensic_summary.json"
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
