#!/usr/bin/env python3
"""Build the complete, fixed 436-row v4 DEV manifest from frozen v3 GT."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image

from common import ROOT, atomic_csv, atomic_json, load_csv, load_json, sha256


PLAN = ROOT / "protocol/v4_full_dev_execution_plan.json"
OUTPUT = ROOT / "manifests/v4_full_dev_436.csv"
AUDIT = ROOT / "manifests/v4_full_dev_436_audit.json"

ATTENTION_TAXONOMIES = {
    "crawling_quadruped_support",
    "crawling_without_explicit_maintenance",
    "pushup_plank",
}


def expected_outcome(row: dict[str, str]) -> str:
    if row["ground_truth"] == "negative":
        return "NO_ALERT_NORMAL_POSE"
    if row["ground_truth"] == "uncertain":
        return "RECHECK_VISUAL_UNCERTAIN"
    if row["ground_truth"] == "positive" and row["taxonomy"] in ATTENTION_TAXONOMIES:
        return "ATTENTION_NEAR_GROUND"
    if row["ground_truth"] == "positive":
        return "ALERT_GROUND_LYING"
    raise RuntimeError(f"unsupported GT: {row['ground_truth']}")


def verify_image(row: dict[str, str]) -> None:
    path = Path(row["image_path"])
    if not path.is_file() or sha256(path) != row["image_sha256"]:
        raise RuntimeError(f"image integrity failure: {row['item_id']}")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()


def main() -> int:
    plan = load_json(PLAN)
    source = Path(plan["parent_dev_manifest"])
    if sha256(source) != plan["parent_dev_manifest_sha256"]:
        raise RuntimeError("parent DEV manifest SHA mismatch")
    rows = load_csv(source)
    expected = plan["expected_dev_counts"]
    gt_counts = Counter(row["ground_truth"] for row in rows)
    stratum_counts = Counter(row["metric_stratum"] for row in rows)
    if len(rows) != expected["total"] or gt_counts != Counter({
        "positive": expected["positive"],
        "negative": expected["negative"],
        "uncertain": expected["uncertain"],
    }):
        raise RuntimeError(f"frozen DEV count mismatch: total={len(rows)} gt={dict(gt_counts)}")
    if stratum_counts["hard_negative"] != expected["hard_negative"]:
        raise RuntimeError("hard-negative count mismatch")
    if stratum_counts["ordinary_negative"] != expected["ordinary_negative"]:
        raise RuntimeError("ordinary-negative count mismatch")
    if any(row["v3_split"] != "V3_DEV" or row["source_split"] == "HOLDOUT" for row in rows):
        raise RuntimeError("non-DEV or Holdout row in parent manifest")
    if any(row["gt_type"] != plan["gt_type"] for row in rows):
        raise RuntimeError("unexpected GT type")

    output_rows = []
    for index, row in enumerate(rows, 1):
        verify_image(row)
        output_rows.append({
            "diagnostic_id": f"PFV4DEV_{index:04d}",
            "expected_v4_outcome": expected_outcome(row),
            "selection_basis": "ALL_FROZEN_V3_DEV_ROWS_IN_PARENT_ORDER",
            **row,
        })
    if len({row["item_id"] for row in output_rows}) != len(output_rows):
        raise RuntimeError("duplicate item_id in frozen DEV")
    fields = ["diagnostic_id", "expected_v4_outcome", "selection_basis", *rows[0].keys()]
    atomic_csv(OUTPUT, fields, output_rows)
    audit = {
        "status": "PASS",
        "dev_only": True,
        "parent_manifest": str(source),
        "parent_manifest_sha256": sha256(source),
        "selected_count": len(output_rows),
        "ground_truth_counts": dict(gt_counts),
        "metric_stratum_counts": dict(stratum_counts),
        "expected_outcome_counts": dict(Counter(row["expected_v4_outcome"] for row in output_rows)),
        "taxonomy_counts": dict(Counter(row["taxonomy"] for row in output_rows)),
        "unique_image_sha256": len({row["image_sha256"] for row in output_rows}),
        "selection_uses_model_predictions": False,
        "screen_rows_read": 0,
        "val_rows_read": 0,
        "holdout_rows_read": 0,
        "gt_type": plan["gt_type"],
        "human_pixel_semantic_gt_available": False,
        "output_manifest": str(OUTPUT),
        "output_manifest_sha256": sha256(OUTPUT),
    }
    atomic_json(AUDIT, audit)
    print(audit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
