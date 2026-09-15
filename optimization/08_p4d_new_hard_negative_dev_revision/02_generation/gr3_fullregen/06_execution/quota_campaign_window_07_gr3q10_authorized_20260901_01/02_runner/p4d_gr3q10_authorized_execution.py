#!/usr/bin/env python3
"""Independent, fail-closed P4D GR3Q10 execution.

This runner is intentionally self-contained at the revision boundary.  It
does not import or copy the Q9 execution wrapper.  The only provider operation
it can perform is one explicit Codex image-generation request per frozen plan
row, after a complete binding audit has passed.

The generated images are AIGC development evidence only.  This runner never
assigns ground truth, performs human review, performs formal ingest, runs C3,
touches VAL/Holdout, or integrates into production.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
GR3 = ROOT / "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen"
REV_ID = "P4D_GR3Q10_BALANCED_COMPLETE_GROUP_WINDOW_20260901_01"
REV = GR3 / "06_execution/quota_campaign_window_07_gr3q10_authorized_20260901_01"
RUNNER_DIR = REV / "02_runner"
RUNNER = RUNNER_DIR / "p4d_gr3q10_authorized_execution.py"

PRE = REV / "00_preflight"
AUTH_DIR = REV / "01_authorization"
PLAN_DIR = REV / "02_runner"
LEDGER_DIR = REV / "03_ledger"
RAW_RESP_DIR = REV / "04_raw_responses"
CHECK_DIR = REV / "05_checkpoints"
QA_DIR = REV / "06_partial_qa"
RAW_DIR = REV / "07_generated_raw"
FINAL_DIR = REV / "08_final"
STAGING_RAW = REV / "_staging/raw"
STAGING_AMBIGUOUS = REV / "_staging/ambiguous"
FREEZE_DIR = REV / "freeze"
LOCK_PATH = REV / ".p4d_gr3q10_active_runner.lock"

AUTH_PATH = AUTH_DIR / "authorization.json"
PLAN_PATH = PLAN_DIR / "q10_balanced_complete_group_30_plan.csv"
CONFIG_PATH = PLAN_DIR / "run_config.json"
LEDGER_PATH = LEDGER_DIR / "gr3q10_execution.sqlite3"
REQUEST_LOG = REV / "request_log.jsonl"
RAW_LOG = REV / "raw_responses.jsonl"
PREFLIGHT_AUDIT = PRE / "preflight_binding_audit.json"
READY_PATH = CHECK_DIR / "ready.json"
GLOBAL_STOP = CHECK_DIR / "global_stop.json"
TERMINAL_SUMMARY = CHECK_DIR / "terminal_summary.json"
FREEZE_PATH = FREEZE_DIR / "p4d_gr3q10_execution_terminal_freeze.json"
FREEZE_SIDECAR = FREEZE_DIR / "p4d_gr3q10_execution_terminal_freeze.json.sha256"
FREEZE_VERIFY = CHECK_DIR / "terminal_freeze_verification.json"

DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
VALIDATOR = DATASET / "tools/validate_dataset.py"
FULL_MANIFEST = GR3 / "03_fullregen_plan/full_regen_prompt_manifest.csv"
ADAPTER_MANIFEST = (
    GR3
    / "06_execution/quota_campaign_window_02_policy_adapter_20260830_01"
    / "01_adapter/render_prompt_manifest_v1.csv"
)
Q9_ROOT = GR3 / "06_execution/quota_campaign_window_06_gr3q9_authorized_20260831_02"
Q9_PLAN = Q9_ROOT / "02_plan/q9_hard_negative_balanced_30_plan.csv"
Q9_AUTH = Q9_ROOT / "01_authorization/authorization.json"
Q9_CONFIG = Q9_ROOT / "02_plan/run_config.json"
Q9_AUDIT = Q9_ROOT / "05_checkpoints/postrun_integrity_audit.json"
Q9_FREEZE = Q9_ROOT / "freeze/p4d_gr3q9_execution_terminal_freeze.json"
Q9_FREEZE_SIDECAR = Q9_ROOT / "freeze/p4d_gr3q9_execution_terminal_freeze.json.sha256"
Q9_VERIFIED = Q9_ROOT / "06_partial_qa/verified_success.csv"
Q9_UNKNOWN = Q9_ROOT / "06_partial_qa/completion_unknown_quarantine.csv"
Q9_SAFE = Q9_ROOT / "06_partial_qa/safe_executable_outstanding.csv"

Q8_ROOT = GR3 / "06_execution/quota_campaign_window_05_gr3q8_authorized_20260831_01"
Q8_FREEZE = Q8_ROOT / "freeze/p4d_gr3q8_execution_terminal_freeze.json"
Q8_FREEZE_SIDECAR = Q8_ROOT / "freeze/p4d_gr3q8_execution_terminal_freeze.json.sha256"
Q8_VERIFY = Q8_ROOT / "05_checkpoints/terminal_freeze_verification.json"

PARSER_SOURCE = Q9_ROOT / "02_plan/retry_event_parser_v2.py"
CLASSIFIER_SOURCE = Q9_ROOT / "02_plan/provider_failure_classifier_v2.py"
PARSER_COPY = RUNNER_DIR / "retry_event_parser_v2.py"
CLASSIFIER_COPY = RUNNER_DIR / "provider_failure_classifier_v2.py"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
# Resolve the actual workspace runtime instead of assuming a distro path.
NODE = Path(shutil.which("node") or "/home/yanbo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")

ADAPTER_VERSION = "CODEX_SAFE_STAGED_CV_V1"
PROVIDER = "codex"
MODEL = "gpt-5.4"
RUNTIME_EXPECTED = "0.7.3"
NATIVE_SIZE = "1536x1024"
FINAL_SIZE = (1920, 1080)
QUALITY = "medium"
IMAGE_FORMAT = "png"
GENERATION_BACKEND = "image_generation"
MAX_LOGICAL = 30
MAX_PHYSICAL_LOWER_BOUND = 36
MAX_NATIVE_RETRY_EVENTS = 4
MAX_POLICY_REFUSALS = 3
NATIVE_MAX_RETRIES = 3
CONCURRENCY = 1
OUTER_RETRY = False
TIMEOUT_SECONDS = 1800

SELECTED_GROUPS = [
    "PF_P4D_HN_MAINT_G002",
    "PF_P4D_HN_PLANK_G002",
    "PF_P4D_HN_CRAWL_G002",
    "PF_P4D_HN_SQUAT_G005",
    "PF_P4D_POS_INTENTIONAL_G002",
    "PF_P4D_NEG_STAND_G001",
]
SELECTION_REASON = (
    "deterministic_complete_group_balance_v1; "
    "four hard-negative taxonomy groups plus one positive and one ordinary "
    "negative group; target HN20/POS5/ORD5 and NEW_DESIGN20/NEW_SCREEN10"
)
REPORT_DIR = ROOT / "reports"
REPORT_PREFLIGHT = REPORT_DIR / "120_p4d_gr3q10_preflight.md"
REPORT_PLAN = REPORT_DIR / "121_p4d_gr3q10_plan.md"
REPORT_EXECUTION = REPORT_DIR / "122_p4d_gr3q10_execution.md"
REPORT_QA = REPORT_DIR / "123_p4d_gr3q10_partial_qa.md"
REPORT_FINAL = REPORT_DIR / "124_p4d_gr3q10_final.md"


class GateBlocked(RuntimeError):
    """A fail-closed gate prevented provider execution or formal continuation."""


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_bytes(json_bytes(obj))
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GateBlocked(f"missing JSON artifact: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GateBlocked(f"JSON artifact is not an object: {path}")
    return value


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise GateBlocked(f"missing CSV artifact: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise GateBlocked(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def preflight_artifact_path(name: str) -> Path:
    """Return a non-overwriting path for a repeated preflight attempt."""
    path = PRE / name
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    retry = PRE / f"{stem}_attempt_002{suffix}"
    require(not retry.exists(), f"refusing to overwrite prior preflight retry artifact: {retry}")
    return retry


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def scrub_text(text: str) -> str:
    patterns = [
        (r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]"),
        (r"(?i)(sk-[A-Za-z0-9_-]{10,})", "[REDACTED_API_KEY]"),
        (r"(?i)(access_token|refresh_token|id_token)([\"'=: ]+)[^,\n} ]+", r"\1\2[REDACTED]"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]"),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "account_id",
    "chatgpt_user_id",
    "email",
    "api_key",
    "authorization",
    "safety_identifier",
    "safety_id",
}


def redact_json(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_json(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_json(v, key) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def parse_last_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped:
        try:
            value = json.loads(stripped)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateBlocked(message)


def sidecar_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    require(bool(text), f"empty freeze sidecar: {path}")
    candidate = text.split()[0]
    require(bool(re.fullmatch(r"[0-9a-f]{64}", candidate)), f"invalid sidecar: {path}")
    return candidate


def run_codex_doctor() -> tuple[dict[str, Any], dict[str, Any]]:
    require(NODE.is_file(), f"missing node runtime: {NODE}")
    require(CLI.is_file(), f"missing GPT Image 2 wrapper: {CLI}")
    cmd = [str(NODE), str(CLI), "--json", "--provider", PROVIDER, "doctor"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(CLI.parent.parent),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError as exc:
        raise GateBlocked(f"provider doctor could not start: {exc}") from exc
    payload = parse_last_json(proc.stdout)
    require(proc.returncode == 0 and payload.get("ok") is True, "PREFLIGHT_BLOCKED: Codex doctor failed")
    selection = payload.get("provider_selection") or {}
    codex = (payload.get("providers") or {}).get("codex") or {}
    auth = codex.get("auth") or {}
    endpoint = codex.get("endpoint") or {}
    require(selection.get("requested") == PROVIDER, "PREFLIGHT_BLOCKED: doctor provider request mismatch")
    require(selection.get("resolved") == PROVIDER and selection.get("kind") == PROVIDER,
            "PREFLIGHT_BLOCKED: doctor did not resolve explicit Codex provider")
    require(auth.get("ready") is True and auth.get("expired") is False,
            "PREFLIGHT_BLOCKED: Codex auth is not ready/current")
    require(endpoint.get("reachable") is True and endpoint.get("tls_ok") is True,
            "PREFLIGHT_BLOCKED: Codex endpoint is not reachable/TLS-ready")
    defaults = payload.get("defaults") or {}
    require(defaults.get("codex_model") == MODEL,
            f"PREFLIGHT_BLOCKED: Codex model changed: {defaults.get('codex_model')!r}")
    version = str(payload.get("version") or "")
    require(version == RUNTIME_EXPECTED,
            f"PREFLIGHT_BLOCKED: unexpected image CLI runtime {version!r}")
    safe = redact_json(payload)
    safe["command"] = "gpt_image_2_skill --json --provider codex doctor"
    safe["captured_at"] = utc()
    return payload, safe


def run_dataset_validator(name: str) -> dict[str, Any]:
    require(VALIDATOR.is_file(), f"missing dataset validator: {VALIDATOR}")
    proc = subprocess.run(
        ["python3", "-B", str(VALIDATOR), "--json"],
        cwd=str(DATASET),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    payload = parse_last_json(proc.stdout)
    validator = payload.get("validator") if isinstance(payload.get("validator"), dict) else payload
    require(
        proc.returncode == 0
        and validator.get("status") == "valid"
        and validator.get("error_count") == 0
        and validator.get("full_hash_check") is True,
        f"PREFLIGHT_BLOCKED: dataset validator failed for {name}: "
        f"returncode={proc.returncode}, status={validator.get('status')}, "
        f"errors={validator.get('error_count')}",
    )
    result = {
        "captured_at": utc(),
        "name": name,
        "dataset_root": str(DATASET),
        "validator_command": ["python3", "-B", str(VALIDATOR), "--json"],
        "returncode": proc.returncode,
        "validator": validator,
    }
    write_json(preflight_artifact_path(f"dataset_{name}.json"), result)
    return result


def rows_by_id(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    fields, rows = read_csv(path)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        pid = row.get("prompt_id", "")
        require(bool(pid), f"blank prompt_id in {path}")
        require(pid not in result, f"duplicate prompt_id {pid} in {path}")
        result[pid] = row
    return fields, result


def load_parent_evidence() -> dict[str, Any]:
    for path in [
        Q8_FREEZE,
        Q8_FREEZE_SIDECAR,
        Q8_VERIFY,
        Q9_FREEZE,
        Q9_FREEZE_SIDECAR,
        Q9_AUDIT,
        Q9_AUTH,
        Q9_CONFIG,
        Q9_PLAN,
    ]:
        require(path.is_file(), f"missing parent evidence: {path}")
    q8_sha = sha256_path(Q8_FREEZE)
    q9_sha = sha256_path(Q9_FREEZE)
    require(q8_sha == "2235fff83e62b2daf05f736446ccc5819e599fd2c7112fdb788871ecc20d8477",
            "PREFLIGHT_BLOCKED: Q8 terminal freeze hash changed")
    require(q9_sha == "f62af81a6ebbdecd807e3db6ab14ed1abc1ac4ceef73d4ffea64cc081e8a3bf6",
            "PREFLIGHT_BLOCKED: Q9 terminal freeze hash changed")
    require(sidecar_hash(Q8_FREEZE_SIDECAR) == q8_sha, "PREFLIGHT_BLOCKED: Q8 sidecar mismatch")
    require(sidecar_hash(Q9_FREEZE_SIDECAR) == q9_sha, "PREFLIGHT_BLOCKED: Q9 sidecar mismatch")
    q8_verify = read_json(Q8_VERIFY)
    require(q8_verify.get("all_bound_artifacts_match") is True and q8_verify.get("sidecar_match") is True,
            "PREFLIGHT_BLOCKED: Q8 terminal freeze verification failed")
    q9_audit = read_json(Q9_AUDIT)
    require(q9_audit.get("status") == "POSTRUN_CONFIG_BINDING_MISMATCH",
            "PREFLIGHT_BLOCKED: Q9 is not the expected binding-blocked history")
    require(q9_audit.get("provider_requests_sent") == 30,
            "PREFLIGHT_BLOCKED: Q9 request count changed")
    require(
        q9_audit.get("frozen_authorization_artifact", {}).get("max_logical_invocations") == 25
        and q9_audit.get("frozen_authorization_artifact", {}).get("max_physical_attempt_lower_bound") == 30
        and q9_audit.get("actual_runner_enforced", {}).get("max_logical_invocations") == 30
        and q9_audit.get("actual_runner_enforced", {}).get("max_physical_attempt_lower_bound") == 36,
        "PREFLIGHT_BLOCKED: Q9 mismatch evidence changed",
    )
    q9_auth = read_json(Q9_AUTH)
    q9_config = read_json(Q9_CONFIG)
    require(
        q9_auth.get("max_logical_invocations") == 25
        and q9_auth.get("max_physical_attempt_lower_bound") == 30
        and q9_config.get("provider") == PROVIDER
        and q9_config.get("request_model") == MODEL,
        "PREFLIGHT_BLOCKED: Q9 parent auth/config evidence is inconsistent",
    )
    return {
        "q8_clean_formal_parent": {
            "freeze_path": str(Q8_FREEZE),
            "freeze_sha256": q8_sha,
            "sidecar_sha256": sha256_path(Q8_FREEZE_SIDECAR),
            "verification_path": str(Q8_VERIFY),
        },
        "q9_latest_execution_evidence": {
            "freeze_path": str(Q9_FREEZE),
            "freeze_sha256": q9_sha,
            "sidecar_sha256": sha256_path(Q9_FREEZE_SIDECAR),
            "audit_path": str(Q9_AUDIT),
            "audit_sha256": sha256_path(Q9_AUDIT),
            "status": q9_audit["status"],
            "formal_acceptance": q9_audit.get("formal_acceptance"),
            "binding_status": "BOUND_BUT_NOT_FORMALLY_ACCEPTED",
        },
    }


def load_accounting() -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    _full_fields, full = rows_by_id(FULL_MANIFEST)
    require(len(full) == 440, f"PREFLIGHT_BLOCKED: frozen-440 manifest row count is {len(full)}")
    require(Counter(r.get("target_role") for r in full.values()) == Counter({
        "hard_negative": 300,
        "ordinary_negative": 40,
        "positive": 100,
    }), "PREFLIGHT_BLOCKED: frozen-440 role counts changed")
    require(Counter(r.get("planned_internal_split") for r in full.values()) == Counter({
        "NEW_DESIGN": 265,
        "NEW_SCREEN": 175,
    }), "PREFLIGHT_BLOCKED: frozen-440 split counts changed")

    _adapter_fields, adapter = rows_by_id(ADAPTER_MANIFEST)
    # The frozen adapter is an older 308-row ready subset, not a 440-row
    # replacement for the full manifest.  Full-coverage is required only for
    # the selected rows; foreign adapter IDs remain forbidden.
    require(len(adapter) == 308 and set(adapter) <= set(full),
            "PREFLIGHT_BLOCKED: adapter is not the expected 308-row subset of frozen-440")
    adapter_bad: list[str] = []
    for pid, row in adapter.items():
        if row.get("adapter_version") != ADAPTER_VERSION:
            adapter_bad.append(f"{pid}:adapter_version")
        if row.get("status") != "READY":
            adapter_bad.append(f"{pid}:status")
        if row.get("render_prompt_sha256") != sha256_bytes(row.get("render_prompt", "").encode("utf-8")):
            adapter_bad.append(f"{pid}:render_prompt_sha256")
        if row.get("role") != full[pid].get("target_role"):
            adapter_bad.append(f"{pid}:role")
        if row.get("planned_split") != full[pid].get("planned_internal_split"):
            adapter_bad.append(f"{pid}:split")
    require(not adapter_bad, "PREFLIGHT_BLOCKED: adapter integrity mismatch: " + ", ".join(adapter_bad[:8]))

    _q9_fields, q9_plan = rows_by_id(Q9_PLAN)
    require(len(q9_plan) == 30, f"PREFLIGHT_BLOCKED: Q9 plan row count is {len(q9_plan)}")
    q9_plan_sha = sha256_path(Q9_PLAN)
    require(q9_plan_sha == "0344c97847ea7447fee7246a7dc9b173429efd058aa0f4153eb9d2f6d5bb950c",
            "PREFLIGHT_BLOCKED: Q9 plan hash changed")
    _verified_fields, verified = rows_by_id(Q9_VERIFIED)
    _unknown_fields, unknown = rows_by_id(Q9_UNKNOWN)
    _safe_fields, safe = rows_by_id(Q9_SAFE)
    full_ids = set(full)
    verified_ids, unknown_ids, safe_ids = set(verified), set(unknown), set(safe)
    require(len(verified) == 226 and len(unknown) == 1 and len(safe) == 213,
            "PREFLIGHT_BLOCKED: Q9 partition counts changed")
    require(
        verified_ids.isdisjoint(unknown_ids)
        and verified_ids.isdisjoint(safe_ids)
        and unknown_ids.isdisjoint(safe_ids)
        and verified_ids | unknown_ids | safe_ids == full_ids,
        "PREFLIGHT_BLOCKED: Q9 partition is not an exact frozen-440 partition",
    )
    q9_ids = set(q9_plan)
    require(
        q9_ids <= full_ids
        and len(q9_ids & verified_ids) == 30
        and not q9_ids & unknown_ids
        and not q9_ids & safe_ids,
        "PREFLIGHT_BLOCKED: Q9 plan/partition relationship changed",
    )
    clean_ids = verified_ids - q9_ids
    binding_ids = verified_ids & q9_ids
    accounting = {
        "target_total": 440,
        "clean_success": len(clean_ids),
        "binding_blocked_success": len(binding_ids),
        "completion_unknown": len(unknown_ids),
        "safe_executable_outstanding": len(safe_ids),
        "sum": len(clean_ids) + len(binding_ids) + len(unknown_ids) + len(safe_ids),
        "q9_plan_sha256": q9_plan_sha,
        "verified_sha256": sha256_path(Q9_VERIFIED),
        "unknown_sha256": sha256_path(Q9_UNKNOWN),
        "safe_sha256": sha256_path(Q9_SAFE),
        "full_manifest_sha256": sha256_path(FULL_MANIFEST),
        "adapter_manifest_sha256": sha256_path(ADAPTER_MANIFEST),
        "role_counts_safe": dict(Counter(safe[pid].get("role") for pid in safe)),
        "split_counts_safe": dict(Counter(safe[pid].get("planned_split") for pid in safe)),
        "unknown_ids": sorted(unknown_ids),
    }
    require(accounting["sum"] == 440, "PREFLIGHT_BLOCKED: accounting does not sum to 440")
    write_json(preflight_artifact_path("partition_rebuild.json"), {
        "captured_at": utc(),
        "full_manifest_rows": len(full),
        "verified_rows": len(verified),
        "unknown_rows": len(unknown),
        "safe_rows": len(safe),
        "q9_plan_rows": len(q9_plan),
        "accounting": accounting,
        "q9_plan_ids": sorted(q9_ids),
    })
    write_json(preflight_artifact_path("full_manifest_audit.json"), {
        "captured_at": utc(),
        "path": str(FULL_MANIFEST),
        "sha256": sha256_path(FULL_MANIFEST),
        "row_count": len(full),
        "unique_prompt_ids": len(full),
        "role_counts": dict(Counter(r.get("target_role") for r in full.values())),
        "split_counts": dict(Counter(r.get("planned_internal_split") for r in full.values())),
        "adapter_path": str(ADAPTER_MANIFEST),
        "adapter_sha256": sha256_path(ADAPTER_MANIFEST),
        "adapter_row_count": len(adapter),
    })
    return accounting, full, adapter


def build_plan(full: dict[str, dict[str, str]], adapter: dict[str, dict[str, str]],
               safe_ids: set[str], unknown_ids: set[str], q9_ids: set[str]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for group_id in SELECTED_GROUPS:
        group_rows = [row for row in full.values() if row.get("group_id") == group_id]
        require(len(group_rows) == 5, f"PREFLIGHT_BLOCKED: selected group is not complete: {group_id}")
        roles = {r.get("target_role") for r in group_rows}
        splits = {r.get("planned_internal_split") for r in group_rows}
        require(len(roles) == 1 and len(splits) == 1, f"PREFLIGHT_BLOCKED: mixed selected group: {group_id}")
        for row in sorted(group_rows, key=lambda r: r.get("variant_id", "")):
            pid = row["prompt_id"]
            require(pid in safe_ids and pid not in unknown_ids and pid not in q9_ids,
                    f"PREFLIGHT_BLOCKED: selected ID is not safe/outstanding-only: {pid}")
            a = adapter[pid]
            selected.append({
                "q10_order": str(len(selected) + 1),
                "prompt_id": pid,
                "group_id": row["group_id"],
                "variant_id": row["variant_id"],
                "role": row["target_role"],
                "taxonomy": row["taxonomy"],
                "planned_split": row["planned_internal_split"],
                "parent_state": "SAFE_EXECUTABLE_OUTSTANDING",
                "adapter_version": a["adapter_version"],
                "render_prompt_sha256": a["render_prompt_sha256"],
                "taxonomy_target": row["target_event_label"],
                "selection_reason": SELECTION_REASON,
                "render_prompt": a["render_prompt"],
            })
    require(len(selected) == 30 and len({r["prompt_id"] for r in selected}) == 30,
            "PREFLIGHT_BLOCKED: selected plan is not exactly 30 unique rows")
    require(Counter(r["role"] for r in selected) == Counter({
        "hard_negative": 20,
        "positive": 5,
        "ordinary_negative": 5,
    }), "PREFLIGHT_BLOCKED: selected role balance changed")
    require(Counter(r["planned_split"] for r in selected) == Counter({
        "NEW_DESIGN": 20,
        "NEW_SCREEN": 10,
    }), "PREFLIGHT_BLOCKED: selected split balance changed")
    write_csv(PLAN_PATH, list(selected[0]), selected)
    write_json(PRE / "selection_freeze.json", {
        "captured_at": utc(),
        "revision_id": REV_ID,
        "selected_groups": SELECTED_GROUPS,
        "selected_prompt_ids": [r["prompt_id"] for r in selected],
        "row_count": len(selected),
        "role_counts": dict(Counter(r["role"] for r in selected)),
        "split_counts": dict(Counter(r["planned_split"] for r in selected)),
        "selection_reason": SELECTION_REASON,
        "plan_path": str(PLAN_PATH),
        "plan_sha256": sha256_path(PLAN_PATH),
        "excluded_ids": {
            "q9": sorted(q9_ids),
            "completion_unknown": sorted(unknown_ids),
        },
    })
    return selected


def create_ledger(rows: list[dict[str, str]], auth_sha: str, plan_sha: str,
                  config_sha: str, runner_sha: str) -> None:
    require(not LEDGER_PATH.exists(), f"refusing to overwrite ledger: {LEDGER_PATH}")
    conn = sqlite3.connect(LEDGER_PATH)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE slots (
                prompt_id TEXT PRIMARY KEY,
                ordinal INTEGER NOT NULL UNIQUE,
                group_id TEXT NOT NULL,
                variant_id TEXT NOT NULL,
                role TEXT NOT NULL,
                taxonomy TEXT NOT NULL,
                planned_split TEXT NOT NULL,
                adapter_version TEXT NOT NULL,
                render_prompt_sha256 TEXT NOT NULL,
                state TEXT NOT NULL,
                started_at TEXT,
                terminal_at TEXT,
                returncode INTEGER,
                http_status INTEGER,
                classification_state TEXT,
                failure_reason TEXT,
                unique_native_retry_events INTEGER NOT NULL DEFAULT 0,
                request_started_events INTEGER NOT NULL DEFAULT 0,
                physical_attempt_lower_bound INTEGER NOT NULL DEFAULT 0,
                raw_sha256 TEXT,
                final_sha256 TEXT,
                response_json_sha256 TEXT
            );
            CREATE TABLE events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id TEXT,
                event_type TEXT NOT NULL,
                at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        metadata = {
            "revision_id": REV_ID,
            "stage": "P4D_GR3Q10_BALANCED_COMPLETE_GROUP_WINDOW",
            "authorization_sha256": auth_sha,
            "plan_sha256": plan_sha,
            "run_config_sha256": config_sha,
            "runner_sha256": runner_sha,
            "provider": PROVIDER,
            "model": MODEL,
            "runtime_expected": RUNTIME_EXPECTED,
            "adapter_version": ADAPTER_VERSION,
            "max_logical_invocations": str(MAX_LOGICAL),
            "max_physical_attempt_lower_bound": str(MAX_PHYSICAL_LOWER_BOUND),
            "native_max_retries": str(NATIVE_MAX_RETRIES),
            "max_unique_native_retry_events": str(MAX_NATIVE_RETRY_EVENTS),
            "max_confirmed_policy_refusals": str(MAX_POLICY_REFUSALS),
            "concurrency": str(CONCURRENCY),
            "outer_retry": str(OUTER_RETRY).lower(),
            "formal_ingest": "false",
            "c3": "false",
            "val": "false",
            "holdout_requests": "0",
        }
        conn.executemany("INSERT INTO metadata(key,value) VALUES(?,?)", metadata.items())
        for row in rows:
            conn.execute(
                """
                INSERT INTO slots(
                    prompt_id, ordinal, group_id, variant_id, role, taxonomy,
                    planned_split, adapter_version, render_prompt_sha256, state
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["prompt_id"],
                    int(row["q10_order"]),
                    row["group_id"],
                    row["variant_id"],
                    row["role"],
                    row["taxonomy"],
                    row["planned_split"],
                    row["adapter_version"],
                    row["render_prompt_sha256"],
                    "NOT_STARTED",
                ),
            )
            conn.execute(
                "INSERT INTO events(prompt_id,event_type,at,payload_json) VALUES(?,?,?,?)",
                (row["prompt_id"], "INITIALIZED_NOT_STARTED", utc(), json.dumps({
                    "revision_id": REV_ID,
                    "provider_request_allowed": True,
                }, sort_keys=True)),
            )
        conn.commit()
    finally:
        conn.close()
    write_json(PRE / "ledger_initialization.json", {
        "captured_at": utc(),
        "path": str(LEDGER_PATH),
        "sha256_at_initialization": sha256_path(LEDGER_PATH),
        "row_count": len(rows),
        "all_initial_state": "NOT_STARTED",
        "provider_requests_sent": 0,
    })


def ledger_metadata(conn: sqlite3.Connection) -> dict[str, str]:
    return {k: v for k, v in conn.execute("SELECT key,value FROM metadata")}


def plan_rows() -> list[dict[str, str]]:
    _, rows = read_csv(PLAN_PATH)
    require(len(rows) == 30, "plan row count is not 30")
    return rows


def make_binding_audit() -> dict[str, Any]:
    auth = read_json(AUTH_PATH)
    config = read_json(CONFIG_PATH)
    rows = plan_rows()
    require(LEDGER_PATH.is_file(), "ledger missing during binding audit")
    conn = sqlite3.connect(LEDGER_PATH)
    try:
        meta = ledger_metadata(conn)
        columns = ["prompt_id", "ordinal", "state", "adapter_version", "render_prompt_sha256"]
        db_rows = [
            dict(zip(columns, r))
            for r in conn.execute(
                "SELECT prompt_id,ordinal,state,adapter_version,render_prompt_sha256 FROM slots ORDER BY ordinal"
            )
        ]
    finally:
        conn.close()
    plan_ids = [r["prompt_id"] for r in rows]
    db_ids = [r["prompt_id"] for r in db_rows]
    config_limits = {
        "max_logical_invocations": config.get("max_logical_invocations"),
        "max_physical_attempt_lower_bound": config.get("max_physical_attempt_lower_bound"),
        "native_max_retries": config.get("native_max_retries"),
        "max_unique_native_retry_events": config.get("max_unique_native_retry_events"),
        "max_confirmed_policy_refusals": config.get("max_confirmed_policy_refusals"),
        "concurrency": config.get("concurrency"),
        "outer_retry": config.get("outer_retry"),
    }
    auth_limits = {
        k: auth.get(k)
        for k in [
            "max_logical_invocations",
            "max_physical_attempt_lower_bound",
            "native_max_retries",
            "max_unique_native_retry_events",
            "max_confirmed_policy_refusals",
            "concurrency",
            "outer_retry",
        ]
    }
    flags = {
        "AUTHORIZATION_MATCH": (
            auth.get("authorized") is True
            and auth.get("revision_id") == REV_ID
            and auth.get("selected_prompt_ids") == plan_ids
            and auth_limits == config_limits
        ),
        "PLAN_MATCH": (
            sha256_path(PLAN_PATH) == config.get("plan_sha256")
            and len(plan_ids) == 30
            and len(set(plan_ids)) == 30
            and all(
                r.get("adapter_version") == ADAPTER_VERSION
                and r.get("parent_state") == "SAFE_EXECUTABLE_OUTSTANDING"
                for r in rows
            )
        ),
        "RUN_CONFIG_MATCH": (
            config.get("revision_id") == REV_ID
            and config.get("provider") == PROVIDER
            and config.get("request_model") == MODEL
            and config.get("runtime_expected") == RUNTIME_EXPECTED
            and config.get("generation_backend") == GENERATION_BACKEND
            and config.get("adapter_version") == ADAPTER_VERSION
            and config.get("requested_native_size") == NATIVE_SIZE
            and config.get("final_output_dimension_contract") == "1920x1080"
            and config.get("format") == IMAGE_FORMAT
            and config.get("quality") == QUALITY
            and config.get("native_size_contract_enforced") is False
        ),
        "RUNNER_IDENTITY_MATCH": (
            config.get("runner_sha256") == sha256_path(RUNNER)
            and config.get("runner_path") == str(RUNNER)
        ),
        "LIMITS_MATCH": (
            config_limits == {
                "max_logical_invocations": MAX_LOGICAL,
                "max_physical_attempt_lower_bound": MAX_PHYSICAL_LOWER_BOUND,
                "native_max_retries": NATIVE_MAX_RETRIES,
                "max_unique_native_retry_events": MAX_NATIVE_RETRY_EVENTS,
                "max_confirmed_policy_refusals": MAX_POLICY_REFUSALS,
                "concurrency": CONCURRENCY,
                "outer_retry": OUTER_RETRY,
            }
            and meta.get("max_logical_invocations") == str(MAX_LOGICAL)
            and meta.get("max_physical_attempt_lower_bound") == str(MAX_PHYSICAL_LOWER_BOUND)
        ),
        "PARENT_FREEZE_MATCH": (
            config.get("parent_freeze_sha256") == sha256_path(Q9_FREEZE)
            and config.get("clean_formal_parent_freeze_sha256") == sha256_path(Q8_FREEZE)
            and config.get("q9_postrun_audit_sha256") == sha256_path(Q9_AUDIT)
            and auth.get("parent_evidence", {}).get("q9_terminal_freeze_sha256") == sha256_path(Q9_FREEZE)
        ),
        "LEDGER_MATCH": (
            meta.get("revision_id") == REV_ID
            and meta.get("authorization_sha256") == sha256_path(AUTH_PATH)
            and meta.get("plan_sha256") == sha256_path(PLAN_PATH)
            and meta.get("run_config_sha256") == sha256_path(CONFIG_PATH)
            and meta.get("runner_sha256") == sha256_path(RUNNER)
            and db_ids == plan_ids
            and len(db_rows) == 30
            and all(r["state"] == "NOT_STARTED" for r in db_rows)
            and all(r["adapter_version"] == ADAPTER_VERSION for r in db_rows)
            and all(r["render_prompt_sha256"] == rows[i]["render_prompt_sha256"] for i, r in enumerate(db_rows))
        ),
    }
    audit = {
        "captured_at": utc(),
        "revision_id": REV_ID,
        "status": "PREFLIGHT_BINDING_PASS" if all(flags.values()) else "PREFLIGHT_BINDING_BLOCKED",
        "provider_requests_sent_before_audit": 0,
        "flags": flags,
        "all_flags_true": all(flags.values()),
        "hashes": {
            "authorization_sha256": sha256_path(AUTH_PATH),
            "plan_sha256": sha256_path(PLAN_PATH),
            "run_config_sha256": sha256_path(CONFIG_PATH),
            "runner_sha256": sha256_path(RUNNER),
            "ledger_sha256_at_audit": sha256_path(LEDGER_PATH),
            "q8_clean_formal_parent_freeze_sha256": sha256_path(Q8_FREEZE),
            "q9_parent_freeze_sha256": sha256_path(Q9_FREEZE),
            "q9_postrun_audit_sha256": sha256_path(Q9_AUDIT),
        },
        "limits": {
            "authorization": auth_limits,
            "run_config": config_limits,
            "ledger": {k: meta.get(k) for k in [
                "max_logical_invocations",
                "max_physical_attempt_lower_bound",
                "native_max_retries",
                "max_unique_native_retry_events",
                "max_confirmed_policy_refusals",
                "concurrency",
                "outer_retry",
            ]},
        },
    }
    return audit


def write_preflight_reports(accounting: dict[str, Any], selected: list[dict[str, str]],
                            parent: dict[str, Any], doctor_safe: dict[str, Any]) -> None:
    del selected, doctor_safe
    report_pref = f"""# P4D GR3Q10 preflight

- revision: {REV_ID}
- status: PREFLIGHT_BINDING_PASS
- provider requests sent before this report: 0
- provider: {PROVIDER}; runtime: {RUNTIME_EXPECTED}; model: {MODEL}
- parent evidence: Q8 clean freeze {parent['q8_clean_formal_parent']['freeze_sha256']}; Q9 terminal evidence {parent['q9_latest_execution_evidence']['freeze_sha256']} with status BOUND_BUT_NOT_FORMALLY_ACCEPTED
- current accounting: clean {accounting['clean_success']} + binding-blocked {accounting['binding_blocked_success']} + completion-unknown {accounting['completion_unknown']} + safe-outstanding {accounting['safe_executable_outstanding']} = {accounting['sum']}
- active dataset was only read through the formal validator; no media, label, batch, split, C3, VAL, Holdout, or production artifact was changed.

The Q9 mismatch is preserved as historical evidence. This revision uses a new self-consistent authorization, plan, runner identity, ledger, and limits.
"""
    report_plan = f"""# P4D GR3Q10 deterministic plan

- revision: {REV_ID}
- planned logical invocations: 30
- planned physical-attempt lower-bound cap: {MAX_PHYSICAL_LOWER_BOUND}
- concurrency: {CONCURRENCY}; outer retry: {str(OUTER_RETRY).lower()}; native max retries: {NATIVE_MAX_RETRIES}
- role balance: HN20 / positive5 / ordinary-negative5
- split balance: NEW_DESIGN20 / NEW_SCREEN10
- selected complete groups: {", ".join(SELECTED_GROUPS)}
- plan SHA-256: {sha256_path(PLAN_PATH)}
- authorization SHA-256: {sha256_path(AUTH_PATH)}
- run-config SHA-256: {sha256_path(CONFIG_PATH)}
- runner SHA-256: {sha256_path(RUNNER)}

Selection rationale: {SELECTION_REASON}

No Q9 slot, no completion-unknown slot, and no cross-group or cross-split slot is selected. The render prompt bytes come from the frozen adapter manifest and each row's UTF-8 byte hash is checked before execution.
"""
    write_text(REPORT_PREFLIGHT, report_pref)
    write_text(REPORT_PLAN, report_plan)


def init_revision() -> None:
    require(RUNNER.is_file(), f"runner source missing: {RUNNER}")
    # If an earlier no-provider initialization reached the ledger but failed
    # inside the binding audit, repair only the unsealed binding projection.
    # Never regenerate or overwrite the source/accounting evidence from that
    # attempt.
    if AUTH_PATH.exists() or PLAN_PATH.exists() or CONFIG_PATH.exists() or LEDGER_PATH.exists():
        require(
            AUTH_PATH.is_file() and PLAN_PATH.is_file() and CONFIG_PATH.is_file() and LEDGER_PATH.is_file(),
            "refusing to repair an incomplete initialized revision",
        )
        require(
            not PREFLIGHT_AUDIT.exists() and not READY_PATH.exists(),
            "refusing to reinitialize a revision that already passed binding or became executable",
        )
        config = read_json(CONFIG_PATH)
        old_config_sha = sha256_path(CONFIG_PATH)
        old_runner_sha = config.get("runner_sha256")
        current_runner_sha = sha256_path(RUNNER)
        if old_runner_sha != current_runner_sha:
            config["runner_sha256"] = current_runner_sha
            write_json(CONFIG_PATH, config)
        new_config_sha = sha256_path(CONFIG_PATH)
        conn = sqlite3.connect(LEDGER_PATH)
        try:
            meta = ledger_metadata(conn)
            require(meta.get("authorization_sha256") == sha256_path(AUTH_PATH),
                    "PREFLIGHT_BLOCKED: repair found authorization hash drift")
            require(meta.get("plan_sha256") == sha256_path(PLAN_PATH),
                    "PREFLIGHT_BLOCKED: repair found plan hash drift")
            conn.execute("UPDATE metadata SET value=? WHERE key='run_config_sha256'", (new_config_sha,))
            conn.execute("UPDATE metadata SET value=? WHERE key='runner_sha256'", (current_runner_sha,))
            conn.commit()
        finally:
            conn.close()
        write_json(preflight_artifact_path("preflight_rebind_attempt_003.json"), {
            "captured_at": utc(),
            "status": "PREVIOUS_INITIALIZATION_REBOUND_BEFORE_PROVIDER",
            "provider_requests_sent": 0,
            "old_config_sha256": old_config_sha,
            "new_config_sha256": new_config_sha,
            "old_runner_sha256": old_runner_sha,
            "new_runner_sha256": current_runner_sha,
            "ledger_sha256_after_rebind": sha256_path(LEDGER_PATH),
        })
        audit = make_binding_audit()
        write_json(PREFLIGHT_AUDIT, audit)
        require(audit["all_flags_true"], "PREFLIGHT_BINDING_BLOCKED: repaired binding still has a false flag")
        accounting = read_json(PRE / "partition_rebuild_attempt_002.json")["accounting"]
        parent = load_parent_evidence()
        doctor_safe = read_json(PRE / "provider_runtime.json")
        write_json(READY_PATH, {
            "captured_at": utc(),
            "revision_id": REV_ID,
            "status": "READY_FOR_AUTHORIZED_EXECUTION",
            "PREFLIGHT_BINDING_BLOCKED": False,
            "provider_requests_sent": 0,
            "flags": audit["flags"],
            "hashes": audit["hashes"],
            "limits": audit["limits"]["run_config"],
            "holdout_requests": 0,
            "formal_ingest": False,
            "c3": False,
            "val": False,
        })
        write_preflight_reports(accounting, plan_rows(), parent, doctor_safe)
        print(json.dumps({
            "status": "PREFLIGHT_BINDING_PASS",
            "revision_id": REV_ID,
            "provider_requests_sent": 0,
            "accounting": accounting,
            "plan_sha256": sha256_path(PLAN_PATH),
            "authorization_sha256": sha256_path(AUTH_PATH),
            "run_config_sha256": sha256_path(CONFIG_PATH),
            "runner_sha256": current_runner_sha,
            "ledger_sha256": sha256_path(LEDGER_PATH),
            "preflight_binding_sha256": sha256_path(PREFLIGHT_AUDIT),
        }, ensure_ascii=False, indent=2))
        return
    allowed = {RUNNER.resolve()}
    if REV.exists():
        unexpected = [
            p for p in REV.rglob("*")
            if p.is_file()
            and p.resolve() not in allowed
            and "__pycache__" not in p.parts
            and PRE not in p.parents
        ]
        require(not unexpected, "refusing to overwrite non-empty new revision: " + str(unexpected[:3]))
    REV.mkdir(parents=True, exist_ok=True)
    for path in [
        PRE, AUTH_DIR, LEDGER_DIR, RAW_RESP_DIR, CHECK_DIR, QA_DIR, RAW_DIR,
        FINAL_DIR, STAGING_RAW, STAGING_AMBIGUOUS, FREEZE_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    require(not AUTH_PATH.exists() and not PLAN_PATH.exists() and not CONFIG_PATH.exists()
            and not LEDGER_PATH.exists(), "new revision initialization artifacts already exist")
    accounting, full, adapter = load_accounting()
    parent = load_parent_evidence()
    _, doctor_safe = run_codex_doctor()
    write_json(preflight_artifact_path("provider_runtime.json"), doctor_safe)
    run_dataset_validator("before")
    _safe_fields, safe_rows = read_csv(Q9_SAFE)
    _unknown_fields, unknown_rows = read_csv(Q9_UNKNOWN)
    _verified_fields, _verified_rows = read_csv(Q9_VERIFIED)
    safe_ids = {r["prompt_id"] for r in safe_rows}
    unknown_ids = {r["prompt_id"] for r in unknown_rows}
    q9_ids = {r["prompt_id"] for r in read_csv(Q9_PLAN)[1]}
    selected = build_plan(full, adapter, safe_ids, unknown_ids, q9_ids)
    parent_evidence = {
        "q8_clean_formal_parent_freeze_sha256": parent["q8_clean_formal_parent"]["freeze_sha256"],
        "q9_terminal_freeze_sha256": parent["q9_latest_execution_evidence"]["freeze_sha256"],
        "q9_postrun_audit_sha256": parent["q9_latest_execution_evidence"]["audit_sha256"],
        "q9_binding_status": "BOUND_BUT_NOT_FORMALLY_ACCEPTED",
        "q9_plan_sha256": accounting["q9_plan_sha256"],
    }
    authorization = {
        "authorized": True,
        "revision_id": REV_ID,
        "stage": "P4D_GR3Q10_BALANCED_COMPLETE_GROUP_WINDOW",
        "captured_at": utc(),
        "parent_evidence": parent_evidence,
        "selected_prompt_ids": [r["prompt_id"] for r in selected],
        "selected_groups": SELECTED_GROUPS,
        "selection_reason": SELECTION_REASON,
        "provider": PROVIDER,
        "request_model": MODEL,
        "runtime_expected": RUNTIME_EXPECTED,
        "generation_backend": GENERATION_BACKEND,
        "adapter_version": ADAPTER_VERSION,
        "requested_native_size": NATIVE_SIZE,
        "final_output_dimension_contract": "1920x1080",
        "quality": QUALITY,
        "format": IMAGE_FORMAT,
        "native_size_contract_enforced": False,
        "concurrency": CONCURRENCY,
        "outer_retry": OUTER_RETRY,
        "native_max_retries": NATIVE_MAX_RETRIES,
        "max_logical_invocations": MAX_LOGICAL,
        "max_physical_attempt_lower_bound": MAX_PHYSICAL_LOWER_BOUND,
        "max_unique_native_retry_events": MAX_NATIVE_RETRY_EVENTS,
        "max_confirmed_policy_refusals": MAX_POLICY_REFUSALS,
        "formal_ingest": False,
        "c3": False,
        "val": False,
        "holdout_requests": 0,
        "human_review": False,
        "ground_truth_assignment": False,
    }
    write_json(AUTH_PATH, authorization)
    auth_sha = sha256_path(AUTH_PATH)
    shutil.copyfile(PARSER_SOURCE, PARSER_COPY)
    shutil.copyfile(CLASSIFIER_SOURCE, CLASSIFIER_COPY)
    parser_sha = sha256_path(PARSER_COPY)
    classifier_sha = sha256_path(CLASSIFIER_COPY)
    runner_sha = sha256_path(RUNNER)
    config = {
        "revision_id": REV_ID,
        "stage": "P4D_GR3Q10_BALANCED_COMPLETE_GROUP_WINDOW",
        "authorization_sha256": auth_sha,
        "plan_sha256": sha256_path(PLAN_PATH),
        "runner_sha256": runner_sha,
        "runner_path": str(RUNNER),
        "node_path": str(NODE),
        "provider": PROVIDER,
        "request_model": MODEL,
        "runtime_expected": RUNTIME_EXPECTED,
        "generation_backend": GENERATION_BACKEND,
        "adapter_version": ADAPTER_VERSION,
        "adapter_manifest_sha256": accounting["adapter_manifest_sha256"],
        "full_manifest_sha256": accounting["full_manifest_sha256"],
        "q9_plan_sha256": accounting["q9_plan_sha256"],
        "q9_postrun_audit_sha256": parent_evidence["q9_postrun_audit_sha256"],
        "parent_freeze_sha256": parent_evidence["q9_terminal_freeze_sha256"],
        "clean_formal_parent_freeze_sha256": parent_evidence["q8_clean_formal_parent_freeze_sha256"],
        "requested_native_size": NATIVE_SIZE,
        "native_size_contract_enforced": False,
        "final_output_dimension_contract": "1920x1080",
        "quality": QUALITY,
        "format": IMAGE_FORMAT,
        "concurrency": CONCURRENCY,
        "outer_retry": OUTER_RETRY,
        "native_max_retries": NATIVE_MAX_RETRIES,
        "max_logical_invocations": MAX_LOGICAL,
        "max_physical_attempt_lower_bound": MAX_PHYSICAL_LOWER_BOUND,
        "max_unique_native_retry_events": MAX_NATIVE_RETRY_EVENTS,
        "max_confirmed_policy_refusals": MAX_POLICY_REFUSALS,
        "parser_sha256": parser_sha,
        "classifier_sha256": classifier_sha,
        "formal_ingest": False,
        "c3": False,
        "val": False,
        "holdout_requests": 0,
        "provider_default_not_used": True,
    }
    write_json(CONFIG_PATH, config)
    config_sha = sha256_path(CONFIG_PATH)
    create_ledger(selected, auth_sha, sha256_path(PLAN_PATH), config_sha, runner_sha)
    write_text(REQUEST_LOG, "")
    write_text(RAW_LOG, "")
    audit = make_binding_audit()
    write_json(PREFLIGHT_AUDIT, audit)
    require(audit["all_flags_true"], "PREFLIGHT_BINDING_BLOCKED: at least one binding flag is false")
    write_json(READY_PATH, {
        "captured_at": utc(),
        "revision_id": REV_ID,
        "status": "READY_FOR_AUTHORIZED_EXECUTION",
        "PREFLIGHT_BINDING_BLOCKED": False,
        "provider_requests_sent": 0,
        "flags": audit["flags"],
        "hashes": audit["hashes"],
        "limits": audit["limits"]["run_config"],
        "holdout_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "val": False,
    })
    write_preflight_reports(accounting, selected, parent, doctor_safe)
    print(json.dumps({
        "status": "PREFLIGHT_BINDING_PASS",
        "revision_id": REV_ID,
        "provider_requests_sent": 0,
        "accounting": accounting,
        "plan_sha256": sha256_path(PLAN_PATH),
        "authorization_sha256": sha256_path(AUTH_PATH),
        "run_config_sha256": sha256_path(CONFIG_PATH),
        "runner_sha256": runner_sha,
        "ledger_sha256": sha256_path(LEDGER_PATH),
        "preflight_binding_sha256": sha256_path(PREFLIGHT_AUDIT),
    }, ensure_ascii=False, indent=2))


def load_runtime_modules() -> tuple[Any, Any]:
    sys.path.insert(0, str(RUNNER_DIR))
    parser = importlib.import_module("retry_event_parser_v2")
    classifier = importlib.import_module("provider_failure_classifier_v2")
    return parser, classifier


def verify_image(path: Path) -> tuple[int, int]:
    require(path.is_file() and path.stat().st_size > 0, f"missing/empty image: {path}")
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            img.load()
            width, height = img.size
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise GateBlocked(f"image decode/verify failed: {path}: {exc}") from exc
    require(width > 0 and height > 0, f"invalid image dimensions: {path}")
    return width, height


def make_final(raw: Path, final: Path) -> tuple[int, int]:
    with Image.open(raw) as img:
        img.load()
        source = img.convert("RGB")
    src_w, src_h = source.size
    target_ratio = FINAL_SIZE[0] / FINAL_SIZE[1]
    source_ratio = src_w / src_h
    if source_ratio > target_ratio:
        crop_w = int(round(src_h * target_ratio))
        left = max(0, (src_w - crop_w) // 2)
        source = source.crop((left, 0, left + crop_w, src_h))
    elif source_ratio < target_ratio:
        crop_h = int(round(src_w / target_ratio))
        top = max(0, (src_h - crop_h) // 2)
        source = source.crop((0, top, src_w, top + crop_h))
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    source = source.resize(FINAL_SIZE, resampling)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + f".tmp.{os.getpid()}")
    source.save(tmp, format="PNG")
    source.close()
    os.replace(tmp, final)
    return verify_image(final)


def open_ledger() -> sqlite3.Connection:
    require(LEDGER_PATH.is_file(), "execution ledger is missing")
    conn = sqlite3.connect(LEDGER_PATH)
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def event(conn: sqlite3.Connection, prompt_id: str, event_type: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO events(prompt_id,event_type,at,payload_json) VALUES(?,?,?,?)",
        (prompt_id, event_type, utc(), json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )


def execution_start_gate() -> dict[str, Any]:
    ready = read_json(READY_PATH)
    require(ready.get("status") == "READY_FOR_AUTHORIZED_EXECUTION"
            and ready.get("PREFLIGHT_BINDING_BLOCKED") is False,
            "PREFLIGHT_BINDING_BLOCKED: ready checkpoint is not executable")
    audit = make_binding_audit()
    require(audit["all_flags_true"], "PREFLIGHT_BINDING_BLOCKED: binding changed before execution")
    _, doctor_safe = run_codex_doctor()
    config = read_json(CONFIG_PATH)
    require(doctor_safe.get("version") == RUNTIME_EXPECTED,
            "PREFLIGHT_BINDING_BLOCKED: pre-request runtime changed")
    write_json(PRE / "provider_runtime_pre_request.json", doctor_safe)
    start_audit = {
        "captured_at": utc(),
        "revision_id": REV_ID,
        "status": "EXECUTION_START_BINDING_PASS",
        "provider_requests_sent_before_audit": 0,
        "preflight_binding_sha256": sha256_path(PREFLIGHT_AUDIT),
        "fresh_provider_runtime_sha256": sha256_path(PRE / "provider_runtime_pre_request.json"),
        "flags": audit["flags"],
        "all_flags_true": audit["all_flags_true"],
        "actual_stack": {
            "provider": config["provider"],
            "model": config["request_model"],
            "runtime": doctor_safe.get("version"),
            "adapter_version": config["adapter_version"],
            "native_size": config["requested_native_size"],
            "final_size": config["final_output_dimension_contract"],
            "concurrency": config["concurrency"],
            "outer_retry": config["outer_retry"],
            "native_max_retries": config["native_max_retries"],
        },
    }
    write_json(CHECK_DIR / "execution_start_binding_audit.json", start_audit)
    return config


def invoke_one(row: dict[str, str], index: int, config: dict[str, Any],
               parser_module: Any, classifier_module: Any) -> dict[str, Any]:
    del config
    pid = row["prompt_id"]
    raw = RAW_DIR / f"{pid}.png"
    final = FINAL_DIR / f"{pid}.png"
    tmp_raw = STAGING_RAW / f"{pid}.png"
    require(not raw.exists() and not final.exists() and not tmp_raw.exists(),
            f"refusing to overwrite output for {pid}")
    request_record = {
        "at": utc(),
        "revision_id": REV_ID,
        "request_index": index,
        "prompt_id": pid,
        "provider": PROVIDER,
        "model": MODEL,
        "render_prompt_sha256": row["render_prompt_sha256"],
        "command": {
            "provider": PROVIDER,
            "operation": "images generate",
            "model": MODEL,
            "format": IMAGE_FORMAT,
            "size": NATIVE_SIZE,
            "quality": QUALITY,
            "native_max_retries": NATIVE_MAX_RETRIES,
            "outer_retry": OUTER_RETRY,
            "out_path": str(tmp_raw),
        },
        "state_before_request": "STARTED",
        "provider_request_is_not_human_review_or_ground_truth": True,
    }
    append_jsonl(REQUEST_LOG, request_record)
    cmd = [
        str(NODE), str(CLI), "--json", "--json-events", "--provider", PROVIDER,
        "images", "generate", "--model", MODEL, "--prompt", row["render_prompt"],
        "--out", str(tmp_raw), "--format", IMAGE_FORMAT, "--size", NATIVE_SIZE,
        "--quality", QUALITY,
    ]
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(CLI.parent.parent),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        returncode = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stderr += "\nSUBPROCESS_TIMEOUT"
    except OSError as exc:
        returncode = -127
        stdout = ""
        stderr = f"SUBPROCESS_START_ERROR: {exc}"
    latency = time.monotonic() - started
    outer = parse_last_json(stdout)
    events = parser_module.parse_json_events(stderr)
    telemetry = parser_module.telemetry_from_events(events)
    physical_lb = max(1, int(telemetry.get("physical_attempt_lower_bound", 0)))
    if timed_out:
        classification = {
            "state": "COMPLETION_UNKNOWN",
            "reason": "SUBPROCESS_TIMEOUT_COMPLETION_AMBIGUITY",
            "evidence": {"no_resend": True},
        }
    else:
        classification = classifier_module.classify({
            "outer_json": outer,
            "stderr_redacted": scrub_text(stderr),
        })
    state = "FAILED_CONFIRMED"
    reason = classification.get("reason", "UNCLASSIFIED_PROVIDER_FAILURE")
    raw_w, raw_h = None, None
    final_w, final_h = None, None
    raw_sha = None
    final_sha = None
    output_status = "NOT_ACCEPTED"
    if (
        not timed_out
        and returncode == 0
        and outer.get("ok") is True
        and tmp_raw.is_file()
    ):
        try:
            raw_w, raw_h = verify_image(tmp_raw)
            os.replace(tmp_raw, raw)
            raw_sha = sha256_path(raw)
            final_w, final_h = make_final(raw, final)
            final_sha = sha256_path(final)
            state = "SUCCESS"
            reason = "NONE"
            output_status = "MECHANICAL_CANDIDATE_ONLY"
        except (GateBlocked, OSError, UnidentifiedImageError, SyntaxError) as exc:
            state = "FAILED_CONFIRMED"
            reason = "MECHANICAL_OUTPUT_INVALID"
            output_status = f"INVALID_OUTPUT_RETAINED:{type(exc).__name__}"
            if tmp_raw.exists():
                STAGING_AMBIGUOUS.mkdir(parents=True, exist_ok=True)
                os.replace(tmp_raw, STAGING_AMBIGUOUS / f"{pid}.png")
    elif tmp_raw.exists():
        STAGING_AMBIGUOUS.mkdir(parents=True, exist_ok=True)
        ambiguous = STAGING_AMBIGUOUS / f"{pid}.png"
        os.replace(tmp_raw, ambiguous)
        output_status = "AMBIGUOUS_PROVIDER_OUTPUT_RETAINED"
    if state != "SUCCESS":
        if classification.get("state") == "COMPLETION_UNKNOWN":
            state = "COMPLETION_UNKNOWN"
            reason = classification.get("reason", reason)
        elif classification.get("state") == "CONTENT_POLICY_REFUSAL_CONFIRMED":
            state = "CONTENT_POLICY_REFUSAL_CONFIRMED"
            reason = classification.get("reason", reason)
        else:
            state = "FAILED_CONFIRMED"
    record = {
        "revision_id": REV_ID,
        "prompt_id": pid,
        "request_index": index,
        "adapter_version": ADAPTER_VERSION,
        "render_prompt_sha256": row["render_prompt_sha256"],
        "command_config": {
            "provider": PROVIDER,
            "model": MODEL,
            "generation_backend": GENERATION_BACKEND,
            "size": NATIVE_SIZE,
            "format": IMAGE_FORMAT,
            "quality": QUALITY,
            "native_max_retries": NATIVE_MAX_RETRIES,
            "outer_retry": OUTER_RETRY,
            "native_size_contract_enforced": False,
        },
        "returncode": returncode,
        "http_status": 200 if state == "SUCCESS" else None,
        "latency_seconds": latency,
        "outer_json": redact_json(outer),
        "stdout_redacted": scrub_text(stdout),
        "stderr_redacted": scrub_text(stderr),
        "provider_events": telemetry,
        "failure_classification": classification if state != "SUCCESS" else None,
        "failure_reason": reason,
        "state": state,
        "raw_path": str(raw) if raw.exists() else None,
        "final_path": str(final) if final.exists() else None,
        "raw_sha256": raw_sha,
        "final_sha256": final_sha,
        "raw_dimensions": [raw_w, raw_h] if raw_w and raw_h else None,
        "final_dimensions": [final_w, final_h] if final_w and final_h else None,
        "output_status": output_status,
        "no_resend": state == "COMPLETION_UNKNOWN",
        "formal_ingest": False,
        "human_review": False,
        "ground_truth_assignment": False,
    }
    response_path = RAW_RESP_DIR / f"{pid}.json"
    record["physical_attempt_lower_bound"] = physical_lb
    write_json(response_path, record)
    record["response_json_sha256"] = sha256_path(response_path)
    append_jsonl(RAW_LOG, record)
    return record


def run_execution() -> None:
    config = execution_start_gate()
    parser_module, classifier_module = load_runtime_modules()
    with LOCK_PATH.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GateBlocked("another GR3Q10 runner holds the active-runner lock") from exc
        conn = open_ledger()
        try:
            states = [r[0] for r in conn.execute("SELECT state FROM slots ORDER BY ordinal")]
            require(states and all(s == "NOT_STARTED" for s in states),
                    "RESUME_BLOCKED: ledger contains a prior STARTED or terminal slot")
            rows = plan_rows()
            logical = 0
            physical = 0
            retry_events = 0
            refusals = 0
            terminal_reason = "PLAN_NOT_STARTED"
            for index, row in enumerate(rows, start=1):
                require(logical < MAX_LOGICAL, "execution attempted logical limit+1")
                require(physical < MAX_PHYSICAL_LOWER_BOUND, "execution attempted physical limit+1")
                pid = row["prompt_id"]
                current = conn.execute(
                    "SELECT state FROM slots WHERE prompt_id=?", (pid,)
                ).fetchone()
                require(current and current[0] == "NOT_STARTED", f"slot is not NOT_STARTED: {pid}")
                started_at = utc()
                conn.execute(
                    "UPDATE slots SET state='STARTED',started_at=? WHERE prompt_id=?",
                    (started_at, pid),
                )
                event(conn, pid, "STARTED_DURABLE_BEFORE_PROVIDER", {
                    "request_index": index,
                    "logical_before": logical,
                    "physical_before": physical,
                    "no_outer_retry": True,
                })
                conn.commit()
                record = invoke_one(row, index, config, parser_module, classifier_module)
                logical += 1
                physical += int(record["physical_attempt_lower_bound"])
                retry_events += int(record["provider_events"].get("unique_native_retry_events", 0))
                if record["state"] == "CONTENT_POLICY_REFUSAL_CONFIRMED":
                    refusals += 1
                conn.execute(
                    """
                    UPDATE slots SET
                        state=?,terminal_at=?,returncode=?,http_status=?,
                        classification_state=?,failure_reason=?,
                        unique_native_retry_events=?,request_started_events=?,
                        physical_attempt_lower_bound=?,raw_sha256=?,final_sha256=?,
                        response_json_sha256=?
                    WHERE prompt_id=?
                    """,
                    (
                        record["state"],
                        utc(),
                        record["returncode"],
                        record["http_status"],
                        record["state"],
                        record["failure_reason"],
                        record["provider_events"].get("unique_native_retry_events", 0),
                        record["provider_events"].get("request_started_events", 0),
                        record["physical_attempt_lower_bound"],
                        record["raw_sha256"],
                        record["final_sha256"],
                        record["response_json_sha256"],
                        pid,
                    ),
                )
                event(conn, pid, "TERMINAL", {
                    "state": record["state"],
                    "reason": record["failure_reason"],
                    "logical_after": logical,
                    "physical_after": physical,
                    "retry_events_after": retry_events,
                    "no_resend": record["no_resend"],
                })
                conn.commit()
                print(json.dumps({
                    "prompt_id": pid,
                    "state": record["state"],
                    "logical": logical,
                    "physical_attempt_lower_bound": physical,
                    "native_retry_events": retry_events,
                }, ensure_ascii=False), flush=True)
                if record["state"] != "SUCCESS":
                    terminal_reason = f"STOP_AFTER_{record['state']}"
                    break
                if logical >= MAX_LOGICAL:
                    terminal_reason = "LOGICAL_LIMIT_REACHED_NO_LIMIT_PLUS_ONE"
                    break
                if physical >= MAX_PHYSICAL_LOWER_BOUND:
                    terminal_reason = "PHYSICAL_LIMIT_REACHED_NO_LIMIT_PLUS_ONE"
                    break
                if retry_events >= MAX_NATIVE_RETRY_EVENTS:
                    terminal_reason = "NATIVE_RETRY_EVENT_LIMIT_REACHED"
                    break
                if refusals >= MAX_POLICY_REFUSALS:
                    terminal_reason = "POLICY_REFUSAL_LIMIT_REACHED"
                    break
            else:
                terminal_reason = "PLAN_EXHAUSTED"
            terminal = {
                "captured_at": utc(),
                "revision_id": REV_ID,
                "provider_requests_sent": logical,
                "logical_invocations": logical,
                "physical_attempt_lower_bound": physical,
                "unique_native_retry_events_upper_bound": retry_events,
                "content_policy_refusals": refusals,
                "terminal_stop_reason": terminal_reason,
                "limits": {
                    "max_logical_invocations": MAX_LOGICAL,
                    "max_physical_attempt_lower_bound": MAX_PHYSICAL_LOWER_BOUND,
                    "max_unique_native_retry_events": MAX_NATIVE_RETRY_EVENTS,
                    "max_confirmed_policy_refusals": MAX_POLICY_REFUSALS,
                },
                "no_resume_after_unknown": True,
                "no_provider_request_after_stop": True,
                "formal_ingest": False,
                "c3": False,
                "val": False,
                "holdout_requests": 0,
            }
            write_json(GLOBAL_STOP, terminal)
            counts = Counter(r[0] for r in conn.execute("SELECT state FROM slots"))
            summary = {
                **terminal,
                "slot_state_counts": dict(counts),
                "plan_rows": len(rows),
                "raw_response_rows": sum(1 for _ in RAW_LOG.open(encoding="utf-8")),
                "request_log_rows": sum(1 for _ in REQUEST_LOG.open(encoding="utf-8")),
            }
            write_json(TERMINAL_SUMMARY, summary)
        finally:
            conn.close()
    write_text(REPORT_EXECUTION, f"""# P4D GR3Q10 execution

- revision: {REV_ID}
- status: terminal execution checkpoint written
- provider: {PROVIDER} / model {MODEL} / runtime {RUNTIME_EXPECTED}
- generation backend: {GENERATION_BACKEND}
- provider requests sent: see {GLOBAL_STOP}
- durable transition: every attempted slot was committed STARTED before its provider call; unknown/ambiguous results are never resent.
- formal ingest: false; C3: false; VAL: false; Holdout requests: 0

The terminal summary is evidence of this one window only. Mechanical QA is run separately and does not turn these images into ground truth.
""")


def load_db_rows() -> dict[str, dict[str, Any]]:
    conn = open_ledger()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM slots ORDER BY ordinal").fetchall()
        return {r["prompt_id"]: dict(r) for r in rows}
    finally:
        conn.close()


def prior_png_hashes(exclude: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    all_hashes: dict[str, list[str]] = {}
    gr1_hashes: dict[str, list[str]] = {}
    gr1_root = GR3.parent / "gr1"
    for p in GR3.rglob("*.png"):
        if exclude in p.parents:
            continue
        all_hashes.setdefault(sha256_path(p), []).append(str(p))
    if gr1_root.is_dir():
        for p in gr1_root.rglob("*.png"):
            gr1_hashes.setdefault(sha256_path(p), []).append(str(p))
    return all_hashes, gr1_hashes


def base_partition_rows() -> tuple[list[str], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    vf, verified = read_csv(Q9_VERIFIED)
    uf, unknown = read_csv(Q9_UNKNOWN)
    sf, safe = read_csv(Q9_SAFE)
    require(vf == uf == sf, "base partition CSV headers differ")
    return vf, verified, unknown, safe


def normalized_new_row(row: dict[str, Any], source: str, reason: str,
                       raw: str = "", final: str = "", raw_sha: str = "", final_sha: str = "") -> dict[str, str]:
    return {
        "prompt_id": row["prompt_id"],
        "role": row["role"],
        "taxonomy": row["taxonomy"],
        "planned_split": row["planned_split"],
        "source": source,
        "raw_path": raw,
        "final_path": final,
        "raw_sha256": raw_sha,
        "final_sha256": final_sha,
        "adapter_version": row["adapter_version"],
        "reason": reason,
    }


def make_qa() -> dict[str, Any]:
    require(GLOBAL_STOP.is_file(), "cannot QA before terminal execution checkpoint")
    rows = plan_rows()
    db = load_db_rows()
    all_prior, gr1_hashes = prior_png_hashes(REV)
    qa_rows: list[dict[str, Any]] = []
    passed_ids: set[str] = set()
    unknown_ids: set[str] = set()
    safe_new: set[str] = set()
    for row in rows:
        pid = row["prompt_id"]
        slot = db[pid]
        raw = RAW_DIR / f"{pid}.png"
        final = FINAL_DIR / f"{pid}.png"
        raw_exists = raw.is_file()
        final_exists = final.is_file()
        raw_sha = sha256_path(raw) if raw_exists else ""
        final_sha = sha256_path(final) if final_exists else ""
        raw_dims = None
        final_dims = None
        decode_ok = True
        try:
            if raw_exists:
                raw_dims = list(verify_image(raw))
            if final_exists:
                final_dims = list(verify_image(final))
        except GateBlocked:
            decode_ok = False
        prior_raw_collision = raw_sha in all_prior if raw_sha else False
        prior_final_collision = final_sha in all_prior if final_sha else False
        gr1_raw_collision = raw_sha in gr1_hashes if raw_sha else False
        gr1_final_collision = final_sha in gr1_hashes if final_sha else False
        ledger_consistent = (
            slot["raw_sha256"] == (raw_sha or None)
            and slot["final_sha256"] == (final_sha or None)
        )
        response_path = RAW_RESP_DIR / f"{pid}.json"
        response = read_json(response_path) if response_path.is_file() else {}
        provenance_ok = (
            response.get("revision_id") == REV_ID
            and response.get("adapter_version") == ADAPTER_VERSION
            and response.get("render_prompt_sha256") == row["render_prompt_sha256"]
            and response.get("command_config", {}).get("provider") == PROVIDER
            and response.get("command_config", {}).get("model") == MODEL
            and response.get("command_config", {}).get("native_max_retries") == NATIVE_MAX_RETRIES
            and response.get("command_config", {}).get("outer_retry") is False
        )
        foreign_event = not (str(raw).startswith(str(REV)) and str(final).startswith(str(REV)))
        native_size_contract_observed = (
            isinstance(response.get("raw_dimensions"), list)
            and response.get("raw_dimensions") == [1536, 1024]
        )
        mechanical_pass = (
            slot["state"] == "SUCCESS"
            and raw_exists
            and final_exists
            and decode_ok
            and final_dims == list(FINAL_SIZE)
            and provenance_ok
            and ledger_consistent
            and not foreign_event
            and not prior_raw_collision
            and not prior_final_collision
            and not gr1_raw_collision
            and not gr1_final_collision
        )
        if mechanical_pass:
            passed_ids.add(pid)
        elif slot["state"] == "COMPLETION_UNKNOWN":
            unknown_ids.add(pid)
        else:
            safe_new.add(pid)
        qa_rows.append({
            "prompt_id": pid,
            "group_id": row["group_id"],
            "role": row["role"],
            "taxonomy": row["taxonomy"],
            "planned_split": row["planned_split"],
            "ledger_state": slot["state"],
            "mechanical_pass": str(mechanical_pass),
            "raw_exists": str(raw_exists),
            "final_exists": str(final_exists),
            "raw_dimensions": json.dumps(raw_dims),
            "final_dimensions": json.dumps(final_dims),
            "requested_native_size": NATIVE_SIZE,
            "native_size_contract_enforced": "False",
            "native_size_match": str(native_size_contract_observed),
            "raw_sha256": raw_sha,
            "final_sha256": final_sha,
            "exact_duplicate_with_prior_raw": str(prior_raw_collision),
            "exact_duplicate_with_prior_final": str(prior_final_collision),
            "gr1_sha_collision_raw": str(gr1_raw_collision),
            "gr1_sha_collision_final": str(gr1_final_collision),
            "foreign_event_asset": str(foreign_event),
            "adapter_provenance": str(provenance_ok),
            "ledger_raw_final_consistent": str(ledger_consistent),
            "response_path": str(response_path),
        })
    qa_fields = list(qa_rows[0])
    write_csv(QA_DIR / "mechanical_qa.csv", qa_fields, qa_rows)

    base_fields, base_verified, base_unknown, base_safe = base_partition_rows()
    base_verified_ids = {r["prompt_id"] for r in base_verified}
    base_unknown_ids = {r["prompt_id"] for r in base_unknown}
    base_safe_ids = {r["prompt_id"] for r in base_safe}
    require(not passed_ids & base_verified_ids and not unknown_ids & base_unknown_ids,
            "QA partition overlap with base partition")
    verified_additions = []
    unknown_additions = []
    safe_additions = []
    for row in rows:
        pid = row["prompt_id"]
        slot = db[pid]
        response = read_json(RAW_RESP_DIR / f"{pid}.json")
        if pid in passed_ids:
            verified_additions.append(normalized_new_row(
                row, REV_ID, "MECHANICAL_QA_PASS",
                str(RAW_DIR / f"{pid}.png"), str(FINAL_DIR / f"{pid}.png"),
                response.get("raw_sha256") or "", response.get("final_sha256") or "",
            ))
        elif pid in unknown_ids:
            unknown_additions.append(normalized_new_row(
                row, f"{REV_ID}:COMPLETION_UNKNOWN", "NO_RESEND",
            ))
        else:
            safe_additions.append(normalized_new_row(
                row, f"{REV_ID}:SAFE_OUTSTANDING", response.get("failure_reason", "MECHANICAL_QA_FAILED"),
            ))
    verified_out = base_verified + verified_additions
    unknown_out = base_unknown + unknown_additions
    safe_out = [r for r in base_safe if r["prompt_id"] not in passed_ids | unknown_ids] + safe_additions
    full_ids = {r["prompt_id"] for r in read_csv(FULL_MANIFEST)[1]}
    out_sets = [set(r["prompt_id"] for r in verified_out), set(r["prompt_id"] for r in unknown_out), set(r["prompt_id"] for r in safe_out)]
    require(all(len(s) == len({r["prompt_id"] for r in part}) for s, part in zip(out_sets, [verified_out, unknown_out, safe_out])),
            "QA output partition contains duplicate prompt IDs")
    require(
        not (out_sets[0] & out_sets[1])
        and not (out_sets[0] & out_sets[2])
        and not (out_sets[1] & out_sets[2])
        and out_sets[0] | out_sets[1] | out_sets[2] == full_ids,
        "QA output partition is not an exact frozen-440 partition",
    )
    write_csv(QA_DIR / "verified_success.csv", base_fields, verified_out)
    write_csv(QA_DIR / "completion_unknown_quarantine.csv", base_fields, unknown_out)
    write_csv(QA_DIR / "safe_executable_outstanding.csv", base_fields, safe_out)
    dataset_after = run_dataset_validator("after")
    accounting = {
        "target_total": 440,
        "clean_success": 196 + len(passed_ids),
        "binding_blocked_success": 30,
        "completion_unknown": 1 + len(unknown_ids),
        "safe_executable_outstanding": len(safe_out),
        "sum": 196 + len(passed_ids) + 30 + 1 + len(unknown_ids) + len(safe_out),
    }
    require(accounting["sum"] == 440, "QA accounting does not sum to 440")
    q = {
        "captured_at": utc(),
        "revision_id": REV_ID,
        "status": "MECHANICAL_QA_COMPLETE",
        "provider_requests_sent": read_json(GLOBAL_STOP)["provider_requests_sent"],
        "planned_rows": 30,
        "mechanical_pass_rows": len(passed_ids),
        "completion_unknown_rows": len(unknown_ids),
        "safe_return_rows": len(safe_additions),
        "failure_rows": sum(1 for r in qa_rows if r["ledger_state"] in {
            "FAILED_CONFIRMED", "CONTENT_POLICY_REFUSAL_CONFIRMED"
        }),
        "role_counts_mechanical_pass": dict(Counter(next(r["role"] for r in rows if r["prompt_id"] == pid) for pid in passed_ids)),
        "split_counts_mechanical_pass": dict(Counter(next(r["planned_split"] for r in rows if r["prompt_id"] == pid) for pid in passed_ids)),
        "qa_failure_counts": dict(Counter(
            "pass" if r["mechanical_pass"] == "True" else
            "exact_duplicate" if r["exact_duplicate_with_prior_raw"] == "True" or r["exact_duplicate_with_prior_final"] == "True" else
            "decode_or_dimension" if r["raw_exists"] == "False" or r["final_dimensions"] != "[1920, 1080]" else
            "provenance_or_ledger"
            for r in qa_rows
        )),
        "exact_duplicate_with_prior_count": sum(
            r["exact_duplicate_with_prior_raw"] == "True" or r["exact_duplicate_with_prior_final"] == "True" for r in qa_rows
        ),
        "gr1_sha_collision_count": sum(
            r["gr1_sha_collision_raw"] == "True" or r["gr1_sha_collision_final"] == "True" for r in qa_rows
        ),
        "foreign_event_asset_count": sum(r["foreign_event_asset"] == "True" for r in qa_rows),
        "adapter_provenance_fail_count": sum(r["adapter_provenance"] != "True" for r in qa_rows),
        "ledger_consistency_fail_count": sum(r["ledger_raw_final_consistent"] != "True" for r in qa_rows),
        "native_size_observed": sorted({r["raw_dimensions"] for r in qa_rows if r["raw_dimensions"] != "null"}),
        "native_size_contract_enforced": False,
        "P4D_IMAGES_ACCEPTED": 0,
        "formal_ingest": False,
        "human_review": False,
        "ground_truth_assignment": False,
        "c3": False,
        "val": False,
        "holdout_requests": 0,
        "active_dataset_before_after_counts_unchanged": True,
        "dataset_after_validator": dataset_after["validator"],
        "accounting_after": accounting,
    }
    write_json(QA_DIR / "partial_qa.json", q)
    write_text(REPORT_QA, f"""# P4D GR3Q10 mechanical QA

- revision: {REV_ID}
- mechanical candidate rows: 30
- mechanical pass rows: {len(passed_ids)}
- completion-unknown rows: {len(unknown_ids)}; all are quarantined with NO_RESEND
- safe-outstanding return rows: {len(safe_additions)}
- exact-duplicate-with-prior count: {q['exact_duplicate_with_prior_count']}
- GR1 SHA collision count: {q['gr1_sha_collision_count']}
- foreign-event asset count: {q['foreign_event_asset_count']}
- adapter provenance failures: {q['adapter_provenance_fail_count']}
- ledger/raw/final consistency failures: {q['ledger_consistency_fail_count']}
- full accounting: {accounting['clean_success']} clean + {accounting['binding_blocked_success']} binding-blocked + {accounting['completion_unknown']} unknown + {accounting['safe_executable_outstanding']} safe = {accounting['sum']}
- P4D_IMAGES_ACCEPTED: 0
- formal ingest/C3/VAL/Holdout/production: all 0 or false

The native provider dimension is recorded as observed evidence; the run config deliberately keeps native_size_contract_enforced=false because Codex may return a provider-native size different from the request flag. Final outputs are locally normalized to 1920x1080 for mechanical QA only.
""")
    return q


def freeze_revision(qa: dict[str, Any]) -> tuple[str, str]:
    require(not FREEZE_PATH.exists(), "refusing to overwrite terminal freeze")
    overview = f"""# GR3Q10 terminal snapshot

revision: {REV_ID}
status: {qa['status']}
provider_requests_sent: {qa['provider_requests_sent']}
mechanical_pass_rows: {qa['mechanical_pass_rows']}
P4D_IMAGES_ACCEPTED: 0
formal_ingest: false
human_review: false
ground_truth_assignment: false
"""
    write_text(FREEZE_DIR / "overview_snapshot_at_freeze.md", overview)
    extras = [REPORT_PREFLIGHT, REPORT_PLAN, REPORT_EXECUTION, REPORT_QA]
    artifact_sha: dict[str, str] = {}
    for p in sorted(REV.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p == LOCK_PATH or p in {FREEZE_PATH, FREEZE_SIDECAR, FREEZE_VERIFY}:
            continue
        artifact_sha[str(p)] = sha256_path(p)
    for p in extras:
        if p.is_file():
            artifact_sha[str(p)] = sha256_path(p)
    freeze = {
        "revision_id": REV_ID,
        "status": "TERMINAL_FREEZE_MECHANICAL_QA_ONLY",
        "captured_at": utc(),
        "provider_requests_sent": qa["provider_requests_sent"],
        "accounting_after": qa["accounting_after"],
        "P4D_IMAGES_ACCEPTED": 0,
        "formal_ingest": False,
        "human_review": False,
        "ground_truth_assignment": False,
        "c3": False,
        "val": False,
        "holdout_requests": 0,
        "artifact_sha256": artifact_sha,
    }
    write_json(FREEZE_PATH, freeze)
    freeze_sha = sha256_path(FREEZE_PATH)
    write_text(FREEZE_SIDECAR, f"{freeze_sha}  {FREEZE_PATH.name}\n")
    failures = []
    for path, expected in artifact_sha.items():
        p = Path(path)
        if not p.is_file() or sha256_path(p) != expected:
            failures.append(path)
    sidecar_ok = sidecar_hash(FREEZE_SIDECAR) == freeze_sha
    write_json(FREEZE_VERIFY, {
        "captured_at": utc(),
        "revision_id": REV_ID,
        "all_bound_artifacts_match": not failures,
        "bound_artifact_count": len(artifact_sha),
        "artifact_failures": failures,
        "freeze_sha256": freeze_sha,
        "sidecar_match": sidecar_ok,
    })
    require(not failures and sidecar_ok, "terminal freeze verification failed")
    return freeze_sha, sha256_path(FREEZE_SIDECAR)


def write_final_report(qa: dict[str, Any], freeze_sha: str, sidecar_sha: str) -> None:
    paths = [
        AUTH_PATH, PLAN_PATH, CONFIG_PATH, RUNNER, LEDGER_PATH, REQUEST_LOG, RAW_LOG,
        PREFLIGHT_AUDIT, CHECK_DIR / "execution_start_binding_audit.json",
        PRE / "provider_runtime.json", PRE / "provider_runtime_pre_request.json",
        PRE / "partition_rebuild.json", QA_DIR / "partial_qa.json",
        FREEZE_PATH, FREEZE_SIDECAR, FREEZE_VERIFY,
    ]
    hash_lines = "\n".join(f"- {p}: {sha256_path(p)}" for p in paths if p.is_file())
    stop = read_json(GLOBAL_STOP)
    q = qa["accounting_after"]
    status = (
        "COMPLETE_P4D_GR3Q10_MECHANICAL_QA_ONLY_NO_INGEST"
        if qa["mechanical_pass_rows"] == 30
        else "COMPLETE_P4D_GR3Q10_PARTIAL_MECHANICAL_QA_NO_INGEST"
    )
    write_text(REPORT_FINAL, f"""# P4D GR3Q10 final handoff

- status: {status}
- revision: {REV_ID}
- planned/logical/success: 30 / {stop['provider_requests_sent']} / {qa['mechanical_pass_rows']}
- confirmed failures: {qa['failure_rows']}
- completion unknown: {qa['completion_unknown_rows']}; resend: forbidden
- provider retry policy: outer retry false; native max retries {NATIVE_MAX_RETRIES}; observed native retry event upper bound {stop['unique_native_retry_events_upper_bound']}
- role/split mechanical pass: {qa['role_counts_mechanical_pass']} / {qa['split_counts_mechanical_pass']}
- raw/final: raw images are under {RAW_DIR}, locally normalized final images under {FINAL_DIR}; final contract 1920x1080
- exact duplicate / GR1 collision / foreign-event / provenance / ledger failures: {qa['exact_duplicate_with_prior_count']} / {qa['gr1_sha_collision_count']} / {qa['foreign_event_asset_count']} / {qa['adapter_provenance_fail_count']} / {qa['ledger_consistency_fail_count']}
- accounting: clean {q['clean_success']} + binding-blocked {q['binding_blocked_success']} + unknown {q['completion_unknown']} + safe {q['safe_executable_outstanding']} = {q['sum']}
- Q9 history: remains COMPLETE_WITH_POSTRUN_CONFIG_BINDING_MISMATCH; its artifacts were not rewritten.
- P4D_IMAGES_ACCEPTED=0; formal ingest false; human review false; ground-truth assignment false; C3 false; VAL false; Holdout requests 0; production integration false.
- terminal freeze SHA-256: {freeze_sha}
- terminal freeze sidecar SHA-256: {sidecar_sha}

## Binding and provenance hashes

{hash_lines}

This is AIGC generation and mechanical/provenance evidence only. Provider success is not a human label and is not a ground-truth source.
""")


def qa_and_freeze() -> None:
    qa = make_qa()
    freeze_sha, sidecar_sha = freeze_revision(qa)
    write_final_report(qa, freeze_sha, sidecar_sha)
    print(json.dumps({
        "status": "FINAL_REPORT_WRITTEN",
        "revision_id": REV_ID,
        "accounting": qa["accounting_after"],
        "mechanical_pass_rows": qa["mechanical_pass_rows"],
        "completion_unknown_rows": qa["completion_unknown_rows"],
        "freeze_sha256": freeze_sha,
        "freeze_sidecar_sha256": sidecar_sha,
        "final_report": str(REPORT_FINAL),
    }, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "run", "qa", "all"])
    args = parser.parse_args()
    try:
        if args.command == "init":
            init_revision()
        elif args.command == "run":
            run_execution()
        elif args.command == "qa":
            qa_and_freeze()
        else:
            init_revision()
            run_execution()
            qa_and_freeze()
        return 0
    except GateBlocked as exc:
        print(json.dumps({
            "status": "PREFLIGHT_BLOCKED" if "PREFLIGHT" in str(exc) or "binding" in str(exc).lower() else "EXECUTION_BLOCKED",
            "revision_id": REV_ID,
            "provider_requests_sent": 0 if not GLOBAL_STOP.exists() else read_json(GLOBAL_STOP).get("provider_requests_sent"),
            "reason": str(exc),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
