#!/usr/bin/env python3
"""Run the frozen v4 perception/policy candidate over all 436 DEV rows."""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from common import ROOT, atomic_csv, atomic_json, atomic_text, load_csv, load_json, sha256

sys.path.insert(0, str(ROOT / "policy"))
from deterministic_policy import map_attributes, validate_attributes  # noqa: E402


PLAN = ROOT / "protocol/v4_full_dev_execution_plan.json"
PROMPT = ROOT / "prompt/V4-A0_pose_attributes_prompt.txt"
POLICY = ROOT / "policy/deterministic_policy.py"
TEMPORAL_POLICY = ROOT / "policy/temporal_recheck.py"
CROP_MANIFEST = ROOT / "manifests/v4_full_dev_crop_manifest.csv"
DETECTOR_SUMMARY = ROOT / "detector/detector_full_dev_summary.json"

ATTRIBUTE_KEYS = [
    "person_visible", "pose", "torso_orientation", "torso_ground_contact",
    "head_shoulders_above_hips", "support_surface", "explicit_work_evidence",
    "visual_quality", "evidence",
]
POSITIVE_DECISIONS = {"ALERT_GROUND_LYING", "ATTENTION_NEAR_GROUND"}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def runtime_preflight(model_cfg: dict) -> dict:
    def get_json(suffix: str) -> dict:
        req = request.Request(model_cfg["endpoint"] + suffix, method="GET")
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    tags = get_json("/api/tags")
    models = {item.get("name"): item for item in tags.get("models", []) if isinstance(item, dict)}
    selected = models.get(model_cfg["name"])
    if selected is None or selected.get("digest") != model_cfg["digest"]:
        raise RuntimeError("runtime model name/digest mismatch")
    version = get_json("/api/version")
    if version.get("version") != model_cfg["ollama_version"]:
        raise RuntimeError("runtime Ollama version mismatch")
    return {"status": "PASS", "captured_at_utc": utc(), "selected_model": selected, "version": version}


def parse_outer(raw: str) -> tuple[dict | None, str]:
    try:
        outer = json.loads(raw)
        if not isinstance(outer, dict) or outer.get("done") is not True:
            return None, "OUTER_RESPONSE_NOT_COMPLETE"
        response_text = outer.get("response")
        if not isinstance(response_text, str):
            return None, "MISSING_RESPONSE_STRING"
        return validate_attributes(json.loads(response_text)), ""
    except Exception as exc:
        return None, f"STRICT_PARSE_FAILURE:{type(exc).__name__}:{exc}"


def call_model(model_cfg: dict, prompt: str, images: list[Path]) -> dict:
    payload = {
        "model": model_cfg["name"],
        "prompt": prompt,
        "images": [base64.b64encode(path.read_bytes()).decode("ascii") for path in images],
        "stream": model_cfg["stream"],
        "format": model_cfg["format"],
        "think": model_cfg["think"],
        "options": {
            "temperature": model_cfg["temperature"],
            "num_ctx": model_cfg["num_ctx"],
            "num_predict": model_cfg["num_predict"],
        },
    }
    started = time.monotonic()
    req = request.Request(
        model_cfg["endpoint"] + "/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=model_cfg["timeout_seconds"]) as response:
            raw = response.read().decode("utf-8")
            return {
                "http_status": response.status,
                "raw": raw,
                "latency_seconds": time.monotonic() - started,
                "transport_unknown": False,
            }
    except error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "raw": exc.read().decode("utf-8", errors="replace"),
            "latency_seconds": time.monotonic() - started,
            "transport_unknown": False,
            "error": f"HTTPError:{exc}",
        }
    except (error.URLError, TimeoutError, OSError) as exc:
        return {
            "http_status": None,
            "raw": "",
            "latency_seconds": time.monotonic() - started,
            "transport_unknown": True,
            "error": f"{type(exc).__name__}:{exc}",
        }


def verify_frozen_inputs(plan: dict) -> None:
    frozen = plan["frozen_components"]
    checks = [
        (PROMPT, frozen["prompt_sha256"]),
        (POLICY, frozen["policy_sha256"]),
        (TEMPORAL_POLICY, frozen["temporal_policy_sha256"]),
    ]
    for path, expected in checks:
        if sha256(path) != expected:
            raise RuntimeError(f"frozen component SHA mismatch: {path}")


def load_cache(plan: dict) -> dict[str, dict]:
    spec = plan["prerequisite_diagnostic"]
    run_dir = ROOT / spec["run_dir"]
    paths = {
        "summary": run_dir / "summary.json",
        "completion": run_dir / "COMPLETION_LOCK.json",
        "predictions": run_dir / "predictions.csv",
        "crop_manifest": ROOT / "manifests/v4_crop_manifest.csv",
    }
    expected = {
        "summary": spec["summary_sha256"],
        "completion": spec["completion_lock_sha256"],
        "predictions": spec["predictions_sha256"],
        "crop_manifest": spec["crop_manifest_sha256"],
    }
    for name, path in paths.items():
        if not path.is_file() or sha256(path) != expected[name]:
            raise RuntimeError(f"diagnostic cache integrity failure: {name}")
    summary = load_json(paths["summary"])
    completion = load_json(paths["completion"])
    if summary.get("gate_pass") is not spec["required_gate_pass"] or completion.get("status") != "COMPLETE":
        raise RuntimeError("prerequisite diagnostic is not a completed PASS")
    if summary.get("prompt_sha256") != plan["frozen_components"]["prompt_sha256"]:
        raise RuntimeError("diagnostic prompt does not match full DEV prompt")

    prior_crops = {row["item_id"]: row for row in load_csv(paths["crop_manifest"])}
    prior_predictions = {row["item_id"]: row for row in load_csv(paths["predictions"])}
    if set(prior_crops) != set(prior_predictions) or len(prior_crops) != spec["eligible_cache_rows"]:
        raise RuntimeError("diagnostic cache row mismatch")
    cache = {}
    for item_id in sorted(prior_crops):
        prediction = prior_predictions[item_id]
        attributes = validate_attributes({key: prediction[key] for key in ATTRIBUTE_KEYS})
        policy = map_attributes(attributes, detector_person_found=prior_crops[item_id]["person_detected"] == "true")
        if policy["frame_decision"] != prediction["frame_decision"] or policy["reason_code"] != prediction["reason_code"]:
            raise RuntimeError(f"cached policy replay mismatch: {item_id}")
        cache[item_id] = {"crop": prior_crops[item_id], "prediction": prediction, "attributes": attributes}
    return cache


def verify_cache_compatibility(rows: list[dict], cache: dict[str, dict], expected_count: int) -> int:
    """Prove every planned cache reuse has byte-identical model inputs before any POST."""
    matched = 0
    for row in rows:
        cached = cache.get(row["item_id"])
        if cached is None:
            continue
        old = cached["crop"]
        if (
            old["image_sha256"] != row["image_sha256"]
            or old["full_view_sha256"] != row["full_view_sha256"]
            or old["crop_view_sha256"] != row["crop_view_sha256"]
            or old["person_detected"] != row["person_detected"]
            or old["view_count"] != row["view_count"]
        ):
            raise RuntimeError(f"cache input mismatch; refusing reuse: {row['item_id']}")
        matched += 1
    if matched != expected_count:
        raise RuntimeError(f"expected {expected_count} compatible cache rows, found {matched}")
    return matched


def predicted_label(decision: str) -> str:
    if decision in POSITIVE_DECISIONS:
        return "positive"
    if decision == "NO_ALERT_NORMAL_POSE":
        return "negative"
    if decision == "RECHECK_VISUAL_UNCERTAIN":
        return "uncertain"
    raise RuntimeError(f"unknown frame decision: {decision}")


def make_record(
    row: dict,
    attributes: dict,
    policy: dict,
    *,
    person_found: bool,
    view_count: int,
    inference_source: str,
    request_id: str,
    latency_seconds: float,
) -> dict:
    decision = policy["frame_decision"]
    return {
        "diagnostic_id": row["diagnostic_id"],
        "item_id": row["item_id"],
        "taxonomy": row["taxonomy"],
        "ground_truth": row["ground_truth"],
        "metric_stratum": row["metric_stratum"],
        "expected_v4_outcome": row["expected_v4_outcome"],
        "person_detected": person_found,
        "view_count": view_count,
        "inference_source": inference_source,
        "request_id": request_id,
        "http_status": 200,
        "latency_seconds": latency_seconds,
        "strict_json_ok": True,
        "parse_error": "",
        **attributes,
        "frame_decision": decision,
        "reason_code": policy["reason_code"],
        "predicted_label": predicted_label(decision),
        "exact_expected_outcome": decision == row["expected_v4_outcome"],
    }


def summarize(rows: list[dict], plan: dict, detector_summary: dict, cache_count: int, request_count: int) -> dict:
    labeled = [row for row in rows if row["ground_truth"] in {"positive", "negative"}]
    positives = [row for row in labeled if row["ground_truth"] == "positive"]
    negatives = [row for row in labeled if row["ground_truth"] == "negative"]
    tp = sum(row["predicted_label"] == "positive" for row in positives)
    fn = len(positives) - tp
    tn = sum(row["predicted_label"] == "negative" for row in negatives)
    fp = len(negatives) - tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    hard = [row for row in negatives if row["metric_stratum"] == "hard_negative"]
    ordinary = [row for row in negatives if row["metric_stratum"] == "ordinary_negative"]
    hard_fp = sum(row["predicted_label"] != "negative" for row in hard)
    ordinary_fp = sum(row["predicted_label"] != "negative" for row in ordinary)
    source_uncertain = [row for row in rows if row["ground_truth"] == "uncertain"]
    attention_expected = [row for row in rows if row["expected_v4_outcome"] == "ATTENTION_NEAR_GROUND"]
    lying_expected = [row for row in rows if row["expected_v4_outcome"] == "ALERT_GROUND_LYING"]
    determinate_rechecks = sum(row["predicted_label"] == "uncertain" for row in labeled)
    new_latencies = [
        float(row["latency_seconds"]) for row in rows
        if row["inference_source"] == "NEW_MODEL_REQUEST"
    ]

    taxonomy = defaultdict(Counter)
    for row in rows:
        taxonomy[row["taxonomy"]][row["frame_decision"]] += 1
    taxonomy_metrics = {
        name: {"total": sum(counts.values()), "decisions": dict(counts)}
        for name, counts in sorted(taxonomy.items())
    }
    metrics = {
        "sample_count": len(rows),
        "labeled_count": len(labeled),
        "source_uncertain_count": len(source_uncertain),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": (tp + tn) / len(labeled),
        "hard_negative_count": len(hard),
        "hard_negative_fp": hard_fp,
        "hard_negative_fpr": hard_fp / len(hard),
        "ordinary_negative_count": len(ordinary),
        "ordinary_negative_fp": ordinary_fp,
        "ordinary_negative_fpr": ordinary_fp / len(ordinary),
        "strict_json_success": sum(row["strict_json_ok"] for row in rows) / len(rows),
        "detector_coverage": detector_summary["person_detection_coverage"],
        "determinate_recheck_count": determinate_rechecks,
        "determinate_recheck_rate": determinate_rechecks / len(labeled),
        "source_uncertain_recheck_count": sum(row["predicted_label"] == "uncertain" for row in source_uncertain),
        "source_uncertain_recheck_rate": (
            sum(row["predicted_label"] == "uncertain" for row in source_uncertain) / len(source_uncertain)
        ),
        "lying_alert_count": sum(row["frame_decision"] == "ALERT_GROUND_LYING" for row in lying_expected),
        "lying_alert_recall": (
            sum(row["frame_decision"] == "ALERT_GROUND_LYING" for row in lying_expected) / len(lying_expected)
        ),
        "attention_exact_count": sum(row["frame_decision"] == "ATTENTION_NEAR_GROUND" for row in attention_expected),
        "attention_exact_recall": (
            sum(row["frame_decision"] == "ATTENTION_NEAR_GROUND" for row in attention_expected) / len(attention_expected)
        ),
        "exact_expected_outcome_accuracy": sum(row["exact_expected_outcome"] for row in rows) / len(rows),
        "decision_distribution": dict(Counter(row["frame_decision"] for row in rows)),
        "pose_distribution": dict(Counter(row["pose"] for row in rows)),
        "cache_reuse_count": cache_count,
        "new_model_request_count": request_count,
        "new_request_latency_seconds": {
            "mean": statistics.mean(new_latencies) if new_latencies else None,
            "p50": percentile(new_latencies, 0.5),
            "p95": percentile(new_latencies, 0.95),
            "max": max(new_latencies) if new_latencies else None,
        },
        "taxonomy": taxonomy_metrics,
    }
    gate = plan["gate"]
    checks = {
        "precision": precision >= gate["precision_min"],
        "recall": recall >= gate["recall_min"],
        "hard_negative_fpr": metrics["hard_negative_fpr"] <= gate["hard_negative_fpr_max"],
        "ordinary_negative_fpr": metrics["ordinary_negative_fpr"] <= gate["ordinary_negative_fpr_max"],
        "strict_json": metrics["strict_json_success"] >= gate["strict_json_success_min"],
        "detector_coverage": metrics["detector_coverage"] >= gate["detector_coverage_min"],
    }
    return {"metrics": metrics, "gate_checks": checks, "gate_pass": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="dev_V4-A0-FULL-CROP-436")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    plan = load_json(PLAN)
    verify_frozen_inputs(plan)
    model_cfg = plan["model"]
    rows = load_csv(CROP_MANIFEST)
    if len(rows) != plan["expected_dev_counts"]["total"]:
        raise RuntimeError("full DEV crop manifest row count mismatch")
    if any(row["v3_split"] != "V3_DEV" or row["source_split"] == "HOLDOUT" for row in rows):
        raise RuntimeError("full DEV crop manifest scope failure")
    detector_summary = load_json(DETECTOR_SUMMARY)
    if detector_summary.get("status") != "PASS" or detector_summary.get("sample_count") != len(rows):
        raise RuntimeError("full DEV detector summary failure")
    if detector_summary["person_detection_coverage"] < plan["gate"]["detector_coverage_min"]:
        raise RuntimeError("detector coverage gate failed before VLM requests")
    cache = load_cache(plan)
    compatible_cache_count = verify_cache_compatibility(
        rows, cache, plan["prerequisite_diagnostic"]["eligible_cache_rows"]
    )

    run_dir = ROOT / "eval/runs" / args.run_id
    completion = run_dir / "COMPLETION_LOCK.json"
    terminal_unknown = run_dir / "TERMINAL_TRANSPORT_UNKNOWN.json"
    terminal_failure = run_dir / "TERMINAL_KNOWN_FAILURE.json"
    active_lock = run_dir / "ACTIVE.lock"
    events = run_dir / "request_events.jsonl"
    if completion.exists():
        raise RuntimeError("run is already complete and immutable")
    if terminal_unknown.exists() or terminal_failure.exists():
        raise RuntimeError("run has terminal failure state; create a new authorized run instead of resending")
    if active_lock.exists():
        raise RuntimeError("active or interrupted run lock exists")
    if events.exists() and events.stat().st_size:
        raise RuntimeError("partial request ledger exists; automatic resume/resend is forbidden")
    run_dir.mkdir(parents=True, exist_ok=True)
    preflight = runtime_preflight(model_cfg)
    preflight.update({
        "plan_sha256": sha256(PLAN),
        "prompt_sha256": sha256(PROMPT),
        "policy_sha256": sha256(POLICY),
        "crop_manifest_sha256": sha256(CROP_MANIFEST),
        "input_count": len(rows),
        "eligible_cache_rows": len(cache),
        "compatible_cache_rows": compatible_cache_count,
        "screen_rows_read": 0,
        "val_rows_read": 0,
        "holdout_rows_read": 0,
    })
    atomic_json(run_dir / "runtime_preflight.json", preflight)
    if args.preflight_only:
        print(json.dumps(preflight, ensure_ascii=False))
        return 0

    try:
        fd = os.open(active_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"pid={os.getpid()} started={utc()}\n".encode())
        os.close(fd)
    except FileExistsError as exc:
        raise RuntimeError("active or interrupted run lock exists") from exc

    prompt = PROMPT.read_text(encoding="utf-8")
    output_rows: list[dict] = []
    cache_count = 0
    request_count = 0
    try:
        for index, row in enumerate(rows, 1):
            full = Path(row["full_view_path"])
            crop = Path(row["crop_view_path"])
            if sha256(full) != row["full_view_sha256"] or sha256(crop) != row["crop_view_sha256"]:
                raise RuntimeError(f"prepared view SHA mismatch: {row['diagnostic_id']}")
            person_found = row["person_detected"] == "true"
            images = [full, crop] if person_found else [full]
            cached = cache.get(row["item_id"])
            if cached is not None:
                old = cached["crop"]
                if (
                    old["image_sha256"] != row["image_sha256"]
                    or old["full_view_sha256"] != row["full_view_sha256"]
                    or old["crop_view_sha256"] != row["crop_view_sha256"]
                    or old["person_detected"] != row["person_detected"]
                ):
                    raise RuntimeError(f"cache input mismatch; refusing reuse: {row['item_id']}")
                prediction = cached["prediction"]
                attributes = cached["attributes"]
                policy = map_attributes(attributes, detector_person_found=person_found)
                record = make_record(
                    row, attributes, policy,
                    person_found=person_found,
                    view_count=len(images),
                    inference_source="CACHE_REUSE_IDENTICAL_INPUT",
                    request_id=prediction["diagnostic_id"],
                    latency_seconds=float(prediction["latency_seconds"]),
                )
                cache_count += 1
            else:
                request_count += 1
                request_id = f"{args.run_id}_NEW_{request_count:04d}"
                append_jsonl(events, {
                    "state": "claimed", "request_id": request_id,
                    "diagnostic_id": row["diagnostic_id"], "timestamp": utc(),
                })
                result = call_model(model_cfg, prompt, images)
                atomic_text(run_dir / "responses" / f"{request_id}.json", result["raw"])
                if result["transport_unknown"]:
                    atomic_json(terminal_unknown, {
                        "status": "TRANSPORT_UNKNOWN_NO_RESEND",
                        "request_id": request_id,
                        "error": result.get("error"),
                        "completed_total_before_unknown": len(output_rows),
                        "new_requests_before_unknown": request_count - 1,
                    })
                    raise RuntimeError("transport outcome unknown; run stopped without resend")
                if result["http_status"] != 200:
                    atomic_json(terminal_failure, {
                        "status": "KNOWN_HTTP_FAILURE_NO_RETRY",
                        "request_id": request_id,
                        "http_status": result["http_status"],
                        "error": result.get("error"),
                        "completed_total_before_failure": len(output_rows),
                    })
                    raise RuntimeError("known HTTP failure; candidate run stopped without retry")
                attributes, parse_error = parse_outer(result["raw"])
                if attributes is None:
                    atomic_json(terminal_failure, {
                        "status": "STRICT_JSON_FAILURE_NO_RETRY",
                        "request_id": request_id,
                        "parse_error": parse_error,
                        "completed_total_before_failure": len(output_rows),
                    })
                    raise RuntimeError("strict JSON failure; 100 percent gate is unreachable")
                policy = map_attributes(attributes, detector_person_found=person_found)
                record = make_record(
                    row, attributes, policy,
                    person_found=person_found,
                    view_count=len(images),
                    inference_source="NEW_MODEL_REQUEST",
                    request_id=request_id,
                    latency_seconds=result["latency_seconds"],
                )
                append_jsonl(events, {
                    "state": "completed", "request_id": request_id,
                    "diagnostic_id": row["diagnostic_id"], "timestamp": utc(),
                    "http_status": result["http_status"], "strict_json_ok": True,
                })
            output_rows.append(record)
            atomic_json(run_dir / "progress.json", {
                "completed_total": index,
                "total": len(rows),
                "cache_reuse_count": cache_count,
                "new_model_request_count": request_count,
                "current": row["diagnostic_id"],
                "updated_at": utc(),
            })
            print(
                f"[{index}/436] {row['diagnostic_id']} {row['taxonomy']} "
                f"{record['inference_source']} {record['pose']} -> {record['frame_decision']}",
                flush=True,
            )

        if cache_count != plan["prerequisite_diagnostic"]["eligible_cache_rows"]:
            raise RuntimeError(f"expected 110 cache rows, found {cache_count}")
        if request_count != len(rows) - cache_count:
            raise RuntimeError("new request count mismatch")
        fields = list(output_rows[0])
        atomic_csv(run_dir / "predictions.csv", fields, output_rows)
        result_summary = summarize(output_rows, plan, detector_summary, cache_count, request_count)
        result_summary.update({
            "status": "COMPLETE",
            "revision_id": plan["revision_id"],
            "candidate": plan["candidate"],
            "dev_only": True,
            "sequential_dev_optimization": True,
            "independent_validation": False,
            "gt_type": plan["gt_type"],
            "model_prediction_used_as_gt": False,
            "conservative_uncertain_as_error": True,
            "plan_sha256": sha256(PLAN),
            "prompt_sha256": sha256(PROMPT),
            "policy_sha256": sha256(POLICY),
            "crop_manifest_sha256": sha256(CROP_MANIFEST),
            "screen_requests": 0,
            "val_requests": 0,
            "holdout_requests": 0,
            "next_action": (
                "FREEZE_DEV_CANDIDATE_NO_SCREEN_VAL"
                if result_summary["gate_pass"]
                else "STOP_AND_REVIEW_TAXONOMY_ERRORS_NO_PROMPT_CHANGE"
            ),
        })
        atomic_json(run_dir / "summary.json", result_summary)
        atomic_csv(
            run_dir / "false_positives_conservative.csv", fields,
            [row for row in output_rows if row["ground_truth"] == "negative" and row["predicted_label"] != "negative"],
        )
        atomic_csv(
            run_dir / "false_negatives_conservative.csv", fields,
            [row for row in output_rows if row["ground_truth"] == "positive" and row["predicted_label"] != "positive"],
        )
        atomic_csv(
            run_dir / "source_uncertain_rows.csv", fields,
            [row for row in output_rows if row["ground_truth"] == "uncertain"],
        )
        atomic_json(completion, {
            "status": "COMPLETE",
            "completed_at_utc": utc(),
            "summary_sha256": sha256(run_dir / "summary.json"),
            "total_rows": len(output_rows),
            "cache_reuse_count": cache_count,
            "new_model_request_count": request_count,
        })
        print(json.dumps(result_summary, ensure_ascii=False))
        return 0
    finally:
        if active_lock.exists():
            active_lock.unlink()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
