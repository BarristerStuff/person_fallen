#!/usr/bin/env python3
"""One-shot direct HTTP runner for the P4D_EB1 EBOND lineage.

The runner is intentionally conservative.  It sends one POST for one logical
slot, uses no client/library/provider-wrapper retries, never follows redirects,
and stops after the first confirmed failure or completion-unknown result.  A
SQLite WAL ledger is committed before the request and after every durable
artifact.  It never performs ingest, C3, VAL, HOLDOUT, or semantic selection.

The only credential read is the existing user-managed EBOND provider config;
the key remains in memory and is never included in arguments, logs, reports,
or generated JSON.  The runner imports preparation constants solely to bind
itself to the already-frozen assets.
"""

from __future__ import annotations

import argparse
import base64
import csv
import fcntl
import hashlib
import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from prepare_ebond_lineage import (
    API_BASE,
    BATCH,
    CONFIG,
    DATASET_VALIDATOR,
    FINAL_SIZE,
    GENERATION_ENDPOINT,
    MANIFEST,
    MANIFEST_SHA,
    MODEL,
    NATIVE_SIZE,
    OPT,
    PROVIDER,
    QUALITY,
    REVISION,
    RUNNER,
    ASSET_HASHES,
    inspect_frozen_assets,
    sha256_bytes,
    sha256_file,
    write_json,
    write_text_atomic,
)


PREFLIGHT = OPT / "freeze/p4d_eb1_preflight_freeze.json"
PREFLIGHT_SIDECAR = PREFLIGHT.with_name(PREFLIGHT.name + ".sha256")
TERMINAL = OPT / "freeze/p4d_eb1_terminal_freeze.json"
TERMINAL_SIDECAR = TERMINAL.with_name(TERMINAL.name + ".sha256")
ORDER = OPT / "order/ebond_balanced_execution_order.csv"
RUN_CONFIG = OPT / "execution/run_config.json"
REQUEST_LOG = OPT / "execution/request_log.jsonl"
RAW_LOG = OPT / "execution/raw_responses.jsonl"
STATUS_PATH = OPT / "execution/execution_status.json"
DB = OPT / "ledger/p4d_eb1_execution.sqlite3"
LEDGER_CSV = OPT / "ledger/execution_ledger.csv"
LOCK_PATH = OPT / "execution/.runner.lock"
ACTIVE_CREDENTIAL = OPT / "config/active_credential_freeze.json"
STOP_MARKER = OPT / "checkpoints/global_stop.json"
LATEST_CHECKPOINT = OPT / "checkpoints/latest_checkpoint.json"
RAW_RESPONSE_DIR = BATCH / "metadata/raw_provider_responses"
RAW_DIR = BATCH / "generated_raw"
FINAL_DIR = BATCH / "final"
TIMEOUT_SECONDS = 900
MAX_RESPONSE_BYTES = 80 * 1024 * 1024
SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_order() -> list[dict[str, str]]:
    with ORDER.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 440 or len({row.get("prompt_id") for row in rows}) != 440:
        raise RuntimeError("execution order is not exactly 440 unique slots")
    if any(row.get("planned_internal_split") == "HOLDOUT" for row in rows):
        raise RuntimeError("HOLDOUT row found in execution order")
    for expected, row in enumerate(rows, 1):
        if int(row.get("order_index", "0")) != expected:
            raise RuntimeError("execution order index is not contiguous")
        if row.get("logical_request_id") != f"P4D_EB1_{expected:04d}":
            raise RuntimeError("logical request id does not match frozen order")
    return rows


def safe_text(text: str, key: str | None = None) -> str:
    if key:
        text = text.replace(key, "<REDACTED>")
    patterns = [
        (r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,}\"']+", r"\1<REDACTED>"),
        (r"(?i)(access[_-]?token\s*[:=]\s*)[^\s,}\"']+", r"\1<REDACTED>"),
        (r"(?i)(bearer\s+)[A-Za-z0-9._-]{20,}", r"\1<REDACTED>"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def fsync_directory(path: Path) -> None:
    fd = os.open(str(path), os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def verify_frozen_preflight() -> dict[str, Any]:
    if TERMINAL.exists():
        raise RuntimeError(f"terminal freeze already exists; sealed run cannot be resumed: {TERMINAL}")
    if not PREFLIGHT.is_file() or not PREFLIGHT_SIDECAR.is_file():
        raise RuntimeError("p4d_eb1_preflight_freeze.json and sidecar are required before provider requests")
    preflight = read_json(PREFLIGHT)
    expected_sidecar = PREFLIGHT_SIDECAR.read_text(encoding="utf-8").split()[0]
    actual_preflight_sha = sha256_file(PREFLIGHT)
    if expected_sidecar != actual_preflight_sha:
        raise RuntimeError("preflight freeze sidecar mismatch")
    if preflight.get("preflight_status") != "FROZEN_BEFORE_PROVIDER_REQUEST":
        raise RuntimeError("preflight status is not frozen-before-provider-request")
    if preflight.get("provider", {}).get("provider") != PROVIDER or preflight.get("provider", {}).get("model") != MODEL:
        raise RuntimeError("preflight provider/model binding mismatch")
    if preflight.get("provider", {}).get("generation_endpoint") != GENERATION_ENDPOINT:
        raise RuntimeError("preflight endpoint binding mismatch")
    if preflight.get("frozen_full_manifest", {}).get("sha256") != MANIFEST_SHA or sha256_file(MANIFEST) != MANIFEST_SHA:
        raise RuntimeError("frozen full manifest mismatch")
    current_assets = inspect_frozen_assets()
    for path_text, expected in ASSET_HASHES.items():
        if not current_assets.get(path_text, {}).get("match") or current_assets[path_text].get("actual_sha256") != expected:
            raise RuntimeError(f"frozen dependency changed after preflight: {path_text}")
    if preflight.get("execution_order", {}).get("sha256") != sha256_file(ORDER):
        raise RuntimeError("balanced execution order changed after preflight freeze")
    if preflight.get("run_config", {}).get("sha256") != sha256_file(RUN_CONFIG):
        raise RuntimeError("run configuration changed after preflight freeze")
    if preflight.get("runner", {}).get("sha256") != sha256_file(RUNNER):
        raise RuntimeError("runner changed after preflight freeze")
    if preflight.get("transport_policy", {}).get("http_client_retry_total") != 0:
        raise RuntimeError("preflight does not bind retry_total=0")
    if preflight.get("transport_policy", {}).get("logical_retry") is not False:
        raise RuntimeError("preflight does not bind logical_retry=false")
    if preflight.get("transport_policy", {}).get("concurrency") != 1:
        raise RuntimeError("preflight does not bind concurrency=1")
    return preflight


def load_primary_key() -> tuple[str, str]:
    value = read_json(CONFIG)
    provider = value.get("providers", {}).get("ebond-gpt-image-2")
    credentials = provider.get("credentials") if isinstance(provider, dict) else None
    node = credentials.get("api_key") if isinstance(credentials, dict) else None
    key = node.get("value") if isinstance(node, dict) else None
    if not isinstance(key, str) or not key:
        raise RuntimeError("PRIMARY EBOND credential unavailable")
    return key, sha256_bytes(key.encode("utf-8"))


def make_db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS slots (
            order_index INTEGER PRIMARY KEY,
            logical_request_id TEXT NOT NULL UNIQUE,
            prompt_id TEXT NOT NULL UNIQUE,
            group_id TEXT NOT NULL,
            variant_id TEXT NOT NULL,
            target_role TEXT NOT NULL,
            target_event_label TEXT NOT NULL,
            taxonomy TEXT NOT NULL,
            planned_internal_split TEXT NOT NULL,
            prompt_sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            latency_seconds REAL,
            http_status INTEGER,
            provider_request_id TEXT,
            raw_response_path TEXT,
            raw_response_sha256 TEXT,
            raw_image_path TEXT,
            final_image_path TEXT,
            raw_sha256 TEXT,
            final_sha256 TEXT,
            native_width INTEGER,
            native_height INTEGER,
            final_width INTEGER,
            final_height INTEGER,
            safe_error TEXT,
            completion_semantics TEXT,
            exact_duplicate_raw INTEGER NOT NULL DEFAULT 0,
            exact_duplicate_final INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_index INTEGER NOT NULL,
            logical_request_id TEXT NOT NULL,
            event TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS run_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def seed_db(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    for row in rows:
        conn.execute(
            """INSERT OR IGNORE INTO slots
            (order_index, logical_request_id, prompt_id, group_id, variant_id,
             target_role, target_event_label, taxonomy, planned_internal_split,
             prompt_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (int(row["order_index"]), row["logical_request_id"], row["prompt_id"], row["group_id"], row["variant_id"], row["target_role"], row["target_event_label"], row["taxonomy"], row["planned_internal_split"], row["prompt_sha256"]),
        )
    conn.execute("INSERT OR REPLACE INTO run_meta(key, value) VALUES (?, ?)", ("runner_schema_version", str(SCHEMA_VERSION)))
    conn.commit()
    for row in rows:
        found = conn.execute("SELECT prompt_sha256, prompt_id, logical_request_id FROM slots WHERE order_index=?", (int(row["order_index"]),)).fetchone()
        if not found or found[0] != row["prompt_sha256"] or found[1] != row["prompt_id"] or found[2] != row["logical_request_id"]:
            raise RuntimeError(f"ledger slot binding mismatch at order {row['order_index']}")


def record_event(conn: sqlite3.Connection, row: dict[str, str], event: str, details: dict[str, Any]) -> None:
    conn.execute("INSERT INTO events(order_index, logical_request_id, event, timestamp, details_json) VALUES (?, ?, ?, ?, ?)", (int(row["order_index"]), row["logical_request_id"], event, now(), json.dumps(details, ensure_ascii=False, sort_keys=True)))


def mark_unresolved_started(conn: sqlite3.Connection) -> list[str]:
    started = conn.execute("SELECT order_index, logical_request_id FROM slots WHERE status='STARTED' ORDER BY order_index").fetchall()
    if not started:
        return []
    for order_index, logical_id in started:
        conn.execute("UPDATE slots SET status='COMPLETION_UNKNOWN', finished_at=?, safe_error=?, completion_semantics=? WHERE order_index=?", (now(), "runner resumed with unresolved STARTED; request outcome cannot be proven; no resend", "COMPLETION_UNKNOWN", order_index))
        conn.execute("INSERT INTO events(order_index, logical_request_id, event, timestamp, details_json) VALUES (?, ?, ?, ?, ?)", (order_index, logical_id, "RESUME_MARKED_COMPLETION_UNKNOWN", now(), json.dumps({"no_resend": True}, sort_keys=True)))
    conn.commit()
    return [item[1] for item in started]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def extract_request_id(payload: Any, headers: Any = None) -> str:
    if headers is not None:
        for name in ("x-request-id", "request-id", "x-correlation-id"):
            value = headers.get(name)
            if value:
                return str(value)
    if isinstance(payload, dict):
        for key in ("id", "request_id", "requestId"):
            value = payload.get(key)
            if isinstance(value, (str, int)) and value:
                return str(value)
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("request_id", "requestId", "id"):
                value = error.get(key)
                if isinstance(value, (str, int)) and value:
                    return str(value)
    return "unknown"


def post_once(key: str, prompt: str, row: dict[str, str]) -> dict[str, Any]:
    payload = {"model": MODEL, "prompt": prompt, "size": NATIVE_SIZE, "quality": QUALITY}
    request_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        GENERATION_ENDPOINT,
        data=request_bytes,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    started = time.monotonic()
    raw = b""
    status: int | None = None
    headers: Any = None
    transport_error: str | None = None
    timeout = False
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = int(response.getcode())
            headers = response.headers
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                transport_error = f"response exceeded {MAX_RESPONSE_BYTES} bytes"
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        headers = exc.headers
        try:
            raw = exc.read(MAX_RESPONSE_BYTES + 1)
        except Exception:
            raw = b""
    except (socket.timeout, TimeoutError) as exc:
        timeout = True
        transport_error = safe_text(f"{type(exc).__name__}: {exc}", key)
    except urllib.error.URLError as exc:
        reason = exc.reason
        timeout = isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower()
        transport_error = safe_text(f"URLError: {reason}", key)
    except ConnectionResetError as exc:
        transport_error = safe_text(f"ConnectionResetError: {exc}", key)
        timeout = True
    except Exception as exc:  # pragma: no cover - defensive transport boundary
        transport_error = safe_text(f"{type(exc).__name__}: {exc}", key)
        timeout = True
    latency = time.monotonic() - started
    response_text = raw.decode("utf-8", errors="replace") if raw else ""
    response_json: Any = None
    json_ok = False
    parse_error = ""
    if response_text:
        try:
            response_json = json.loads(response_text)
            json_ok = isinstance(response_json, (dict, list))
        except json.JSONDecodeError as exc:
            parse_error = f"JSONDecodeError: {exc.msg}"
    provider_request_id = extract_request_id(response_json, headers)
    return {
        "http_status": status,
        "raw_body": raw,
        "raw_body_sha256": sha256_bytes(raw),
        "raw_body_text": safe_text(response_text, key),
        "response_json": response_json,
        "json_ok": json_ok,
        "parse_error": parse_error,
        "provider_request_id": provider_request_id,
        "latency_seconds": latency,
        "transport_error": transport_error,
        "timeout": timeout,
        "client_http_generation_attempts": 1,
    }


def extract_image_bytes(response_json: Any) -> tuple[bytes | None, str]:
    if not isinstance(response_json, dict):
        return None, "provider JSON is not an object"
    data = response_json.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None, "missing data[0] object"
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        return None, "missing data[0].b64_json; URL fallback disabled"
    if "," in encoded and encoded.lower().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    encoded = "".join(encoded.split())
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        return None, f"invalid base64 image bytes: {type(exc).__name__}"
    if not decoded:
        return None, "decoded image bytes empty"
    return decoded, ""


def convert_image(raw_path: Path, final_path: Path) -> dict[str, Any]:
    # verify() is deliberately called immediately after Image.open(); reopen
    # for load before conversion, as required by the image QA guidance.
    with Image.open(raw_path) as image:
        image.verify()
    with Image.open(raw_path) as image:
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
        converted = cropped.resize(tuple(FINAL_SIZE), resampling)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = final_path.with_name(final_path.name + ".tmp")
        converted.save(temporary, format="PNG")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, final_path)
        fsync_directory(final_path.parent)
    with Image.open(final_path) as image:
        image.verify()
    with Image.open(final_path) as image:
        image.load()
        final_width, final_height = image.size
    if (final_width, final_height) != tuple(FINAL_SIZE):
        raise ValueError(f"final size {(final_width, final_height)} != {tuple(FINAL_SIZE)}")
    return {"native_width": native_width, "native_height": native_height, "native_aspect_ratio": native_width / native_height, "crop_box": list(crop_box), "final_width": final_width, "final_height": final_height}


def save_raw_response(row: dict[str, str], response: dict[str, Any], credential_fingerprint: str) -> Path:
    path = RAW_RESPONSE_DIR / f"{row['logical_request_id']}_{row['prompt_id']}.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "logical_request_id": row["logical_request_id"],
        "prompt_id": row["prompt_id"],
        "timestamp": now(),
        "provider": PROVIDER,
        "model": MODEL,
        "credential_slot_safe": "PRIMARY",
        "credential_fingerprint_sha256": credential_fingerprint,
        "http_status": response["http_status"],
        "provider_request_id": response["provider_request_id"],
        "latency_seconds": response["latency_seconds"],
        "client_http_generation_attempts": 1,
        "raw_body_sha256": response["raw_body_sha256"],
        "raw_body_text": response["raw_body_text"],
        "json_ok": response["json_ok"],
        "parse_error": response["parse_error"],
        "transport_error": response["transport_error"],
        "timeout": response["timeout"],
    }
    write_json(path, payload)
    return path


def classify_response(response: dict[str, Any]) -> tuple[str, str, bytes | None]:
    if response["timeout"]:
        return "COMPLETION_UNKNOWN", response["transport_error"] or "HTTP timeout; provider completion cannot be confirmed", None
    status = response["http_status"]
    if response["transport_error"]:
        return "COMPLETION_UNKNOWN", response["transport_error"], None
    if status is None:
        return "COMPLETION_UNKNOWN", "no HTTP status returned", None
    if not (200 <= status < 300):
        return "FAILED_CONFIRMED", f"provider HTTP {status}", None
    if not response["json_ok"]:
        return "FAILED_CONFIRMED", response["parse_error"] or "invalid provider JSON", None
    image_bytes, error = extract_image_bytes(response["response_json"])
    if image_bytes is None:
        return "FAILED_CONFIRMED", error, None
    return "SUCCESS", "", image_bytes


def count_statuses(conn: sqlite3.Connection) -> Counter[str]:
    return Counter(row[0] for row in conn.execute("SELECT status FROM slots").fetchall())


def successes_before(conn: sqlite3.Connection, order_index: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM slots WHERE status='SUCCESS' AND order_index < ?", (order_index,)).fetchone()[0])


def update_stage_checkpoints(conn: sqlite3.Connection, row: dict[str, str], status: str, credential_fingerprint: str) -> None:
    order_index = int(row["order_index"])
    if status != "SUCCESS":
        return
    stage = None
    if order_index == 1:
        stage = "smoke"
    elif order_index == 6:
        stage = "ramp1"
    elif order_index == 16:
        stage = "ramp2"
    if stage:
        statuses = count_statuses(conn)
        expected = {"smoke": 1, "ramp1": 6, "ramp2": 16}[stage]
        record = {"stage": stage, "completed_order_index": order_index, "required_successes": expected, "success_count": statuses.get("SUCCESS", 0), "status": "PASS" if statuses.get("SUCCESS", 0) == expected else "FAIL", "concurrency": 1, "credential_slot_safe": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint, "created_at": now()}
        write_json(OPT / "checkpoints" / f"{stage}_status.json", record)


def checkpoint(conn: sqlite3.Connection, row: dict[str, str] | None, run_status: str, credential_fingerprint: str) -> None:
    statuses = count_statuses(conn)
    record = {"created_at": now(), "run_status": run_status, "last_order_index": int(row["order_index"]) if row else None, "last_prompt_id": row["prompt_id"] if row else None, "counts": dict(statuses), "success_count": statuses.get("SUCCESS", 0), "failure_count": statuses.get("FAILED_CONFIRMED", 0), "completion_unknown_count": statuses.get("COMPLETION_UNKNOWN", 0), "holdout_requests": 0, "credential_slot_safe": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint}
    write_json(LATEST_CHECKPOINT, record)
    if row and int(row["order_index"]) % 5 == 0:
        write_json(OPT / "checkpoints" / f"group_{row['group_id']}.json", record | {"group_id": row["group_id"]})


def activate_credential(row: dict[str, str], provider_request_id: str, credential_fingerprint: str) -> None:
    if ACTIVE_CREDENTIAL.exists():
        return
    payload = {"schema_version": 1, "created_at": now(), "active_credential_slot": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint, "first_success_logical_request_id": row["logical_request_id"], "first_success_prompt_id": row["prompt_id"], "first_success_provider_request_id": provider_request_id, "successful_image_credential_slot_count_target": 1, "secret_persisted": False}
    write_json(ACTIVE_CREDENTIAL, payload)
    write_text_atomic(ACTIVE_CREDENTIAL.with_name(ACTIVE_CREDENTIAL.name + ".sha256"), f"{sha256_file(ACTIVE_CREDENTIAL)}  {ACTIVE_CREDENTIAL.name}\n")


def export_ledger(conn: sqlite3.Connection) -> None:
    fields = [item[1] for item in conn.execute("PRAGMA table_info(slots)").fetchall()]
    rows = [dict(zip(fields, values)) for values in conn.execute(f"SELECT {','.join(fields)} FROM slots ORDER BY order_index").fetchall()]
    LEDGER_CSV.parent.mkdir(parents=True, exist_ok=True)
    temporary = LEDGER_CSV.with_name(LEDGER_CSV.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, LEDGER_CSV)
    fsync_directory(LEDGER_CSV.parent)


def db_checkpoint_and_close(conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.close()
    if DB.exists():
        checkpoint_conn = sqlite3.connect(str(DB), timeout=30)
        try:
            checkpoint_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            checkpoint_conn.commit()
        finally:
            checkpoint_conn.close()
        with DB.open("rb") as handle:
            os.fsync(handle.fileno())
        fsync_directory(DB.parent)


def summarize_counts(conn: sqlite3.Connection | None) -> dict[str, Any]:
    if conn is None:
        return {"total_slots": 0, "success": 0, "failed_confirmed": 0, "completion_unknown": 0, "pending": 0, "started": 0}
    rows = conn.execute("SELECT status FROM slots").fetchall()
    counts = Counter(item[0] for item in rows)
    return {"total_slots": len(rows), "success": counts.get("SUCCESS", 0), "failed_confirmed": counts.get("FAILED_CONFIRMED", 0), "completion_unknown": counts.get("COMPLETION_UNKNOWN", 0), "pending": counts.get("PENDING", 0), "started": counts.get("STARTED", 0)}


def terminal_freeze(run_status: str, conn: sqlite3.Connection | None, preflight: dict[str, Any] | None, error: str | None, credential_fingerprint: str | None) -> dict[str, Any]:
    counts = summarize_counts(conn)
    rows: list[sqlite3.Row] = []
    if conn is not None:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM slots ORDER BY order_index").fetchall()
    latencies = sorted(float(row["latency_seconds"]) for row in rows if row["latency_seconds"] is not None)
    def percentile(q: float) -> float | None:
        if not latencies:
            return None
        index = max(0, min(len(latencies) - 1, int(round((len(latencies) - 1) * q))))
        return latencies[index]
    http_classes = Counter()
    for row in rows:
        status = row["http_status"]
        if status is None:
            continue
        if 200 <= int(status) < 300:
            http_classes["2xx"] += 1
        elif int(status) == 401:
            http_classes["401"] += 1
        elif int(status) == 403:
            http_classes["403"] += 1
        elif int(status) == 429:
            http_classes["429"] += 1
        elif 500 <= int(status) < 600:
            http_classes["5xx"] += 1
        else:
            http_classes[str(status)] += 1
    terminal = {
        "schema_version": 1,
        "created_at": now(),
        "project": "net_vlm",
        "event": "person_fallen",
        "event_version": "v2.0",
        "p4d_eb1_name": "P4D_EB1_EBOND_FULL_REGENERATION",
        "p4d_eb1_generation_revision": REVISION,
        "terminal_status": run_status,
        "error_safe": safe_text(error or ""),
        "preflight_freeze_path": str(PREFLIGHT),
        "preflight_freeze_sha256": sha256_file(PREFLIGHT) if PREFLIGHT.exists() else None,
        "runner_path": str(RUNNER),
        "runner_sha256": sha256_file(RUNNER) if RUNNER.exists() else None,
        "ledger_sqlite_path": str(DB),
        "ledger_sqlite_sha256": sha256_file(DB) if DB.exists() else None,
        "ledger_csv_path": str(LEDGER_CSV),
        "ledger_csv_sha256": sha256_file(LEDGER_CSV) if LEDGER_CSV.exists() else None,
        "request_log_path": str(REQUEST_LOG),
        "request_log_sha256": sha256_file(REQUEST_LOG) if REQUEST_LOG.exists() else None,
        "raw_responses_log_path": str(RAW_LOG),
        "raw_responses_log_sha256": sha256_file(RAW_LOG) if RAW_LOG.exists() else None,
        "counts": counts,
        "http_classes": dict(http_classes),
        "latency_seconds": {"p50": percentile(0.50), "p95": percentile(0.95), "max": max(latencies) if latencies else None},
        "raw_image_count": len(list(RAW_DIR.glob("*.png"))) if RAW_DIR.exists() else 0,
        "final_image_count": len(list(FINAL_DIR.glob("*.png"))) if FINAL_DIR.exists() else 0,
        "provider": PROVIDER,
        "model": MODEL,
        "api_base_safe": API_BASE,
        "credential_slot_safe": "PRIMARY" if credential_fingerprint else None,
        "credential_fingerprint_sha256": credential_fingerprint,
        "client_http_generation_attempts_total": sum(int(row["attempt_count"] or 0) for row in rows),
        "client_http_generation_attempts_per_logical_slot_max": 1,
        "http_library": "urllib.request",
        "http_client_retry_total": 0,
        "logical_retry": False,
        "provider_wrapper_retry": 0,
        "concurrency": 1,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "codex_images_reused": 0,
        "gr1_images_reused": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
        "p4d_images_accepted": 0,
        "preflight_verified": preflight is not None,
    }
    write_json(TERMINAL, terminal)
    write_text_atomic(TERMINAL_SIDECAR, f"{sha256_file(TERMINAL)}  {TERMINAL.name}\n")
    return terminal


def process_slots(conn: sqlite3.Connection, rows: list[dict[str, str]], key: str, credential_fingerprint: str) -> str:
    unresolved = mark_unresolved_started(conn)
    if unresolved:
        safe_error = "unresolved STARTED slot found at runner start; no request resent"
        write_json(STOP_MARKER, {"created_at": now(), "status": "STOPPED_COMPLETION_UNKNOWN", "logical_request_ids": unresolved, "holdout_requests": 0, "safe_error": safe_error})
        return "STOPPED_COMPLETION_UNKNOWN"
    for row in rows:
        current = conn.execute("SELECT status FROM slots WHERE order_index=?", (int(row["order_index"]),)).fetchone()
        status = current[0] if current else "PENDING"
        if status == "SUCCESS":
            continue
        if status in {"FAILED_CONFIRMED", "COMPLETION_UNKNOWN"}:
            write_json(STOP_MARKER, {"created_at": now(), "status": "STOPPED_PRESERVED_PRIOR_FAILURE", "order_index": int(row["order_index"]), "logical_request_id": row["logical_request_id"], "holdout_requests": 0})
            return "STOPPED_PRESERVED_PRIOR_FAILURE"
        if status != "PENDING":
            raise RuntimeError(f"unexpected ledger status {status} at {row['logical_request_id']}")
        prompt_path = Path(row["original_prompt_path"])
        prompt_bytes = prompt_path.read_bytes()
        if sha256_bytes(prompt_bytes) != row["prompt_sha256"]:
            raise RuntimeError(f"prompt bytes changed for {row['prompt_id']}")
        prompt = prompt_bytes.decode("utf-8")
        started_at = now()
        conn.execute("UPDATE slots SET status='STARTED', attempt_count=1, started_at=?, completion_semantics=? WHERE order_index=?", (started_at, "ONE_HTTP_GENERATION_REQUEST", int(row["order_index"])))
        record_event(conn, row, "STARTED_COMMITTED", {"attempt_count": 1, "http_generation_attempts": 1, "credential_slot_safe": "PRIMARY"})
        conn.commit()
        response = post_once(key, prompt, row)
        raw_response_path = save_raw_response(row, response, credential_fingerprint)
        append_jsonl(RAW_LOG, {"logical_request_id": row["logical_request_id"], "prompt_id": row["prompt_id"], "http_status": response["http_status"], "provider_request_id": response["provider_request_id"], "raw_response_path": str(raw_response_path), "raw_body_sha256": response["raw_body_sha256"], "json_ok": response["json_ok"], "parse_error": response["parse_error"], "latency_seconds": response["latency_seconds"], "client_http_generation_attempts": 1, "credential_slot_safe": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint, "transport_error": response["transport_error"], "timeout": response["timeout"]})
        status_after, safe_error, image_bytes = classify_response(response)
        raw_path: Path | None = None
        final_path: Path | None = None
        raw_sha: str | None = None
        final_sha: str | None = None
        dimensions: dict[str, Any] = {}
        exact_raw = 0
        exact_final = 0
        if status_after == "SUCCESS" and image_bytes is not None:
            raw_path = RAW_DIR / row["raw_filename"]
            final_path = FINAL_DIR / row["final_filename"]
            try:
                atomic_bytes(raw_path, image_bytes)
                raw_sha = sha256_file(raw_path)
                dimensions = convert_image(raw_path, final_path)
                final_sha = sha256_file(final_path)
                exact_raw = int(conn.execute("SELECT COUNT(*) FROM slots WHERE status='SUCCESS' AND raw_sha256=?", (raw_sha,)).fetchone()[0] > 0)
                exact_final = int(conn.execute("SELECT COUNT(*) FROM slots WHERE status='SUCCESS' AND final_sha256=?", (final_sha,)).fetchone()[0] > 0)
                record_event(conn, row, "RAW_AND_FINAL_DURABLE", {"raw_sha256": raw_sha, "final_sha256": final_sha, "native_width": dimensions["native_width"], "native_height": dimensions["native_height"], "final_width": dimensions["final_width"], "final_height": dimensions["final_height"], "exact_duplicate_raw": exact_raw, "exact_duplicate_final": exact_final})
            except Exception as exc:
                status_after = "FAILED_CONFIRMED"
                safe_error = safe_text(f"image decode/conversion failure: {type(exc).__name__}: {exc}")
        finished_at = now()
        conn.execute(
            """UPDATE slots SET status=?, finished_at=?, latency_seconds=?, http_status=?,
               provider_request_id=?, raw_response_path=?, raw_response_sha256=?,
               raw_image_path=?, final_image_path=?, raw_sha256=?, final_sha256=?,
               native_width=?, native_height=?, final_width=?, final_height=?,
               safe_error=?, completion_semantics=?, exact_duplicate_raw=?, exact_duplicate_final=?
               WHERE order_index=?""",
            (status_after, finished_at, response["latency_seconds"], response["http_status"], response["provider_request_id"], str(raw_response_path), response["raw_body_sha256"], str(raw_path) if raw_path else None, str(final_path) if final_path and final_path.exists() else None, raw_sha, final_sha, dimensions.get("native_width"), dimensions.get("native_height"), dimensions.get("final_width"), dimensions.get("final_height"), safe_error, "COMPLETION_UNKNOWN" if status_after == "COMPLETION_UNKNOWN" else "CONFIRMED", exact_raw, exact_final, int(row["order_index"])),
        )
        record_event(conn, row, status_after, {"http_status": response["http_status"], "safe_error": safe_error, "client_http_generation_attempts": 1, "raw_response_path": str(raw_response_path), "raw_sha256": raw_sha, "final_sha256": final_sha})
        conn.commit()
        append_jsonl(REQUEST_LOG, {"logical_request_id": row["logical_request_id"], "order_index": int(row["order_index"]), "prompt_id": row["prompt_id"], "group_id": row["group_id"], "variant_id": row["variant_id"], "target_role": row["target_role"], "taxonomy": row["taxonomy"], "planned_internal_split": row["planned_internal_split"], "prompt_sha256": row["prompt_sha256"], "provider": PROVIDER, "model": MODEL, "credential_slot_safe": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint, "request_payload_config": {"model": MODEL, "size": NATIVE_SIZE, "quality": QUALITY, "prompt_sha256": row["prompt_sha256"]}, "started_at": started_at, "finished_at": finished_at, "latency_seconds": response["latency_seconds"], "http_status": response["http_status"], "provider_request_id": response["provider_request_id"], "raw_response_path": str(raw_response_path), "raw_response_sha256": response["raw_body_sha256"], "raw_image_path": str(raw_path) if raw_path else None, "final_image_path": str(final_path) if final_path and final_path.exists() else None, "raw_sha256": raw_sha, "final_sha256": final_sha, "native_size": [dimensions.get("native_width"), dimensions.get("native_height")] if dimensions else None, "final_size": [dimensions.get("final_width"), dimensions.get("final_height")] if dimensions else None, "status": status_after, "safe_error": safe_error, "client_http_generation_attempts": 1, "holdout": False})
        if status_after == "SUCCESS":
            activate_credential(row, response["provider_request_id"], credential_fingerprint)
            update_stage_checkpoints(conn, row, status_after, credential_fingerprint)
            checkpoint(conn, row, "RUNNING", credential_fingerprint)
            print(json.dumps({"logical_request_id": row["logical_request_id"], "prompt_id": row["prompt_id"], "status": "SUCCESS", "latency_seconds": round(response["latency_seconds"], 3), "raw_sha256": raw_sha, "final_sha256": final_sha}, ensure_ascii=False, sort_keys=True), flush=True)
            continue
        statuses = count_statuses(conn)
        status_code = response["http_status"]
        if status_code in {401, 403} and statuses.get("SUCCESS", 0) == 0:
            stop_status = "BLOCKED_PRIMARY_AUTH_NO_SECONDARY"
        elif status_code == 429 and statuses.get("SUCCESS", 0) == 0:
            stop_status = "BLOCKED_PRIMARY_QUOTA"
        else:
            stop_status = "STOPPED_BY_PROVIDER_OR_TRANSPORT_FAILURE" if status_after == "FAILED_CONFIRMED" else "STOPPED_COMPLETION_UNKNOWN"
        write_json(STOP_MARKER, {"created_at": now(), "status": stop_status, "order_index": int(row["order_index"]), "logical_request_id": row["logical_request_id"], "http_status": status_code, "safe_error": safe_error, "holdout_requests": 0, "no_retry": True})
        checkpoint(conn, row, stop_status, credential_fingerprint)
        print(json.dumps({"logical_request_id": row["logical_request_id"], "prompt_id": row["prompt_id"], "status": status_after, "stop_status": stop_status, "http_status": status_code, "safe_error": safe_error}, ensure_ascii=False, sort_keys=True), flush=True)
        return stop_status
    checkpoint(conn, rows[-1] if rows else None, "COMPLETE_440" if summarize_counts(conn)["success"] == 440 else "RUNNING", credential_fingerprint)
    return "COMPLETE_440" if summarize_counts(conn)["success"] == 440 else "INCOMPLETE_PENDING"


def main() -> int:
    parser = argparse.ArgumentParser(description="P4D_EB1 direct one-shot EBOND runner")
    parser.add_argument("command", choices=["run", "status"])
    args = parser.parse_args()
    if args.command == "status":
        if not DB.exists():
            print(json.dumps({"status": "NOT_INITIALIZED", "holdout_requests": 0}, sort_keys=True))
            return 0
        conn = sqlite3.connect(str(DB))
        summary = summarize_counts(conn)
        conn.close()
        print(json.dumps({"status": summary, "terminal_freeze": str(TERMINAL) if TERMINAL.exists() else None, "holdout_requests": 0}, ensure_ascii=False, sort_keys=True))
        return 0

    lock_handle = LOCK_PATH.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("another EBOND runner holds the lock") from exc
    conn: sqlite3.Connection | None = None
    preflight: dict[str, Any] | None = None
    credential_fingerprint: str | None = None
    run_status = "NOT_STARTED"
    error: str | None = None
    try:
        preflight = verify_frozen_preflight()
        rows = read_order()
        key, credential_fingerprint = load_primary_key()
        conn = make_db()
        seed_db(conn, rows)
        write_json(RUN_CONFIG.with_name("run_started.json"), {"created_at": now(), "provider": PROVIDER, "model": MODEL, "credential_slot_safe": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint, "http_library": "urllib.request", "http_client_retry_total": 0, "logical_retry": False, "concurrency": 1, "holdout_requests": 0, "secret_persisted": False})
        run_status = process_slots(conn, rows, key, credential_fingerprint)
        write_json(STATUS_PATH, {"created_at": now(), "status": run_status, "counts": summarize_counts(conn), "holdout_requests": 0, "holdout_consumed": False, "credential_slot_safe": "PRIMARY", "credential_fingerprint_sha256": credential_fingerprint})
        return_code = 0
    except Exception as exc:
        error = safe_text(f"{type(exc).__name__}: {exc}")
        run_status = "BLOCKED_PRE_REQUEST" if conn is None else "STOPPED_RUNNER_EXCEPTION"
        write_json(STOP_MARKER, {"created_at": now(), "status": run_status, "safe_error": error, "holdout_requests": 0, "no_retry": True})
        if conn is not None:
            conn.commit()
        return_code = 1
    finally:
        if conn is not None:
            try:
                export_ledger(conn)
            except Exception as exc:
                error = error or safe_text(f"ledger export failure: {type(exc).__name__}: {exc}")
                run_status = "STOPPED_LEDGER_FINALIZATION_FAILURE"
            try:
                db_checkpoint_and_close(conn)
            except Exception as exc:
                error = error or safe_text(f"sqlite finalization failure: {type(exc).__name__}: {exc}")
                run_status = "STOPPED_LEDGER_FINALIZATION_FAILURE"
            conn = None
        # Terminal freeze is emitted for complete, failed, auth, quota, and
        # completion-unknown runs.  The DB is closed/checkpointed before its
        # hash is bound here.
        terminal_conn: sqlite3.Connection | None = None
        if DB.exists():
            terminal_conn = sqlite3.connect(str(DB))
        try:
            terminal = terminal_freeze(run_status, terminal_conn, preflight, error, credential_fingerprint)
        finally:
            if terminal_conn is not None:
                terminal_conn.close()
        if terminal.get("terminal_status") != run_status:
            run_status = terminal.get("terminal_status", run_status)
        write_json(STATUS_PATH, {"created_at": now(), "status": run_status, "counts": terminal.get("counts"), "holdout_requests": 0, "holdout_consumed": False, "credential_slot_safe": "PRIMARY" if credential_fingerprint else None, "credential_fingerprint_sha256": credential_fingerprint, "terminal_freeze": str(TERMINAL), "terminal_freeze_sha256": sha256_file(TERMINAL)})
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
    print(json.dumps({"status": run_status, "return_code": return_code, "terminal_freeze": str(TERMINAL), "terminal_freeze_sha256": sha256_file(TERMINAL) if TERMINAL.exists() else None, "holdout_requests": 0}, ensure_ascii=False, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
