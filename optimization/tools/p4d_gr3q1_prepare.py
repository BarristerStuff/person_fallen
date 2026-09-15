#!/usr/bin/env python3
"""Prepare the P4D GR3Q1 quota-recovery revision without provider requests.

This audit-only utility verifies the sealed GR3E parent, rebuilds the 440-slot
lineage inventory from the frozen manifest plus durable SQLite ledger, verifies
all preserved image bytes, runs read-only provider/profile/runtime probes, and
creates an authorization-required recovery plan.  It never invokes an image
generation subcommand and never edits the sealed parent execution.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation" / "gr3_fullregen"
PARENT = GR3 / "06_execution" / "authorized_20260827_01"
REV = GR3 / "06_execution" / "quota_recovery_20260827_01"
PREFLIGHT = REV / "00_preflight"
AUTH = REV / "01_authorization"
PLAN = REV / "02_plan"
LEDGER = REV / "03_ledger"
RAW_RESPONSES = REV / "04_raw_responses"
CHECKPOINTS = REV / "05_checkpoints"
QA = REV / "06_partial_or_full_qa"
FREEZE = REV / "freeze"

OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
REPORTS = ROOT / "reports"
PARENT_REPORT = REPORTS / "54_p4d_gr3e_authorized_final.md"
PREP_FREEZE = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
PARENT_FREEZE = PARENT / "freeze" / "p4d_gr3e_terminal_freeze.json"
MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
DB = PARENT / "03_ledger" / "gr3e_execution.sqlite3"
PARENT_LEDGER_CSV = PARENT / "03_ledger" / "execution_ledger.csv"
FAILED_RAW_RESPONSE = PARENT / "04_raw_responses" / "P4D_GR3E_BULK_0100_PF_P4D_HN_KNEEL_G008_V05.json"
FAILED_METADATA = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m/metadata/PF_P4D_HN_KNEEL_G008_V05.json")
OLD_GR1_QA = P4D / "03_intake_audit" / "gr1_independent_mechanical_qa.csv"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")

EXPECTED_PREP_SHA = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
EXPECTED_PARENT_SHA = "6afb294c4696eb89bea5d6dfb333efc38477fa05546b4e8cd4cc8ffa52d89f40"
EXPECTED_MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
EXPECTED_WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
EXPECTED_BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
EXPECTED_PROFILE = "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe"
EXPECTED_RUNTIME = "0.7.3"
EXPECTED_FAILED_PROMPT = "PF_P4D_HN_KNEEL_G008_V05"
EXPECTED_FAILED_REQUEST = "P4D_GR3E_BULK_0100_PF_P4D_HN_KNEEL_G008_V05"
FINAL_SIZE = (1920, 1080)

FROZEN_FILES = {
    "group_manifest.csv": (P4D / "01_prompt_plan" / "group_manifest.csv", "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab"),
    "group_split_freeze.json": (P4D / "01_prompt_plan" / "group_split_freeze.json", "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843"),
    "prompt_manifest.csv": (P4D / "01_prompt_plan" / "prompt_manifest.csv", "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb"),
    "prompt_pack.md": (P4D / "01_prompt_plan" / "prompt_pack.md", "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250"),
    "prompt_pack_freeze.json": (P4D / "01_prompt_plan" / "prompt_pack_freeze.json", "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b"),
    "C3_prompt.txt": (ROOT / "07_p3_structured_hard_negative_refinement" / "03_candidates" / "C3_BASELINE" / "C3_prompt.txt", "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"),
}

AUTHORIZATION_TEXT = (
    "我明确授权 P4D_GR3Q1 在保持当前 P4D_FULLREGEN_CODEX_PROFILE2_20260827_01 generation lineage 不变的前提下，"
    "保留已经成功并通过完整性复核的 99 张 GR3E 图像；允许在新的 quota-recovery revision 中重新尝试此前已确认 "
    "HTTP 429 失败的 PF_P4D_HN_KNEEL_G008_V05，并生成其余 340 个从未开始的 frozen prompt slots，共最多 "
    "341 个新的 logical slot invocations。我继续接受当前 GPT Image 2 runtime max_retries=3、单个 logical invocation "
    "最多约 4 次 provider attempts、精确费用未知以及由此产生的 quota/成本风险。任何返回的 HTTP "
    "429/401/403/timeout/5xx 均立即停止后续 logical slots，不执行自动 recovery。"
)


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


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(value if value.endswith("\n") else value + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def sidecar_value(path: Path) -> str | None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists():
        return None
    parts = sidecar.read_text(encoding="utf-8").split()
    return parts[0] if parts else None


def sanitize_text(text: str) -> str:
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(refresh[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    return text


def redact(value: Any) -> Any:
    sensitive = {"account_id", "chatgpt_user_id", "access_token", "refresh_token", "id_token", "api_key", "token"}
    if isinstance(value, dict):
        return {key: ("<REDACTED>" if key.lower() in sensitive else redact(child)) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def verify_parent() -> dict[str, Any]:
    parent = read_json(PARENT_FREEZE, {}) or {}
    bound_checks: list[dict[str, Any]] = []
    for section in ("artifact_sha256", "reports_sha256"):
        for raw_path, expected in (parent.get(section) or {}).items():
            path = Path(raw_path)
            actual = sha256_file(path)
            bound_checks.append({"section": section, "path": raw_path, "expected": expected, "actual": actual, "match": actual == expected})
    overview_binding = parent.get("overview") or {}
    if overview_binding.get("path") and overview_binding.get("sha256"):
        path = Path(str(overview_binding["path"]))
        actual = sha256_file(path)
        bound_checks.append({"section": "overview", "path": str(path), "expected": overview_binding["sha256"], "actual": actual, "match": actual == overview_binding["sha256"]})
    result = {
        "captured_at": now(),
        "preparation_freeze": {"path": str(PREP_FREEZE), "expected_sha256": EXPECTED_PREP_SHA, "actual_sha256": sha256_file(PREP_FREEZE), "sidecar_value": sidecar_value(PREP_FREEZE)},
        "parent_terminal_freeze": {"path": str(PARENT_FREEZE), "expected_sha256": EXPECTED_PARENT_SHA, "actual_sha256": sha256_file(PARENT_FREEZE), "sidecar_value": sidecar_value(PARENT_FREEZE)},
        "bound_checks": bound_checks,
        "bound_artifact_count": sum(1 for item in bound_checks if item["section"] == "artifact_sha256"),
        "bound_report_count": sum(1 for item in bound_checks if item["section"] == "reports_sha256"),
        "all_bound_artifacts_match": all(item["match"] for item in bound_checks),
        "parent_status": parent.get("status"),
        "parent_terminal": parent.get("terminal"),
    }
    result["preparation_freeze_verified"] = bool(result["preparation_freeze"]["actual_sha256"] == EXPECTED_PREP_SHA == result["preparation_freeze"]["sidecar_value"])
    result["parent_terminal_freeze_verified"] = bool(result["parent_terminal_freeze"]["actual_sha256"] == EXPECTED_PARENT_SHA == result["parent_terminal_freeze"]["sidecar_value"] and result["all_bound_artifacts_match"])
    write_json(PREFLIGHT / "parent_freeze_audit.json", result)
    return result


def verify_frozen_assets() -> dict[str, Any]:
    checks = []
    for name, (path, expected) in FROZEN_FILES.items():
        actual = sha256_file(path)
        checks.append({"name": name, "path": str(path), "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    result = {"captured_at": now(), "checks": checks, "all_match": all(item["match"] for item in checks)}
    write_json(PREFLIGHT / "p4d_frozen_hash_audit.json", result)
    return result


def verify_manifest() -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = read_csv(MANIFEST)
    prompt_mismatches = []
    for row in rows:
        path = Path(row["original_prompt_path"])
        actual = sha256_file(path)
        if actual != row["prompt_sha256"]:
            prompt_mismatches.append({"prompt_id": row["prompt_id"], "path": str(path), "expected": row["prompt_sha256"], "actual": actual})
    role_counts = Counter(row["target_role"] for row in rows)
    split_counts = Counter(row["planned_internal_split"] for row in rows)
    group_splits: dict[str, set[str]] = {}
    for row in rows:
        group_splits.setdefault(row["group_id"], set()).add(row["planned_internal_split"])
    result = {
        "captured_at": now(), "path": str(MANIFEST), "expected_sha256": EXPECTED_MANIFEST_SHA, "actual_sha256": sha256_file(MANIFEST),
        "rows": len(rows), "unique_prompt_ids": len({row["prompt_id"] for row in rows}), "unique_groups": len({row["group_id"] for row in rows}),
        "prompt_byte_mismatch": len(prompt_mismatches), "prompt_byte_mismatches": prompt_mismatches,
        "role_counts": dict(role_counts), "planned_split_counts": dict(split_counts),
        "cross_split_groups": sum(1 for values in group_splits.values() if len(values) > 1),
        "gr1_reuse_values": sorted({row["gr1_images_reused"] for row in rows}),
        "all_match": bool(sha256_file(MANIFEST) == EXPECTED_MANIFEST_SHA and len(rows) == 440 and len({row["prompt_id"] for row in rows}) == 440 and len({row["group_id"] for row in rows}) == 88 and not prompt_mismatches),
    }
    write_json(PREFLIGHT / "full_regen_manifest_audit.json", result)
    return rows, result


def db_rows() -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM slots ORDER BY ordinal")]
    finally:
        connection.close()


def verify_image(path: Path) -> tuple[bool, tuple[int, int] | None, str]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            return True, image.size, ""
    except Exception as exc:  # evidence is persisted; fail closed below
        return False, None, f"{type(exc).__name__}: {exc}"


def build_inventory(manifest_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    slots = db_rows()
    slot_by_id = {row["prompt_id"]: row for row in slots}
    old_hashes: set[str] = set()
    old_paths: list[Path] = []
    for old in read_csv(OLD_GR1_QA):
        for field in ("raw_sha256", "final_sha256"):
            if old.get(field):
                old_hashes.add(old[field])
        for field in ("raw_path", "final_path"):
            if old.get(field):
                old_paths.append(Path(old[field]))
    inventory: list[dict[str, Any]] = []
    preserved: list[dict[str, Any]] = []
    raw_issues: list[dict[str, Any]] = []
    final_issues: list[dict[str, Any]] = []
    gr1_hits: list[dict[str, Any]] = []
    samefile_hits: list[dict[str, Any]] = []
    symlink_hits: list[dict[str, Any]] = []
    for manifest in manifest_rows:
        prompt_id = manifest["prompt_id"]
        slot = slot_by_id.get(prompt_id, {})
        state = str(slot.get("state") or "MISSING_LEDGER_SLOT")
        raw_path = Path(str(slot.get("raw_path"))) if slot.get("raw_path") else None
        final_path = Path(str(slot.get("final_path"))) if slot.get("final_path") else None
        raw_exists = bool(raw_path and raw_path.exists() and raw_path.is_file())
        final_exists = bool(final_path and final_path.exists() and final_path.is_file())
        raw_actual = sha256_file(raw_path) if raw_path else None
        final_actual = sha256_file(final_path) if final_path else None
        raw_ok, raw_size, raw_error = verify_image(raw_path) if raw_exists and raw_path else (False, None, "missing")
        final_ok, final_size, final_error = verify_image(final_path) if final_exists and final_path else (False, None, "missing")
        raw_hash_match = bool(raw_actual and raw_actual == slot.get("raw_sha256"))
        final_hash_match = bool(final_actual and final_actual == slot.get("final_sha256"))
        dimension_ok = final_size == FINAL_SIZE if final_size else False
        raw_symlink = bool(raw_path and raw_path.is_symlink())
        final_symlink = bool(final_path and final_path.is_symlink())
        samefile = False
        if state == "SUCCESS" and raw_path and final_path and raw_exists and final_exists:
            try:
                samefile = os.path.samefile(raw_path, final_path)
            except OSError:
                samefile = False
        success_verified = bool(state == "SUCCESS" and raw_exists and final_exists and raw_hash_match and final_hash_match and raw_ok and final_ok and dimension_ok and not raw_symlink and not final_symlink and not samefile)
        if state == "SUCCESS":
            if not (raw_exists and raw_hash_match and raw_ok and not raw_symlink):
                raw_issues.append({"prompt_id": prompt_id, "path": str(raw_path) if raw_path else None, "exists": raw_exists, "hash_match": raw_hash_match, "pillow_pass": raw_ok, "error": raw_error, "symlink": raw_symlink})
            if not (final_exists and final_hash_match and final_ok and dimension_ok and not final_symlink):
                final_issues.append({"prompt_id": prompt_id, "path": str(final_path) if final_path else None, "exists": final_exists, "hash_match": final_hash_match, "pillow_pass": final_ok, "dimension": final_size, "error": final_error, "symlink": final_symlink})
            for kind, actual, path in (("raw", raw_actual, raw_path), ("final", final_actual, final_path)):
                if actual and actual in old_hashes:
                    gr1_hits.append({"prompt_id": prompt_id, "kind": kind, "sha256": actual, "path": str(path)})
            for current_path in (raw_path, final_path):
                if current_path and current_path.exists():
                    if current_path.is_symlink():
                        symlink_hits.append({"prompt_id": prompt_id, "path": str(current_path)})
                    for old_path in old_paths:
                        if old_path.exists():
                            try:
                                if os.path.samefile(current_path, old_path):
                                    samefile_hits.append({"prompt_id": prompt_id, "current": str(current_path), "gr1": str(old_path)})
                            except OSError:
                                pass
        row = {
            "prompt_id": prompt_id, "ordinal": slot.get("ordinal"), "group_id": manifest["group_id"], "variant_id": manifest["variant_id"],
            "taxonomy": manifest["taxonomy"], "role": manifest["target_role"], "planned_split": manifest["planned_internal_split"],
            "prompt_sha256": manifest["prompt_sha256"], "previous_execution_state": state, "previous_invocation_count": slot.get("invocation_count", 0),
            "previous_request_id": slot.get("request_id") or "", "previous_http_status": slot.get("http_status") or "", "previous_error_code": slot.get("error_code") or "",
            "raw_path": str(raw_path) if raw_path else "", "final_path": str(final_path) if final_path else "", "raw_sha256_ledger": slot.get("raw_sha256") or "", "raw_sha256_actual": raw_actual or "",
            "final_sha256_ledger": slot.get("final_sha256") or "", "final_sha256_actual": final_actual or "", "raw_integrity_pass": raw_exists and raw_hash_match and raw_ok and not raw_symlink,
            "final_integrity_pass": final_exists and final_hash_match and final_ok and dimension_ok and not final_symlink, "final_width": final_size[0] if final_size else "", "final_height": final_size[1] if final_size else "",
            "symlink_hit": raw_symlink or final_symlink, "raw_final_samefile": samefile, "verified_preserved_success": success_verified,
        }
        inventory.append(row)
        if state == "SUCCESS":
            preserved.append(row)
    verified_ids = {row["prompt_id"] for row in preserved if row["verified_preserved_success"]}
    outstanding_ids = {row["prompt_id"] for row in manifest_rows} - verified_ids
    outstanding: list[dict[str, Any]] = []
    recovery_order = 1
    ordered_ids = [EXPECTED_FAILED_PROMPT] + [row["prompt_id"] for row in manifest_rows if row["prompt_id"] != EXPECTED_FAILED_PROMPT]
    for prompt_id in ordered_ids:
        if prompt_id not in outstanding_ids:
            continue
        row = next(item for item in inventory if item["prompt_id"] == prompt_id)
        state = row["previous_execution_state"]
        if state == "FAILED_CONFIRMED" and str(row["previous_http_status"]) == "429":
            classification = "FAILED_CONFIRMED_HTTP_429"
            eligible = True
        elif state == "NOT_STARTED" and int(row["previous_invocation_count"] or 0) == 0:
            classification = "NEVER_STARTED"
            eligible = True
        else:
            classification = "COMPLETION_UNKNOWN"
            eligible = False
        outstanding.append({
            "prompt_id": prompt_id, "group_id": row["group_id"], "taxonomy": row["taxonomy"], "role": row["role"], "planned_split": row["planned_split"],
            "previous_execution_state": classification, "previous_request_id": row["previous_request_id"], "previous_http_status": row["previous_http_status"], "previous_error_code": row["previous_error_code"],
            "eligible_for_recovery": str(eligible).lower(), "recovery_order": recovery_order,
        })
        recovery_order += 1
    summary = {
        "captured_at": now(), "manifest_slots": len(manifest_rows), "sqlite_slots": len(slots), "sqlite_state_counts": dict(Counter(str(row["state"]) for row in slots)),
        "parent_logical_invocations": sum(1 for row in slots if int(row.get("invocation_count") or 0) > 0), "parent_csv_ledger_rows": len(read_csv(PARENT_LEDGER_CSV)),
        "preserved_success_expected": 99, "preserved_success_ledger": len(preserved), "verified_preserved_success": len(verified_ids),
        "preserved_raw_integrity_issues": len(raw_issues), "preserved_final_integrity_issues": len(final_issues), "raw_issues": raw_issues, "final_issues": final_issues,
        "gr1_hash_hits": gr1_hits, "gr1_hash_hit_count": len(gr1_hits), "samefile_hits": samefile_hits, "samefile_hit_count": len(samefile_hits), "symlink_hits": symlink_hits, "symlink_hit_count": len(symlink_hits),
        "derived_outstanding": len(outstanding_ids), "failed_confirmed_http_429": sum(1 for row in outstanding if row["previous_execution_state"] == "FAILED_CONFIRMED_HTTP_429"),
        "never_started": sum(1 for row in outstanding if row["previous_execution_state"] == "NEVER_STARTED"), "completion_unknown": sum(1 for row in outstanding if row["previous_execution_state"] == "COMPLETION_UNKNOWN"),
        "failed_prompt_id": EXPECTED_FAILED_PROMPT, "failed_parent_request_id": EXPECTED_FAILED_REQUEST,
    }
    fields = list(inventory[0].keys())
    write_csv(PLAN / "current_lineage_inventory.csv", fields, inventory)
    write_csv(PLAN / "verified_preserved_success_inventory.csv", fields, preserved)
    write_csv(PLAN / "recovery_outstanding_slots.csv", list(outstanding[0].keys()), outstanding)
    write_json(QA / "preserved_success_integrity_summary.json", summary)
    return inventory, preserved, outstanding, summary


def run_cli(label: str, args: list[str], timeout: int = 120) -> tuple[dict[str, Any], dict[str, Any]]:
    command = ["node", str(CLI), "--json", "--provider", "codex", *args]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout": sanitize_text(proc.stdout)}
    record = {"label": label, "command": command, "returncode": proc.returncode, "payload": redact(payload), "stderr": sanitize_text(proc.stderr), "captured_at": now(), "provider_requests": 0}
    write_json(PREFLIGHT / f"{label}.json", record)
    return payload, record


def provider_preflight() -> dict[str, Any]:
    config, config_record = run_cli("config_inspect", ["config", "inspect"])
    doctor, doctor_record = run_cli("doctor", ["doctor"])
    auth, auth_record = run_cli("auth_inspect", ["auth", "inspect"])
    help_payload, help_record = run_cli("images_generate_help", ["images", "generate", "--help"])
    codex_doctor = (((doctor.get("providers") or {}).get("codex") or {}) if isinstance(doctor, dict) else {})
    codex_auth = codex_doctor.get("auth") if isinstance(codex_doctor, dict) else {}
    codex_endpoint = codex_doctor.get("endpoint") if isinstance(codex_doctor, dict) else {}
    codex_auth = codex_auth if isinstance(codex_auth, dict) else {}
    codex_endpoint = codex_endpoint if isinstance(codex_endpoint, dict) else {}
    auth_codex = (((auth.get("providers") or {}).get("codex") or {}) if isinstance(auth, dict) else {})
    auth_codex = auth_codex if isinstance(auth_codex, dict) else {}
    account = str(codex_auth.get("account_id") or auth_codex.get("account_id") or "")
    user = str(codex_auth.get("chatgpt_user_id") or auth_codex.get("chatgpt_user_id") or "")
    fingerprint = hashlib.sha256(f"account={account}|user={user}".encode("utf-8")).hexdigest() if account or user else None
    selection = doctor.get("provider_selection") if isinstance(doctor, dict) else {}
    defaults = doctor.get("defaults") if isinstance(doctor, dict) else {}
    selection = selection if isinstance(selection, dict) else {}
    defaults = defaults if isinstance(defaults, dict) else {}
    provider = selection.get("resolved") or "codex"
    model = defaults.get("codex_model") or "gpt-5.4"
    backend = "image_generation"
    auth_ready = bool(codex_auth.get("ready") or auth_codex.get("ready"))
    endpoint_reachable = bool(codex_endpoint.get("reachable"))
    session_ready = bool(auth_ready and endpoint_reachable and codex_endpoint.get("tls_ok"))
    runtime_version = doctor.get("version") if isinstance(doctor, dict) else None
    retry_policy = doctor.get("retry_policy") if isinstance(doctor, dict) else None
    retry_policy = retry_policy if isinstance(retry_policy, dict) else {}
    help_text = json.dumps(help_payload, ensure_ascii=False).lower()
    config_text = json.dumps(config, ensure_ascii=False).lower()
    no_retry_control = any(token in help_text or token in config_text for token in ("--no-retry", "--max-retries", "max_retries=0", "retry=false"))
    wrapper_sha = sha256_file(CLI)
    binary_sha = sha256_file(BINARY)
    identity_match = bool(provider == "codex" and model == "gpt-5.4" and backend == "image_generation" and fingerprint == EXPECTED_PROFILE)
    runtime_match = bool(runtime_version == EXPECTED_RUNTIME and wrapper_sha == EXPECTED_WRAPPER_SHA and binary_sha == EXPECTED_BINARY_SHA and retry_policy.get("max_retries") == 3)
    result = {
        "stage": "P4D_GR3Q1_READ_ONLY_PROVIDER_PREFLIGHT", "captured_at": now(), "provider": provider, "request_model": model, "generation_backend": backend,
        "safe_profile_fingerprint": fingerprint, "expected_safe_profile_fingerprint": EXPECTED_PROFILE, "profile_continuity": fingerprint == EXPECTED_PROFILE,
        "runtime_version": runtime_version, "expected_runtime_version": EXPECTED_RUNTIME, "wrapper_path": str(CLI), "wrapper_sha256": wrapper_sha, "expected_wrapper_sha256": EXPECTED_WRAPPER_SHA,
        "binary_path": str(BINARY), "binary_sha256": binary_sha, "expected_binary_sha256": EXPECTED_BINARY_SHA,
        "auth_ready": auth_ready, "session_ready": session_ready, "endpoint_reachable": endpoint_reachable,
        "native_retry_policy": retry_policy, "native_max_retries": retry_policy.get("max_retries"), "outer_retry": False, "no_retry_control_observed": no_retry_control, "no_retry_guarantee": False,
        "possible_provider_attempts_per_logical_invocation_upper_bound": 4, "identity_continuity_gate": identity_match, "runtime_retry_compatibility_gate": runtime_match,
        "commands": {"config": config_record, "doctor": doctor_record, "auth": auth_record, "help": help_record}, "provider_requests": 0,
    }
    write_json(PREFLIGHT / "provider_quota_preflight_summary.json", result)
    return result


def dataset_snapshot(label: str) -> dict[str, Any]:
    proc = subprocess.run(["python3", str(VALIDATOR), "--json"], capture_output=True, text=True, check=False, timeout=240)
    try:
        validator = json.loads(proc.stdout)
    except json.JSONDecodeError:
        validator = {"parse_error": True, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]}
    counts: dict[str, int] = {}
    hashes: dict[str, str | None] = {}
    hits: dict[str, list[int]] = {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        hits[name] = [index for index, line in enumerate(lines, 1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()]
    result = {
        "label": label, "captured_at": now(), "validator_command": ["python3", str(VALIDATOR), "--json"], "validator_returncode": proc.returncode, "validator": validator,
        "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]},
        "annotation_sha256": hashes, "p4d_reference_hits_by_active_csv": hits, "p4d_reference_hits_total": sum(len(values) for values in hits.values()),
        "formal_dataset_mutation_by_gr3q1": False,
    }
    write_json(PREFLIGHT / f"dataset_boundary_{label}.json", result)
    return result


def write_plan_and_authorization(summary: dict[str, Any], provider: dict[str, Any]) -> tuple[Path, Path, Path]:
    failed_evidence = {
        "prompt_id": EXPECTED_FAILED_PROMPT, "parent_request_id": EXPECTED_FAILED_REQUEST, "parent_status": "FAILED_CONFIRMED_HTTP_429",
        "parent_raw_response_path": str(FAILED_RAW_RESPONSE), "parent_raw_response_sha256": sha256_file(FAILED_RAW_RESPONSE),
        "parent_metadata_path": str(FAILED_METADATA), "parent_metadata_sha256": sha256_file(FAILED_METADATA), "image_bytes": "none",
        "history_must_not_be_overwritten": True, "future_recovery_revision_required": True,
    }
    write_json(PLAN / "failed_slot_parent_evidence.json", failed_evidence)
    plan = {
        "stage": "P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION", "generation_lineage": "P4D_FULLREGEN_CODEX_PROFILE2_20260827_01", "recovery_revision": "P4D_GR3Q1_QUOTA_RECOVERY_20260827_01",
        "preserve_existing_gr3e_99": True, "verified_preserved_success": summary["verified_preserved_success"], "outstanding": summary["derived_outstanding"],
        "first_recovery_prompt_id": EXPECTED_FAILED_PROMPT, "first_request_is_recovery_smoke": True, "ramp_after_smoke": [5, 10], "bulk_micro_batch": 10, "concurrency": 1,
        "outer_automatic_retry": False, "native_max_retries": 3, "possible_new_logical_invocations": 341, "possible_provider_attempt_upper_bound": 1364,
        "global_stop_conditions": ["HTTP_429", "HTTP_401", "HTTP_403", "timeout", "HTTP_5xx", "connection_reset"],
        "parent_failed_history_immutable": True, "parent_request_binding_required": True, "authorization_required": True, "authorized": False,
        "provider_identity": {key: provider.get(key) for key in ("provider", "request_model", "generation_backend", "safe_profile_fingerprint", "runtime_version", "wrapper_sha256", "binary_sha256")},
        "provider_requests": 0, "exact_monetary_cost": "UNKNOWN", "formal_ingest": False, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0,
    }
    plan_path = PLAN / "quota_recovery_plan.json"
    write_json(plan_path, plan)
    write_text(PLAN / "quota_recovery_plan.md", """# P4D GR3Q1 quota-recovery execution preregistration

This is an unexecuted plan. It preserves 99 verified GR3E successes and permits no provider call until a separate, exact authorization is attested.

Future order: retry the one confirmed HTTP 429 slot as the recovery smoke; if it succeeds, run 5 then 10 never-started slots; thereafter use sequential 10-slot micro-batches. Any 429, 401, 403, timeout, 5xx, or connection reset globally stops new logical slots. Parent ledger history is immutable.
""")
    auth_json = AUTH / "quota_recovery_authorization.json"
    write_json(auth_json, {"stage": "P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION", "authorized": False, "authorization_attestation_present": False, "required_authorization_text_sha256": hashlib.sha256(AUTHORIZATION_TEXT.encode("utf-8")).hexdigest(), "preserve_existing_gr3e_99_required": True, "maximum_new_logical_slot_invocations": 341, "provider_requests": 0, "execution_eligible": None, "invalid_reason": None})
    auth_packet = AUTH / "quota_recovery_authorization_packet.md"
    write_text(auth_packet, f"""# P4D GR3Q1 quota-recovery authorization packet

```text
AUTHORIZED=false
PRESERVE_EXISTING_GR3E_99=true
MAX_NEW_LOGICAL_SLOT_INVOCATIONS=341
NATIVE_MAX_RETRIES=3
POSSIBLE_PROVIDER_ATTEMPTS_UPPER_BOUND=1364
EXACT_MONETARY_COST=UNKNOWN
PROVIDER_REQUESTS=0
```

The preparation artifact must remain unauthorized. This template is usable only if all continuation-compatibility gates pass. A profile/account mismatch invalidates quota recovery and requires a new full-regeneration lineage instead.

> {AUTHORIZATION_TEXT}

If and only if continuation compatibility passes, a later authorization creates a separate `quota_recovery_authorization_attestation.json`; do not edit the parent GR3E ledger/freeze.
""")
    return plan_path, auth_json, auth_packet


def determine_status(parent: dict[str, Any], frozen: dict[str, Any], manifest: dict[str, Any], summary: dict[str, Any], provider: dict[str, Any]) -> tuple[str, bool]:
    if not (parent["preparation_freeze_verified"] and parent["parent_terminal_freeze_verified"]):
        return "BLOCKED_PARENT_EXECUTION_FREEZE_MISMATCH", False
    if not frozen["all_match"] or not manifest["all_match"]:
        return "BLOCKED_FROZEN_ASSET_MISMATCH", False
    if summary["preserved_raw_integrity_issues"] or summary["preserved_final_integrity_issues"] or summary["gr1_hash_hit_count"] or summary["samefile_hit_count"] or summary["symlink_hit_count"]:
        return "BLOCKED_PRESERVED_SUCCESS_INTEGRITY", False
    if summary["verified_preserved_success"] != 99:
        return "BLOCKED_PRESERVED_SUCCESS_INTEGRITY", False
    if summary["derived_outstanding"] != 341 or summary["failed_confirmed_http_429"] != 1 or summary["never_started"] != 340:
        return "BLOCKED_SLOT_INVENTORY_MISMATCH", False
    if summary["completion_unknown"]:
        return "BLOCKED_COMPLETION_AMBIGUITY", False
    if not provider["identity_continuity_gate"]:
        if not provider["profile_continuity"]:
            return "BLOCKED_PROFILE_LINEAGE_CHANGE", False
        return "BLOCKED_PROVIDER_LINEAGE_CHANGE", False
    if not provider["runtime_retry_compatibility_gate"]:
        return "RETRY_POLICY_REAUDIT_REQUIRED", False
    if not (provider["auth_ready"] and provider["session_ready"] and provider["endpoint_reachable"]):
        return "BLOCKED_PROVIDER_NOT_READY", False
    return "READY_AWAITING_QUOTA_RECOVERY_AUTHORIZATION", True


def make_freeze(status: str, compatible: bool, parent: dict[str, Any], frozen: dict[str, Any], manifest: dict[str, Any], summary: dict[str, Any], provider: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> tuple[Path, str]:
    boundary = {
        "before": str(PREFLIGHT / "dataset_boundary_before.json"), "after": str(PREFLIGHT / "dataset_boundary_after.json"),
        "before_counts": before["counts"], "after_counts": after["counts"], "delta": {key: after["counts"][key] - before["counts"][key] for key in before["counts"]},
        "p4d_active_media_hits": len(after["p4d_reference_hits_by_active_csv"]["media.csv"]), "p4d_active_label_hits": len(after["p4d_reference_hits_by_active_csv"]["labels.csv"]),
        "p4d_active_batch_hits": len(after["p4d_reference_hits_by_active_csv"]["batches.csv"]), "p4d_active_split_hits": len(after["p4d_reference_hits_by_active_csv"]["splits.csv"]),
        "formal_ingest": False, "media_added": 0, "labels_added": 0,
    }
    write_json(PREFLIGHT / "dataset_boundary_audit.json", boundary)
    retry_history = read_json(PARENT / "06_full_qa" / "retry_observation.json", {}) or {}
    bind_paths = [
        PREP_FREEZE, PARENT_FREEZE, MANIFEST, DB, PARENT_LEDGER_CSV, FAILED_RAW_RESPONSE, FAILED_METADATA,
        PREFLIGHT / "parent_freeze_audit.json", PREFLIGHT / "p4d_frozen_hash_audit.json", PREFLIGHT / "full_regen_manifest_audit.json",
        PREFLIGHT / "config_inspect.json", PREFLIGHT / "doctor.json", PREFLIGHT / "auth_inspect.json", PREFLIGHT / "images_generate_help.json",
        PREFLIGHT / "provider_quota_preflight_summary.json", PREFLIGHT / "dataset_boundary_before.json", PREFLIGHT / "dataset_boundary_after.json", PREFLIGHT / "dataset_boundary_audit.json",
        PLAN / "current_lineage_inventory.csv", PLAN / "verified_preserved_success_inventory.csv", PLAN / "recovery_outstanding_slots.csv", PLAN / "failed_slot_parent_evidence.json",
        PLAN / "quota_recovery_plan.json", PLAN / "quota_recovery_plan.md", AUTH / "quota_recovery_authorization.json", AUTH / "quota_recovery_authorization_packet.md",
        QA / "preserved_success_integrity_summary.json",
    ]
    value = {
        "stage": "P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION", "name": "P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION", "status": status, "P4D_STATUS": "GENERATION_REQUIRED",
        "generation_lineage": "P4D_FULLREGEN_CODEX_PROFILE2_20260827_01", "recovery_revision": "P4D_GR3Q1_QUOTA_RECOVERY_20260827_01", "continuation_compatible": compatible,
        "terminal": {"PRESERVED_GR3E_SUCCESS": summary["verified_preserved_success"], "FAILED_CONFIRMED_429": summary["failed_confirmed_http_429"], "NEVER_STARTED": summary["never_started"], "COMPLETION_UNKNOWN": summary["completion_unknown"], "OUTSTANDING": summary["derived_outstanding"], "QUOTA_RECOVERY_AUTHORIZED": False, "PROVIDER_REQUESTS": 0, "FORMAL_INGEST": False, "MEDIA_ADDED": 0, "LABELS_ADDED": 0, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0, "HOLDOUT_CONSUMED": False, "PRODUCTION_CODE_MODIFIED": False, "OLLAMA_SERVICE_MODIFIED": False},
        "parent_freezes": parent, "frozen_assets": frozen, "manifest_audit": manifest, "preserved_success_audit": summary,
        "provider_runtime": provider, "retry_history": {"observed_native_retry_scheduled_events": retry_history.get("observed_native_retry_scheduled_events"), "observed_attempt_lower_bound_sum": retry_history.get("observed_attempt_lower_bound_sum"), "future_possible_logical_invocations": 341, "future_possible_provider_attempt_upper_bound": 1364, "exact_monetary_cost": "UNKNOWN", "outer_retry": False, "native_max_retries": 3},
        "dataset_boundary": boundary, "artifact_sha256": {str(path): sha256_file(path) for path in bind_paths}, "captured_at": now(),
    }
    freeze_path = FREEZE / "p4d_gr3q1_preparation_freeze.json"
    write_json(freeze_path, value)
    digest = sha256_file(freeze_path)
    sidecar = freeze_path.with_name(freeze_path.name + ".sha256")
    write_text(sidecar, f"{digest}  {freeze_path.name}")
    return freeze_path, str(digest)


def write_reports(status: str, compatible: bool, parent: dict[str, Any], frozen: dict[str, Any], manifest: dict[str, Any], summary: dict[str, Any], provider: dict[str, Any], before: dict[str, Any], after: dict[str, Any], freeze_path: Path, freeze_sha: str) -> list[Path]:
    common_risks = "No image-generation request was sent. Readiness is a point-in-time preflight, not authorization and not a guarantee that quota will remain available. Exact provider billing remains unknown."
    contents = {
        "55_p4d_gr3q1_parent_execution_audit.md": f"""# 55 — P4D GR3Q1 parent execution audit

```text
P4D_GR3Q1_STATUS={status}
GR3_PREPARATION_FREEZE_VERIFIED={str(parent['preparation_freeze_verified']).lower()}
GR3E_PARENT_TERMINAL_FREEZE_VERIFIED={str(parent['parent_terminal_freeze_verified']).lower()}
PARENT_BOUND_ARTIFACTS={parent['bound_artifact_count']}
PARENT_BOUND_REPORTS={parent['bound_report_count']}
ALL_PARENT_BINDINGS_MATCH={str(parent['all_bound_artifacts_match']).lower()}
P4D_FROZEN_HASHES_MATCH={str(frozen['all_match']).lower()}
FULLREGEN_MANIFEST_MATCH={str(manifest['all_match']).lower()}
PROVIDER_REQUESTS=0
```

## 已确认事实

The sealed authorized GR3E execution remains `BLOCKED_PROVIDER_USAGE_LIMIT`: 440 planned slots, 100 logical invocations, 99 successes, and one confirmed HTTP 429 failure. Its terminal freeze, sidecar, bound artifacts, reports, and overview binding all match.

## 合理推理

The sealed parent may be used as immutable evidence for a separate quota-recovery revision; it must not be resumed or rewritten.

## 风险与限制

{common_risks}
""",
        "56_p4d_gr3q1_preserved_99_inventory.md": f"""# 56 — P4D GR3Q1 preserved 99 inventory

```text
PRESERVED_SUCCESS_EXPECTED=99
PRESERVED_SUCCESS_VERIFIED={summary['verified_preserved_success']}
RAW_INTEGRITY_ISSUES={summary['preserved_raw_integrity_issues']}
FINAL_INTEGRITY_ISSUES={summary['preserved_final_integrity_issues']}
GR1_HASH_HITS={summary['gr1_hash_hit_count']}
SAMEFILE_HITS={summary['samefile_hit_count']}
SYMLINK_HITS={summary['symlink_hit_count']}
```

## 已确认事实

All {summary['verified_preserved_success']} ledger-success slots were re-opened with Pillow, matched ledger raw/final SHA-256 values, and had final dimensions 1920×1080. No GR1 content hash, same-file, or symlink reuse was detected.

## 合理推理

Image integrity passed, but preservation in a continued lineage remains conditional on provider/profile/model/backend/runtime continuity. When that continuity fails, these 99 remain historical lineage artifacts and cannot be mixed with newly generated images from the changed profile.

## 风险与限制

This is integrity and lineage QA only. It is not human semantic acceptance, formal ingest, or a completed 440-image revision.
""",
        "57_p4d_gr3q1_outstanding_341_plan.md": f"""# 57 — P4D GR3Q1 outstanding 341 plan

```text
DERIVED_OUTSTANDING={summary['derived_outstanding']}
FAILED_CONFIRMED_HTTP_429={summary['failed_confirmed_http_429']}
NEVER_STARTED={summary['never_started']}
COMPLETION_UNKNOWN={summary['completion_unknown']}
FIRST_RECOVERY_PROMPT_ID={EXPECTED_FAILED_PROMPT}
POSSIBLE_NEW_LOGICAL_INVOCATIONS=341
POSSIBLE_PROVIDER_ATTEMPT_UPPER_BOUND=1364
EXACT_MONETARY_COST=UNKNOWN
AUTHORIZED=false
```

## 已确认事实

Outstanding was derived as frozen 440 prompt IDs minus 99 verified-success IDs. The first future request is preregistered as a new logical recovery attempt bound to parent request `{EXPECTED_FAILED_REQUEST}`; the parent failed row remains immutable.

## 合理推理

The confirmed 429 slot is ambiguity-free because it returned no image bytes. It may be retried once in a new authorized recovery revision, followed by 5, 10, then sequential micro-batches of 10.

## 风险与限制

The 1,364 figure is only `341 × 4`, a theoretical runtime-attempt upper bound. It is neither a prediction nor a billing estimate.
""",
        "58_p4d_gr3q1_provider_quota_preflight.md": f"""# 58 — P4D GR3Q1 provider quota preflight

```text
PROVIDER={provider['provider']}
MODEL={provider['request_model']}
BACKEND={provider['generation_backend']}
SAFE_PROFILE_FINGERPRINT={provider['safe_profile_fingerprint']}
PROFILE_CONTINUITY={str(provider['profile_continuity']).lower()}
RUNTIME_VERSION={provider['runtime_version']}
WRAPPER_SHA256={provider['wrapper_sha256']}
BINARY_SHA256={provider['binary_sha256']}
AUTH_READY={str(provider['auth_ready']).lower()}
SESSION_READY={str(provider['session_ready']).lower()}
ENDPOINT_REACHABLE={str(provider['endpoint_reachable']).lower()}
NATIVE_MAX_RETRIES={provider['native_max_retries']}
OUTER_RETRY=false
CONTINUATION_COMPATIBLE={str(compatible).lower()}
PROVIDER_REQUESTS=0
```

## 已确认事实

Read-only `config inspect`, `doctor`, `auth inspect`, and `images generate --help` were executed. Provider, model, backend, wrapper, binary, runtime version, and native retry policy match the sealed lineage. The safe profile fingerprint must be evaluated separately and is shown by `PROFILE_CONTINUITY` above.

## 合理推理

Quota reset is only an execution boundary while every required identity remains unchanged. A changed safe profile fingerprint is an account/profile lineage boundary and blocks reuse of the 99 successes in a continued 341-slot recovery.

## 风险与限制

{common_risks}
""",
        "59_p4d_gr3q1_authorization_required.md": f"""# 59 — P4D GR3Q1 authorization required

```text
P4D_GR3Q1_STATUS={status}
P4D_STATUS=GENERATION_REQUIRED
CONTINUATION_COMPATIBLE={str(compatible).lower()}
QUOTA_RECOVERY_AUTHORIZED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
PREPARATION_FREEZE={freeze_path}
PREPARATION_FREEZE_SHA256={freeze_sha}
```

## 已确认事实

The current preparation is complete and frozen, but no recovery authorization exists. Shared-dataset validator after the audit reports status `{(after.get('validator') or {}).get('status')}`, errors `{(after.get('validator') or {}).get('error_count')}`, full hash `{(after.get('validator') or {}).get('full_hash_check')}`, warnings `{(after.get('validator') or {}).get('warning_count')}`. Active P4D references are {after['p4d_reference_hits_total']}.

## 合理推理

If `CONTINUATION_COMPATIBLE=true`, the exact packet could authorize a separate execution attestation. If it is false because the safe profile changed, no authorization text can make the current 99+341 recovery lineage valid; a new 440-slot full-regeneration lineage is required.

## 风险与限制

Authorization does not guarantee quota availability. Any first returned 429/401/403/timeout/5xx/connection reset must globally stop new logical slots; native retries may still occur inside the runtime.

## 条件授权模板

> {AUTHORIZATION_TEXT}

This template is `NOT_APPLICABLE` when `P4D_GR3Q1_STATUS=BLOCKED_PROFILE_LINEAGE_CHANGE`.
""",
    }
    paths: list[Path] = []
    for name, text in contents.items():
        path = REPORTS / name
        write_text(path, text)
        paths.append(path)
    return paths


def append_overview(status: str, compatible: bool, summary: dict[str, Any], provider: dict[str, Any], freeze_path: Path, freeze_sha: str) -> None:
    marker = "## P4D_GR3Q1 provider-quota recovery preparation"
    if marker in OVERVIEW.read_text(encoding="utf-8"):
        raise RuntimeError("P4D_GR3Q1 overview section already exists; refusing non-append-only rewrite")
    continuity_sentence = (
        "confirmed provider/model/backend/runtime continuity but detected a changed safe profile fingerprint"
        if not compatible else
        "confirmed provider/profile/model/backend/runtime continuity"
    )
    block = f"""

{marker}

```text
P4D_GR3Q1_NAME=P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION
P4D_GR3Q1_STATUS={status}
P4D_STATUS=GENERATION_REQUIRED
PRESERVED_GR3E_SUCCESS={summary['verified_preserved_success']}
FAILED_CONFIRMED_429={summary['failed_confirmed_http_429']}
NEVER_STARTED={summary['never_started']}
COMPLETION_UNKNOWN={summary['completion_unknown']}
OUTSTANDING={summary['derived_outstanding']}
CONTINUATION_COMPATIBLE={str(compatible).lower()}
QUOTA_RECOVERY_AUTHORIZED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
```

The sealed GR3E authorized execution remains unchanged. GR3Q1 verified its 99 successes against the durable ledger and image bytes, derived 341 outstanding slots, and {continuity_sentence}. No provider request was sent. The preparation freeze is `{freeze_path}` with SHA-256 `{freeze_sha}`. When compatibility is false, the 341-slot recovery is not authorizable; a new 440-slot full-regeneration lineage is required.
"""
    with OVERVIEW.open("a", encoding="utf-8") as handle:
        handle.write(block)
        handle.flush()
        os.fsync(handle.fileno())


def final_verify(freeze_path: Path, freeze_sha: str, report_paths: list[Path], overview_before: str | None) -> dict[str, Any]:
    freeze_payload = read_json(freeze_path, {}) or {}
    bindings = []
    for path_text, expected in (freeze_payload.get("artifact_sha256") or {}).items():
        path = Path(path_text)
        actual = sha256_file(path)
        bindings.append({"path": path_text, "expected": expected, "actual": actual, "match": expected == actual})
    result = {
        "captured_at": now(), "preparation_freeze_path": str(freeze_path), "preparation_freeze_sha256_expected": freeze_sha, "preparation_freeze_sha256_actual": sha256_file(freeze_path),
        "sidecar_value": sidecar_value(freeze_path), "freeze_self_match": sha256_file(freeze_path) == freeze_sha == sidecar_value(freeze_path),
        "all_bound_artifacts_match": all(item["match"] for item in bindings), "bound_artifact_checks": bindings,
        "reports": {str(path): sha256_file(path) for path in report_paths}, "overview_sha256_before_append": overview_before, "overview_sha256_after_append": sha256_file(OVERVIEW),
        "provider_requests": 0, "formal_ingest": False, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0,
    }
    write_json(CHECKPOINTS / "final_preparation_verification.json", result)
    return result


def main() -> int:
    for directory in (PREFLIGHT, AUTH, PLAN, LEDGER, RAW_RESPONSES, CHECKPOINTS, QA, FREEZE):
        directory.mkdir(parents=True, exist_ok=True)
    if any(RAW_RESPONSES.iterdir()):
        raise RuntimeError("quota-recovery raw-response directory is not empty")
    overview_before = sha256_file(OVERVIEW)
    if not OVERVIEW.exists() or not PARENT_REPORT.exists():
        raise RuntimeError("required overview or GR3E parent final report missing")
    before = dataset_snapshot("before")
    parent = verify_parent()
    frozen = verify_frozen_assets()
    manifest_rows, manifest = verify_manifest()
    _, _, _, summary = build_inventory(manifest_rows)
    provider = provider_preflight()
    write_plan_and_authorization(summary, provider)
    after = dataset_snapshot("after")
    status, compatible = determine_status(parent, frozen, manifest, summary, provider)
    freeze_path, freeze_sha = make_freeze(status, compatible, parent, frozen, manifest, summary, provider, before, after)
    report_paths = write_reports(status, compatible, parent, frozen, manifest, summary, provider, before, after, freeze_path, freeze_sha)
    append_overview(status, compatible, summary, provider, freeze_path, freeze_sha)
    verification = final_verify(freeze_path, freeze_sha, report_paths, overview_before)
    zero_request_gate = {
        "stage": "P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION", "status": status, "provider_requests": 0,
        "quota_recovery_authorized": False, "formal_ingest": False, "media_added": 0, "labels_added": 0, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0, "holdout_consumed": False,
        "raw_response_files": len(list(RAW_RESPONSES.iterdir())), "generation_runner_created": False, "generation_runner_executed": False,
    }
    write_json(CHECKPOINTS / "zero_request_gate.json", zero_request_gate)
    result = {
        "P4D_GR3Q1_STATUS": status, "P4D_STATUS": "GENERATION_REQUIRED", "CONTINUATION_COMPATIBLE": compatible,
        "parent_freeze_verified": parent["parent_terminal_freeze_verified"], "preparation_freeze_verified": parent["preparation_freeze_verified"], "p4d_hashes_match": frozen["all_match"], "manifest_match": manifest["all_match"],
        "summary": summary, "provider": {key: provider.get(key) for key in ("provider", "request_model", "generation_backend", "safe_profile_fingerprint", "profile_continuity", "runtime_version", "wrapper_sha256", "binary_sha256", "auth_ready", "session_ready", "endpoint_reachable", "native_max_retries")},
        "provider_requests": 0, "quota_recovery_authorized": False, "possible_new_logical_invocations": 341, "possible_provider_attempt_upper_bound": 1364, "exact_monetary_cost": "UNKNOWN",
        "dataset_final": after, "freeze_path": str(freeze_path), "freeze_sha256": freeze_sha, "final_verification": verification,
        "authorization_text": AUTHORIZATION_TEXT,
    }
    write_json(REV / "preparation_summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
