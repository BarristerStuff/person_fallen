#!/usr/bin/env python3
"""Build immutable operational SCREEN and VAL manifests from legal v3 splits."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image

from common import ROOT, atomic_csv, atomic_json, load_csv, load_json, sha256


PLAN = ROOT / "protocol/final_operational_plan.json"
V3_DEV = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_dev_manifest.csv")
SOURCE = {
    "screen": Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_screen_manifest.csv"),
    "val": Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_val_manifest.csv"),
}
OUTPUT = {
    "screen": ROOT / "manifests/person_fallen_v4_operational_screen.csv",
    "val": ROOT / "manifests/person_fallen_v4_operational_val.csv",
}
AUDIT = {
    "screen": ROOT / "manifests/person_fallen_v4_operational_screen_audit.json",
    "val": ROOT / "manifests/person_fallen_v4_operational_val_audit.json",
}
EXPECTED_SOURCE_SHA = {
    "screen": "8e9b4048c0bc97807e8afe647eee11c0903d50108844f2117ae41b85c6e8923c",
    "val": "ffe093f90a64698f1006541400dc8bf6bda774bbe54febc47ef2c388ef184302",
}


def verify_image(row: dict[str, str]) -> None:
    source = Path(row["image_path"])
    if not source.is_file() or sha256(source) != row["image_sha256"]:
        raise RuntimeError(f"image integrity failure: {row['item_id']}")
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        image.load()


def main() -> int:
    plan = load_json(PLAN)
    if sha256(V3_DEV) != "fc41fcc39b87d8da7decfd50a4d832e8c5f38470c7c6cf08aaaaa160aa751f2b":
        raise RuntimeError("v3 DEV manifest changed")
    dev_rows = load_csv(V3_DEV)
    dev_groups = {row["group_id"] for row in dev_rows}
    result = {}
    split_groups = {}
    for phase in ("screen", "val"):
        source = SOURCE[phase]
        if sha256(source) != EXPECTED_SOURCE_SHA[phase]:
            raise RuntimeError(f"{phase} source manifest SHA mismatch")
        rows = load_csv(source)
        expected_split = "V3_SCREEN" if phase == "screen" else "V3_VAL"
        if any(row["v3_split"] != expected_split for row in rows):
            raise RuntimeError(f"{phase} split mismatch")
        if any(row["source_split"] == "HOLDOUT" or row["v3_split"] == "HOLDOUT" for row in rows):
            raise RuntimeError(f"{phase} contains Holdout row")
        if any(row["ground_truth"] not in {"positive", "negative"} for row in rows):
            raise RuntimeError(f"{phase} contains unsupported uncertain GT")
        if len({row["item_id"] for row in rows}) != len(rows):
            raise RuntimeError(f"{phase} duplicate item_id")
        if len({row["image_sha256"] for row in rows}) != len(rows):
            raise RuntimeError(f"{phase} duplicate image SHA")
        groups = {row["group_id"] for row in rows}
        if groups & dev_groups:
            raise RuntimeError(f"{phase} group overlap with DEV")
        split_groups[phase] = groups
        output_rows = []
        for index, row in enumerate(rows, 1):
            verify_image(row)
            operational_class = "ground_lying" if row["ground_truth"] == "positive" else "normal_negative"
            output_rows.append({
                "operational_id": f"PFV4_{phase.upper()}_{index:04d}",
                "operational_class": operational_class,
                "expected_high_priority": "ALERT_GROUND_LYING" if operational_class == "ground_lying" else "NO_ALERT_NORMAL_POSE",
                "selection_basis": "FROZEN_LEGAL_V3_SPLIT_PRESERVED_WITHOUT_GT_REWRITE",
                **row,
            })
        fields = ["operational_id", "operational_class", "expected_high_priority", "selection_basis", *rows[0].keys()]
        atomic_csv(OUTPUT[phase], fields, output_rows)
        result[phase] = {
            "status": "PASS",
            "source_manifest": str(source),
            "source_manifest_sha256": sha256(source),
            "rows": len(output_rows),
            "operational_class_counts": dict(Counter(row["operational_class"] for row in output_rows)),
            "taxonomy_counts": dict(Counter(row["taxonomy"] for row in output_rows)),
            "floor_sitting_count": sum(row["taxonomy"] == "floor_sitting" for row in output_rows),
            "unique_group_count": len(groups),
            "unique_image_sha256": len({row["image_sha256"] for row in output_rows}),
            "output_manifest": str(OUTPUT[phase]),
            "output_manifest_sha256": sha256(OUTPUT[phase]),
            "screen_rows_read": 0,
            "val_rows_read": 0,
            "holdout_rows_read": 0,
        }
        atomic_json(AUDIT[phase], result[phase])
    if split_groups["screen"] & split_groups["val"]:
        raise RuntimeError("SCREEN/VAL group leakage")
    result["status"] = "PASS"
    result["dev_rows_read"] = 436
    result["screen_rows_read"] = 0
    result["val_rows_read"] = 0
    result["holdout_rows_read"] = 0
    atomic_json(ROOT / "manifests/operational_split_audit.json", result)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
