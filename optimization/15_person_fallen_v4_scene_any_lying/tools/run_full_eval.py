#!/usr/bin/env python3
"""Run the frozen V4 operational candidate on one legal SCREEN or VAL split."""

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

from common import atomic_csv, atomic_json, atomic_text, load_csv, load_json, sha256
ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "policy"))
from deterministic_policy import map_attributes, validate_attributes  # noqa: E402


PLAN = ROOT / "protocol/final_operational_plan.json"
FREEZE = ROOT / "freeze/CANDIDATE_FREEZE.json"
PROMPT = ROOT / "prompt/V4_scene_any_lying_prompt.txt"
POLICY = ROOT / "policy/deterministic_policy.py"
TEMPORAL_POLICY = ROOT / "policy/temporal_recheck.py"
MANIFESTS = {"dev": ROOT / "manifests/dev_operational_crop.csv", "screen": ROOT / "manifests/targeted_regression_crop.csv", "val": ROOT / "manifests/val_operational_crop.csv"}
DETECTOR_SUMMARIES = {}
ATTRIBUTE_KEYS = [
    "person_visible", "pose", "torso_orientation", "torso_ground_contact",
    "head_shoulders_above_hips", "support_surface", "explicit_work_evidence",
    "visual_quality", "evidence",
]


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
        response = outer.get("response")
        if not isinstance(response, str):
            return None, "MISSING_RESPONSE_STRING"
        return validate_attributes(json.loads(response)), ""
    except Exception as exc:
        return None, f"STRICT_PARSE_FAILURE:{type(exc).__name__}:{exc}"


def call_model(model_cfg: dict, prompt: str, images: list[Path]) -> dict:
    payload = {
        "model": model_cfg["name"], "prompt": prompt,
        "images": [base64.b64encode(path.read_bytes()).decode("ascii") for path in images],
        "stream": model_cfg["stream"], "format": model_cfg["format"], "think": model_cfg["think"],
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
            return {"http_status": response.status, "raw": response.read().decode("utf-8"),
                    "latency_seconds": time.monotonic() - started, "transport_unknown": False}
    except error.HTTPError as exc:
        return {"http_status": exc.code, "raw": exc.read().decode("utf-8", errors="replace"),
                "latency_seconds": time.monotonic() - started, "transport_unknown": False,
                "error": f"HTTPError:{exc}"}
    except (error.URLError, TimeoutError, OSError) as exc:
        return {"http_status": None, "raw": "", "latency_seconds": time.monotonic() - started,
                "transport_unknown": True, "error": f"{type(exc).__name__}:{exc}"}


def verify_binding(plan: dict, phase: str) -> None:
    checks=[(ROOT/plan["definition"]["path"],plan["definition"]["sha256"]),(ROOT/plan["prompt"]["path"],plan["prompt"]["sha256"]),(ROOT/plan["policy"]["path"],plan["policy"]["sha256"])]
    for path,expected in checks:
        if expected and sha256(path)!=expected: raise RuntimeError(f"binding SHA mismatch: {path}")
    if plan["model"]["name"]!="qwen3.5:4b" or plan["model"]["endpoint"]!="http://192.168.20.62:11434": raise RuntimeError("model endpoint/name binding mismatch")
    if phase=="val":
        screen_dir=ROOT/"eval/runs/screen_REV15"
        if not (screen_dir/"summary.json").is_file() or not (screen_dir/"COMPLETION_LOCK.json").is_file(): raise RuntimeError("VAL requires completed targeted regression")
        if load_json(screen_dir/"summary.json").get("gate_pass") is not True: raise RuntimeError("targeted regression gate failed; VAL forbidden")

def metrics(rows: list[dict], detector_summary: dict, phase: str, plan: dict) -> dict:
    ground = [row for row in rows if row["operational_class"] == "ground_lying"]
    negatives = [row for row in rows if row["operational_class"] == "normal_negative"]
    floor = [row for row in negatives if row["taxonomy"] == "floor_sitting"]
    alerts = lambda subset: sum(row["frame_decision"] == "ALERT_GROUND_LYING" for row in subset)
    rechecks = lambda subset: sum(row["frame_decision"] == "RECHECK_VISUAL_UNCERTAIN" for row in subset)
    ground_alert = alerts(ground)
    ground_recheck = rechecks(ground)
    neg_alert = alerts(negatives)
    floor_alert = alerts(floor)
    strict = sum(row["strict_json_ok"] for row in rows) / len(rows)
    latencies = [float(row["latency_seconds"]) for row in rows if row["http_status"] == 200]
    result = {
        "phase": phase, "sample_count": len(rows), "ground_lying_count": len(ground),
        "ground_lying_alert": ground_alert, "ground_lying_recheck": ground_recheck,
        "ground_lying_no_alert": len(ground) - ground_alert - ground_recheck,
        "ground_lying_alert_recall": ground_alert / len(ground) if ground else None,
        "ground_lying_alert_recheck_coverage": (ground_alert + ground_recheck) / len(ground) if ground else None,
        "floor_sitting_count": len(floor), "floor_sitting_alert": floor_alert,
        "floor_sitting_alert_fpr": floor_alert / len(floor) if floor else None,
        "determinate_negative_count": len(negatives), "determinate_negative_alert": neg_alert,
        "determinate_negative_alert_fpr": neg_alert / len(negatives) if negatives else None,
        "recheck_count": rechecks(rows), "recheck_rate": rechecks(rows) / len(rows),
        "attention_count": sum(row["frame_decision"] == "ATTENTION_NEAR_GROUND" for row in rows),
        "strict_json_success": strict,
        "detector_coverage": detector_summary["person_detection_coverage"],
        "decision_distribution": dict(Counter(row["frame_decision"] for row in rows)),
        "taxonomy": {},
        "latency_seconds": {"mean": statistics.mean(latencies) if latencies else None,
                             "p50": percentile(latencies, .5), "p95": percentile(latencies, .95),
                             "max": max(latencies) if latencies else None},
    }
    for taxonomy in sorted({row["taxonomy"] for row in rows}):
        subset = [row for row in rows if row["taxonomy"] == taxonomy]
        result["taxonomy"][taxonomy] = {"count": len(subset), "decisions": dict(Counter(row["frame_decision"] for row in subset))}
    gate = plan["operational_gate"]
    gate_checks = {
        "ground_lying_alert_recall": result["ground_lying_alert_recall"] is not None and result["ground_lying_alert_recall"] >= gate["ground_lying_alert_recall_min"],
        "ground_lying_alert_recheck_coverage": result["ground_lying_alert_recheck_coverage"] == gate["ground_lying_alert_recheck_coverage_required"],
        "floor_sitting_alert_fpr": result["floor_sitting_alert_fpr"] is None or result["floor_sitting_alert_fpr"] <= gate["floor_sitting_alert_fpr_max"],
        "determinate_negative_alert_fpr": result["determinate_negative_alert_fpr"] is not None and result["determinate_negative_alert_fpr"] <= gate["determinate_negative_alert_fpr_max"],
        "strict_json_success": result["strict_json_success"] >= gate["strict_json_success_min"],
    }
    result["floor_sitting_gate_status"] = "NOT_APPLICABLE" if not floor else ("PASS" if gate_checks["floor_sitting_alert_fpr"] else "FAIL")
    return {"metrics": result, "gate_checks": gate_checks, "gate_pass": all(gate_checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["dev", "screen", "val"])
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    plan = load_json(PLAN)
    verify_binding(plan, args.phase)
    crop_manifest = MANIFESTS[args.phase]
    rows = load_csv(crop_manifest)
    expected_split = {"dev":"V3_DEV","screen":"V3_SCREEN","val":"V3_VAL"}[args.phase]
    if not rows or any(row["v3_split"] != expected_split for row in rows):
        raise RuntimeError("operational crop manifest split mismatch")
    if any(row["source_split"] == "HOLDOUT" or row["v3_split"] == "HOLDOUT" for row in rows):
        raise RuntimeError("Holdout row in operational crop manifest")
    detector_summary = {"person_detection_coverage": sum(r["person_detected"]=="true" for r in rows)/len(rows)}
    run_dir = ROOT / "eval/runs" / f"{args.phase}_full_REV15"
    completion = run_dir / "COMPLETION_LOCK.json"
    terminal_unknown = run_dir / "TERMINAL_TRANSPORT_UNKNOWN.json"
    terminal_failure = run_dir / "TERMINAL_KNOWN_FAILURE.json"
    active = run_dir / "ACTIVE.lock"
    events = run_dir / "request_events.jsonl"
    if completion.exists():
        raise RuntimeError("run already complete and immutable")
    if terminal_unknown.exists() or terminal_failure.exists() or active.exists():
        raise RuntimeError("run has terminal/active state; automatic resume is forbidden")
    if events.exists() and events.stat().st_size:
        raise RuntimeError("partial request ledger exists; resend is forbidden")
    run_dir.mkdir(parents=True, exist_ok=True)
    preflight = runtime_preflight(plan["model"])
    preflight.update({
        "revision_id": plan["revision_id"], "candidate": plan["candidate"], "phase": args.phase,
        "plan_sha256": sha256(PLAN), "freeze_sha256": sha256(FREEZE) if FREEZE.exists() else None,
        "definition_sha256": sha256(ROOT / plan["definition"]["path"]),
        "prompt_sha256": sha256(PROMPT), "policy_sha256": sha256(POLICY),
        "crop_manifest_sha256": sha256(crop_manifest), "input_count": len(rows),
        "screen_rows_read": 0, "val_rows_read": 0, "holdout_rows_read": 0,
    })
    atomic_json(run_dir / "runtime_preflight.json", preflight)
    if args.preflight_only:
        print(json.dumps(preflight, ensure_ascii=False))
        return 0

    fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.write(fd, f"pid={os.getpid()} started={utc()}\n".encode())
    os.close(fd)
    prompt = PROMPT.read_text(encoding="utf-8")
    output_rows: list[dict] = []
    try:
        for index, row in enumerate(rows, 1):
            full = Path(row["full_view_path"])
            crop = Path(row["crop_view_path"])
            if sha256(full) != row["full_view_sha256"] or sha256(crop) != row["crop_view_sha256"]:
                raise RuntimeError(f"view SHA mismatch: {row['operational_id']}")
            person_found = row["person_detected"] == "true"
            images = [full, crop] if person_found else [full]
            request_id = f"{args.phase.upper()}_REV15_{index:04d}"
            append_jsonl(events, {"state": "claimed", "request_id": request_id, "operational_id": row["operational_id"], "timestamp": utc()})
            result = call_model(plan["model"], prompt, images)
            atomic_text(run_dir / "responses" / f"{request_id}.json", result["raw"])
            if result["transport_unknown"]:
                atomic_json(terminal_unknown, {"status": "TRANSPORT_UNKNOWN_NO_RESEND", "request_id": request_id, "error": result.get("error"), "completed_before_unknown": len(output_rows)})
                raise RuntimeError("transport unknown; stopped without resend")
            if result["http_status"] != 200:
                atomic_json(terminal_failure, {"status": "KNOWN_HTTP_FAILURE_NO_RETRY", "request_id": request_id, "http_status": result["http_status"], "error": result.get("error")})
                raise RuntimeError("known HTTP failure; stopped without retry")
            attributes, parse_error = parse_outer(result["raw"])
            if attributes is None:
                atomic_json(terminal_failure, {"status": "STRICT_JSON_FAILURE_NO_RETRY", "request_id": request_id, "parse_error": parse_error})
                raise RuntimeError("strict JSON failure; stopped without retry")
            policy = map_attributes(attributes, detector_person_found=person_found)
            frame = policy["frame_decision"]
            output_rows.append({
                "operational_id": row["operational_id"], "item_id": row["item_id"],
                "taxonomy": row["taxonomy"], "operational_class": row["operational_class"],
                "ground_truth": row["ground_truth"], "metric_stratum": row["metric_stratum"],
                "person_detected": person_found, "view_count": len(images),
                "request_id": request_id, "http_status": result["http_status"],
                "latency_seconds": result["latency_seconds"], "strict_json_ok": True,
                "parse_error": "", **attributes, **policy,
                "high_priority_alert": frame == "ALERT_GROUND_LYING",
                "recheck": frame == "RECHECK_VISUAL_UNCERTAIN",
                "near_ground_attention": frame == "ATTENTION_NEAR_GROUND",
            })
            append_jsonl(events, {"state": "completed", "request_id": request_id, "operational_id": row["operational_id"], "timestamp": utc(), "http_status": result["http_status"], "strict_json_ok": True})
            atomic_json(run_dir / "progress.json", {"completed": index, "total": len(rows), "current": row["operational_id"], "updated_at": utc()})
            print(f"[{index}/{len(rows)}] {row['operational_id']} {attributes['pose']} -> {frame}", flush=True)
        fields = list(output_rows[0])
        atomic_csv(run_dir / "predictions.csv", fields, output_rows)
        evaluated = metrics(output_rows, detector_summary, args.phase, plan)
        summary = {"status": "COMPLETE", "revision_id": plan["revision_id"], "candidate": plan["candidate"], "phase": args.phase, "operational_definition_frozen": True, "gt_type": "PROMPT_DERIVED_SYNTHETIC_GT", "model_prediction_used_as_gt": False, "screen_rows_read": len(rows) if args.phase == "screen" else 0, "val_rows_read": len(rows) if args.phase == "val" else 0, "holdout_rows_read": 0, "plan_sha256": sha256(PLAN), "freeze_sha256": sha256(FREEZE) if FREEZE.exists() else None, "definition_sha256": sha256(ROOT / plan["definition"]["path"]), "prompt_sha256": sha256(PROMPT), "policy_sha256": sha256(POLICY), "crop_manifest_sha256": sha256(crop_manifest), **evaluated}
        atomic_json(run_dir / "summary.json", summary)
        atomic_csv(run_dir / "high_priority_alert_false_positives.csv", fields, [row for row in output_rows if row["operational_class"] == "normal_negative" and row["high_priority_alert"]])
        atomic_csv(run_dir / "ground_lying_misses.csv", fields, [row for row in output_rows if row["operational_class"] == "ground_lying" and not row["high_priority_alert"]])
        atomic_csv(run_dir / "rechecks.csv", fields, [row for row in output_rows if row["recheck"]])
        atomic_json(completion, {"status": "COMPLETE", "completed_at_utc": utc(), "summary_sha256": sha256(run_dir / "summary.json"), "request_count": len(output_rows)})
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        if active.exists():
            active.unlink()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
