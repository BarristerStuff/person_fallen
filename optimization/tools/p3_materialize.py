#!/usr/bin/env python3
"""Materialize P3 durable responses without using ``thinking``.

For a structured run the same response is materialized twice: the model's
``person_fallen`` field (S1_DIRECT) and the frozen deterministic rule
(S1_RULE).  No new model request is made for the second view.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
CFG = P3 / "03_candidates/p3_request_config.json"
RUNNER = ROOT / "tools/p3_inference_runner.py"
FIELDS = [
    "request_id", "media_id", "split", "event_label", "sample_role", "scenario_id", "group_id",
    "image_sha256", "predicted_status", "predicted_binary_alert", "evidence",
    "response_nonempty", "thinking_present", "http_ok", "json_ok", "schema_ok", "canonical_ok",
    "attempt_count", "latency_seconds", "done", "done_reason", "eval_count", "is_correct", "error_type",
    "real_person", "support_surface", "torso_pelvis_state", "active_nonlying_support",
    "nonlying_posture_type", "direct_status", "direct_alert", "rule_status", "rule_alert",
    "direct_is_correct", "rule_is_correct", "structured_conflict", "conflict_reason",
]
STRUCTURED_FIELDS = {
    "real_person": {"yes", "no", "uncertain"},
    "support_surface": {"abnormal_non_rest_surface", "normal_rest_surface", "uncertain"},
    "torso_pelvis_state": {"lying", "nonlying", "uncertain"},
    "active_nonlying_support": {"yes", "no", "uncertain"},
    "nonlying_posture_type": {"none", "seated", "kneeling", "squatting_or_crouching", "bending", "exercise_supported", "upright_or_walking", "other_nonlying", "uncertain"},
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (position - low)


def parse_response(wrapper: dict, structured: bool) -> dict:
    outer = wrapper.get("outer_json") or {}
    response = outer.get("response", "")
    thinking = outer.get("thinking", "")
    result = {
        "response_nonempty": isinstance(response, str) and bool(response.strip()),
        "thinking_present": isinstance(thinking, str) and bool(thinking.strip()),
        "json_ok": False,
        "schema_ok": False,
        "canonical_ok": False,
        "status": "protocol_failure",
        "evidence": "",
        "direct_status": "protocol_failure",
        "rule_status": "protocol_failure",
        "fields": {name: "" for name in STRUCTURED_FIELDS},
        "error": "",
        "conflict": False,
        "conflict_reason": "",
    }
    if not result["response_nonempty"]:
        result["error"] = "response_empty"
        return result
    try:
        obj = json.loads(response)
        result["json_ok"] = True
    except Exception as exc:
        result["error"] = "response_json_failure: " + str(exc)
        return result
    if not isinstance(obj, dict):
        result["error"] = "response_not_object"
        return result
    if structured:
        expected = set(STRUCTURED_FIELDS) | {"person_fallen", "evidence"}
        if set(obj) != expected:
            result["error"] = "structured_schema_keys_failure"
            return result
        for name, allowed in STRUCTURED_FIELDS.items():
            if not isinstance(obj.get(name), str) or obj[name] not in allowed:
                result["error"] = "structured_enum_failure:" + name
                return result
    else:
        if set(obj) != {"person_fallen", "evidence"}:
            result["error"] = "c3_schema_keys_failure"
            return result
    if obj.get("person_fallen") not in {"positive", "negative", "uncertain"}:
        result["error"] = "person_fallen_enum_failure"
        return result
    if not isinstance(obj.get("evidence"), str) or not obj["evidence"].strip():
        result["error"] = "evidence_failure"
        return result
    result["schema_ok"] = True
    result["canonical_ok"] = True
    result["status"] = obj["person_fallen"]
    result["direct_status"] = obj["person_fallen"]
    result["evidence"] = obj["evidence"].strip()
    if structured:
        for name in STRUCTURED_FIELDS:
            result["fields"][name] = obj[name]
        if obj["real_person"] == "no":
            rule = "negative"
        elif obj["support_surface"] == "normal_rest_surface":
            rule = "negative"
        elif obj["torso_pelvis_state"] == "nonlying":
            rule = "negative"
        elif obj["active_nonlying_support"] == "yes":
            rule = "negative"
        elif (
            obj["real_person"] == "yes"
            and obj["support_surface"] == "abnormal_non_rest_surface"
            and obj["torso_pelvis_state"] == "lying"
            and obj["active_nonlying_support"] == "no"
        ):
            rule = "positive"
        else:
            rule = "uncertain"
        result["rule_status"] = rule
        reasons = []
        if obj["real_person"] == "no" and obj["person_fallen"] == "positive":
            reasons.append("real_person_no_vs_positive")
        if obj["support_surface"] == "normal_rest_surface" and obj["person_fallen"] == "positive":
            reasons.append("normal_rest_surface_vs_positive")
        if obj["torso_pelvis_state"] == "nonlying" and obj["person_fallen"] == "positive":
            reasons.append("nonlying_torso_vs_positive")
        if obj["active_nonlying_support"] == "yes" and obj["person_fallen"] == "positive":
            reasons.append("active_support_vs_positive")
        if obj["torso_pelvis_state"] == "lying" and obj["active_nonlying_support"] == "yes":
            reasons.append("lying_and_active_support_attribute_conflict")
        result["conflict_reason"] = ";".join(reasons)
        result["conflict"] = bool(reasons)
    return result


def metric(rows: list[dict], variant: str = "direct") -> dict:
    status_key = "predicted_status" if variant == "direct" else "rule_status"
    valid = [r for r in rows if r["event_label"] in {"0", "1"} and (r["canonical_ok"] if variant == "direct" else r["rule_canonical_ok"]) == "true"]
    tp = fp = tn = fn = 0
    for row in valid:
        gt = row["event_label"]
        alert = row[status_key] == "positive"
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
    uncertain = sum(r[status_key] == "uncertain" for r in valid)
    ratio = lambda a, b: None if not b else a / b
    return {
        "determinate_count": len(valid), "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn), "accuracy": ratio(tp + tn, tp + tn + fp + fn),
        "fpr": ratio(fp, fp + tn), "specificity": ratio(tn, tn + fp),
        "ordinary_negative_fpr": ratio(sum(r[status_key] == "positive" for r in ordinary), len(ordinary)),
        "hard_negative_fpr": ratio(sum(r[status_key] == "positive" for r in hard), len(hard)),
        "positive_recall": ratio(tp, tp + fn), "model_uncertain_count": uncertain,
        "model_uncertain_rate": ratio(uncertain, len(valid)),
        "gt_uncertain_prediction_distribution": dict(Counter(r[status_key] for r in rows if r["event_label"] == "uncertain")),
    }


def paths(phase: str, candidate: str) -> tuple[Path, Path]:
    if phase == "design":
        return P3 / "01_c3_design_baseline", P2 / "01_internal_split/p2_design_manifest.csv"
    if phase == "canary":
        return P3 / "04_canary", P3 / "04_canary/canary_manifest.csv"
    if phase == "screen":
        return P3 / "05_screen" / candidate, P2 / "01_internal_split/p2_screen_manifest.csv"
    raise ValueError(phase)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["design", "canary", "screen"])
    parser.add_argument("candidate", choices=["C3_BASELINE", "S1_STRUCTURED", "S1_DIRECT", "OPTIONAL_S2"])
    args = parser.parse_args()
    run_dir, manifest_path = paths(args.phase, args.candidate)
    manifest = load_csv(manifest_path)
    by_id = {row["media_id"]: row for row in manifest}
    db_path = run_dir / "request_ledger.sqlite3"
    if not db_path.is_file():
        raise SystemExit("P3_MATERIALIZE_LEDGER_MISSING")
    with sqlite3.connect(db_path) as db:
        metadata = dict(db.execute("SELECT k,v FROM metadata"))
        ledger = db.execute("SELECT request_id,ordinal,media_id,state,started_at,completed_at,attempt,http_status,latency_seconds,response_sha256,error_type FROM requests ORDER BY ordinal").fetchall()
        states = dict(db.execute("SELECT state,count(*) FROM requests GROUP BY state"))
    if states.get("STARTED", 0) or states.get("NOT_STARTED", 0):
        raise SystemExit("P3_MATERIALIZE_INDETERMINATE_REQUEST")
    structured = args.candidate != "C3_BASELINE"
    rows: list[dict] = []
    raw_rows: list[dict] = []
    log_rows: list[dict] = []
    for request_id, ordinal, media_id, state, started_at, completed_at, attempt, http_status, latency, response_sha, error_type in ledger:
        manifest_row = by_id[media_id]
        wrapper: dict = {}
        response_path = run_dir / "responses" / f"{request_id}.json"
        if state == "COMPLETED":
            if not response_path.is_file() or sha(response_path) != response_sha:
                raise SystemExit("P3_MATERIALIZE_RESPONSE_HASH_MISMATCH")
            wrapper = json.loads(response_path.read_text(encoding="utf-8"))
        parsed = parse_response(wrapper, structured=structured) if state == "COMPLETED" and http_status == 200 else parse_response(wrapper, structured=structured)
        if state != "COMPLETED":
            parsed["error"] = error_type or "request_failed_confirmed"
        outer = wrapper.get("outer_json") or {}
        split = manifest_row.get("split") or manifest_row.get("original_split") or ""
        direct = parsed["direct_status"]
        rule = parsed["rule_status"]
        gt = manifest_row["event_label"]
        direct_correct = "" if gt == "uncertain" or direct not in {"positive", "negative", "uncertain"} else str((gt == "1") == (direct == "positive")).lower()
        rule_correct = "" if gt == "uncertain" or rule not in {"positive", "negative", "uncertain"} else str((gt == "1") == (rule == "positive")).lower()
        row = {
            "request_id": request_id, "media_id": media_id, "split": split, "event_label": gt,
            "sample_role": manifest_row["sample_role"], "scenario_id": manifest_row["scenario_id"], "group_id": manifest_row["group_id"],
            "image_sha256": manifest_row["image_sha256"], "predicted_status": direct,
            "predicted_binary_alert": str(direct == "positive").lower() if parsed["canonical_ok"] else "",
            "evidence": parsed["evidence"], "response_nonempty": str(parsed["response_nonempty"]).lower(),
            "thinking_present": str(parsed["thinking_present"]).lower(), "http_ok": str(state == "COMPLETED" and http_status == 200).lower(),
            "json_ok": str(parsed["json_ok"]).lower(), "schema_ok": str(parsed["schema_ok"]).lower(),
            "canonical_ok": str(parsed["canonical_ok"]).lower(), "attempt_count": attempt,
            "latency_seconds": f"{latency:.6f}" if latency is not None else "", "done": str(outer.get("done", "")).lower(),
            "done_reason": outer.get("done_reason", ""), "eval_count": outer.get("eval_count", ""),
            "is_correct": direct_correct, "error_type": parsed["error"] or error_type or "",
            **parsed["fields"], "direct_status": direct, "direct_alert": str(direct == "positive").lower() if parsed["canonical_ok"] else "",
            "rule_status": rule, "rule_alert": str(rule == "positive").lower() if rule in {"positive", "negative", "uncertain"} else "",
            "direct_is_correct": direct_correct, "rule_is_correct": rule_correct,
            "structured_conflict": str(parsed["conflict"]).lower(), "conflict_reason": parsed["conflict_reason"],
        }
        row["rule_canonical_ok"] = str(rule in {"positive", "negative", "uncertain"} and parsed["schema_ok"]).lower()
        rows.append(row)
        raw_rows.append({
            "request_id": request_id, "ordinal": ordinal, "media_id": media_id,
            "outer_json": outer, "response": outer.get("response", ""), "thinking": outer.get("thinking", ""),
            "done": outer.get("done"), "done_reason": outer.get("done_reason"), "eval_count": outer.get("eval_count"),
        })
        log_rows.append({
            "request_id": request_id, "ordinal": ordinal, "media_id": media_id, "split": split, "state": state,
            "request_payload_config": wrapper.get("request_payload_without_image", {}),
            "timestamp_start_utc": started_at, "timestamp_end_utc": completed_at, "attempt": attempt,
            "http_code": http_status, "latency_seconds": latency, "response_sha256": response_sha,
            "image_sha256": manifest_row["image_sha256"], "prompt_sha256": wrapper.get("prompt_sha256", metadata.get("prompt_sha256")),
            "config_sha256": wrapper.get("config_sha256", metadata.get("config_sha256")), "done": outer.get("done"),
            "done_reason": outer.get("done_reason"), "eval_count": outer.get("eval_count"),
            "error_type": parsed["error"] or error_type or "",
        })

    # Keep the response-backed primary rows and durable audit files together.
    atomic_csv(run_dir / "predictions.csv", rows, FIELDS + ["rule_canonical_ok"])
    atomic_csv(run_dir / "protocol_failures.csv", [r for r in rows if r["canonical_ok"] != "true"], FIELDS + ["rule_canonical_ok"])
    atomic_text(run_dir / "raw_responses.jsonl", "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in raw_rows))
    atomic_text(run_dir / "request_log.jsonl", "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in log_rows))
    n = len(rows)
    rates = lambda key: sum(r[key] == "true" for r in rows) / n if n else None
    latencies = [float(r["latency_seconds"]) for r in rows if r["latency_seconds"]]
    warm = latencies[1:]
    protocol = {
        "request_count": n,
        "http_success_rate": rates("http_ok"), "response_nonempty_rate": rates("response_nonempty"),
        "thinking_present_rate": rates("thinking_present"), "json_parse_success_rate": rates("json_ok"),
        "schema_success_rate": rates("schema_ok"), "canonical_prediction_success_rate": rates("canonical_ok"),
        "latency_seconds": {
            "cold": latencies[0] if latencies else None,
            "warm_mean": statistics.mean(warm) if warm else None,
            "p50": quantile(warm, 0.5), "p95": quantile(warm, 0.95), "max": max(warm) if warm else None,
            "observed_p50": quantile(latencies, 0.5), "observed_p95": quantile(latencies, 0.95), "observed_max": max(latencies) if latencies else None,
        },
        "prediction_distribution_direct": dict(Counter(r["predicted_status"] for r in rows)),
        "prediction_distribution_rule": dict(Counter(r["rule_status"] for r in rows)),
    }
    protocol_gate = all(protocol[key] == 1.0 for key in ["http_success_rate", "response_nonempty_rate", "json_parse_success_rate", "schema_success_rate", "canonical_prediction_success_rate"])
    summary = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT", "phase": args.phase, "candidate": args.candidate,
        "execution_status": "COMPLETE" if sum(states.values()) == n and set(states) <= {"COMPLETED", "FAILED_CONFIRMED"} else "INCOMPLETE",
        "ledger_states": states, "planned_requests": len(manifest), "holdout_requests": 0, "val_requests": 0,
        "manifest_sha256": sha(manifest_path), "prompt_sha256": metadata.get("prompt_sha256"), "config_sha256": sha(CFG),
        "runner_sha256": sha(RUNNER), "protocol": protocol, "protocol_gate_pass": protocol_gate,
        "metrics_direct": metric(rows, "direct") if args.phase in {"design", "screen"} and protocol_gate else None,
        "metrics_rule": metric(rows, "rule") if args.phase in {"screen"} and protocol_gate else None,
        "structured_conflict_count": sum(r["structured_conflict"] == "true" for r in rows) if structured else 0,
        "structured_conflict_rate": (sum(r["structured_conflict"] == "true" for r in rows) / n if structured and n else 0.0),
        "predictions_sha256": sha(run_dir / "predictions.csv"), "raw_responses_sha256": sha(run_dir / "raw_responses.jsonl"),
        "request_log_sha256": sha(run_dir / "request_log.jsonl"),
    }
    atomic_text(run_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(run_dir / "summary.md", "# P3 " + args.phase.upper() + " " + args.candidate + " summary\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n```\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
