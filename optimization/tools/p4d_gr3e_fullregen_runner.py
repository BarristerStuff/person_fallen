#!/usr/bin/env python3
"""Authorized P4D_GR3E full-regeneration runner.

This runner is deliberately single-threaded and outer-retry-free.  It writes
only the authorized continuation revision and the new GR3 batch image files;
the preparation batch metadata files (README, generation_attempts.csv, and
generation_state.json) remain immutable.  A slot is durably marked STARTED in
SQLite before its one CLI invocation.  An unresolved STARTED slot is never
resent automatically and becomes COMPLETION_UNKNOWN on the next inspection.

Commands:
    init, smoke, ramp1, ramp2, bulk, status

QA, semantic review, formal ingest, C3, NEW_VAL, and HOLDOUT are intentionally
outside this runner and remain blocked until a later, separately gated stage.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation" / "gr3_fullregen"
CONT = GR3 / "06_execution" / "authorized_20260827_01"
PRE = CONT / "00_preflight"
AUTH = CONT / "01_authorization"
RUNNER_DIR = CONT / "02_runner"
LEDGER_DIR = CONT / "03_ledger"
RAW_LOG_DIR = CONT / "04_raw_responses"
CHECKPOINT_DIR = CONT / "05_checkpoints"
QA_DIR = CONT / "06_full_qa"
REVIEW_DIR = CONT / "07_human_review_package"

DB = LEDGER_DIR / "gr3e_execution.sqlite3"
LEDGER_CSV = LEDGER_DIR / "execution_ledger.csv"
REQUEST_LOG = CONT / "request_log.jsonl"
RAW_RESPONSES = CONT / "raw_responses.jsonl"
RUN_CONFIG = RUNNER_DIR / "run_config.json"
STOP_MARKER = CHECKPOINT_DIR / "global_stop.json"
LOCK_PATH = RUNNER_DIR / ".runner.lock"

MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
RAW_DIR = BATCH / "generated_raw"
FINAL_DIR = BATCH / "final"
METADATA_DIR = BATCH / "metadata"
DATASET_VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")

PREP = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
PREP_SIDECAR = PREP.with_name(PREP.name + ".sha256")
PREV_TF = GR3 / "06_execution" / "freeze" / "p4d_gr3e_terminal_freeze.json"
PREV_TF_SIDECAR = PREV_TF.with_name(PREV_TF.name + ".sha256")
PREFLIGHT = PRE / "authorized_runtime_preflight.json"
ATTESTATION = AUTH / "full_regen_authorization_attestation.json"

PREP_SHA = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
PREV_TF_SHA = "8ff93df4e33d670ab626fc0584d0cf27f0e5bbddd0d216dbdd821adbfd11ade1"
MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
FINAL_SIZE = (1920, 1080)
NATIVE_SIZE = "1536x1024"
QUALITY = "medium"
MODEL = "gpt-5.4"
PROVIDER = "codex"
REVISION_ID = "P4D_FULLREGEN_CODEX_PROFILE2_20260827_01"
BATCH_ID = "batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(value if value.endswith("\n") else value + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sanitize(text: str) -> str:
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{20,}", r"\1<REDACTED>", text)
    return text


def parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"ok": False, "raw_json": value}
    except json.JSONDecodeError:
        return {"ok": False, "parse_error": True, "raw_stdout": sanitize(text)}


def nested_values(value: Any, keys: set[str]) -> list[Any]:
    result: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and child not in (None, ""):
                result.append(child)
            result.extend(nested_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            result.extend(nested_values(child, keys))
    return result


def parse_http_status(payload: dict[str, Any], returncode: int | None) -> str:
    texts = []
    for item in nested_values(payload, {"message", "detail", "error", "stderr", "raw_stdout"}):
        texts.append(str(item))
    text = " ".join(texts)
    match = re.search(r"\bHTTP\s*(?:status\s*)?(\d{3})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b(429|401|403|5\d\d)\b", text)
    if match:
        return match.group(1)
    return "200" if returncode == 0 and payload.get("ok") is True else "unknown"


def parse_error(payload: dict[str, Any]) -> tuple[str, str]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        if payload.get("parse_error"):
            return "invalid_provider_json", "provider stdout was not valid JSON"
        return "", ""
    detail = error.get("detail", "")
    nested: dict[str, Any] = {}
    if isinstance(detail, str):
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                nested = parsed
        except json.JSONDecodeError:
            pass
    code = str(nested.get("code") or error.get("code") or "provider_error")
    message = str(nested.get("message") or error.get("message") or "provider error")
    return code, sanitize(message)


def fsync_path(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def atomic_move(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fsync_path(source)
    os.replace(source, target)
    directory_fd = os.open(str(target.parent), os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def verify_and_convert(raw_temp: Path, final_temp: Path) -> dict[str, Any]:
    # verify() must be called immediately after open(), then reopen for load.
    with Image.open(raw_temp) as image:
        image.verify()
    with Image.open(raw_temp) as image:
        image.load()
        native_width, native_height = image.size
        if native_width <= 0 or native_height <= 0:
            raise ValueError("invalid native dimensions")
        rgb = image.convert("RGB")
        target_ratio = FINAL_SIZE[0] / FINAL_SIZE[1]
        native_ratio = native_width / native_height
        if native_ratio > target_ratio:
            crop_width = int(round(native_height * target_ratio))
            left = max(0, (native_width - crop_width) // 2)
            crop_box = (left, 0, left + crop_width, native_height)
        elif native_ratio < target_ratio:
            crop_height = int(round(native_width / target_ratio))
            top = max(0, (native_height - crop_height) // 2)
            crop_box = (0, top, native_width, top + crop_height)
        else:
            crop_box = (0, 0, native_width, native_height)
        cropped = rgb.crop(crop_box)
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        final_image = cropped.resize(FINAL_SIZE, resampling)
        final_temp.parent.mkdir(parents=True, exist_ok=True)
        final_image.save(final_temp, format="PNG")
    with Image.open(final_temp) as image:
        image.verify()
    with Image.open(final_temp) as image:
        image.load()
        final_width, final_height = image.size
    if (final_width, final_height) != FINAL_SIZE:
        raise ValueError(f"final dimensions {(final_width, final_height)} != {FINAL_SIZE}")
    return {
        "native_width": native_width,
        "native_height": native_height,
        "native_aspect_ratio": native_width / native_height,
        "crop_box": list(crop_box),
        "final_width": final_width,
        "final_height": final_height,
        "resize_method": "Pillow_LANCZOS",
    }


def dataset_snapshot(label: str) -> dict[str, Any]:
    command = ["python3", str(DATASET_VALIDATOR), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
    payload = parse_json(proc.stdout)
    counts: dict[str, int] = {}
    hashes: dict[str, str | None] = {}
    refs: dict[str, list[int]] = {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        refs[name] = [index for index, line in enumerate(lines, start=1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()][:50]
    value = {
        "label": label,
        "captured_at": now(),
        "validator_command": command,
        "validator_returncode": proc.returncode,
        "validator": payload,
        "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]},
        "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": refs,
        "p4d_reference_hits_total": sum(len(rows) for rows in refs.values()),
        "formal_dataset_mutation_by_gr3e": False,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", value)
    return value


def verify_parent_and_preflight() -> dict[str, Any]:
    prep_actual = sha256_file(PREP)
    prep_sidecar = PREP_SIDECAR.read_text(encoding="utf-8").split()[0] if PREP_SIDECAR.exists() else None
    prev_actual = sha256_file(PREV_TF)
    prev_sidecar = PREV_TF_SIDECAR.read_text(encoding="utf-8").split()[0] if PREV_TF_SIDECAR.exists() else None
    prep = read_json(PREP, {}) or {}
    att = read_json(ATTESTATION, {}) or {}
    preflight = read_json(PREFLIGHT, {}) or {}
    checks = {
        "preparation_freeze": prep_actual == PREP_SHA and prep_sidecar == prep_actual,
        "previous_no_auth_freeze": prev_actual == PREV_TF_SHA and prev_sidecar == prev_actual,
        "preparation_authorized_false_unchanged": prep.get("terminal", {}).get("FULL_REGEN_AUTHORIZED") is False,
        "authorization_attestation": att.get("authorization_present") is True and att.get("authorization_scope") == "440_full_regeneration" and att.get("current_codex_profile_explicit") is True and att.get("GR1_images_excluded") is True and att.get("retry_risk_accepted") is True and att.get("quota_risk_accepted") is True and att.get("unknown_cost_risk_accepted") is True,
        "preflight_identity": preflight.get("identity_gate") is True and preflight.get("profile_continuity_match") is True,
        "preflight_runtime": preflight.get("runtime_identity_gate") is True,
        "preflight_provider_ready": preflight.get("provider_ready_gate") is True,
        "manifest_sha": sha256_file(MANIFEST) == MANIFEST_SHA,
        "wrapper_sha": sha256_file(CLI) == WRAPPER_SHA,
    }
    value = {
        "verified_at": now(),
        "checks": checks,
        "all_pass": all(checks.values()),
        "preparation_freeze_sha256": prep_actual,
        "previous_terminal_freeze_sha256": prev_actual,
        "authorization_attestation_sha256": sha256_file(ATTESTATION),
        "preflight_path": str(PREFLIGHT),
        "preflight_summary": {key: preflight.get(key) for key in ("provider", "request_model", "generation_backend", "auth_ready", "session_ready", "endpoint_reachable", "safe_profile_fingerprint_current", "safe_profile_fingerprint_preparation", "profile_continuity_match", "no_retry_guarantee", "native_retry_policy_preparation", "wrapper_sha256_actual", "binary_sha256_actual", "runtime_version")},
    }
    write_json(PRE / "runner_gate_check.json", value)
    if not value["all_pass"]:
        raise RuntimeError(f"runner gate failed: {checks}")
    return value


def batch_zero_check() -> dict[str, Any]:
    images = [str(p) for p in BATCH.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES] if BATCH.exists() else []
    links = [str(p) for p in BATCH.rglob("*") if p.is_symlink()] if BATCH.exists() else []
    value = {"image_count": len(images), "symlink_count": len(links), "images": images[:20], "symlinks": links[:20], "verified_at": now()}
    write_json(PRE / "authorized_batch_initial_check.json", value)
    if links:
        raise RuntimeError("new batch contains symlinks")
    if images:
        raise RuntimeError("new batch contains images before authorized continuation init")
    return value


def load_manifest() -> list[dict[str, str]]:
    rows = read_csv(MANIFEST)
    if len(rows) != 440 or len({row.get("prompt_id") for row in rows}) != 440:
        raise RuntimeError("manifest cardinality mismatch")
    role_counts = Counter(row.get("target_role") for row in rows)
    split_counts = Counter(row.get("planned_internal_split") for row in rows)
    if role_counts != Counter({"hard_negative": 300, "positive": 100, "ordinary_negative": 40}):
        raise RuntimeError(f"role counts changed: {role_counts}")
    if split_counts != Counter({"NEW_DESIGN": 265, "NEW_SCREEN": 175}):
        raise RuntimeError(f"split counts changed: {split_counts}")
    for row in rows:
        path = Path(row["original_prompt_path"])
        if not path.exists() or sha256_file(path) != row.get("prompt_sha256"):
            raise RuntimeError(f"prompt bytes changed: {row.get('prompt_id')}")
    return rows


def connect_db() -> sqlite3.Connection:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slots (
          prompt_id TEXT PRIMARY KEY,
          ordinal INTEGER NOT NULL UNIQUE,
          group_id TEXT NOT NULL,
          variant_id TEXT NOT NULL,
          target_role TEXT NOT NULL,
          target_event_label TEXT NOT NULL,
          taxonomy TEXT NOT NULL,
          planned_split TEXT NOT NULL,
          prompt_path TEXT NOT NULL,
          prompt_sha256 TEXT NOT NULL,
          state TEXT NOT NULL,
          phase TEXT,
          invocation_count INTEGER NOT NULL DEFAULT 0,
          observed_native_retry_count TEXT,
          request_id TEXT,
          provider_request_id TEXT,
          request_started_at TEXT,
          request_finished_at TEXT,
          http_status TEXT,
          error_code TEXT,
          error_message_safe TEXT,
          raw_path TEXT,
          final_path TEXT,
          raw_sha256 TEXT,
          final_sha256 TEXT,
          native_width INTEGER,
          native_height INTEGER,
          final_width INTEGER,
          final_height INTEGER,
          crop_box TEXT,
          latency_seconds REAL,
          metadata_path TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          prompt_id TEXT,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          captured_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def initialize_db(rows: list[dict[str, str]], gate: dict[str, Any], before: dict[str, Any]) -> None:
    conn = connect_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
        if existing == 0:
            for ordinal, row in enumerate(rows):
                conn.execute("""
                    INSERT INTO slots(prompt_id,ordinal,group_id,variant_id,target_role,target_event_label,taxonomy,planned_split,prompt_path,prompt_sha256,state,observed_native_retry_count)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (row["prompt_id"], ordinal, row["group_id"], row["variant_id"], row["target_role"], row["target_event_label"], row["taxonomy"], row["planned_internal_split"], row["original_prompt_path"], row["prompt_sha256"], "NOT_STARTED", "UNKNOWN_IF_NOT_EXPOSED"))
            conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(NULL,?,?,?)", ("INIT", json.dumps({"gate": gate, "dataset_before": before["counts"]}, ensure_ascii=False, sort_keys=True), now()))
            conn.commit()
        elif existing != 440:
            raise RuntimeError(f"existing SQLite slot count is {existing}, expected 440")
    finally:
        conn.close()
    if not LEDGER_CSV.exists():
        write_text(LEDGER_CSV, "logical_slot_id,ordinal,group_id,variant_id,planned_split,target_role,phase,state,invocation_count,observed_native_retry_count,provider_request_id,http_status,error_code,raw_sha256,final_sha256,latency_seconds,timestamp\n")
    config = {
        "stage": "P4D_GR3E_FULL_REGEN_EXECUTION",
        "continuation_revision": "authorized_20260827_01",
        "provider": PROVIDER,
        "model": MODEL,
        "generation_backend": "image_generation",
        "revision_id": REVISION_ID,
        "batch_id": BATCH_ID,
        "batch_path": str(BATCH),
        "manifest_path": str(MANIFEST),
        "manifest_sha256": sha256_file(MANIFEST),
        "preparation_freeze_sha256": sha256_file(PREP),
        "previous_no_auth_terminal_freeze_sha256": sha256_file(PREV_TF),
        "authorization_attestation_sha256": sha256_file(ATTESTATION),
        "provider_preflight_sha256": sha256_file(PREFLIGHT),
        "wrapper_sha256": sha256_file(CLI),
        "binary_sha256": (read_json(PREFLIGHT, {}) or {}).get("binary_sha256_actual"),
        "native_size_requested": NATIVE_SIZE,
        "quality": QUALITY,
        "final_size": list(FINAL_SIZE),
        "concurrency": 1,
        "outer_retry": False,
        "recovery_pass": False,
        "holdout_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
        "created_at": now(),
    }
    write_json(RUN_CONFIG, config)


def db_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT state,COUNT(*) AS n FROM slots GROUP BY state").fetchall()
    counts = {str(row["state"]): int(row["n"]) for row in rows}
    counts["TOTAL"] = sum(counts.values())
    counts["SUCCESS"] = counts.get("SUCCESS", 0)
    counts["OUTSTANDING"] = 440 - counts["SUCCESS"]
    return counts


def unresolved_started(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM slots WHERE state='STARTED' ORDER BY ordinal").fetchall()


def assert_resumable(conn: sqlite3.Connection) -> None:
    unresolved = unresolved_started(conn)
    if unresolved:
        for row in unresolved:
            conn.execute("UPDATE slots SET state='COMPLETION_UNKNOWN', error_code=?, error_message_safe=?, request_finished_at=? WHERE prompt_id=?", ("completion_unknown", "process restarted with STARTED slot lacking durable provider result", now(), row["prompt_id"]))
            conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (row["prompt_id"], "COMPLETION_UNKNOWN", json.dumps({"reason": "STARTED without durable result"}, ensure_ascii=False), now()))
        conn.commit()
        write_json(STOP_MARKER, {"status": "GLOBAL_STOP", "reason": "COMPLETION_UNKNOWN", "prompt_ids": [row["prompt_id"] for row in unresolved], "captured_at": now()})
        raise RuntimeError("completion unknown; no automatic resend is allowed")
    marker = read_json(STOP_MARKER, {}) or {}
    if marker.get("status") == "GLOBAL_STOP":
        raise RuntimeError(f"global stop already recorded: {marker.get('reason')}")
    bad = conn.execute("SELECT prompt_id,state FROM slots WHERE state IN ('FAILED_CONFIRMED','COMPLETION_UNKNOWN') ORDER BY ordinal").fetchall()
    if bad:
        raise RuntimeError(f"prior failed/completion-unknown slot prevents continuation: {[dict(row) for row in bad]}")


def phase_rows(conn: sqlite3.Connection, phase: str) -> list[sqlite3.Row]:
    success = conn.execute("SELECT COUNT(*) FROM slots WHERE state='SUCCESS'").fetchone()[0]
    if phase == "SMOKE":
        return conn.execute("SELECT * FROM slots WHERE ordinal=0").fetchall()
    if phase == "RAMP1":
        return conn.execute("SELECT * FROM slots WHERE state='NOT_STARTED' ORDER BY ordinal LIMIT 5").fetchall()
    if phase == "RAMP2":
        return conn.execute("SELECT * FROM slots WHERE state='NOT_STARTED' ORDER BY ordinal LIMIT 10").fetchall()
    if phase == "BULK":
        return conn.execute("SELECT * FROM slots WHERE state='NOT_STARTED' ORDER BY ordinal").fetchall()
    raise ValueError(phase)


def stage_status_path(phase: str) -> Path:
    return CHECKPOINT_DIR / f"{phase.lower()}_status.json"


def extract_provider_id(payload: dict[str, Any]) -> str:
    values = nested_values(payload, {"provider_request_id", "request_id", "id"})
    return str(values[0]) if values else "unknown"


def extract_seed(payload: dict[str, Any]) -> str:
    values = nested_values(payload, {"seed"})
    return str(values[0]) if values else "unknown"


def append_ledger_row(row: sqlite3.Row) -> None:
    new_file = not LEDGER_CSV.exists() or LEDGER_CSV.stat().st_size == 0
    with LEDGER_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["logical_slot_id","ordinal","group_id","variant_id","planned_split","target_role","phase","state","invocation_count","observed_native_retry_count","provider_request_id","http_status","error_code","raw_sha256","final_sha256","latency_seconds","timestamp"], lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerow({
            "logical_slot_id": row["prompt_id"], "ordinal": row["ordinal"], "group_id": row["group_id"], "variant_id": row["variant_id"], "planned_split": row["planned_split"], "target_role": row["target_role"], "phase": row["phase"], "state": row["state"], "invocation_count": row["invocation_count"], "observed_native_retry_count": row["observed_native_retry_count"], "provider_request_id": row["provider_request_id"], "http_status": row["http_status"], "error_code": row["error_code"], "raw_sha256": row["raw_sha256"], "final_sha256": row["final_sha256"], "latency_seconds": row["latency_seconds"], "timestamp": row["request_finished_at"],
        })
        handle.flush()
        os.fsync(handle.fileno())


def invoke_slot(conn: sqlite3.Connection, row: sqlite3.Row, phase: str) -> dict[str, Any]:
    prompt_path = Path(row["prompt_path"])
    prompt = prompt_path.read_text(encoding="utf-8").rstrip("\n")
    if sha256_file(prompt_path) != row["prompt_sha256"]:
        raise RuntimeError(f"prompt hash changed before request: {row['prompt_id']}")
    request_id = f"P4D_GR3E_{phase}_{int(row['ordinal']) + 1:04d}_{row['prompt_id']}"
    raw_target = RAW_DIR / f"{row['prompt_id']}.png"
    final_target = FINAL_DIR / f"{row['prompt_id']}.png"
    raw_temp = RAW_DIR / f".{row['prompt_id']}.{request_id}.tmp.png"
    final_temp = FINAL_DIR / f".{row['prompt_id']}.{request_id}.tmp.png"
    for path in (raw_temp, final_temp):
        if path.exists():
            raise RuntimeError(f"unexpected stale temporary output exists: {path}")
    start_time = now()
    start_mono = time.monotonic()
    conn.execute("UPDATE slots SET state='STARTED',phase=?,invocation_count=1,request_id=?,request_started_at=?,observed_native_retry_count=? WHERE prompt_id=?", (phase, request_id, start_time, "UNKNOWN_IF_NOT_EXPOSED", row["prompt_id"]))
    conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (row["prompt_id"], "STARTED_DURABLE", json.dumps({"phase": phase, "request_id": request_id, "outer_retry": False}, ensure_ascii=False), now()))
    conn.commit()
    command = ["node", str(CLI), "--json", "--json-events", "--provider", PROVIDER, "images", "generate", "--model", MODEL, "--prompt", prompt, "--out", str(raw_temp), "--format", "png", "--size", NATIVE_SIZE, "--quality", QUALITY]
    returncode: int | None = None
    stdout = ""
    stderr = ""
    timeout = False
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=1800)
        returncode = proc.returncode
        stdout = sanitize(proc.stdout)
        stderr = sanitize(proc.stderr)
        payload = parse_json(stdout)
    except subprocess.TimeoutExpired as exc:
        timeout = True
        stdout = sanitize(exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = sanitize(exc.stderr or "") if isinstance(exc.stderr, str) else ""
        payload = {"ok": False, "error": {"code": "timeout", "message": "generation timeout"}}
    except Exception as exc:
        payload = {"ok": False, "error": {"code": "runner_exception", "message": sanitize(str(exc))}}
    elapsed = time.monotonic() - start_mono
    finish_time = now()
    http_status = parse_http_status(payload, returncode)
    error_code, error_message = parse_error(payload)
    provider_request_id = extract_provider_id(payload)
    seed = extract_seed(payload)
    raw_sha = None
    final_sha = None
    qa: dict[str, Any] = {}
    state = "FAILED_CONFIRMED"
    if timeout:
        state = "COMPLETION_UNKNOWN"
        error_code = "timeout"
        error_message = "provider completion cannot be established after timeout"
    elif returncode == 0 and payload.get("ok") is True and raw_temp.exists() and raw_temp.stat().st_size > 0:
        try:
            qa = verify_and_convert(raw_temp, final_temp)
            atomic_move(raw_temp, raw_target)
            atomic_move(final_temp, final_target)
            raw_sha = sha256_file(raw_target)
            final_sha = sha256_file(final_target)
            state = "SUCCESS"
        except Exception as exc:
            state = "FAILED_CONFIRMED"
            error_code = "mechanical_image_failure"
            error_message = sanitize(str(exc))
    else:
        if raw_temp.exists():
            raw_temp.unlink()
    if final_temp.exists() and state != "SUCCESS":
        final_temp.unlink()
    response_record = {
        "request_id": request_id,
        "provider_request_id": provider_request_id,
        "provider": PROVIDER,
        "model": MODEL,
        "phase": phase,
        "ordinal": row["ordinal"],
        "prompt_id": row["prompt_id"],
        "group_id": row["group_id"],
        "planned_split": row["planned_split"],
        "prompt_sha256": row["prompt_sha256"],
        "request_payload_config": {"provider": PROVIDER, "model": MODEL, "generation_backend": "image_generation", "format": "png", "native_size": NATIVE_SIZE, "quality": QUALITY, "outer_retry": False, "reference_images": []},
        "command_redacted": ["node", "<gpt-image-2-skill>", "--json", "--json-events", "--provider", PROVIDER, "images", "generate", "--model", MODEL, "--prompt_sha256", row["prompt_sha256"], "--out", str(raw_target), "--format", "png", "--size", NATIVE_SIZE, "--quality", QUALITY],
        "request_started_at": start_time,
        "request_finished_at": finish_time,
        "returncode": returncode,
        "http_status": http_status,
        "outer_json": payload,
        "stdout": stdout,
        "stderr": stderr,
        "response": None,
        "thinking": None,
        "done": None,
        "done_reason": None,
        "eval_count": None,
        "native_retry_count": "UNKNOWN_IF_NOT_EXPOSED",
        "latency_seconds": elapsed,
        "seed": seed,
        "status": state,
        "error_code": error_code,
        "error_message_safe": error_message,
        "raw_path": str(raw_target) if state == "SUCCESS" else None,
        "final_path": str(final_target) if state == "SUCCESS" else None,
        "raw_sha256": raw_sha,
        "final_sha256": final_sha,
        "mechanical_qa": qa,
    }
    response_path = RAW_LOG_DIR / f"{request_id}.json"
    write_json(response_path, response_record)
    append_jsonl(RAW_RESPONSES, {"request_id": request_id, "prompt_id": row["prompt_id"], "phase": phase, "response_path": str(response_path), "outer_json": payload, "status": state})
    append_jsonl(REQUEST_LOG, response_record)
    metadata_path = METADATA_DIR / f"{row['prompt_id']}.json"
    write_json(metadata_path, {"provider": PROVIDER, "model": MODEL, "generation_backend": "image_generation", "revision_id": REVISION_ID, "batch_id": BATCH_ID, "prompt_id": row["prompt_id"], "prompt_sha256": row["prompt_sha256"], "group_id": row["group_id"], "planned_split": row["planned_split"], "target_role": row["target_role"], "taxonomy": row["taxonomy"], "request_id": request_id, "provider_request_id": provider_request_id, "seed": seed, "runtime_version": (read_json(PREFLIGHT, {}) or {}).get("runtime_version", {}).get("doctor_version"), "request_started_at": start_time, "request_finished_at": finish_time, "latency_seconds": elapsed, "status": state, "raw_path": str(raw_target) if state == "SUCCESS" else None, "final_path": str(final_target) if state == "SUCCESS" else None, "raw_sha256": raw_sha, "final_sha256": final_sha, "native_retry_count": "UNKNOWN_IF_NOT_EXPOSED", "mechanical_qa": qa})
    conn.execute("""
        UPDATE slots SET state=?,request_finished_at=?,provider_request_id=?,http_status=?,error_code=?,error_message_safe=?,raw_path=?,final_path=?,raw_sha256=?,final_sha256=?,native_width=?,native_height=?,final_width=?,final_height=?,crop_box=?,latency_seconds=?,metadata_path=? WHERE prompt_id=?
    """, (state, finish_time, provider_request_id, http_status, error_code, error_message, str(raw_target) if state == "SUCCESS" else None, str(final_target) if state == "SUCCESS" else None, raw_sha, final_sha, qa.get("native_width"), qa.get("native_height"), qa.get("final_width"), qa.get("final_height"), json.dumps(qa.get("crop_box")) if qa.get("crop_box") else None, elapsed, str(metadata_path), row["prompt_id"]))
    conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (row["prompt_id"], state, json.dumps({"phase": phase, "http_status": http_status, "error_code": error_code, "raw_sha256": raw_sha, "final_sha256": final_sha, "latency_seconds": elapsed}, ensure_ascii=False), now()))
    conn.commit()
    updated = conn.execute("SELECT * FROM slots WHERE prompt_id=?", (row["prompt_id"],)).fetchone()
    append_ledger_row(updated)
    if state != "SUCCESS":
        reason = "COMPLETION_UNKNOWN" if state == "COMPLETION_UNKNOWN" else (f"HTTP_{http_status}" if http_status in {"429", "401", "403"} else error_code or "provider_or_mechanical_failure")
        write_json(STOP_MARKER, {"status": "GLOBAL_STOP", "reason": reason, "prompt_id": row["prompt_id"], "phase": phase, "http_status": http_status, "error_code": error_code, "provider_request_id": provider_request_id, "captured_at": now()})
    return {"prompt_id": row["prompt_id"], "phase": phase, "state": state, "http_status": http_status, "error_code": error_code, "latency_seconds": elapsed, "raw_sha256": raw_sha, "final_sha256": final_sha, "mechanical_qa": qa, "request_id": request_id, "provider_request_id": provider_request_id}


def checkpoint(conn: sqlite3.Connection, phase: str, results: list[dict[str, Any]], stage_status: str) -> None:
    counts = db_counts(conn)
    payload = {
        "stage": phase,
        "status": stage_status,
        "captured_at": now(),
        "results": results,
        "logical_requests_total": conn.execute("SELECT COUNT(*) FROM slots WHERE invocation_count > 0").fetchone()[0],
        "logical_successes_total": counts.get("SUCCESS", 0),
        "logical_failures_total": counts.get("FAILED_CONFIRMED", 0),
        "completion_unknown_total": counts.get("COMPLETION_UNKNOWN", 0),
        "current_image_count": len([p for p in RAW_DIR.glob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]),
        "remaining_slots": counts.get("OUTSTANDING", 440),
        "last_http_status": results[-1].get("http_status") if results else None,
        "outer_retry": False,
        "native_retry_count": "UNKNOWN_IF_NOT_EXPOSED",
    }
    write_json(stage_status_path(phase), payload)
    write_json(CHECKPOINT_DIR / "latest_checkpoint.json", payload)


def run_phase(phase: str) -> int:
    gate = verify_parent_and_preflight()
    conn = connect_db()
    lock_handle = LOCK_PATH.open("a+")
    try:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another GR3E runner process holds the lock") from exc
        assert_resumable(conn)
        rows = phase_rows(conn, phase)
        if phase == "SMOKE" and conn.execute("SELECT state FROM slots WHERE ordinal=0").fetchone()[0] == "SUCCESS":
            checkpoint(conn, phase, [], "PASS_ALREADY_COMPLETE")
            return 0
        if phase != "SMOKE" and not rows:
            checkpoint(conn, phase, [], "NOT_NEEDED")
            return 0
        expected = {"SMOKE": 1, "RAMP1": 5, "RAMP2": 10, "BULK": len(rows)}[phase]
        if len(rows) != expected:
            raise RuntimeError(f"{phase} selection expected {expected}, got {len(rows)}")
        results: list[dict[str, Any]] = []
        for row in rows:
            result = invoke_slot(conn, row, phase)
            results.append(result)
            checkpoint(conn, phase, results, "IN_PROGRESS" if result["state"] == "SUCCESS" else "FAIL")
            if result["state"] != "SUCCESS":
                print(json.dumps({"stage": phase, "status": "FAIL", "result": result, "gate": gate}, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
                return 2
            print(json.dumps({"stage": phase, "status": "SUCCESS", "result": result, "counts": db_counts(conn)}, ensure_ascii=False, sort_keys=True), flush=True)
        checkpoint(conn, phase, results, "PASS")
        if phase == "SMOKE" and len(results) != 1:
            return 2
        print(json.dumps({"stage": phase, "status": "PASS", "requests": len(results), "successes": len(results), "counts": db_counts(conn)}, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        return 0
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
            conn.close()


def init_command() -> int:
    gate = verify_parent_and_preflight()
    batch_zero_check()
    before = dataset_snapshot("before_generation")
    if before["p4d_reference_hits_total"] != 0:
        raise RuntimeError("active dataset already contains P4D references")
    rows = load_manifest()
    initialize_db(rows, gate, before)
    print(json.dumps({"status": "INITIALIZED", "slots": len(rows), "dataset_before": before["counts"], "db": str(DB), "ledger": str(LEDGER_CSV), "outer_retry": False}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def status_command() -> int:
    conn = connect_db()
    try:
        counts = db_counts(conn)
        sample = [dict(row) for row in conn.execute("SELECT prompt_id,ordinal,state,phase,http_status,error_code FROM slots WHERE state!='SUCCESS' ORDER BY ordinal LIMIT 20").fetchall()]
        print(json.dumps({"status": "OK", "counts": counts, "sample_non_success": sample, "db": str(DB), "provider_requests": conn.execute("SELECT COUNT(*) FROM slots WHERE invocation_count>0").fetchone()[0], "holdout_requests": 0, "formal_ingest": False, "c3": False, "new_val": 0}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "smoke", "ramp1", "ramp2", "bulk", "status"))
    args = parser.parse_args()
    for directory in (CONT, PRE, AUTH, RUNNER_DIR, LEDGER_DIR, RAW_LOG_DIR, CHECKPOINT_DIR, QA_DIR, REVIEW_DIR, RAW_DIR, FINAL_DIR, METADATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if args.command == "init":
        return init_command()
    if args.command == "status":
        return status_command()
    return run_phase(args.command.upper())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
