#!/usr/bin/env python3
"""Run the bounded v3 floor-pose cascade without mutating v3 history."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import os
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "11_person_fallen_v3_revision"
CONFIG_PATH = ROOT / "protocol/cascade_config.json"
STAGE2_PROMPT = ROOT / "prompt/V3-CASCADE-S2-C0_prompt.txt"
STAGE1_PROMPT = SOURCE / "prompt/V3-C0_prompt.txt"
MANIFESTS = ROOT / "manifests"
AUDIT_PATH = ROOT / "audit/stage1_dev_reuse_audit.json"
RUNS = ROOT / "eval/runs"
FREEZE = ROOT / "freeze/person_fallen_v3_cascade_dev_winner.json"
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else ["item_id"]
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


def append_event(handle, value: object) -> None:
    handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def preprocess(source: Path, destination: Path, width: int, height: int, runtime: dict) -> None:
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((width, height), RESAMPLE)
        canvas = Image.new("RGB", (width, height), tuple(runtime["letterbox_rgb"]))
        canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        canvas.save(temporary, "JPEG", quality=runtime["jpeg_quality"], optimize=runtime["jpeg_optimize"])
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    with Image.open(destination) as image:
        if image.size != (width, height) or image.format != "JPEG":
            raise RuntimeError("CASCADE_PREPROCESS_OUTPUT_INVALID")


def parse_stage1(raw: str) -> dict[str, object]:
    output: dict[str, object] = {"outer_json_ok": False, "response_json_ok": False, "schema_ok": False, "strict_json_ok": False, "prediction": "protocol_failure", "pose": "", "evidence": "", "error_type": ""}
    try:
        outer = json.loads(raw)
        output["outer_json_ok"] = True
        value = json.loads(outer["response"])
        output["response_json_ok"] = True
    except Exception as exc:
        output["error_type"] = f"stage1_json_parse:{type(exc).__name__}:{exc}"
        return output
    if not isinstance(value, dict) or set(value) != {"person_fallen", "evidence"}:
        output["error_type"] = "stage1_schema_keys"
        return output
    status, evidence = value.get("person_fallen"), value.get("evidence")
    if status not in {"positive", "negative", "uncertain"} or not isinstance(evidence, str) or not evidence.strip():
        output["error_type"] = "stage1_schema_values"
        return output
    output.update({"schema_ok": True, "strict_json_ok": True, "prediction": status, "evidence": evidence.strip()})
    return output


def parse_stage2(raw: str) -> dict[str, object]:
    output: dict[str, object] = {"outer_json_ok": False, "response_json_ok": False, "schema_ok": False, "strict_json_ok": False, "prediction": "protocol_failure", "pose": "", "evidence": "", "error_type": ""}
    try:
        outer = json.loads(raw)
        output["outer_json_ok"] = True
        value = json.loads(outer["response"])
        output["response_json_ok"] = True
    except Exception as exc:
        output["error_type"] = f"stage2_json_parse:{type(exc).__name__}:{exc}"
        return output
    if not isinstance(value, dict) or set(value) != {"decision", "pose", "evidence"}:
        output["error_type"] = "stage2_schema_keys"
        return output
    decision, pose, evidence = value.get("decision"), value.get("pose"), value.get("evidence")
    valid = {"KEEP_ALERT": "alert_posture", "UNCERTAIN": "unknown"}
    if decision == "SUPPRESS_NORMAL_POSE":
        semantic_ok = pose in {"floor_sitting", "kneeling", "maintenance"}
    else:
        semantic_ok = valid.get(decision) == pose
    if decision not in {"KEEP_ALERT", "SUPPRESS_NORMAL_POSE", "UNCERTAIN"} or pose not in {"floor_sitting", "kneeling", "maintenance", "alert_posture", "unknown"} or not isinstance(evidence, str) or not evidence.strip() or not semantic_ok:
        output["error_type"] = "stage2_schema_or_decision_pose_contract"
        return output
    output.update({"schema_ok": True, "strict_json_ok": True, "prediction": decision, "pose": pose, "evidence": evidence.strip()})
    return output


def call_endpoint(runtime: dict, processed: Path, prompt: str) -> dict[str, object]:
    payload = {"model": runtime["model"], "prompt": prompt, "images": [base64.b64encode(processed.read_bytes()).decode("ascii")], "stream": runtime["stream"], "format": runtime["format"], "think": runtime["think"], "options": runtime["options"]}
    started = time.monotonic()
    try:
        req = request.Request(runtime["endpoint"] + "/api/generate", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=runtime["timeout_seconds"]) as response:
            raw, status = response.read().decode("utf-8"), response.status
        return {"http_ok": status == 200, "http_status": status, "raw": raw, "latency_seconds": time.monotonic() - started, "error_type": "" if status == 200 else f"HTTP_STATUS_{status}", "payload_without_image": {key: value for key, value in payload.items() if key != "images"}}
    except error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        return {"http_ok": False, "http_status": exc.code, "raw": raw, "latency_seconds": time.monotonic() - started, "error_type": f"HTTPError:{exc}", "confirmed_failure": True, "payload_without_image": {key: value for key, value in payload.items() if key != "images"}}
    except (error.URLError, TimeoutError, OSError) as exc:
        return {"http_ok": False, "http_status": None, "raw": "", "latency_seconds": time.monotonic() - started, "error_type": f"TRANSPORT_UNKNOWN:{type(exc).__name__}:{exc}", "transport_unknown": True, "payload_without_image": {key: value for key, value in payload.items() if key != "images"}}


def preflight_runtime(runtime: dict) -> dict[str, object]:
    def get_json(path: str) -> dict:
        req = request.Request(runtime["endpoint"] + path, method="GET")
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    tags, version = get_json("/api/tags"), get_json("/api/version")
    models = {item.get("name"): item for item in tags.get("models", []) if isinstance(item, dict)}
    if runtime["model"] not in models or models[runtime["model"]].get("digest") != runtime["model_digest"]:
        raise SystemExit("CASCADE_RUNTIME_MODEL_DIGEST_MISMATCH")
    if version.get("version") != runtime["ollama_version"]:
        raise SystemExit("CASCADE_RUNTIME_OLLAMA_VERSION_MISMATCH")
    return {"status": "PASS", "captured_at_utc": utc(), "endpoint": runtime["endpoint"], "selected_model": models[runtime["model"]], "api_version": version}


def validate_manifest(rows: list[dict[str, str]], phase: str) -> None:
    expected = {"dev": "V3_DEV", "screen": "V3_SCREEN", "val": "V3_VAL"}[phase]
    if not rows or len({row["item_id"] for row in rows}) != len(rows):
        raise SystemExit("CASCADE_MANIFEST_SHAPE_INVALID")
    if any(row["v3_split"] != expected or row["formal_v3_evaluation"] != "true" for row in rows):
        raise SystemExit("CASCADE_MANIFEST_SCOPE_INVALID")
    if any(row["source_split"] == "HOLDOUT" or row["v3_split"] == "HOLDOUT" for row in rows):
        raise SystemExit("CASCADE_HOLDOUT_CONTAMINATION")
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        groups[row["group_id"]].add(row["v3_split"])
        image, source_prompt = Path(row["image_path"]), Path(row["prompt_path"])
        if not image.is_file() or sha256(image) != row["image_sha256"]:
            raise SystemExit(f"CASCADE_IMAGE_HASH_MISMATCH={row['item_id']}")
        if not source_prompt.is_file() or sha256(source_prompt) != row["prompt_sha256"]:
            raise SystemExit(f"CASCADE_SOURCE_PROMPT_HASH_MISMATCH={row['item_id']}")
    if any(len(values) != 1 for values in groups.values()):
        raise SystemExit("CASCADE_GROUP_SPLIT_LEAKAGE")


def init_ledger(stage_dir: Path, stage: str, rows: list[dict[str, str]], phase: str, candidate: str, prompt: Path, resolution: tuple[int, int], cfg: dict) -> sqlite3.Connection:
    path = stage_dir / "request_ledger.sqlite3"
    new = not path.exists()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY,ordinal INTEGER NOT NULL,item_id TEXT UNIQUE NOT NULL,state TEXT NOT NULL,started_at TEXT,completed_at TEXT,image_sha256 TEXT NOT NULL,processed_image_sha256 TEXT,prompt_sha256 TEXT NOT NULL,config_sha256 TEXT NOT NULL,http_status INTEGER,latency_seconds REAL,response_sha256 TEXT,error_type TEXT)")
    item_order_sha = hashlib.sha256("\n".join(row["item_id"] for row in rows).encode("utf-8")).hexdigest()
    binding = {"stage": stage, "phase": phase, "candidate": candidate, "resolution": json.dumps(resolution), "manifest_sha256": sha256(MANIFESTS / f"{phase}_full_manifest.csv"), "input_item_order_sha256": item_order_sha, "prompt_sha256": sha256(prompt), "config_sha256": sha256(CONFIG_PATH), "runner_sha256": sha256(Path(__file__)), "automatic_retry": "false", "resend_completion_unknown": "false", "holdout_requests": "0"}
    if new:
        run_id = f"CASCADE_{phase.upper()}_{candidate}_{stage.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", {"run_id": run_id, **binding, "planned_requests": str(len(rows))}.items())
        for ordinal, row in enumerate(rows, 1):
            connection.execute("INSERT INTO requests(request_id,ordinal,item_id,state,image_sha256,prompt_sha256,config_sha256) VALUES (?,?,?,?,?,?,?)", (f"{run_id}_{ordinal:04d}", ordinal, row["item_id"], "NOT_STARTED", row["image_sha256"], sha256(prompt), sha256(CONFIG_PATH)))
        connection.commit()
    else:
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        if any(metadata.get(key) != value for key, value in binding.items()):
            raise SystemExit("CASCADE_EXISTING_LEDGER_BINDING_MISMATCH")
    if connection.execute("SELECT count(*) FROM requests WHERE state IN ('STARTED','UNKNOWN')").fetchone()[0]:
        raise SystemExit("CASCADE_INDETERMINATE_REQUEST_NEVER_RESENT")
    return connection


def execute_stage(run_dir: Path, stage: str, rows: list[dict[str, str]], phase: str, candidate: str, prompt: Path, resolution: tuple[int, int], cfg: dict) -> list[dict[str, object]]:
    stage_dir = run_dir / stage
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "responses").mkdir(exist_ok=True)
    (stage_dir / f"processed_{resolution[0]}x{resolution[1]}").mkdir(exist_ok=True)
    parser = parse_stage1 if stage == "stage1" else parse_stage2
    connection = init_ledger(stage_dir, stage, rows, phase, candidate, prompt, resolution, cfg)
    pending = connection.execute("SELECT request_id,ordinal,item_id FROM requests WHERE state='NOT_STARTED' ORDER BY ordinal").fetchall()
    source_by_id = {row["item_id"]: row for row in rows}
    prompt_text = prompt.read_text(encoding="utf-8")
    with (stage_dir / "request_events.jsonl").open("a", encoding="utf-8") as events:
        for index, (request_id, ordinal, item_id) in enumerate(pending, 1):
            source, started = source_by_id[item_id], utc()
            connection.execute("UPDATE requests SET state='STARTED',started_at=? WHERE request_id=? AND state='NOT_STARTED'", (started, request_id)); connection.commit()
            append_event(events, {"event": "REQUEST_STARTED", "stage": stage, "request_id": request_id, "ordinal": ordinal, "item_id": item_id, "timestamp_utc": started, "attempt": 1, "image_sha256": source["image_sha256"], "prompt_sha256": sha256(prompt), "config_sha256": sha256(CONFIG_PATH)})
            processed = stage_dir / f"processed_{resolution[0]}x{resolution[1]}" / f"{ordinal:04d}_{source['prompt_id']}.jpg"
            try:
                preprocess(Path(source["image_path"]), processed, resolution[0], resolution[1], cfg["runtime"])
                processed_sha = sha256(processed)
                connection.execute("UPDATE requests SET processed_image_sha256=? WHERE request_id=?", (processed_sha, request_id)); connection.commit()
            except Exception as exc:
                error_text = f"PREPROCESS_FAILED:{type(exc).__name__}:{exc}"
                connection.execute("UPDATE requests SET state='FAILED_CONFIRMED',completed_at=?,error_type=? WHERE request_id=?", (utc(), error_text, request_id)); connection.commit()
                append_event(events, {"event": "REQUEST_FAILED_CONFIRMED", "stage": stage, "request_id": request_id, "item_id": item_id, "timestamp_utc": utc(), "error_type": error_text})
                continue
            result, completed = call_endpoint(cfg["runtime"], processed, prompt_text), utc()
            if result.get("transport_unknown"):
                connection.execute("UPDATE requests SET state='UNKNOWN',completed_at=?,latency_seconds=?,error_type=? WHERE request_id=?", (completed, result["latency_seconds"], result["error_type"], request_id)); connection.commit(); connection.close()
                append_event(events, {"event": "REQUEST_UNKNOWN_STOP", "stage": stage, "request_id": request_id, "item_id": item_id, "timestamp_utc": completed, "error_type": result["error_type"]})
                raise SystemExit("CASCADE_STOPPED_TRANSPORT_UNKNOWN_NO_RESEND")
            wrapper = {"request_id": request_id, "ordinal": ordinal, "item_id": item_id, "stage": stage, "phase": phase, "candidate": candidate, "request_payload_without_image": result["payload_without_image"], "source_image_path": source["image_path"], "source_image_sha256": source["image_sha256"], "processed_image_path": str(processed), "processed_image_sha256": processed_sha, "prompt_sha256": sha256(prompt), "config_sha256": sha256(CONFIG_PATH), "timestamp_start_utc": started, "timestamp_end_utc": completed, "http_status": result["http_status"], "latency_seconds": result["latency_seconds"], "outer_raw": result["raw"], "transport_error": result.get("error_type", "")}
            response_path = stage_dir / "responses" / f"{request_id}.json"
            write_json(response_path, wrapper)
            state = "COMPLETED" if result.get("http_ok") else "FAILED_CONFIRMED"
            connection.execute("UPDATE requests SET state=?,completed_at=?,http_status=?,latency_seconds=?,response_sha256=?,error_type=? WHERE request_id=?", (state, completed, result["http_status"], result["latency_seconds"], sha256(response_path), result.get("error_type", ""), request_id)); connection.commit()
            append_event(events, {"event": "REQUEST_COMPLETED" if state == "COMPLETED" else "REQUEST_FAILED_CONFIRMED", "stage": stage, "request_id": request_id, "item_id": item_id, "timestamp_utc": completed, "http_status": result["http_status"], "latency_seconds": result["latency_seconds"], "response_sha256": sha256(response_path), "error_type": result.get("error_type", "")})
            if index % 10 == 0 or index == len(pending):
                print(f"CASCADE_{phase.upper()}_{candidate}_{stage.upper()}_PROGRESS={index}/{len(pending)}", flush=True)
    request_rows = connection.execute("SELECT request_id,ordinal,item_id,state,http_status,latency_seconds,response_sha256,error_type FROM requests ORDER BY ordinal").fetchall(); connection.close()
    output: list[dict[str, object]] = []
    for request_id, ordinal, item_id, state, http, latency, response_sha, ledger_error in request_rows:
        parsed = {"outer_json_ok": False, "response_json_ok": False, "schema_ok": False, "strict_json_ok": False, "prediction": "protocol_failure", "pose": "", "evidence": "", "error_type": ledger_error or ""}
        response_path = stage_dir / "responses" / f"{request_id}.json"
        if state == "COMPLETED" and response_path.is_file():
            parsed = parser(json.loads(response_path.read_text(encoding="utf-8")).get("outer_raw", ""))
        output.append({"request_id": request_id, "ordinal": ordinal, "item_id": item_id, "state": state, "http_status": "" if http is None else http, "latency_seconds": float(latency or 0), "response_path": str(response_path) if response_path.is_file() else "", "response_sha256": response_sha or "", "outer_json_ok": str(parsed["outer_json_ok"]).lower(), "response_json_ok": str(parsed["response_json_ok"]).lower(), "schema_ok": str(parsed["schema_ok"]).lower(), "strict_json_ok": str(parsed["strict_json_ok"]).lower(), "prediction": parsed["prediction"], "pose": parsed["pose"], "evidence": parsed["evidence"], "error_type": parsed["error_type"]})
    write_csv(stage_dir / "predictions.csv", output)
    return output


def frozen_dev_stage1(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    source_path = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/eval/runs/dev_V3-C0-448/predictions.csv")
    if sha256(source_path) != audit["source_hashes"]["stage1_dev_predictions"]:
        raise SystemExit("CASCADE_FROZEN_STAGE1_DEV_PREDICTIONS_HASH_MISMATCH")
    source = load_csv(source_path)
    expected = {row["item_id"]: row for row in rows}
    if len(source) != len(rows) or len({row["item_id"] for row in source}) != len(rows):
        raise SystemExit("CASCADE_FROZEN_STAGE1_DEV_SHAPE_INVALID")
    output = []
    for ordinal, row in enumerate(source, 1):
        item = expected.get(row["item_id"])
        if not item or any(row[key] != item[key] for key in ("image_sha256", "prompt_sha256", "ground_truth", "metric_stratum", "taxonomy")):
            raise SystemExit(f"CASCADE_FROZEN_STAGE1_DEV_BINDING_MISMATCH={row['item_id']}")
        output.append({"request_id": row["request_id"], "ordinal": ordinal, "item_id": row["item_id"], "state": row["state"], "http_status": row["http_status"], "latency_seconds": float(row["latency_seconds"]), "response_path": row["response_path"], "response_sha256": row["response_sha256"], "outer_json_ok": row["outer_json_ok"], "response_json_ok": row["response_json_ok"], "schema_ok": row["schema_ok"], "strict_json_ok": row["strict_json_ok"], "prediction": row["predicted_status"], "pose": "", "evidence": row["evidence"], "error_type": row["error_type"]})
    if any(row["state"] != "COMPLETED" or row["strict_json_ok"] != "true" for row in output):
        raise SystemExit("CASCADE_FROZEN_STAGE1_DEV_NONCANONICAL")
    return output


def metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    valid = [row for row in rows if row["ground_truth"] in {"positive", "negative"} and row["canonical_prediction_success"] == "true"]
    tp = sum(row["ground_truth"] == "positive" and row["final_prediction"] == "positive" for row in valid)
    fn = sum(row["ground_truth"] == "positive" and row["final_prediction"] != "positive" for row in valid)
    fp = sum(row["ground_truth"] == "negative" and row["final_prediction"] == "positive" for row in valid)
    tn = sum(row["ground_truth"] == "negative" and row["final_prediction"] != "positive" for row in valid)
    hard = [row for row in valid if row["metric_stratum"] == "hard_negative"]
    ordinary = [row for row in valid if row["metric_stratum"] == "ordinary_negative"]
    ratio = lambda a, b: None if not b else a / b
    return {"determinate_count": len(valid), "TP": tp, "FP": fp, "TN": tn, "FN": fn, "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn), "f1": ratio(2 * tp, 2 * tp + fp + fn), "accuracy": ratio(tp + tn, len(valid)), "hard_negative_count": len(hard), "hard_negative_fpr": ratio(sum(row["final_prediction"] == "positive" for row in hard), len(hard)), "ordinary_negative_count": len(ordinary), "ordinary_negative_fpr": ratio(sum(row["final_prediction"] == "positive" for row in ordinary), len(ordinary)), "uncertain_count": sum(row["final_prediction"] == "uncertain" for row in rows), "uncertain_rate": ratio(sum(row["final_prediction"] == "uncertain" for row in rows), len(rows))}


def stage1_metrics(rows: list[dict[str, object]], full: list[dict[str, str]]) -> dict[str, object]:
    by = {row["item_id"]: row for row in rows}
    merged = []
    for source in full:
        stage = by[source["item_id"]]
        merged.append({**source, "final_prediction": stage["prediction"], "canonical_prediction_success": str(stage["strict_json_ok"] == "true").lower()})
    return metrics(merged)


def verify_freeze(candidate: str, cfg: dict, phase: str, manifest: Path) -> None:
    if not FREEZE.is_file():
        raise SystemExit("CASCADE_SCREEN_VAL_BLOCKED_WINNER_FREEZE_MISSING")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if freeze.get("winner_candidate") != candidate or freeze.get("winner_dev_gate_pass") is not True or freeze.get("phase_locked") is not True:
        raise SystemExit("CASCADE_SCREEN_VAL_FREEZE_INVALID")
    if freeze.get("config_sha256") != sha256(CONFIG_PATH) or freeze.get("stage2_prompt_sha256") != sha256(STAGE2_PROMPT) or freeze.get("runner_sha256") != sha256(Path(__file__)):
        raise SystemExit("CASCADE_SCREEN_VAL_FREEZE_BINDING_MISMATCH")
    if freeze.get(f"{phase}_manifest_sha256") != sha256(manifest):
        raise SystemExit("CASCADE_SCREEN_VAL_MANIFEST_FREEZE_MISMATCH")
    if freeze.get("final_holdout_executed") is not False or freeze.get("holdout_consumed") is not False:
        raise SystemExit("CASCADE_SCREEN_VAL_HOLDOUT_BOUNDARY_INVALID")


def materialize(run_dir: Path, phase: str, candidate: str, full: list[dict[str, str]], stage1: list[dict[str, object]], stage2: list[dict[str, object]], cfg: dict, stage1_model_call_count: int) -> dict[str, object]:
    s1, s2 = {row["item_id"]: row for row in stage1}, {row["item_id"]: row for row in stage2}
    output: list[dict[str, object]] = []
    for source in full:
        first = s1[source["item_id"]]
        second = s2.get(source["item_id"])
        canonical = first["strict_json_ok"] == "true"
        final = first["prediction"] if canonical else "protocol_failure"
        decision = pose = evidence = ""
        if canonical and first["prediction"] == "positive":
            if second is None:
                canonical, final = False, "protocol_failure"
            else:
                canonical = second["strict_json_ok"] == "true"
                decision, pose, evidence = str(second["prediction"]), str(second["pose"]), str(second["evidence"])
                final = {"SUPPRESS_NORMAL_POSE": "negative", "KEEP_ALERT": "positive", "UNCERTAIN": "uncertain"}.get(decision, "protocol_failure") if canonical else "protocol_failure"
        output.append({**source, "stage1_request_id": first["request_id"], "stage1_state": first["state"], "stage1_http_status": first["http_status"], "stage1_latency_seconds": first["latency_seconds"], "stage1_strict_json_ok": first["strict_json_ok"], "stage1_prediction": first["prediction"], "stage1_evidence": first["evidence"], "stage2_request_id": second["request_id"] if second else "", "stage2_state": second["state"] if second else "", "stage2_http_status": second["http_status"] if second else "", "stage2_latency_seconds": second["latency_seconds"] if second else "", "stage2_strict_json_ok": second["strict_json_ok"] if second else "", "stage2_decision": decision, "stage2_pose": pose, "stage2_evidence": evidence, "canonical_prediction_success": str(canonical).lower(), "final_prediction": final})
    write_csv(run_dir / "stage1_predictions.csv", stage1)
    write_csv(run_dir / "stage2_predictions.csv", stage2)
    write_csv(run_dir / "cascade_predictions.csv", output)
    final_metrics, base = metrics(output), stage1_metrics(stage1, full)
    fprows = [row for row in output if row["ground_truth"] == "negative" and row["final_prediction"] == "positive"]
    fnrows = [row for row in output if row["ground_truth"] == "positive" and row["final_prediction"] != "positive"]
    write_csv(run_dir / "false_positives.csv", fprows, list(output[0]))
    write_csv(run_dir / "false_negatives.csv", fnrows, list(output[0]))
    floor_base = [row for row in output if row["taxonomy"] == "floor_sitting" and row["ground_truth"] == "negative" and row["stage1_prediction"] == "positive"]
    floor_suppressed = [row for row in floor_base if row["stage2_decision"] == "SUPPRESS_NORMAL_POSE"]
    floor_remaining = [row for row in floor_base if row["final_prediction"] == "positive"]
    true_positive_suppressed = [row for row in output if row["ground_truth"] == "positive" and row["stage1_prediction"] == "positive" and row["stage2_decision"] == "SUPPRESS_NORMAL_POSE"]
    stage2_latencies = [float(row["latency_seconds"]) for row in stage2 if row["state"] == "COMPLETED" and int(row["http_status"] or 0) == 200]
    all_calls = len(stage1) + len(stage2)
    strict_calls = sum(row["strict_json_ok"] == "true" for row in stage1) + sum(row["strict_json_ok"] == "true" for row in stage2)
    gates = cfg["gates"]
    gate = {"precision_min": gates["precision_min"], "recall_min": gates["recall_min"], "hard_negative_fpr_max": gates["hard_negative_fpr_max"], "ordinary_negative_fpr_required": gates["ordinary_negative_fpr_required"], "strict_json_success_min": gates["strict_json_success_min"], "precision_pass": final_metrics["precision"] is not None and final_metrics["precision"] >= gates["precision_min"], "recall_pass": final_metrics["recall"] is not None and final_metrics["recall"] >= gates["recall_min"], "hard_negative_fpr_pass": final_metrics["hard_negative_fpr"] is not None and final_metrics["hard_negative_fpr"] <= gates["hard_negative_fpr_max"], "ordinary_negative_fpr_pass": final_metrics["ordinary_negative_fpr"] == gates["ordinary_negative_fpr_required"], "strict_json_success_pass": all_calls > 0 and strict_calls / all_calls == gates["strict_json_success_min"]}
    gate["pass"] = all(value for key, value in gate.items() if key.endswith("_pass"))
    remaining_taxes = {row["taxonomy"] for row in fprows}
    failed_dimensions = [key for key in ("precision_pass", "recall_pass", "hard_negative_fpr_pass", "ordinary_negative_fpr_pass", "strict_json_success_pass") if not gate[key]]
    fallback_eligible = phase == "dev" and candidate == "V3-CASCADE-448" and not gate["pass"] and gate["recall_pass"] and gate["ordinary_negative_fpr_pass"] and gate["strict_json_success_pass"] and set(failed_dimensions).issubset({"precision_pass", "hard_negative_fpr_pass"}) and bool(remaining_taxes) and remaining_taxes == {"floor_sitting"}
    taxonomy = []
    for name in sorted({row["taxonomy"] for row in output}):
        subset = [row for row in output if row["taxonomy"] == name]
        taxonomy.append({"taxonomy": name, "count": len(subset), "baseline_fp": sum(row["ground_truth"] == "negative" and row["stage1_prediction"] == "positive" for row in subset), "cascade_fp": sum(row["ground_truth"] == "negative" and row["final_prediction"] == "positive" for row in subset), "cascade_fn": sum(row["ground_truth"] == "positive" and row["final_prediction"] != "positive" for row in subset), "suppressed": sum(row["stage2_decision"] == "SUPPRESS_NORMAL_POSE" for row in subset)})
    write_csv(run_dir / "taxonomy_metrics.csv", taxonomy)
    summary = {"status": "COMPLETE" if all(row["canonical_prediction_success"] == "true" for row in output) else "INCOMPLETE_OR_PROTOCOL_FAILURE", "event_name": "person_fallen", "event_definition_version": "v3.0", "revision_id": cfg["revision_id"], "phase": phase, "candidate": candidate, "stage1": {"candidate": "V3-C0-448", "resolution": "448x336", "input_count": len(stage1), "model_call_count": stage1_model_call_count, "reused_frozen_dev_predictions": phase == "dev", "baseline_metrics": base}, "stage2": {"prompt_id": cfg["stage2"]["prompt_id"], "resolution": "x".join(map(str, cfg["stage2"]["candidate_resolutions"][candidate])), "call_count": len(stage2), "strict_json_success_rate": sum(row["strict_json_ok"] == "true" for row in stage2) / len(stage2) if stage2 else 1.0, "latency_seconds": {"p50": percentile(stage2_latencies, 0.5), "p95": percentile(stage2_latencies, 0.95), "mean": statistics.mean(stage2_latencies) if stage2_latencies else None, "max": max(stage2_latencies) if stage2_latencies else None}}, "cascade": {"metrics": final_metrics, "strict_json_success_rate": strict_calls / all_calls if all_calls else 0.0, "strict_json_required_invocation_count": all_calls, "call_count_including_reused_stage1": all_calls, "floor_sitting": {"baseline_fp": len(floor_base), "suppressed": len(floor_suppressed), "remaining_fp": len(floor_remaining)}, "true_positive_incorrectly_suppressed": len(true_positive_suppressed), "false_positive_taxonomy": dict(sorted(Counter(row["taxonomy"] for row in fprows).items())), "false_negative_taxonomy": dict(sorted(Counter(row["taxonomy"] for row in fnrows).items()))}, "gate": gate, "fallback_eligible_stage2_896": fallback_eligible, "holdout_requests": 0, "holdout_consumed": False, "stop_further_p4d_generation": True, "formal_dataset_ingest": False, "model_prediction_used_as_gt": False, "human_semantic_review_required": False, "manifest_sha256": sha256(MANIFESTS / f"{phase}_full_manifest.csv"), "stage2_prompt_sha256": sha256(STAGE2_PROMPT), "config_sha256": sha256(CONFIG_PATH), "runner_sha256": sha256(Path(__file__))}
    write_json(run_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["dev", "screen", "val"])
    parser.add_argument("candidate", choices=["V3-CASCADE-448", "V3-CASCADE-896"])
    args = parser.parse_args()
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    manifest = MANIFESTS / f"{args.phase}_full_manifest.csv"
    if not manifest.is_file() or not AUDIT_PATH.is_file():
        raise SystemExit("CASCADE_MANIFEST_OR_AUDIT_MISSING_RUN_BUILDER_FIRST")
    full = load_csv(manifest); validate_manifest(full, args.phase)
    if args.phase in {"screen", "val"}:
        verify_freeze(args.candidate, cfg, args.phase, manifest)
    run_dir = (RUNS / f"{args.phase}_{args.candidate}").resolve()
    if (run_dir / "summary.json").is_file():
        print(json.dumps(json.loads((run_dir / "summary.json").read_text(encoding="utf-8")), ensure_ascii=False, sort_keys=True)); return
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "run_config.json", {**cfg, "phase": args.phase, "candidate": args.candidate, "manifest_path": str(manifest), "manifest_sha256": sha256(manifest), "stage1_prompt_sha256": sha256(STAGE1_PROMPT), "stage2_prompt_sha256": sha256(STAGE2_PROMPT), "runner_sha256": sha256(Path(__file__)), "created_at_utc": utc(), "holdout_requests": 0})
    write_json(run_dir / "runtime_preflight.json", preflight_runtime(cfg["runtime"]))
    if args.phase == "dev":
        stage1, stage1_calls = frozen_dev_stage1(full), 0
    else:
        stage1, stage1_calls = execute_stage(run_dir, "stage1", full, args.phase, args.candidate, STAGE1_PROMPT, (448, 336), cfg), len(full)
    stage1_by_id = {row["item_id"]: row for row in stage1}
    if set(stage1_by_id) != {row["item_id"] for row in full}:
        raise SystemExit("CASCADE_STAGE1_OUTPUT_ITEM_SET_MISMATCH")
    positive_inputs = [row for row in full if stage1_by_id[row["item_id"]]["prediction"] == "positive"]
    stage2 = execute_stage(run_dir, "stage2", positive_inputs, args.phase, args.candidate, STAGE2_PROMPT, tuple(cfg["stage2"]["candidate_resolutions"][args.candidate]), cfg)
    summary = materialize(run_dir, args.phase, args.candidate, full, stage1, stage2, cfg, stage1_calls)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
