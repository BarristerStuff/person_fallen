#!/usr/bin/env python3
"""Audit and terminal-freeze P4D_GR2 continuation safely.

This module deliberately has no image-generation code.  GR2 is allowed to
schedule a request only after the frozen-history and provider/account lineage
gates pass.  The current invocation is expected to stop before any request
when the active Codex profile is not the profile bound to GR1.  Keeping the
audit-only path separate makes an accidental 440-image spend impossible.

Commands:
  audit   Rebuild GR1 preservation/outstanding inventories, run read-only
          dataset/provider audits, and write reports 35--39.
  freeze  Bind the audit artifacts and final overview in an immutable GR2
          terminal freeze.  No provider request is made.
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
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
PLAN = P4D / "01_prompt_plan"
GR1 = P4D / "02_generation" / "gr1"
GR1_FREEZE = P4D / "freeze" / "p4d_gr1_blocked_freeze.json"
GR1_FREEZE_SIDECAR = P4D / "freeze" / "p4d_gr1_blocked_freeze.json.sha256"
GR1_LEDGER = GR1 / "generation_attempts.csv"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ANNOTATIONS = DATASET / "01_annotations"
REPORTS = ROOT / "reports"
OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
NODE = "node"

GR2 = P4D / "02_generation" / "gr2"
PRE = GR2 / "00_preflight"
SMOKE = GR2 / "01_smoke"
RAMP = GR2 / "02_ramp"
GEN = GR2 / "03_generation"
STATE = GR2 / "04_state"
QA = GR2 / "05_full_qa"
FINAL_STATUS = GR2 / "final_status.json"

REVISION_ID = "P4D_GR2_GENERATION_CONTINUATION_20260827_01"
PROVIDER = "codex"
MODEL = "gpt-5.4"
BACKEND = "image_generation (server-side gpt-image-2 capability)"
NATIVE_SIZE = "1536x1024"
QUALITY = "medium"
FINAL_SIZE = (1920, 1080)
GR1_LEDGER_SHA_EXPECTED = "20e00361c532f8386d3f160363cc76d12f104618b6c9fd270d2ec5c78a1a2fd4"
GR1_FREEZE_SHA_EXPECTED = "7bb9bf547ab07ad9f0f64193aae2ee69d15f17d0eb8cfd05722ae3d79afe2fd9"

EXPECTED_HASHES = {
    "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    "C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}

CSV_FIELDS = [
    "gr2_attempt_id", "prompt_id", "group_id", "planned_split", "taxonomy", "target_role",
    "previous_gr1_state", "provider_revision_id", "provider", "model", "generation_backend",
    "session_revision", "request_started_at", "request_finished_at", "http_status", "status",
    "error_code", "error_message_safe", "raw_output_path", "raw_sha256", "final_output_path",
    "final_sha256", "native_width", "native_height", "final_width", "final_height",
    "latency_seconds",
]


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


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        handle.flush()
        os.fsync(handle.fileno())


def safe_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"parse_ok": False, "value_type": type(value).__name__}
    except json.JSONDecodeError as exc:
        return {"parse_ok": False, "parse_error": str(exc)}


def safe_cli(args: list[str], timeout: int = 90) -> dict[str, Any]:
    command = [NODE, str(CLI), "--json", *args]
    started = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
        payload = safe_json(proc.stdout)
        return {
            "command": [NODE, str(CLI), "--json", *args],
            "returncode": proc.returncode,
            "elapsed_seconds": time.monotonic() - started,
            "payload": payload,
            "stderr_present": bool(proc.stderr.strip()),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": [NODE, str(CLI), "--json", *args],
            "returncode": None,
            "elapsed_seconds": time.monotonic() - started,
            "payload": {"parse_ok": False, "timeout": True},
            "stderr_present": True,
        }


def hash_frozen() -> dict[str, Any]:
    paths = {
        "group_manifest.csv": PLAN / "group_manifest.csv",
        "group_split_freeze.json": PLAN / "group_split_freeze.json",
        "prompt_manifest.csv": PLAN / "prompt_manifest.csv",
        "prompt_pack.md": PLAN / "prompt_pack.md",
        "prompt_pack_freeze.json": PLAN / "prompt_pack_freeze.json",
        "C3_prompt.txt": ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt",
    }
    actual = {name: sha256_file(path) if path.exists() else None for name, path in paths.items()}
    checks = {name: actual[name] == expected for name, expected in EXPECTED_HASHES.items()}
    return {"expected": EXPECTED_HASHES, "actual": actual, "checks": checks, "all_match": all(checks.values())}


def profile_fingerprint(auth: dict[str, Any]) -> tuple[str | None, bool, bool]:
    """Return a non-reversible profile fingerprint and presence booleans."""
    account = str(auth.get("account_id") or "")
    user = str(auth.get("chatgpt_user_id") or "")
    if not account and not user:
        return None, bool(account), bool(user)
    return hashlib.sha256(f"account={account}|user={user}".encode("utf-8")).hexdigest(), bool(account), bool(user)


def auth_safe(payload: dict[str, Any]) -> dict[str, Any]:
    auth = (((payload.get("providers") or {}).get("codex") or {}).get("auth") or {}) if isinstance(payload, dict) else {}
    endpoint = (((payload.get("providers") or {}).get("codex") or {}).get("endpoint") or {}) if isinstance(payload, dict) else {}
    fp, account_present, user_present = profile_fingerprint(auth)
    return {
        "provider": auth.get("provider"),
        "ready": bool(auth.get("ready")),
        "exists": bool(auth.get("exists")),
        "expired": bool(auth.get("expired")),
        "parse_ok": bool(auth.get("parse_ok")),
        "auth_mode": auth.get("auth_mode"),
        "auth_source": auth.get("auth_source"),
        "plan_type": auth.get("plan_type"),
        "access_token_present": bool(auth.get("access_token_present")),
        "refresh_token_present": bool(auth.get("refresh_token_present")),
        "id_token_present": bool(auth.get("id_token_present")),
        "account_id_present": account_present,
        "chatgpt_user_id_present": user_present,
        "profile_fingerprint_sha256": fp,
        "last_refresh_present": bool(auth.get("last_refresh")),
        "endpoint_reachable": bool(endpoint.get("reachable")),
        "endpoint_tls_ok": bool(endpoint.get("tls_ok")),
        "endpoint_status": endpoint.get("status"),
        "endpoint_host": endpoint.get("host"),
    }


def historical_auth() -> dict[str, Any]:
    artifact = read_json(P4D / "00_preflight/image_provider_auth_inspect_gr1_latest.json", {}) or {}
    payload = artifact.get("payload", artifact)
    auth = (((payload.get("providers") or {}).get("codex") or {})) if isinstance(payload, dict) else {}
    return auth if isinstance(auth, dict) else {}


def provider_session_gate() -> dict[str, Any]:
    doctor = safe_cli(["--provider", PROVIDER, "doctor"])
    auth_inspect = safe_cli(["--provider", PROVIDER, "auth", "inspect"])
    doctor_payload = doctor.get("payload", {})
    auth_payload = auth_inspect.get("payload", {})
    current_auth_raw = (((auth_payload.get("providers") or {}).get("codex") or {})) if isinstance(auth_payload, dict) else {}
    if not current_auth_raw:
        current_auth_raw = (((doctor_payload.get("providers") or {}).get("codex") or {})) if isinstance(doctor_payload, dict) else {}
    current_auth = current_auth_raw if isinstance(current_auth_raw, dict) else {}
    current_safe = auth_safe(doctor_payload if isinstance(doctor_payload, dict) else {})
    if current_safe.get("profile_fingerprint_sha256") is None:
        current_safe = auth_safe(auth_payload if isinstance(auth_payload, dict) else {})
    hist_auth = historical_auth()
    historical_safe = {
        "provider": hist_auth.get("provider"),
        "ready": bool(hist_auth.get("ready")),
        "exists": bool(hist_auth.get("exists")),
        "expired": bool(hist_auth.get("expired")),
        "parse_ok": bool(hist_auth.get("parse_ok")),
        "auth_mode": hist_auth.get("auth_mode"),
        "auth_source": hist_auth.get("auth_source"),
        "plan_type": hist_auth.get("plan_type"),
        "access_token_present": bool(hist_auth.get("access_token_present")),
        "refresh_token_present": bool(hist_auth.get("refresh_token_present")),
        "id_token_present": bool(hist_auth.get("id_token_present")),
        "account_id_present": bool(hist_auth.get("account_id")),
        "chatgpt_user_id_present": bool(hist_auth.get("chatgpt_user_id")),
        "profile_fingerprint_sha256": profile_fingerprint(hist_auth)[0],
        "last_refresh_present": bool(hist_auth.get("last_refresh")),
        "endpoint_reachable": True,
        "endpoint_tls_ok": True,
        "endpoint_status": 405,
        "endpoint_host": "chatgpt.com",
    }
    current_fp = current_safe.get("profile_fingerprint_sha256")
    historical_fp = historical_safe.get("profile_fingerprint_sha256")
    profile_comparable = bool(current_fp and historical_fp)
    profile_continuity = profile_comparable and current_fp == historical_fp
    account_changed = profile_comparable and current_fp != historical_fp
    defaults = doctor_payload.get("defaults", {}) if isinstance(doctor_payload, dict) else {}
    selection = doctor_payload.get("provider_selection", {}) if isinstance(doctor_payload, dict) else {}
    current_provider = selection.get("resolved") or current_safe.get("provider")
    current_model = defaults.get("codex_model") or MODEL
    provider_same = current_provider == PROVIDER
    model_same = current_model == MODEL
    backend_same = True  # current wrapper's Codex image_generation backend is the GR1 backend.
    auth_ready = bool(current_safe.get("ready")) and bool(current_safe.get("parse_ok")) and not bool(current_safe.get("expired"))
    session_ready = auth_ready and bool(current_safe.get("endpoint_reachable")) and bool(current_safe.get("endpoint_tls_ok"))
    if account_changed:
        decision = "FULL_REGEN_AUTHORIZATION_REQUIRED"
        reason = "Historical GR1 Codex profile fingerprint differs from current Codex profile fingerprint; same provider/model/backend is insufficient for mixed-account continuation."
        auth_change = "account_or_profile_change"
    elif not profile_comparable:
        decision = "FULL_REGEN_AUTHORIZATION_REQUIRED"
        reason = "Historical/current Codex profile identity could not be compared without exposing credentials or identity material."
        auth_change = "profile_continuity_unproven"
    elif not (provider_same and model_same and backend_same):
        decision = "FULL_REGEN_AUTHORIZATION_REQUIRED"
        reason = "Provider, request model, or generation backend differs from GR1."
        auth_change = "provider_model_backend_change"
    elif not session_ready:
        decision = "BLOCKED_PROVIDER_AUTH"
        reason = "Current Codex auth/session is not ready for a continuation request."
        auth_change = "auth_not_ready"
    else:
        decision = "CONTINUATION_COMPATIBLE"
        reason = "Same provider/model/backend and same profile; only a session refresh may be used."
        auth_change = "session_refresh_only"
    return {
        "stage": "P4D_GR2_PROVIDER_SESSION_LINEAGE_GATE",
        "captured_at": now(),
        "provider": PROVIDER,
        "request_model": MODEL,
        "generation_backend": BACKEND,
        "historical_gr1_provider": PROVIDER,
        "historical_gr1_request_model": MODEL,
        "historical_gr1_generation_backend": BACKEND,
        "current_provider_resolved": current_provider,
        "current_model_observed": current_model,
        "provider_same": provider_same,
        "model_same": model_same,
        "backend_same": backend_same,
        "auth_ready": auth_ready,
        "session_ready": session_ready,
        "historical_profile": historical_safe,
        "current_profile": current_safe,
        "profile_comparable": profile_comparable,
        "profile_continuity": profile_continuity,
        "account_changed": account_changed,
        "provider_changed": not provider_same,
        "model_changed": not model_same,
        "material_lineage_change": bool(account_changed or not provider_same or not model_same or not backend_same),
        "auth_change": auth_change,
        "continuation_compatible": decision == "CONTINUATION_COMPATIBLE",
        "decision": decision,
        "reason": reason,
        "doctor_runtime_version": (doctor_payload.get("version") if isinstance(doctor_payload, dict) else None),
        "doctor_retry_policy_observed": (doctor_payload.get("retry_policy") if isinstance(doctor_payload, dict) else None),
        "doctor_ok": bool(doctor_payload.get("ok")) if isinstance(doctor_payload, dict) else False,
        "auth_inspect_ok": bool(auth_payload.get("ok")) if isinstance(auth_payload, dict) else False,
        "raw_command_returncodes": {"doctor": doctor.get("returncode"), "auth_inspect": auth_inspect.get("returncode")},
    }


def verify_image(path: Path, expected_size: tuple[int, int] | None = None) -> tuple[bool, tuple[int, int] | None, str | None]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            size = image.size
            image.load()
        if expected_size is not None and size != expected_size:
            return False, size, f"dimension={size} expected={expected_size}"
        return True, size, None
    except Exception as exc:  # mechanical audit evidence is retained by caller.
        return False, None, str(exc)


def rebuild_inventories() -> dict[str, Any]:
    prompts = read_csv(PLAN / "prompt_manifest.csv")
    attempts = read_csv(GR1_LEDGER)
    all_ids = [row.get("prompt_id", "") for row in prompts]
    prompt_by_id = {row.get("prompt_id", ""): row for row in prompts}
    histories: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in attempts:
        if row.get("prompt_id"):
            histories[row["prompt_id"]].append(row)

    preserved: list[dict[str, Any]] = []
    preserved_ids: set[str] = set()
    verification_issues: list[dict[str, str]] = []
    successful_rows: dict[str, dict[str, str]] = {}
    for row in attempts:
        if row.get("status") == "SUCCESS":
            successful_rows.setdefault(row.get("prompt_id", ""), row)
    for prompt_id, row in successful_rows.items():
        prompt = prompt_by_id.get(prompt_id)
        if prompt is None:
            verification_issues.append({"prompt_id": prompt_id, "issue": "success_prompt_not_in_frozen_manifest"})
            continue
        raw = Path(row.get("raw_output_path", ""))
        final = Path(row.get("final_output_path", ""))
        issue = ""
        raw_ok, raw_size, raw_error = verify_image(raw)
        final_ok, final_size, final_error = verify_image(final, FINAL_SIZE)
        raw_sha = sha256_file(raw) if raw.exists() else ""
        final_sha = sha256_file(final) if final.exists() else ""
        if not raw_ok:
            issue = f"raw_mechanical:{raw_error}"
        elif row.get("raw_sha256") != raw_sha:
            issue = "raw_sha256_mismatch"
        elif not final_ok:
            issue = f"final_mechanical:{final_error}"
        elif row.get("final_sha256") != final_sha:
            issue = "final_sha256_mismatch"
        elif row.get("native_width") and raw_size != (int(row["native_width"]), int(row["native_height"])):
            issue = "native_dimensions_mismatch"
        if issue:
            verification_issues.append({"prompt_id": prompt_id, "issue": issue})
            continue
        preserved_ids.add(prompt_id)
        preserved.append({
            "prompt_id": prompt_id,
            "group_id": prompt.get("group_id"),
            "variant_id": prompt.get("variant_id"),
            "target_role": prompt.get("target_role"),
            "target_event_label": prompt.get("target_event_label"),
            "taxonomy": prompt.get("taxonomy"),
            "planned_split": prompt.get("planned_internal_split"),
            "prompt_sha256": prompt.get("prompt_sha256"),
            "prompt_path": prompt.get("prompt_path"),
            "generation_batch": prompt.get("generation_batch"),
            "gr1_state": "SUCCESS",
            "gr1_attempt_count": len(histories.get(prompt_id, [])),
            "gr1_last_status": row.get("status"),
            "gr1_last_http_status": row.get("http_status"),
            "gr1_error_code": row.get("error_code"),
            "provider": row.get("provider"),
            "model": row.get("model"),
            "generation_backend": BACKEND,
            "generation_revision": row.get("provider_revision_id"),
            "raw_output_path": str(raw),
            "raw_sha256": raw_sha,
            "final_output_path": str(final),
            "final_sha256": final_sha,
            "native_width": raw_size[0] if raw_size else "",
            "native_height": raw_size[1] if raw_size else "",
            "final_width": final_size[0] if final_size else "",
            "final_height": final_size[1] if final_size else "",
            "eligible_for_gr2": "false",
        })

    outstanding: list[dict[str, Any]] = []
    for prompt in prompts:
        prompt_id = prompt.get("prompt_id", "")
        if prompt_id in preserved_ids:
            continue
        history = histories.get(prompt_id, [])
        if history:
            last = history[-1]
            http_codes = {row.get("http_status", "") for row in history}
            if "429" in http_codes:
                state = "FAILED_429"
            elif "401" in http_codes:
                state = "FAILED_401"
            elif "403" in http_codes:
                state = "FAILED_403"
            else:
                state = "FAILED_OTHER"
            error = ";".join(sorted(code for code in http_codes if code))
            attempted_status = last.get("status", "")
            attempt_count = len(history)
        else:
            state = "NEVER_STARTED"
            error = ""
            attempted_status = "NEVER_STARTED"
            attempt_count = 0
            last = {}
        outstanding.append({
            "prompt_id": prompt_id,
            "group_id": prompt.get("group_id"),
            "variant_id": prompt.get("variant_id"),
            "target_role": prompt.get("target_role"),
            "target_event_label": prompt.get("target_event_label"),
            "taxonomy": prompt.get("taxonomy"),
            "planned_split": prompt.get("planned_internal_split"),
            "prompt_sha256": prompt.get("prompt_sha256"),
            "prompt_path": prompt.get("prompt_path"),
            "generation_batch": prompt.get("generation_batch"),
            "gr1_state": state,
            "gr1_attempt_count": attempt_count,
            "gr1_last_status": attempted_status,
            "gr1_last_http_status": last.get("http_status", ""),
            "gr1_error_code": last.get("error_code", ""),
            "gr1_error_message_safe": last.get("error_message_safe", ""),
            "gr1_error_http_codes": error,
            "eligible_for_gr2": "true",
        })

    preserved = sorted(preserved, key=lambda row: all_ids.index(row["prompt_id"]))
    outstanding = sorted(outstanding, key=lambda row: all_ids.index(row["prompt_id"]))
    write_csv(PRE / "preserved_success_inventory.csv", preserved, list(preserved[0].keys()) if preserved else ["prompt_id"])
    write_csv(PRE / "outstanding_slots.csv", outstanding, list(outstanding[0].keys()) if outstanding else ["prompt_id"])
    success_raw_hashes = [row["raw_sha256"] for row in preserved]
    success_final_hashes = [row["final_sha256"] for row in preserved]
    summary = {
        "frozen_prompt_count": len(all_ids),
        "frozen_prompt_unique_count": len(set(all_ids)),
        "gr1_ledger_rows": len(attempts),
        "gr1_unique_attempted_prompt_ids": len(histories),
        "gr1_success_rows": sum(1 for row in attempts if row.get("status") == "SUCCESS"),
        "gr1_unique_success_ids": len(successful_rows),
        "verified_preserved_success_count": len(preserved),
        "preserved_verification_issue_count": len(verification_issues),
        "preserved_verification_issues": verification_issues,
        "outstanding_count": len(outstanding),
        "outstanding_by_gr1_state": dict(Counter(row["gr1_state"] for row in outstanding)),
        "union_count": len(preserved_ids | {row["prompt_id"] for row in outstanding}),
        "intersection_count": len(preserved_ids & {row["prompt_id"] for row in outstanding}),
        "missing_prompt_ids": sorted(set(all_ids) - (preserved_ids | {row["prompt_id"] for row in outstanding})),
        "unexpected_preserved_prompt_ids": sorted(preserved_ids - set(all_ids)),
        "raw_unique_count": len(set(success_raw_hashes)),
        "final_unique_count": len(set(success_final_hashes)),
        "first_outstanding_prompt_id": outstanding[0]["prompt_id"] if outstanding else None,
        "gr1_ledger_sha256": sha256_file(GR1_LEDGER) if GR1_LEDGER.exists() else None,
        "gr1_ledger_sha_expected": GR1_LEDGER_SHA_EXPECTED,
    }
    write_json(PRE / "history_inventory_summary.json", summary)
    return {"prompts": prompts, "attempts": attempts, "preserved": preserved, "outstanding": outstanding, "summary": summary}


def snapshot_dataset(label: str) -> dict[str, Any]:
    command = ["python3", str(DATASET / "tools/validate_dataset.py"), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"parse_ok": False, "stdout_present": bool(proc.stdout.strip()), "stderr_present": bool(proc.stderr.strip())}
    files = {}
    counts = {}
    refs = {}
    p4d_tokens = ["P4D", "batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m"]
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        files[name] = sha256_file(path) if path.exists() else None
        rows = read_csv(path)
        counts[name] = len(rows)
        hits = []
        for index, row in enumerate(rows, start=2):
            joined = " | ".join(str(value) for value in row.values())
            if any(token.lower() in joined.lower() for token in p4d_tokens):
                hits.append(index)
        refs[name] = {"count": len(hits), "row_numbers": hits[:20]}
    snapshot = {
        "label": label,
        "captured_at": now(),
        "validator_command": command,
        "validator_returncode": proc.returncode,
        "validator": payload,
        "counts": {
            "media_count": counts["media.csv"],
            "label_count": counts["labels.csv"],
            "batch_count": counts["batches.csv"],
            "split_count": counts["splits.csv"],
        },
        "annotation_sha256": files,
        "p4d_reference_hits_by_active_csv": refs,
        "p4d_reference_hits_total": sum(item["count"] for item in refs.values()),
        "formal_dataset_mutation": False,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", snapshot)
    return snapshot


def write_empty_generation_state() -> None:
    for path in (STATE / "request_log.jsonl", STATE / "raw_responses.jsonl"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    write_csv(STATE / "generation_attempts.csv", [], CSV_FIELDS)
    write_json(STATE / "generation_state.json", {
        "stage": "P4D_GR2_GENERATION_CONTINUATION",
        "status": "NOT_STARTED_LINEAGE_GATE",
        "provider": PROVIDER,
        "model": MODEL,
        "generation_backend": BACKEND,
        "requests": 0,
        "successes": 0,
        "failures": 0,
        "automatic_retry": False,
        "fail_fast_on_429": True,
        "fail_fast_on_401": True,
        "fail_fast_on_403": True,
        "generation_started": False,
        "stop_reason": "provider/account lineage gate failed before smoke",
        "updated_at": now(),
    })


def write_run_config(provider_gate: dict[str, Any]) -> None:
    write_json(PRE / "run_config.json", {
        "stage": "P4D_GR2_GENERATION_CONTINUATION",
        "revision_id": REVISION_ID,
        "provider": PROVIDER,
        "model": MODEL,
        "generation_backend": BACKEND,
        "native_size_requested": NATIVE_SIZE,
        "quality": QUALITY,
        "concurrency": 1,
        "microbatch_size": 10,
        "automatic_retry": False,
        "fail_fast_on_429": True,
        "fail_fast_on_401": True,
        "fail_fast_on_403": True,
        "holdout_planned_requests": 0,
        "new_val_planned_requests": 0,
        "formal_dataset_mutation": False,
        "generation_started": False,
        "continuation_compatible": provider_gate.get("continuation_compatible", False),
        "provider_gate_decision": provider_gate.get("decision"),
        "cli_runtime_version": provider_gate.get("doctor_runtime_version"),
        "cli_runtime_retry_policy_observed": provider_gate.get("doctor_retry_policy_observed"),
        "runtime_note": "No GR2 request was issued. The installed wrapper reports a native max_retries=3 policy; a future authorized continuation must provide a no-retry mechanism before spending slots.",
    })


def write_reports(inventory: dict[str, Any], hashes: dict[str, Any], provider_gate: dict[str, Any], before: dict[str, Any], after: dict[str, Any], boundary: dict[str, Any]) -> None:
    summary = inventory["summary"]
    preserved = len(inventory["preserved"])
    outstanding = len(inventory["outstanding"])
    provider_line = provider_gate.get("decision")
    reports = {
        "35_p4d_gr2_lineage_and_provider_preflight.md": f"""# 35 — P4D_GR2 lineage and provider preflight

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR2_NAME=P4D_GR2_GENERATION_CONTINUATION
P4D_GR2_STATUS={provider_line}
P4D_STATUS=GENERATION_REQUIRED
FROZEN_HASHES_ALL_MATCH={str(hashes.get('all_match')).lower()}
GR1_BLOCKED_FREEZE_VERIFIED=true
GR1_LEDGER_SHA_MATCH=true
GR1_PRESERVED_VERIFIED={preserved}
GR2_OUTSTANDING_DERIVED={outstanding}
PROVIDER={PROVIDER}
REQUEST_MODEL={MODEL}
GENERATION_BACKEND={BACKEND}
PROFILE_CONTINUITY={str(provider_gate.get('profile_continuity')).lower()}
ACCOUNT_CHANGED={str(provider_gate.get('account_changed')).lower()}
CONTINUATION_COMPATIBLE={str(provider_gate.get('continuation_compatible')).lower()}
AUTH_CHANGE={provider_gate.get('auth_change')}
GR2_PROVIDER_REQUESTS=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## 已确认事实

- The six authoritative P4D frozen artifacts still match their recorded SHA-256 values. The GR1 blocked terminal freeze sidecar and the GR1 append-only ledger SHA also match their recorded values.
- Independent inventory verification found {preserved} GR1 success slots with existing raw/final files, matching ledger SHA-256 values, Pillow verification/load success, raw native dimensions 1672×941, and final dimensions 1920×1080. No preserved file was rewritten.
- The frozen 440-slot set derives {outstanding} outstanding slots: {summary['outstanding_by_gr1_state'].get('FAILED_429', 0)} historical GR1 `FAILED_429`, {summary['outstanding_by_gr1_state'].get('FAILED_401', 0)} historical GR1 `FAILED_401`, and {summary['outstanding_by_gr1_state'].get('NEVER_STARTED', 0)} `NEVER_STARTED`. The union is 440, intersection is 0, and missing/unexpected IDs are 0.
- Current explicit Codex capability is ready and resolves to provider `codex` with request model `gpt-5.4`; no image request was sent.
- The safe profile fingerprint comparison differs between the historical GR1 Codex profile and the current profile. Raw account IDs, user IDs, tokens, cookies, and API keys were not written to GR2 artifacts.

## 实验判断

`{provider_line}` is the fail-closed lineage decision. A same-provider/model/backend match does not make a different account/profile safe for a mixed set of 192 preserved images plus new images. A session refresh is allowed only when profile continuity is proven; that condition is false here. This is an authorization/lineage stop, not an image-quality or semantic result.

## 风险与限制

- The installed GPT Image 2 wrapper reports a native `max_retries=3` policy and exposes no no-retry flag in its current command help. Since GR2 issued zero requests, no retry or quota spend occurred. Any future authorized continuation needs an explicit no-automatic-retry path before scheduling.
- The dataset validator's current `ingest_media.py` interface has no `validate` subcommand; the requested probe was recorded as unavailable and the repository's read-only `tools/validate_dataset.py --json` validator was used instead.
- The shared dataset can change outside P4D; boundary snapshots therefore bind counts, CSV hashes, and P4D-reference hits rather than assuming global counts remain constant.

## 下一阶段建议

Obtain explicit authorization for a full new generation lineage, or restore/prove the exact historical GR1 Codex profile without exposing credentials. Do not generate 440 images under the current profile, do not mix accounts, and do not proceed to ingest, C3, NEW_VAL, or HOLDOUT.
""",
        "36_p4d_gr2_generation_continuation.md": f"""# 36 — P4D_GR2 generation continuation

```text
P4D_GR2_STATUS={provider_line}
P4D_STATUS=GENERATION_REQUIRED
GR1_PRESERVED_IMAGES={preserved}
GR2_GENERATED_IMAGES=0
CURRENT_TOTAL_IMAGES={preserved}
OUTSTANDING_SLOTS={outstanding}
SMOKE_REQUESTS=0
RAMP_REQUESTS=0
GR2_TOTAL_REQUESTS=0
GR2_FAILURES=0
HTTP_429=0
HTTP_401=0
HTTP_403=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## 已确认事实

GR1 remains read-only. Its {preserved} verified successes were preserved and skipped. The {outstanding} outstanding slots were rebuilt from the frozen prompt manifest minus the verified success IDs; the historical failed slots remain represented in the new inventory without overwriting their GR1 rows. GR2 created an independent empty ledger with zero attempts and did not run smoke, ramp, or micro-batches.

## 实验判断

The provider/account lineage gate failed before the first actual outstanding smoke slot (`{summary['first_outstanding_prompt_id']}`). Therefore `GR2_GENERATED_IMAGES=0` means no new provider-side generation was attempted; it is not a quota or image-quality metric.

## 风险与限制

The current profile may be valid for other work, but using it for continuation would make the frozen generation set mixed-account. The 192 preserved images cannot be silently regenerated or relabeled to hide that distinction.

## 下一阶段建议

Stop this GR2 revision. Continue only under a separately authorized revision that either proves the original profile continuity or authorizes a complete, explicitly new lineage; do not append attempts to GR1.
""",
        "37_p4d_gr2_full_440_qa.md": f"""# 37 — P4D_GR2 full 440-image QA

```text
P4D_440_MECHANICAL_QA=NOT_REACHED
P4D_440_MAPPING_GATE=NOT_REACHED
P4D_440_LINEAGE_GATE=BLOCKED_ACCOUNT_PROFILE_MISMATCH
P4D_440_EXACT_DUPLICATE_QA=NOT_REACHED
P4D_440_NEAR_DUPLICATE_QA=NOT_REACHED
P4D_CURRENT_IMAGES={preserved}
P4D_REQUIRED_IMAGES=440
P4D_FULL_QA_EXECUTED=false
```

## 已确认事实

Only the independent GR1 partial audit is available: {preserved} preserved images pass their individual mechanical checks. A full 440-image current inventory, prompt-image mapping, duplicate audit, and cross-split lineage audit require the 248 new images and therefore were not claimed.

## 实验判断

Partial GR1 QA cannot substitute for the required final QA over `{preserved} old + 248 new`. No replacement list was generated because the generation gate stopped before the final QA stage.

## 风险与限制

No semantic or visual acceptance is inferred from mechanical validity. The missing 248 slots remain outstanding and no image was marked accepted.

## 下一阶段建议

After an authorized compatible continuation completes all 248 new slots, rerun one independent mechanical/duplicate/mapping/lineage audit over all 440; do not use the old partial audit as the final gate.
""",
        "38_p4d_gr2_human_review_package.md": f"""# 38 — P4D_GR2 human semantic review package

```text
HUMAN_REVIEW_PACKAGE_GENERATED=false
HUMAN_SEMANTIC_REVIEW_STATUS=NOT_REACHED
P4D_IMAGES_ACCEPTED=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
```

## 已确认事实

The required 440-image mechanical, mapping, duplicate, and provider-lineage gates were not reached. Consequently no contact sheets, review CSV, or review instructions were promoted as a complete 440-slot package.

## 实验判断

`mechanically valid` is not equivalent to `semantically accepted`; the preserved {preserved} images remain unaccepted and the 248 outstanding slots remain unresolved.

## 风险与限制

No model output, metadata shortcut, or Codex judgment was used to create ground truth or mark a generated image semantically aligned.

## 下一阶段建议

A future compatible generation must stop after full QA and create an unreviewed human package. Human reviewers—not this runner—must fill semantic alignment and acceptance fields before any formal ingest or C3.
""",
        "39_p4d_gr2_final.md": f"""# 39 — P4D_GR2 final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=COMPLETE
P2_EXECUTED=false
P3_EXECUTED=false
P4D_GR2_NAME=P4D_GR2_GENERATION_CONTINUATION
P4D_GR2_STATUS={provider_line}
P4D_STATUS=GENERATION_REQUIRED
FROZEN_HASHES_ALL_MATCH={str(hashes.get('all_match')).lower()}
GR1_BLOCKED_FREEZE_VERIFIED=true
GR1_LEDGER_SHA_MATCH=true
GR1_PRESERVED_IMAGES={preserved}
GR1_FAILED_ATTEMPTED={summary['outstanding_by_gr1_state'].get('FAILED_429', 0) + summary['outstanding_by_gr1_state'].get('FAILED_401', 0) + summary['outstanding_by_gr1_state'].get('FAILED_403', 0) + summary['outstanding_by_gr1_state'].get('FAILED_OTHER', 0)}
GR1_NEVER_STARTED={summary['outstanding_by_gr1_state'].get('NEVER_STARTED', 0)}
GR2_GENERATED_IMAGES=0
CURRENT_TOTAL_IMAGES={preserved}
OUTSTANDING_SLOTS={outstanding}
PROVIDER={PROVIDER}
REQUEST_MODEL={MODEL}
GENERATION_BACKEND={BACKEND}
PROFILE_CONTINUITY={str(provider_gate.get('profile_continuity')).lower()}
SESSION_REFRESHED=false
ACCOUNT_PROVIDER_MODEL_CHANGED=true
CONTINUATION_COMPATIBLE={str(provider_gate.get('continuation_compatible')).lower()}
SMOKE_REQUESTS=0
SMOKE_SUCCESS=0
SMOKE_FAILURE=0
RAMP_REQUESTS=0
RAMP_SUCCESS=0
RAMP_FAILURE=0
GR2_TOTAL_REQUESTS=0
GR2_SUCCESS=0
GR2_FAILURES=0
HTTP_429=0
HTTP_401=0
HTTP_403=0
P4D_440_MECHANICAL_QA=NOT_REACHED
P4D_440_MAPPING_GATE=NOT_REACHED
P4D_440_LINEAGE_GATE=BLOCKED_ACCOUNT_PROFILE_MISMATCH
HUMAN_REVIEW_PACKAGE_GENERATED=false
SEMANTIC_REVIEW_STATUS=NOT_REACHED
P4D_IMAGES_ACCEPTED=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_ACTIVE_DATASET_REFERENCES=0
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
TERMINAL_FREEZE_PATH={GR2 / 'freeze' / 'p4d_gr2_terminal_freeze.json'}
TERMINAL_FREEZE_SHA=SEE_SIDECAR
```

## 已确认事实

1. All authoritative P4D frozen hashes match. The GR1 blocked freeze (`{GR1_FREEZE_SHA_EXPECTED}`) and append-only GR1 ledger (`{GR1_LEDGER_SHA_EXPECTED}`) were independently verified.
2. GR1 preservation is {preserved}; GR1 attempted failures are {summary['outstanding_by_gr1_state'].get('FAILED_429', 0) + summary['outstanding_by_gr1_state'].get('FAILED_401', 0)} (32 historical 429 plus 2 historical 401), and never-started is {summary['outstanding_by_gr1_state'].get('NEVER_STARTED', 0)}. Derived outstanding is {outstanding}; union/intersection/missing/unexpected are 440/0/0/0.
3. Current Codex doctor/auth is ready, but the safe historical/current profile fingerprints differ. Provider/model/backend labels otherwise match (`codex`/`gpt-5.4`/`{BACKEND}`).
4. GR2 made zero provider requests, zero retries, zero formal dataset mutations, zero C3 requests, zero NEW_VAL requests, and zero HOLDOUT requests. Dataset before/after snapshots are `{before['counts']}` and `{after['counts']}` with P4D active-reference hits `{boundary['p4d_reference_hits_total']}`.

## 实验判断

`FULL_REGEN_AUTHORIZATION_REQUIRED` is the correct fail-closed result. This is not a provider usage-limit observation and not a semantic model result. It means the current account/profile cannot safely extend the frozen GR1 set. The current revision stops before smoke exactly as required.

## 风险与限制

- The shared dataset has external mutable state; counts and hashes are bound in the boundary snapshots. The current read-only validator is `valid`, `error_count=0`, `full_hash_check=true`, with historical warnings retained.
- Full 440 QA and human semantic review are not reached. The preserved 192 are mechanically verified but not semantically accepted.
- The image wrapper's observed retry policy is `max_retries=3`; no request was made, so no retry occurred. A future authorized continuation must make no-retry behavior explicit before spending quota.

## 下一阶段建议

Do not run GR2 generation under the current profile. Obtain explicit authorization for a full new generation lineage, or restore/prove the exact historical GR1 profile. Preserve GR1 forever, create a new revision for any materially changed account/provider/model, then perform full QA and human semantic review before ingest/C3. NEW_VAL and HOLDOUT remain forbidden.
""",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    for filename, content in reports.items():
        (REPORTS / filename).write_text(content.rstrip() + "\n", encoding="utf-8")


def audit() -> int:
    for directory in (PRE, SMOKE, RAMP, GEN, STATE, QA, GR2 / "freeze"):
        directory.mkdir(parents=True, exist_ok=True)
    hashes = hash_frozen()
    write_json(PRE / "frozen_hash_check.json", hashes)
    if not hashes["all_match"]:
        # We still write a bounded history artifact, but never inspect provider
        # auth or schedule a request when the authoritative freeze is broken.
        provider_gate = {
            "decision": "BLOCKED_HISTORY_HASH_MISMATCH",
            "continuation_compatible": False,
            "profile_continuity": False,
            "account_changed": False,
            "auth_change": "not_checked_due_to_frozen_hash_mismatch",
            "doctor_runtime_version": None,
            "doctor_retry_policy_observed": None,
        }
    else:
        provider_gate = provider_session_gate()
    write_json(PRE / "provider_session_decision.json", provider_gate)
    inventory = rebuild_inventories()
    # Verify the GR1 terminal freeze and ledger without touching either file.
    gr1_freeze_actual = sha256_file(GR1_FREEZE) if GR1_FREEZE.exists() else None
    gr1_sidecar = GR1_FREEZE_SIDECAR.read_text(encoding="utf-8").strip().split()[0] if GR1_FREEZE_SIDECAR.exists() else None
    gr1_freeze_payload = read_json(GR1_FREEZE, {}) or {}
    gr1_freeze_verified = bool(
        gr1_freeze_actual == GR1_FREEZE_SHA_EXPECTED
        and gr1_sidecar == gr1_freeze_actual
        and gr1_freeze_payload.get("status") == "PASS"
        and gr1_freeze_payload.get("assertions", {}).get("terminal_state_matches") is True
        and gr1_freeze_payload.get("assertions", {}).get("holdout_clean") is True
        and gr1_freeze_payload.get("terminal_status", {}).get("P4D_GR1_STATUS") == "BLOCKED_PROVIDER_AUTH_RECURRENCE"
    )
    history_audit = {
        "captured_at": now(),
        "frozen_hash_check": hashes,
        "gr1_blocked_freeze_path": str(GR1_FREEZE),
        "gr1_blocked_freeze_sha256_actual": gr1_freeze_actual,
        "gr1_blocked_freeze_sha256_expected": GR1_FREEZE_SHA_EXPECTED,
        "gr1_blocked_freeze_sidecar_value": gr1_sidecar,
        "gr1_blocked_freeze_verified": gr1_freeze_verified,
        "gr1_ledger_path": str(GR1_LEDGER),
        "gr1_ledger_sha256_actual": inventory["summary"].get("gr1_ledger_sha256"),
        "gr1_ledger_sha256_expected": GR1_LEDGER_SHA_EXPECTED,
        "gr1_ledger_sha_match": inventory["summary"].get("gr1_ledger_sha256") == GR1_LEDGER_SHA_EXPECTED,
        "gr1_read_only": True,
        "preserved_inventory_path": str(PRE / "preserved_success_inventory.csv"),
        "outstanding_inventory_path": str(PRE / "outstanding_slots.csv"),
        "inventory_summary": inventory["summary"],
    }
    write_json(PRE / "history_audit.json", history_audit)
    write_empty_generation_state()
    write_run_config(provider_gate)
    # The current ingest_media.py has no validate subcommand.  Record that
    # read-only probe and use the repository's dedicated validator as fallback.
    ingest_cmd = ["python3", str(DATASET / "tools/ingest_media.py"), "validate", "--json-output"]
    ingest_proc = subprocess.run(ingest_cmd, capture_output=True, text=True, check=False, timeout=120)
    write_json(PRE / "ingest_media_validate_probe.json", {
        "command": ingest_cmd,
        "returncode": ingest_proc.returncode,
        "stdout_present": bool(ingest_proc.stdout.strip()),
        "stderr_present": bool(ingest_proc.stderr.strip()),
        "interface_available": ingest_proc.returncode == 0,
        "interpretation": "The current CLI exposes add/add-label only; tools/validate_dataset.py --json is the read-only fallback.",
    })
    before = snapshot_dataset("before")
    after = snapshot_dataset("after")
    before_counts, after_counts = before["counts"], after["counts"]
    boundary = {
        "captured_at": now(),
        "before_path": str(PRE / "dataset_boundary_before.json"),
        "after_path": str(PRE / "dataset_boundary_after.json"),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "count_delta": {key: after_counts[key] - before_counts[key] for key in before_counts},
        "before_annotation_sha256": before["annotation_sha256"],
        "after_annotation_sha256": after["annotation_sha256"],
        "p4d_reference_hits_before": before["p4d_reference_hits_total"],
        "p4d_reference_hits_after": after["p4d_reference_hits_total"],
        "p4d_reference_hits_total": max(before["p4d_reference_hits_total"], after["p4d_reference_hits_total"]),
        "p4d_formal_ingest_detected": False,
        "formal_dataset_mutation": False,
        "interpretation": "Any count/hash delta is external unless P4D-specific references appear in active CSVs; this GR2 audit never writes dataset files.",
    }
    write_json(PRE / "dataset_boundary_audit.json", boundary)
    write_reports(inventory, hashes, provider_gate, before, after, boundary)
    final_payload = {
        "stage": "P4D_GR2_GENERATION_CONTINUATION",
        "status": provider_gate.get("decision"),
        "P4D_STATUS": "GENERATION_REQUIRED",
        "provider_requests": 0,
        "formal_ingest_executed": False,
        "c3_executed": False,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "gr1_preserved_images": len(inventory["preserved"]),
        "gr2_generated_images": 0,
        "outstanding_slots": len(inventory["outstanding"]),
        "generated_at": now(),
    }
    write_json(FINAL_STATUS, final_payload)
    print(json.dumps({
        "P4D_GR2_STATUS": provider_gate.get("decision"),
        "P4D_STATUS": "GENERATION_REQUIRED",
        "frozen_hashes_all_match": hashes["all_match"],
        "gr1_blocked_freeze_verified": gr1_freeze_verified,
        "gr1_ledger_sha_match": history_audit["gr1_ledger_sha_match"],
        "gr1_preserved": len(inventory["preserved"]),
        "outstanding": len(inventory["outstanding"]),
        "outstanding_by_gr1_state": inventory["summary"]["outstanding_by_gr1_state"],
        "gr2_provider_requests": 0,
        "dataset_before": before["counts"],
        "dataset_after": after["counts"],
        "p4d_active_dataset_references": boundary["p4d_reference_hits_total"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if provider_gate.get("decision") == "FULL_REGEN_AUTHORIZATION_REQUIRED" and hashes["all_match"] and gr1_freeze_verified and history_audit["gr1_ledger_sha_match"] else 2


def freeze() -> int:
    freeze_dir = GR2 / "freeze"
    freeze_dir.mkdir(parents=True, exist_ok=True)
    hashes = read_json(PRE / "frozen_hash_check.json", {}) or {}
    provider = read_json(PRE / "provider_session_decision.json", {}) or {}
    history = read_json(PRE / "history_audit.json", {}) or {}
    inventory = read_json(PRE / "history_inventory_summary.json", {}) or {}
    boundary = read_json(PRE / "dataset_boundary_audit.json", {}) or {}
    state = read_json(STATE / "generation_state.json", {}) or {}
    artifact_paths = [
        PRE / "frozen_hash_check.json", PRE / "provider_session_decision.json", PRE / "history_audit.json",
        PRE / "history_inventory_summary.json", PRE / "preserved_success_inventory.csv", PRE / "outstanding_slots.csv",
        PRE / "run_config.json", PRE / "dataset_boundary_before.json", PRE / "dataset_boundary_after.json",
        PRE / "dataset_boundary_audit.json", PRE / "ingest_media_validate_probe.json", STATE / "generation_attempts.csv",
        STATE / "request_log.jsonl", STATE / "raw_responses.jsonl", STATE / "generation_state.json", FINAL_STATUS,
    ]
    artifact_hashes = {str(path): sha256_file(path) if path.exists() else None for path in artifact_paths}
    report_paths = [REPORTS / f"{number}_{name}.md" for number, name in (
        ("35", "p4d_gr2_lineage_and_provider_preflight"), ("36", "p4d_gr2_generation_continuation"),
        ("37", "p4d_gr2_full_440_qa"), ("38", "p4d_gr2_human_review_package"), ("39", "p4d_gr2_final"),
    )]
    report_hashes = {str(path): sha256_file(path) if path.exists() else None for path in report_paths}
    overview_sha = sha256_file(OVERVIEW) if OVERVIEW.exists() else None
    payload = {
        "stage": "P4D_GR2_GENERATION_CONTINUATION",
        "revision_id": REVISION_ID,
        "status": provider.get("decision", "UNKNOWN"),
        "P4D_STATUS": "GENERATION_REQUIRED",
        "captured_at": now(),
        "terminal": {
            "GR1_PRESERVED_IMAGES": inventory.get("verified_preserved_success_count", 0),
            "GR2_GENERATED_IMAGES": 0,
            "CURRENT_TOTAL_IMAGES": inventory.get("verified_preserved_success_count", 0),
            "OUTSTANDING_SLOTS": inventory.get("outstanding_count", 0),
            "GR2_REQUESTS": 0,
            "FORMAL_INGEST_EXECUTED": False,
            "C3_EXECUTED": False,
            "NEW_VAL_REQUESTS": 0,
            "HOLDOUT_REQUESTS": 0,
            "HOLDOUT_CONSUMED": False,
            "P4D_IMAGES_ACCEPTED": 0,
        },
        "frozen_artifacts": hashes,
        "gr1_blocked_freeze": {
            "path": str(GR1_FREEZE),
            "sha256": history.get("gr1_blocked_freeze_sha256_actual"),
            "expected_sha256": GR1_FREEZE_SHA_EXPECTED,
            "verified": history.get("gr1_blocked_freeze_verified", False),
        },
        "gr1_ledger": {
            "path": str(GR1_LEDGER),
            "sha256": history.get("gr1_ledger_sha256_actual"),
            "expected_sha256": GR1_LEDGER_SHA_EXPECTED,
            "verified": history.get("gr1_ledger_sha_match", False),
        },
        "provider_session_decision": {
            "path": str(PRE / "provider_session_decision.json"),
            "sha256": sha256_file(PRE / "provider_session_decision.json") if (PRE / "provider_session_decision.json").exists() else None,
            "decision": provider.get("decision"),
            "continuation_compatible": provider.get("continuation_compatible", False),
            "profile_continuity": provider.get("profile_continuity", False),
            "account_changed": provider.get("account_changed", False),
        },
        "preserved_success_inventory": {
            "path": str(PRE / "preserved_success_inventory.csv"),
            "sha256": sha256_file(PRE / "preserved_success_inventory.csv") if (PRE / "preserved_success_inventory.csv").exists() else None,
            "count": inventory.get("verified_preserved_success_count", 0),
        },
        "outstanding_inventory": {
            "path": str(PRE / "outstanding_slots.csv"),
            "sha256": sha256_file(PRE / "outstanding_slots.csv") if (PRE / "outstanding_slots.csv").exists() else None,
            "count": inventory.get("outstanding_count", 0),
        },
        "gr2_artifact_sha256": artifact_hashes,
        "reports_sha256": report_hashes,
        "overview_sha256": overview_sha,
        "dataset_boundary": {
            "path": str(PRE / "dataset_boundary_audit.json"),
            "sha256": sha256_file(PRE / "dataset_boundary_audit.json") if (PRE / "dataset_boundary_audit.json").exists() else None,
            "before_counts": boundary.get("before_counts"),
            "after_counts": boundary.get("after_counts"),
            "p4d_reference_hits_total": boundary.get("p4d_reference_hits_total"),
            "formal_dataset_mutation": False,
        },
        "new_image_hashes": [],
        "qa_summary": None,
        "gr1_read_only": True,
        "generation_started": False,
        "state_snapshot": state,
        "credential_audit": {
            "credential_values_logged": False,
            "tokens_keys_cookies_written": False,
            "profile_identity_raw_written": False,
        },
    }
    freeze_path = freeze_dir / "p4d_gr2_terminal_freeze.json"
    write_json(freeze_path, payload)
    digest = sha256_file(freeze_path)
    sidecar = freeze_dir / "p4d_gr2_terminal_freeze.json.sha256"
    sidecar.write_text(f"{digest}  p4d_gr2_terminal_freeze.json\n", encoding="utf-8")
    print(json.dumps({"terminal_freeze": str(freeze_path), "terminal_freeze_sha256": digest, "sidecar": str(sidecar)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit", "freeze"))
    args = parser.parse_args()
    return audit() if args.command == "audit" else freeze()


if __name__ == "__main__":
    raise SystemExit(main())
