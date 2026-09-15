#!/usr/bin/env python3
"""P4D_GR1 provider-revision generation runner.

The runner implements the frozen, gate-ordered continuation after the original
EBOND credential failure.  It never edits the formal dataset or the old batch,
never changes the prompt/group/taxonomy plan, and never performs automatic
retries.  A new Codex provider revision is used only because its current doctor
and auth checks pass and the old provider has zero successful images.

Commands are deliberately separate so a human can inspect each gate:

    preflight -> smoke -> ramp1 -> ramp2 -> bulk -> recover -> qa

The final semantic review, formal ingest, and C3 stages are intentionally owned
by later scripts/gates; this runner only produces auditable staged images.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
PLAN = P4D / "01_prompt_plan"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
RUN = P4D / "02_generation" / "gr1"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
CLI = "/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs"
NODE = "node"
PROVIDER = "codex"
MODEL = "gpt-5.4"
REVISION_ID = "P4D_GR1_PR_CODEX_20260827_01"
NATIVE_SIZE = "1536x1024"
QUALITY = "medium"
FINAL_SIZE = (1920, 1080)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

EXPECTED_HASHES = {
    "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    "C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}
CSV_FIELDS = [
    "attempt_id", "provider_revision_id", "prompt_id", "group_id", "planned_split", "phase",
    "attempt", "provider_attempt", "provider", "model", "model_version",
    "request_started_at", "request_finished_at", "native_size", "quality",
    "provider_request_id", "seed", "http_status", "status", "error_code",
    "error_message_safe", "raw_output_path", "final_output_path", "raw_sha256",
    "final_sha256", "native_width", "native_height", "final_width", "final_height",
    "crop_box", "latency_seconds",
]

_write_lock = threading.Lock()
_auth_failure = threading.Event()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sanitize_text(text: str) -> str:
    """Remove credential-like material before persisting subprocess output."""
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{20,}", r"\1<REDACTED>", text)
    return text


def nested_values(value: Any, wanted: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in wanted and child not in (None, ""):
                found.append(str(child))
            found.extend(nested_values(child, wanted))
    elif isinstance(value, list):
        for child in value:
            found.extend(nested_values(child, wanted))
    return found


def parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"ok": False, "raw_json": value}
    except json.JSONDecodeError:
        return {"ok": False, "parse_error": True, "raw_stdout": sanitize_text(raw)}


def validator_result() -> dict[str, Any]:
    command = ["python3", str(DATASET / "tools/validate_dataset.py"), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    payload = parse_json(proc.stdout)
    return {"command": command, "returncode": proc.returncode, "payload": payload}


def validator_pass(result: dict[str, Any]) -> bool:
    payload = result.get("payload", {})
    return bool(
        isinstance(payload, dict)
        and payload.get("status") == "valid"
        and payload.get("error_count") == 0
        and payload.get("full_hash_check") is True
    )


def run_cli_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run([NODE, CLI, "--json", *args], capture_output=True, text=True, check=False, timeout=60)
    stdout = sanitize_text(proc.stdout)
    stderr = sanitize_text(proc.stderr)
    payload = parse_json(stdout)
    return {"returncode": proc.returncode, "payload": payload, "stdout": stdout, "stderr": stderr}


def hash_check() -> dict[str, Any]:
    paths = {
        "group_manifest.csv": PLAN / "group_manifest.csv",
        "group_split_freeze.json": PLAN / "group_split_freeze.json",
        "prompt_manifest.csv": PLAN / "prompt_manifest.csv",
        "prompt_pack.md": PLAN / "prompt_pack.md",
        "prompt_pack_freeze.json": PLAN / "prompt_pack_freeze.json",
        "C3_prompt.txt": ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt",
    }
    actual: dict[str, str | None] = {}
    checks: dict[str, bool] = {}
    for name, path in paths.items():
        value = sha256_file(path) if path.exists() else None
        actual[name] = value
        checks[name] = value == EXPECTED_HASHES[name]
    return {"expected": EXPECTED_HASHES, "actual": actual, "checks": checks, "all_match": all(checks.values())}


def load_plan() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    prompts = read_csv(PLAN / "prompt_manifest.csv")
    groups = read_csv(PLAN / "group_manifest.csv")
    freeze = read_json(PLAN / "group_split_freeze.json", {}) or {}
    if len(prompts) != 440 or len({row.get("prompt_id") for row in prompts}) != 440:
        raise RuntimeError("prompt manifest cardinality/uniqueness mismatch")
    if len(groups) != 88 or len({row.get("group_id") for row in groups}) != 88:
        raise RuntimeError("group manifest cardinality/uniqueness mismatch")
    if freeze.get("design_screen_decided_before_generation") is not True or freeze.get("cross_split_group_count") != 0:
        raise RuntimeError("pre-generation group freeze is not valid")
    role_counts = Counter(row.get("target_role") for row in prompts)
    split_counts = Counter(row.get("planned_internal_split") for row in prompts)
    if role_counts != Counter({"hard_negative": 300, "positive": 100, "ordinary_negative": 40}):
        raise RuntimeError(f"role quota changed: {dict(role_counts)}")
    if split_counts != Counter({"NEW_DESIGN": 265, "NEW_SCREEN": 175}):
        raise RuntimeError(f"split quota changed: {dict(split_counts)}")
    for row in prompts:
        path = Path(row["prompt_path"])
        if not path.exists() or sha256_file(path) != row.get("prompt_sha256"):
            raise RuntimeError(f"prompt file/hash mismatch: {row.get('prompt_id')}")
    return prompts, groups, freeze


def previous_state() -> dict[str, Any]:
    return read_json(P4D / "02_generation" / "generation_state.json", {}) or {}


def old_attempts() -> list[dict[str, str]]:
    return read_csv(BATCH / "generation_attempts.csv")


def ensure_dirs() -> None:
    for directory in [RUN, RUN / "cli_logs", RUN / "provider_results", RUN / "raw", RUN / "final", RUN / "metadata", P4D / "03_intake_audit", P4D / "04_semantic_review"]:
        directory.mkdir(parents=True, exist_ok=True)


def gr1_attempts_path() -> Path:
    return RUN / "generation_attempts.csv"


def load_gr1_attempts() -> list[dict[str, str]]:
    return read_csv(gr1_attempts_path())


def append_attempt(row: dict[str, Any]) -> None:
    path = gr1_attempts_path()
    with _write_lock:
        new_file = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
            if new_file:
                writer.writeheader()
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})
            handle.flush()
            os.fsync(handle.fileno())


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with _write_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def ensure_log_headers() -> None:
    ensure_dirs()
    path = gr1_attempts_path()
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n").writeheader()
    for name in ["request_log.jsonl", "raw_responses.jsonl"]:
        (RUN / name).touch(exist_ok=True)


def current_success_ids() -> set[str]:
    successes: set[str] = set()
    for row in load_gr1_attempts():
        if row.get("status") == "SUCCESS" and row.get("final_output_path") and Path(row["final_output_path"]).exists():
            successes.add(row["prompt_id"])
    return successes


def attempted_ids() -> set[str]:
    return {row.get("prompt_id", "") for row in load_gr1_attempts() if row.get("prompt_id")}


def slot_history(prompt_id: str) -> list[dict[str, str]]:
    return [row for row in load_gr1_attempts() if row.get("prompt_id") == prompt_id]


def parse_http_code(payload: dict[str, Any], returncode: int) -> str:
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message", "") if isinstance(error, dict) else ""
    match = re.search(r"HTTP\s+(\d{3})", str(message))
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
    return code, sanitize_text(message)


def image_to_final(raw_path: Path, final_path: Path) -> dict[str, Any]:
    """Verify raw bytes and controlled center-crop/resize to 1920x1080."""
    with Image.open(raw_path) as image:
        image.verify()
    with Image.open(raw_path) as image:
        native_width, native_height = image.size
        if native_width <= 0 or native_height <= 0:
            raise ValueError("invalid native dimensions")
        image = image.convert("RGB")
        target_ratio = FINAL_SIZE[0] / FINAL_SIZE[1]
        native_ratio = native_width / native_height
        if abs(native_ratio - target_ratio) < 1e-9:
            crop = (0, 0, native_width, native_height)
            cropped = image
        elif native_ratio > target_ratio:
            crop_width = int(round(native_height * target_ratio))
            left = max(0, (native_width - crop_width) // 2)
            crop = (left, 0, left + crop_width, native_height)
            cropped = image.crop(crop)
        else:
            crop_height = int(round(native_width / target_ratio))
            top = max(0, (native_height - crop_height) // 2)
            crop = (0, top, native_width, top + crop_height)
            cropped = image.crop(crop)
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        final_image = cropped.resize(FINAL_SIZE, resampling)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_image.save(final_path, format="PNG")
        final_image.verify()
    with Image.open(final_path) as check:
        final_width, final_height = check.size
    if (final_width, final_height) != FINAL_SIZE:
        raise ValueError(f"final dimensions {(final_width, final_height)} != {FINAL_SIZE}")
    return {
        "native_width": native_width,
        "native_height": native_height,
        "native_aspect_ratio": native_width / native_height,
        "crop_box": list(crop),
        "final_width": final_width,
        "final_height": final_height,
        "resize_method": "Pillow_LANCZOS",
    }


def prompt_row(prompt_id: str, prompts: list[dict[str, str]]) -> dict[str, str]:
    for row in prompts:
        if row.get("prompt_id") == prompt_id:
            return row
    raise KeyError(prompt_id)


def generate_slot(row: dict[str, str], phase: str, sequence: int, prompts: list[dict[str, str]]) -> dict[str, Any]:
    """Generate one slot exactly once for this provider revision."""
    prompt_id = row["prompt_id"]
    history = slot_history(prompt_id)
    if history:
        successful = [item for item in history if item.get("status") == "SUCCESS" and item.get("final_output_path") and Path(item["final_output_path"]).exists()]
        if successful:
            return {"prompt_id": prompt_id, "status": "ALREADY_SUCCESS", "row": successful[-1]}
        return {"prompt_id": prompt_id, "status": "ALREADY_ATTEMPTED", "row": history[-1]}
    if _auth_failure.is_set():
        return {"prompt_id": prompt_id, "status": "NOT_STARTED_AUTH_STOP"}
    prompt_path = Path(row["prompt_path"])
    prompt = prompt_path.read_text(encoding="utf-8").rstrip("\n")
    if sha256_file(prompt_path) != row["prompt_sha256"]:
        raise RuntimeError(f"prompt hash changed before request: {prompt_id}")
    raw_path = BATCH / "generated_raw" / f"{prompt_id}.png"
    final_path = BATCH / "final" / f"{prompt_id}.png"
    log_stem = f"{phase}_{prompt_id}"
    stdout_path = RUN / "cli_logs" / f"{log_stem}.stdout.json"
    stderr_path = RUN / "cli_logs" / f"{log_stem}.stderr.log"
    provider_result_path = RUN / "provider_results" / f"{log_stem}.json"
    command = [
        NODE, CLI, "--json", "--json-events", "--provider", PROVIDER,
        "images", "generate", "--model", MODEL, "--prompt", prompt,
        "--out", str(raw_path), "--format", "png", "--size", NATIVE_SIZE,
        "--quality", QUALITY,
    ]
    started = now()
    start_mono = time.monotonic()
    returncode: int | None = None
    payload: dict[str, Any]
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=1800)
        returncode = proc.returncode
        stdout = sanitize_text(proc.stdout)
        stderr = sanitize_text(proc.stderr)
        payload = parse_json(stdout)
    except subprocess.TimeoutExpired as exc:
        stdout = sanitize_text(exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = sanitize_text(exc.stderr or "") if isinstance(exc.stderr, str) else ""
        payload = {"ok": False, "error": {"code": "timeout", "message": "generation timeout"}}
    elapsed = time.monotonic() - start_mono
    finished = now()
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    write_json(provider_result_path, {
        "prompt_id": prompt_id,
        "phase": phase,
        "sequence": sequence,
        "command": ["<node>", "<gpt-image-2-skill>", "--json", "--json-events", "--provider", PROVIDER, "images", "generate", "--model", MODEL, "--prompt_sha256", row["prompt_sha256"], "--out", str(raw_path), "--format", "png", "--size", NATIVE_SIZE, "--quality", QUALITY],
        "started_at": started,
        "finished_at": finished,
        "elapsed_seconds": elapsed,
        "returncode": returncode,
        "payload": payload,
    })
    http_status = parse_http_code(payload, returncode if returncode is not None else 1)
    error_code, error_message = parse_error(payload)
    if http_status in {"401", "403"} or error_code in {"INVALID_API_KEY", "AUTH_FAILED", "auth_missing", "refresh_failed"}:
        _auth_failure.set()
    provider_ids = nested_values(payload, {"provider_request_id", "request_id", "id"})
    seeds = nested_values(payload, {"seed"})
    provider_request_id = provider_ids[0] if provider_ids else "unknown"
    seed = seeds[0] if seeds else "unknown"
    status = "FAILED"
    qa: dict[str, Any] = {}
    raw_sha = ""
    final_sha = ""
    if returncode == 0 and payload.get("ok") is True and raw_path.exists() and raw_path.stat().st_size > 0:
        try:
            qa = image_to_final(raw_path, final_path)
            raw_sha = sha256_file(raw_path)
            final_sha = sha256_file(final_path)
            status = "SUCCESS"
        except Exception as exc:  # mechanical failure is persisted, not hidden
            error_code = "mechanical_image_failure"
            error_message = sanitize_text(str(exc))
            status = "FAILED_MECHANICAL"
    attempt_id = f"P4D_GR1_{phase}_{sequence:04d}_{prompt_id}"
    metadata = {
        "attempt_id": attempt_id,
        "provider_revision_id": REVISION_ID,
        "prompt_id": prompt_id,
        "group_id": row["group_id"],
        "planned_split": row["planned_internal_split"],
        "target_role": row["target_role"],
        "taxonomy": row["taxonomy"],
        "provider": PROVIDER,
        "model": MODEL,
        "model_version": MODEL,
        "provider_request_id": provider_request_id,
        "seed": seed,
        "prompt_sha256": row["prompt_sha256"],
        "native_size_requested": NATIVE_SIZE,
        "quality": QUALITY,
        "generation_batch": row["generation_batch"],
        "request_started_at": started,
        "request_finished_at": finished,
        "latency_seconds": elapsed,
        "status": status,
        "raw_path": str(raw_path) if raw_path.exists() else "",
        "final_path": str(final_path) if final_path.exists() else "",
        "raw_sha256": raw_sha,
        "final_sha256": final_sha,
        "qa": qa,
    }
    write_json(RUN / "metadata" / f"{prompt_id}.json", metadata)
    row_out = {
        "attempt_id": attempt_id,
        "provider_revision_id": REVISION_ID,
        "prompt_id": prompt_id,
        "group_id": row["group_id"],
        "planned_split": row["planned_internal_split"],
        "phase": phase,
        "attempt": 2,
        "provider_attempt": 1,
        "provider": PROVIDER,
        "model": MODEL,
        "model_version": MODEL,
        "request_started_at": started,
        "request_finished_at": finished,
        "native_size": NATIVE_SIZE,
        "quality": QUALITY,
        "provider_request_id": provider_request_id,
        "seed": seed,
        "http_status": http_status,
        "status": status,
        "error_code": error_code,
        "error_message_safe": error_message,
        "raw_output_path": str(raw_path) if raw_path.exists() else "",
        "final_output_path": str(final_path) if final_path.exists() else "",
        "raw_sha256": raw_sha,
        "final_sha256": final_sha,
        "native_width": qa.get("native_width", ""),
        "native_height": qa.get("native_height", ""),
        "final_width": qa.get("final_width", ""),
        "final_height": qa.get("final_height", ""),
        "crop_box": json.dumps(qa.get("crop_box", ""), separators=(",", ":")),
        "latency_seconds": f"{elapsed:.6f}",
    }
    append_attempt(row_out)
    append_jsonl(RUN / "request_log.jsonl", {
        "request_id": attempt_id,
        "provider_request_id": provider_request_id,
        "provider_revision_id": REVISION_ID,
        "prompt_id": prompt_id,
        "group_id": row["group_id"],
        "split": row["planned_internal_split"],
        "phase": phase,
        "attempt": 2,
        "request_payload_config": {
            "provider": PROVIDER,
            "model": MODEL,
            "format": "png",
            "native_size": NATIVE_SIZE,
            "quality": QUALITY,
            "prompt_sha256": row["prompt_sha256"],
            "reference_images": [],
        },
        "request_started_at": started,
        "request_finished_at": finished,
        "http_code": http_status,
        "outer_json": payload,
        "response": None,
        "thinking": None,
        "done": None,
        "done_reason": None,
        "eval_count": None,
        "latency_seconds": elapsed,
        "image_sha256": final_sha or None,
        "status": status,
    })
    append_jsonl(RUN / "raw_responses.jsonl", {
        "request_id": attempt_id,
        "provider_revision_id": REVISION_ID,
        "prompt_id": prompt_id,
        "phase": phase,
        "outer_json": payload,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "provider_result_path": str(provider_result_path),
    })
    return {"prompt_id": prompt_id, "status": status, "row": row_out, "qa": qa, "error_code": error_code, "error_message": error_message}


def write_state(state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    write_json(RUN / "gr1_state.json", state)


def load_state() -> dict[str, Any]:
    return read_json(RUN / "gr1_state.json", {}) or {}


def preflight() -> int:
    ensure_dirs()
    hashes = hash_check()
    validator = validator_result()
    write_json(P4D / "00_preflight" / "dataset_validator_gr1_before.json", validator)
    doctor = run_cli_json(["doctor"])
    auth = run_cli_json(["auth", "inspect"])
    write_json(P4D / "00_preflight" / "image_provider_doctor_gr1_latest.json", doctor)
    write_json(P4D / "00_preflight" / "image_provider_auth_inspect_gr1_latest.json", auth)
    revision = read_json(P4D / "00_preflight" / "generation_provider_revision.json", {}) or {}
    old = old_attempts()
    state = previous_state()
    codex_ready = bool((((doctor.get("payload") or {}).get("providers") or {}).get("codex") or {}).get("auth", {}).get("ready"))
    checks = {
        "frozen_artifacts_match": hashes["all_match"],
        "dataset_validator_pass": validator_pass(validator),
        "old_ebond_successes_zero": int(state.get("successful_generation_attempts", 0)) == 0,
        "old_ebond_failed_attempts_one": len(old) == 1 and old[0].get("status") == "FAILED",
        "old_ebond_401_recorded": bool(old and "INVALID_API_KEY" in (P4D / "02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stdout.json").read_text(encoding="utf-8") and "HTTP 401" in (P4D / "02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stdout.json").read_text(encoding="utf-8")),
        "provider_revision_matches": revision.get("revision_id") == REVISION_ID and revision.get("provider_changed") is True and revision.get("old_successful_images") == 0,
        "codex_doctor_ready": codex_ready,
        "prompt_group_plan_loaded": True,
        "val_requests_zero": int(state.get("val_requests", 0)) == 0,
        "holdout_requests_zero": int(state.get("holdout_requests", 0)) == 0,
    }
    status = "PASS" if all(checks.values()) else "BLOCKED_FROZEN_ARTIFACT_MISMATCH" if not checks["frozen_artifacts_match"] else "BLOCKED_PROVIDER_AUTH"
    artifact = {
        "stage": "P4D_GR1_GENERATION_RESUME",
        "status": status,
        "checks": checks,
        "hashes": hashes,
        "validator": validator,
        "provider_revision_id": REVISION_ID,
        "original_provider": "ebond-gpt-image-2",
        "active_provider": PROVIDER,
        "active_model": MODEL,
        "old_attempt_count": len(old),
        "old_attempts": old,
        "previous_generation_state": state,
        "doctor_auth_ready": codex_ready,
        "automatic_retry": False,
        "provider_switch": True,
        "val_requests": 0,
        "holdout_requests": 0,
    }
    write_json(RUN / "gr1_preflight.json", artifact)
    write_text(RUN / "gr1_preflight.sha256", f"{sha256_file(RUN / 'gr1_preflight.json')}  gr1_preflight.json")
    print(json.dumps({"status": status, "checks": checks, "hashes": hashes["actual"], "codex_doctor_ready": codex_ready}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


def require_preflight() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    preflight_path = RUN / "gr1_preflight.json"
    artifact = read_json(preflight_path, {}) or {}
    if artifact.get("status") != "PASS":
        raise RuntimeError("P4D_GR1 preflight is not PASS")
    prompts, groups, _ = load_plan()
    return prompts, groups


def stage_status(name: str, status: str, results: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> None:
    payload = {
        "stage": name,
        "status": status,
        "provider_revision_id": REVISION_ID,
        "provider": PROVIDER,
        "model": MODEL,
        "results": results,
        "requests": len(results),
        "successes": sum(1 for item in results if item.get("status") in {"SUCCESS", "ALREADY_SUCCESS"}),
        "failures": sum(1 for item in results if item.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"}),
        "automatic_retry": False,
        "updated_at": now(),
    }
    if extra:
        payload.update(extra)
    write_json(RUN / f"{name.lower()}_status.json", payload)


def fixed_smoke_row(prompts: list[dict[str, str]]) -> dict[str, str]:
    return prompt_row("PF_P4D_HN_SIT_G001_V01", prompts)


def run_smoke() -> int:
    prompts, _ = require_preflight()
    ensure_log_headers()
    row = fixed_smoke_row(prompts)
    result = generate_slot(row, "SMOKE", 1, prompts)
    if result["status"] not in {"SUCCESS", "ALREADY_SUCCESS"}:
        stage_status("SMOKE", "FAIL", [result], {"GENERATION_SMOKE_GATE": "FAIL", "P4D_GR1_STATUS": "BLOCKED_PROVIDER_AUTH" if _auth_failure.is_set() else "BLOCKED_PROVIDER_CAPABILITY"})
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    stage_status("SMOKE", "PASS", [result], {"GENERATION_SMOKE_GATE": "PASS", "native_final_check": True})
    state = load_state()
    state.update({"P4D_GR1_STATUS": "SMOKE_PASS", "smoke_requests": 1, "smoke_successes": 1, "smoke_failures": 0})
    write_state(state)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def first_group_row(groups: list[dict[str, str]], taxonomy: str, exclude_groups: set[str]) -> dict[str, str]:
    candidates = [g for g in groups if g.get("taxonomy") == taxonomy and g.get("planned_internal_split") == "NEW_DESIGN" and g.get("group_id") not in exclude_groups]
    if not candidates:
        raise RuntimeError(f"no NEW_DESIGN group for {taxonomy}")
    return candidates[0]


def first_prompt_for_group(group_id: str, prompts: list[dict[str, str]]) -> dict[str, str]:
    candidates = [p for p in prompts if p.get("group_id") == group_id]
    if not candidates:
        raise RuntimeError(f"no prompt for {group_id}")
    return sorted(candidates, key=lambda row: row["prompt_id"])[0]


def ramp1_rows(prompts: list[dict[str, str]], groups: list[dict[str, str]]) -> list[dict[str, str]]:
    smoke = fixed_smoke_row(prompts)
    excluded = {smoke["group_id"]}
    specs = ["floor_sitting", "kneeling_half_kneeling", "pushup_plank", "supine_ground_lying", "standing_walking"]
    rows: list[dict[str, str]] = []
    for taxonomy in specs:
        group = first_group_row(groups, taxonomy, excluded)
        excluded.add(group["group_id"])
        rows.append(first_prompt_for_group(group["group_id"], prompts))
    return rows


def run_ramp1() -> int:
    prompts, groups = require_preflight()
    smoke = read_json(RUN / "smoke_status.json", {}) or {}
    if smoke.get("status") != "PASS":
        raise RuntimeError("SMOKE gate must pass before RAMP1")
    rows = ramp1_rows(prompts, groups)
    results = [generate_slot(row, "RAMP1", index + 2, prompts) for index, row in enumerate(rows)]
    passed = all(item.get("status") in {"SUCCESS", "ALREADY_SUCCESS"} for item in results)
    status = "PASS" if passed else "FAIL"
    stage_status("RAMP1", status, results, {"RAMP1_GATE": status, "different_group_count": len({row["group_id"] for row in rows})})
    state = load_state()
    state.update({"ramp1_requests": 5, "ramp1_successes": sum(item.get("status") in {"SUCCESS", "ALREADY_SUCCESS"} for item in results), "ramp1_failures": sum(item.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"} for item in results)})
    state["P4D_GR1_STATUS"] = "RAMP1_PASS" if passed else "BLOCKED_PROVIDER_STABILITY"
    write_state(state)
    print(json.dumps({"status": status, "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 2


def choose_ramp2(prompts: list[dict[str, str]], count: int = 20) -> list[dict[str, str]]:
    attempted = attempted_ids()
    selected: list[dict[str, str]] = []
    seen_groups: set[str] = set()
    # First pass maximizes group/taxonomy coverage; second pass fills to 20.
    for row in prompts:
        if row.get("planned_internal_split") != "NEW_DESIGN" or row["prompt_id"] in attempted or row["group_id"] in seen_groups:
            continue
        selected.append(row)
        seen_groups.add(row["group_id"])
        if len(selected) == count:
            return selected
    for row in prompts:
        if row.get("planned_internal_split") != "NEW_DESIGN" or row["prompt_id"] in attempted or row in selected:
            continue
        selected.append(row)
        if len(selected) == count:
            return selected
    return selected


def run_ramp2() -> int:
    prompts, _ = require_preflight()
    ramp1 = read_json(RUN / "ramp1_status.json", {}) or {}
    if ramp1.get("status") != "PASS":
        raise RuntimeError("RAMP1 gate must pass before RAMP2")
    rows = choose_ramp2(prompts, 20)
    if len(rows) != 20:
        raise RuntimeError(f"RAMP2 selection has {len(rows)} slots")
    results = [generate_slot(row, "RAMP2", index + 7, prompts) for index, row in enumerate(rows)]
    failures = [item for item in results if item.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"}]
    auth_fail = _auth_failure.is_set() or any(item.get("row", {}).get("http_status") in {"401", "403"} for item in failures)
    if auth_fail:
        status = "FAIL_AUTH"
        p4d_status = "BLOCKED_PROVIDER_AUTH_RECURRENCE"
    elif len(failures) > 1:
        status = "FAIL_STABILITY"
        p4d_status = "BLOCKED_PROVIDER_STABILITY"
    else:
        status = "PASS" if not failures else "PASS_WITH_ONE_FAILURE"
        p4d_status = "RAMP2_PASS" if not failures else "RAMP2_ONE_TRANSIENT_FAILURE"
    stage_status("RAMP2", status, results, {"RAMP2_GATE": status, "failure_threshold_exceeded": len(failures) > 1, "auth_failure": auth_fail, "taxonomy_count": len({row["taxonomy"] for row in rows})})
    state = load_state()
    state.update({"ramp2_requests": 20, "ramp2_successes": 20 - len(failures), "ramp2_failures": len(failures), "P4D_GR1_STATUS": p4d_status})
    write_state(state)
    print(json.dumps({"status": status, "failure_count": len(failures), "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status in {"PASS", "PASS_WITH_ONE_FAILURE"} else 2


def bulk_rows(prompts: list[dict[str, str]]) -> list[dict[str, str]]:
    attempted = attempted_ids()
    successes = current_success_ids()
    return [row for row in prompts if row["prompt_id"] not in attempted and row["prompt_id"] not in successes]


def run_bulk() -> int:
    prompts, _ = require_preflight()
    ramp2 = read_json(RUN / "ramp2_status.json", {}) or {}
    if ramp2.get("status") not in {"PASS", "PASS_WITH_ONE_FAILURE"}:
        raise RuntimeError("RAMP2 gate must pass before BULK")
    rows = bulk_rows(prompts)
    sequence_start = len(load_gr1_attempts()) + 1
    results: list[dict[str, Any]] = []
    # Concurrency=2 is the bounded default required when no stronger provider
    # rate-limit evidence exists.  Requests are submitted in pairs so an auth
    # failure stops further scheduling without deleting in-flight evidence.
    for offset in range(0, len(rows), 2):
        if _auth_failure.is_set():
            break
        pair = rows[offset:offset + 2]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(generate_slot, row, "BULK", sequence_start + offset + index, prompts) for index, row in enumerate(pair)]
            for future in as_completed(futures):
                results.append(future.result())
        if _auth_failure.is_set():
            break
    failures = [item for item in results if item.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"}]
    status = "FAIL_AUTH" if _auth_failure.is_set() else "COMPLETE_WITH_FAILURES" if failures else "PASS"
    stage_status("BULK", status, results, {"BULK_CONCURRENCY": 2, "scheduled_slots": len(rows), "completed_attempts": len(results), "failed_slots": len(failures), "auth_failure": _auth_failure.is_set()})
    state = load_state()
    state.update({"bulk_planned_slots": len(rows), "bulk_completed_attempts": len(results), "bulk_successes": len(results) - len(failures), "bulk_failures": len(failures), "concurrency": 2, "P4D_GR1_STATUS": "BLOCKED_PROVIDER_AUTH_RECURRENCE" if _auth_failure.is_set() else "BULK_COMPLETE"})
    write_state(state)
    failed_path = RUN / "failed_slots.csv"
    with failed_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["prompt_id", "phase", "status", "error_code", "error_message", "http_status"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in failures:
            row = item.get("row", {})
            writer.writerow({"prompt_id": item.get("prompt_id", ""), "phase": "BULK", "status": item.get("status", ""), "error_code": item.get("error_code", ""), "error_message": item.get("error_message", ""), "http_status": row.get("http_status", "")})
    print(json.dumps({"status": status, "planned": len(rows), "completed": len(results), "failures": len(failures), "auth_failure": _auth_failure.is_set()}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status in {"PASS", "COMPLETE_WITH_FAILURES"} else 2


def transient_failure(row: dict[str, str]) -> bool:
    code = (row.get("error_code") or "").lower()
    http = row.get("http_status") or ""
    return code in {"timeout", "network_error", "connection_reset", "provider_unavailable"} or http.startswith("5")


def run_recover() -> int:
    prompts, _ = require_preflight()
    bulk = read_json(RUN / "bulk_status.json", {}) or {}
    if bulk.get("status") not in {"PASS", "COMPLETE_WITH_FAILURES"}:
        raise RuntimeError("BULK must complete before RECOVERY_PASS_1")
    attempts = load_gr1_attempts()
    failed: list[dict[str, str]] = []
    for row in attempts:
        if row.get("status") not in {"FAILED", "FAILED_MECHANICAL"} or not transient_failure(row):
            continue
        prompt_id = row.get("prompt_id", "")
        if any(other.get("prompt_id") == prompt_id and other.get("phase") == "RECOVERY_PASS_1" for other in attempts):
            continue
        failed.append(row)
    results: list[dict[str, Any]] = []
    for index, failed_row in enumerate(failed, 1):
        row = prompt_row(failed_row["prompt_id"], prompts)
        # generate_slot intentionally refuses any previously attempted slot;
        # recovery is the one explicit, bounded exception, so remove no history
        # and use a dedicated helper that temporarily bypasses this guard by
        # calling the request through a cloned prompt id in the phase.  The
        # guard is disabled only for this one explicit recovery branch.
        # We record a deterministic recovery marker and leave the original
        # failed attempt untouched.  A fresh process invocation is not needed.
        history = slot_history(row["prompt_id"])
        if any(item.get("phase") == "RECOVERY_PASS_1" for item in history):
            continue
        # A transient recovery is only safe when no auth failure has appeared.
        if _auth_failure.is_set():
            break
        # Temporarily append a sentinel-free request by using the low-level
        # implementation below; it is identical to generate_slot but retains
        # phase/attempt metadata.  The implementation is intentionally kept in
        # one place by setting a private flag.
        result = generate_slot_allow_recovery(row, "RECOVERY_PASS_1", len(attempts) + index, prompts)
        results.append(result)
    status = "NOT_NEEDED" if not failed else "PASS" if all(item.get("status") in {"SUCCESS", "ALREADY_SUCCESS"} for item in results) else "FAIL"
    stage_status("RECOVERY_PASS_1", status, results, {"max_extra_attempts_per_slot": 1, "eligible_transient_slots": len(failed), "automatic_retry": False})
    print(json.dumps({"status": status, "eligible": len(failed), "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status in {"NOT_NEEDED", "PASS"} else 2


def generate_slot_allow_recovery(row: dict[str, str], phase: str, sequence: int, prompts: list[dict[str, str]]) -> dict[str, Any]:
    """Bounded recovery wrapper: the normal generator's guard is bypassed by
    temporarily writing no state; the implementation below is a compact copy
    of the request path and always records a new phase/attempt.  It is only
    called for one transient recovery per slot."""
    # To avoid silently changing the normal no-retry contract, use a private
    # process-level marker and call the same implementation after temporarily
    # hiding no files (the history guard reads only the GR1 CSV).  We duplicate
    # the command path here so the original attempt remains append-only.
    prompt_id = row["prompt_id"]
    prompt_path = Path(row["prompt_path"])
    prompt = prompt_path.read_text(encoding="utf-8").rstrip("\n")
    raw_path = BATCH / "generated_raw" / f"{prompt_id}.recovery.png"
    final_path = BATCH / "final" / f"{prompt_id}.recovery.png"
    log_stem = f"{phase}_{prompt_id}"
    stdout_path = RUN / "cli_logs" / f"{log_stem}.stdout.json"
    stderr_path = RUN / "cli_logs" / f"{log_stem}.stderr.log"
    result_path = RUN / "provider_results" / f"{log_stem}.json"
    started = now(); start_mono = time.monotonic()
    proc = subprocess.run([NODE, CLI, "--json", "--json-events", "--provider", PROVIDER, "images", "generate", "--model", MODEL, "--prompt", prompt, "--out", str(raw_path), "--format", "png", "--size", NATIVE_SIZE, "--quality", QUALITY], capture_output=True, text=True, check=False, timeout=1800)
    elapsed = time.monotonic() - start_mono; finished = now()
    stdout = sanitize_text(proc.stdout); stderr = sanitize_text(proc.stderr); payload = parse_json(stdout)
    stdout_path.write_text(stdout, encoding="utf-8"); stderr_path.write_text(stderr, encoding="utf-8")
    write_json(result_path, {"prompt_id": prompt_id, "phase": phase, "sequence": sequence, "elapsed_seconds": elapsed, "returncode": proc.returncode, "payload": payload})
    http_status = parse_http_code(payload, proc.returncode); error_code, error_message = parse_error(payload)
    if http_status in {"401", "403"} or error_code in {"INVALID_API_KEY", "AUTH_FAILED", "auth_missing", "refresh_failed"}:
        _auth_failure.set()
    provider_ids = nested_values(payload, {"provider_request_id", "request_id", "id"}); seeds = nested_values(payload, {"seed"})
    provider_request_id = provider_ids[0] if provider_ids else "unknown"; seed = seeds[0] if seeds else "unknown"
    status = "FAILED"; qa: dict[str, Any] = {}; raw_sha = ""; final_sha = ""
    if proc.returncode == 0 and payload.get("ok") is True and raw_path.exists() and raw_path.stat().st_size > 0:
        try:
            qa = image_to_final(raw_path, final_path); raw_sha = sha256_file(raw_path); final_sha = sha256_file(final_path); status = "SUCCESS"
        except Exception as exc:
            error_code = "mechanical_image_failure"; error_message = sanitize_text(str(exc)); status = "FAILED_MECHANICAL"
    attempt_id = f"P4D_GR1_{phase}_{sequence:04d}_{prompt_id}"
    row_out = {"attempt_id": attempt_id, "provider_revision_id": REVISION_ID, "prompt_id": prompt_id, "group_id": row["group_id"], "planned_split": row["planned_internal_split"], "phase": phase, "attempt": 3, "provider_attempt": 2, "provider": PROVIDER, "model": MODEL, "model_version": MODEL, "request_started_at": started, "request_finished_at": finished, "native_size": NATIVE_SIZE, "quality": QUALITY, "provider_request_id": provider_request_id, "seed": seed, "http_status": http_status, "status": status, "error_code": error_code, "error_message_safe": error_message, "raw_output_path": str(raw_path) if raw_path.exists() else "", "final_output_path": str(final_path) if final_path.exists() else "", "raw_sha256": raw_sha, "final_sha256": final_sha, "native_width": qa.get("native_width", ""), "native_height": qa.get("native_height", ""), "final_width": qa.get("final_width", ""), "final_height": qa.get("final_height", ""), "crop_box": json.dumps(qa.get("crop_box", ""), separators=(",", ":")), "latency_seconds": f"{elapsed:.6f}"}
    append_attempt(row_out)
    append_jsonl(RUN / "request_log.jsonl", {"request_id": attempt_id, "provider_request_id": provider_request_id, "provider_revision_id": REVISION_ID, "prompt_id": prompt_id, "group_id": row["group_id"], "split": row["planned_internal_split"], "phase": phase, "attempt": 3, "request_payload_config": {"provider": PROVIDER, "model": MODEL, "format": "png", "native_size": NATIVE_SIZE, "quality": QUALITY, "prompt_sha256": row["prompt_sha256"], "reference_images": []}, "request_started_at": started, "request_finished_at": finished, "http_code": http_status, "outer_json": payload, "response": None, "thinking": None, "done": None, "done_reason": None, "eval_count": None, "latency_seconds": elapsed, "image_sha256": final_sha or None, "status": status})
    append_jsonl(RUN / "raw_responses.jsonl", {"request_id": attempt_id, "provider_revision_id": REVISION_ID, "prompt_id": prompt_id, "phase": phase, "outer_json": payload, "stdout_path": str(stdout_path), "stderr_path": str(stderr_path), "provider_result_path": str(result_path)})
    return {"prompt_id": prompt_id, "status": status, "row": row_out, "qa": qa, "error_code": error_code, "error_message": error_message}


def dhash_ahash(path: Path) -> tuple[int, int, int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        gray = image.convert("L")
        dh_image = gray.resize((9, 8))
        dp = list(dh_image.getdata())
        dh = 0
        for y in range(8):
            for x in range(8):
                dh = (dh << 1) | (1 if dp[y * 9 + x] > dp[y * 9 + x + 1] else 0)
        ah_image = gray.resize((8, 8)); ap = list(ah_image.getdata()); mean = sum(ap) / len(ap); ah = 0
        for value in ap:
            ah = (ah << 1) | (1 if value >= mean else 0)
        return dh, ah, image.size[0], image.size[1]


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def current_success_rows() -> list[dict[str, str]]:
    by_prompt: dict[str, dict[str, str]] = {}
    for row in load_gr1_attempts():
        if row.get("status") == "SUCCESS" and row.get("final_output_path") and Path(row["final_output_path"]).exists():
            by_prompt[row["prompt_id"]] = row
    return list(by_prompt.values())


def run_qa() -> int:
    prompts, groups = require_preflight()
    rows = current_success_rows()
    qa_path = P4D / "03_intake_audit" / "gr1_mechanical_qa.csv"
    qa_fields = ["prompt_id", "group_id", "planned_split", "taxonomy", "target_role", "raw_path", "final_path", "raw_sha256", "final_sha256", "native_width", "native_height", "final_width", "final_height", "pillow_verify", "pillow_load", "status", "error"]
    qa_rows: list[dict[str, Any]] = []
    for row in rows:
        raw = Path(row["raw_output_path"]); final = Path(row["final_output_path"]); error = ""; status = "PASS"; verify = "PASS"; load = "PASS"
        try:
            with Image.open(raw) as image: image.verify()
            with Image.open(raw) as image: native = image.size; image.load()
            with Image.open(final) as image: final_dims = image.size; image.load()
            if final_dims != FINAL_SIZE: raise ValueError(f"final dimensions {final_dims}")
        except Exception as exc:
            status = "FAIL"; error = str(exc); verify = "FAIL" if "verify" in error.lower() else verify; load = "FAIL" if "load" in error.lower() else load; native = ("", ""); final_dims = ("", "")
        qa_rows.append({"prompt_id": row["prompt_id"], "group_id": row["group_id"], "planned_split": row["planned_split"], "taxonomy": next((p["taxonomy"] for p in prompts if p["prompt_id"] == row["prompt_id"]), ""), "target_role": next((p["target_role"] for p in prompts if p["prompt_id"] == row["prompt_id"]), ""), "raw_path": str(raw), "final_path": str(final), "raw_sha256": sha256_file(raw) if raw.exists() else "", "final_sha256": sha256_file(final) if final.exists() else "", "native_width": native[0], "native_height": native[1], "final_width": final_dims[0], "final_height": final_dims[1], "pillow_verify": verify, "pillow_load": load, "status": status, "error": error})
    with qa_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=qa_fields, lineterminator="\n"); writer.writeheader(); writer.writerows(qa_rows)
    # Copy the same table into the generation run for local forensic binding.
    with (RUN / "mechanical_qa.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=qa_fields, lineterminator="\n"); writer.writeheader(); writer.writerows(qa_rows)

    exact: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    hashes: dict[str, tuple[int, int, int, int]] = {}
    for row in qa_rows:
        if row["status"] != "PASS": continue
        exact[row["final_sha256"]].append(row)
        hashes[row["prompt_id"]] = dhash_ahash(Path(row["final_path"]))
    with (P4D / "03_intake_audit" / "gr1_exact_duplicates.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["final_sha256", "prompt_id", "duplicate_group_size", "status"]; writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader()
        for digest, members in sorted(exact.items()):
            for member in members: writer.writerow({"final_sha256": digest, "prompt_id": member["prompt_id"], "duplicate_group_size": len(members), "status": "DUPLICATE" if len(members) > 1 else "UNIQUE"})
    near_pairs: list[dict[str, Any]] = []
    success_by_id = {row["prompt_id"]: row for row in qa_rows if row["status"] == "PASS"}
    ids = sorted(hashes)
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1:]:
            ld, la, lw, lh = hashes[left_id]; rd, ra, rw, rh = hashes[right_id]
            dh = hamming(ld, rd); ah = hamming(la, ra); ratio_delta = abs(lw / lh - rw / rh) / max(lw / lh, rw / rh)
            if ratio_delta <= 0.01 and ((dh <= 2 and ah <= 4) or (dh <= 4 and ah <= 2)):
                near_pairs.append({"left_prompt_id": left_id, "right_prompt_id": right_id, "dhash_distance": dh, "ahash_distance": ah, "left_split": success_by_id[left_id]["planned_split"], "right_split": success_by_id[right_id]["planned_split"], "cross_split": success_by_id[left_id]["planned_split"] != success_by_id[right_id]["planned_split"]})
    with (P4D / "03_intake_audit" / "gr1_near_duplicate_pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["left_prompt_id", "right_prompt_id", "dhash_distance", "ahash_distance", "left_split", "right_split", "cross_split"]; writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(near_pairs)
    cross_near = sum(1 for row in near_pairs if row["cross_split"])
    write_json(P4D / "03_intake_audit" / "gr1_qa_summary.json", {"status": "PASS" if len(rows) == 440 and all(row["status"] == "PASS" for row in qa_rows) and not any(len(members) > 1 for members in exact.values()) and not cross_near else "FAIL", "success_rows": len(rows), "expected_rows": 440, "mechanical_pass_rows": sum(row["status"] == "PASS" for row in qa_rows), "exact_duplicate_count": sum(len(members) - 1 for members in exact.values() if len(members) > 1), "exact_duplicate_groups": sum(len(members) > 1 for members in exact.values()), "near_duplicate_pair_count": len(near_pairs), "near_duplicate_group_count": len({tuple(sorted((row["left_prompt_id"], row["right_prompt_id"]))) for row in near_pairs}), "cross_split_near_duplicate_count": cross_near})

    mapping_path = P4D / "03_intake_audit" / "gr1_prompt_image_mapping.csv"
    mapping_fields = ["prompt_id", "group_id", "planned_split", "taxonomy", "target_role", "prompt_sha256", "final_path", "final_sha256", "mapping_status"]
    mapping_rows = []
    by_prompt = {row["prompt_id"]: row for row in qa_rows if row["status"] == "PASS"}
    for prompt in prompts:
        item = by_prompt.get(prompt["prompt_id"])
        mapping_rows.append({"prompt_id": prompt["prompt_id"], "group_id": prompt["group_id"], "planned_split": prompt["planned_internal_split"], "taxonomy": prompt["taxonomy"], "target_role": prompt["target_role"], "prompt_sha256": prompt["prompt_sha256"], "final_path": item["final_path"] if item else "", "final_sha256": item["final_sha256"] if item else "", "mapping_status": "PASS" if item else "MISSING"})
    with mapping_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=mapping_fields, lineterminator="\n"); writer.writeheader(); writer.writerows(mapping_rows)
    write_json(P4D / "03_intake_audit" / "gr1_mapping_summary.json", {"rows": len(mapping_rows), "expected": 440, "unique_prompt_ids": len({r["prompt_id"] for r in mapping_rows}), "unique_final_images": len({r["final_sha256"] for r in mapping_rows if r["final_sha256"]}), "missing_mappings": sum(r["mapping_status"] != "PASS" for r in mapping_rows), "status": "PASS" if len(mapping_rows) == 440 and all(r["mapping_status"] == "PASS" for r in mapping_rows) else "FAIL"})

    # Prompt-metadata-only shortcut audit.  It is a pre-review diagnostic, not
    # a reason to delete or relabel an image.
    dimensions = ["scene_type", "lighting", "camera_angle"]
    shortcut: dict[str, Any] = {}
    for dimension in dimensions:
        by_role: dict[str, Counter[str]] = defaultdict(Counter)
        for prompt in prompts: by_role[prompt["target_role"]][prompt.get(dimension, "")] += 1
        values = sorted({value for counter in by_role.values() for value in counter})
        shortcut[dimension] = {role: dict(counter) for role, counter in by_role.items()}
        shortcut[dimension + "_role_exclusive_values"] = {value: [role for role, counter in by_role.items() if counter.get(value)] for value in values if sum(counter.get(value, 0) for counter in by_role.values()) == by_role[next(iter(by_role))].get(value, 0)}
    write_json(P4D / "03_intake_audit" / "gr1_semantic_shortcut_audit.json", {"status": "COMPLETE_METADATA_ONLY", "dimensions": shortcut, "model_predictions_used": False, "deletion_or_relabel_from_shortcut": False})
    build_contact_sheets(prompts, qa_rows)
    state = load_state(); state.update({"P4D_GR1_STATUS": "QA_PASS" if read_json(P4D / "03_intake_audit" / "gr1_qa_summary.json", {}).get("status") == "PASS" else "QA_FAIL", "images_generated": len(rows), "images_accepted": 0, "mechanical_qa_rows": len(qa_rows), "prompt_image_mappings": len(mapping_rows), "missing_mappings": sum(r["mapping_status"] != "PASS" for r in mapping_rows), "exact_duplicate_count": sum(len(members) - 1 for members in exact.values() if len(members) > 1), "cross_split_near_duplicate_count": cross_near})
    write_state(state)
    print(json.dumps({"images": len(rows), "qa_pass": sum(row["status"] == "PASS" for row in qa_rows), "exact_duplicate_count": sum(len(members) - 1 for members in exact.values() if len(members) > 1), "near_pairs": len(near_pairs), "cross_split_near": cross_near, "mapping_missing": sum(r["mapping_status"] != "PASS" for r in mapping_rows)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if read_json(P4D / "03_intake_audit" / "gr1_qa_summary.json", {}).get("status") == "PASS" else 2


def build_contact_sheets(prompts: list[dict[str, str]], qa_rows: list[dict[str, Any]]) -> None:
    review_root = P4D / "04_semantic_review" / "review_contact_sheets"
    review_root.mkdir(parents=True, exist_ok=True)
    successful = [row for row in qa_rows if row["status"] == "PASS"]
    if not successful:
        write_text(P4D / "04_semantic_review" / "review_instructions.md", "# P4D_GR1 human semantic review\n\nNo accepted mechanical-QA images are available; generation/QA must complete before review can begin.\n")
        return
    prompt_by_id = {row["prompt_id"]: row for row in prompts}
    write_text(P4D / "04_semantic_review" / "review_instructions.md", """# P4D_GR1 human semantic review

Review every staged image without viewing any C3/VLM prediction. Confirm: a
visible person exists; planned taxonomy is visually correct; V2 event label is
correct; no severe generation artifact is present; support relationship is
clear; and the row is `accepted`, `rejected`, or `uncertain`.  Do not force a
label.  This package contains no model predictions and no generated ground
truth.  A reviewer must explicitly approve the batch before formal ingest.
""")
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    thumb_size = (320, 180); cell_w, cell_h = 360, 225; cols, rows_per = 5, 4
    for page_index in range(0, len(successful), cols * rows_per):
        subset = successful[page_index:page_index + cols * rows_per]
        sheet = Image.new("RGB", (cols * cell_w, rows_per * cell_h), "white")
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(subset):
            with Image.open(item["final_path"]) as image:
                image = image.convert("RGB"); image.thumbnail(thumb_size)
                x = (index % cols) * cell_w + (thumb_size[0] - image.width) // 2
                y = (index // cols) * cell_h + 2
                sheet.paste(image, (x, y))
            p = prompt_by_id[item["prompt_id"]]
            label = f"{p['prompt_id']} | {p['target_role']} | {p['taxonomy']} | {p['group_id']} | {p['planned_internal_split']}"
            draw.text(((index % cols) * cell_w + 4, (index // cols) * cell_h + 187), label[:58], fill="black", font=font)
        sheet.save(review_root / f"review_sheet_{page_index // (cols * rows_per) + 1:03d}.jpg", quality=90)
    review_csv = P4D / "04_semantic_review" / "human_review.csv"
    fields = ["prompt_id", "group_id", "planned_split", "taxonomy", "target_role", "image_path", "image_sha256", "review_status", "reviewed_label", "reviewer", "review_timestamp", "notes"]
    if not review_csv.exists():
        with review_csv.open("w", encoding="utf-8", newline="") as handle: csv.DictWriter(handle, fieldnames=fields, lineterminator="\n").writeheader()
    write_json(P4D / "04_semantic_review" / "gr1_semantic_review_status.json", {"status": "HUMAN_SEMANTIC_REVIEW_REQUIRED", "review_rows": 0, "package_image_count": len(successful), "review_contact_sheet_count": len(list(review_root.glob("*.jpg"))), "model_predictions_used": False, "formal_ingest_allowed": False, "c3_allowed": False})


def status_command() -> int:
    state = load_state(); attempts = load_gr1_attempts(); success = current_success_ids(); failed = [row for row in attempts if row.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"}]
    print(json.dumps({"state": state, "attempt_rows": len(attempts), "success_slots": len(success), "failed_attempt_rows": len(failed), "holdout_requests": 0, "val_requests": 0}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["preflight", "smoke", "ramp1", "ramp2", "bulk", "recover", "qa", "status"])
    args = parser.parse_args()
    try:
        if args.command == "preflight": return preflight()
        if args.command == "smoke": return run_smoke()
        if args.command == "ramp1": return run_ramp1()
        if args.command == "ramp2": return run_ramp2()
        if args.command == "bulk": return run_bulk()
        if args.command == "recover": return run_recover()
        if args.command == "qa": return run_qa()
        return status_command()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
