#!/usr/bin/env python3
"""Independently bind the already-existing P2 C3 SCREEN baseline."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
OUT = P3 / "05_screen/C3_BASELINE"
SOURCE = P2 / "04_screening/C3/predictions.csv"
SOURCE_SUMMARY = P2 / "04_screening/C3/summary.json"
MANIFEST = P2 / "01_internal_split/p2_screen_manifest.csv"
EXPECTED_SOURCE_SHA = "5d21d873dc327c8e59d25c59fad79522f65d6d0e19a817c5d893f662aaa1a848"
EXPECTED_MANIFEST_SHA = "ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def metric(rows: list[dict[str, str]]) -> dict:
    valid = [r for r in rows if r["event_label"] in {"0", "1"} and r["canonical_ok"] == "true"]
    tp = fp = tn = fn = 0
    for row in valid:
        gt = row["event_label"]
        alert = row["predicted_status"] == "positive"
        if gt == "1" and alert:
            tp += 1
        elif gt == "1":
            fn += 1
        elif alert:
            fp += 1
        else:
            tn += 1
    ordinary = [r for r in valid if r["sample_role"] == "negative"]
    hard = [r for r in valid if r["sample_role"] == "hard_negative"]
    uncertain = sum(r["predicted_status"] == "uncertain" for r in valid)
    ratio = lambda a, b: None if not b else a / b
    return {
        "determinate_count": len(valid), "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn), "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "accuracy": ratio(tp + tn, tp + tn + fp + fn), "fpr": ratio(fp, fp + tn), "specificity": ratio(tn, tn + fp),
        "ordinary_negative_fpr": ratio(sum(r["predicted_status"] == "positive" for r in ordinary), len(ordinary)),
        "hard_negative_fpr": ratio(sum(r["predicted_status"] == "positive" for r in hard), len(hard)),
        "positive_recall": ratio(tp, tp + fn), "model_uncertain_count": uncertain, "model_uncertain_rate": ratio(uncertain, len(valid)),
        "gt_uncertain_prediction_distribution": dict(Counter(r["predicted_status"] for r in rows if r["event_label"] == "uncertain")),
    }


def main() -> None:
    if sha(SOURCE) != EXPECTED_SOURCE_SHA or sha(MANIFEST) != EXPECTED_MANIFEST_SHA:
        raise SystemExit("P3_C3_SCREEN_BASELINE_SOURCE_HASH_MISMATCH")
    rows = load_csv(SOURCE)
    manifest = load_csv(MANIFEST)
    if len(rows) != 120 or len(manifest) != 120:
        raise SystemExit("P3_C3_SCREEN_BASELINE_COUNT_MISMATCH")
    if {r["media_id"] for r in rows} != {r["media_id"] for r in manifest}:
        raise SystemExit("P3_C3_SCREEN_BASELINE_ENTITY_MISMATCH")
    if any((r.get("original_split") or r.get("split")) in {"VAL", "HOLDOUT"} for r in manifest):
        raise SystemExit("P3_C3_SCREEN_BASELINE_SCOPE_INVALID")
    out_predictions = OUT / "predictions.csv"
    OUT.mkdir(parents=True, exist_ok=True)
    if out_predictions.exists():
        raise SystemExit("P3_C3_SCREEN_BASELINE_OUTPUT_ALREADY_EXISTS")
    shutil.copyfile(SOURCE, out_predictions)
    with out_predictions.open("rb") as handle:
        os.fsync(handle.fileno())
    computed = metric(rows)
    source_summary = json.loads(SOURCE_SUMMARY.read_text(encoding="utf-8"))
    expected = source_summary.get("metrics")
    if any(computed.get(k) != expected.get(k) for k in ["TP", "FP", "TN", "FN", "precision", "recall", "f1", "accuracy", "ordinary_negative_fpr", "hard_negative_fpr", "positive_recall", "model_uncertain_count", "model_uncertain_rate"]):
        raise SystemExit("P3_C3_SCREEN_BASELINE_METRIC_RECOMPUTE_MISMATCH")
    summary = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT", "candidate": "C3_BASELINE", "phase": "screen_reuse",
        "source_stage": "P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION", "source_predictions_path": str(SOURCE),
        "source_predictions_sha256": sha(SOURCE), "predictions_sha256": sha(out_predictions),
        "manifest_path": str(MANIFEST), "manifest_sha256": sha(MANIFEST), "request_count": len(rows),
        "protocol_gate_pass": bool(source_summary.get("protocol_gate_pass")), "protocol": source_summary.get("protocol"),
        "metrics_direct": computed, "new_requests": 0, "val_requests": 0, "holdout_requests": 0,
        "screen_is_pristine": False, "p2_screen_individual_errors_used_for_p3_design": False,
    }
    atomic_json(OUT / "summary.json", summary)
    atomic_json(OUT / "baseline_source_attestation.json", {
        "source_predictions_sha256": sha(SOURCE), "source_manifest_sha256": sha(MANIFEST),
        "recomputed_metrics": computed, "reported_p2_metrics": expected, "metric_recompute_match": True,
        "screen_is_pristine": False, "new_requests": 0, "val_requests": 0, "holdout_requests": 0,
    })
    (OUT / "summary.md").write_text("# P3 C3 SCREEN baseline reuse\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n```\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
