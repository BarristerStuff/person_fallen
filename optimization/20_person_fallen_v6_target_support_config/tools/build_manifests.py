#!/usr/bin/env python3
"""Build the V6 target-support pilot manifests entirely from local frozen CSVs.

This tool intentionally does not inspect VAL/Holdout material, model outputs, or
image pixels beyond JPEG dimensions/magic needed for mechanical view checks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment error
    raise SystemExit("Pillow is required for offline JPEG dimension checks") from exc

BASE = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
DEFAULT_OUT = BASE / "20_person_fallen_v6_target_support_config"
DIAG = BASE / "13_person_fallen_v4_pose_attributes/manifests/v4_diagnostic_110.csv"
DIAG_CROP = BASE / "13_person_fallen_v4_pose_attributes/manifests/v4_crop_manifest.csv"
FULL = BASE / "13_person_fallen_v4_pose_attributes/manifests/v4_full_dev_436.csv"
FULL_CROP = BASE / "13_person_fallen_v4_pose_attributes/manifests/v4_full_dev_crop_manifest.csv"
SCREEN_CROP = BASE / "14_person_fallen_v4_operational_freeze/manifests/person_fallen_v4_operational_screen_crop.csv"

PILOT_FIELDS = [
    "item_id", "diagnostic_id", "expected_v4_outcome", "expected_outcome", "selection_basis",
    "source_family", "prompt_id", "media_id", "group_id", "source_split",
    "v3_split", "image_path", "image_sha256", "image_sha_basis", "prompt_path",
    "prompt_sha256", "taxonomy", "old_role", "old_label", "ground_truth",
    "metric_stratum", "source_provenance_status", "gt_type", "gt_source",
    "human_semantic_review_required", "formal_v3_evaluation", "person_detected",
    "detector_confidence", "detector_box_area_ratio", "full_view_path",
    "full_view_sha256", "crop_view_path", "crop_view_sha256", "view_count",
    "operational_id", "evaluation_stratum", "experiment_role", "phase", "request_id",
]
REG_FIELDS = [
    "operational_id", "operational_class", "expected_high_priority", "expected_outcome",
    "selection_basis", "item_id", "source_family", "prompt_id", "media_id", "group_id",
    "source_split", "v3_split", "image_path", "image_sha256", "image_sha_basis",
    "prompt_path", "prompt_sha256", "taxonomy", "old_role", "old_label", "ground_truth",
    "metric_stratum", "source_provenance_status", "gt_type", "gt_source",
    "human_semantic_review_required", "formal_v3_evaluation", "person_detected",
    "detector_confidence", "detector_box_area_ratio", "full_view_path", "full_view_sha256",
    "crop_view_path", "crop_view_sha256", "view_count", "evaluation_stratum",
    "experiment_role", "phase", "request_id",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_record(r: dict[str, str], label: str) -> dict[str, object]:
    paths = ["image_path", "prompt_path", "full_view_path", "crop_view_path"]
    hashes = ["image_sha256", "prompt_sha256", "full_view_sha256", "crop_view_sha256"]
    for pfield in paths:
        require(r.get(pfield, "") != "", f"{label}: missing {pfield}")
        p = Path(r[pfield])
        require(p.is_file(), f"{label}: missing file {p}")
    for pfield, hfield in zip(paths, hashes):
        actual = sha256(Path(r[pfield]))
        require(actual == r[hfield], f"{label}: SHA mismatch {hfield}: {actual} != {r[hfield]}")
    require(r.get("view_count") == "2", f"{label}: view_count must be 2")
    dims: dict[str, list[int]] = {}
    for pfield in ["full_view_path", "crop_view_path"]:
        p = Path(r[pfield])
        with Image.open(p) as im:
            require(im.format == "JPEG", f"{label}: {pfield} is not JPEG")
            require(im.size == (448, 336), f"{label}: {pfield} size {im.size}, expected (448, 336)")
            dims[pfield] = list(im.size)
    return {"item_id": r["item_id"], "image_sha256": r["image_sha256"],
            "prompt_sha256": r["prompt_sha256"], "full_view_sha256": r["full_view_sha256"],
            "crop_view_sha256": r["crop_view_sha256"], "view_dimensions": dims}


def enrich(source: dict[str, str], crop: dict[str, str]) -> dict[str, str]:
    # Keep source row values authoritative; add only mechanical crop/detector fields.
    out = dict(source)
    for key in ["person_detected", "detector_confidence", "detector_box_area_ratio",
                "full_view_path", "full_view_sha256", "crop_view_path", "crop_view_sha256", "view_count"]:
        out[key] = crop[key]
    return out


def build(outdir: Path, rebuild: bool = False) -> dict[str, object]:
    if not rebuild:
        require(not (outdir / "manifests/pilot156.json").exists(), "refusing to overwrite pilot156.json")
        require(not (outdir / "manifests/pilot156.csv").exists(), "refusing to overwrite pilot156.csv")
        require(not (outdir / "manifests/regression1.json").exists(), "refusing to overwrite regression1.json")
        require(not (outdir / "manifests/regression1.csv").exists(), "refusing to overwrite regression1.csv")
        require(not (outdir / "reports/source_audit.json").exists(), "refusing to overwrite source_audit.json")

    diag = read_csv(DIAG); diag_crop = {r["item_id"]: r for r in read_csv(DIAG_CROP)}
    full = read_csv(FULL); full_crop = {r["item_id"]: r for r in read_csv(FULL_CROP)}
    screen = read_csv(SCREEN_CROP)
    require(len(diag) == 110 and len(full) == 436, "unexpected source manifest size")

    floors = [r for r in diag if r["diagnostic_class"] == "floor_sitting"]
    lying_tax = {"prone_ground_lying", "side_lying", "supine_ground_lying"}
    lying = [r for r in diag if r["taxonomy"] in lying_tax]
    aux_tax = {"pushup_plank", "crawling_without_explicit_maintenance", "crawling_quadruped_support"}
    aux = [r for r in full if r["taxonomy"] in aux_tax]
    require(len(floors) == 55 and len(lying) == 55, f"diagnostic counts wrong: {len(floors)}, {len(lying)}")
    require(Counter(r["taxonomy"] for r in aux) == Counter({"pushup_plank": 26, "crawling_without_explicit_maintenance": 10, "crawling_quadruped_support": 5}), "aux taxonomy counts wrong")
    require(len([r for r in aux if r["taxonomy"].startswith("crawling")]) == 15, "crawling count wrong")
    multi = [r for r in full if r["taxonomy"] == "multi_person_one_lying"]
    require(len(multi) == 5 and len({r["group_id"] for r in multi}) == 1, "multi_person_one_lying must have exactly one group")

    selected_sources = floors + lying + aux + multi
    seen: set[str] = set(); pilot: list[dict[str, str]] = []
    for src in selected_sources:
        require(src["item_id"] not in seen, f"duplicate item_id in selected pilot: {src['item_id']}")
        seen.add(src["item_id"])
        crop = diag_crop.get(src["item_id"]) or full_crop.get(src["item_id"])
        require(crop is not None, f"no crop enrichment for {src['item_id']}")
        row = enrich(src, crop)
        row["operational_id"] = f"PFV6_PILOT_{len(pilot)+1:04d}"
        is_floor = src in floors
        is_lying = src in lying or src["taxonomy"] == "multi_person_one_lying"
        row["evaluation_stratum"] = "normal_negative" if is_floor else ("ground_lying" if is_lying else "auxiliary_attention")
        row["expected_outcome"] = "NO_ALERT_NORMAL_POSE" if is_floor else ("ALERT_GROUND_LYING" if is_lying else row.get("expected_v4_outcome", ""))
        row["experiment_role"] = row["evaluation_stratum"]
        row["phase"] = "v6_target_support_pilot"
        row["request_id"] = f"V6_TARGET_SUPPORT_PILOT_{len(pilot)+1:04d}"
        pilot.append(row)
    require(len(pilot) == 156 and len({r["item_id"] for r in pilot}) == 156, "pilot must be exactly 156 unique items")
    require(sum(r["evaluation_stratum"] == "ground_lying" for r in pilot) == 60, "ground_lying must include 55 lying + 5 multi")
    require(sum(r["evaluation_stratum"] == "auxiliary_attention" for r in pilot) == 41, "auxiliary_attention must include 26 pushup + 15 crawling")
    require(all(r["expected_outcome"] == "ALERT_GROUND_LYING" for r in pilot if r["taxonomy"] == "multi_person_one_lying"), "multi rows must bind ALERT_GROUND_LYING")

    target = [r for r in screen if r["operational_id"] == "PFV4_SCREEN_0066" and r["item_id"] == "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05"]
    require(len(target) == 1, f"regression target binding expected 1 row, got {len(target)}")
    reg = dict(target[0])
    reg["expected_outcome"] = reg["expected_high_priority"]
    reg["evaluation_stratum"] = reg["operational_class"]
    reg["experiment_role"] = "KNOWN_FAILURE_DEVELOPMENT_REGRESSION"
    reg["phase"] = "v6_target_support_development_regression"
    reg["request_id"] = "V6_TARGET_SUPPORT_REGRESSION_0001"

    verifications = [verify_record(r, f"pilot/{r['operational_id']}") for r in pilot]
    reg_verification = [verify_record(reg, "regression/PFV4_SCREEN_0066")]
    all_rows = pilot + [reg]
    audit = {
        "status": "PASS",
        "generated_at": "2026-09-10",
        "offline_only": True,
        "counts": {"pilot": len(pilot), "regression": 1, "total": len(all_rows),
                   "pilot_by_evaluation_stratum": dict(Counter(r["evaluation_stratum"] for r in pilot)),
                   "pilot_by_taxonomy": dict(Counter(r["taxonomy"] for r in pilot)),
                   "pilot_by_source_manifest": {"v4_diagnostic_110.csv": 110, "v4_full_dev_436.csv": 41},
                   "multi_person_one_lying_rows": 5},
        "group_count": {"pilot_total": len({r["group_id"] for r in pilot}),
                        "multi_person_one_lying": len({r["group_id"] for r in multi}),
                        "pilot_by_stratum": {k: len({r["group_id"] for r in pilot if r["evaluation_stratum"] == k}) for k in ["normal_negative", "ground_lying", "auxiliary_attention"]}},
        "bindings": {"regression_operational_id": reg["operational_id"], "regression_item_id": reg["item_id"], "expected_outcome": reg["expected_outcome"], "source_expected_high_priority": reg["expected_high_priority"], "sha_verification_records": verifications + reg_verification},
        "scope": {"read_sources": [str(DIAG), str(DIAG_CROP), str(FULL), str(FULL_CROP), str(SCREEN_CROP)], "selected_regression_row_only": True, "screen_other_rows_not_read_for_content": True, "val_holdout_read": False, "network": False, "model": False, "ollama": False, "human_review": False, "pixel_semantic_validation": False, "localization_validation": False, "view_validation": "mechanical JPEG format and 448x336 dimensions only"},
    }

    outdir.joinpath("manifests").mkdir(parents=True, exist_ok=True); outdir.joinpath("reports").mkdir(parents=True, exist_ok=True)
    for name, rows, fields in [("pilot156", pilot, PILOT_FIELDS), ("regression1", [reg], REG_FIELDS)]:
        with (outdir / f"manifests/{name}.json").open("w", encoding="utf-8") as fh: json.dump([{k: r.get(k, "") for k in fields} for r in rows], fh, ensure_ascii=False, indent=2); fh.write("\n")
        with (outdir / f"manifests/{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows([{k: r.get(k, "") for k in fields} for r in rows])
    with (outdir / "reports/source_audit.json").open("w", encoding="utf-8") as fh: json.dump(audit, fh, ensure_ascii=False, indent=2); fh.write("\n")
    return audit


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--outdir", type=Path, default=DEFAULT_OUT); ap.add_argument("--rebuild", action="store_true", help="allow replacement in the current unfrozen output directory"); args = ap.parse_args()
    try: audit = build(args.outdir, rebuild=args.rebuild)
    except Exception as exc: print(f"ERROR: {exc}", file=sys.stderr); return 1
    print(json.dumps({"status": audit["status"], "counts": audit["counts"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
