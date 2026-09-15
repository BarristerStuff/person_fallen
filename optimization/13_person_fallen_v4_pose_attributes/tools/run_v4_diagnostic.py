#!/usr/bin/env python3
"""Run the single frozen v4 perception-only 110-row DEV diagnostic."""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from common import ROOT, atomic_csv, atomic_json, atomic_text, load_csv, load_json, sha256

sys.path.insert(0, str(ROOT / "policy"))
from deterministic_policy import LYING_POSES, map_attributes, validate_attributes  # noqa: E402


CONFIG = ROOT / "protocol/v4_diagnostic_config.json"
PROMPT = ROOT / "prompt/V4-A0_pose_attributes_prompt.txt"
CROP_MANIFEST = ROOT / "manifests/v4_crop_manifest.csv"


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
        value = json.loads(response_text)
        return validate_attributes(value), ""
    except Exception as exc:
        return None, f"STRICT_PARSE_FAILURE:{type(exc).__name__}:{exc}"


def call_model(model_cfg: dict, prompt: str, images: list[Path]) -> dict:
    payload = {
        "model": model_cfg["name"], "prompt": prompt,
        "images": [base64.b64encode(path.read_bytes()).decode("ascii") for path in images],
        "stream": model_cfg["stream"], "format": model_cfg["format"],
        "think": model_cfg["think"],
        "options": {
            "temperature": model_cfg["temperature"], "num_ctx": model_cfg["num_ctx"],
            "num_predict": model_cfg["num_predict"],
        },
    }
    started = time.monotonic()
    req = request.Request(
        model_cfg["endpoint"] + "/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with request.urlopen(req, timeout=model_cfg["timeout_seconds"]) as response:
            raw = response.read().decode("utf-8")
            return {"http_status": response.status, "raw": raw,
                    "latency_seconds": time.monotonic() - started, "transport_unknown": False}
    except error.HTTPError as exc:
        return {"http_status": exc.code, "raw": exc.read().decode("utf-8", errors="replace"),
                "latency_seconds": time.monotonic() - started, "transport_unknown": False,
                "error": f"HTTPError:{exc}"}
    except (error.URLError, TimeoutError, OSError) as exc:
        return {"http_status": None, "raw": "", "latency_seconds": time.monotonic() - started,
                "transport_unknown": True, "error": f"{type(exc).__name__}:{exc}"}


def pose_family(attributes: dict | None) -> str:
    if not attributes:
        return "unknown"
    if attributes["pose"] == "floor_sitting":
        return "floor_sitting"
    if attributes["pose"] in LYING_POSES:
        return "lying"
    return "other"


def summarize(rows: list[dict], cfg: dict, detector_summary: dict) -> dict:
    floor = [row for row in rows if row["diagnostic_class"] == "floor_sitting"]
    lying = [row for row in rows if row["diagnostic_class"] == "lying"]
    count_decision = lambda subset, name: sum(row["frame_decision"] == name for row in subset)
    strict = sum(row["strict_json_ok"] for row in rows) / len(rows)
    floor_alarm = count_decision(floor, "ALERT_GROUND_LYING")
    floor_no = count_decision(floor, "NO_ALERT_NORMAL_POSE")
    lying_alarm = count_decision(lying, "ALERT_GROUND_LYING")
    rechecks = count_decision(rows, "RECHECK_VISUAL_UNCERTAIN")
    latencies = [float(row["latency_seconds"]) for row in rows if row["http_status"] == 200]
    metrics = {
        "sample_count": len(rows), "strict_json_success": strict,
        "detector_coverage": detector_summary["person_detection_coverage"],
        "floor_sitting_count": len(floor), "floor_sitting_false_alarm_count": floor_alarm,
        "floor_sitting_false_alarm_rate": floor_alarm / len(floor),
        "floor_sitting_no_alert_count": floor_no,
        "floor_sitting_no_alert_rate": floor_no / len(floor),
        "lying_count": len(lying), "lying_alert_count": lying_alarm,
        "lying_alert_recall": lying_alarm / len(lying),
        "recheck_count": rechecks, "recheck_rate": rechecks / len(rows),
        "pose_family_accuracy": sum(row["predicted_pose_family"] == row["expected_pose_family"] for row in rows) / len(rows),
        "latency_seconds": {
            "mean": statistics.mean(latencies) if latencies else None,
            "p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
        "decision_distribution": dict(Counter(row["frame_decision"] for row in rows)),
        "pose_distribution": dict(Counter(row["pose"] for row in rows)),
    }
    gate_cfg = cfg["gate"]
    checks = {
        "strict_json": strict >= gate_cfg["strict_json_success_min"],
        "detector_coverage": metrics["detector_coverage"] >= gate_cfg["detector_coverage_min"],
        "floor_sitting_false_alarm": metrics["floor_sitting_false_alarm_rate"] <= gate_cfg["floor_sitting_false_alarm_rate_max"],
        "floor_sitting_no_alert": metrics["floor_sitting_no_alert_rate"] >= gate_cfg["floor_sitting_no_alert_rate_min"],
        "lying_alert_recall": metrics["lying_alert_recall"] >= gate_cfg["lying_alert_recall_min"],
        "recheck_rate": metrics["recheck_rate"] <= gate_cfg["recheck_rate_max"],
    }
    return {"metrics": metrics, "gate_checks": checks, "gate_pass": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="dev_V4-A0-FULL-CROP-110")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    cfg = load_json(CONFIG)
    model_cfg = cfg["model"]
    rows = load_csv(CROP_MANIFEST)
    if len(rows) != 110 or any(row["v3_split"] != "V3_DEV" or row["source_split"] == "HOLDOUT" for row in rows):
        raise RuntimeError("crop manifest scope failure")
    detector_summary = load_json(ROOT / "detector/detector_summary.json")
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
        "config_sha256": sha256(CONFIG), "prompt_sha256": sha256(PROMPT),
        "crop_manifest_sha256": sha256(CROP_MANIFEST), "input_count": len(rows),
        "screen_rows_read": 0, "val_rows_read": 0, "holdout_rows_read": 0,
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
    try:
        for index, row in enumerate(rows, 1):
            full = Path(row["full_view_path"])
            crop = Path(row["crop_view_path"])
            if sha256(full) != row["full_view_sha256"] or sha256(crop) != row["crop_view_sha256"]:
                raise RuntimeError(f"prepared view SHA mismatch: {row['diagnostic_id']}")
            person_found = row["person_detected"] == "true"
            images = [full, crop] if person_found else [full]
            request_id = f"{args.run_id}_{index:04d}"
            append_jsonl(events, {"state": "claimed", "request_id": request_id,
                                  "diagnostic_id": row["diagnostic_id"], "timestamp": utc()})
            result = call_model(model_cfg, prompt, images)
            atomic_text(run_dir / "responses" / f"{request_id}.json", result["raw"])
            if result["transport_unknown"]:
                atomic_json(run_dir / "TERMINAL_TRANSPORT_UNKNOWN.json", {
                    "status": "TRANSPORT_UNKNOWN_NO_RESEND", "request_id": request_id,
                    "error": result.get("error"), "completed_before_unknown": len(output_rows),
                })
                raise RuntimeError("transport outcome unknown; run stopped without resend")
            if result["http_status"] != 200:
                atomic_json(terminal_failure, {
                    "status": "KNOWN_HTTP_FAILURE_NO_RETRY", "request_id": request_id,
                    "http_status": result["http_status"], "error": result.get("error"),
                    "completed_before_failure": len(output_rows),
                })
                raise RuntimeError("known HTTP failure; candidate run stopped without retry")
            attributes, parse_error = parse_outer(result["raw"])
            if attributes is None:
                atomic_json(terminal_failure, {
                    "status": "STRICT_JSON_FAILURE_NO_RETRY", "request_id": request_id,
                    "parse_error": parse_error, "completed_before_failure": len(output_rows),
                })
                raise RuntimeError("strict JSON failure; 100 percent gate is unreachable")
            policy = map_attributes(attributes, detector_person_found=person_found)
            record = {
                "diagnostic_id": row["diagnostic_id"], "item_id": row["item_id"],
                "taxonomy": row["taxonomy"], "diagnostic_class": row["diagnostic_class"],
                "expected_pose_family": row["expected_pose_family"],
                "person_detected": person_found, "view_count": len(images),
                "http_status": result["http_status"], "latency_seconds": result["latency_seconds"],
                "strict_json_ok": attributes is not None, "parse_error": parse_error,
                "person_visible": "" if attributes is None else attributes["person_visible"],
                "pose": "" if attributes is None else attributes["pose"],
                "torso_orientation": "" if attributes is None else attributes["torso_orientation"],
                "torso_ground_contact": "" if attributes is None else attributes["torso_ground_contact"],
                "head_shoulders_above_hips": "" if attributes is None else attributes["head_shoulders_above_hips"],
                "support_surface": "" if attributes is None else attributes["support_surface"],
                "explicit_work_evidence": "" if attributes is None else attributes["explicit_work_evidence"],
                "visual_quality": "" if attributes is None else attributes["visual_quality"],
                "evidence": "" if attributes is None else attributes["evidence"],
                "predicted_pose_family": pose_family(attributes),
                **policy,
            }
            output_rows.append(record)
            append_jsonl(events, {"state": "completed", "request_id": request_id,
                                  "diagnostic_id": row["diagnostic_id"], "timestamp": utc(),
                                  "http_status": result["http_status"], "strict_json_ok": attributes is not None})
            atomic_json(run_dir / "progress.json", {"completed": index, "total": len(rows),
                                                     "current": row["diagnostic_id"], "updated_at": utc()})
            print(f"[{index}/110] {row['diagnostic_id']} {record['pose']} -> {record['frame_decision']}", flush=True)
        fields = list(output_rows[0])
        atomic_csv(run_dir / "predictions.csv", fields, output_rows)
        summary = summarize(output_rows, cfg, detector_summary)
        summary.update({
            "status": "COMPLETE", "revision_id": cfg["revision_id"],
            "candidate": cfg["candidate"], "diagnostic_only": True,
            "gt_type": cfg["gt_type"], "model_prediction_used_as_gt": False,
            "config_sha256": sha256(CONFIG), "prompt_sha256": sha256(PROMPT),
            "crop_manifest_sha256": sha256(CROP_MANIFEST),
            "screen_requests": 0, "val_requests": 0, "holdout_requests": 0,
            "next_action": "BUILD_FULL_DEV_MANIFEST_ONLY" if summary["gate_pass"] else "STOP_4B_V4_A0_AND_DIAGNOSE",
        })
        atomic_json(run_dir / "summary.json", summary)
        atomic_csv(run_dir / "floor_sitting_errors.csv", fields,
                   [row for row in output_rows if row["diagnostic_class"] == "floor_sitting" and row["frame_decision"] != "NO_ALERT_NORMAL_POSE"])
        atomic_csv(run_dir / "lying_errors.csv", fields,
                   [row for row in output_rows if row["diagnostic_class"] == "lying" and row["frame_decision"] != "ALERT_GROUND_LYING"])
        atomic_json(completion, {"status": "COMPLETE", "completed_at_utc": utc(),
                                 "summary_sha256": sha256(run_dir / "summary.json"),
                                 "request_count": len(output_rows)})
        print(json.dumps(summary, ensure_ascii=False))
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
