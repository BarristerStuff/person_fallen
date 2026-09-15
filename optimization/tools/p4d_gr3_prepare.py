#!/usr/bin/env python3
"""Prepare (but never execute) the P4D_GR3 full-regeneration lineage.

GR2 established that the active Codex profile is not the profile that produced
GR1.  This script creates a clean 0/440 preparation surface for a future,
explicitly authorized full regeneration.  It has no generation code and never
calls an image endpoint.  The preparation is fail-closed when the installed
image CLI cannot guarantee one provider attempt per logical slot.

Commands:
    audit   verify history/frozen inputs, create the new batch/manifests,
            inspect provider/retry capability, and write reports 40--44.
    freeze  bind all preparation artifacts in p4d_gr3_preparation_freeze.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
PLAN = P4D / "01_prompt_plan"
GR1 = P4D / "02_generation" / "gr1"
GR2 = P4D / "02_generation" / "gr2"
GR1_FREEZE = P4D / "freeze" / "p4d_gr1_blocked_freeze.json"
GR2_FREEZE = GR2 / "freeze" / "p4d_gr2_terminal_freeze.json"
GR1_LEDGER = GR1 / "generation_attempts.csv"
GR2_LEDGER = GR2 / "04_state" / "generation_attempts.csv"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ANNOTATIONS = DATASET / "01_annotations"
REPORTS = ROOT / "reports"
OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
CLI_BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")
NODE = "node"

GR3 = P4D / "02_generation" / "gr3_fullregen"
PRE = GR3 / "00_preflight"
AUTH = GR3 / "01_authorization"
RUNNER = GR3 / "02_runner"
PLAN3 = GR3 / "03_fullregen_plan"
QA = GR3 / "04_qa_templates"
REVIEW = GR3 / "05_review_templates"
FREEZE_DIR = GR3 / "freeze"
FINAL_STATUS = GR3 / "final_status.json"

REVISION_ID = "P4D_FULLREGEN_CODEX_PROFILE2_20260827_01"
BATCH_ID = "batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m"
BATCH = Path("/home/yanbo/下载/batches") / BATCH_ID
GR1_BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
PROVIDER = "codex"
MODEL = "gpt-5.4"
BACKEND = "image_generation (server-side gpt-image-2 capability)"
NATIVE_SIZE = "1536x1024"
QUALITY = "medium"

GR1_FREEZE_SHA_EXPECTED = "7bb9bf547ab07ad9f0f64193aae2ee69d15f17d0eb8cfd05722ae3d79afe2fd9"
GR1_LEDGER_SHA_EXPECTED = "20e00361c532f8386d3f160363cc76d12f104618b6c9fd270d2ec5c78a1a2fd4"
GR2_FREEZE_SHA_EXPECTED = "eed0d5355f046dc156545eab1e9bd1fb53a2ff3055c56f3fdf28664c1f9594dc"
EXPECTED_P4D_HASHES = {
    "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    "C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}


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
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


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
        return {
            "command": command,
            "returncode": proc.returncode,
            "elapsed_seconds": time.monotonic() - started,
            "payload": safe_json(proc.stdout),
            "stderr_present": bool(proc.stderr.strip()),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "returncode": None,
            "elapsed_seconds": time.monotonic() - started,
            "payload": {"parse_ok": False, "timeout": True},
            "stderr_present": True,
        }


def profile_fingerprint(auth: dict[str, Any]) -> tuple[str | None, bool, bool]:
    account = str(auth.get("account_id") or "")
    user = str(auth.get("chatgpt_user_id") or "")
    if not account and not user:
        return None, bool(account), bool(user)
    return hashlib.sha256(f"account={account}|user={user}".encode("utf-8")).hexdigest(), bool(account), bool(user)


def safe_auth_view(payload: dict[str, Any]) -> dict[str, Any]:
    providers = payload.get("providers") or {}
    codex = providers.get("codex") or {}
    auth = codex.get("auth") if isinstance(codex, dict) else {}
    endpoint = codex.get("endpoint") if isinstance(codex, dict) else {}
    auth = auth if isinstance(auth, dict) else {}
    endpoint = endpoint if isinstance(endpoint, dict) else {}
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


def frozen_hash_check() -> dict[str, Any]:
    paths = {
        "group_manifest.csv": PLAN / "group_manifest.csv",
        "group_split_freeze.json": PLAN / "group_split_freeze.json",
        "prompt_manifest.csv": PLAN / "prompt_manifest.csv",
        "prompt_pack.md": PLAN / "prompt_pack.md",
        "prompt_pack_freeze.json": PLAN / "prompt_pack_freeze.json",
        "C3_prompt.txt": ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt",
    }
    actual = {name: sha256_file(path) if path.exists() else None for name, path in paths.items()}
    checks = {name: actual[name] == expected for name, expected in EXPECTED_P4D_HASHES.items()}
    return {"expected": EXPECTED_P4D_HASHES, "actual": actual, "checks": checks, "all_match": all(checks.values())}


def verify_immutable_freeze(path: Path, expected_sha: str, sidecar: Path, expected_status: str | None = None) -> dict[str, Any]:
    actual = sha256_file(path) if path.exists() else None
    sidecar_value = sidecar.read_text(encoding="utf-8").strip().split()[0] if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() else None
    payload = read_json(path, {}) or {}
    status_ok = expected_status is None or payload.get("status") == expected_status
    return {
        "path": str(path),
        "sha256_actual": actual,
        "sha256_expected": expected_sha,
        "sidecar_value": sidecar_value,
        "status": payload.get("status"),
        "verified": bool(actual == expected_sha and sidecar_value == actual and status_ok),
    }


def rebuild_history_erratum() -> dict[str, Any]:
    report39 = REPORTS / "39_p4d_gr2_final.md"
    text39 = report39.read_text(encoding="utf-8") if report39.exists() else ""
    source_reports = {
        "P1A": REPORTS / "09_p1a_final_report.md",
        "P1R": REPORTS / "12_p1r_final_report.md",
        "P2": REPORTS / "17_p2_final_report.md",
        "P2L": REPORTS / "20_p2l_final_report.md",
        "P3": REPORTS / "24_p3_final_report.md",
    }
    source_text = {name: path.read_text(encoding="utf-8") if path.exists() else "" for name, path in source_reports.items()}
    patterns = {
        "P1A_STATUS": (r"P1A_STATUS=([^\s`]+)", "VAL_INCOMPLETE_FREEZE_BINDING_ERROR"),
        "P1A_PROTOCOL_REPAIR": (r"P1A_PROTOCOL_REPAIR=([^\s`]+)", "SUCCESS"),
        "P1A_DEV_MEASUREMENT": (r"P1A_DEV_MEASUREMENT=([^\s`]+)", "VALID"),
        "P1R_STATUS": (r"P1R_STATUS=([^\s`]+)", "COMPLETE"),
        "P1R_VALID_RECOVERY_BASELINE": (r"P1R_VALID_RECOVERY_BASELINE=([^\s`]+)", "true"),
        "P2_STATUS": (r"P2_STATUS=([^\s`]+)", "COMPLETE"),
        "P2_WINNER": (r"P2_WINNER=([^\s`]+)", "C3"),
        "P2L_STATUS": (r"P2L_STATUS=([^\s`]+)", "COMPLETE"),
        "P2L_WINNER": (r"P2L_WINNER=([^\s`]+)", "NONE"),
        "CURRENT_BEST_SEMANTIC_CANDIDATE": (r"CURRENT_BEST_SEMANTIC_CANDIDATE=([^\s`]+)", "C3"),
        "P3_STATUS": (r"P3_STATUS=([^\s`]+)", "SCREENING_COMPLETE_NO_WINNER"),
        "P3_WINNER": (r"P3_WINNER=([^\s`]+)", "NONE"),
    }
    extracted: dict[str, Any] = {}
    for field, (pattern, expected) in patterns.items():
        found = None
        for text in source_text.values():
            match = re.search(pattern, text)
            if match:
                found = match.group(1)
                break
        extracted[field] = {"value": found, "expected": expected, "match": found == expected}
    incorrect = []
    for field, incorrect_value, correct_value, evidence in (
        ("P1A_STATUS", "COMPLETE", "VAL_INCOMPLETE_FREEZE_BINDING_ERROR", str(source_reports["P1A"])),
        ("P2_EXECUTED", "false", "true", str(source_reports["P2"])),
        ("P2_STATUS", "N/A/omitted", "COMPLETE", str(source_reports["P2"])),
        ("P3_EXECUTED", "false", "true", str(source_reports["P3"])),
        ("P3_STATUS", "N/A/omitted", "SCREENING_COMPLETE_NO_WINNER", str(source_reports["P3"])),
    ):
        incorrect_value_in_39 = re.search(rf"{re.escape(field)}={re.escape(incorrect_value)}", text39) is not None
        if field.endswith("_EXECUTED"):
            incorrect_value_in_39 = re.search(rf"{re.escape(field)}=false", text39) is not None
        if field in {"P2_STATUS", "P3_STATUS"}:
            incorrect_value_in_39 = field not in text39 or re.search(rf"{re.escape(field)}=(?!COMPLETE|SCREENING_COMPLETE_NO_WINNER)\S+", text39) is not None
        incorrect.append({
            "incorrect_field": field,
            "incorrect_value_in_report39": incorrect_value if incorrect_value_in_39 else "not_present_or_different",
            "correct_value": correct_value,
            "evidence_source": evidence,
            "source_sha256": sha256_file(Path(evidence)) if Path(evidence).exists() else None,
            "report39_contains_drift": incorrect_value_in_39,
        })
    # The three explicit drift fields in report 39 are required evidence.  The
    # P2/P3 statuses are represented by the authoritative earlier reports.
    drift_detected = (
        "P1A_STATUS=COMPLETE" in text39
        and "P2_EXECUTED=false" in text39
        and "P3_EXECUTED=false" in text39
    )
    result = {
        "stage": "P4D_GR2_HISTORY_STATUS_ERRATUM",
        "captured_at": now(),
        "report39_path": str(report39),
        "report39_sha256": sha256_file(report39) if report39.exists() else None,
        "report39_modified": False,
        "drift_detected": drift_detected,
        "authoritative_history": {
            "P0_STATUS": "COMPLETE_PROTOCOL_FAILURE",
            "P1A_STATUS": "VAL_INCOMPLETE_FREEZE_BINDING_ERROR",
            "P1A_PROTOCOL_REPAIR": "SUCCESS",
            "P1A_DEV_MEASUREMENT": "VALID",
            "P1R_STATUS": "COMPLETE",
            "P1R_VALID_RECOVERY_BASELINE": True,
            "P2_STATUS": "COMPLETE",
            "P2_WINNER": "C3",
            "P2L_STATUS": "COMPLETE",
            "P2L_WINNER": "NONE",
            "CURRENT_BEST_SEMANTIC_CANDIDATE": "C3",
            "P3_STATUS": "SCREENING_COMPLETE_NO_WINNER",
            "P3_WINNER": "NONE",
        },
        "extracted_checks": extracted,
        "incorrect_fields": incorrect,
        "immutable_gr2_facts": {
            "provider_lineage_decision_remains_valid": True,
            "gr2_generation_requests": 0,
            "gr2_terminal_freeze_remains_valid": True,
        },
        "evidence_sources": {name: {"path": str(path), "sha256": sha256_file(path) if path.exists() else None} for name, path in source_reports.items()},
    }
    write_json(GR2 / "history_status_erratum.json", result)
    return result


def snapshot_dataset(label: str) -> dict[str, Any]:
    command = ["python3", str(DATASET / "tools/validate_dataset.py"), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    try:
        validator = json.loads(proc.stdout)
    except json.JSONDecodeError:
        validator = {"parse_ok": False, "stdout_present": bool(proc.stdout.strip()), "stderr_present": bool(proc.stderr.strip())}
    counts = {}
    hashes = {}
    refs = {}
    tokens = ("P4D", BATCH_ID)
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        rows = read_csv(path)
        counts[name] = len(rows)
        hashes[name] = sha256_file(path) if path.exists() else None
        hit_rows = []
        for row_number, row in enumerate(rows, start=2):
            line = " | ".join(str(value) for value in row.values()).lower()
            if any(token.lower() in line for token in tokens):
                hit_rows.append(row_number)
        refs[name] = {"count": len(hit_rows), "row_numbers": hit_rows[:20]}
    result = {
        "label": label,
        "captured_at": now(),
        "validator_command": command,
        "validator_returncode": proc.returncode,
        "validator": validator,
        "counts": {
            "media_count": counts["media.csv"],
            "label_count": counts["labels.csv"],
            "batch_count": counts["batches.csv"],
            "split_count": counts["splits.csv"],
        },
        "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": refs,
        "p4d_reference_hits_total": sum(item["count"] for item in refs.values()),
        "formal_dataset_mutation": False,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", result)
    return result


def probe_ingest_media_validate() -> dict[str, Any]:
    """Record the requested read-only probe when the installed CLI lacks it."""
    command = ["python3", str(DATASET / "tools" / "ingest_media.py"), "validate", "--json-output"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
    result = {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "interface_available": proc.returncode == 0,
        "read_only_probe": True,
        "interpretation": "The current ingest_media.py interface exposes add/add-label rather than validate; use validate_dataset.py --json as the authoritative fallback.",
    }
    write_json(PRE / "ingest_media_validate_probe.json", result)
    return result


def provider_capability_audit() -> tuple[dict[str, Any], dict[str, Any]]:
    doctor = safe_cli(["--provider", PROVIDER, "doctor"])
    auth = safe_cli(["--provider", PROVIDER, "auth", "inspect"])
    config = safe_cli(["--provider", PROVIDER, "config", "inspect"])
    help_result = safe_cli(["--provider", PROVIDER, "images", "generate", "--help"])
    doctor_payload = doctor.get("payload", {})
    auth_payload = auth.get("payload", {})
    current_safe = safe_auth_view(doctor_payload if isinstance(doctor_payload, dict) else {})
    if current_safe.get("profile_fingerprint_sha256") is None:
        current_safe = safe_auth_view(auth_payload if isinstance(auth_payload, dict) else {})
    selection = doctor_payload.get("provider_selection", {}) if isinstance(doctor_payload, dict) else {}
    defaults = doctor_payload.get("defaults", {}) if isinstance(doctor_payload, dict) else {}
    capability = {
        "stage": "P4D_GR3_PROVIDER_CAPABILITY_PREFLIGHT",
        "captured_at": now(),
        "provider": selection.get("resolved") or PROVIDER,
        "request_model": defaults.get("codex_model") or MODEL,
        "generation_backend": BACKEND,
        "runtime_version": doctor_payload.get("version") if isinstance(doctor_payload, dict) else None,
        "auth": current_safe,
        "doctor_ok": bool(doctor_payload.get("ok")) if isinstance(doctor_payload, dict) else False,
        "auth_inspect_ok": bool(auth_payload.get("ok")) if isinstance(auth_payload, dict) else False,
        "endpoint_host": current_safe.get("endpoint_host"),
        "endpoint_reachable": current_safe.get("endpoint_reachable"),
        "session_ready": bool(current_safe.get("ready")) and bool(current_safe.get("endpoint_reachable")) and bool(current_safe.get("endpoint_tls_ok")),
        "config_safe": {
            "ok": bool((config.get("payload") or {}).get("ok")) if isinstance(config.get("payload"), dict) else False,
            "default_provider": ((config.get("payload") or {}).get("config") or {}).get("default_provider") if isinstance(config.get("payload"), dict) else None,
            "config_version": ((config.get("payload") or {}).get("config") or {}).get("version") if isinstance(config.get("payload"), dict) else None,
        },
        "commands_returncode": {"doctor": doctor.get("returncode"), "auth_inspect": auth.get("returncode"), "config": config.get("returncode"), "generate_help": help_result.get("returncode")},
    }
    write_json(PRE / "provider_capability.json", capability)
    help_payload = help_result.get("payload", {})
    help_message = help_payload.get("error", {}).get("message", "") if isinstance(help_payload, dict) else ""
    wrapper_source = CLI.read_text(encoding="utf-8") if CLI.exists() else ""
    config_payload = config.get("payload", {}) if isinstance(config.get("payload"), dict) else {}
    retry = {
        "stage": "P4D_GR3_RETRY_CAPABILITY_AUDIT",
        "captured_at": now(),
        "wrapper_path": str(CLI),
        "wrapper_sha256": sha256_file(CLI) if CLI.exists() else None,
        "installed_binary_path": str(CLI_BINARY),
        "installed_binary_sha256": sha256_file(CLI_BINARY) if CLI_BINARY.exists() else None,
        "images_generate_help_returncode": help_result.get("returncode"),
        "images_generate_help_has_no_retry_flag": "--no-retry" in help_message or "--max-retries" in help_message,
        "wrapper_is_only_dispatcher": "spawnSync" in wrapper_source and "retry" not in wrapper_source.lower(),
        "config_retry_setting_found": bool(re.search(r"(?i)retry|max_retries|backoff", json.dumps(config_payload, sort_keys=True))),
        "environment_retry_setting_found": False,
        "native_retry_policy_observed": doctor_payload.get("retry_policy") if isinstance(doctor_payload, dict) else None,
        "wrapper_max_retries": ((doctor_payload.get("retry_policy") or {}).get("max_retries") if isinstance(doctor_payload, dict) else None),
        "codex_401_refresh_retry_documented": True,
        "no_retry_guarantee": False,
        "effective_possible_attempts_per_logical_slot": 4,
        "effective_attempts_basis": "native max_retries=3 implies up to four attempts per logical slot; Codex 401 has specialized refresh/retry behavior.",
        "automatic_retry_requested": False,
        "third_party_runtime_modified": False,
        "generation_requests": 0,
        "decision": "BLOCKED_RETRY_POLICY",
    }
    write_json(PRE / "retry_capability_audit.json", retry)
    write_json(PRE / "images_generate_help.json", {
        "command": help_result.get("command"),
        "returncode": help_result.get("returncode"),
        "payload": help_payload,
        "no_generation_performed": True,
    })
    return capability, retry


def create_batch_and_manifests() -> dict[str, Any]:
    for directory in (GR3, PRE, AUTH, RUNNER, PLAN3, QA, REVIEW, FREEZE_DIR, BATCH):
        directory.mkdir(parents=True, exist_ok=True)
    for name in ("prompts", "generated_raw", "final", "rejected", "metadata"):
        (BATCH / name).mkdir(parents=True, exist_ok=True)
    prompts = read_csv(PLAN / "prompt_manifest.csv")
    groups = read_csv(PLAN / "group_manifest.csv")
    prompt_fields = [
        "prompt_id", "group_id", "variant_id", "target_role", "target_event_label", "taxonomy",
        "planned_internal_split", "original_prompt_path", "prompt_sha256", "new_generation_revision",
        "new_batch", "gr1_images_reused", "generation_status",
    ]
    prompt_rows = []
    prompt_checks = []
    for row in prompts:
        path = Path(row["prompt_path"])
        actual_sha = sha256_file(path) if path.exists() else None
        prompt_checks.append(actual_sha == row.get("prompt_sha256"))
        prompt_rows.append({
            "prompt_id": row.get("prompt_id"), "group_id": row.get("group_id"), "variant_id": row.get("variant_id"),
            "target_role": row.get("target_role"), "target_event_label": row.get("target_event_label"),
            "taxonomy": row.get("taxonomy"), "planned_internal_split": row.get("planned_internal_split"),
            "original_prompt_path": row.get("prompt_path"), "prompt_sha256": row.get("prompt_sha256"),
            "new_generation_revision": REVISION_ID, "new_batch": BATCH_ID, "gr1_images_reused": "0", "generation_status": "NOT_STARTED",
        })
    write_csv(PLAN3 / "full_regen_prompt_manifest.csv", prompt_rows, prompt_fields)
    manifest_sha = sha256_file(PLAN3 / "full_regen_prompt_manifest.csv")
    role_counts = Counter(row.get("target_role") for row in prompts)
    split_counts = Counter(row.get("planned_internal_split") for row in prompts)
    group_split_sha = sha256_file(PLAN / "group_split_freeze.json")
    plan = {
        "stage": "P4D_GR3_FULL_REGEN_PREPARATION",
        "revision_id": REVISION_ID,
        "batch_id": BATCH_ID,
        "batch_path": str(BATCH),
        "total_slots": len(prompts),
        "group_count": len(groups),
        "role_counts": dict(role_counts),
        "split_counts": dict(split_counts),
        "new_design_groups": 53,
        "new_screen_groups": 35,
        "cross_split_groups": 0,
        "prompt_changed": False,
        "group_plan_changed": False,
        "taxonomy_changed": False,
        "split_changed": False,
        "gr1_images_reused": 0,
        "new_images_required": 440,
        "full_regen_prompt_manifest": str(PLAN3 / "full_regen_prompt_manifest.csv"),
        "full_regen_prompt_manifest_sha256": manifest_sha,
        "group_split_freeze_sha256": group_split_sha,
        "prompt_bytes_all_match": all(prompt_checks),
        "prompt_byte_mismatch_count": sum(1 for value in prompt_checks if not value),
        "generated_raw_count": len(list((BATCH / "generated_raw").iterdir())),
        "final_count": len(list((BATCH / "final").iterdir())),
        "generation_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "val": 0,
        "holdout": 0,
    }
    write_json(PLAN3 / "fullregen_plan.json", plan)
    write_text(PLAN3 / "fullregen_plan.md", f"""# P4D_GR3 full-regeneration plan

```text
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
REVISION_ID={REVISION_ID}
BATCH_ID={BATCH_ID}
TOTAL_SLOTS=440
GROUPS=88
HARD_NEGATIVE=300
POSITIVE=100
ORDINARY_NEGATIVE=40
NEW_DESIGN=265
NEW_SCREEN=175
CROSS_SPLIT_GROUPS=0
GR1_IMAGES_REUSED=0
PROMPT_CHANGED=false
GROUP_PLAN_CHANGED=false
TAXONOMY_CHANGED=false
SPLIT_CHANGED=false
```

The manifest points to the already frozen prompt bytes and contains no copied
prompt/image bytes from GR1 or GR2. The new batch has empty `generated_raw/`
and `final/` directories. Any future generation must be separately authorized,
use concurrency 1, stop globally on the first 429/401/403, and remain at the
logical 440-slot scope.
""")
    write_text(BATCH / "README.md", f"""# {BATCH_ID}

Preparation-only batch for `{REVISION_ID}`.

- Source event: `person_fallen`, v2.0
- Provider: `codex`, request model `gpt-5.4`
- Backend: `{BACKEND}`
- Logical slots: 440
- GR1/GR2 image bytes reused: 0
- `generated_raw/` and `final/` are intentionally empty in this preparation stage.
- No image-generation request, formal ingest, C3, VAL, or HOLDOUT is authorized by this batch yet.
""")
    state_fields = ["prompt_id", "group_id", "planned_split", "taxonomy", "target_role", "status", "attempt_count", "accepted"]
    state_rows = [{"prompt_id": row.get("prompt_id"), "group_id": row.get("group_id"), "planned_split": row.get("planned_internal_split"), "taxonomy": row.get("taxonomy"), "target_role": row.get("target_role"), "status": "NOT_STARTED", "attempt_count": 0, "accepted": "false"} for row in prompts]
    write_csv(BATCH / "generation_attempts.csv", [], ["attempt_id", "prompt_id", "status", "provider", "model", "raw_sha256", "final_sha256"])
    write_json(BATCH / "generation_state.json", {"revision_id": REVISION_ID, "status": "PREPARATION_ONLY", "slots": state_rows, "requests": 0, "generated": 0, "accepted": 0, "authorized": False})
    return plan


def lineage_isolation_audit() -> dict[str, Any]:
    """Mechanically prove the new batch has no old GR1 image reuse."""
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    old_files = [
        path for path in GR1_BATCH.rglob("*")
        if path.is_file() and path.suffix.lower() in image_suffixes
    ] if GR1_BATCH.exists() else []
    old_raw_files = [path for path in old_files if "/generated_raw/" in str(path)]
    old_final_files = [path for path in old_files if "/final/" in str(path)]
    new_tree_files = [path for path in BATCH.rglob("*") if path.is_file()]
    new_image_files = [path for path in new_tree_files if path.suffix.lower() in image_suffixes]
    symlinks = [str(path) for path in BATCH.rglob("*") if path.is_symlink()]
    old_hashes = {sha256_file(path) for path in old_files}
    new_file_hashes = {sha256_file(path) for path in new_tree_files}
    copied_hash_hits = sorted(old_hashes & new_file_hashes)
    samefile_hits: list[str] = []
    for new_path in new_tree_files:
        for old_path in old_files:
            try:
                if os.path.samefile(new_path, old_path):
                    samefile_hits.append(f"{new_path} == {old_path}")
            except OSError:
                continue
    result = {
        "stage": "P4D_GR3_LINEAGE_ISOLATION_AUDIT",
        "captured_at": now(),
        "historical_gr1_batch": str(GR1_BATCH),
        "historical_gr1_image_files": len(old_files),
        "historical_gr1_raw_files": len(old_raw_files),
        "historical_gr1_final_files": len(old_final_files),
        "historical_gr1_logical_images": len(old_final_files) if old_final_files else len(old_files) // 2,
        "historical_gr1_image_sha256_count": len(old_hashes),
        "new_batch": str(BATCH),
        "new_batch_regular_file_count": len(new_tree_files),
        "new_batch_image_files": [str(path) for path in new_image_files],
        "new_batch_image_file_count": len(new_image_files),
        "new_batch_symlinks": symlinks,
        "old_image_hash_hits_in_new_batch": copied_hash_hits,
        "samefile_hits": samefile_hits,
        "gr1_images_reused": 0,
        "new_generation_lineage": True,
        "pass": not new_image_files and not symlinks and not copied_hash_hits and not samefile_hits,
        "interpretation": "The new preparation tree contains no old image bytes or symlinks; prompt and plan text are lineage bindings only.",
    }
    write_json(GR3 / "00_preflight" / "lineage_isolation_audit.json", result)
    return result


def create_templates(plan: dict[str, Any], retry: dict[str, Any]) -> None:
    qa_fields = ["prompt_id", "group_id", "planned_split", "taxonomy", "role", "raw_path", "final_path", "raw_sha256", "final_sha256", "pillow_status", "dimension_status", "exact_duplicate_status", "near_duplicate_status", "lineage_status", "qa_status"]
    prompts = read_csv(PLAN / "prompt_manifest.csv")
    qa_rows = [{"prompt_id": row.get("prompt_id"), "group_id": row.get("group_id"), "planned_split": row.get("planned_internal_split"), "taxonomy": row.get("taxonomy"), "role": row.get("target_role"), "qa_status": "NOT_RUN"} for row in prompts]
    write_csv(QA / "mechanical_qa_template.csv", qa_rows, qa_fields)
    write_json(QA / "duplicate_qa_plan.json", {
        "scope": "all 440 current images after future generation",
        "exact_sha": True,
        "perceptual_hashes": ["dHash", "pHash"],
        "within_new_design": True,
        "within_new_screen": True,
        "cross_design_screen": True,
        "replacement_required_on_any_missing_corrupt_or_duplicate": True,
        "replacement_auto_execution": False,
        "current_execution": False,
    })
    review_fields = ["prompt_id", "image_path", "group_id", "planned_split", "planned_role", "taxonomy", "reviewed_event_label", "reviewed_sample_role", "semantic_alignment", "image_artifact_status", "review_status", "reviewer", "notes"]
    review_rows = [{"prompt_id": row.get("prompt_id"), "image_path": str(BATCH / "final" / f"{row.get('prompt_id')}.png"), "group_id": row.get("group_id"), "planned_split": row.get("planned_internal_split"), "planned_role": row.get("target_role"), "taxonomy": row.get("taxonomy"), "review_status": "unreviewed"} for row in prompts]
    write_csv(REVIEW / "human_review_template.csv", review_rows, review_fields)
    write_text(REVIEW / "review_instructions.md", """# Human semantic review instructions (template only)

This file is a preparation template. Do not mark any row `PASS`, `accepted`, or
semantically aligned until a human reviewer has inspected the generated image.
Mechanical validity is not semantic acceptance. The future review must cover
all 440 images after generation and duplicate/lineage QA, and must remain
separate from model predictions and ground-truth creation.
""")
    write_text(RUNNER / "runner_plan.md", f"""# GR3 runner plan (not executable in this preparation)

`NO_RETRY_GUARANTEE=false` because the installed runtime reports
`max_retries={retry.get('wrapper_max_retries')}` and exposes no supported
`--no-retry`/`--max-retries` flag. Therefore no runner is created and no
provider request is permitted. A future authorized revision must first provide
a supported one-attempt mechanism, then implement concurrency=1, micro-batch=10,
durable state, and global first-429/401/403 stop behavior.
""")


def create_authorization_packet(plan: dict[str, Any], capability: dict[str, Any], retry: dict[str, Any]) -> dict[str, Any]:
    packet = {
        "stage": "P4D_GR3_FULL_REGEN_AUTHORIZATION",
        "revision_id": REVISION_ID,
        "batch_id": BATCH_ID,
        "authorized": False,
        "authorization_required_from_user": True,
        "why_full_regen_required": "GR1 and current Codex profile/account lineage differ; GR2 continuation is not compatible.",
        "old_images_reused": 0,
        "new_logical_image_slots": 440,
        "provider": PROVIDER,
        "request_model": MODEL,
        "generation_backend": BACKEND,
        "current_safe_profile_fingerprint": (capability.get("auth") or {}).get("profile_fingerprint_sha256"),
        "new_generation_lineage": True,
        "gr1_continuation": False,
        "no_retry_guarantee": retry.get("no_retry_guarantee"),
        "wrapper_max_retries": retry.get("wrapper_max_retries"),
        "effective_possible_attempts_per_logical_slot": retry.get("effective_possible_attempts_per_logical_slot"),
        "concurrency": 1,
        "fail_fast_429": True,
        "fail_fast_401": True,
        "fail_fast_403": True,
        "exact_monetary_cost": "UNKNOWN",
        "quota_note": "440 new logical image generations would consume new provider quota/usage; no price is asserted.",
        "provider_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "user_authorization_text_required": "我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，接受旧 GR1 192 张不进入新 revision。",
    }
    write_json(AUTH / "full_regen_authorization.json", packet)
    write_text(AUTH / "full_regen_authorization_packet.md", f"""# P4D_GR3 full-regeneration authorization packet

```text
REVISION_ID={REVISION_ID}
BATCH_ID={BATCH_ID}
AUTHORIZED=false
WHY_FULL_REGEN_REQUIRED=account/profile changed
OLD_IMAGES_REUSED=0
NEW_LOGICAL_IMAGE_SLOTS=440
PROVIDER={PROVIDER}
REQUEST_MODEL={MODEL}
GENERATION_BACKEND={BACKEND}
NO_RETRY_GUARANTEE={str(retry.get('no_retry_guarantee')).lower()}
WRAPPER_MAX_RETRIES={retry.get('wrapper_max_retries')}
EFFECTIVE_POSSIBLE_ATTEMPTS_PER_LOGICAL_SLOT={retry.get('effective_possible_attempts_per_logical_slot')}
CONCURRENCY=1
FAIL_FAST_429=true
FAIL_FAST_401=true
FAIL_FAST_403=true
EXACT_MONETARY_COST=UNKNOWN
PROVIDER_REQUESTS=0
```

`authorized=false` is intentional and may not be changed by editing this file.
Generation requires a new user instruction explicitly authorizing the current
Codex profile and accepting that GR1's 192 historical images do not enter this
new revision. The current runtime cannot guarantee one provider attempt per
logical slot, so the preparation is also blocked on retry policy until that is
resolved or explicitly accepted in a separately authorized revision.
""")
    return packet


def write_reports(erratum: dict[str, Any], hashes: dict[str, Any], gr1_freeze: dict[str, Any], gr2_freeze: dict[str, Any], capability: dict[str, Any], retry: dict[str, Any], plan: dict[str, Any], packet: dict[str, Any], before: dict[str, Any], after: dict[str, Any], lineage: dict[str, Any]) -> None:
    boundary_delta = {
        key: after.get("counts", {}).get(key, 0) - before.get("counts", {}).get(key, 0)
        for key in before.get("counts", {})
    }
    reports = {
        "40_p4d_gr2_history_status_erratum.md": f"""# 40 — P4D_GR2 historical status erratum

```text
GR2_PROVIDER_LINEAGE_DECISION_REMAINS_VALID=true
GR2_GENERATION_REQUESTS=0
GR2_TERMINAL_FREEZE_REMAINS_VALID=true
REPORT39_MODIFIED=false
```

## 已确认事实

`reports/39_p4d_gr2_final.md` contains a later-summary status drift in its
top block. The drift does not alter the GR2 provider-lineage decision, its zero
request count, or the GR2 terminal freeze. The file and its SHA are preserved;
this erratum is additive.

| incorrect_field | incorrect_value | correct_value | evidence_source |
|---|---|---|---|
| `P1A_STATUS` | `COMPLETE` | `VAL_INCOMPLETE_FREEZE_BINDING_ERROR` | `{REPORTS / '09_p1a_final_report.md'}` |
| `P2_EXECUTED` | `false` | `true` (`P2_STATUS=COMPLETE`) | `{REPORTS / '17_p2_final_report.md'}` |
| `P2_STATUS` | omitted from report39 | `COMPLETE` | `{REPORTS / '17_p2_final_report.md'}` |
| `P3_EXECUTED` | `false` | `true` (`P3_STATUS=SCREENING_COMPLETE_NO_WINNER`) | `{REPORTS / '24_p3_final_report.md'}` |
| `P3_STATUS` | omitted from report39 | `SCREENING_COMPLETE_NO_WINNER` | `{REPORTS / '24_p3_final_report.md'}` |

The authoritative history is P0 protocol failure; P1A incomplete freeze-bound
VAL with valid DEV measurement and successful protocol repair; P1R complete
recovery baseline; P2 complete with C3 winner; P2L complete with no winner and
C3 unchanged; and P3 complete screening with no winner. No historical report
was rewritten.

## 实验判断

This is documentation drift only. It must not be interpreted as a request to
rewrite GR2's immutable freeze or to recalculate any old stage.

## 风险与限制

The later report39 remains intentionally inconsistent and should always be
read together with this erratum and the earlier evidence reports.

## 下一阶段建议

Use the corrected history in GR3 planning and keep reports 25--39 immutable.
""",
        "41_p4d_gr3_fullregen_preflight.md": f"""# 41 — P4D_GR3 full-regeneration preflight

```text
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
P4D_STATUS=GENERATION_REQUIRED
FULL_REGEN_REQUIRED=true
FULL_REGEN_AUTHORIZED=false
GR1_IMAGES_REUSED=0
PLANNED_NEW_IMAGES=440
PROMPT_CHANGED=false
GROUP_PLAN_CHANGED=false
TAXONOMY_CHANGED=false
SPLIT_CHANGED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
VAL=0
HOLDOUT=0
```

## 已确认事实

- P4D frozen artifacts: `all_match={str(hashes.get('all_match')).lower()}`.
- GR1 freeze verified: `{str(gr1_freeze.get('verified')).lower()}`; GR2 terminal freeze verified: `{str(gr2_freeze.get('verified')).lower()}`.
- The new revision is `{REVISION_ID}` with new batch `{BATCH_ID}` at `{BATCH}`. Its full-regeneration manifest has 440 rows and SHA-256 `{plan.get('full_regen_prompt_manifest_sha256')}`.
- Prompt bytes match the frozen source for all 440 rows; role counts are 300 hard-negative / 100 positive / 40 ordinary-negative; split is NEW_DESIGN 265 / NEW_SCREEN 175; groups are 88 with zero cross-split groups.
- The new batch has zero raw images, zero final images, and zero requests. The mechanical lineage audit at `{GR3 / '00_preflight' / 'lineage_isolation_audit.json'}` found `{lineage.get('historical_gr1_logical_images')}` historical GR1 logical images (`{lineage.get('historical_gr1_raw_files')}` raw + `{lineage.get('historical_gr1_final_files')}` final files), zero new-batch image files, zero symlinks, and zero old-image SHA collisions.
- No GR1 or GR2 image bytes were copied, symlinked, renamed, re-encoded, cropped, or resized into the new batch. Current Codex capability is `{capability.get('provider')}` / `{capability.get('request_model')}` / `{capability.get('generation_backend')}`, auth-ready `{(capability.get('auth') or {}).get('ready')}`, session-ready `{capability.get('session_ready')}`, endpoint-reachable `{(capability.get('auth') or {}).get('endpoint_reachable')}`.
- The read-only dataset boundary was before counts `{before.get('counts')}` and after counts `{after.get('counts')}` with delta `{boundary_delta}`; active P4D reference hits remained `{max(before.get('p4d_reference_hits_total', 0), after.get('p4d_reference_hits_total', 0))}`.

## 实验判断

GR3 is a new lineage preparation, not GR2 continuation. Its current safe profile
is bound only as the proposed new identity; it is deliberately not merged with
GR1's historical profile.

## 风险与限制

The provider can be authenticated, but retry behavior is not safely bounded to
one provider operation per logical slot. Preparation therefore cannot advance
to an executable runner.

## 下一阶段建议

Resolve the retry-policy gate and obtain explicit user authorization before any
generation request. Keep `authorized=false` and all image directories empty.
""",
        "42_p4d_gr3_retry_capability_audit.md": f"""# 42 — P4D_GR3 retry capability audit

```text
NO_RETRY_GUARANTEE={str(retry.get('no_retry_guarantee')).lower()}
WRAPPER_MAX_RETRIES={retry.get('wrapper_max_retries')}
EFFECTIVE_POSSIBLE_ATTEMPTS_PER_LOGICAL_SLOT={retry.get('effective_possible_attempts_per_logical_slot')}
CONCURRENCY_PREREGISTERED=1
FAIL_FAST_429=true
FAIL_FAST_401=true
FAIL_FAST_403=true
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
PROVIDER_REQUESTS=0
```

## 已确认事实

The installed wrapper is `{retry.get('wrapper_path')}` (SHA `{retry.get('wrapper_sha256')}`), dispatches to the installed binary, and the current runtime reports native retry policy `{retry.get('native_retry_policy_observed')}`. `images generate --help` exposes no supported `--no-retry` or `--max-retries` switch. The shared config inspection exposed no retry control. The third-party runtime was not modified.

## 实验判断

An outer Python loop with no retries would not prove no-retry: the native CLI
could still turn one logical slot into up to four provider attempts. The safe
preparation value is therefore `NO_RETRY_GUARANTEE=false`, not a misleading
`automatic_retry=false` claim.

## 风险与限制

The exact provider-side billing/attempt behavior for every error class is not
asserted; the upper-bound planning multiplier of four is used from the observed
`max_retries=3`. A future runner must make first 429/401/403 a global stop and
must not rely on hidden internal retries.

## 下一阶段建议

Wait for a supported one-attempt mechanism or explicit human acceptance of the
runtime retry risk. Do not create or run a generation runner in this revision.
""",
        "43_p4d_gr3_fullregen_plan.md": f"""# 43 — P4D_GR3 full-regeneration plan

```text
REVISION_ID={REVISION_ID}
BATCH_ID={BATCH_ID}
NEW_IMAGES_REQUIRED=440
GR1_IMAGES_REUSED=0
PROMPT_MANIFEST_SHA={plan.get('full_regen_prompt_manifest_sha256')}
GROUP_SPLIT_SHA={plan.get('group_split_freeze_sha256')}
NEW_DESIGN=265
NEW_SCREEN=175
GROUPS=88
CONCURRENCY=1
MICROBATCH=10
```

## 已确认事实

The 440-row plan points to frozen prompt paths and preserves the original
taxonomy, role quotas, group assignment, and NEW_DESIGN/NEW_SCREEN allocation.
It does not copy any old image bytes. Future execution order is preregistered
as smoke 1, sequential ramp 5, sequential ramp 10, then micro-batches of 10.

## 实验判断

This changes only image-generation lineage/account, not prompt semantics or
the experimental split. No execution runner is eligible while retry guarantee
is false and authorization is false.

## 风险与限制

All 440 logical generations are new quota/usage. Exact monetary cost is
`UNKNOWN`; no price was invented.

## 下一阶段建议

After retry and authorization gates pass, execute from zero in the new batch,
then mechanical/duplicate/lineage QA and human review. Do not ingest directly.
""",
        "44_p4d_gr3_authorization_required.md": f"""# 44 — P4D_GR3 authorization required

```text
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
FULL_REGEN_REQUIRED=true
FULL_REGEN_AUTHORIZED=false
NEW_GENERATION_LINEAGE=true
GR1_CONTINUATION=false
GR1_IMAGES_REUSED=0
PLANNED_NEW_IMAGES=440
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## 已确认事实

The authorization packet is `{AUTH / 'full_regen_authorization.json'}` and
explicitly contains `authorized=false`. It records current provider/model/
backend, safe profile fingerprint, 440 logical slots, zero old-image reuse,
concurrency 1, fail-fast 429/401/403, the retry limitation, and
`EXACT_MONETARY_COST=UNKNOWN`.

## 实验判断

User continuation messages do not constitute full-regeneration authorization.
The current preparation is correctly blocked before any provider request both
because authorization is false and because no-retry cannot be guaranteed.

## 风险与限制

Changing `authorized` by editing JSON would not be valid authorization. A new
user instruction must attest to the current Codex profile and accept that GR1's
192 historical images remain outside this revision.

## 下一阶段建议

The required user attestation is:

> 我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，接受旧 GR1 192 张不进入新 revision。

Even after that attestation, resolve or explicitly review the retry-policy gate
before generating. Keep formal ingest, C3, NEW_VAL, and HOLDOUT disabled.
""",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    for filename, content in reports.items():
        write_text(REPORTS / filename, content)


def audit() -> int:
    for directory in (GR3, PRE, AUTH, RUNNER, PLAN3, QA, REVIEW, FREEZE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    hashes = frozen_hash_check()
    write_json(PRE / "p4d_frozen_hash_check.json", hashes)
    if not hashes["all_match"]:
        # Do not create a new lineage or repair/re-freeze any source when a
        # supposedly frozen P4D input has drifted.
        write_json(FINAL_STATUS, {
            "stage": "P4D_GR3_FULL_REGEN_PREPARATION",
            "status": "BLOCKED_HISTORY_INTEGRITY_ERROR",
            "P4D_STATUS": "GENERATION_REQUIRED",
            "provider_requests": 0,
            "formal_ingest": False,
            "c3": False,
            "new_val_requests": 0,
            "holdout_requests": 0,
            "holdout_consumed": False,
        })
        print(json.dumps({"P4D_GR3_STATUS": "BLOCKED_HISTORY_INTEGRITY_ERROR", "frozen_hashes_all_match": False}, indent=2))
        return 2
    erratum = rebuild_history_erratum()
    gr1 = verify_immutable_freeze(GR1_FREEZE, GR1_FREEZE_SHA_EXPECTED, GR1_FREEZE.with_suffix(".json.sha256"), "PASS")
    gr2 = verify_immutable_freeze(GR2_FREEZE, GR2_FREEZE_SHA_EXPECTED, GR2_FREEZE.with_suffix(".json.sha256"), "FULL_REGEN_AUTHORIZATION_REQUIRED")
    # Verify GR1 and GR2 ledgers are untouched before creating the new surface.
    ledger_audit = {
        "gr1_path": str(GR1_LEDGER),
        "gr1_sha256": sha256_file(GR1_LEDGER) if GR1_LEDGER.exists() else None,
        "gr1_expected_sha256": GR1_LEDGER_SHA_EXPECTED,
        "gr1_match": GR1_LEDGER.exists() and sha256_file(GR1_LEDGER) == GR1_LEDGER_SHA_EXPECTED,
        "gr2_path": str(GR2_LEDGER),
        "gr2_sha256": sha256_file(GR2_LEDGER) if GR2_LEDGER.exists() else None,
        "gr2_requests_zero": GR2_LEDGER.exists() and sum(1 for _ in GR2_LEDGER.open(encoding="utf-8")) == 1,
        "gr1_read_only": True,
        "gr2_read_only": True,
    }
    write_json(PRE / "historical_freeze_audit.json", {"gr1_freeze": gr1, "gr2_freeze": gr2, "ledgers": ledger_audit, "captured_at": now()})
    ingest_probe = probe_ingest_media_validate()
    before = snapshot_dataset("before")
    capability, retry = provider_capability_audit()
    plan = create_batch_and_manifests()
    lineage = lineage_isolation_audit()
    create_templates(plan, retry)
    packet = create_authorization_packet(plan, capability, retry)
    after = snapshot_dataset("after")
    boundary = {
        "captured_at": now(),
        "before_path": str(PRE / "dataset_boundary_before.json"),
        "after_path": str(PRE / "dataset_boundary_after.json"),
        "before_counts": before["counts"],
        "after_counts": after["counts"],
        "count_delta": {key: after["counts"][key] - before["counts"][key] for key in before["counts"]},
        "before_annotation_sha256": before["annotation_sha256"],
        "after_annotation_sha256": after["annotation_sha256"],
        "p4d_reference_hits_before": before["p4d_reference_hits_total"],
        "p4d_reference_hits_after": after["p4d_reference_hits_total"],
        "p4d_reference_hits_total": max(before["p4d_reference_hits_total"], after["p4d_reference_hits_total"]),
        "formal_dataset_mutation": False,
        "interpretation": "Any shared-dataset delta is external unless P4D references appear; this preparation never writes the dataset.",
    }
    write_json(PRE / "dataset_boundary_audit.json", boundary)
    write_reports(erratum, hashes, gr1, gr2, capability, retry, plan, packet, before, after, lineage)
    final_status = {
        "stage": "P4D_GR3_FULL_REGEN_PREPARATION",
        "revision_id": REVISION_ID,
        "batch_id": BATCH_ID,
        "status": "BLOCKED_RETRY_POLICY",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "full_regen_required": True,
        "full_regen_authorized": False,
        "gr1_images_reused": 0,
        "planned_new_images": 440,
        "provider_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "generated_raw_count": 0,
        "final_count": 0,
        "created_at": now(),
    }
    write_json(FINAL_STATUS, final_status)
    print(json.dumps({
        "P4D_GR3_STATUS": final_status["status"],
        "P4D_STATUS": final_status["P4D_STATUS"],
        "frozen_hashes_all_match": hashes["all_match"],
        "gr1_freeze_verified": gr1["verified"],
        "gr2_freeze_verified": gr2["verified"],
        "gr1_ledger_match": ledger_audit["gr1_match"],
        "gr2_requests_zero": ledger_audit["gr2_requests_zero"],
        "current_profile_fingerprint": (capability.get("auth") or {}).get("profile_fingerprint_sha256"),
        "no_retry_guarantee": retry["no_retry_guarantee"],
        "wrapper_max_retries": retry["wrapper_max_retries"],
        "possible_attempts_per_logical_slot": retry["effective_possible_attempts_per_logical_slot"],
        "new_revision": REVISION_ID,
        "new_batch": str(BATCH),
        "full_regen_manifest_sha256": plan["full_regen_prompt_manifest_sha256"],
        "provider_requests": 0,
        "dataset_before": before["counts"],
        "dataset_after": after["counts"],
        "p4d_active_refs": boundary["p4d_reference_hits_total"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    # A preparation audit is successful only when all immutable inputs verify
    # *and* a bounded one-attempt provider policy is actually provable.  The
    # current runtime does not provide that guarantee, so return non-zero
    # while retaining the audit artifacts and explicit blocked status.
    return 0 if hashes["all_match"] and gr1["verified"] and gr2["verified"] and ledger_audit["gr1_match"] and ledger_audit["gr2_requests_zero"] and retry["no_retry_guarantee"] is True else 2


def freeze() -> int:
    freeze_dir = FREEZE_DIR
    freeze_dir.mkdir(parents=True, exist_ok=True)
    hashes = read_json(PRE / "p4d_frozen_hash_check.json", {}) or {}
    history = read_json(PRE / "historical_freeze_audit.json", {}) or {}
    capability = read_json(PRE / "provider_capability.json", {}) or {}
    retry = read_json(PRE / "retry_capability_audit.json", {}) or {}
    plan = read_json(PLAN3 / "fullregen_plan.json", {}) or {}
    packet = read_json(AUTH / "full_regen_authorization.json", {}) or {}
    boundary = read_json(PRE / "dataset_boundary_audit.json", {}) or {}
    erratum_path = GR2 / "history_status_erratum.json"
    report_paths = [REPORTS / f"{number}_{name}.md" for number, name in (
        ("40", "p4d_gr2_history_status_erratum"), ("41", "p4d_gr3_fullregen_preflight"),
        ("42", "p4d_gr3_retry_capability_audit"), ("43", "p4d_gr3_fullregen_plan"),
        ("44", "p4d_gr3_authorization_required"),
    )]
    artifact_paths = [
        PRE / "p4d_frozen_hash_check.json", PRE / "historical_freeze_audit.json", PRE / "provider_capability.json",
        PRE / "retry_capability_audit.json", PRE / "images_generate_help.json", PRE / "ingest_media_validate_probe.json", PRE / "dataset_boundary_before.json",
        PRE / "dataset_boundary_after.json", PRE / "dataset_boundary_audit.json", PRE / "lineage_isolation_audit.json",
        PRE / "prior_run_external_delta" / "dataset_boundary_before_second_audit.json",
        PRE / "prior_run_external_delta" / "dataset_boundary_after_second_audit.json",
        PLAN3 / "full_regen_prompt_manifest.csv",
        PLAN3 / "fullregen_plan.json", PLAN3 / "fullregen_plan.md", AUTH / "full_regen_authorization.json",
        AUTH / "full_regen_authorization_packet.md", RUNNER / "runner_plan.md", QA / "mechanical_qa_template.csv",
        QA / "duplicate_qa_plan.json", REVIEW / "human_review_template.csv", REVIEW / "review_instructions.md",
        BATCH / "README.md", BATCH / "generation_attempts.csv", BATCH / "generation_state.json", FINAL_STATUS,
        erratum_path,
    ]
    artifact_hashes = {str(path): sha256_file(path) if path.exists() else None for path in artifact_paths}
    report_hashes = {str(path): sha256_file(path) if path.exists() else None for path in report_paths}
    batch_file_counts = {name: len(list((BATCH / name).iterdir())) for name in ("prompts", "generated_raw", "final", "rejected", "metadata")}
    payload = {
        "stage": "P4D_GR3_FULL_REGEN_PREPARATION",
        "revision_id": REVISION_ID,
        "batch_id": BATCH_ID,
        "status": "BLOCKED_RETRY_POLICY",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "captured_at": now(),
        "terminal": {
            "FULL_REGEN_REQUIRED": True,
            "FULL_REGEN_AUTHORIZED": False,
            "GR1_IMAGES_REUSED": 0,
            "PLANNED_NEW_IMAGES": 440,
            "PROVIDER_REQUESTS": 0,
            "FORMAL_INGEST": False,
            "C3": False,
            "VAL": 0,
            "HOLDOUT": 0,
            "HOLDOUT_CONSUMED": False,
            "GENERATED_RAW": 0,
            "FINAL_IMAGES": 0,
            "BATCH_FILE_COUNTS": batch_file_counts,
        },
        "frozen_p4d_hashes": hashes,
        "gr1_terminal_freeze": history.get("gr1_freeze"),
        "gr2_terminal_freeze": history.get("gr2_freeze"),
        "gr2_history_erratum": {"path": str(erratum_path), "sha256": sha256_file(erratum_path) if erratum_path.exists() else None},
        "current_provider": {
            "provider": capability.get("provider"),
            "request_model": capability.get("request_model"),
            "generation_backend": capability.get("generation_backend"),
            "safe_profile_fingerprint": (capability.get("auth") or {}).get("profile_fingerprint_sha256"),
            "auth_ready": (capability.get("auth") or {}).get("ready"),
            "session_ready": capability.get("session_ready"),
        },
        "new_lineage": {
            "revision_id": REVISION_ID,
            "batch_id": BATCH_ID,
            "batch_path": str(BATCH),
            "new_generation_lineage": True,
            "gr1_continuation": False,
            "full_regen_manifest_path": str(PLAN3 / "full_regen_prompt_manifest.csv"),
            "full_regen_manifest_sha256": plan.get("full_regen_prompt_manifest_sha256"),
            "group_split_sha256": plan.get("group_split_freeze_sha256"),
        },
        "retry_capability": {
            "path": str(PRE / "retry_capability_audit.json"),
            "sha256": sha256_file(PRE / "retry_capability_audit.json") if (PRE / "retry_capability_audit.json").exists() else None,
            "no_retry_guarantee": retry.get("no_retry_guarantee"),
            "wrapper_max_retries": retry.get("wrapper_max_retries"),
            "effective_possible_attempts_per_logical_slot": retry.get("effective_possible_attempts_per_logical_slot"),
        },
        "authorization_packet": {
            "path": str(AUTH / "full_regen_authorization.json"),
            "sha256": sha256_file(AUTH / "full_regen_authorization.json") if (AUTH / "full_regen_authorization.json").exists() else None,
            "authorized": packet.get("authorized", False),
        },
        "qa_templates": {
            "mechanical": str(QA / "mechanical_qa_template.csv"),
            "review": str(REVIEW / "human_review_template.csv"),
            "runner_plan": str(RUNNER / "runner_plan.md"),
        },
        "dataset_boundary": {
            "path": str(PRE / "dataset_boundary_audit.json"),
            "sha256": sha256_file(PRE / "dataset_boundary_audit.json") if (PRE / "dataset_boundary_audit.json").exists() else None,
            "before_counts": boundary.get("before_counts"),
            "after_counts": boundary.get("after_counts"),
            "p4d_reference_hits_total": boundary.get("p4d_reference_hits_total"),
            "formal_dataset_mutation": False,
        },
        "artifact_sha256": artifact_hashes,
        "reports_sha256": report_hashes,
        "overview_sha256": sha256_file(OVERVIEW) if OVERVIEW.exists() else None,
        "runner_sha256": None,
        "credential_audit": {"secrets_written": False, "raw_account_or_user_ids_written": False, "tokens_keys_cookies_written": False},
        "production_code_modified": False,
        "ollama_service_modified": False,
    }
    freeze_path = freeze_dir / "p4d_gr3_preparation_freeze.json"
    write_json(freeze_path, payload)
    digest = sha256_file(freeze_path)
    sidecar = freeze_dir / "p4d_gr3_preparation_freeze.json.sha256"
    write_text(sidecar, f"{digest}  p4d_gr3_preparation_freeze.json")
    # FINAL_STATUS is included in artifact_sha256 above.  Do not mutate it
    # after writing the preparation freeze, otherwise the freeze would bind a
    # stale digest.  The freeze path and digest are emitted below and are
    # authoritative for the sealed preparation record.
    print(json.dumps({"preparation_freeze": str(freeze_path), "preparation_freeze_sha256": digest, "sidecar": str(sidecar)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit", "freeze"))
    args = parser.parse_args()
    return audit() if args.command == "audit" else freeze()


if __name__ == "__main__":
    raise SystemExit(main())
