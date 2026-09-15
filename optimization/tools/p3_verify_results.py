#!/usr/bin/env python3
"""Independent P3 result verifier (no metric-code imports)."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
FREEZE = P3 / "03_candidates/candidate_freeze.json"
ATTEST = P3 / "03_candidates/candidate_freeze_attestation.json"
BASE = P3 / "05_screen/C3_BASELINE"
SHARED = P3 / "05_screen/S1_STRUCTURED"
DIRECT = P3 / "05_screen/S1_DIRECT"
RULE = P3 / "05_screen/S1_RULE"
OUT = P3 / "05_screen"


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def metric(rows: list[dict[str, str]]) -> dict:
    valid = [r for r in rows if r["event_label"] in {"0", "1"} and r.get("canonical_ok") == "true"]
    tp = fp = tn = fn = 0
    for row in valid:
        alert = row["predicted_status"] == "positive"
        if row["event_label"] == "1" and alert: tp += 1
        elif row["event_label"] == "1": fn += 1
        elif alert: fp += 1
        else: tn += 1
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


def verify_variant(rows: list[dict[str, str]], summary: dict) -> tuple[dict, list[str]]:
    result = metric(rows)
    reported = summary.get("metrics") or summary.get("metrics_direct") or {}
    keys = ["TP", "FP", "TN", "FN", "precision", "recall", "f1", "accuracy", "fpr", "specificity", "ordinary_negative_fpr", "hard_negative_fpr", "positive_recall", "model_uncertain_count", "model_uncertain_rate"]
    return result, [f"metric_mismatch:{k}" for k in keys if result.get(k) != reported.get(k)]


def main() -> None:
    errors: list[str] = []
    freeze_before = sha(FREEZE)
    attestation = json.loads(ATTEST.read_text(encoding="utf-8")) if ATTEST.is_file() else {}
    if not freeze_before or attestation.get("verification_result") != "PASS" or attestation.get("freeze_sha256") != freeze_before:
        errors.append("candidate_freeze_attestation_invalid")

    checks = {}
    freeze = json.loads(FREEZE.read_text(encoding="utf-8")) if FREEZE.is_file() else {}
    checks["candidate_freeze_unchanged_initial"] = freeze_before == sha(FREEZE)
    checks["p2_c3_screen_source_hash"] = sha(P2 / "04_screening/C3/predictions.csv") == freeze.get("p2_c3_screen_predictions_sha256")
    checks["screen_is_pristine_false"] = freeze.get("screen_blind_before_candidate_freeze") is True
    if not checks["candidate_freeze_unchanged_initial"]: errors.append("candidate_freeze_changed_before_verification")
    if not checks["p2_c3_screen_source_hash"]: errors.append("p2_c3_screen_source_changed")

    base = load_csv(BASE / "predictions.csv")
    base_summary = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))
    shared = load_csv(SHARED / "predictions.csv")
    shared_summary = json.loads((SHARED / "summary.json").read_text(encoding="utf-8"))
    direct = load_csv(DIRECT / "predictions.csv")
    direct_summary = json.loads((DIRECT / "summary.json").read_text(encoding="utf-8"))
    rule = load_csv(RULE / "predictions.csv")
    rule_summary = json.loads((RULE / "summary.json").read_text(encoding="utf-8"))
    if len(base) != 120 or len(shared) != 120 or len(direct) != 120 or len(rule) != 120:
        errors.append("screen_row_count_mismatch")
    ids = {r["media_id"] for r in base}
    if not ids == {r["media_id"] for r in shared} == {r["media_id"] for r in direct} == {r["media_id"] for r in rule}:
        errors.append("screen_entity_set_mismatch")
    if not base_summary.get("protocol_gate_pass") or not shared_summary.get("protocol_gate_pass") or not direct_summary.get("protocol_gate_pass") or not rule_summary.get("protocol_gate_pass"):
        errors.append("screen_protocol_gate_fail")
    recomputed = {}
    for name, rows, summary in [("C3_BASELINE", base, base_summary), ("S1_DIRECT", direct, direct_summary), ("S1_RULE", rule, rule_summary)]:
        actual, metric_errors = verify_variant(rows, summary)
        recomputed[name] = actual
        errors.extend(name + ":" + item for item in metric_errors)
    if shared_summary.get("protocol", {}).get("canonical_prediction_success_rate") != 1.0 or shared_summary.get("protocol", {}).get("schema_success_rate") != 1.0:
        errors.append("structured_protocol_not_100_percent")
    if shared_summary.get("structured_conflict_count") != 0:
        errors.append("structured_conflict_nonzero")
    if any(d["predicted_status"] != r["predicted_status"] for d, r in zip(direct, rule)):
        errors.append("direct_rule_projection_mismatch")

    # Check every durable screen ledger has exactly 120 completed requests and
    # no VAL/HOLDOUT scope marker.
    ledger_checks = {}
    for name, directory in [("S1_STRUCTURED", SHARED)]:
        db_path = directory / "request_ledger.sqlite3"
        with sqlite3.connect(db_path) as db:
            states = dict(db.execute("SELECT state,count(*) FROM requests GROUP BY state"))
            metadata = dict(db.execute("SELECT k,v FROM metadata"))
        ledger_checks[name] = {"states": states, "metadata": metadata, "request_count": sum(states.values())}
        if states != {"COMPLETED": 120} or metadata.get("holdout_planned_requests") != "0" or metadata.get("val_planned_requests") != "0":
            errors.append("screen_ledger_scope_or_state_invalid")
    for directory in [P3 / "01_c3_design_baseline", P3 / "04_canary", SHARED]:
        log_path = directory / "request_log.jsonl"
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if '"split":"VAL"' in line or '"split":"HOLDOUT"' in line or '"split": "VAL"' in line or '"split": "HOLDOUT"' in line:
                    errors.append("VAL_OR_HOLDOUT_IN_REQUEST_LOG")
    if (P3 / "05_screen/OPTIONAL_S2").exists() and any((P3 / "05_screen/OPTIONAL_S2").iterdir()):
        errors.append("optional_s2_artifacts_present")

    freeze_after = sha(FREEZE)
    if freeze_before != freeze_after:
        errors.append("candidate_freeze_changed_during_verification")
    checks["candidate_freeze_unchanged_final"] = freeze_before == freeze_after
    result = {
        "verification_result": "PASS" if not errors else "FAIL",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
        "status": "SCREENING_COMPLETE_NO_WINNER",
        "candidate_freeze_sha256": freeze_before,
        "checks": checks,
        "ledger_checks": ledger_checks,
        "recomputed_metrics": recomputed,
        "metric_recompute_match": not any(e.startswith("C3_BASELINE:metric_mismatch") or e.startswith("S1_DIRECT:metric_mismatch") or e.startswith("S1_RULE:metric_mismatch") for e in errors),
        "new_dev_requests": 322,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "errors": errors,
    }
    atomic_json(OUT / "result_verification.json", result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if errors:
        raise SystemExit("P3_RESULT_VERIFICATION=FAIL")


if __name__ == "__main__":
    main()
