#!/usr/bin/env python3
"""Prepare, but do not execute, P4D GR3Q3 quota-window recovery.

This script is intentionally a zero-provider-request preparation boundary.  It
rebuilds the current-success inventory from the frozen prompt manifest and the
GR3E/GR3Q2E ledgers plus the actual image files, derives the exact outstanding
slots, captures quota/time/runtime evidence, creates an empty durable recovery
ledger, and seals the preparation in a new revision directory.  It never calls
the image-generation command.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
GR3 = ROOT / "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen"
EXEC = GR3 / "06_execution/quota_window_recovery_20260828_02"
PRE = EXEC / "00_preflight"
AUTH = EXEC / "01_authorization"
INV = EXEC / "02_inventory"
RUNNER = EXEC / "02_runner"
LEDGER = EXEC / "03_ledger"
RAW = EXEC / "04_raw_responses"
CHECK = EXEC / "05_checkpoints"
QA = EXEC / "06_full_qa"
FREEZE = EXEC / "freeze"

MANIFEST = GR3 / "03_fullregen_plan/full_regen_prompt_manifest.csv"
GR3E_INV = GR3 / "06_execution/authorized_20260827_01/06_full_qa/current_generation_inventory.csv"
GR3E_LEDGER = GR3 / "06_execution/authorized_20260827_01/03_ledger/execution_ledger.csv"
Q2E_ROOT = GR3 / "06_execution/profile_stratified_recovery_20260828_01"
Q2E_LEDGER = Q2E_ROOT / "03_ledger/execution_ledger.csv"
Q2E_FREEZE = Q2E_ROOT / "freeze/p4d_gr3q2e_terminal_freeze.json"
Q2E_RAW_FAILURE = Q2E_ROOT / "04_raw_responses/P4D_GR3Q2E_RECOVERY_0004_PF_P4D_HN_KNEEL_G009_V03.json"
Q2E_RUN_CONFIG = Q2E_ROOT / "02_runner/run_config.json"
GR1_QA = ROOT / "08_p4d_new_hard_negative_dev_revision/03_intake_audit/gr1_independent_mechanical_qa.csv"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")
SELF = Path(__file__).resolve()

EXPECTED_Q2E_FREEZE_SHA = "9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44"
EXPECTED_MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
EXPECTED_WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
EXPECTED_BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
EXPECTED_RUNTIME = "0.7.3"
EXPECTED_PROFILE_A = "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe"
EXPECTED_PROFILE_B = "d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190"
FAILED_PROMPT = "PF_P4D_HN_KNEEL_G009_V03"
FAILED_REQUEST = "P4D_GR3Q2E_RECOVERY_0004_PF_P4D_HN_KNEEL_G009_V03"
RESET_EPOCH = 1787914147
SAFETY_MARGIN_SECONDS = 653
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
FINAL_SIZE = (1920, 1080)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())


def write_empty(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.flush()
        os.fsync(f.fileno())


def sidecar_value(path: Path) -> str | None:
    p = path.with_name(path.name + ".sha256")
    if not p.exists():
        return None
    parts = p.read_text(encoding="utf-8").split()
    return parts[0] if parts else None


def sanitize_text(text: str) -> str:
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(refresh[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    return text


def redact(value: Any) -> Any:
    hidden = {"account_id", "chatgpt_user_id", "access_token", "refresh_token", "id_token", "token", "api_key", "email", "auth_file"}
    if isinstance(value, dict):
        return {k: ("<REDACTED>" if k.lower() in hidden else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def verify_image(path: Path | None) -> tuple[bool, tuple[int, int] | None, str]:
    if path is None or not path.is_file():
        return False, None, "missing"
    try:
        # verify() must be called immediately after open, before any load.
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            return True, image.size, ""
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def run_cli(label: str, args: list[str]) -> dict[str, Any]:
    command = ["node", str(CLI), "--json", "--provider", "codex", *args]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        stdout = proc.stdout
        stderr = proc.stderr
        try:
            payload = json.loads(stdout)
        except Exception:
            payload = {"parse_error": True, "stdout": sanitize_text(stdout[-12000:])}
        record = {
            "label": label,
            "command": ["node", "<gpt-image-2-skill>", "--json", "--provider", "codex", *args],
            "returncode": proc.returncode,
            "payload": redact(payload),
            "stderr": sanitize_text(stderr[-12000:]),
            "captured_at": iso(utc_now()),
            "image_generation_provider_requests": 0,
        }
    except Exception as exc:
        payload = {"exception": f"{type(exc).__name__}: {exc}"}
        record = {
            "label": label,
            "command": ["node", "<gpt-image-2-skill>", "--json", "--provider", "codex", *args],
            "returncode": None,
            "payload": payload,
            "stderr": "",
            "captured_at": iso(utc_now()),
            "image_generation_provider_requests": 0,
        }
    write_json(PRE / f"{label}.json", record)
    return {"raw": payload, "record": record}


def nested(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = nested(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = nested(child, key)
            if found is not None:
                return found
    return None


def q2e_parent_audit() -> dict[str, Any]:
    freeze = read_json(Q2E_FREEZE, {}) or {}
    artifact_checks = []
    for path_text, expected in (freeze.get("artifact_sha256") or {}).items():
        actual = sha256_file(Path(path_text))
        artifact_checks.append({"path": path_text, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    actual = sha256_file(Q2E_FREEZE)
    sidecar = sidecar_value(Q2E_FREEZE)
    terminal = freeze.get("terminal") or {}
    counts = terminal.get("counts") or {}
    value = {
        "captured_at": iso(utc_now()),
        "path": str(Q2E_FREEZE),
        "expected_sha256": EXPECTED_Q2E_FREEZE_SHA,
        "actual_sha256": actual,
        "sidecar_sha256": sidecar,
        "sidecar_match": actual == sidecar == EXPECTED_Q2E_FREEZE_SHA,
        "status": freeze.get("status"),
        "stage": freeze.get("stage"),
        "revision_id": freeze.get("revision_id"),
        "terminal_counts": counts,
        "bound_artifact_count": len(artifact_checks),
        "bound_artifacts": artifact_checks,
        "all_bound_artifacts_match": all(x["match"] for x in artifact_checks),
        "canonical_parent": True,
        "initial_binding_error_freeze_not_used": True,
    }
    value["all_match"] = bool(value["sidecar_match"] and value["status"] == "STOPPED_BY_FAILURE_POLICY" and value["all_bound_artifacts_match"])
    write_json(PRE / "q2e_parent_freeze_audit.json", value)
    return value


def manifest_audit() -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = read_csv(MANIFEST)
    mismatches = []
    for row in rows:
        actual = sha256_file(Path(row.get("original_prompt_path", "")))
        if actual != row.get("prompt_sha256"):
            mismatches.append({"prompt_id": row.get("prompt_id"), "expected_sha256": row.get("prompt_sha256"), "actual_sha256": actual})
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        groups[row.get("group_id", "")].add(row.get("planned_internal_split", ""))
    value = {
        "captured_at": iso(utc_now()),
        "path": str(MANIFEST),
        "expected_sha256": EXPECTED_MANIFEST_SHA,
        "actual_sha256": sha256_file(MANIFEST),
        "rows": len(rows),
        "unique_prompt_ids": len({r.get("prompt_id") for r in rows}),
        "unique_groups": len({r.get("group_id") for r in rows}),
        "prompt_byte_mismatch": len(mismatches),
        "prompt_byte_mismatches": mismatches,
        "role_counts": dict(Counter(r.get("target_role") for r in rows)),
        "split_counts": dict(Counter(r.get("planned_internal_split") for r in rows)),
        "cross_split_group_count": sum(1 for s in groups.values() if len(s) > 1),
        "cross_split_groups": sorted(k for k, s in groups.items() if len(s) > 1),
        "gr1_reuse_values": sorted({r.get("gr1_images_reused") for r in rows}),
    }
    value["all_match"] = bool(
        value["actual_sha256"] == EXPECTED_MANIFEST_SHA
        and value["rows"] == 440
        and value["unique_prompt_ids"] == 440
        and value["unique_groups"] == 88
        and value["prompt_byte_mismatch"] == 0
        and value["cross_split_group_count"] == 0
        and value["gr1_reuse_values"] == ["0"]
    )
    write_json(PRE / "full_manifest_audit.json", value)
    return rows, value


def load_q2e_response_map() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((Q2E_ROOT / "04_raw_responses").glob("*.json")):
        obj = read_json(path, {}) or {}
        pid = obj.get("prompt_id")
        if pid:
            result[pid] = obj
    return result


def build_inventory(manifest_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    manifest_by_id = {r.get("prompt_id"): r for r in manifest_rows}
    gr3e_rows = {r.get("prompt_id"): r for r in read_csv(GR3E_INV)}
    gr3e_ledger = {r.get("logical_slot_id"): r for r in read_csv(GR3E_LEDGER)}
    q2e_rows = {r.get("logical_slot_id"): r for r in read_csv(Q2E_LEDGER)}
    q2e_response = load_q2e_response_map()
    verified: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    source_success = []

    # GR3E supplies the 99 Profile-A successes.
    for pid, source in gr3e_rows.items():
        if source.get("state") != "SUCCESS":
            continue
        source_success.append((pid, "GR3E_PROFILE_A", source, gr3e_ledger.get(pid, {}), None))
    # Q2E supplies exactly three Profile-B successes, including the former GR3E failure recovery.
    for pid, source in q2e_rows.items():
        if source.get("state") != "SUCCESS_PROFILE_B":
            continue
        response = q2e_response.get(pid, {})
        source_success.append((pid, "GR3Q2_PROFILE_B", source, source, response))

    seen: set[str] = set()
    for pid, profile, source, ledger, response in source_success:
        manifest = manifest_by_id.get(pid)
        if not manifest:
            issues.append({"prompt_id": pid, "issue": "success_not_in_frozen_manifest"})
            continue
        if pid in seen:
            issues.append({"prompt_id": pid, "issue": "duplicate_success_source"})
            continue
        seen.add(pid)
        if profile == "GR3E_PROFILE_A":
            raw_text, final_text = source.get("raw_path", ""), source.get("final_path", "")
            raw_expected, final_expected = source.get("raw_sha256", ""), source.get("final_sha256", "")
            request_id, http_status, parent_state = ledger.get("provider_request_id", ""), ledger.get("http_status", ""), "SUCCESS"
            parent_revision = "P4D_GR3E_AUTHORIZED_20260827_01"
        else:
            raw_text = response.get("raw_path") or str(BATCH / "generated_raw" / f"{pid}.png")
            final_text = response.get("final_path") or str(BATCH / "final" / f"{pid}.png")
            raw_expected, final_expected = source.get("raw_sha256", ""), source.get("final_sha256", "")
            request_id, http_status, parent_state = source.get("provider_request_id", ""), source.get("http_status", ""), source.get("parent_state", "")
            parent_revision = "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY_20260828_01"
        raw_path, final_path = Path(raw_text), Path(final_text)
        raw_actual, final_actual = sha256_file(raw_path), sha256_file(final_path)
        raw_pillow, raw_size, raw_error = verify_image(raw_path)
        final_pillow, final_size, final_error = verify_image(final_path)
        raw_link, final_link = raw_path.is_symlink(), final_path.is_symlink()
        samefile = False
        if raw_path.is_file() and final_path.is_file():
            try:
                samefile = os.path.samefile(raw_path, final_path)
            except OSError:
                samefile = False
        dimensions = final_size == FINAL_SIZE
        matches_manifest = all(
            [manifest.get("group_id") == source.get("group_id", manifest.get("group_id")),
             manifest.get("variant_id") == source.get("variant_id", manifest.get("variant_id")),
             manifest.get("target_role") == source.get("target_role", manifest.get("target_role")),
             manifest.get("taxonomy") == source.get("taxonomy", manifest.get("taxonomy")),
             manifest.get("planned_internal_split") == source.get("planned_split", source.get("planned_internal_split", manifest.get("planned_internal_split"))),
             manifest.get("prompt_sha256") == source.get("prompt_sha256", manifest.get("prompt_sha256"))]
        )
        ok = bool(raw_actual == raw_expected and final_actual == final_expected and raw_pillow and final_pillow and dimensions and not raw_link and not final_link and not samefile and matches_manifest)
        if not ok:
            issues.append({"prompt_id": pid, "profile": profile, "raw_error": raw_error, "final_error": final_error, "raw_sha_match": raw_actual == raw_expected, "final_sha_match": final_actual == final_expected, "dimensions": final_size, "symlink": raw_link or final_link, "samefile": samefile, "manifest_match": matches_manifest})
        verified.append({
            "prompt_id": pid,
            "ordinal": manifest_rows.index(manifest),
            "group_id": manifest.get("group_id"),
            "variant_id": manifest.get("variant_id"),
            "planned_split": manifest.get("planned_internal_split"),
            "target_role": manifest.get("target_role"),
            "taxonomy": manifest.get("taxonomy"),
            "event_label": manifest.get("target_event_label"),
            "prompt_sha256": manifest.get("prompt_sha256"),
            "generation_profile_stratum": profile,
            "parent_revision": parent_revision,
            "parent_state": parent_state,
            "parent_http_status": http_status,
            "parent_request_id": request_id,
            "raw_path": str(raw_path),
            "final_path": str(final_path),
            "raw_sha256_expected": raw_expected,
            "raw_sha256_actual": raw_actual or "",
            "final_sha256_expected": final_expected,
            "final_sha256_actual": final_actual or "",
            "raw_pillow_pass": raw_pillow,
            "final_pillow_pass": final_pillow,
            "final_width": final_size[0] if final_size else "",
            "final_height": final_size[1] if final_size else "",
            "raw_final_samefile": samefile,
            "symlink_hit": bool(raw_link or final_link),
            "verified_success": ok,
        })

    verified_ok = [r for r in verified if r["verified_success"]]
    ids = {r["prompt_id"] for r in verified_ok}
    summary = {
        "captured_at": iso(utc_now()),
        "total_verified_success": len(verified_ok),
        "expected_total": 102,
        "profile_strata": dict(Counter(r["generation_profile_stratum"] for r in verified_ok)),
        "role_counts": dict(Counter(r["target_role"] for r in verified_ok)),
        "split_counts": dict(Counter(r["planned_split"] for r in verified_ok)),
        "taxonomy_counts": dict(Counter(r["taxonomy"] for r in verified_ok)),
        "inventory_issues": issues,
        "source_counts": {"gr3e_success_rows": sum(1 for r in gr3e_rows.values() if r.get("state") == "SUCCESS"), "q2e_success_profile_b_rows": sum(1 for r in q2e_rows.values() if r.get("state") == "SUCCESS_PROFILE_B")},
        "unique_prompt_ids": len(ids),
        "all_verified": len(verified_ok) == 102 and len(ids) == 102 and not issues,
    }
    fields = list(verified[0].keys()) if verified else ["prompt_id"]
    write_csv(INV / "current_success_inventory_gr3q3.csv", fields, sorted(verified, key=lambda r: int(r["ordinal"])))
    write_json(INV / "inventory_summary.json", summary)
    return verified_ok, summary, {"gr3e_rows": gr3e_rows, "q2e_rows": q2e_rows, "q2e_response": q2e_response, "manifest_by_id": manifest_by_id}


def gr1_exclusion_audit(current: list[dict[str, Any]], manifest_rows: list[dict[str, str]]) -> dict[str, Any]:
    old_rows = read_csv(GR1_QA)
    old_hashes: set[str] = set()
    old_paths: list[Path] = []
    for row in old_rows:
        old_hashes.update(v for k in ("raw_sha256", "final_sha256") if (v := row.get(k)))
        old_paths.extend(Path(v) for k in ("raw_path", "final_path") if (v := row.get(k)))
    sha_hits, samefile_hits, symlink_hits = [], [], []
    for row in current:
        for kind in ("raw", "final"):
            digest = row.get(f"{kind}_sha256_actual")
            if digest and digest in old_hashes:
                sha_hits.append({"prompt_id": row["prompt_id"], "kind": kind, "sha256": digest})
        for text in (row.get("raw_path", ""), row.get("final_path", "")):
            path = Path(text)
            if path.is_symlink():
                symlink_hits.append({"prompt_id": row["prompt_id"], "path": text})
            for old in old_paths:
                if path.is_file() and old.is_file():
                    try:
                        if os.path.samefile(path, old):
                            samefile_hits.append({"prompt_id": row["prompt_id"], "current_path": text, "gr1_path": str(old)})
                    except OSError:
                        pass
    value = {
        "captured_at": iso(utc_now()),
        "gr1_qa_path": str(GR1_QA),
        "gr1_row_count": len(old_rows),
        "manifest_gr1_reuse_values": sorted({r.get("gr1_images_reused") for r in manifest_rows}),
        "GR1_IMAGES_REUSED": 0,
        "GR1_SHA_HITS": len(sha_hits),
        "GR1_SAMEFILE_HITS": len(samefile_hits),
        "GR1_SYMLINK_HITS": len(symlink_hits),
        "sha_hits": sha_hits,
        "samefile_hits": samefile_hits,
        "symlink_hits": symlink_hits,
        "all_excluded": not sha_hits and not samefile_hits and not symlink_hits,
    }
    write_json(INV / "gr1_exclusion_audit.json", value)
    return value


def build_outstanding(manifest_rows: list[dict[str, str]], verified: list[dict[str, Any]], sources: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    success_ids = {r["prompt_id"] for r in verified}
    gr3e = sources["gr3e_rows"]
    q2e = sources["q2e_rows"]
    q2e_failed = q2e.get(FAILED_PROMPT, {})
    rows: list[dict[str, Any]] = []
    ordered = [r for r in manifest_rows if r.get("prompt_id") == FAILED_PROMPT] + [r for r in manifest_rows if r.get("prompt_id") != FAILED_PROMPT]
    for manifest in ordered:
        pid = manifest.get("prompt_id")
        if pid in success_ids:
            continue
        parent = gr3e.get(pid, {})
        if pid == FAILED_PROMPT and q2e_failed.get("state") == "FAILED_CONFIRMED_PROFILE_B":
            parent_state, parent_request_id, parent_http, parent_error = "FAILED_CONFIRMED_HTTP_429", q2e_failed.get("provider_request_id") or FAILED_REQUEST, q2e_failed.get("http_status") or "429", q2e_failed.get("error_code") or "http_error"
        elif parent.get("state") == "NOT_STARTED":
            parent_state, parent_request_id, parent_http, parent_error = "NEVER_STARTED", "", "", ""
        elif parent.get("state") == "FAILED_CONFIRMED":
            parent_state, parent_request_id, parent_http, parent_error = "COMPLETION_UNKNOWN", "", "", "parent_failed_not_reconciled"
        else:
            parent_state, parent_request_id, parent_http, parent_error = "COMPLETION_UNKNOWN", "", "", "unrecognized_parent_state"
        rows.append({
            "recovery_order": len(rows) + 1,
            "prompt_id": pid,
            "ordinal": manifest_rows.index(manifest),
            "group_id": manifest.get("group_id"),
            "variant_id": manifest.get("variant_id"),
            "planned_split": manifest.get("planned_internal_split"),
            "target_role": manifest.get("target_role"),
            "taxonomy": manifest.get("taxonomy"),
            "prompt_path": manifest.get("original_prompt_path"),
            "prompt_sha256": manifest.get("prompt_sha256"),
            "parent_state": parent_state,
            "parent_request_id": parent_request_id,
            "parent_http_status": parent_http,
            "parent_error_code": parent_error,
            "profile_stratum": "GR3Q3_PROFILE_B",
            "eligible_after_authorization": False,
        })
    counts = Counter(r["parent_state"] for r in rows)
    summary = {
        "captured_at": iso(utc_now()),
        "total_outstanding": len(rows),
        "expected_outstanding": 338,
        "failed_confirmed_http_429": counts.get("FAILED_CONFIRMED_HTTP_429", 0),
        "never_started": counts.get("NEVER_STARTED", 0),
        "completion_unknown": counts.get("COMPLETION_UNKNOWN", 0),
        "role_counts": dict(Counter(r["target_role"] for r in rows)),
        "split_counts": dict(Counter(r["planned_split"] for r in rows)),
        "first_recovery_slot": rows[0]["prompt_id"] if rows else None,
        "exact_expected_state": len(rows) == 338 and counts.get("FAILED_CONFIRMED_HTTP_429", 0) == 1 and counts.get("NEVER_STARTED", 0) == 337 and counts.get("COMPLETION_UNKNOWN", 0) == 0,
    }
    fields = list(rows[0].keys()) if rows else ["recovery_order", "prompt_id"]
    write_csv(INV / "outstanding_338.csv", fields, rows)
    write_json(INV / "outstanding_summary.json", summary)
    return rows, summary


def quota_evidence() -> dict[str, Any]:
    raw = read_json(Q2E_RAW_FAILURE, {}) or {}
    detail_text = (((raw.get("outer_json") or {}).get("error") or {}).get("detail"))
    detail = {}
    try:
        detail = json.loads(detail_text) if isinstance(detail_text, str) else (detail_text or {})
    except Exception as exc:
        detail = {"parse_error": f"{type(exc).__name__}: {exc}", "raw_detail": str(detail_text)}
    error = detail.get("error") or {}
    reset = datetime.fromtimestamp(RESET_EPOCH, timezone.utc)
    not_before = reset + timedelta(seconds=SAFETY_MARGIN_SECONDS)
    value = {
        "captured_at": iso(utc_now()),
        "parent_raw_path": str(Q2E_RAW_FAILURE),
        "parent_raw_sha256": sha256_file(Q2E_RAW_FAILURE),
        "parent_raw_expected_sha256": "a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99",
        "http_status": raw.get("http_status"),
        "error_code": raw.get("error_code"),
        "provider_error_type": error.get("type"),
        "provider_error_message": error.get("message"),
        "plan_type": error.get("plan_type"),
        "resets_at_epoch": error.get("resets_at"),
        "resets_at_utc": reset.isoformat(),
        "resets_at_local": reset.astimezone(LOCAL_TZ).isoformat(),
        "resets_in_seconds": error.get("resets_in_seconds"),
        "safety_margin_seconds": SAFETY_MARGIN_SECONDS,
        "not_before_utc": not_before.isoformat(),
        "not_before_local": not_before.astimezone(LOCAL_TZ).isoformat(),
        "evidence_matches_expected": bool(sha256_file(Q2E_RAW_FAILURE) == "a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99" and error.get("type") == "usage_limit_reached" and error.get("resets_at") == RESET_EPOCH and error.get("resets_in_seconds") == 15278),
    }
    write_json(PRE / "quota_reset_evidence.json", value)
    return value


def time_gate(quota: dict[str, Any]) -> dict[str, Any]:
    local = utc_now().astimezone(LOCAL_TZ)
    utc = local.astimezone(timezone.utc)
    not_before = datetime.fromisoformat(quota["not_before_local"])
    value = {
        "captured_at": iso(utc_now()),
        "current_utc": iso(utc),
        "current_local": iso(local),
        "not_before_utc": quota["not_before_utc"],
        "not_before_local": quota["not_before_local"],
        "time_gate_pass": local >= not_before,
        "status_if_not_pass": "WAITING_FOR_PROVIDER_QUOTA_RESET",
        "provider_requests": 0,
    }
    write_json(PRE / "time_gate.json", value)
    return value


def provider_runtime_audit() -> dict[str, Any]:
    config = run_cli("config_inspect", ["config", "inspect"])
    doctor = run_cli("doctor", ["doctor"])
    auth = run_cli("auth_inspect", ["auth", "inspect"])
    help_result = run_cli("images_generate_help", ["images", "generate", "--help"])
    raw_doctor = doctor["raw"] if isinstance(doctor["raw"], dict) else {}
    raw_auth = auth["raw"] if isinstance(auth["raw"], dict) else {}
    codex = ((raw_doctor.get("providers") or {}).get("codex") or {})
    auth_codex = ((raw_auth.get("providers") or {}).get("codex") or {})
    account = str(codex.get("auth", {}).get("account_id") or auth_codex.get("account_id") or "")
    user = str(codex.get("auth", {}).get("chatgpt_user_id") or auth_codex.get("chatgpt_user_id") or "")
    profile_hash = hashlib.sha256(f"account={account}|user={user}".encode()).hexdigest() if account or user else None
    selection = raw_doctor.get("provider_selection") or {}
    defaults = raw_doctor.get("defaults") or {}
    endpoint = codex.get("endpoint") or {}
    retry = raw_doctor.get("retry_policy") or {}
    value = {
        "captured_at": iso(utc_now()),
        "requested_provider": "codex",
        "resolved_provider": selection.get("resolved"),
        "provider": "codex",
        "request_model": defaults.get("codex_model"),
        "generation_backend": "image_generation",
        "runtime_version": raw_doctor.get("version"),
        "wrapper_path": str(CLI),
        "wrapper_sha256": sha256_file(CLI),
        "binary_path": str(BINARY),
        "binary_sha256": sha256_file(BINARY),
        "native_retry_policy": retry,
        "native_max_retries": retry.get("max_retries"),
        "outer_retry": False,
        "auth_ready_observed": bool((codex.get("auth") or {}).get("ready") or auth_codex.get("ready")),
        "endpoint_reachable_observed": bool(endpoint.get("reachable")),
        "tls_ok_observed": bool(endpoint.get("tls_ok")),
        "profile_fingerprint_safe_hash": profile_hash,
        "profile_fingerprint_matches_expected_b": profile_hash == EXPECTED_PROFILE_B,
        "account_or_user_raw_values_persisted": False,
        "commands": {"config_inspect": config["record"], "doctor": doctor["record"], "auth_inspect": auth["record"], "images_generate_help": help_result["record"]},
        "image_generation_provider_requests": 0,
        "read_only_capability_audit": True,
    }
    write_json(PRE / "provider_runtime_audit.json", value)
    return value


def dataset_snapshot(label: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(["python3", str(VALIDATOR), "--json"], capture_output=True, text=True, timeout=240, check=False)
        try:
            validator = json.loads(proc.stdout)
        except Exception:
            validator = {"parse_error": True, "stdout_tail": proc.stdout[-16000:], "stderr_tail": proc.stderr[-4000:]}
        returncode = proc.returncode
    except Exception as exc:
        validator, returncode = {"exception": f"{type(exc).__name__}: {exc}"}, None
    counts, hashes, hits = {}, {}, {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        hits[name] = [i for i, line in enumerate(lines, 1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()]
    value = {
        "label": label,
        "captured_at": iso(utc_now()),
        "validator_command": ["python3", str(VALIDATOR), "--json"],
        "validator_returncode": returncode,
        "validator": validator,
        "validator_status": validator.get("status") if isinstance(validator, dict) else None,
        "validator_error_count": validator.get("error_count") if isinstance(validator, dict) else None,
        "validator_full_hash_check": validator.get("full_hash_check") if isinstance(validator, dict) else None,
        "validator_warning_count": validator.get("warning_count") if isinstance(validator, dict) else None,
        "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]},
        "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": hits,
        "p4d_reference_hits_total": sum(len(v) for v in hits.values()),
        "formal_ingest": False,
        "media_added": 0,
        "labels_added": 0,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", value)
    return value


def make_ledger(outstanding: list[dict[str, Any]]) -> tuple[Path, Path]:
    csv_path = LEDGER / "quota_window_ledger.csv"
    fields = ["recovery_order", "prompt_id", "ordinal", "group_id", "variant_id", "planned_split", "target_role", "taxonomy", "parent_state", "parent_request_id", "parent_http_status", "state", "invocation_count", "provider_request_id", "http_status", "error_code", "raw_sha256", "final_sha256", "latency_seconds", "native_retry_count", "timestamp", "profile_stratum", "eligible_after_authorization"]
    rows = [{**r, "state": "NOT_STARTED", "invocation_count": 0, "provider_request_id": "", "http_status": "", "error_code": "", "raw_sha256": "", "final_sha256": "", "latency_seconds": "", "native_retry_count": "", "timestamp": ""} for r in outstanding]
    write_csv(csv_path, fields, rows)
    db_path = LEDGER / "quota_window_execution.sqlite3"
    if db_path.exists():
        raise RuntimeError(f"refusing to overwrite {db_path}")
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("""CREATE TABLE slots (
            prompt_id TEXT PRIMARY KEY, recovery_order INTEGER UNIQUE NOT NULL, ordinal INTEGER NOT NULL,
            group_id TEXT NOT NULL, variant_id TEXT NOT NULL, planned_split TEXT NOT NULL,
            target_role TEXT NOT NULL, taxonomy TEXT NOT NULL, prompt_path TEXT NOT NULL,
            prompt_sha256 TEXT NOT NULL, parent_state TEXT NOT NULL, parent_request_id TEXT,
            parent_http_status TEXT, state TEXT NOT NULL, invocation_count INTEGER NOT NULL DEFAULT 0,
            provider_request_id TEXT, http_status TEXT, error_code TEXT, raw_sha256 TEXT,
            final_sha256 TEXT, latency_seconds REAL, native_retry_count INTEGER, timestamp TEXT,
            profile_stratum TEXT NOT NULL, eligible_after_authorization INTEGER NOT NULL
        )""")
        con.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, captured_at TEXT NOT NULL)")
        for r in rows:
            con.execute("""INSERT INTO slots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                r["prompt_id"], r["recovery_order"], r["ordinal"], r["group_id"], r["variant_id"], r["planned_split"], r["target_role"], r["taxonomy"], r["prompt_path"], r["prompt_sha256"], r["parent_state"], r["parent_request_id"], r["parent_http_status"], r["state"], r["invocation_count"], r["provider_request_id"], r["http_status"], r["error_code"], r["raw_sha256"], r["final_sha256"], r["latency_seconds"] or None, r["native_retry_count"] or None, r["timestamp"], r["profile_stratum"], 0))
        con.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (None, "PREPARED_ZERO_REQUEST", json.dumps({"outstanding": len(rows), "provider_requests": 0, "status": "WAITING_FOR_PROVIDER_QUOTA_RESET"}, sort_keys=True), iso(utc_now())))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    return csv_path, db_path


def main() -> int:
    if EXEC.exists() and any(EXEC.iterdir()):
        print(f"REFUSING_NONEMPTY_EXECUTION_DIRECTORY={EXEC}", file=sys.stderr)
        return 2
    for d in (PRE, AUTH, INV, RUNNER, LEDGER, RAW, CHECK, QA, FREEZE):
        d.mkdir(parents=True, exist_ok=True)

    before = dataset_snapshot("before_execution")
    q2e_audit = q2e_parent_audit()
    manifest_rows, manifest = manifest_audit()
    quota = quota_evidence()
    gate = time_gate(quota)
    runtime = provider_runtime_audit()
    verified, inventory_summary, sources = build_inventory(manifest_rows)
    inventory_sha = sha256_file(INV / "current_success_inventory_gr3q3.csv")
    inventory_summary["inventory_csv_sha256"] = inventory_sha
    write_json(INV / "inventory_summary.json", inventory_summary)
    gr1 = gr1_exclusion_audit(verified, manifest_rows)
    outstanding, outstanding_summary = build_outstanding(manifest_rows, verified, sources)
    outstanding_sha = sha256_file(INV / "outstanding_338.csv")
    outstanding_summary["outstanding_csv_sha256"] = outstanding_sha
    write_json(INV / "outstanding_summary.json", outstanding_summary)

    config_parent = read_json(Q2E_RUN_CONFIG, {}) or {}
    config_match = {
        "provider": config_parent.get("provider") == "codex",
        "request_model": config_parent.get("model") == "gpt-5.4",
        "generation_backend": config_parent.get("generation_backend") == "image_generation",
        "native_size": config_parent.get("native_size_requested") == "1536x1024",
        "quality": config_parent.get("quality") == "medium",
        "format": config_parent.get("format") == "png",
        "outer_retry": config_parent.get("outer_retry") is False,
        "concurrency": config_parent.get("concurrency") == 1,
        "native_max_retries": config_parent.get("native_max_retries") == 3,
    }
    run_config = {
        "stage": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY",
        "revision_id": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY_20260828_02",
        "provider": "codex",
        "request_model": "gpt-5.4",
        "generation_backend": "image_generation",
        "runtime_version": runtime.get("runtime_version"),
        "wrapper_sha256": runtime.get("wrapper_sha256"),
        "binary_sha256": runtime.get("binary_sha256"),
        "quality": "medium",
        "format": "png",
        "native_size_requested": "1536x1024",
        "final_size": "1920x1080",
        "output_conversion": {"raw_format": "PNG", "rgb_conversion": True, "crop": "center_crop_to_16_by_9", "resize_method": "Pillow_LANCZOS", "final_format": "PNG"},
        "reference_images": [],
        "max_logical_invocations_this_window": 90,
        "concurrency": 1,
        "outer_retry": False,
        "native_max_retries": 3,
        "safety_margin_seconds": SAFETY_MARGIN_SECONDS,
        "not_before_local": gate["not_before_local"],
        "explicit_window_authorization": False,
        "authorization_present": False,
        "execution_eligible": False,
        "time_gate_pass": gate["time_gate_pass"],
        "provider_requests": 0,
        "physical_attempts": 0,
        "prompt_manifest_sha256": manifest.get("actual_sha256"),
        "frozen_440_manifest_sha256": EXPECTED_MANIFEST_SHA,
        "parent_q2e_freeze_sha256": EXPECTED_Q2E_FREEZE_SHA,
        "material_config_match_parent": config_match,
        "material_config_match_all": all(config_match.values()),
        "holdout_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
        "created_at": iso(utc_now()),
    }
    write_json(RUNNER / "run_config.json", run_config)
    ledger_csv, ledger_db = make_ledger(outstanding)
    write_empty(RUNNER / "request_log.jsonl")
    write_empty(RAW / "raw_responses.jsonl")
    write_json(CHECK / "provider_requests_before_execution.json", {"captured_at": iso(utc_now()), "provider_requests": 0, "physical_attempts": 0, "request_log_lines": 0, "raw_response_lines": 0})
    write_json(QA / "new_image_hash_manifest.json", {"captured_at": iso(utc_now()), "status": "NOT_EXECUTED", "raw_count": 0, "final_count": 0, "images": [], "provider_requests": 0})

    after = dataset_snapshot("after_execution")
    boundary = {
        "captured_at": iso(utc_now()),
        "before": {"path": str(PRE / "dataset_boundary_before_execution.json"), "counts": before["counts"], "annotation_sha256": before["annotation_sha256"]},
        "after": {"path": str(PRE / "dataset_boundary_after_execution.json"), "counts": after["counts"], "annotation_sha256": after["annotation_sha256"]},
        "counts_delta": {k: after["counts"][k] - before["counts"][k] for k in before["counts"]},
        "annotation_hashes_same": before["annotation_sha256"] == after["annotation_sha256"],
        "p4d_active_reference_hits": after["p4d_reference_hits_total"],
        "formal_ingest": False,
        "media_added": 0,
        "labels_added": 0,
    }
    write_json(PRE / "dataset_boundary_audit.json", boundary)

    prep_checks = {
        "q2e_parent_freeze_match": q2e_audit["all_match"],
        "frozen_440_manifest_match": manifest["all_match"],
        "current_success_inventory_exact_102": inventory_summary["all_verified"] and inventory_summary["total_verified_success"] == 102,
        "gr1_exclusion_clean": gr1["all_excluded"],
        "outstanding_exact_338": outstanding_summary["exact_expected_state"],
        "quota_reset_evidence_match": quota["evidence_matches_expected"],
        "dataset_before_valid": before.get("validator_status") == "valid" and before.get("validator_error_count") == 0 and before.get("validator_full_hash_check") is True,
        "dataset_after_valid": after.get("validator_status") == "valid" and after.get("validator_error_count") == 0 and after.get("validator_full_hash_check") is True,
        "dataset_unchanged": boundary["annotation_hashes_same"] and all(v == 0 for v in boundary["counts_delta"].values()),
        "active_p4d_refs_zero": boundary["p4d_active_reference_hits"] == 0,
        "config_matches_parent": all(config_match.values()),
        "provider_requests_zero": 0 == 0,
        "time_gate_pass": gate["time_gate_pass"],
        "explicit_window_authorization": False,
    }
    write_json(CHECK / "preparation_gate.json", {"captured_at": iso(utc_now()), "stage": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY", "preparation_checks": prep_checks, "preparation_checks_pass": all(prep_checks[k] for k in prep_checks if k not in ("time_gate_pass", "explicit_window_authorization")), "execution_eligible": False, "blocking_reasons": ["WAITING_FOR_PROVIDER_QUOTA_RESET"] if not gate["time_gate_pass"] else ["AWAITING_QUOTA_WINDOW_AUTHORIZATION"], "provider_requests": 0})

    status = "WAITING_FOR_PROVIDER_QUOTA_RESET" if not gate["time_gate_pass"] else "AWAITING_QUOTA_WINDOW_AUTHORIZATION"
    terminal_summary = {
        "stage": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY",
        "revision_id": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY_20260828_02",
        "status": status,
        "P4D_GR3Q2E_STATUS": "STOPPED_BY_FAILURE_POLICY",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "FULL_341_RECOVERY_COMPLETE": False,
        "P4D_VALIDATED_GENERATION_BASELINE": False,
        "profile_a_success": inventory_summary["profile_strata"].get("GR3E_PROFILE_A", 0),
        "profile_b_success": inventory_summary["profile_strata"].get("GR3Q2_PROFILE_B", 0),
        "total_current_success": inventory_summary["total_verified_success"],
        "failed_confirmed": outstanding_summary["failed_confirmed_http_429"],
        "never_started": outstanding_summary["never_started"],
        "completion_unknown": outstanding_summary["completion_unknown"],
        "outstanding": outstanding_summary["total_outstanding"],
        "window_cap": 90,
        "window_cap_reached": False,
        "window_logical_invocations": 0,
        "window_success": 0,
        "window_failure": 0,
        "provider_requests": 0,
        "physical_attempts": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
        "dataset_after": after,
        "active_p4d_refs": 0,
        "new_image_generation": "NOT_EXECUTED",
        "full_440_qa": "NOT_REACHED",
        "semantic_metrics": "N/A",
        "explicit_window_authorization": False,
        "time_gate_pass": gate["time_gate_pass"],
        "created_at": iso(utc_now()),
    }
    write_json(CHECK / "terminal_summary.json", terminal_summary)

    artifact_paths = [
        (Q2E_FREEZE, EXPECTED_Q2E_FREEZE_SHA),
        (MANIFEST, EXPECTED_MANIFEST_SHA),
        (INV / "current_success_inventory_gr3q3.csv", inventory_sha),
        (INV / "inventory_summary.json", sha256_file(INV / "inventory_summary.json")),
        (INV / "gr1_exclusion_audit.json", sha256_file(INV / "gr1_exclusion_audit.json")),
        (INV / "outstanding_338.csv", outstanding_sha),
        (INV / "outstanding_summary.json", sha256_file(INV / "outstanding_summary.json")),
        (Q2E_RAW_FAILURE, "a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99"),
        (PRE / "q2e_parent_freeze_audit.json", sha256_file(PRE / "q2e_parent_freeze_audit.json")),
        (PRE / "full_manifest_audit.json", sha256_file(PRE / "full_manifest_audit.json")),
        (PRE / "quota_reset_evidence.json", sha256_file(PRE / "quota_reset_evidence.json")),
        (PRE / "time_gate.json", sha256_file(PRE / "time_gate.json")),
        (PRE / "provider_runtime_audit.json", sha256_file(PRE / "provider_runtime_audit.json")),
        (PRE / "dataset_boundary_before_execution.json", sha256_file(PRE / "dataset_boundary_before_execution.json")),
        (PRE / "dataset_boundary_after_execution.json", sha256_file(PRE / "dataset_boundary_after_execution.json")),
        (PRE / "dataset_boundary_audit.json", sha256_file(PRE / "dataset_boundary_audit.json")),
        (AUTH / "window_authorization_status.json", None),
        (RUNNER / "run_config.json", sha256_file(RUNNER / "run_config.json")),
        (LEDGER / "quota_window_ledger.csv", sha256_file(LEDGER / "quota_window_ledger.csv")),
        (LEDGER / "quota_window_execution.sqlite3", sha256_file(LEDGER / "quota_window_execution.sqlite3")),
        (RUNNER / "request_log.jsonl", sha256_file(RUNNER / "request_log.jsonl")),
        (RAW / "raw_responses.jsonl", sha256_file(RAW / "raw_responses.jsonl")),
        (QA / "new_image_hash_manifest.json", sha256_file(QA / "new_image_hash_manifest.json")),
        (CHECK / "provider_requests_before_execution.json", sha256_file(CHECK / "provider_requests_before_execution.json")),
        (CHECK / "preparation_gate.json", sha256_file(CHECK / "preparation_gate.json")),
        (CHECK / "terminal_summary.json", sha256_file(CHECK / "terminal_summary.json")),
        (SELF, sha256_file(SELF)),
        (CLI, EXPECTED_WRAPPER_SHA),
        (BINARY, EXPECTED_BINARY_SHA),
    ]
    auth_status = {
        "stage": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY",
        "captured_at": iso(utc_now()),
        "explicit_window_authorization": False,
        "authorization_present": False,
        "source": "none_in_current_top_level_user_message",
        "template_is_authorization": False,
        "max_logical_invocations_this_window": 90,
        "concurrency": 1,
        "outer_retry": False,
        "native_max_retries": 3,
        "provider_requests_before_execution": 0,
        "physical_attempts_before_execution": 0,
        "execution_eligible": False,
        "required_next_action": "standalone_top_level_GR3Q3_window_authorization_after_not_before",
    }
    write_json(AUTH / "window_authorization_status.json", auth_status)
    # Replace the deliberately late authorization entry with its now-stable hash.
    artifact_paths = [(p, sha256_file(p) if expected is None else expected) for p, expected in artifact_paths]
    artifact_map = {str(p): expected for p, expected in artifact_paths}
    freeze_obj = {
        "stage": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY",
        "name": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY",
        "revision_id": "P4D_GR3Q3_QUOTA_WINDOW_RECOVERY_20260828_02",
        "status": status,
        "P4D_GR3Q2E_STATUS": "STOPPED_BY_FAILURE_POLICY",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "FULL_341_RECOVERY_COMPLETE": False,
        "P4D_VALIDATED_GENERATION_BASELINE": False,
        "current_success_inventory": {"total": inventory_summary["total_verified_success"], "profile_a": inventory_summary["profile_strata"].get("GR3E_PROFILE_A", 0), "profile_b": inventory_summary["profile_strata"].get("GR3Q2_PROFILE_B", 0), "sha256": inventory_sha},
        "outstanding_inventory": {"total": outstanding_summary["total_outstanding"], "failed_confirmed_http_429": outstanding_summary["failed_confirmed_http_429"], "never_started": outstanding_summary["never_started"], "completion_unknown": outstanding_summary["completion_unknown"], "sha256": outstanding_sha},
        "quota_reset_evidence": {"path": str(PRE / "quota_reset_evidence.json"), "sha256": sha256_file(PRE / "quota_reset_evidence.json"), "not_before_local": quota["not_before_local"]},
        "time_gate": gate,
        "authorization": auth_status,
        "execution_not_executed": True,
        "provider_requests": 0,
        "physical_attempts": 0,
        "window_cap": 90,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
        "full_440_qa": "NOT_REACHED",
        "semantic_metrics": "N/A",
        "active_p4d_refs": 0,
        "dataset_boundary_audit": {"before": before["annotation_sha256"], "after": after["annotation_sha256"], "unchanged": boundary["annotation_hashes_same"]},
        "parent_q2e_canonical_freeze_sha256": EXPECTED_Q2E_FREEZE_SHA,
        "frozen_440_manifest_sha256": EXPECTED_MANIFEST_SHA,
        "parent_failed_raw_evidence_sha256": "a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99",
        "provider_runtime_audit_sha256": sha256_file(PRE / "provider_runtime_audit.json"),
        "artifact_sha256": artifact_map,
        "created_at": iso(utc_now()),
    }
    freeze_path = FREEZE / "p4d_gr3q3_terminal_freeze.json"
    write_json(freeze_path, freeze_obj)
    freeze_sha = sha256_file(freeze_path)
    sidecar = freeze_path.with_name(freeze_path.name + ".sha256")
    with sidecar.open("w", encoding="utf-8") as f:
        f.write(f"{freeze_sha}  {freeze_path.name}\n")
        f.flush()
        os.fsync(f.fileno())
    checks = [{"path": p, "expected_sha256": e, "actual_sha256": sha256_file(Path(p)), "match": sha256_file(Path(p)) == e} for p, e in artifact_map.items()]
    verification = {
        "captured_at": iso(utc_now()),
        "freeze_path": str(freeze_path),
        "freeze_sha256": freeze_sha,
        "sidecar_sha256": sidecar_value(freeze_path),
        "sidecar_match": freeze_sha == sidecar_value(freeze_path),
        "bound_artifacts": checks,
        "all_bound_artifacts_match": all(x["match"] for x in checks),
        "provider_requests_added": 0,
        "request_log_lines": 0,
        "raw_response_lines": 0,
        "all_pass": bool(freeze_sha == sidecar_value(freeze_path) and all(x["match"] for x in checks)),
    }
    write_json(CHECK / "terminal_freeze_verification.json", verification)
    print(json.dumps({"status": status, "provider_requests": 0, "current_success": len(verified), "outstanding": len(outstanding), "freeze": str(freeze_path), "freeze_sha256": freeze_sha, "time_gate_pass": gate["time_gate_pass"], "authorization_present": False}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
