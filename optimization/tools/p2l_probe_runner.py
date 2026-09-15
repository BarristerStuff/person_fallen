#!/usr/bin/env python3
"""Durable DEV-only P2L runtime probes using the frozen P2 C3 protocol."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
P2L = ROOT / "06_p2l_remote_latency_forensics"
CFG_PATH = P2 / "03_candidates/p2_request_config.json"
PROMPT_PATH = P2 / "05_winner_freeze/p2_winner_prompt.txt"
EXPECTED_PROMPT_SHA = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
EXPECTED_MODEL_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
ENDPOINT = "http://192.168.20.62:11434"
VALID_STATUS = {"positive", "negative", "uncertain"}

sys.path.insert(0, str(ROOT / "tools"))
from p2l_runtime_snapshot import capture_snapshot  # noqa: E402


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_fsync(path: Path, obj: object) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


def preprocess(src: Path, dst: Path, cfg: dict) -> None:
    with Image.open(src) as im:
        im.verify()
    with Image.open(src) as im:
        im = im.convert("RGB")
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        im.thumbnail((cfg["target_width"], cfg["target_height"]), resample)
        canvas = Image.new("RGB", (cfg["target_width"], cfg["target_height"]), tuple(cfg["letterbox_rgb"]))
        canvas.paste(im, ((cfg["target_width"] - im.width) // 2, (cfg["target_height"] - im.height) // 2))
        canvas.save(dst, "JPEG", quality=cfg["jpeg_quality"], optimize=cfg["jpeg_optimize"])


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * p
    lo, hi = int(pos), int(pos + 0.999999999)
    if lo == hi:
        return vals[lo]
    return vals[lo] + (pos - lo) * (vals[hi] - vals[lo])


def duration_stats(values: list[float]) -> dict[str, object]:
    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p50": quantile(values, 0.50),
        "p90": quantile(values, 0.90),
        "p95": quantile(values, 0.95),
        "max": max(values) if values else None,
    }


def parse_response(outer: object) -> dict[str, object]:
    if not isinstance(outer, dict):
        return {"response_nonempty": False, "json_ok": False, "schema_ok": False, "canonical_ok": False, "predicted_status": "", "evidence": "", "error_type": "outer_json_failure"}
    response = outer.get("response", "")
    if not isinstance(response, str) or not response.strip():
        return {"response_nonempty": False, "json_ok": False, "schema_ok": False, "canonical_ok": False, "predicted_status": "", "evidence": "", "error_type": "response_empty"}
    try:
        obj = json.loads(response)
    except Exception as exc:
        return {"response_nonempty": True, "json_ok": False, "schema_ok": False, "canonical_ok": False, "predicted_status": "", "evidence": "", "error_type": f"response_json_failure:{exc}"}
    if not isinstance(obj, dict):
        return {"response_nonempty": True, "json_ok": True, "schema_ok": False, "canonical_ok": False, "predicted_status": "", "evidence": "", "error_type": "schema_not_object"}
    status = obj.get("person_fallen")
    evidence = obj.get("evidence")
    schema = isinstance(status, str) and isinstance(evidence, str)
    canonical = schema and status in VALID_STATUS
    return {"response_nonempty": True, "json_ok": True, "schema_ok": schema, "canonical_ok": canonical, "predicted_status": status if canonical else "", "evidence": evidence if isinstance(evidence, str) else "", "error_type": "" if canonical else ("invalid_enum" if schema else "schema_failure")}


def init_db(path: Path, rows: list[dict[str, str]], run_id: str, probe: str, cfg_sha: str, prompt_sha: str, manifest_sha: str, keep_alive: str | None) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("CREATE TABLE IF NOT EXISTS metadata (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    # P2L A/B deliberately repeat one fixed media.  Unlike the P2 inference
    # ledger, media_id is not UNIQUE; request_id remains the identity key.
    conn.execute("CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, media_id TEXT NOT NULL, state TEXT NOT NULL, started_at TEXT, completed_at TEXT, attempt INTEGER NOT NULL, image_sha256 TEXT NOT NULL, config_sha256 TEXT NOT NULL, prompt_sha256 TEXT NOT NULL, http_status INTEGER, latency_seconds REAL, response_sha256 TEXT, error_type TEXT)")
    existing = dict(conn.execute("SELECT k,v FROM metadata"))
    if existing:
        expected = {"run_id": run_id, "probe": probe, "manifest_sha256": manifest_sha, "config_sha256": cfg_sha, "prompt_sha256": prompt_sha, "automatic_retry": "false"}
        for key, value in expected.items():
            if existing.get(key) != value:
                raise RuntimeError(f"existing ledger binding mismatch: {key}")
    else:
        metadata = {"run_id": run_id, "probe": probe, "manifest_sha256": manifest_sha, "config_sha256": cfg_sha, "prompt_sha256": prompt_sha, "planned_requests": str(len(rows)), "automatic_retry": "false", "keep_alive": keep_alive or "omitted", "endpoint": ENDPOINT, "created_at_utc": utc()}
        conn.executemany("INSERT INTO metadata(k,v) VALUES (?,?)", metadata.items())
        conn.executemany("INSERT INTO requests(request_id,media_id,state,attempt,image_sha256,config_sha256,prompt_sha256) VALUES (?,?,?,?,?,?,?)", [(f"{run_id}_{i:03d}", row["media_id"], "NOT_STARTED", 1, row["image_sha256"], cfg_sha, prompt_sha) for i, row in enumerate(rows, 1)])
        conn.commit()
    return conn


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0].keys()) if rows else ["request_id"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=["A", "B", "C"])
    args = parser.parse_args()
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt_sha = sha256(PROMPT_PATH)
    cfg_sha = sha256(CFG_PATH)
    if prompt_sha != EXPECTED_PROMPT_SHA:
        raise SystemExit("P2L_STATUS=BLOCKED_C3_PROMPT_HASH_MISMATCH")
    if cfg["model"] != "qwen3.5:4b" or cfg["model_digest"] != EXPECTED_MODEL_DIGEST or cfg["endpoint"] != ENDPOINT:
        raise SystemExit("P2L_STATUS=BLOCKED_MODEL_OR_ENDPOINT_MISMATCH")
    if cfg.get("think") is not False or cfg.get("format") != "json" or cfg.get("stream") is not False or cfg.get("thinking_fallback") is not False:
        raise SystemExit("P2L_STATUS=BLOCKED_C3_PROTOCOL_MISMATCH")
    manifest_path = P2L / "02_diagnostic_manifest" / ("p2l_fixed_image_manifest.csv" if args.probe in {"A", "B"} else "p2l_diverse_manifest.csv")
    manifest_rows = load_rows(manifest_path)
    expected_n = 24 if args.probe in {"A", "B"} else 16
    expected_keep_alive = "30m" if args.probe == "B" else None
    if len(manifest_rows) != (1 if args.probe in {"A", "B"} else 16) or any((row.get("original_split") or "") != "DEV" or row.get("p2_internal_role") != "P2_DESIGN" for row in manifest_rows):
        raise SystemExit("P2L_STATUS=BLOCKED_DIAGNOSTIC_MANIFEST")
    if any(row.get("split") == "HOLDOUT" for row in manifest_rows):
        raise SystemExit("P2L_STATUS=INVALID_HOLDOUT_CONTAMINATION")
    rows = [dict(manifest_rows[0], repetition_index=i) for i in range(1, 25)] if args.probe in {"A", "B"} else manifest_rows
    run_dir = P2L / ({"A": "04_probe_A_exact_c3", "B": "05_probe_B_keepalive", "C": "06_probe_C_diverse_images"}[args.probe])
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "request_ledger.sqlite3").exists():
        # Never resume or rerun a partial performance probe implicitly.
        raise SystemExit(f"P2L_STATUS=EXISTING_LEDGER_REQUIRES_MANUAL_AUDIT:{run_dir}")
    processed_dir = run_dir / "processed_448x336"
    response_dir = run_dir / "responses"
    processed_dir.mkdir(exist_ok=True)
    response_dir.mkdir(exist_ok=True)
    run_id = f"P2L_{args.probe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    manifest_sha = sha256(manifest_path)
    run_config = {"stage": "P2L_REMOTE_LATENCY_FORENSICS", "probe": f"P2L_{args.probe}", "run_id": run_id, "model": cfg["model"], "model_digest": cfg["model_digest"], "endpoint": ENDPOINT, "prompt_path": str(PROMPT_PATH), "prompt_sha256": prompt_sha, "request_config_path": str(CFG_PATH), "request_config_sha256": cfg_sha, "manifest_path": str(manifest_path), "manifest_sha256": manifest_sha, "unique_media_count": len(manifest_rows), "repeated_requests_per_media": 24 if args.probe in {"A", "B"} else 1, "keep_alive": expected_keep_alive, "protocol": cfg, "automatic_retry": False, "new_val_requests": 0, "holdout_requests": 0, "parser_source": "response_only", "thinking_fallback": False, "created_at_utc": utc()}
    atomic_json(run_dir / "run_config.json", run_config)
    conn = init_db(run_dir / "request_ledger.sqlite3", rows, run_id, f"P2L_{args.probe}", cfg_sha, prompt_sha, manifest_sha, expected_keep_alive)
    if conn.execute("SELECT COUNT(*) FROM requests WHERE state='STARTED'").fetchone()[0]:
        raise SystemExit("P2L_RUN_INDETERMINATE_STARTED_REQUEST")
    by_id = {row["media_id"]: row for row in rows}
    pending = conn.execute("SELECT request_id,media_id FROM requests WHERE state='NOT_STARTED' ORDER BY request_id").fetchall()
    if len(pending) != expected_n:
        raise SystemExit("P2L_STATUS=EXISTING_OR_INCOMPLETE_LEDGER")
    capture_snapshot(f"P2L_{args.probe}", "before")
    events_path = run_dir / "request_events.jsonl"
    prompt_config = {"model": cfg["model"], "prompt": prompt, "stream": False, "format": "json", "think": False, "options": cfg["options"]}
    if expected_keep_alive is not None:
        prompt_config["keep_alive"] = expected_keep_alive
    all_rows: list[dict[str, object]] = []
    for index, (request_id, media_id) in enumerate(pending, 1):
        row = by_id[media_id]
        if row.get("original_split") != "DEV" or row.get("p2_internal_role") != "P2_DESIGN":
            raise SystemExit("P2L_STATUS=INVALID_NON_DEV_REQUEST")
        started = utc()
        conn.execute("UPDATE requests SET state='STARTED',started_at=? WHERE request_id=? AND state='NOT_STARTED'", (started, request_id))
        conn.commit()
        append_fsync(events_path, {"event": "REQUEST_STARTED", "request_id": request_id, "media_id": media_id, "timestamp_utc": started, "attempt": 1, "image_sha256": row["image_sha256"], "config_sha256": cfg_sha, "prompt_sha256": prompt_sha, "keep_alive": expected_keep_alive})
        processed = processed_dir / f"{media_id}.jpg"
        if not processed.exists():
            preprocess(Path(row["image_path"]), processed, cfg)
        image_bytes = processed.read_bytes()
        payload = {"model": cfg["model"], "prompt": prompt, "images": [base64.b64encode(image_bytes).decode("ascii")], "stream": False, "format": "json", "think": False, "options": cfg["options"]}
        if expected_keep_alive is not None:
            payload["keep_alive"] = expected_keep_alive
        request_start = time.time()
        http_code = None
        outer = {}
        outer_raw = ""
        error_type = ""
        try:
            req = urllib.request.Request(ENDPOINT + "/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=cfg["timeout_seconds"]) as response:
                http_code = response.status
                outer_raw = response.read().decode("utf-8")
            try:
                outer = json.loads(outer_raw)
            except Exception as exc:
                error_type = f"outer_json_failure:{exc}"
        except urllib.error.HTTPError as exc:
            http_code = exc.code
            error_type = f"HTTPError:{exc}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error_type = f"transport_failure:{type(exc).__name__}:{exc}"
        latency = time.time() - request_start
        wrapper = {"request_id": request_id, "media_id": media_id, "http_status": http_code, "outer_raw": outer_raw, "outer_json": outer, "outer_json_error": error_type if not outer else "", "request_payload_without_image": prompt_config, "image_sha256": row["image_sha256"], "processed_sha256": hashlib.sha256(image_bytes).hexdigest(), "processed_bytes": len(image_bytes), "timestamp_start_utc": started, "timestamp_end_utc": utc()}
        response_path = response_dir / f"{request_id}.json"
        atomic_json(response_path, wrapper)
        response_sha = sha256(response_path)
        state = "COMPLETED" if http_code == 200 and not error_type.startswith("transport_failure") else "FAILED_CONFIRMED"
        conn.execute("UPDATE requests SET state=?,completed_at=?,http_status=?,latency_seconds=?,response_sha256=?,error_type=? WHERE request_id=?", (state, utc(), http_code, latency, response_sha, error_type, request_id))
        conn.commit()
        append_fsync(events_path, {"event": "REQUEST_COMPLETED" if state == "COMPLETED" else "REQUEST_FAILED_CONFIRMED", "request_id": request_id, "media_id": media_id, "timestamp_utc": utc(), "http_status": http_code, "latency_seconds": latency, "response_sha256": response_sha, "error_type": error_type})
        parsed = parse_response(outer) if state == "COMPLETED" and http_code == 200 else {"response_nonempty": False, "json_ok": False, "schema_ok": False, "canonical_ok": False, "predicted_status": "", "evidence": "", "error_type": error_type or "http_failure"}
        outer = outer if isinstance(outer, dict) else {}
        all_rows.append({"request_id": request_id, "media_id": media_id, "probe": f"P2L_{args.probe}", "request_index": index, "split": "DEV", "sample_role": row["sample_role"], "scenario_id": row["scenario_id"], "group_id": row["group_id"], "image_sha256": row["image_sha256"], "processed_sha256": hashlib.sha256(image_bytes).hexdigest(), "processed_bytes": len(image_bytes), "predicted_status": parsed["predicted_status"], "evidence": parsed["evidence"], "response_nonempty": str(parsed["response_nonempty"]).lower(), "json_ok": str(parsed["json_ok"]).lower(), "schema_ok": str(parsed["schema_ok"]).lower(), "canonical_ok": str(parsed["canonical_ok"]).lower(), "http_ok": str(http_code == 200).lower(), "attempt_count": 1, "client_latency_seconds": f"{latency:.6f}", "total_duration_ns": outer.get("total_duration", ""), "load_duration_ns": outer.get("load_duration", ""), "prompt_eval_duration_ns": outer.get("prompt_eval_duration", ""), "eval_duration_ns": outer.get("eval_duration", ""), "prompt_eval_count": outer.get("prompt_eval_count", ""), "eval_count": outer.get("eval_count", ""), "done_reason": outer.get("done_reason", ""), "keep_alive": expected_keep_alive or "", "error_type": parsed["error_type"]})
        print(f"P2L_{args.probe}_PROGRESS={index}/{expected_n} latency={latency:.3f}s", flush=True)
        if args.probe in {"A", "B"} and index == expected_n // 2:
            capture_snapshot(f"P2L_{args.probe}", "midpoint")
    capture_snapshot(f"P2L_{args.probe}", "after")
    states = dict(conn.execute("SELECT state,COUNT(*) FROM requests GROUP BY state").fetchall())
    conn.close()
    fields = list(all_rows[0].keys()) if all_rows else ["request_id"]
    write_csv(run_dir / "predictions.csv", all_rows)
    protocol_failures = [row for row in all_rows if row["canonical_ok"] != "true"]
    write_csv(run_dir / "protocol_failures.csv", protocol_failures)
    # Raw response and request log are reconstructed from the durable response
    # wrappers after the ledger is complete, keeping one canonical row/order.
    raw_rows, logs = [], []
    for row in all_rows:
        wrapper = json.loads((response_dir / f"{row['request_id']}.json").read_text(encoding="utf-8"))
        raw_rows.append({"request_id": row["request_id"], "media_id": row["media_id"], "outer_json": wrapper.get("outer_json", {}), "response": wrapper.get("outer_json", {}).get("response", ""), "thinking": wrapper.get("outer_json", {}).get("thinking", "")})
        logs.append({"request_id": row["request_id"], "media_id": row["media_id"], "probe": row["probe"], "split": "DEV", "state": "COMPLETED" if row["http_ok"] == "true" else "FAILED_CONFIRMED", "request_payload_config": prompt_config, "timestamp_start_utc": wrapper.get("timestamp_start_utc"), "timestamp_end_utc": wrapper.get("timestamp_end_utc"), "attempt": 1, "http_code": wrapper.get("http_status"), "latency_seconds": float(row["client_latency_seconds"]), "response_sha256": sha256(response_dir / f"{row['request_id']}.json"), "image_sha256": row["image_sha256"], "error_type": row["error_type"]})
    (run_dir / "raw_responses.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in raw_rows), encoding="utf-8")
    (run_dir / "request_log.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in logs), encoding="utf-8")
    valid = [row for row in all_rows if row["canonical_ok"] == "true"]
    durations = {name: [float(row[f"{name}_duration_ns"]) / 1e9 for row in valid if row[f"{name}_duration_ns"] != ""] for name in ("total", "load", "prompt_eval", "eval")}
    client = [float(row["client_latency_seconds"]) for row in all_rows]
    summary = {"stage": "P2L_REMOTE_LATENCY_FORENSICS", "probe": f"P2L_{args.probe}", "run_id": run_id, "manifest_sha256": manifest_sha, "prompt_sha256": prompt_sha, "config_sha256": cfg_sha, "model": cfg["model"], "model_digest": cfg["model_digest"], "endpoint": ENDPOINT, "keep_alive": expected_keep_alive, "planned_requests": expected_n, "ledger_states": states, "holdout_requests": 0, "new_val_requests": 0, "protocol": {"request_count": len(all_rows), "http_success_rate": sum(r["http_ok"] == "true" for r in all_rows) / len(all_rows) if all_rows else None, "response_nonempty_rate": sum(r["response_nonempty"] == "true" for r in all_rows) / len(all_rows) if all_rows else None, "json_parse_success_rate": sum(r["json_ok"] == "true" for r in all_rows) / len(all_rows) if all_rows else None, "schema_success_rate": sum(r["schema_ok"] == "true" for r in all_rows) / len(all_rows) if all_rows else None, "canonical_prediction_success_rate": sum(r["canonical_ok"] == "true" for r in all_rows) / len(all_rows) if all_rows else None}, "latency_seconds": {"client": duration_stats(client), "total": duration_stats(durations["total"]), "load": duration_stats(durations["load"]), "prompt_eval": duration_stats(durations["prompt_eval"]), "eval": duration_stats(durations["eval"])}, "high_load_threshold_seconds": 5.0, "high_load_count": sum(v > 5.0 for v in durations["load"]), "execution_status": "COMPLETE" if states == {"COMPLETED": expected_n} else "INCOMPLETE", "raw_responses_sha256": sha256(run_dir / "raw_responses.jsonl"), "request_log_sha256": sha256(run_dir / "request_log.jsonl"), "predictions_sha256": sha256(run_dir / "predictions.csv"), "protocol_failures_sha256": sha256(run_dir / "protocol_failures.csv")}
    atomic_json(run_dir / "summary.json", summary)
    (run_dir / "summary.md").write_text("# " + summary["probe"] + " summary\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["execution_status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
