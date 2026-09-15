#!/usr/bin/env python3
"""Run the isolated person_fallen v3.0 image-first evaluation.

The runner is deliberately single-threaded and no-retry.  It binds every run
to the v3 prompt, config, runner, input manifest, source image hashes, and
model digest.  A transport-unknown request stops the run and is never resent.
"""
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
REMAP = ROOT / "remap"
CONFIG_PATH = ROOT / "protocol/v3_eval_config.json"
PROMPT_PATH = ROOT / "prompt/V3-C0_prompt.txt"
RUNS = ROOT / "eval/runs"
FREEZE_PATH = ROOT / "freeze/person_fallen_v3_dev_winner.json"
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
STATUSES = {"positive", "negative", "uncertain"}


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


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def append_event(handle, value: object) -> None:
    handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def preprocess(source: Path, destination: Path, width: int, height: int, cfg: dict) -> None:
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((width, height), RESAMPLE)
        canvas = Image.new("RGB", (width, height), tuple(cfg["letterbox_rgb"]))
        canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        canvas.save(temporary, "JPEG", quality=cfg["jpeg_quality"], optimize=cfg["jpeg_optimize"])
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    with Image.open(destination) as image:
        if image.size != (width, height) or image.format != "JPEG":
            raise RuntimeError(f"processed image shape/format mismatch: {destination}")


def strict_parse(outer_raw: str) -> dict[str, object]:
    result: dict[str, object] = {
        "outer_json_ok": False,
        "response_json_ok": False,
        "schema_ok": False,
        "strict_json_ok": False,
        "predicted_status": "protocol_failure",
        "evidence": "",
        "error_type": "",
    }
    try:
        outer = json.loads(outer_raw)
        result["outer_json_ok"] = True
    except Exception as exc:
        result["error_type"] = f"outer_json_parse_failure:{type(exc).__name__}:{exc}"
        return result
    response_text = outer.get("response") if isinstance(outer, dict) else None
    if not isinstance(response_text, str):
        result["error_type"] = "missing_string_response"
        return result
    try:
        value = json.loads(response_text)
        result["response_json_ok"] = True
    except Exception as exc:
        result["error_type"] = f"response_json_parse_failure:{type(exc).__name__}:{exc}"
        return result
    if not isinstance(value, dict) or set(value) != {"person_fallen", "evidence"}:
        result["error_type"] = "strict_schema_keys_failure"
        return result
    if value.get("person_fallen") not in STATUSES or not isinstance(value.get("evidence"), str) or not value["evidence"].strip():
        result["error_type"] = "strict_schema_value_failure"
        return result
    result.update({
        "schema_ok": True,
        "strict_json_ok": True,
        "predicted_status": value["person_fallen"],
        "evidence": value["evidence"].strip(),
    })
    return result


def call_endpoint(cfg: dict, processed: Path, prompt: str) -> dict[str, object]:
    payload = {
        "model": cfg["model"],
        "prompt": prompt,
        "images": [base64.b64encode(processed.read_bytes()).decode("ascii")],
        "stream": cfg["stream"],
        "format": cfg["format"],
        "think": cfg["think"],
        "options": cfg["options"],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    started = time.monotonic()
    endpoint = cfg["endpoint"] + "/api/generate"
    try:
        req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=cfg["timeout_seconds"]) as response:
            raw = response.read().decode("utf-8")
            code = response.status
        return {
            "http_ok": code == 200,
            "http_status": code,
            "raw": raw,
            "latency_seconds": time.monotonic() - started,
            "error_type": "" if code == 200 else f"HTTP_STATUS_{code}",
            "payload_without_image": {key: value for key, value in payload.items() if key != "images"},
        }
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {
            "http_ok": False,
            "http_status": exc.code,
            "raw": body,
            "latency_seconds": time.monotonic() - started,
            "error_type": f"HTTPError:{exc}",
            "payload_without_image": {key: value for key, value in payload.items() if key != "images"},
            "confirmed_failure": True,
        }
    except (error.URLError, TimeoutError, OSError) as exc:
        return {
            "http_ok": False,
            "http_status": None,
            "raw": "",
            "latency_seconds": time.monotonic() - started,
            "error_type": f"TRANSPORT_UNKNOWN:{type(exc).__name__}:{exc}",
            "payload_without_image": {key: value for key, value in payload.items() if key != "images"},
            "transport_unknown": True,
        }


def preflight_runtime(cfg: dict) -> dict:
    def get_json(path: str) -> dict:
        req = request.Request(cfg["endpoint"] + path, method="GET")
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    tags = get_json("/api/tags")
    models = {item.get("name"): item for item in tags.get("models", []) if isinstance(item, dict)}
    model = models.get(cfg["model"])
    if not model:
        raise SystemExit("V3_RUNTIME_PREFLIGHT_MODEL_MISSING")
    if model.get("digest") != cfg["model_digest"]:
        raise SystemExit("V3_RUNTIME_PREFLIGHT_MODEL_DIGEST_MISMATCH")
    version = get_json("/api/version")
    if version.get("version") != cfg["ollama_version"]:
        raise SystemExit("V3_RUNTIME_PREFLIGHT_OLLAMA_VERSION_MISMATCH")
    return {
        "captured_at_utc": utc(),
        "endpoint": cfg["endpoint"],
        "api_tags": tags,
        "api_version": version,
        "selected_model": model,
        "status": "PASS",
    }


def manifest_path(phase: str) -> Path:
    return REMAP / {
        "dev": "person_fallen_v3_dev_manifest.csv",
        "screen": "person_fallen_v3_screen_manifest.csv",
        "val": "person_fallen_v3_val_manifest.csv",
    }[phase]


def verify_manifest(rows: list[dict[str, str]], phase: str) -> None:
    expected_split = {"dev": "V3_DEV", "screen": "V3_SCREEN", "val": "V3_VAL"}[phase]
    if not rows or len({row["item_id"] for row in rows}) != len(rows):
        raise SystemExit("V3_EVAL_MANIFEST_SHAPE_INVALID")
    if any(row["v3_split"] != expected_split for row in rows):
        raise SystemExit("V3_EVAL_MANIFEST_SPLIT_INVALID")
    if any(row["formal_v3_evaluation"] != "true" for row in rows):
        raise SystemExit("V3_EVAL_MANIFEST_NONFORMAL_ROW")
    if any(row["ground_truth"] not in STATUSES for row in rows):
        raise SystemExit("V3_EVAL_MANIFEST_GT_INVALID")
    if any(row["source_split"] == "HOLDOUT" or row["v3_split"] == "HOLDOUT" for row in rows):
        raise SystemExit("V3_EVAL_HOLDOUT_CONTAMINATION")
    group_splits = defaultdict(set)
    for row in rows:
        group_splits[row["group_id"]].add(row["v3_split"])
        image = Path(row["image_path"])
        prompt = Path(row["prompt_path"])
        if not image.is_file() or sha256(image) != row["image_sha256"]:
            raise SystemExit(f"V3_EVAL_IMAGE_HASH_MISMATCH={row['item_id']}")
        if not prompt.is_file() or sha256(prompt) != row["prompt_sha256"]:
            raise SystemExit(f"V3_EVAL_PROMPT_HASH_MISMATCH={row['item_id']}")
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise SystemExit("V3_EVAL_GROUP_SPLIT_LEAKAGE")


def init_ledger(run_dir: Path, rows: list[dict[str, str]], phase: str, candidate: str, cfg: dict, manifest: Path) -> sqlite3.Connection:
    path = run_dir / "request_ledger.sqlite3"
    new = not path.exists()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS requests ("
        "request_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, item_id TEXT UNIQUE NOT NULL, state TEXT NOT NULL, "
        "started_at TEXT, completed_at TEXT, image_sha256 TEXT NOT NULL, processed_image_sha256 TEXT, "
        "prompt_sha256 TEXT NOT NULL, config_sha256 TEXT NOT NULL, http_status INTEGER, latency_seconds REAL, "
        "response_sha256 TEXT, error_type TEXT)"
    )
    binding = {
        "phase": phase,
        "candidate": candidate,
        "resolution": json.dumps(cfg["candidate_resolutions"][candidate]),
        "manifest_sha256": sha256(manifest),
        "prompt_sha256": sha256(PROMPT_PATH),
        "config_sha256": sha256(CONFIG_PATH),
        "runner_sha256": sha256(Path(__file__)),
        "automatic_retry": "false",
        "resend_completion_unknown": "false",
        "holdout_requests": "0",
    }
    if new:
        run_id = f"V3_{phase.upper()}_{candidate}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        metadata = {"run_id": run_id, **binding, "planned_requests": str(len(rows))}
        connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", metadata.items())
        for ordinal, row in enumerate(rows, 1):
            connection.execute(
                "INSERT INTO requests(request_id,ordinal,item_id,state,image_sha256,prompt_sha256,config_sha256) VALUES (?,?,?,?,?,?,?)",
                (f"{run_id}_{ordinal:04d}", ordinal, row["item_id"], "NOT_STARTED", row["image_sha256"], sha256(PROMPT_PATH), sha256(CONFIG_PATH)),
            )
        connection.commit()
    else:
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        if any(metadata.get(key) != value for key, value in binding.items()):
            raise SystemExit("V3_EVAL_EXISTING_LEDGER_BINDING_MISMATCH")
    if connection.execute("SELECT count(*) FROM requests WHERE state='STARTED'").fetchone()[0]:
        raise SystemExit("V3_EVAL_INCOMPLETE_INDETERMINATE_REQUEST")
    if connection.execute("SELECT count(*) FROM requests WHERE state='UNKNOWN'").fetchone()[0]:
        raise SystemExit("V3_EVAL_UNKNOWN_REQUEST_NEVER_RESENT")
    return connection


def binary_metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    valid = [row for row in rows if row["ground_truth"] in {"positive", "negative"} and row["canonical_prediction_success"] == "true"]
    tp = fp = tn = fn = 0
    for row in valid:
        alert = row["predicted_status"] == "positive"
        if row["ground_truth"] == "positive" and alert:
            tp += 1
        elif row["ground_truth"] == "positive":
            fn += 1
        elif alert:
            fp += 1
        else:
            tn += 1
    ratio = lambda numerator, denominator: None if not denominator else numerator / denominator
    hard = [row for row in valid if row["metric_stratum"] == "hard_negative"]
    ordinary = [row for row in valid if row["metric_stratum"] == "ordinary_negative"]
    return {
        "determinate_count": len(valid),
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "positive_recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "accuracy": ratio(tp + tn, tp + tn + fp + fn),
        "fpr": ratio(fp, fp + tn),
        "specificity": ratio(tn, tn + fp),
        "hard_negative_count": len(hard),
        "hard_negative_fpr": ratio(sum(row["predicted_status"] == "positive" for row in hard), len(hard)),
        "ordinary_negative_count": len(ordinary),
        "ordinary_negative_fpr": ratio(sum(row["predicted_status"] == "positive" for row in ordinary), len(ordinary)),
        "model_uncertain_count": sum(row["predicted_status"] == "uncertain" for row in valid),
        "model_uncertain_rate": ratio(sum(row["predicted_status"] == "uncertain" for row in valid), len(valid)),
        "gt_uncertain_prediction_distribution": dict(sorted(Counter(row["predicted_status"] for row in rows if row["ground_truth"] == "uncertain").items())),
    }


def taxonomy_metrics(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output = []
    for taxonomy in sorted({row["taxonomy"] for row in rows}):
        subset = [row for row in rows if row["taxonomy"] == taxonomy]
        valid = [row for row in subset if row["ground_truth"] in {"positive", "negative"} and row["canonical_prediction_success"] == "true"]
        tp = sum(row["ground_truth"] == "positive" and row["predicted_status"] == "positive" for row in valid)
        fn = sum(row["ground_truth"] == "positive" and row["predicted_status"] != "positive" for row in valid)
        fp = sum(row["ground_truth"] == "negative" and row["predicted_status"] == "positive" for row in valid)
        tn = sum(row["ground_truth"] == "negative" and row["predicted_status"] != "positive" for row in valid)
        output.append({
            "taxonomy": taxonomy,
            "count": len(subset),
            "gt_positive": sum(row["ground_truth"] == "positive" for row in subset),
            "gt_negative": sum(row["ground_truth"] == "negative" for row in subset),
            "gt_uncertain": sum(row["ground_truth"] == "uncertain" for row in subset),
            "TP": tp,
            "FP": fp,
            "TN": tn,
            "FN": fn,
            "model_uncertain": sum(row["predicted_status"] == "uncertain" for row in subset),
            "protocol_failure": sum(row["canonical_prediction_success"] != "true" for row in subset),
            "false_positive": fp,
            "false_negative": fn,
        })
    return output


def materialize(run_dir: Path, rows: list[dict[str, str]], phase: str, candidate: str, width: int, height: int, cfg: dict, manifest: Path) -> dict:
    connection = sqlite3.connect(run_dir / "request_ledger.sqlite3")
    request_rows = connection.execute("SELECT request_id,ordinal,item_id,state,http_status,latency_seconds,response_sha256,error_type FROM requests ORDER BY ordinal").fetchall()
    connection.close()
    source_by_id = {row["item_id"]: row for row in rows}
    predictions: list[dict[str, object]] = []
    for request_id, ordinal, item_id, state, http_status, latency, response_sha, ledger_error in request_rows:
        source = source_by_id[item_id]
        response_path = run_dir / "responses" / f"{request_id}.json"
        parsed = {
            "outer_json_ok": False,
            "response_json_ok": False,
            "schema_ok": False,
            "strict_json_ok": False,
            "predicted_status": "protocol_failure",
            "evidence": "",
            "error_type": ledger_error or "",
        }
        raw = ""
        if state == "COMPLETED" and response_path.is_file():
            wrapper = json.loads(response_path.read_text(encoding="utf-8"))
            raw = wrapper.get("outer_raw", "")
            parsed = strict_parse(raw)
        canonical = bool(parsed["strict_json_ok"])
        status = str(parsed["predicted_status"])
        predictions.append({
            "request_id": request_id,
            "ordinal": ordinal,
            "phase": phase,
            "candidate": candidate,
            "resolution": f"{width}x{height}",
            "item_id": source["item_id"],
            "source_family": source["source_family"],
            "prompt_id": source["prompt_id"],
            "media_id": source["media_id"],
            "group_id": source["group_id"],
            "source_split": source["source_split"],
            "v3_split": source["v3_split"],
            "image_path": source["image_path"],
            "image_sha256": source["image_sha256"],
            "prompt_path": source["prompt_path"],
            "prompt_sha256": source["prompt_sha256"],
            "taxonomy": source["taxonomy"],
            "old_role": source["old_role"],
            "old_label": source["old_label"],
            "ground_truth": source["ground_truth"],
            "metric_stratum": source["metric_stratum"],
            "gt_type": source["gt_type"],
            "gt_source": source["gt_source"],
            "human_semantic_review_required": source["human_semantic_review_required"],
            "state": state,
            "http_status": http_status if http_status is not None else "",
            "latency_seconds": f"{float(latency or 0):.6f}",
            "response_path": str(response_path) if response_path.is_file() else "",
            "response_sha256": response_sha or "",
            "outer_json_ok": str(parsed["outer_json_ok"]).lower(),
            "response_json_ok": str(parsed["response_json_ok"]).lower(),
            "schema_ok": str(parsed["schema_ok"]).lower(),
            "strict_json_ok": str(parsed["strict_json_ok"]).lower(),
            "canonical_prediction_success": str(canonical).lower(),
            "predicted_status": status,
            "predicted_binary_alert": str(status == "positive").lower() if canonical else "",
            "evidence": parsed["evidence"],
            "error_type": parsed["error_type"],
        })
    fields = list(predictions[0])
    write_csv(run_dir / "predictions.csv", predictions, fields)
    write_csv(run_dir / "protocol_failures.csv", [row for row in predictions if row["canonical_prediction_success"] != "true"], fields)
    write_csv(run_dir / "false_positives.csv", [row for row in predictions if row["ground_truth"] == "negative" and row["predicted_status"] == "positive"], fields)
    write_csv(run_dir / "false_negatives.csv", [row for row in predictions if row["ground_truth"] == "positive" and row["predicted_status"] != "positive"], fields)
    write_csv(run_dir / "model_uncertain.csv", [row for row in predictions if row["predicted_status"] == "uncertain"], fields)
    tax_rows = taxonomy_metrics(predictions)
    write_csv(run_dir / "taxonomy_metrics.csv", tax_rows, list(tax_rows[0]) if tax_rows else ["taxonomy"])
    latencies = [float(row["latency_seconds"]) for row in predictions if row["state"] == "COMPLETED" and row["http_status"] == 200]
    metrics = binary_metrics(predictions)
    gate = {
        "precision_min": 0.93,
        "recall_min": 0.95,
        "hard_negative_fpr_max": 0.05,
        "ordinary_negative_fpr_required": 0.0,
        "strict_json_success_min": 1.0,
        "precision_pass": metrics["precision"] is not None and metrics["precision"] >= 0.93,
        "recall_pass": metrics["recall"] is not None and metrics["recall"] >= 0.95,
        "hard_negative_fpr_pass": metrics["hard_negative_fpr"] is not None and metrics["hard_negative_fpr"] <= 0.05,
        "ordinary_negative_fpr_pass": metrics["ordinary_negative_fpr"] == 0.0,
        "strict_json_success_pass": sum(row["strict_json_ok"] == "true" for row in predictions) / len(predictions) == 1.0,
    }
    gate["pass"] = all(value for key, value in gate.items() if key.endswith("_pass"))
    protocol = {
        "request_count": len(predictions),
        "completed_count": sum(row["state"] == "COMPLETED" for row in predictions),
        "failed_confirmed_count": sum(row["state"] == "FAILED_CONFIRMED" for row in predictions),
        "transport_unknown_count": sum(row["state"] == "UNKNOWN" for row in predictions),
        "http_success_rate": sum(row["http_status"] == 200 for row in predictions) / len(predictions),
        "strict_json_success_rate": sum(row["strict_json_ok"] == "true" for row in predictions) / len(predictions),
        "schema_success_rate": sum(row["schema_ok"] == "true" for row in predictions) / len(predictions),
        "prediction_distribution": dict(sorted(Counter(row["predicted_status"] for row in predictions).items())),
        "latency_seconds": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "mean": statistics.mean(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
    }
    summary = {
        "status": "COMPLETE" if all(row["state"] == "COMPLETED" for row in predictions) else "INCOMPLETE",
        "event_name": "person_fallen",
        "event_definition_version": "v3.0",
        "revision_id": "PERSON_FALLEN_V3_ANOMALOUS_NEAR_GROUND_20260901_01",
        "phase": phase,
        "candidate": candidate,
        "resolution": f"{width}x{height}",
        "run_dir": str(run_dir),
        "manifest_path": str(manifest),
        "manifest_sha256": sha256(manifest),
        "prompt_sha256": sha256(PROMPT_PATH),
        "config_sha256": sha256(CONFIG_PATH),
        "runner_sha256": sha256(Path(__file__)),
        "model": cfg["model"],
        "model_digest": cfg["model_digest"],
        "endpoint": cfg["endpoint"],
        "gt_policy": {
            "GT_TYPE": cfg["gt_type"],
            "GT_SOURCE": cfg["gt_source"],
            "HUMAN_SEMANTIC_REVIEW_REQUIRED": cfg["human_semantic_review_required"],
            "model_prediction_used_as_gt": False,
        },
        "counts": {
            "planned_requests": len(predictions),
            "ground_truth_positive": sum(row["ground_truth"] == "positive" for row in predictions),
            "ground_truth_negative": sum(row["ground_truth"] == "negative" for row in predictions),
            "ground_truth_uncertain": sum(row["ground_truth"] == "uncertain" for row in predictions),
            "groups": len({row["group_id"] for row in predictions}),
        },
        "metrics": metrics,
        "protocol": protocol,
        "gate": gate,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "q9_binding_blocked_in_main_metrics": False,
        "taxonomy_error_file": str(run_dir / "taxonomy_metrics.csv"),
    }
    write_json(run_dir / "summary.json", summary)
    lines = [
        f"# person_fallen v3.0 {phase.upper()} {candidate}",
        "",
        f"- Resolution: `{width}x{height}` letterbox JPEG{cfg['jpeg_quality']}",
        f"- Requests: `{len(predictions)}`; Holdout requests: `0`; Holdout consumed: `false`",
        f"- GT: `{cfg['gt_type']}` from `{cfg['gt_source']}`; human semantic review required: `false`",
        "",
        "## Metrics",
    ]
    for key in ("TP", "FP", "TN", "FN", "precision", "recall", "f1", "accuracy", "hard_negative_fpr", "ordinary_negative_fpr", "model_uncertain_rate"):
        lines.append(f"- {key}: `{metrics.get(key)}`")
    lines.extend([
        "",
        "## Protocol and latency",
        f"- strict JSON success: `{protocol['strict_json_success_rate']}`",
        f"- P50 seconds: `{protocol['latency_seconds']['p50']}`",
        f"- P95 seconds: `{protocol['latency_seconds']['p95']}`",
        f"- gate pass: `{gate['pass']}`",
        "",
        "Taxonomy-level TP/FP/TN/FN and protocol errors are in `taxonomy_metrics.csv`; individual error rows are in the false-positive/false-negative/uncertain files.",
    ])
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def verify_winner_freeze(cfg: dict, candidate: str, phase: str, manifest: Path) -> None:
    if not FREEZE_PATH.is_file():
        raise SystemExit("V3_SCREEN_VAL_BLOCKED_WINNER_FREEZE_MISSING")
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if freeze.get("winner_candidate_id") != candidate:
        raise SystemExit("V3_SCREEN_VAL_BLOCKED_WINNER_CANDIDATE_MISMATCH")
    if freeze.get("winner_resolution") != cfg["candidate_resolutions"][candidate]:
        raise SystemExit("V3_SCREEN_VAL_BLOCKED_WINNER_RESOLUTION_MISMATCH")
    if freeze.get("prompt_sha256") != sha256(PROMPT_PATH) or freeze.get("config_sha256") != sha256(CONFIG_PATH) or freeze.get("runner_sha256") != sha256(Path(__file__)):
        raise SystemExit("V3_SCREEN_VAL_BLOCKED_WINNER_BINDING_MISMATCH")
    if phase not in {"screen", "val"}:
        raise SystemExit("V3_WINNER_FREEZE_PHASE_INVALID")
    if freeze.get("winner_dev_gate_pass") is not True:
        raise SystemExit("V3_SCREEN_VAL_BLOCKED_DEV_GATE_NOT_PASS")
    if freeze.get("screen_manifest_sha256") != sha256(REMAP / "person_fallen_v3_screen_manifest.csv"):
        raise SystemExit("V3_SCREEN_MANIFEST_FREEZE_MISMATCH")
    if freeze.get("val_manifest_sha256") != sha256(REMAP / "person_fallen_v3_val_manifest.csv"):
        raise SystemExit("V3_VAL_MANIFEST_FREEZE_MISMATCH")
    if freeze.get("phase_locked") is not True or freeze.get("final_holdout_executed") is not False:
        raise SystemExit("V3_SCREEN_VAL_FREEZE_POLICY_INVALID")
    if freeze.get("requested_manifest_sha256") not in {sha256(manifest), None}:
        raise SystemExit("V3_SCREEN_VAL_REQUESTED_MANIFEST_MISMATCH")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["dev", "screen", "val"])
    parser.add_argument("candidate", choices=["V3-C0-448", "V3-C0-896"])
    parser.add_argument("--run-dir", default="")
    args = parser.parse_args()
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    manifest = manifest_path(args.phase)
    if not manifest.is_file():
        raise SystemExit("V3_EVAL_MANIFEST_MISSING")
    rows = load_csv(manifest)
    verify_manifest(rows, args.phase)
    if args.phase in {"screen", "val"}:
        verify_winner_freeze(cfg, args.candidate, args.phase, manifest)
    width, height = cfg["candidate_resolutions"][args.candidate]
    run_dir = Path(args.run_dir) if args.run_dir else RUNS / f"{args.phase}_{args.candidate}"
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "responses").mkdir(exist_ok=True)
    (run_dir / f"processed_{width}x{height}").mkdir(exist_ok=True)
    if (run_dir / "summary.json").is_file() and (run_dir / "request_ledger.sqlite3").is_file():
        print(json.dumps(json.loads((run_dir / "summary.json").read_text(encoding="utf-8")), ensure_ascii=False, sort_keys=True))
        return
    write_csv(run_dir / "run_manifest.csv", rows, list(rows[0]))
    write_json(run_dir / "run_config.json", {
        **cfg,
        "phase": args.phase,
        "candidate": args.candidate,
        "resolution": [width, height],
        "manifest_path": str(manifest),
        "manifest_sha256": sha256(manifest),
        "prompt_sha256": sha256(PROMPT_PATH),
        "config_sha256": sha256(CONFIG_PATH),
        "runner_sha256": sha256(Path(__file__)),
        "created_at_utc": utc(),
        "holdout_requests": 0,
    })
    write_json(run_dir / "runtime_preflight.json", preflight_runtime(cfg))
    connection = init_ledger(run_dir, rows, args.phase, args.candidate, cfg, manifest)
    pending = connection.execute("SELECT request_id,ordinal,item_id FROM requests WHERE state='NOT_STARTED' ORDER BY ordinal").fetchall()
    source_by_id = {row["item_id"]: row for row in rows}
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    events_path = run_dir / "request_events.jsonl"
    with events_path.open("a", encoding="utf-8") as events:
        for index, (request_id, ordinal, item_id) in enumerate(pending, 1):
            source = source_by_id[item_id]
            started_at = utc()
            connection.execute("UPDATE requests SET state='STARTED',started_at=? WHERE request_id=? AND state='NOT_STARTED'", (started_at, request_id))
            connection.commit()
            append_event(events, {
                "event": "REQUEST_STARTED",
                "request_id": request_id,
                "ordinal": ordinal,
                "item_id": item_id,
                "timestamp_utc": started_at,
                "attempt": 1,
                "image_sha256": source["image_sha256"],
                "prompt_sha256": sha256(PROMPT_PATH),
                "config_sha256": sha256(CONFIG_PATH),
                "phase": args.phase,
                "candidate": args.candidate,
            })
            processed = run_dir / f"processed_{width}x{height}" / f"{ordinal:04d}_{source['prompt_id']}.jpg"
            try:
                preprocess(Path(source["image_path"]), processed, width, height, cfg)
                processed_sha = sha256(processed)
                connection.execute("UPDATE requests SET processed_image_sha256=? WHERE request_id=?", (processed_sha, request_id))
                connection.commit()
            except Exception as exc:
                error_text = f"PREPROCESS_FAILED:{type(exc).__name__}:{exc}"
                connection.execute("UPDATE requests SET state='FAILED_CONFIRMED',completed_at=?,error_type=? WHERE request_id=?", (utc(), error_text, request_id))
                connection.commit()
                append_event(events, {"event": "REQUEST_FAILED_CONFIRMED", "request_id": request_id, "item_id": item_id, "timestamp_utc": utc(), "error_type": error_text})
                continue
            result = call_endpoint(cfg, processed, prompt)
            completed_at = utc()
            if result.get("transport_unknown"):
                error_text = str(result["error_type"])
                append_event(events, {"event": "REQUEST_UNKNOWN_STOP", "request_id": request_id, "item_id": item_id, "timestamp_utc": completed_at, "error_type": error_text})
                connection.execute("UPDATE requests SET state='UNKNOWN',completed_at=?,latency_seconds=?,error_type=? WHERE request_id=?", (completed_at, result["latency_seconds"], error_text, request_id))
                connection.commit()
                connection.close()
                raise SystemExit("V3_EVAL_STOPPED_TRANSPORT_UNKNOWN_NO_RESEND")
            wrapper = {
                "request_id": request_id,
                "ordinal": ordinal,
                "item_id": item_id,
                "phase": args.phase,
                "candidate": args.candidate,
                "request_payload_without_image": result["payload_without_image"],
                "source_image_path": source["image_path"],
                "source_image_sha256": source["image_sha256"],
                "processed_image_path": str(processed),
                "processed_image_sha256": processed_sha,
                "prompt_sha256": sha256(PROMPT_PATH),
                "config_sha256": sha256(CONFIG_PATH),
                "timestamp_start_utc": started_at,
                "timestamp_end_utc": completed_at,
                "http_status": result["http_status"],
                "latency_seconds": result["latency_seconds"],
                "outer_raw": result["raw"],
                "transport_error": result.get("error_type", ""),
            }
            response_path = run_dir / "responses" / f"{request_id}.json"
            write_json(response_path, wrapper)
            response_sha = sha256(response_path)
            state = "COMPLETED" if result.get("http_ok") else "FAILED_CONFIRMED"
            connection.execute("UPDATE requests SET state='" + state + "',completed_at=?,http_status=?,latency_seconds=?,response_sha256=?,error_type=? WHERE request_id=?", (completed_at, result["http_status"], result["latency_seconds"], response_sha, result.get("error_type", ""), request_id))
            connection.commit()
            append_event(events, {"event": "REQUEST_COMPLETED" if state == "COMPLETED" else "REQUEST_FAILED_CONFIRMED", "request_id": request_id, "item_id": item_id, "timestamp_utc": completed_at, "http_status": result["http_status"], "latency_seconds": result["latency_seconds"], "response_sha256": response_sha, "error_type": result.get("error_type", "")})
            if index % 10 == 0 or index == len(pending):
                print(f"V3_{args.phase.upper()}_{args.candidate}_PROGRESS={index}/{len(pending)}", flush=True)
    summary = materialize(run_dir, rows, args.phase, args.candidate, width, height, cfg, manifest)
    connection.close()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
