"""Build the single normalized full-DEV recovery manifest without model calls.

Only the explicitly named DEV sources and the V5-B0 pilot artifacts are read.
No VAL/Holdout image, prompt, prediction, or evidence is opened.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
V5 = BASE / "17_person_fallen_v5_target_attributes"
V13 = BASE / "13_person_fallen_v4_pose_attributes"
FULL_SOURCE = V13 / "manifests/v4_full_dev_436.csv"
CROP_SOURCE = V13 / "manifests/v4_full_dev_crop_manifest.csv"
V5_FULL_MANIFEST = V5 / "manifests/pilot115.csv"

OUTPUTS = [
    ROOT / "manifests/full_dev_manifest.csv",
    ROOT / "manifests/full_dev_manifest.json",
    ROOT / "manifests/reuse115_manifest.csv",
    ROOT / "manifests/reuse115_manifest.json",
    ROOT / "manifests/new321_manifest.csv",
    ROOT / "manifests/new321_manifest.json",
    ROOT / "manifests/input_binding_inventory.json",
    ROOT / "reports/source_audit.json",
]

STRATA = {
    "ALERT_GROUND_LYING": "ground_lying",
    "NO_ALERT_NORMAL_POSE": "normal_negative",
    "ATTENTION_NEAR_GROUND": "auxiliary_attention",
    "RECHECK_VISUAL_UNCERTAIN": "visual_uncertain",
}
ORDER = ["normal_negative", "ground_lying", "auxiliary_attention", "visual_uncertain"]
SOURCE_FIELDS = [
    "item_id", "diagnostic_id", "expected_v4_outcome", "selection_basis", "source_family",
    "prompt_id", "media_id", "group_id", "source_split", "v3_split", "image_path",
    "image_sha256", "image_sha_basis", "prompt_path", "prompt_sha256", "taxonomy",
    "old_role", "old_label", "ground_truth", "metric_stratum", "source_provenance_status",
    "gt_type", "gt_source", "human_semantic_review_required", "formal_v3_evaluation",
    "person_detected", "detector_confidence", "detector_box_area_ratio", "full_view_path",
    "full_view_sha256", "crop_view_path", "crop_view_sha256", "view_count",
]
EXTRA_FIELDS = [
    "operational_id", "evaluation_stratum", "result_source", "phase", "request_id",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"invalid CSV header: {path}")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"malformed CSV row: {path}")
    return rows


def index(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError(f"{label} duplicate/missing {key}: {value}")
        result[value] = row
    return result


def verify_hash(path: str, expected: str) -> str:
    actual = sha256(Path(path))
    if actual != expected:
        raise ValueError(f"SHA mismatch: {path}")
    return actual


def verify_view(path: str, expected: str) -> dict[str, Any]:
    verify_hash(path, expected)
    with Image.open(path) as image:
        fmt, size = image.format, image.size
        image.verify()
    with Image.open(path) as image:
        image.load()
    if fmt != "JPEG" or size != (448, 336):
        raise ValueError(f"view is not 448x336 JPEG: {path}")
    return {"path": path, "sha256": expected, "format": fmt, "size": list(size)}


def base_row(full: dict[str, str], crop: dict[str, str]) -> dict[str, str]:
    for key in SOURCE_FIELDS:
        if key in full and key in crop and full[key] != crop[key]:
            raise ValueError(f"full/crop source conflict {key}: {full['item_id']}")
    row = {key: full.get(key, crop.get(key, "")) for key in SOURCE_FIELDS}
    for key in ["person_detected", "detector_confidence", "detector_box_area_ratio", "full_view_path", "full_view_sha256", "crop_view_path", "crop_view_sha256", "view_count"]:
        row[key] = crop[key]
    outcome = row["expected_v4_outcome"]
    if outcome not in STRATA:
        raise ValueError(f"unknown V4 outcome {outcome}: {row['item_id']}")
    row["operational_id"] = row["diagnostic_id"]
    row["evaluation_stratum"] = STRATA[outcome]
    return row


def main() -> None:
    if any(path.exists() for path in OUTPUTS):
        raise RuntimeError("recovery manifest output already exists; refusing overwrite")
    full_rows = load_csv(FULL_SOURCE)
    crop_rows = load_csv(CROP_SOURCE)
    v5_rows = load_csv(V5_FULL_MANIFEST)
    if len(full_rows) != 436 or len(crop_rows) != 436 or len(v5_rows) != 115:
        raise ValueError("unexpected source row count")
    full = index(full_rows, "item_id", "full DEV")
    crop = index(crop_rows, "item_id", "crop DEV")
    v5 = index(v5_rows, "item_id", "V5-B0 pilot")
    pilot_ids = set(v5)
    if len(pilot_ids) != 115:
        raise ValueError("pilot identity count is not 115")

    normalized: list[dict[str, str]] = []
    resource_bindings: dict[str, dict[str, Any]] = {}
    for source in full_rows:
        item_id = source["item_id"]
        if item_id not in crop:
            raise ValueError(f"full row missing crop: {item_id}")
        row = base_row(source, crop[item_id])
        if row["v3_split"] != "V3_DEV" or "VAL" in row["source_split"].upper() or "HOLDOUT" in row["source_split"].upper():
            raise ValueError(f"forbidden split: {item_id}")
        for path_key, hash_key in (("image_path", "image_sha256"), ("prompt_path", "prompt_sha256")):
            verify_hash(row[path_key], row[hash_key])
            resource_bindings[row[path_key]] = {"sha256": row[hash_key], "kind": path_key}
        for path_key, hash_key in (("full_view_path", "full_view_sha256"), ("crop_view_path", "crop_view_sha256")):
            resource_bindings[row[path_key]] = verify_view(row[path_key], row[hash_key]) | {"kind": path_key}
        if item_id in pilot_ids:
            p = v5[item_id]
            for key in SOURCE_FIELDS + ["person_detected", "full_view_path", "full_view_sha256", "crop_view_path", "crop_view_sha256", "view_count"]:
                if key in p and key in row and p[key] != row[key]:
                    raise ValueError(f"pilot/full source mismatch {key}: {item_id}")
            if p["experiment_stratum"] != row["evaluation_stratum"]:
                raise ValueError(f"pilot stratum mismatch: {item_id}")
            row["result_source"] = "REUSE_V5_B0_PILOT"
            row["phase"] = "full_dev"
            row["request_id"] = p["request_id"]
            row["original_request_id"] = p["request_id"]
        else:
            row["result_source"] = "NEW_INFERENCE"
            row["phase"] = "full_dev"
            row["request_id"] = ""
            row["original_request_id"] = ""
        normalized.append(row)

    counts = Counter(row["evaluation_stratum"] for row in normalized)
    expected = Counter({"ground_lying": 145, "normal_negative": 230, "auxiliary_attention": 41, "visual_uncertain": 20})
    if counts != expected:
        raise ValueError(f"full DEV strata mismatch: {counts}")
    floor_count = sum(row["taxonomy"] == "floor_sitting" for row in normalized if row["evaluation_stratum"] == "normal_negative")
    if floor_count != 55:
        raise ValueError(f"floor-sitting count mismatch: {floor_count}")

    reused = [row for row in normalized if row["result_source"] == "REUSE_V5_B0_PILOT"]
    new = [row for row in normalized if row["result_source"] == "NEW_INFERENCE"]
    if len(reused) != 115 or len(new) != 321:
        raise ValueError("reuse/new count mismatch")
    if any(row["item_id"] not in pilot_ids for row in reused):
        raise ValueError("reuse row is not from V5-B0 pilot")
    # Fixed dispatch order: each stratum retains the original full DEV order.
    new_ordered = [row for stratum in ORDER for row in normalized if row["result_source"] == "NEW_INFERENCE" and row["evaluation_stratum"] == stratum]
    for i, row in enumerate(new_ordered, 1):
        row["request_id"] = f"V5_B0_FULLDEV_EXTENSION_{i:04d}"
    if len({row["request_id"] for row in normalized}) != 321 + 115:
        raise ValueError("request IDs are not unique")
    # Reuse rows retain original request IDs; all new rows have the fixed prefix.
    if any(not row["request_id"].startswith("V5_B0_PILOT_") for row in reused):
        raise ValueError("reuse request ID changed")

    fields = SOURCE_FIELDS + ["operational_id", "evaluation_stratum", "result_source", "phase", "request_id", "original_request_id"]
    def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    def write_json(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    write_csv(ROOT / "manifests/full_dev_manifest.csv", normalized)
    write_json(ROOT / "manifests/full_dev_manifest.json", normalized)
    write_csv(ROOT / "manifests/reuse115_manifest.csv", reused)
    write_json(ROOT / "manifests/reuse115_manifest.json", reused)
    write_csv(ROOT / "manifests/new321_manifest.csv", new_ordered)
    write_json(ROOT / "manifests/new321_manifest.json", new_ordered)
    input_inventory = {
        "status": "PASS",
        "full_dev_rows": 436,
        "reused_rows": 115,
        "new_rows": 321,
        "resource_bindings": resource_bindings,
        "resource_binding_count": len(resource_bindings),
        "source_manifest_hashes": {str(FULL_SOURCE): sha256(FULL_SOURCE), str(CROP_SOURCE): sha256(CROP_SOURCE), str(V5_FULL_MANIFEST): sha256(V5_FULL_MANIFEST)},
        "source_fields_unchanged": True,
        "VAL_images_read": 0,
        "VAL_predictions_read": 0,
        "HOLDOUT_read": 0,
        "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED",
    }
    with (ROOT / "manifests/input_binding_inventory.json").open("x", encoding="utf-8") as handle:
        json.dump(input_inventory, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    audit = {
        "status": "PASS_RECOVERY_SOURCE_AND_HASH_AUDIT",
        "candidate": "V5-B0-TARGET-ATTRIBUTES",
        "execution": "FULL_DEV_RECOVERY_R1",
        "counts": {"full_dev": 436, "reused_v5_b0": 115, "new_inference": 321, **dict(counts), "floor_sitting_normal_negative": floor_count},
        "new_request_order": ORDER,
        "new_request_ids": [row["request_id"] for row in new_ordered],
        "bindings": resource_bindings,
        "scope": {"DEV_only": True, "VAL_images_read": 0, "VAL_predictions_read": 0, "HOLDOUT_read": 0, "source_fields_unchanged": True, "GT_relabelled": False, "pixel_semantics_verified": False, "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED"},
        "output_sha256": {str(path): sha256(path) for path in OUTPUTS if path.exists() or path in []},
    }
    # Add output hashes after all output files have been written.
    audit["output_sha256"] = {str(path): sha256(path) for path in OUTPUTS if path.exists() and path.name != "source_audit.json"}
    with (ROOT / "reports/source_audit.json").open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"full": len(normalized), "reused": len(reused), "new": len(new_ordered), "strata": dict(counts), "resources": len(resource_bindings)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
