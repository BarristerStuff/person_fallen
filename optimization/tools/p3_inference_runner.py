#!/usr/bin/env python3
"""Durable, no-retry P3 inference runner.

The runner intentionally supports only the three in-scope streams:
* C3_BASELINE on the complete P2_DESIGN manifest;
* a frozen structured candidate on the 12-image DESIGN canary;
* the same frozen candidate on the already-used P2_SCREEN manifest.

It never reads or queues VAL/HOLDOUT and never falls back to ``thinking``.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from PIL import Image

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
CFG = P3 / "03_candidates/p3_request_config.json"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
FREEZE = P3 / "03_candidates/candidate_freeze.json"
ATTEST = P3 / "03_candidates/candidate_freeze_attestation.json"
P3_MODEL_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
P2_C3_PROMPT_SHA = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_atomic_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def append_fsync(handle, obj: object) -> None:
    handle.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def prompt_path(candidate: str) -> Path:
    if candidate == "C3_BASELINE":
        return P3 / "03_candidates/C3_BASELINE/C3_prompt.txt"
    if candidate == "S1_STRUCTURED":
        return P3 / "03_candidates/S1_STRUCTURED/S1_prompt.txt"
    if candidate == "OPTIONAL_S2":
        return P3 / "03_candidates/OPTIONAL_S2/S2_prompt.txt"
    raise ValueError(candidate)


def run_paths(phase: str, candidate: str) -> tuple[Path, Path]:
    if phase == "design":
        if candidate != "C3_BASELINE":
            raise SystemExit("P3_DESIGN_CANDIDATE_INVALID")
        return P3 / "01_c3_design_baseline", P2 / "01_internal_split/p2_design_manifest.csv"
    if phase == "canary":
        return P3 / "04_canary", P3 / "04_canary/canary_manifest.csv"
    if phase == "screen":
        return P3 / "05_screen" / candidate, P2 / "01_internal_split/p2_screen_manifest.csv"
    raise ValueError(phase)


def preprocess(source: Path, destination: Path, cfg: dict) -> None:
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((cfg["target_width"], cfg["target_height"]), RESAMPLE)
        canvas = Image.new(
            "RGB",
            (cfg["target_width"], cfg["target_height"]),
            tuple(cfg["letterbox_rgb"]),
        )
        canvas.paste(
            image,
            ((cfg["target_width"] - image.width) // 2,
             (cfg["target_height"] - image.height) // 2),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        canvas.save(
            tmp,
            "JPEG",
            quality=cfg["jpeg_quality"],
            optimize=cfg["jpeg_optimize"],
        )
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, destination)


def verify_config(cfg: dict) -> None:
    required = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
        "event_name": "person_fallen",
        "event_definition_version": "v2.0",
        "model": "qwen3.5:4b",
        "model_digest": P3_MODEL_DIGEST,
        "ollama_version": "0.23.2",
        "endpoint": "http://192.168.20.62:11434",
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 256},
        "concurrency": 1,
        "timeout_seconds": 120,
        "attempts_per_media": 1,
        "automatic_retry": False,
        "preprocess": "letterbox",
        "target_width": 448,
        "target_height": 336,
        "jpeg_quality": 70,
        "jpeg_optimize": True,
        "letterbox_rgb": [128, 128, 128],
        "parser_source": "response_only",
        "thinking_fallback": False,
    }
    if cfg != required:
        raise SystemExit("P3_RUN_BLOCKED_CONFIG_SEMANTICS")


def verify_rows(phase: str, rows: list[dict[str, str]], manifest: Path) -> None:
    expected = {"design": 190, "canary": 12, "screen": 120}[phase]
    if len(rows) != expected or len({row.get("media_id") for row in rows}) != expected:
        raise SystemExit(f"P3_{phase.upper()}_MANIFEST_SHAPE_INVALID")
    for row in rows:
        split = row.get("split") or row.get("original_split")
        if split == "HOLDOUT":
            raise SystemExit("P3_STATUS=INVALID_HOLDOUT_CONTAMINATION")
        if split == "VAL":
            raise SystemExit("P3_STATUS=INVALID_VAL_REQUEST")
        image = Path(row["image_path"])
        if not image.is_file() or sha(image) != row["image_sha256"]:
            raise SystemExit(f"P3_{phase.upper()}_IMAGE_HASH_MISMATCH")
    if phase == "design" and any(row.get("p2_internal_role") != "P2_DESIGN" for row in rows):
        raise SystemExit("P3_C3_DESIGN_NOT_P2_DESIGN_ONLY")
    if phase == "screen" and any(row.get("p2_internal_role") != "P2_SCREEN" for row in rows):
        raise SystemExit("P3_SCREEN_NOT_P2_SCREEN_ONLY")
    if phase == "canary" and any(row.get("canary_role") != "P3_STRUCTURED_CANARY" for row in rows):
        raise SystemExit("P3_CANARY_MANIFEST_INVALID")
    if manifest.name == "p2_design_manifest.csv" and sha(manifest) != "f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1":
        raise SystemExit("P3_DESIGN_MANIFEST_FREEZE_MISMATCH")
    if manifest.name == "p2_screen_manifest.csv" and sha(manifest) != "ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5":
        raise SystemExit("P3_SCREEN_MANIFEST_FREEZE_MISMATCH")


def verify_candidate_freeze(candidate: str, manifest: Path) -> None:
    if not FREEZE.is_file() or not ATTEST.is_file():
        raise SystemExit("P3_RUN_BLOCKED_CANDIDATE_FREEZE_MISSING")
    before = sha(FREEZE)
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    attestation = json.loads(ATTEST.read_text(encoding="utf-8"))
    if attestation.get("verification_result") != "PASS" or attestation.get("freeze_sha256") != before:
        raise SystemExit("P3_RUN_BLOCKED_CANDIDATE_FREEZE_ATTESTATION")
    entries = freeze.get("candidates", {})
    if candidate not in entries or not entries[candidate].get("candidate_eligible_for_screen"):
        raise SystemExit("P3_RUN_BLOCKED_CANDIDATE_NOT_FROZEN")
    if sha(manifest) != freeze.get("screen_manifest_sha256"):
        raise SystemExit("P3_RUN_BLOCKED_SCREEN_MANIFEST_BINDING")
    if sha(CFG) != freeze.get("config_sha256"):
        raise SystemExit("P3_RUN_BLOCKED_CONFIG_BINDING")
    if sha(Path(__file__)) != freeze.get("runner_sha256"):
        raise SystemExit("P3_RUN_BLOCKED_RUNNER_BINDING")
    if sha(prompt_path(candidate)) != entries[candidate].get("prompt_sha256"):
        raise SystemExit("P3_RUN_BLOCKED_PROMPT_BINDING")
    after = sha(FREEZE)
    if before != after:
        raise SystemExit("P3_RUN_BLOCKED_FREEZE_CHANGED")


def init_ledger(run_dir: Path, rows: list[dict[str, str]], manifest: Path, candidate: str, phase: str, prompt: Path, runner: Path, cfg: Path) -> sqlite3.Connection:
    db_path = run_dir / "request_ledger.sqlite3"
    new = not db_path.exists()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("CREATE TABLE IF NOT EXISTS metadata (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS requests ("
        "request_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, media_id TEXT UNIQUE NOT NULL, "
        "state TEXT NOT NULL, started_at TEXT, completed_at TEXT, attempt INTEGER NOT NULL, "
        "image_sha256 TEXT NOT NULL, config_sha256 TEXT NOT NULL, prompt_sha256 TEXT NOT NULL, "
        "http_status INTEGER, latency_seconds REAL, response_sha256 TEXT, error_type TEXT)"
    )
    if new:
        run_id = f"P3_{phase.upper()}_{candidate}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        metadata = {
            "run_id": run_id,
            "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
            "phase": phase,
            "candidate": candidate,
            "manifest_sha256": sha(manifest),
            "config_sha256": sha(cfg),
            "prompt_sha256": sha(prompt),
            "runner_sha256": sha(runner),
            "planned_requests": str(len(rows)),
            "automatic_retry": "false",
            "holdout_planned_requests": "0",
            "val_planned_requests": "0",
        }
        conn.executemany("INSERT INTO metadata(k,v) VALUES (?,?)", metadata.items())
        for ordinal, row in enumerate(rows, 1):
            conn.execute(
                "INSERT INTO requests(request_id,ordinal,media_id,state,attempt,image_sha256,config_sha256,prompt_sha256) VALUES (?,?,?,?,?,?,?,?)",
                (f"{run_id}_{ordinal:03d}", ordinal, row["media_id"], "NOT_STARTED", 1, row["image_sha256"], sha(cfg), sha(prompt)),
            )
        conn.commit()
    else:
        metadata = dict(conn.execute("SELECT k,v FROM metadata"))
        bindings = {
            "manifest_sha256": sha(manifest),
            "config_sha256": sha(cfg),
            "prompt_sha256": sha(prompt),
            "runner_sha256": sha(runner),
        }
        if any(metadata.get(k) != value for k, value in bindings.items()):
            raise SystemExit("P3_RUN_BLOCKED_EXISTING_LEDGER_BINDING")
    if conn.execute("SELECT count(*) FROM requests WHERE state='STARTED'").fetchone()[0]:
        raise SystemExit("P3_RUN_INCOMPLETE_INDETERMINATE_REQUEST")
    return conn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["design", "canary", "screen"])
    parser.add_argument("candidate", choices=["C3_BASELINE", "S1_STRUCTURED", "OPTIONAL_S2"])
    args = parser.parse_args()

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    verify_config(cfg)
    run_dir, manifest = run_paths(args.phase, args.candidate)
    if not manifest.is_file():
        raise SystemExit("P3_RUN_MANIFEST_MISSING")
    rows = load_csv(manifest)
    verify_rows(args.phase, rows, manifest)
    prompt = prompt_path(args.candidate)
    if not prompt.is_file():
        raise SystemExit("P3_RUN_PROMPT_MISSING")
    if args.phase == "design" and sha(prompt) != P2_C3_PROMPT_SHA:
        raise SystemExit("P3_C3_PROMPT_HASH_MISMATCH")
    if args.phase in {"canary", "screen"}:
        verify_candidate_freeze(args.candidate, manifest if args.phase == "screen" else P2 / "01_internal_split/p2_screen_manifest.csv")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "responses").mkdir(exist_ok=True)
    (run_dir / "processed_448x336").mkdir(exist_ok=True)
    runner = Path(__file__)
    conn = init_ledger(run_dir, rows, manifest, args.candidate, args.phase, prompt, runner, CFG)
    pending = conn.execute(
        "SELECT request_id,ordinal,media_id FROM requests WHERE state='NOT_STARTED' ORDER BY ordinal"
    ).fetchall()
    by_id = {row["media_id"]: row for row in rows}
    events_path = run_dir / "request_events.jsonl"
    events = events_path.open("a", encoding="utf-8")
    prompt_text = prompt.read_text(encoding="utf-8")
    for index, (request_id, ordinal, media_id) in enumerate(pending, 1):
        row = by_id[media_id]
        started_at = utc()
        conn.execute(
            "UPDATE requests SET state='STARTED',started_at=? WHERE request_id=? AND state='NOT_STARTED'",
            (started_at, request_id),
        )
        conn.commit()
        append_fsync(events, {
            "event": "REQUEST_STARTED",
            "request_id": request_id,
            "ordinal": ordinal,
            "media_id": media_id,
            "timestamp_utc": started_at,
            "attempt": 1,
            "image_sha256": row["image_sha256"],
            "config_sha256": sha(CFG),
            "prompt_sha256": sha(prompt),
            "split": row.get("split") or row.get("original_split"),
        })
        processed = run_dir / "processed_448x336" / f"{media_id}.jpg"
        try:
            preprocess(Path(row["image_path"]), processed, cfg)
        except Exception as exc:
            error_text = type(exc).__name__ + ": " + str(exc)
            conn.execute(
                "UPDATE requests SET state='FAILED_CONFIRMED',completed_at=?,error_type=? WHERE request_id=?",
                (utc(), error_text, request_id),
            )
            conn.commit()
            append_fsync(events, {"event": "REQUEST_FAILED_CONFIRMED", "request_id": request_id, "media_id": media_id, "timestamp_utc": utc(), "error_type": error_text})
            continue

        payload = {
            "model": cfg["model"],
            "prompt": prompt_text,
            "images": [base64.b64encode(processed.read_bytes()).decode("ascii")],
            "stream": False,
            "format": "json",
            "think": False,
            "options": cfg["options"],
        }
        payload_without_image = {key: value for key, value in payload.items() if key != "images"}
        request_started_clock = time.monotonic()
        try:
            req = request.Request(
                cfg["endpoint"] + "/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=cfg["timeout_seconds"]) as response:
                raw = response.read().decode("utf-8")
                code = response.status
            try:
                outer = json.loads(raw)
                outer_json_error = ""
            except Exception as exc:
                outer = {}
                outer_json_error = type(exc).__name__ + ": " + str(exc)
            ended_at = utc()
            latency = time.monotonic() - request_started_clock
            wrapper = {
                "request_id": request_id,
                "ordinal": ordinal,
                "media_id": media_id,
                "split": row.get("split") or row.get("original_split"),
                "request_payload_without_image": payload_without_image,
                "image_sha256": row["image_sha256"],
                "prompt_sha256": sha(prompt),
                "config_sha256": sha(CFG),
                "timestamp_start_utc": started_at,
                "timestamp_end_utc": ended_at,
                "http_status": code,
                "outer_raw": raw,
                "outer_json": outer,
                "outer_json_error": outer_json_error,
            }
            response_path = run_dir / "responses" / f"{request_id}.json"
            write_atomic_json(response_path, wrapper)
            response_sha = sha(response_path)
            conn.execute(
                "UPDATE requests SET state='COMPLETED',completed_at=?,http_status=?,latency_seconds=?,response_sha256=?,error_type=? WHERE request_id=?",
                (ended_at, code, latency, response_sha, "" if code == 200 else f"HTTP_STATUS_{code}", request_id),
            )
            conn.commit()
            append_fsync(events, {
                "event": "REQUEST_COMPLETED",
                "request_id": request_id,
                "media_id": media_id,
                "timestamp_utc": ended_at,
                "http_status": code,
                "latency_seconds": latency,
                "response_sha256": response_sha,
            })
        except error.HTTPError as exc:
            latency = time.monotonic() - request_started_clock
            error_text = f"HTTPError: {exc}"
            conn.execute(
                "UPDATE requests SET state='FAILED_CONFIRMED',completed_at=?,http_status=?,latency_seconds=?,error_type=? WHERE request_id=?",
                (utc(), exc.code, latency, error_text, request_id),
            )
            conn.commit()
            append_fsync(events, {"event": "REQUEST_FAILED_CONFIRMED", "request_id": request_id, "media_id": media_id, "timestamp_utc": utc(), "http_status": exc.code, "latency_seconds": latency, "error_type": error_text})
        except (error.URLError, TimeoutError, KeyboardInterrupt) as exc:
            error_text = type(exc).__name__ + ": " + str(exc)
            append_fsync(events, {"event": "REQUEST_INTERRUPTED_OR_UNKNOWN", "request_id": request_id, "media_id": media_id, "timestamp_utc": utc(), "error_type": error_text})
            events.close()
            conn.close()
            raise SystemExit("P3_RUN_INCOMPLETE_INDETERMINATE_REQUEST")
        if index % 10 == 0 or index == len(pending):
            print(f"P3_{args.phase.upper()}_{args.candidate}_PROGRESS={index}/{len(pending)}", flush=True)
    events.close()
    states = dict(conn.execute("SELECT state,count(*) FROM requests GROUP BY state"))
    conn.close()
    print(json.dumps({"phase": args.phase, "candidate": args.candidate, "ledger_states": states, "new_requests": len(pending), "holdout_requests": 0, "val_requests": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
