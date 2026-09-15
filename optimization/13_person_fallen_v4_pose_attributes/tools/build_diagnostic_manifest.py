#!/usr/bin/env python3
"""Build the fixed 110-row DEV-only v4 diagnostic manifest."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image

from common import ROOT, atomic_csv, atomic_json, load_csv, load_json, sha256


CONFIG = ROOT / "protocol/v4_diagnostic_config.json"
OUTPUT = ROOT / "manifests/v4_diagnostic_110.csv"
AUDIT = ROOT / "manifests/v4_diagnostic_110_audit.json"


def verify_image(row: dict[str, str]) -> None:
    path = Path(row["image_path"])
    if not path.is_file() or sha256(path) != row["image_sha256"]:
        raise RuntimeError(f"image integrity failure: {row['item_id']}")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()


def main() -> int:
    cfg = load_json(CONFIG)
    source = Path(cfg["parent_dev_manifest"])
    if sha256(source) != cfg["parent_dev_manifest_sha256"]:
        raise RuntimeError("parent DEV manifest SHA mismatch")
    rows = load_csv(source)
    if len(rows) != 436:
        raise RuntimeError(f"expected parent DEV=436, found {len(rows)}")
    if any(row["v3_split"] != "V3_DEV" or row["source_split"] == "HOLDOUT" for row in rows):
        raise RuntimeError("non-DEV or Holdout row in parent manifest")
    if any(row["gt_type"] != "PROMPT_DERIVED_SYNTHETIC_GT" for row in rows):
        raise RuntimeError("unexpected GT type")

    selected: list[dict[str, str]] = []
    quotas = cfg["selection"]
    for taxonomy, count in quotas.items():
        candidates = sorted(
            (row for row in rows if row["taxonomy"] == taxonomy),
            key=lambda row: (row["group_id"], row["item_id"]),
        )
        if len(candidates) < count:
            raise RuntimeError(f"insufficient taxonomy {taxonomy}: {len(candidates)} < {count}")
        selected.extend(candidates[:count])
    selected.sort(key=lambda row: (row["taxonomy"], row["group_id"], row["item_id"]))
    if len(selected) != 110 or len({row["item_id"] for row in selected}) != 110:
        raise RuntimeError("diagnostic selection is not 110 unique rows")

    output_rows = []
    for index, row in enumerate(selected, 1):
        verify_image(row)
        diagnostic_class = "floor_sitting" if row["taxonomy"] == "floor_sitting" else "lying"
        output_rows.append({
            "diagnostic_id": f"PFV4D_{index:04d}",
            "diagnostic_class": diagnostic_class,
            "expected_pose_family": diagnostic_class,
            "selection_basis": "FROZEN_TAXONOMY_AND_STABLE_ID_ONLY",
            **row,
        })
    fields = [
        "diagnostic_id", "diagnostic_class", "expected_pose_family", "selection_basis",
        *rows[0].keys(),
    ]
    atomic_csv(OUTPUT, fields, output_rows)
    audit = {
        "status": "PASS",
        "diagnostic_only": True,
        "parent_manifest": str(source),
        "parent_manifest_sha256": sha256(source),
        "selected_count": len(output_rows),
        "diagnostic_class_counts": dict(Counter(row["diagnostic_class"] for row in output_rows)),
        "taxonomy_counts": dict(Counter(row["taxonomy"] for row in output_rows)),
        "unique_image_sha256": len({row["image_sha256"] for row in output_rows}),
        "selection_uses_model_predictions": False,
        "screen_rows_read": 0,
        "val_rows_read": 0,
        "holdout_rows_read": 0,
        "gt_type": "PROMPT_DERIVED_SYNTHETIC_GT",
        "human_pixel_semantic_gt_available": False,
        "output_manifest": str(OUTPUT),
        "output_manifest_sha256": sha256(OUTPUT),
    }
    atomic_json(AUDIT, audit)
    print(audit)
    return 0


if __name__ == "__main__":
    sys.exit(main())

