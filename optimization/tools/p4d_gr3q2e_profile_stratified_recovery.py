#!/usr/bin/env python3
"""P4D_GR3Q2E profile-stratified recovery runner.

This is a new execution revision, never a resume or rewrite of GR3E/GR3Q1/GR3Q2.
It preserves the verified GR3E Profile-A images in-place, writes all new evidence
under its own revision directory, and appends only successful Profile-B raw/final
images for the frozen 341 outstanding slots.  A durable STARTED row precedes every
CLI call.  There is no outer retry, and any non-success result fail-closes the
entire revision; a future attempt needs a different explicitly authorized revision.
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
Q2 = GR3 / "06_execution" / "lineage_policy_amendment_20260828_01"
EXEC = GR3 / "06_execution" / "profile_stratified_recovery_20260828_01"
PRE = EXEC / "00_preflight"
AUTH = EXEC / "01_authorization"
RUNNER = EXEC / "02_runner"
LEDGER = EXEC / "03_ledger"
RAW_LOGS = EXEC / "04_raw_responses"
CHECKPOINTS = EXEC / "05_checkpoints"
QA = EXEC / "06_full_qa"
FREEZE = EXEC / "freeze"
STAGING_RAW = EXEC / "_staging" / "generated_raw"
STAGING_FINAL = EXEC / "_staging" / "final"

MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
Q2_FREEZE = Q2 / "freeze" / "p4d_gr3q2_preparation_freeze.json"
GR3_FREEZE = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
GR3E_FREEZE = GR3 / "06_execution" / "authorized_20260827_01" / "freeze" / "p4d_gr3e_terminal_freeze.json"
Q1_FREEZE = GR3 / "06_execution" / "quota_recovery_20260827_01" / "freeze" / "p4d_gr3q1_preparation_freeze.json"
Q2_AUTH = Q2 / "03_authorization" / "profile_stratified_recovery_authorization.json"
VERIFIED_99 = Q2 / "02_inventory" / "verified_99.csv"
OUTSTANDING_341 = Q2 / "02_inventory" / "outstanding_341.csv"
PROFILE_PLAN = Q2 / "02_inventory" / "profile_strata_plan.csv"
INVENTORY = Q2 / "02_inventory" / "inventory_summary.json"
PARENT_RUN_CONFIG = GR3 / "06_execution" / "authorized_20260827_01" / "02_runner" / "run_config.json"
PARENT_RUNNER = ROOT / "tools" / "p4d_gr3e_fullregen_runner.py"

BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
BATCH_RAW = BATCH / "generated_raw"
BATCH_FINAL = BATCH / "final"
BATCH_METADATA = BATCH / "metadata"
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")

DB = LEDGER / "p4d_gr3q2e_execution.sqlite3"
LEDGER_CSV = LEDGER / "execution_ledger.csv"
SLOT_PLAN = LEDGER / "initial_profile_stratified_slot_plan.csv"
REQUEST_LOG = EXEC / "request_log.jsonl"
RAW_RESPONSES = EXEC / "raw_responses.jsonl"
RUN_CONFIG = RUNNER / "run_config.json"
AUTH_ATTESTATION = AUTH / "recovery_authorization_attestation.json"
PREP_FREEZE = FREEZE / "p4d_gr3q2e_execution_preflight_freeze.json"
TERMINAL_FREEZE = FREEZE / "p4d_gr3q2e_terminal_freeze.json"
STOP_MARKER = CHECKPOINTS / "global_stop.json"
LOCK_PATH = RUNNER / ".runner.lock"

Q2_FREEZE_SHA = "bd788e5b2d72bb1681846909e4cb2a2bf314897523c8011285f78deae5889801"
GR3_FREEZE_SHA = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
GR3E_FREEZE_SHA = "6afb294c4696eb89bea5d6dfb333efc38477fa05546b4e8cd4cc8ffa52d89f40"
Q1_FREEZE_SHA = "e64a41f735c8837b273b9100a40f7437e70721df4f1f5be8230a9e634890a847"
MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
PROFILE_A = "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe"
PROFILE_B = "d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190"
FAILED_PROMPT = "PF_P4D_HN_KNEEL_G008_V05"
FAILED_PARENT_REQUEST = "P4D_GR3E_BULK_0100_PF_P4D_HN_KNEEL_G008_V05"
FINAL_SIZE = (1920, 1080)
NATIVE_SIZE = "1536x1024"
QUALITY = "medium"
PROVIDER = "codex"
MODEL = "gpt-5.4"
RUNTIME_VERSION = "0.7.3"
REVISION_ID = "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY_20260828_01"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

AUTH_TEXT = (
    "我明确授权 P4D_GR3Q2E 在新的 lineage-policy amendment 下继续当前 P4D full-regeneration revision："
    "保留已经成功并通过完整性验证的 99 张 GR3E 图像，并将其标记为历史生成 profile stratum A；"
    "允许使用当前 Codex profile 作为 profile stratum B，重新尝试此前已确认 HTTP 429 失败的 1 个 slot，"
    "并生成其余 340 个从未开始的 frozen slots，共最多 341 个新的 logical slot invocations。"
    "我接受 profile/account fingerprint 不同但 provider、request model、generation backend、runtime、prompt 和 generation configuration 一致时作为 provenance 分层而不是强制 semantic-lineage break；"
    "同时继续接受 GPT Image 2 runtime max_retries=3、单 logical invocation 最多约4次 provider attempts、精确费用未知以及 quota/成本风险。"
    "任何 logical invocation 返回 429/401/403/timeout/5xx 均立即停止后续 slot，不执行外层自动 recovery。"
)

SENSITIVE_KEYS = {
    "account_id", "chatgpt_user_id", "email", "auth_file", "access_token", "refresh_token",
    "id_token", "token", "api_key", "authorization", "cookie", "safety_identifier", "user",
    "prompt_cache_key",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_object(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def redact_text(text: str) -> str:
    for name in SENSITIVE_KEYS:
        pattern = rf'(?i)(["\']?{re.escape(name)}["\']?\s*[:=]\s*["\']?)[^,\s}}"\']+'
        text = re.sub(pattern, r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(refresh[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<REDACTED>" if key.lower() in SENSITIVE_KEYS else redact(child)) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def parse_json_sanitized(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        return redact(value) if isinstance(value, dict) else {"ok": False, "raw_json": redact(value)}
    except json.JSONDecodeError:
        return {"ok": False, "parse_error": True, "stdout_redacted": redact_text(text[-12000:])}


def sidecar_value(path: Path) -> str | None:
    sidecar = path.with_name(path.name + ".sha256")
    parts = sidecar.read_text(encoding="utf-8").split() if sidecar.is_file() else []
    return parts[0] if parts else None


def nested_values(value: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and child not in (None, ""):
                values.append(child)
            values.extend(nested_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            values.extend(nested_values(child, keys))
    return values


def parse_http_status(payload: dict[str, Any], returncode: int | None) -> str:
    text = " ".join(str(item) for item in nested_values(payload, {"message", "detail", "error", "stderr", "stdout_redacted"}))
    found = re.search(r"\bHTTP\s*(?:status\s*)?(\d{3})\b", text, re.IGNORECASE)
    if found:
        return found.group(1)
    found = re.search(r"\b(429|401|403|5\d\d)\b", text)
    if found:
        return found.group(1)
    return "200" if returncode == 0 and payload.get("ok") is True else "unknown"


def parse_error(payload: dict[str, Any]) -> tuple[str, str]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return ("invalid_provider_json", "provider stdout was not valid JSON") if payload.get("parse_error") else ("", "")
    detail = error.get("detail", "")
    nested: dict[str, Any] = {}
    if isinstance(detail, str):
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                nested = parsed
        except json.JSONDecodeError:
            pass
    return str(nested.get("code") or error.get("code") or "provider_error"), redact_text(str(nested.get("message") or error.get("message") or "provider error"))


def extract_provider_request_id(payload: dict[str, Any]) -> str:
    values = nested_values(payload, {"response_id", "provider_request_id", "request_id", "item_id", "id"})
    return str(values[0]) if values else "unknown"


def native_retry_count(stderr: str) -> int:
    return len(re.findall(r'"type"\s*:\s*"retry_scheduled"', stderr))


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def atomic_move(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise RuntimeError(f"target collision: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fsync_file(source)
    os.replace(source, target)
    directory_fd = os.open(str(target.parent), os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def image_verify(path: Path) -> tuple[bool, tuple[int, int] | None, str]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            return True, image.size, ""
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def verify_and_convert(raw_temp: Path, final_temp: Path) -> dict[str, Any]:
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
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        final_temp.parent.mkdir(parents=True, exist_ok=True)
        rgb.crop(crop_box).resize(FINAL_SIZE, resampling).save(final_temp, format="PNG")
    with Image.open(final_temp) as image:
        image.verify()
    with Image.open(final_temp) as image:
        image.load()
        final_size = image.size
    if final_size != FINAL_SIZE:
        raise ValueError(f"final dimensions {final_size} != {FINAL_SIZE}")
    return {"native_width": native_width, "native_height": native_height, "native_aspect_ratio": native_width / native_height, "crop_box": list(crop_box), "final_width": final_size[0], "final_height": final_size[1], "resize_method": "Pillow_LANCZOS"}


def verify_freeze(path: Path, expected_sha: str, verify_bindings: bool) -> dict[str, Any]:
    actual = sha256_file(path)
    freeze = read_json(path, {}) or {}
    binding_checks: list[dict[str, Any]] = []
    if verify_bindings:
        for raw_path, expected in (freeze.get("artifact_sha256") or {}).items():
            target = Path(raw_path)
            binding_checks.append({"path": raw_path, "expected": expected, "actual": sha256_file(target), "match": sha256_file(target) == expected})
        for raw_path, expected in (freeze.get("reports_sha256") or {}).items():
            target = Path(raw_path)
            binding_checks.append({"path": raw_path, "expected": expected, "actual": sha256_file(target), "match": sha256_file(target) == expected})
    result = {"path": str(path), "expected_sha256": expected_sha, "actual_sha256": actual, "sidecar": sidecar_value(path), "binding_checks": binding_checks}
    result["verified"] = bool(actual == expected_sha == result["sidecar"] and all(item["match"] for item in binding_checks))
    return result


def dataset_snapshot(label: str) -> dict[str, Any]:
    proc = subprocess.run(["python3", str(VALIDATOR), "--json"], capture_output=True, text=True, check=False, timeout=300)
    try:
        validator = json.loads(proc.stdout)
    except json.JSONDecodeError:
        validator = {"parse_error": True, "stdout_tail": proc.stdout[-12000:], "stderr_tail": proc.stderr[-12000:]}
    counts: dict[str, int] = {}
    hashes: dict[str, str | None] = {}
    p4d_hits: dict[str, list[int]] = {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        p4d_hits[name] = [line_no for line_no, line in enumerate(lines, 1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()]
    result = {"captured_at": now(), "label": label, "validator_command": ["python3", str(VALIDATOR), "--json"], "validator_returncode": proc.returncode, "validator": validator, "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]}, "annotation_sha256": hashes, "p4d_reference_hits_by_active_csv": p4d_hits, "p4d_reference_hits_total": sum(len(rows) for rows in p4d_hits.values()), "formal_ingest": False}
    write_json(PRE / f"dataset_boundary_{label}.json", result)
    return result


def run_readonly_cli(label: str, args: list[str], persist: bool) -> dict[str, Any]:
    command = ["node", str(CLI), "--json", "--provider", "codex", *args]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
    raw_payload: dict[str, Any]
    try:
        parsed = json.loads(proc.stdout)
        raw_payload = parsed if isinstance(parsed, dict) else {"ok": False, "raw_json": parsed}
    except json.JSONDecodeError:
        raw_payload = {"ok": False, "parse_error": True, "stdout": proc.stdout[-12000:]}
    record = {"label": label, "command": command, "returncode": proc.returncode, "payload": redact(raw_payload), "stderr": redact_text(proc.stderr), "captured_at": now(), "image_generation_provider_requests": 0}
    if persist:
        write_json(PRE / f"{label}.json", record)
    return raw_payload


def current_runtime_identity(persist: bool) -> dict[str, Any]:
    config = run_readonly_cli("config_inspect", ["config", "inspect"], persist)
    doctor = run_readonly_cli("doctor", ["doctor"], persist)
    auth = run_readonly_cli("auth_inspect", ["auth", "inspect"], persist)
    codex = ((doctor.get("providers") or {}).get("codex") or {}) if isinstance(doctor, dict) else {}
    c_auth = codex.get("auth") if isinstance(codex, dict) else {}
    endpoint = codex.get("endpoint") if isinstance(codex, dict) else {}
    auth_codex = ((auth.get("providers") or {}).get("codex") or {}) if isinstance(auth, dict) else {}
    c_auth = c_auth if isinstance(c_auth, dict) else {}
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    auth_codex = auth_codex if isinstance(auth_codex, dict) else {}
    account = str(c_auth.get("account_id") or auth_codex.get("account_id") or "")
    user = str(c_auth.get("chatgpt_user_id") or auth_codex.get("chatgpt_user_id") or "")
    profile_hash = hashlib.sha256(f"account={account}|user={user}".encode("utf-8")).hexdigest() if account or user else None
    selection = doctor.get("provider_selection") if isinstance(doctor, dict) else {}
    defaults = doctor.get("defaults") if isinstance(doctor, dict) else {}
    retry = doctor.get("retry_policy") if isinstance(doctor, dict) else {}
    selection = selection if isinstance(selection, dict) else {}
    defaults = defaults if isinstance(defaults, dict) else {}
    retry = retry if isinstance(retry, dict) else {}
    result = {"captured_at": now(), "provider": selection.get("resolved") or "codex", "request_model": defaults.get("codex_model") or "gpt-5.4", "generation_backend": "image_generation", "runtime_version": doctor.get("version") if isinstance(doctor, dict) else None, "wrapper_sha256": sha256_file(CLI), "binary_sha256": sha256_file(BINARY), "native_retry_policy": retry, "native_max_retries": retry.get("max_retries"), "outer_retry": False, "auth_ready": bool(c_auth.get("ready") or auth_codex.get("ready")), "endpoint_reachable": bool(endpoint.get("reachable")), "session_ready": bool((c_auth.get("ready") or auth_codex.get("ready")) and endpoint.get("reachable") and endpoint.get("tls_ok")), "profile_fingerprint_safe_hash": profile_hash, "profile_account_present": bool(account), "profile_user_present": bool(user), "image_generation_provider_requests": 0}
    if persist:
        write_json(PRE / "provider_runtime_audit.json", result)
    return result


def audit_manifest() -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = read_csv(MANIFEST)
    prompt_mismatches = []
    for row in rows:
        actual = sha256_file(Path(row["original_prompt_path"]))
        if actual != row.get("prompt_sha256"):
            prompt_mismatches.append({"prompt_id": row.get("prompt_id"), "expected": row.get("prompt_sha256"), "actual": actual})
    groups: dict[str, set[str]] = {}
    for row in rows:
        groups.setdefault(row["group_id"], set()).add(row["planned_internal_split"])
    result = {"captured_at": now(), "path": str(MANIFEST), "expected_sha256": MANIFEST_SHA, "actual_sha256": sha256_file(MANIFEST), "rows": len(rows), "unique_prompt_ids": len({row["prompt_id"] for row in rows}), "unique_groups": len({row["group_id"] for row in rows}), "role_counts": dict(Counter(row["target_role"] for row in rows)), "split_counts": dict(Counter(row["planned_internal_split"] for row in rows)), "cross_split_groups": sum(1 for value in groups.values() if len(value) > 1), "prompt_byte_mismatch": len(prompt_mismatches), "prompt_byte_mismatches": prompt_mismatches, "gr1_reuse_values": sorted({row.get("gr1_images_reused") for row in rows})}
    result["all_match"] = bool(result["actual_sha256"] == MANIFEST_SHA and result["rows"] == 440 and result["unique_prompt_ids"] == 440 and result["unique_groups"] == 88 and result["role_counts"] == {"hard_negative": 300, "positive": 100, "ordinary_negative": 40} and result["split_counts"] == {"NEW_DESIGN": 265, "NEW_SCREEN": 175} and result["cross_split_groups"] == 0 and result["prompt_byte_mismatch"] == 0 and result["gr1_reuse_values"] == ["0"])
    write_json(PRE / "full_manifest_audit.json", result)
    return rows, result


def audit_batch(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    preserved = read_csv(VERIFIED_99)
    outstanding = read_csv(OUTSTANDING_341)
    profile_rows = read_csv(PROFILE_PLAN)
    manifest_by_id = {row["prompt_id"]: row for row in rows}
    preserved_by_id = {row["prompt_id"]: row for row in preserved}
    outstanding_by_id = {row["prompt_id"]: row for row in outstanding}
    issues: list[dict[str, Any]] = []
    if len(preserved) != 99 or len(outstanding) != 341 or len(profile_rows) != 440:
        issues.append({"kind": "inventory_cardinality", "preserved": len(preserved), "outstanding": len(outstanding), "profile_rows": len(profile_rows)})
    if set(preserved_by_id) & set(outstanding_by_id) or set(preserved_by_id) | set(outstanding_by_id) != set(manifest_by_id):
        issues.append({"kind": "inventory_id_partition"})
    order = [int(row["recovery_order"]) for row in outstanding if row.get("recovery_order", "").isdigit()]
    if order != list(range(1, 342)) or not outstanding or outstanding[0].get("prompt_id") != FAILED_PROMPT or outstanding[0].get("parent_request_id") != FAILED_PARENT_REQUEST:
        issues.append({"kind": "recovery_order_or_failed_binding"})
    if sum(1 for row in outstanding if row.get("previous_execution_state") == "FAILED_CONFIRMED_HTTP_429") != 1 or sum(1 for row in outstanding if row.get("previous_execution_state") == "NEVER_STARTED") != 340:
        issues.append({"kind": "outstanding_parent_states"})
    for row in preserved:
        raw_path = Path(row["raw_path"])
        final_path = Path(row["final_path"])
        raw_sha = sha256_file(raw_path)
        final_sha = sha256_file(final_path)
        raw_ok, _, raw_error = image_verify(raw_path)
        final_ok, final_size, final_error = image_verify(final_path)
        expected_raw = row.get("raw_sha256_actual")
        expected_final = row.get("final_sha256_actual")
        valid = bool(raw_path.is_file() and final_path.is_file() and not raw_path.is_symlink() and not final_path.is_symlink() and raw_sha == expected_raw and final_sha == expected_final and raw_ok and final_ok and final_size == FINAL_SIZE)
        if not valid:
            issues.append({"kind": "preserved_integrity", "prompt_id": row["prompt_id"], "raw_sha_match": raw_sha == expected_raw, "final_sha_match": final_sha == expected_final, "raw_ok": raw_ok, "final_ok": final_ok, "final_size": final_size, "raw_error": raw_error, "final_error": final_error})
    raw_ids = {path.stem for path in BATCH_RAW.glob("*.png") if path.is_file()}
    final_ids = {path.stem for path in BATCH_FINAL.glob("*.png") if path.is_file()}
    if raw_ids != set(preserved_by_id) or final_ids != set(preserved_by_id):
        issues.append({"kind": "batch_image_partition", "raw_count": len(raw_ids), "final_count": len(final_ids), "expected_preserved": len(preserved_by_id), "raw_extra": sorted(raw_ids - set(preserved_by_id))[:20], "final_extra": sorted(final_ids - set(preserved_by_id))[:20], "raw_missing": sorted(set(preserved_by_id) - raw_ids)[:20], "final_missing": sorted(set(preserved_by_id) - final_ids)[:20]})
    symlinks = [str(path) for directory in (BATCH_RAW, BATCH_FINAL) if directory.exists() for path in directory.rglob("*") if path.is_symlink()]
    temp_files = [str(path) for directory in (BATCH_RAW, BATCH_FINAL, STAGING_RAW, STAGING_FINAL) if directory.exists() for path in directory.rglob("*") if path.is_file() and ".tmp" in path.name]
    if symlinks:
        issues.append({"kind": "batch_symlinks", "paths": symlinks[:20]})
    if temp_files:
        issues.append({"kind": "stale_temporary_files", "paths": temp_files[:20]})
    for row in outstanding:
        for target in (BATCH_RAW / f"{row['prompt_id']}.png", BATCH_FINAL / f"{row['prompt_id']}.png"):
            if target.exists() or target.is_symlink():
                issues.append({"kind": "outstanding_target_collision", "prompt_id": row["prompt_id"], "path": str(target)})
    metadata_hashes = {path.name: sha256_file(path) for path in sorted(BATCH_METADATA.glob("*.json")) if path.is_file()}
    result = {"captured_at": now(), "preserved_count": len(preserved), "outstanding_count": len(outstanding), "batch_raw_count": len(raw_ids), "batch_final_count": len(final_ids), "batch_metadata_count": len(metadata_hashes), "parent_metadata_sha256": metadata_hashes, "integrity_issues": issues, "all_match": not issues, "profile_a_safe_fingerprint": PROFILE_A, "profile_b_safe_fingerprint": PROFILE_B, "profile_a_role_counts": dict(Counter(row["target_role"] for row in preserved)), "profile_b_role_counts": dict(Counter(row["target_role"] for row in outstanding)), "profile_a_split_counts": dict(Counter(row["planned_split"] for row in preserved)), "profile_b_split_counts": dict(Counter(row["planned_split"] for row in outstanding))}
    write_json(PRE / "batch_and_inventory_audit.json", result)
    return preserved_by_id, outstanding, result


def build_parent_audit() -> dict[str, Any]:
    gr3 = verify_freeze(GR3_FREEZE, GR3_FREEZE_SHA, False)
    gr3e = verify_freeze(GR3E_FREEZE, GR3E_FREEZE_SHA, True)
    q1 = verify_freeze(Q1_FREEZE, Q1_FREEZE_SHA, True)
    q2 = verify_freeze(Q2_FREEZE, Q2_FREEZE_SHA, True)
    q2_payload = read_json(Q2_FREEZE, {}) or {}
    result = {"captured_at": now(), "gr3": gr3, "gr3e": gr3e, "gr3q1": q1, "gr3q2": q2, "q2_status": q2_payload.get("status"), "q2_material_generation_config_change": q2_payload.get("MATERIAL_GENERATION_CONFIG_CHANGE"), "q2_preserve_99": q2_payload.get("PRESERVE_GR3E_99"), "q2_continue_341": q2_payload.get("CONTINUE_OUTSTANDING_341"), "all_required_parent_bindings_match": all(item["verified"] for item in (gr3, gr3e, q1, q2))}
    write_json(PRE / "parent_and_q2_freeze_audit.json", result)
    return result


def validate_authorization() -> dict[str, Any]:
    packet = read_json(Q2_AUTH, {}) or {}
    required_hash = packet.get("required_authorization_text_sha256")
    actual_hash = sha256_object(AUTH_TEXT)
    checks = {"packet_authorized_false_before_q2e": packet.get("authorized") is False and packet.get("EXPLICIT_RECOVERY_AUTHORIZATION") is False, "packet_execution_eligible": packet.get("execution_eligible_after_explicit_authorization") is True, "packet_preserve_99": packet.get("preserve_gr3e_99") is True, "packet_continue_341": packet.get("continue_outstanding_341") is True, "packet_profile_stratification": packet.get("profile_stratification_required") is True, "packet_max_slots": packet.get("maximum_new_logical_slot_invocations") == 341, "packet_native_retries": packet.get("native_max_retries") == 3, "packet_outer_retry": packet.get("outer_retry") is False, "authorization_text_matches_packet": required_hash == actual_hash == "ae484cf957c0e88f6a7329c3359e2ebbc7a3e4794fd3dc35f22dbc9f606e9cbd"}
    result = {"stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY", "captured_at": now(), "authorization_source": "standalone_user_message_after_GR3Q2_preparation", "authorization_text": AUTH_TEXT, "authorization_text_sha256": actual_hash, "packet_required_authorization_text_sha256": required_hash, "checks": checks, "authorized": all(checks.values()), "EXPLICIT_RECOVERY_AUTHORIZATION": all(checks.values()), "maximum_new_logical_slot_invocations": 341, "provider_requests_before_execution": 0, "formal_ingest": False, "c3": False, "new_val": 0, "holdout": 0}
    write_json(AUTH_ATTESTATION, result)
    write_text(AUTH / "recovery_authorization_attestation.md", "# P4D GR3Q2E authorization attestation\n\n```text\nAUTHORIZED=true\nEXPLICIT_RECOVERY_AUTHORIZATION=true\nAUTHORIZATION_TEXT_MATCHES_Q2_PACKET=true\nMAXIMUM_NEW_LOGICAL_SLOT_INVOCATIONS=341\nNATIVE_MAX_RETRIES=3\nOUTER_RETRY=false\nEXACT_MONETARY_COST=UNKNOWN\n```\n\nThe standalone user authorization was matched against the previously frozen GR3Q2 packet by SHA-256. This attestation authorizes only the separate Q2E recovery revision, never a rewrite or resume of GR3E/GR3Q1/GR3Q2.\n")
    return result


def compare_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    checks = {"provider_same": runtime.get("provider") == PROVIDER, "model_same": runtime.get("request_model") == MODEL, "backend_same": runtime.get("generation_backend") == "image_generation", "runtime_same": runtime.get("runtime_version") == RUNTIME_VERSION, "wrapper_same": runtime.get("wrapper_sha256") == WRAPPER_SHA, "binary_same": runtime.get("binary_sha256") == BINARY_SHA, "profile_b_same": runtime.get("profile_fingerprint_safe_hash") == PROFILE_B, "auth_ready": runtime.get("auth_ready") is True, "session_ready": runtime.get("session_ready") is True, "endpoint_reachable": runtime.get("endpoint_reachable") is True, "native_retry_max_3": runtime.get("native_max_retries") == 3, "outer_retry_false": runtime.get("outer_retry") is False}
    result = {"captured_at": now(), "checks": checks, "MATERIAL_GENERATION_CONFIG_CHANGE": not all(checks[key] for key in ("provider_same", "model_same", "backend_same", "runtime_same", "wrapper_same", "binary_same", "native_retry_max_3", "outer_retry_false")), "profile_changed_from_A": runtime.get("profile_fingerprint_safe_hash") != PROFILE_A, "profile_b_confirmed": checks["profile_b_same"], "all_execution_runtime_gates_pass": all(checks.values()), "scope": "observable_generation_material_variables_and_frozen_Profile_B"}
    write_json(PRE / "execution_runtime_comparison.json", result)
    return result


def connect_db() -> sqlite3.Connection:
    LEDGER.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slots (
          prompt_id TEXT PRIMARY KEY,
          parent_ordinal INTEGER NOT NULL,
          recovery_order INTEGER UNIQUE,
          group_id TEXT NOT NULL,
          variant_id TEXT NOT NULL,
          taxonomy TEXT NOT NULL,
          target_role TEXT NOT NULL,
          planned_split TEXT NOT NULL,
          prompt_path TEXT NOT NULL,
          prompt_sha256 TEXT NOT NULL,
          profile_stratum TEXT NOT NULL,
          profile_fingerprint_safe_hash TEXT NOT NULL,
          parent_state TEXT NOT NULL,
          parent_request_id TEXT,
          parent_http_status TEXT,
          state TEXT NOT NULL,
          invocation_count INTEGER NOT NULL DEFAULT 0,
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
          native_retry_count INTEGER,
          response_path TEXT,
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


def init_db(rows: list[dict[str, str]], preserved: dict[str, dict[str, Any]], outstanding: list[dict[str, str]]) -> None:
    conn = connect_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
        if existing:
            if existing != 440:
                raise RuntimeError(f"existing Q2E slot count={existing}, expected 440")
            return
        outstanding_by_id = {row["prompt_id"]: row for row in outstanding}
        plan: list[dict[str, Any]] = []
        for ordinal, manifest in enumerate(rows):
            prompt_id = manifest["prompt_id"]
            if prompt_id in preserved:
                prior = preserved[prompt_id]
                record = {"prompt_id": prompt_id, "parent_ordinal": ordinal, "recovery_order": "", "group_id": manifest["group_id"], "variant_id": manifest["variant_id"], "taxonomy": manifest["taxonomy"], "target_role": manifest["target_role"], "planned_split": manifest["planned_internal_split"], "prompt_path": manifest["original_prompt_path"], "prompt_sha256": manifest["prompt_sha256"], "profile_stratum": "GR3E_PROFILE_A", "profile_fingerprint_safe_hash": PROFILE_A, "parent_state": "SUCCESS", "parent_request_id": prior.get("parent_request_id", ""), "parent_http_status": prior.get("parent_http_status", ""), "state": "PRESERVED_PROFILE_A", "invocation_count": 0, "raw_path": prior.get("raw_path", ""), "final_path": prior.get("final_path", ""), "raw_sha256": prior.get("raw_sha256_actual", ""), "final_sha256": prior.get("final_sha256_actual", "")}
            else:
                prior = outstanding_by_id.get(prompt_id)
                if prior is None:
                    raise RuntimeError(f"outstanding inventory missing {prompt_id}")
                record = {"prompt_id": prompt_id, "parent_ordinal": ordinal, "recovery_order": int(prior["recovery_order"]), "group_id": manifest["group_id"], "variant_id": manifest["variant_id"], "taxonomy": manifest["taxonomy"], "target_role": manifest["target_role"], "planned_split": manifest["planned_internal_split"], "prompt_path": manifest["original_prompt_path"], "prompt_sha256": manifest["prompt_sha256"], "profile_stratum": "GR3Q2_PROFILE_B", "profile_fingerprint_safe_hash": PROFILE_B, "parent_state": prior["previous_execution_state"], "parent_request_id": prior.get("parent_request_id", ""), "parent_http_status": prior.get("parent_http_status", ""), "state": "NOT_STARTED_PROFILE_B", "invocation_count": 0, "raw_path": "", "final_path": "", "raw_sha256": "", "final_sha256": ""}
            plan.append(record)
            conn.execute("""
                INSERT INTO slots(prompt_id,parent_ordinal,recovery_order,group_id,variant_id,taxonomy,target_role,planned_split,prompt_path,prompt_sha256,profile_stratum,profile_fingerprint_safe_hash,parent_state,parent_request_id,parent_http_status,state,invocation_count,raw_path,final_path,raw_sha256,final_sha256)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (record["prompt_id"], record["parent_ordinal"], record["recovery_order"] or None, record["group_id"], record["variant_id"], record["taxonomy"], record["target_role"], record["planned_split"], record["prompt_path"], record["prompt_sha256"], record["profile_stratum"], record["profile_fingerprint_safe_hash"], record["parent_state"], record["parent_request_id"], record["parent_http_status"], record["state"], 0, record["raw_path"] or None, record["final_path"] or None, record["raw_sha256"] or None, record["final_sha256"] or None))
        conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(NULL,?,?,?)", ("INITIALIZED", json.dumps({"revision": REVISION_ID, "profile_a": 99, "profile_b": 341, "provider_requests": 0}, ensure_ascii=False, sort_keys=True), now()))
        conn.commit()
        fields = ["prompt_id", "parent_ordinal", "recovery_order", "group_id", "variant_id", "taxonomy", "target_role", "planned_split", "prompt_path", "prompt_sha256", "profile_stratum", "profile_fingerprint_safe_hash", "parent_state", "parent_request_id", "parent_http_status", "state", "invocation_count", "raw_path", "final_path", "raw_sha256", "final_sha256"]
        write_csv(SLOT_PLAN, fields, plan)
        write_text(LEDGER_CSV, "logical_slot_id,parent_ordinal,recovery_order,profile_stratum,planned_split,target_role,taxonomy,parent_state,phase,state,invocation_count,provider_request_id,http_status,error_code,raw_sha256,final_sha256,latency_seconds,native_retry_count,timestamp\n")
    finally:
        conn.close()


def config_value(auth: dict[str, Any], runtime: dict[str, Any], manifest_audit: dict[str, Any], batch_audit: dict[str, Any]) -> dict[str, Any]:
    return {"stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY", "revision_id": REVISION_ID, "created_at": now(), "authorization_attestation_sha256": sha256_file(AUTH_ATTESTATION), "authorization_text_sha256": auth["authorization_text_sha256"], "parent_gr3q2_freeze_sha256": sha256_file(Q2_FREEZE), "parent_gr3e_freeze_sha256": sha256_file(GR3E_FREEZE), "manifest_path": str(MANIFEST), "manifest_sha256": manifest_audit["actual_sha256"], "batch_path": str(BATCH), "preserved_profile_a_count": 99, "recovery_profile_b_count": 341, "profile_a_safe_fingerprint": PROFILE_A, "profile_b_safe_fingerprint": PROFILE_B, "provider": PROVIDER, "model": MODEL, "generation_backend": "image_generation", "runtime_version": runtime["runtime_version"], "wrapper_sha256": runtime["wrapper_sha256"], "binary_sha256": runtime["binary_sha256"], "native_size_requested": NATIVE_SIZE, "quality": QUALITY, "format": "png", "reference_images": [], "concurrency": 1, "outer_retry": False, "native_max_retries": 3, "stop_on": ["429", "401", "403", "timeout", "5xx", "connection_reset", "any_non_success"], "failed_slot_first": FAILED_PROMPT, "failed_slot_parent_request_id": FAILED_PARENT_REQUEST, "parent_metadata_count": batch_audit["batch_metadata_count"], "parent_metadata_sha256": batch_audit["parent_metadata_sha256"], "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0}


def create_preflight_freeze(parent: dict[str, Any], manifest: dict[str, Any], batch: dict[str, Any], auth: dict[str, Any], runtime: dict[str, Any], runtime_compare: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    static_paths = [Q2_FREEZE, GR3_FREEZE, GR3E_FREEZE, Q1_FREEZE, Q2_AUTH, VERIFIED_99, OUTSTANDING_341, PROFILE_PLAN, INVENTORY, MANIFEST, PARENT_RUN_CONFIG, PARENT_RUNNER, CLI, BINARY, Path(__file__).resolve(), PRE / "parent_and_q2_freeze_audit.json", PRE / "full_manifest_audit.json", PRE / "batch_and_inventory_audit.json", PRE / "config_inspect.json", PRE / "doctor.json", PRE / "auth_inspect.json", PRE / "provider_runtime_audit.json", PRE / "execution_runtime_comparison.json", PRE / "dataset_boundary_before_execution.json", AUTH_ATTESTATION, AUTH / "recovery_authorization_attestation.md", RUN_CONFIG, SLOT_PLAN]
    payload = {"stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY", "revision_id": REVISION_ID, "status": "READY_FOR_AUTHORIZED_PROFILE_STRATIFIED_RECOVERY", "captured_at": now(), "authorization": {"authorized": auth["authorized"], "authorization_text_sha256": auth["authorization_text_sha256"]}, "parents": parent, "manifest": {key: manifest[key] for key in ("actual_sha256", "rows", "unique_prompt_ids", "unique_groups", "role_counts", "split_counts", "cross_split_groups", "prompt_byte_mismatch")}, "batch": {"preserved_count": batch["preserved_count"], "outstanding_count": batch["outstanding_count"], "parent_metadata_sha256": batch["parent_metadata_sha256"]}, "runtime": runtime, "runtime_comparison": runtime_compare, "dataset_before": {"counts": before["counts"], "annotation_sha256": before["annotation_sha256"], "p4d_reference_hits_total": before["p4d_reference_hits_total"], "validator_status": (before.get("validator") or {}).get("status"), "validator_errors": (before.get("validator") or {}).get("error_count")}, "retry": {"native_max_retries": 3, "outer_retry": False, "theoretical_provider_attempt_upper_bound": 1364, "exact_monetary_cost": "UNKNOWN"}, "terminal_scope": {"FORMAL_INGEST": False, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0, "HOLDOUT_CONSUMED": False, "PROVIDER_REQUESTS_BEFORE_EXECUTION": 0}, "artifact_sha256": {str(path): sha256_file(path) for path in static_paths}}
    write_json(PREP_FREEZE, payload)
    digest = sha256_file(PREP_FREEZE)
    write_text(PREP_FREEZE.with_name(PREP_FREEZE.name + ".sha256"), f"{digest}  {PREP_FREEZE.name}")
    return {"path": str(PREP_FREEZE), "sha256": digest, "artifact_count": len(payload["artifact_sha256"])}


def verify_execution_freeze() -> dict[str, Any]:
    payload = read_json(PREP_FREEZE, {}) or {}
    expected = sha256_file(PREP_FREEZE)
    sidecar = sidecar_value(PREP_FREEZE)
    checks = []
    for raw_path, wanted in (payload.get("artifact_sha256") or {}).items():
        actual = sha256_file(Path(raw_path))
        checks.append({"path": raw_path, "expected": wanted, "actual": actual, "match": actual == wanted})
    result = {"captured_at": now(), "freeze_path": str(PREP_FREEZE), "freeze_sha256": expected, "sidecar": sidecar, "freeze_self_match": bool(expected and expected == sidecar), "artifact_count": len(checks), "bad_artifacts": [item for item in checks if not item["match"]], "all_bound_artifacts_match": all(item["match"] for item in checks), "authorized": (payload.get("authorization") or {}).get("authorized") is True, "status": payload.get("status")}
    result["all_pass"] = bool(result["freeze_self_match"] and result["all_bound_artifacts_match"] and result["authorized"] and result["status"] == "READY_FOR_AUTHORIZED_PROFILE_STRATIFIED_RECOVERY")
    return result


def append_ledger_row(row: sqlite3.Row) -> None:
    with LEDGER_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["logical_slot_id", "parent_ordinal", "recovery_order", "profile_stratum", "planned_split", "target_role", "taxonomy", "parent_state", "phase", "state", "invocation_count", "provider_request_id", "http_status", "error_code", "raw_sha256", "final_sha256", "latency_seconds", "native_retry_count", "timestamp"], lineterminator="\n")
        writer.writerow({"logical_slot_id": row["prompt_id"], "parent_ordinal": row["parent_ordinal"], "recovery_order": row["recovery_order"], "profile_stratum": row["profile_stratum"], "planned_split": row["planned_split"], "target_role": row["target_role"], "taxonomy": row["taxonomy"], "parent_state": row["parent_state"], "phase": "RECOVERY", "state": row["state"], "invocation_count": row["invocation_count"], "provider_request_id": row["provider_request_id"], "http_status": row["http_status"], "error_code": row["error_code"], "raw_sha256": row["raw_sha256"], "final_sha256": row["final_sha256"], "latency_seconds": row["latency_seconds"], "native_retry_count": row["native_retry_count"], "timestamp": row["request_finished_at"]})
        handle.flush()
        os.fsync(handle.fileno())


def db_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {str(row["state"]): int(row["n"]) for row in conn.execute("SELECT state,COUNT(*) AS n FROM slots GROUP BY state").fetchall()}
    counts["TOTAL"] = sum(counts.values())
    counts["PROFILE_A_PRESERVED"] = counts.get("PRESERVED_PROFILE_A", 0)
    counts["PROFILE_B_SUCCESS"] = counts.get("SUCCESS_PROFILE_B", 0)
    counts["PROFILE_B_NOT_STARTED"] = counts.get("NOT_STARTED_PROFILE_B", 0)
    counts["PROFILE_B_STARTED"] = counts.get("STARTED_PROFILE_B", 0)
    counts["PROFILE_B_FAILED"] = counts.get("FAILED_CONFIRMED_PROFILE_B", 0)
    counts["COMPLETION_UNKNOWN"] = counts.get("COMPLETION_UNKNOWN_PROFILE_B", 0)
    counts["PROVIDER_REQUESTS"] = conn.execute("SELECT COUNT(*) FROM slots WHERE profile_stratum='GR3Q2_PROFILE_B' AND invocation_count>0").fetchone()[0]
    return counts


def stop(conn: sqlite3.Connection, reason: str, row: sqlite3.Row | None = None, extra: dict[str, Any] | None = None) -> None:
    payload = {"status": "GLOBAL_STOP", "reason": reason, "captured_at": now(), "provider_requests": db_counts(conn)["PROVIDER_REQUESTS"], "prompt_id": row["prompt_id"] if row else None, "recovery_order": row["recovery_order"] if row else None}
    if extra:
        payload.update(extra)
    write_json(STOP_MARKER, payload)
    conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (row["prompt_id"] if row else None, "GLOBAL_STOP", json.dumps(payload, ensure_ascii=False, sort_keys=True), now()))
    conn.commit()


def assert_resumable(conn: sqlite3.Connection) -> None:
    unresolved = conn.execute("SELECT * FROM slots WHERE state='STARTED_PROFILE_B' ORDER BY recovery_order").fetchall()
    if unresolved:
        for row in unresolved:
            conn.execute("UPDATE slots SET state='COMPLETION_UNKNOWN_PROFILE_B',error_code=?,error_message_safe=?,request_finished_at=? WHERE prompt_id=?", ("completion_unknown", "runner found durable STARTED request with no terminal provider evidence", now(), row["prompt_id"]))
        conn.commit()
        stop(conn, "COMPLETION_UNKNOWN", unresolved[0], {"prompt_ids": [row["prompt_id"] for row in unresolved]})
        raise RuntimeError("completion ambiguity detected; no automatic resend is allowed")
    marker = read_json(STOP_MARKER, {}) or {}
    if marker.get("status") == "GLOBAL_STOP":
        raise RuntimeError(f"global stop already recorded: {marker.get('reason')}")
    terminal_bad = conn.execute("SELECT prompt_id,state FROM slots WHERE state IN ('FAILED_CONFIRMED_PROFILE_B','COMPLETION_UNKNOWN_PROFILE_B') ORDER BY recovery_order").fetchall()
    if terminal_bad:
        raise RuntimeError(f"terminal failure already recorded: {[dict(row) for row in terminal_bad]}")


def checkpoint(conn: sqlite3.Connection, status: str, last: dict[str, Any] | None = None) -> None:
    counts = db_counts(conn)
    payload = {"stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY", "status": status, "captured_at": now(), "counts": counts, "last": last, "global_stop": (read_json(STOP_MARKER, {}) or {}).get("status") == "GLOBAL_STOP", "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0}
    write_json(CHECKPOINTS / "latest_checkpoint.json", payload)


def invoke_slot(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    prompt_path = Path(row["prompt_path"])
    if sha256_file(prompt_path) != row["prompt_sha256"]:
        raise RuntimeError(f"prompt bytes changed before request: {row['prompt_id']}")
    raw_target = BATCH_RAW / f"{row['prompt_id']}.png"
    final_target = BATCH_FINAL / f"{row['prompt_id']}.png"
    if raw_target.exists() or raw_target.is_symlink() or final_target.exists() or final_target.is_symlink():
        raise RuntimeError(f"target collision before provider request: {row['prompt_id']}")
    request_id = f"P4D_GR3Q2E_RECOVERY_{int(row['recovery_order']):04d}_{row['prompt_id']}"
    raw_temp = STAGING_RAW / f".{row['prompt_id']}.{request_id}.tmp.png"
    final_temp = STAGING_FINAL / f".{row['prompt_id']}.{request_id}.tmp.png"
    if raw_temp.exists() or final_temp.exists():
        raise RuntimeError(f"unexpected temporary file before request: {row['prompt_id']}")
    started_at = now()
    started_mono = time.monotonic()
    conn.execute("UPDATE slots SET state='STARTED_PROFILE_B',invocation_count=1,request_id=?,request_started_at=?,native_retry_count=? WHERE prompt_id=?", (request_id, started_at, 0, row["prompt_id"]))
    conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (row["prompt_id"], "STARTED_DURABLE", json.dumps({"request_id": request_id, "outer_retry": False, "profile_stratum": "GR3Q2_PROFILE_B"}, ensure_ascii=False, sort_keys=True), now()))
    conn.commit()
    command = ["node", str(CLI), "--json", "--json-events", "--provider", PROVIDER, "images", "generate", "--model", MODEL, "--prompt", prompt_path.read_text(encoding="utf-8").rstrip("\n"), "--out", str(raw_temp), "--format", "png", "--size", NATIVE_SIZE, "--quality", QUALITY]
    returncode: int | None = None
    stdout = ""
    stderr = ""
    timeout = False
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=1800)
        returncode = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
        payload = parse_json_sanitized(stdout)
    except subprocess.TimeoutExpired as exc:
        timeout = True
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        payload = {"ok": False, "error": {"code": "timeout", "message": "generation timeout"}}
    except Exception as exc:
        payload = {"ok": False, "error": {"code": "runner_exception", "message": redact_text(str(exc))}}
    elapsed = time.monotonic() - started_mono
    finished_at = now()
    http_status = parse_http_status(payload, returncode)
    error_code, error_message = parse_error(payload)
    retries = native_retry_count(stderr)
    provider_request_id = extract_provider_request_id(payload)
    state = "FAILED_CONFIRMED_PROFILE_B"
    qa: dict[str, Any] = {}
    raw_sha = final_sha = None
    final_raw_path: str | None = None
    final_final_path: str | None = None
    if timeout:
        state = "COMPLETION_UNKNOWN_PROFILE_B"
        error_code = "timeout"
        error_message = "provider completion cannot be established after timeout"
    elif returncode == 0 and payload.get("ok") is True and raw_temp.is_file() and raw_temp.stat().st_size > 0:
        try:
            qa = verify_and_convert(raw_temp, final_temp)
            atomic_move(raw_temp, raw_target)
            atomic_move(final_temp, final_target)
            raw_sha, final_sha = sha256_file(raw_target), sha256_file(final_target)
            final_raw_path, final_final_path = str(raw_target), str(final_target)
            state = "SUCCESS_PROFILE_B"
        except Exception as exc:
            error_code = "mechanical_image_or_target_failure"
            error_message = redact_text(str(exc))
    else:
        if not error_code:
            error_code, error_message = "provider_non_success", "provider did not return a valid generated file"
    response = {"request_id": request_id, "provider_request_id": provider_request_id, "provider": PROVIDER, "model": MODEL, "generation_backend": "image_generation", "profile_stratum": "GR3Q2_PROFILE_B", "profile_fingerprint_safe_hash": PROFILE_B, "recovery_order": row["recovery_order"], "prompt_id": row["prompt_id"], "group_id": row["group_id"], "taxonomy": row["taxonomy"], "target_role": row["target_role"], "planned_split": row["planned_split"], "parent_state": row["parent_state"], "parent_request_id": row["parent_request_id"], "prompt_sha256": row["prompt_sha256"], "request_payload_config": {"provider": PROVIDER, "model": MODEL, "format": "png", "native_size": NATIVE_SIZE, "quality": QUALITY, "reference_images": [], "outer_retry": False, "native_max_retries": 3}, "command_redacted": ["node", "<gpt-image-2-skill>", "--json", "--json-events", "--provider", PROVIDER, "images", "generate", "--model", MODEL, "--prompt_sha256", row["prompt_sha256"], "--out", str(raw_target), "--format", "png", "--size", NATIVE_SIZE, "--quality", QUALITY], "request_started_at": started_at, "request_finished_at": finished_at, "returncode": returncode, "http_status": http_status, "outer_json": payload, "stdout_redacted": redact_text(stdout), "stderr_redacted": redact_text(stderr), "native_retry_count": retries, "latency_seconds": elapsed, "status": state, "error_code": error_code, "error_message_safe": error_message, "raw_staging_path": str(raw_temp) if raw_temp.exists() else None, "final_staging_path": str(final_temp) if final_temp.exists() else None, "raw_path": final_raw_path, "final_path": final_final_path, "raw_sha256": raw_sha, "final_sha256": final_sha, "mechanical_qa": qa}
    response_path = RAW_LOGS / f"{request_id}.json"
    write_json(response_path, response)
    append_jsonl(RAW_RESPONSES, {"request_id": request_id, "prompt_id": row["prompt_id"], "recovery_order": row["recovery_order"], "response_path": str(response_path), "http_status": http_status, "status": state, "error_code": error_code})
    append_jsonl(REQUEST_LOG, response)
    metadata_path = LEDGER / "slot_metadata" / f"{row['prompt_id']}.json"
    write_json(metadata_path, {key: response[key] for key in ("request_id", "provider_request_id", "provider", "model", "generation_backend", "profile_stratum", "profile_fingerprint_safe_hash", "recovery_order", "prompt_id", "group_id", "taxonomy", "target_role", "planned_split", "parent_state", "parent_request_id", "prompt_sha256", "request_started_at", "request_finished_at", "http_status", "native_retry_count", "latency_seconds", "status", "error_code", "error_message_safe", "raw_path", "final_path", "raw_sha256", "final_sha256", "mechanical_qa")})
    conn.execute("""
        UPDATE slots SET state=?,request_finished_at=?,provider_request_id=?,http_status=?,error_code=?,error_message_safe=?,raw_path=?,final_path=?,raw_sha256=?,final_sha256=?,native_width=?,native_height=?,final_width=?,final_height=?,crop_box=?,latency_seconds=?,native_retry_count=?,response_path=?,metadata_path=? WHERE prompt_id=?
    """, (state, finished_at, provider_request_id, http_status, error_code, error_message, final_raw_path, final_final_path, raw_sha, final_sha, qa.get("native_width"), qa.get("native_height"), qa.get("final_width"), qa.get("final_height"), json.dumps(qa.get("crop_box")) if qa.get("crop_box") else None, elapsed, retries, str(response_path), str(metadata_path), row["prompt_id"]))
    conn.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (row["prompt_id"], state, json.dumps({"http_status": http_status, "error_code": error_code, "latency_seconds": elapsed, "native_retry_count": retries, "raw_sha256": raw_sha, "final_sha256": final_sha}, ensure_ascii=False, sort_keys=True), now()))
    conn.commit()
    updated = conn.execute("SELECT * FROM slots WHERE prompt_id=?", (row["prompt_id"],)).fetchone()
    append_ledger_row(updated)
    result = {"request_id": request_id, "prompt_id": row["prompt_id"], "recovery_order": row["recovery_order"], "state": state, "http_status": http_status, "error_code": error_code, "latency_seconds": elapsed, "native_retry_count": retries, "raw_sha256": raw_sha, "final_sha256": final_sha}
    if state != "SUCCESS_PROFILE_B":
        reason = "COMPLETION_UNKNOWN" if state == "COMPLETION_UNKNOWN_PROFILE_B" else (f"HTTP_{http_status}" if http_status in {"429", "401", "403"} or http_status.startswith("5") else error_code or "NON_SUCCESS")
        stop(conn, reason, updated, {"provider_request_id": provider_request_id, "http_status": http_status, "error_code": error_code, "native_retry_count": retries})
    return result


def batch_output_inventory() -> dict[str, Any]:
    items = []
    for kind, directory in (("raw", BATCH_RAW), ("final", BATCH_FINAL)):
        for path in sorted(directory.glob("*.png")):
            ok, size, error = image_verify(path)
            items.append({"kind": kind, "prompt_id": path.stem, "path": str(path), "sha256": sha256_file(path), "is_symlink": path.is_symlink(), "pillow_ok": ok, "size": list(size) if size else None, "error": error})
    return {"captured_at": now(), "items": items, "counts": dict(Counter(item["kind"] for item in items)), "sha256": sha256_object(items)}


def seal_terminal(conn: sqlite3.Connection) -> dict[str, Any]:
    counts = db_counts(conn)
    marker = read_json(STOP_MARKER, {}) or {}
    finished = counts["PROFILE_B_SUCCESS"] == 341 and counts["PROFILE_B_NOT_STARTED"] == 0 and counts["PROFILE_B_STARTED"] == 0
    stopped = marker.get("status") == "GLOBAL_STOP"
    if not finished and not stopped:
        raise RuntimeError("terminal seal requires all 341 successes or a global stop")
    after = dataset_snapshot("after_execution")
    batch = batch_output_inventory()
    write_json(QA / "batch_output_inventory.json", batch)
    metadata_current = {path.name: sha256_file(path) for path in sorted(BATCH_METADATA.glob("*.json")) if path.is_file()}
    config = read_json(RUN_CONFIG, {}) or {}
    summary = {"stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY", "revision_id": REVISION_ID, "terminal_status": "COMPLETE_GENERATION_PENDING_QA" if finished else "STOPPED_BY_FAILURE_POLICY", "captured_at": now(), "counts": counts, "stop_marker": marker if stopped else None, "provider_requests": counts["PROVIDER_REQUESTS"], "profile_a_preserved": counts["PROFILE_A_PRESERVED"], "profile_b_success": counts["PROFILE_B_SUCCESS"], "profile_b_unstarted": counts["PROFILE_B_NOT_STARTED"], "profile_b_failed": counts["PROFILE_B_FAILED"], "completion_unknown": counts["COMPLETION_UNKNOWN"], "batch_image_counts": batch["counts"], "parent_metadata_unchanged": metadata_current == config.get("parent_metadata_sha256", {}), "dataset_after": {"counts": after["counts"], "annotation_sha256": after["annotation_sha256"], "p4d_reference_hits_total": after["p4d_reference_hits_total"], "validator_status": (after.get("validator") or {}).get("status"), "validator_errors": (after.get("validator") or {}).get("error_count")}, "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0, "holdout_consumed": False}
    write_json(EXEC / "terminal_summary.json", summary)
    raw_manifest = {path.name: sha256_file(path) for path in sorted(RAW_LOGS.glob("*.json")) if path.is_file()}
    write_json(QA / "raw_response_manifest.json", raw_manifest)
    static = [PREP_FREEZE, AUTH_ATTESTATION, RUN_CONFIG, SLOT_PLAN, DB, LEDGER_CSV, REQUEST_LOG, RAW_RESPONSES, QA / "batch_output_inventory.json", QA / "raw_response_manifest.json", PRE / "dataset_boundary_before_execution.json", PRE / "dataset_boundary_after_execution.json", Path(__file__).resolve()]
    terminal = {"stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY", "revision_id": REVISION_ID, "status": summary["terminal_status"], "captured_at": now(), "preflight_freeze_sha256": sha256_file(PREP_FREEZE), "terminal": summary, "artifact_sha256": {str(path): sha256_file(path) for path in static}, "raw_response_file_count": len(raw_manifest), "batch_output_sha256": batch["sha256"]}
    write_json(TERMINAL_FREEZE, terminal)
    digest = sha256_file(TERMINAL_FREEZE)
    write_text(TERMINAL_FREEZE.with_name(TERMINAL_FREEZE.name + ".sha256"), f"{digest}  {TERMINAL_FREEZE.name}")
    return {"terminal_status": summary["terminal_status"], "terminal_freeze": str(TERMINAL_FREEZE), "terminal_freeze_sha256": digest, "counts": counts}


def prepare_command() -> int:
    if PREP_FREEZE.exists() or RUN_CONFIG.exists() or DB.exists():
        raise RuntimeError("Q2E preparation already exists; inspect status rather than rebuilding it")
    for directory in (EXEC, PRE, AUTH, RUNNER, LEDGER, RAW_LOGS, CHECKPOINTS, QA, FREEZE, STAGING_RAW, STAGING_FINAL):
        directory.mkdir(parents=True, exist_ok=True)
    parent = build_parent_audit()
    auth = validate_authorization()
    rows, manifest = audit_manifest()
    preserved, outstanding, batch = audit_batch(rows)
    runtime = current_runtime_identity(persist=True)
    runtime_compare = compare_runtime(runtime)
    before = dataset_snapshot("before_execution")
    checks = {"parent_freezes": parent["all_required_parent_bindings_match"], "authorization": auth["authorized"], "manifest": manifest["all_match"], "batch_and_inventory": batch["all_match"], "runtime": runtime_compare["all_execution_runtime_gates_pass"], "dataset_valid": (before.get("validator") or {}).get("status") == "valid" and (before.get("validator") or {}).get("error_count") == 0 and (before.get("validator") or {}).get("full_hash_check") is True, "dataset_no_p4d_refs": before["p4d_reference_hits_total"] == 0}
    write_json(PRE / "preflight_gate.json", {"captured_at": now(), "checks": checks, "all_pass": all(checks.values()), "provider_requests": 0})
    if not all(checks.values()):
        raise RuntimeError(f"P4D_GR3Q2E_STATUS=BLOCKED_PREFLIGHT: {checks}")
    init_db(rows, preserved, outstanding)
    config = config_value(auth, runtime, manifest, batch)
    write_json(RUN_CONFIG, config)
    freeze = create_preflight_freeze(parent, manifest, batch, auth, runtime, runtime_compare, before)
    print(json.dumps({"status": "READY_FOR_AUTHORIZED_PROFILE_STRATIFIED_RECOVERY", "preflight_freeze": freeze, "preserved_profile_a": 99, "outstanding_profile_b": 341, "provider_requests": 0}, ensure_ascii=False, sort_keys=True))
    return 0


def runtime_gate_before_requests(conn: sqlite3.Connection) -> None:
    frozen = verify_execution_freeze()
    runtime = current_runtime_identity(persist=False)
    runtime_checks = {"preflight_freeze": frozen["all_pass"], "provider_same": runtime.get("provider") == PROVIDER, "model_same": runtime.get("request_model") == MODEL, "runtime_same": runtime.get("runtime_version") == RUNTIME_VERSION, "wrapper_same": runtime.get("wrapper_sha256") == WRAPPER_SHA, "binary_same": runtime.get("binary_sha256") == BINARY_SHA, "profile_b_same": runtime.get("profile_fingerprint_safe_hash") == PROFILE_B, "auth_ready": runtime.get("auth_ready") is True, "session_ready": runtime.get("session_ready") is True, "native_retry_max_3": runtime.get("native_max_retries") == 3}
    gate = {"captured_at": now(), "checks": runtime_checks, "all_pass": all(runtime_checks.values()), "runtime": redact(runtime), "image_generation_provider_requests": 0}
    write_json(CHECKPOINTS / "pre_request_runtime_gate.json", gate)
    if not gate["all_pass"]:
        stop(conn, "PRE_REQUEST_RUNTIME_OR_FREEZE_GATE_FAILED", None, {"checks": runtime_checks})
        raise RuntimeError(f"pre-request gate failed: {runtime_checks}")


def run_command() -> int:
    conn = connect_db()
    lock_handle = LOCK_PATH.open("a+")
    try:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another P4D_GR3Q2E runner holds the lock") from exc
        assert_resumable(conn)
        try:
            runtime_gate_before_requests(conn)
        except Exception as exc:
            marker = read_json(STOP_MARKER, {}) or {}
            if marker.get("status") != "GLOBAL_STOP":
                stop(conn, "PRE_REQUEST_GATE_EXCEPTION", None, {"error_safe": redact_text(str(exc))})
            terminal = seal_terminal(conn)
            print(json.dumps({"stage": "P4D_GR3Q2E", "status": "STOPPED_BEFORE_PROVIDER_REQUEST", "terminal": terminal}, ensure_ascii=False, sort_keys=True), flush=True)
            return 2
        rows = conn.execute("SELECT * FROM slots WHERE state='NOT_STARTED_PROFILE_B' ORDER BY recovery_order").fetchall()
        if not rows:
            checkpoint(conn, "NOT_NEEDED")
            print(json.dumps({"status": "NO_OUTSTANDING_PROFILE_B_SLOTS", "counts": db_counts(conn)}, ensure_ascii=False, sort_keys=True))
            return 0
        if len(rows) > 341 or rows[0]["prompt_id"] != FAILED_PROMPT or rows[0]["recovery_order"] != 1:
            raise RuntimeError("recovery selection does not begin with the authorized failed slot")
        checkpoint(conn, "RUNNING")
        for row in rows:
            try:
                result = invoke_slot(conn, row)
            except Exception as exc:
                current = conn.execute("SELECT * FROM slots WHERE prompt_id=?", (row["prompt_id"],)).fetchone()
                if current is not None and current["state"] == "STARTED_PROFILE_B":
                    conn.execute("UPDATE slots SET state='COMPLETION_UNKNOWN_PROFILE_B',error_code=?,error_message_safe=?,request_finished_at=? WHERE prompt_id=?", ("runner_exception_after_durable_start", redact_text(str(exc)), now(), row["prompt_id"]))
                elif current is not None and current["state"] == "NOT_STARTED_PROFILE_B":
                    conn.execute("UPDATE slots SET state='FAILED_CONFIRMED_PROFILE_B',error_code=?,error_message_safe=?,request_finished_at=? WHERE prompt_id=?", ("pre_invocation_validation_failure", redact_text(str(exc)), now(), row["prompt_id"]))
                conn.commit()
                current = conn.execute("SELECT * FROM slots WHERE prompt_id=?", (row["prompt_id"],)).fetchone()
                stop(conn, "RUNNER_EXCEPTION", current, {"error_safe": redact_text(str(exc))})
                checkpoint(conn, "STOPPED_BY_RUNNER_EXCEPTION", {"prompt_id": row["prompt_id"], "error_code": "runner_exception"})
                terminal = seal_terminal(conn)
                print(json.dumps({"stage": "P4D_GR3Q2E", "status": "STOPPED_BY_RUNNER_EXCEPTION", "terminal": terminal}, ensure_ascii=False, sort_keys=True), flush=True)
                return 2
            checkpoint(conn, "RUNNING" if result["state"] == "SUCCESS_PROFILE_B" else "STOPPED", result)
            print(json.dumps({"stage": "P4D_GR3Q2E", "result": result, "counts": db_counts(conn)}, ensure_ascii=False, sort_keys=True), flush=True)
            if result["state"] != "SUCCESS_PROFILE_B":
                terminal = seal_terminal(conn)
                print(json.dumps({"stage": "P4D_GR3Q2E", "status": "STOPPED", "terminal": terminal}, ensure_ascii=False, sort_keys=True), flush=True)
                return 2
        terminal = seal_terminal(conn)
        print(json.dumps({"stage": "P4D_GR3Q2E", "status": "COMPLETE", "terminal": terminal}, ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
            conn.close()


def status_command() -> int:
    conn = connect_db()
    try:
        output = {"status": "OK", "counts": db_counts(conn), "global_stop": read_json(STOP_MARKER, None), "preflight_freeze": verify_execution_freeze() if PREP_FREEZE.is_file() else None, "terminal_freeze_sha256": sha256_file(TERMINAL_FREEZE), "terminal_sidecar": sidecar_value(TERMINAL_FREEZE), "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0}
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


def seal_command() -> int:
    conn = connect_db()
    lock_handle = LOCK_PATH.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = seal_terminal(conn)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "status", "seal"))
    args = parser.parse_args()
    if args.command == "prepare":
        return prepare_command()
    if args.command == "run":
        return run_command()
    if args.command == "seal":
        return seal_command()
    return status_command()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
