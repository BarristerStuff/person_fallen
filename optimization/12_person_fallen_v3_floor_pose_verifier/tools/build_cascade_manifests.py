#!/usr/bin/env python3
"""Bind frozen v3 manifests and Stage-1 DEV predictions for the cascade revision."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "11_person_fallen_v3_revision"
SOURCE_REMAP = SOURCE / "remap"
SOURCE_RUN = SOURCE / "eval/runs/dev_V3-C0-448"
OUT = ROOT / "manifests"
AUDIT = ROOT / "audit/stage1_dev_reuse_audit.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def validate_manifest(rows: list[dict[str, str]], split: str) -> None:
    if not rows or len({row["item_id"] for row in rows}) != len(rows):
        raise SystemExit(f"CASCADE_{split}_MANIFEST_SHAPE_INVALID")
    if any(row["v3_split"] != split for row in rows):
        raise SystemExit(f"CASCADE_{split}_MANIFEST_SPLIT_INVALID")
    if any(row["formal_v3_evaluation"] != "true" for row in rows):
        raise SystemExit(f"CASCADE_{split}_MANIFEST_NONFORMAL")
    if any(row["source_split"] == "HOLDOUT" or row["v3_split"] == "HOLDOUT" for row in rows):
        raise SystemExit(f"CASCADE_{split}_HOLDOUT_CONTAMINATION")
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        groups[row["group_id"]].add(row["v3_split"])
        image = Path(row["image_path"])
        prompt = Path(row["prompt_path"])
        if not image.is_file() or sha256(image) != row["image_sha256"]:
            raise SystemExit(f"CASCADE_{split}_IMAGE_HASH_MISMATCH={row['item_id']}")
        if not prompt.is_file() or sha256(prompt) != row["prompt_sha256"]:
            raise SystemExit(f"CASCADE_{split}_SOURCE_PROMPT_HASH_MISMATCH={row['item_id']}")
    if any(len(values) != 1 for values in groups.values()):
        raise SystemExit(f"CASCADE_{split}_GROUP_LEAKAGE")


def binary(rows: list[dict[str, str]]) -> dict[str, object]:
    valid = [row for row in rows if row["ground_truth"] in {"positive", "negative"} and row["canonical_prediction_success"] == "true"]
    tp = sum(row["ground_truth"] == "positive" and row["predicted_status"] == "positive" for row in valid)
    fn = sum(row["ground_truth"] == "positive" and row["predicted_status"] != "positive" for row in valid)
    fp = sum(row["ground_truth"] == "negative" and row["predicted_status"] == "positive" for row in valid)
    tn = sum(row["ground_truth"] == "negative" and row["predicted_status"] != "positive" for row in valid)
    hard = [row for row in valid if row["metric_stratum"] == "hard_negative"]
    ordinary = [row for row in valid if row["metric_stratum"] == "ordinary_negative"]
    return {
        "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "precision": tp / (tp + fp), "recall": tp / (tp + fn),
        "f1": 2 * tp / (2 * tp + fp + fn), "accuracy": (tp + tn) / len(valid),
        "hard_negative_fpr": sum(row["predicted_status"] == "positive" for row in hard) / len(hard),
        "ordinary_negative_fpr": sum(row["predicted_status"] == "positive" for row in ordinary) / len(ordinary),
        "hard_negative_count": len(hard), "ordinary_negative_count": len(ordinary),
    }


def main() -> None:
    paths = {
        "V3_DEV": SOURCE_REMAP / "person_fallen_v3_dev_manifest.csv",
        "V3_SCREEN": SOURCE_REMAP / "person_fallen_v3_screen_manifest.csv",
        "V3_VAL": SOURCE_REMAP / "person_fallen_v3_val_manifest.csv",
    }
    manifests = {split: load_csv(path) for split, path in paths.items()}
    for split, rows in manifests.items():
        validate_manifest(rows, split)

    predictions_path = SOURCE_RUN / "predictions.csv"
    summary_path = SOURCE_RUN / "summary.json"
    if not predictions_path.is_file() or not summary_path.is_file():
        raise SystemExit("CASCADE_FROZEN_STAGE1_DEV_EVIDENCE_MISSING")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "COMPLETE" or summary.get("candidate") != "V3-C0-448" or summary.get("resolution") != "448x336":
        raise SystemExit("CASCADE_FROZEN_STAGE1_DEV_SUMMARY_INVALID")
    predictions = load_csv(predictions_path)
    dev = manifests["V3_DEV"]
    dev_by_id = {row["item_id"]: row for row in dev}
    if len(predictions) != len(dev) or len({row["item_id"] for row in predictions}) != len(dev):
        raise SystemExit("CASCADE_FROZEN_STAGE1_DEV_CARDINALITY_INVALID")
    for row in predictions:
        source = dev_by_id.get(row["item_id"])
        if source is None:
            raise SystemExit(f"CASCADE_FROZEN_STAGE1_UNKNOWN_ITEM={row['item_id']}")
        for key in ("image_sha256", "prompt_sha256", "ground_truth", "metric_stratum", "taxonomy"):
            if row[key] != source[key]:
                raise SystemExit(f"CASCADE_FROZEN_STAGE1_BINDING_MISMATCH={row['item_id']}:{key}")
        if row["state"] != "COMPLETED" or row["strict_json_ok"] != "true" or row["canonical_prediction_success"] != "true":
            raise SystemExit(f"CASCADE_FROZEN_STAGE1_NONCANONICAL={row['item_id']}")

    stage2 = []
    for row in predictions:
        if row["predicted_status"] != "positive":
            continue
        source = dict(dev_by_id[row["item_id"]])
        source.update({
            "stage1_request_id": row["request_id"],
            "stage1_prediction": row["predicted_status"],
            "stage1_evidence": row["evidence"],
            "stage1_response_sha256": row["response_sha256"],
        })
        stage2.append(source)
    if len(stage2) != 233:
        raise SystemExit(f"CASCADE_STAGE2_DEV_CALL_COUNT_UNEXPECTED={len(stage2)}")

    fields = list(dev[0])
    stage2_fields = fields + ["stage1_request_id", "stage1_prediction", "stage1_evidence", "stage1_response_sha256"]
    write_csv(OUT / "dev_full_manifest.csv", dev, fields)
    write_csv(OUT / "screen_full_manifest.csv", manifests["V3_SCREEN"], fields)
    write_csv(OUT / "val_full_manifest.csv", manifests["V3_VAL"], fields)
    write_csv(OUT / "dev_stage2_manifest.csv", stage2, stage2_fields)

    audit = {
        "status": "PASS",
        "revision_id": "PERSON_FALLEN_V3_FLOOR_POSE_VERIFIER_20260902_01",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": str(SOURCE),
        "source_hashes": {
            "v3_definition": sha256(SOURCE / "definition/person_fallen_v3_definition.md"),
            "v3_prompt": sha256(SOURCE / "prompt/V3-C0_prompt.txt"),
            "v3_config": sha256(SOURCE / "protocol/v3_eval_config.json"),
            "v3_dev_manifest": sha256(paths["V3_DEV"]),
            "v3_screen_manifest": sha256(paths["V3_SCREEN"]),
            "v3_val_manifest": sha256(paths["V3_VAL"]),
            "stage1_dev_predictions": sha256(predictions_path),
            "stage1_dev_summary": sha256(summary_path),
        },
        "counts": {
            "dev_full": len(dev), "screen_full": len(manifests["V3_SCREEN"]), "val_full": len(manifests["V3_VAL"]),
            "stage1_dev_positive_calls_to_stage2": len(stage2),
            "stage1_dev_predictions": dict(sorted(Counter(row["predicted_status"] for row in predictions).items())),
        },
        "stage1_dev_baseline": binary(predictions),
        "stage1_dev_false_positive_taxonomy": dict(sorted(Counter(row["taxonomy"] for row in predictions if row["ground_truth"] == "negative" and row["predicted_status"] == "positive").items())),
        "boundaries": {"holdout_rows": 0, "holdout_consumed": False, "new_p4d_generation": False, "production_or_shared_dataset_modified": False},
    }
    write_json(AUDIT, audit)
    write_json(OUT / "manifest_index.json", {
        "status": "PASS",
        "dev_full_manifest_sha256": sha256(OUT / "dev_full_manifest.csv"),
        "dev_stage2_manifest_sha256": sha256(OUT / "dev_stage2_manifest.csv"),
        "screen_full_manifest_sha256": sha256(OUT / "screen_full_manifest.csv"),
        "val_full_manifest_sha256": sha256(OUT / "val_full_manifest.csv"),
        "stage1_dev_positive_calls_to_stage2": len(stage2),
        "holdout_rows": 0,
    })
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
