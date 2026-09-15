#!/usr/bin/env python3
"""P3 SCREEN analysis, paired comparison, latency audit, and no-winner gate."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
SHARED = P3 / "05_screen/S1_STRUCTURED"
BASE = P3 / "05_screen/C3_BASELINE"
OUT = P3 / "05_screen"
REFERENCE_LATENCY = 1.852084
FP_FIELDS = [
    "media_id", "event_label", "sample_role", "scenario_id", "group_id", "predicted_status", "rule_status", "evidence",
    "real_person", "support_surface", "torso_pelvis_state", "active_nonlying_support", "nonlying_posture_type",
    "latency_seconds", "structured_conflict", "conflict_reason",
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_json(path: Path, obj: object) -> None:
    write_atomic(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def ratio(a: int, b: int) -> float | None:
    return None if not b else a / b


def metric(rows: list[dict[str, str]], status_key: str = "predicted_status", canonical_key: str = "canonical_ok") -> dict:
    valid = [r for r in rows if r["event_label"] in {"0", "1"} and r.get(canonical_key) == "true"]
    tp = fp = tn = fn = 0
    for row in valid:
        gt = row["event_label"]
        alert = row.get(status_key) == "positive"
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
    uncertain = sum(r.get(status_key) == "uncertain" for r in valid)
    return {
        "determinate_count": len(valid), "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn), "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "accuracy": ratio(tp + tn, tp + tn + fp + fn), "fpr": ratio(fp, fp + tn), "specificity": ratio(tn, tn + fp),
        "ordinary_negative_fpr": ratio(sum(r.get(status_key) == "positive" for r in ordinary), len(ordinary)),
        "hard_negative_fpr": ratio(sum(r.get(status_key) == "positive" for r in hard), len(hard)),
        "positive_recall": ratio(tp, tp + fn), "model_uncertain_count": uncertain,
        "model_uncertain_rate": ratio(uncertain, len(valid)),
        "gt_uncertain_prediction_distribution": dict(Counter(r.get(status_key, "") for r in rows if r["event_label"] == "uncertain")),
    }


def taxonomy_name(scenario_id: str) -> str:
    value = scenario_id.lower()
    if "sitting-on-floor" in value:
        return "sitting_on_floor"
    if "squatting" in value:
        return "squatting_or_crouching"
    if "exercise-push-up-plank" in value:
        return "exercise_pushup_or_plank"
    if "crawling-under-equipment-inspection" in value:
        return "crawling_or_kneeling_support"
    if "kneeling" in value:
        return "kneeling_or_half_kneeling"
    if "deep-bending" in value:
        return "deep_bending_or_picking"
    return "other"


def make_variant_rows(shared: list[dict[str, str]], variant: str) -> list[dict[str, str]]:
    rows = []
    for source in shared:
        row = dict(source)
        status = source["predicted_status"] if variant == "S1_DIRECT" else source["rule_status"]
        canonical = source["canonical_ok"] if variant == "S1_DIRECT" else source["rule_canonical_ok"]
        correct = source["direct_is_correct"] if variant == "S1_DIRECT" else source["rule_is_correct"]
        row["decision_variant"] = variant
        row["predicted_status"] = status
        row["predicted_binary_alert"] = str(status == "positive").lower() if canonical == "true" else ""
        row["canonical_ok"] = canonical
        row["is_correct"] = correct
        row["variant_source_stream"] = "S1_STRUCTURED"
        rows.append(row)
    return rows


def variant_summary(rows: list[dict[str, str]], variant: str, source_summary: dict) -> dict:
    metrics = metric(rows)
    n = len(rows)
    latencies = [float(r["latency_seconds"]) for r in rows if r.get("latency_seconds")]
    warm = latencies[1:]
    protocol_latency = source_summary.get("protocol", {}).get("latency_seconds", {})
    q = lambda values, p: None if not values else sorted(values)[int(round((len(values) - 1) * p))]
    return {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT", "phase": "screen", "candidate": variant,
        "source_stream": "S1_STRUCTURED", "stream_request_count": n, "protocol": source_summary["protocol"],
        "protocol_gate_pass": source_summary["protocol_gate_pass"], "metrics": metric(rows),
        "structured_conflict_count": source_summary["structured_conflict_count"],
        "structured_conflict_rate": source_summary["structured_conflict_rate"],
        "latency_seconds": {
            "cold": latencies[0] if latencies else None, "warm_mean": statistics.mean(warm) if warm else None,
            "p50": protocol_latency.get("p50", q(warm, 0.5)), "p95": protocol_latency.get("p95", q(warm, 0.95)), "max": protocol_latency.get("max", max(warm) if warm else None),
            "observed_p50": protocol_latency.get("observed_p50", q(latencies, 0.5)), "observed_p95": protocol_latency.get("observed_p95", q(latencies, 0.95)), "observed_max": protocol_latency.get("observed_max", max(latencies) if latencies else None),
        },
        "new_requests": n, "val_requests": 0, "holdout_requests": 0, "screen_is_pristine": False,
        "p2_screen_individual_errors_used_for_p3_design": False,
        "predictions_sha256": None,
    }


def write_variant_artifacts(rows: list[dict[str, str]], variant: str, source_summary: dict) -> dict:
    dest = OUT / variant
    dest.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    write_csv(dest / "predictions.csv", rows, fields)
    summary = variant_summary(rows, variant, source_summary)
    summary["predictions_sha256"] = sha(dest / "predictions.csv")
    write_json(dest / "summary.json", summary)
    write_atomic(dest / "summary.md", "# P3 SCREEN " + variant + "\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n```\n")
    write_csv(dest / "false_positives.csv", [r for r in rows if r["event_label"] == "0" and r["predicted_status"] == "positive"], FP_FIELDS)
    write_csv(dest / "false_negatives.csv", [r for r in rows if r["event_label"] == "1" and r["predicted_status"] != "positive"], FP_FIELDS)
    write_csv(dest / "model_uncertain.csv", [r for r in rows if r["event_label"] in {"0", "1"} and r["predicted_status"] == "uncertain"], FP_FIELDS)
    # Keep one explicit pointer to the single durable response stream rather
    # than suggesting DIRECT and RULE made separate model calls.
    write_json(dest / "shared_response_stream.json", {
        "source_directory": str(SHARED), "source_predictions_sha256": sha(SHARED / "predictions.csv"),
        "model_requests": 0, "derived_offline_from": "S1_STRUCTURED", "variant": variant,
    })
    return summary


def paired_rows(base: list[dict[str, str]], candidate: list[dict[str, str]], variant: str) -> tuple[list[dict], dict]:
    bmap = {r["media_id"]: r for r in base}
    cmap = {r["media_id"]: r for r in candidate}
    if set(bmap) != set(cmap):
        raise SystemExit("P3_PAIRED_ENTITY_SET_MISMATCH")
    rows = []
    counts = Counter()
    for media_id in sorted(bmap):
        b = bmap[media_id]; c = cmap[media_id]; gt = b["event_label"]
        bs = b["predicted_status"]; cs = c["predicted_status"]
        b_alert = bs == "positive"; c_alert = cs == "positive"
        b_correct = "" if gt == "uncertain" else ((gt == "1") == b_alert)
        c_correct = "" if gt == "uncertain" else ((gt == "1") == c_alert)
        transition = f"{bs}->{cs}"
        rows.append({"media_id": media_id, "event_label": gt, "sample_role": b["sample_role"], "scenario_id": b["scenario_id"], "group_id": b["group_id"], "taxonomy": taxonomy_name(b["scenario_id"]), "c3_status": bs, "candidate": variant, "candidate_status": cs, "transition": transition, "c3_correct": b_correct, "candidate_correct": c_correct})
        if gt == "0" and bs == "positive" and cs == "negative": counts["C3_FP_to_candidate_TN"] += 1
        if gt == "0" and bs == "positive" and cs == "uncertain": counts["C3_FP_to_candidate_uncertain"] += 1
        if gt == "0" and bs != "positive" and cs == "positive": counts["C3_TN_to_candidate_FP"] += 1
        if gt == "1" and bs == "positive" and cs == "negative": counts["C3_TP_to_candidate_FN"] += 1
        if gt == "1" and bs == "positive" and cs == "uncertain": counts["C3_TP_to_candidate_uncertain"] += 1
        if gt == "1" and bs != "positive" and cs == "positive": counts["C3_FN_to_candidate_TP"] += 1
    return rows, dict(counts)


def component_stats(path_raw: Path, path_log: Path, candidate: str) -> tuple[list[dict], dict]:
    raw_rows = [json.loads(line) for line in path_raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    log_rows = [json.loads(line) for line in path_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {r["media_id"]: r for r in log_rows}
    out = []
    for raw in raw_rows:
        outer = raw.get("outer_json") or {}
        log = by_id.get(raw["media_id"], {})
        values = {}
        for key in ["total_duration", "load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_count", "eval_count"]:
            value = outer.get(key)
            if key.endswith("duration") and isinstance(value, (int, float)):
                value = value / 1_000_000_000
            values[key] = value
        values.update({"candidate": candidate, "media_id": raw["media_id"], "request_id": raw.get("request_id"), "client_latency_seconds": log.get("latency_seconds")})
        out.append(values)
    durations = [float(r["load_duration"]) for r in out if isinstance(r.get("load_duration"), (int, float))]
    high = [d > 5.0 for d in durations]
    longest = 0; current = 0
    for flag in high:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    stats = {
        "candidate": candidate, "request_count": len(out),
        "component_p50": {}, "component_p95": {}, "component_max": {},
        "load_duration_gt_5s_count": sum(high), "longest_sustained_load_gt_5s": longest,
        "sustained_load_anomaly": longest >= 3,
    }
    for key in ["total_duration", "load_duration", "prompt_eval_duration", "eval_duration", "client_latency_seconds"]:
        vals = [float(r[key]) for r in out if isinstance(r.get(key), (int, float))]
        if vals:
            vals.sort(); stats["component_p50"][key] = vals[int(round((len(vals) - 1) * 0.50))]; stats["component_p95"][key] = vals[int(round((len(vals) - 1) * 0.95))]; stats["component_max"][key] = max(vals)
    return out, stats


def main() -> None:
    base = load_csv(BASE / "predictions.csv")
    shared = load_csv(SHARED / "predictions.csv")
    base_summary = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))
    shared_summary = json.loads((SHARED / "summary.json").read_text(encoding="utf-8"))
    if len(base) != 120 or len(shared) != 120 or {r["media_id"] for r in base} != {r["media_id"] for r in shared}:
        raise SystemExit("P3_SCREEN_ANALYSIS_ENTITY_OR_COUNT_MISMATCH")
    if not base_summary.get("protocol_gate_pass") or not shared_summary.get("protocol_gate_pass"):
        raise SystemExit("P3_SCREEN_PROTOCOL_GATE_FAIL")
    direct = make_variant_rows(shared, "S1_DIRECT")
    rule = make_variant_rows(shared, "S1_RULE")
    direct_summary = write_variant_artifacts(direct, "S1_DIRECT", shared_summary)
    rule_summary = write_variant_artifacts(rule, "S1_RULE", shared_summary)

    paired_all = []
    paired_summary = {}
    for variant, rows in [("S1_DIRECT", direct), ("S1_RULE", rule)]:
        changes, counts = paired_rows(base, rows, variant)
        paired_all.extend(changes)
        paired_summary[variant] = counts
    write_csv(OUT / "paired_changes.csv", paired_all, list(paired_all[0]) if paired_all else [])

    # Direct-vs-rule discrepancy is an explicit audit, not a hidden selector.
    direct_by = {r["media_id"]: r for r in direct}; rule_by = {r["media_id"]: r for r in rule}
    direct_wrong_rule_correct = 0; direct_correct_rule_wrong = 0
    for media_id in direct_by:
        d = direct_by[media_id]; r = rule_by[media_id]; gt = d["event_label"]
        if gt not in {"0", "1"}:
            continue
        d_ok = ((gt == "1") == (d["predicted_status"] == "positive")); r_ok = ((gt == "1") == (r["predicted_status"] == "positive"))
        if not d_ok and r_ok: direct_wrong_rule_correct += 1
        if d_ok and not r_ok: direct_correct_rule_wrong += 1

    hard = [r for r in base if r["sample_role"] == "hard_negative"]
    base_by_id = {r["media_id"]: r for r in base}
    taxonomy_rows = []
    for tax in sorted({taxonomy_name(r["scenario_id"]) for r in hard}):
        ids = {r["media_id"] for r in hard if taxonomy_name(r["scenario_id"]) == tax}
        # Keep this deliberately explicit to avoid an accidental use of GT
        # uncertain or ordinary negatives in the hard-negative denominator.
        bfp = sum(base_by_id[media_id]["predicted_status"] == "positive" for media_id in ids)
        dfp = sum(direct_by[media_id]["predicted_status"] == "positive" for media_id in ids)
        rfp = sum(rule_by[media_id]["predicted_status"] == "positive" for media_id in ids)
        taxonomy_rows.append({"taxonomy": tax, "total_hard_negative": len(ids), "group_count": len({base_by_id[media_id]["group_id"] for media_id in ids}), "C3_error_count": bfp, "S1_DIRECT_error_count": dfp, "S1_RULE_error_count": rfp, "S1_DIRECT_delta_vs_C3": dfp - bfp, "S1_RULE_delta_vs_C3": rfp - bfp, "C3_FPR": ratio(bfp, len(ids)), "S1_DIRECT_FPR": ratio(dfp, len(ids)), "S1_RULE_FPR": ratio(rfp, len(ids))})
    write_csv(OUT / "taxonomy_comparison.csv", taxonomy_rows)

    group_rows = []
    for group in sorted({r["group_id"] for r in hard}):
        ids = {r["media_id"] for r in hard if r["group_id"] == group}
        bfp = sum(base_by_id[media_id]["predicted_status"] == "positive" for media_id in ids)
        dfp = sum(direct_by[media_id]["predicted_status"] == "positive" for media_id in ids)
        rfp = sum(rule_by[media_id]["predicted_status"] == "positive" for media_id in ids)
        group_rows.append({"group_id": group, "taxonomy": taxonomy_name(next(base_by_id[mid]["scenario_id"] for mid in ids)), "hard_negative_count": len(ids), "C3_FP": bfp, "S1_DIRECT_FP": dfp, "S1_RULE_FP": rfp, "C3_has_FP": bool(bfp), "S1_DIRECT_has_FP": bool(dfp), "S1_RULE_has_FP": bool(rfp)})
    write_csv(OUT / "group_metrics.csv", group_rows)
    group_summary = {"hard_negative_group_count": len(group_rows), "C3_groups_with_FP": sum(r["C3_has_FP"] for r in group_rows), "S1_DIRECT_groups_with_FP": sum(r["S1_DIRECT_has_FP"] for r in group_rows), "S1_RULE_groups_with_FP": sum(r["S1_RULE_has_FP"] for r in group_rows), "C3_group_level_hard_negative_error_rate": ratio(sum(r["C3_has_FP"] for r in group_rows), len(group_rows)), "S1_DIRECT_group_level_hard_negative_error_rate": ratio(sum(r["S1_DIRECT_has_FP"] for r in group_rows), len(group_rows)), "S1_RULE_group_level_hard_negative_error_rate": ratio(sum(r["S1_RULE_has_FP"] for r in group_rows), len(group_rows))}

    s1_components, s1_latency = component_stats(SHARED / "raw_responses.jsonl", SHARED / "request_log.jsonl", "S1_STRUCTURED")
    p2_raw = P2 / "04_screening/C3/raw_responses.jsonl"; p2_log = P2 / "04_screening/C3/request_log.jsonl"
    c3_components, c3_latency = component_stats(p2_raw, p2_log, "C3_BASELINE") if p2_raw.is_file() and p2_log.is_file() else ([], {"candidate": "C3_BASELINE", "request_count": 0, "component_p50": {}, "component_p95": {}, "component_max": {}, "load_duration_gt_5s_count": 0, "longest_sustained_load_gt_5s": 0, "sustained_load_anomaly": False})
    latency_components = s1_components + c3_components
    write_csv(OUT / "latency_components.csv", latency_components)
    write_json(OUT / "runtime_latency_summary.json", {"reference_limit_seconds": REFERENCE_LATENCY, "C3_BASELINE": c3_latency, "S1_STRUCTURED": s1_latency, "runtime_anomaly_detected": bool(s1_latency.get("sustained_load_anomaly"))})

    candidate_rows = [
        {"candidate": "C3_BASELINE", **base_summary["metrics_direct"], "protocol_gate": base_summary["protocol_gate_pass"], "structured_conflict_rate": 0.0, "p50": base_summary.get("protocol", {}).get("latency_seconds", {}).get("p50"), "p95": base_summary.get("protocol", {}).get("latency_seconds", {}).get("p95"), "positive_recall": base_summary["metrics_direct"]["positive_recall"], "advancement_gate": False, "reference_quality_pass": False, "decision": "historical_baseline"},
        {"candidate": "S1_DIRECT", **direct_summary["metrics"], "protocol_gate": direct_summary["protocol_gate_pass"], "structured_conflict_rate": direct_summary["structured_conflict_rate"], "p50": direct_summary["latency_seconds"]["observed_p50"], "p95": direct_summary["latency_seconds"]["observed_p95"], "positive_recall": direct_summary["metrics"]["positive_recall"], "advancement_gate": bool(direct_summary["protocol_gate_pass"] and direct_summary["metrics"]["positive_recall"] >= .95 and direct_summary["metrics"]["ordinary_negative_fpr"] == 0 and direct_summary["metrics"]["hard_negative_fpr"] <= .075), "reference_quality_pass": bool(direct_summary["metrics"]["precision"] >= .93 and direct_summary["metrics"]["hard_negative_fpr"] <= .05 and direct_summary["metrics"]["positive_recall"] >= .95 and direct_summary["metrics"]["ordinary_negative_fpr"] == 0), "decision": "not_eligible"},
        {"candidate": "S1_RULE", **rule_summary["metrics"], "protocol_gate": rule_summary["protocol_gate_pass"], "structured_conflict_rate": rule_summary["structured_conflict_rate"], "p50": rule_summary["latency_seconds"]["observed_p50"], "p95": rule_summary["latency_seconds"]["observed_p95"], "positive_recall": rule_summary["metrics"]["positive_recall"], "advancement_gate": bool(rule_summary["protocol_gate_pass"] and rule_summary["metrics"]["positive_recall"] >= .95 and rule_summary["metrics"]["ordinary_negative_fpr"] == 0 and rule_summary["metrics"]["hard_negative_fpr"] <= .075), "reference_quality_pass": bool(rule_summary["metrics"]["precision"] >= .93 and rule_summary["metrics"]["hard_negative_fpr"] <= .05 and rule_summary["metrics"]["positive_recall"] >= .95 and rule_summary["metrics"]["ordinary_negative_fpr"] == 0), "decision": "not_eligible"},
    ]
    # Remove the helper-only keys and keep a stable human-facing table.
    write_csv(OUT / "comparison.csv", candidate_rows)
    eligible = [r["candidate"] for r in candidate_rows if r["candidate"] != "C3_BASELINE" and r["advancement_gate"]]
    winner = None
    if eligible:
        winner = sorted(eligible, key=lambda c: (next(r for r in candidate_rows if r["candidate"] == c)["hard_negative_fpr"], -next(r for r in candidate_rows if r["candidate"] == c)["positive_recall"], -next(r for r in candidate_rows if r["candidate"] == c)["precision"], next(r for r in candidate_rows if r["candidate"] == c)["p95"]))[0]
    decision = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT", "screen_is_pristine": False,
        "p2_screen_individual_errors_used_for_p3_design": False, "val_individual_errors_used_for_p3_design": False,
        "optional_s2_created": False, "candidates": ["C3_BASELINE", "S1_DIRECT", "S1_RULE", "OPTIONAL_S2"],
        "eligible_candidates": eligible, "winner": winner or "NONE", "selection_rule": ["minimum hard_negative_fpr", "maximum positive_recall", "maximum precision", "maximum f1", "minimum model_uncertain_rate", "minimum p95"],
        "advancement_gate": {"protocol": "100%", "positive_recall_min": .95, "ordinary_negative_fpr": 0, "hard_negative_fpr_max": .075},
        "reference_quality_gate": {"precision_min": .93, "hard_negative_fpr_max": .05, "positive_recall_min": .95, "ordinary_negative_fpr": 0},
        "candidate_rows": candidate_rows, "paired_summary": paired_summary, "direct_wrong_rule_correct": direct_wrong_rule_correct,
        "direct_correct_rule_wrong": direct_correct_rule_wrong, "group_summary": group_summary,
        "p3_runtime_gate": "PASS" if direct_summary["latency_seconds"]["observed_p95"] is not None and direct_summary["latency_seconds"]["observed_p95"] <= REFERENCE_LATENCY and not s1_latency.get("sustained_load_anomaly") else "FAIL",
        "p3_runtime_anomaly_detected": bool(s1_latency.get("sustained_load_anomaly")),
        "p3_reference_quality_pass": bool(winner and next(r for r in candidate_rows if r["candidate"] == winner)["reference_quality_pass"]),
        "p3_holdout_ready_quality": False, "p3_holdout_ready_runtime": False, "p3_holdout_ready": False,
        "new_dev_requests": 190 + 12 + 120, "new_val_requests": 0, "holdout_requests": 0, "holdout_consumed": False,
    }
    write_json(OUT / "winner_decision.json", decision)
    write_json(OUT / "structured_consistency_audit.json", {
        "candidate": "S1_STRUCTURED", "row_count": len(shared), "structured_conflict_count": shared_summary["structured_conflict_count"], "structured_conflict_rate": shared_summary["structured_conflict_rate"], "direct_rule_disagreement_count": sum(direct_by[mid]["predicted_status"] != rule_by[mid]["predicted_status"] for mid in direct_by), "direct_wrong_rule_correct": direct_wrong_rule_correct, "direct_correct_rule_wrong": direct_correct_rule_wrong,
    })
    write_json(OUT / "screen_analysis_summary.json", {"C3_BASELINE": base_summary, "S1_DIRECT": direct_summary, "S1_RULE": rule_summary, "decision": decision, "taxonomy": taxonomy_rows, "groups": group_summary, "latency": {"C3_BASELINE": c3_latency, "S1_STRUCTURED": s1_latency}})
    print(json.dumps({"winner": winner or "NONE", "eligible": eligible, "direct_metrics": direct_summary["metrics"], "rule_metrics": rule_summary["metrics"], "p3_runtime_gate": decision["p3_runtime_gate"], "p3_holdout_ready": False}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
