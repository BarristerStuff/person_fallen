#!/usr/bin/env python3
"""Prepare V5 DEV lineage and historical metrics; no network/model access.

Only explicitly listed DEV inputs are opened. No VAL/Holdout manifests,
images, predictions, responses, or generation jobs are read or executed.
Writes use exclusive creation under this V5 directory; sources are read-only.
"""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
PARENT = BASE / "13_person_fallen_v4_pose_attributes"
REV15 = BASE / "15_person_fallen_v4_scene_any_lying"
ALERT = "ALERT_GROUND_LYING"
NORMAL = "NO_ALERT_NORMAL_POSE"
ATTENTION = "ATTENTION_NEAR_GROUND"
RECHECK = "RECHECK_VISUAL_UNCERTAIN"
STRATA = {ALERT: "ground_lying", NORMAL: "normal_negative",
          ATTENTION: "auxiliary_attention", RECHECK: "visual_uncertain"}
EXPECTED_COUNTS = {"ground_lying": 145, "normal_negative": 230,
                   "auxiliary_attention": 41, "visual_uncertain": 20}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def classify(row):
    """Use the existing V4 expected outcome, NOT the v3 binary label alone."""
    outcome = row["expected_v4_outcome"]
    if outcome not in STRATA:
        raise ValueError("Unknown original V4 outcome")
    gt = row["ground_truth"]
    expected_gt = {ALERT: "positive", ATTENTION: "positive",
                   NORMAL: "negative", RECHECK: "uncertain"}[outcome]
    if gt != expected_gt:
        raise ValueError("Original GT / V4 outcome inconsistency")
    if row["taxonomy"] == "floor_sitting" and outcome != NORMAL:
        raise ValueError("Floor sitting must stay a normal-negative subset")
    return STRATA[outcome]


def summarize(source_rows, predictions):
    source = {r["item_id"]: r for r in source_rows}
    pred = {r["item_id"]: r for r in predictions}
    if len(source) != len(source_rows) or len(pred) != len(predictions):
        raise ValueError("Duplicate item_id")
    if set(source) != set(pred):
        raise ValueError("Prediction/source item sets differ")
    output = {}
    for name in (*EXPECTED_COUNTS, "floor_sitting"):
        ids = [item for item, row in source.items()
               if (row["taxonomy"] == "floor_sitting" if name == "floor_sitting"
                   else classify(row) == name)]
        decisions = Counter(pred[item]["frame_decision"] for item in ids)
        if set(decisions) - set(STRATA):
            raise ValueError("Unknown frame decision")
        count = len(ids)
        alerts = decisions[ALERT]
        rechecks = decisions[RECHECK]
        output[name] = {"count": count, "decisions": dict(decisions),
                        "alert_count": alerts, "recheck_count": rechecks,
                        "alert_rate": alerts / count if count else None,
                        "alert_recheck_coverage": (alerts + rechecks) / count if count else None}
    if output["floor_sitting"]["count"] > output["normal_negative"]["count"]:
        raise ValueError("Floor-sitting subset inconsistency")
    return output


def write_json(path, obj):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    outputs = [ROOT / "manifests/v5_dev_manifest.csv",
               ROOT / "reports/preparation_audit.json"]
    if any(p.exists() for p in outputs):
        raise RuntimeError("Preparation output already exists; no overwrite/resume")
    source_path = PARENT / "manifests/v4_full_dev_crop_manifest.csv"
    v4_pred_path = PARENT / "eval/runs/dev_V4-A0-FULL-CROP-436/predictions.csv"
    r15_pred_path = REV15 / "eval/runs/dev_full_REV15/predictions.csv"
    source = load_csv(source_path)
    if len(source) != 436 or len({r["item_id"] for r in source}) != 436:
        raise ValueError("Unexpected DEV row count or duplicate identity")
    counts = Counter(classify(r) for r in source)
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError(f"Wrong V4 strata: {dict(counts)}")
    if sum(r["taxonomy"] == "floor_sitting" for r in source) != 55:
        raise ValueError("Missing floor-sitting regression subset")
    lineage = Counter()
    for row in source:
        if row["v3_split"] != "V3_DEV" or "HOLDOUT" in row["source_split"].upper():
            raise ValueError("Non-DEV input forbidden")
        if row["gt_type"] != "PROMPT_DERIVED_SYNTHETIC_GT":
            raise ValueError("Unexpected GT policy")
        prompt_path = Path(row["prompt_path"])
        prompt_path.resolve().relative_to(Path("/home/yanbo/下载/batches").resolve())
        for path_key, hash_key, counter in [
            ("image_path", "image_sha256", "source_images_verified"),
            ("prompt_path", "prompt_sha256", "generation_prompts_verified"),
            ("full_view_path", "full_view_sha256", "full_views_verified"),
            ("crop_view_path", "crop_view_sha256", "crop_views_verified"),
        ]:
            if sha256(row[path_key]) != row[hash_key]:
                raise ValueError(f"Hash mismatch: {row['item_id']} / {path_key}")
            lineage[counter] += 1
    v4_predictions = load_csv(v4_pred_path)
    rev15_predictions = load_csv(r15_pred_path)
    baseline = summarize(source, v4_predictions)
    revised = summarize(source, rev15_predictions)
    output_rows = []
    for row in source:
        output_rows.append({"v5_stratum": classify(row),
                            "v5_floor_sitting_subset": str(row["taxonomy"] == "floor_sitting").lower(),
                            **row})
    with outputs[0].open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    audit = {
        "status": "PREPARATION_COMPLETE_NO_INFERENCE",
        "revision_id": "PERSON_FALLEN_V5_PATROL_RECHECK_20260909_01",
        "event_name": "person_fallen",
        "business_target": "Find visible ground-lying/collapsed people during patrol, not recognize the fall transition",
        "gt_type": "PROMPT_DERIVED_SYNTHETIC_GT",
        "human_semantic_review_required_for_synthetic_development": False,
        "pixel_prompt_alignment": "USER_ATTESTED_NOT_EXHAUSTIVELY_VERIFIED",
        "model_prediction_used_as_gt": False,
        "source_counts": dict(counts), "floor_sitting_subset_count": 55,
        "source_split_counts_preserved": dict(Counter(r["source_split"] for r in source)),
        "hash_verification": dict(lineage),
        "historical_metrics_only_not_new_v5_predictions": True,
        "historical_v4_operational_dev": baseline,
        "historical_rev15_corrected_operational_dev": revised,
        "proposed_auxiliary_dev_calls_using_exact_cached_v4_primary": sum(
            r["frame_decision"] != ALERT for r in v4_predictions),
        "model_requests_this_preparation": 0, "detector_requests_this_preparation": 0,
        "val_images_read": 0, "val_predictions_read": 0,
        "holdout_rows_read": 0, "holdout_images_read": 0,
        "candidate_freeze_created": False, "current_winner": None,
        "production_integration_ready": False,
        "bindings": {str(p): sha256(p) for p in [source_path, v4_pred_path, r15_pred_path, outputs[0]]},
        "next_action": "Implement and freeze a single independent scene-review branch; no VAL/Holdout until lawful gates and exposure audit pass"
    }
    write_json(outputs[1], audit)
    print(json.dumps({k: audit[k] for k in ("status", "source_counts", "floor_sitting_subset_count", "hash_verification", "proposed_auxiliary_dev_calls_using_exact_cached_v4_primary", "model_requests_this_preparation", "current_winner")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
