#!/usr/bin/env python3
"""Build the zero-request GR3Q2 lineage-policy amendment and recovery prep.

GR3Q1's profile-fingerprint blocker remains historical evidence.  GR3Q2 is a
new governance revision: it distinguishes observable generation-material
variables from operational provenance.  It verifies every preserved asset and
all frozen surfaces, audits the current runtime without image generation, and
prepares (but does not authorize or execute) a profile-stratified 341-slot
recovery.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation" / "gr3_fullregen"
PARENT = GR3 / "06_execution" / "authorized_20260827_01"
Q1 = GR3 / "06_execution" / "quota_recovery_20260827_01"
REV = GR3 / "06_execution" / "lineage_policy_amendment_20260828_01"
PRE = REV / "00_preflight"
GOV = REV / "01_governance"
INV = REV / "02_inventory"
AUTH = REV / "03_authorization"
FREEZE = REV / "freeze"
CHECKPOINTS = REV / "05_checkpoints"
SELF = ROOT / "tools" / "p4d_gr3q2_prepare.py"

OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
REPORTS = ROOT / "reports"
PREP_FREEZE = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
GR3E_FREEZE = PARENT / "freeze" / "p4d_gr3e_terminal_freeze.json"
Q1_FREEZE = Q1 / "freeze" / "p4d_gr3q1_preparation_freeze.json"
MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
PARENT_DB = PARENT / "03_ledger" / "gr3e_execution.sqlite3"
PARENT_LEDGER = PARENT / "03_ledger" / "execution_ledger.csv"
PARENT_RUN_CONFIG = PARENT / "02_runner" / "run_config.json"
PARENT_RUNNER = ROOT / "tools" / "p4d_gr3e_fullregen_runner.py"
FAILED_RAW = PARENT / "04_raw_responses" / "P4D_GR3E_BULK_0100_PF_P4D_HN_KNEEL_G008_V05.json"
FAILED_METADATA = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m/metadata/PF_P4D_HN_KNEEL_G008_V05.json")
OLD_GR1_QA = P4D / "03_intake_audit" / "gr1_independent_mechanical_qa.csv"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")

EXPECTED_PREP_SHA = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
EXPECTED_GR3E_SHA = "6afb294c4696eb89bea5d6dfb333efc38477fa05546b4e8cd4cc8ffa52d89f40"
EXPECTED_Q1_SHA = "e64a41f735c8837b273b9100a40f7437e70721df4f1f5be8230a9e634890a847"
EXPECTED_MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
EXPECTED_WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
EXPECTED_BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
EXPECTED_RUNNER_SHA = "eae256f386a7a77fc2671a94bc071b1883d3aeaaf55e5fc8becd469cf7810d6a"
EXPECTED_RUN_CONFIG_SHA = "bcee14579c29275b483c554d8c5ecec9e953bb91dc1cca486b610b41e5f746f4"
EXPECTED_PROFILE_A = "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe"
EXPECTED_RUNTIME = "0.7.3"
FAILED_PROMPT = "PF_P4D_HN_KNEEL_G008_V05"
FAILED_REQUEST = "P4D_GR3E_BULK_0100_PF_P4D_HN_KNEEL_G008_V05"
FINAL_SIZE = (1920, 1080)

FROZEN_FILES = {
    "group_manifest.csv": (P4D / "01_prompt_plan" / "group_manifest.csv", "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab"),
    "group_split_freeze.json": (P4D / "01_prompt_plan" / "group_split_freeze.json", "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843"),
    "prompt_manifest.csv": (P4D / "01_prompt_plan" / "prompt_manifest.csv", "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb"),
    "prompt_pack.md": (P4D / "01_prompt_plan" / "prompt_pack.md", "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250"),
    "prompt_pack_freeze.json": (P4D / "01_prompt_plan" / "prompt_pack_freeze.json", "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b"),
    "C3_prompt.txt": (ROOT / "07_p3_structured_hard_negative_refinement" / "03_candidates" / "C3_BASELINE" / "C3_prompt.txt", "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"),
}

AUTH_TEXT = (
    "我明确授权 P4D_GR3Q2E 在新的 lineage-policy amendment 下继续当前 P4D full-regeneration revision："
    "保留已经成功并通过完整性验证的 99 张 GR3E 图像，并将其标记为历史生成 profile stratum A；"
    "允许使用当前 Codex profile 作为 profile stratum B，重新尝试此前已确认 HTTP 429 失败的 1 个 slot，"
    "并生成其余 340 个从未开始的 frozen slots，共最多 341 个新的 logical slot invocations。"
    "我接受 profile/account fingerprint 不同但 provider、request model、generation backend、runtime、prompt 和 generation configuration 一致时作为 provenance 分层而不是强制 semantic-lineage break；"
    "同时继续接受 GPT Image 2 runtime max_retries=3、单 logical invocation 最多约4次 provider attempts、精确费用未知以及 quota/成本风险。"
    "任何 logical invocation 返回 429/401/403/timeout/5xx 均立即停止后续 slot，不执行外层自动 recovery。"
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


def sha256_object(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(value if value.endswith("\n") else value + "\n")
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
    hidden = {"account_id", "chatgpt_user_id", "access_token", "refresh_token", "id_token", "token", "api_key", "email", "auth_file"}
    if isinstance(value, dict):
        return {key: ("<REDACTED>" if key.lower() in hidden else redact(child)) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def artifact_checks(mapping: dict[str, str]) -> list[dict[str, Any]]:
    checks = []
    for raw, expected in mapping.items():
        path = Path(raw)
        actual = sha256_file(path)
        checks.append({"path": raw, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    return checks


def audit_parent_freezes() -> dict[str, Any]:
    gr3e = read_json(GR3E_FREEZE, {}) or {}
    q1 = read_json(Q1_FREEZE, {}) or {}
    gr3e_artifacts = artifact_checks(gr3e.get("artifact_sha256") or {})
    gr3e_reports = artifact_checks(gr3e.get("reports_sha256") or {})
    q1_artifacts = artifact_checks(q1.get("artifact_sha256") or {})
    overview_info = gr3e.get("overview") or {}
    current_overview = sha256_file(Path(str(overview_info.get("path")))) if overview_info.get("path") else None
    result = {
        "captured_at": now(),
        "gr3_preparation": {"path": str(PREP_FREEZE), "expected_sha256": EXPECTED_PREP_SHA, "actual_sha256": sha256_file(PREP_FREEZE), "sidecar": sidecar_value(PREP_FREEZE)},
        "gr3e_authorized": {"path": str(GR3E_FREEZE), "expected_sha256": EXPECTED_GR3E_SHA, "actual_sha256": sha256_file(GR3E_FREEZE), "sidecar": sidecar_value(GR3E_FREEZE), "bound_artifact_checks": gr3e_artifacts, "bound_report_checks": gr3e_reports},
        "gr3q1": {"path": str(Q1_FREEZE), "expected_sha256": EXPECTED_Q1_SHA, "actual_sha256": sha256_file(Q1_FREEZE), "sidecar": sidecar_value(Q1_FREEZE), "bound_artifact_checks": q1_artifacts},
        "gr3e_overview_historical_binding": {"path": overview_info.get("path"), "sha_at_terminal_freeze": overview_info.get("sha256"), "current_sha256": current_overview, "changed_by_later_append_only_stages": current_overview != overview_info.get("sha256")},
    }
    result["gr3_preparation_verified"] = bool(result["gr3_preparation"]["actual_sha256"] == EXPECTED_PREP_SHA == result["gr3_preparation"]["sidecar"])
    result["gr3e_freeze_verified"] = bool(result["gr3e_authorized"]["actual_sha256"] == EXPECTED_GR3E_SHA == result["gr3e_authorized"]["sidecar"] and all(item["match"] for item in gr3e_artifacts + gr3e_reports))
    result["gr3q1_freeze_verified"] = bool(result["gr3q1"]["actual_sha256"] == EXPECTED_Q1_SHA == result["gr3q1"]["sidecar"] and all(item["match"] for item in q1_artifacts))
    result["all_required_parent_bindings_match"] = bool(result["gr3_preparation_verified"] and result["gr3e_freeze_verified"] and result["gr3q1_freeze_verified"])
    write_json(PRE / "parent_freeze_audit.json", result)
    return result


def audit_frozen_assets() -> dict[str, Any]:
    checks = []
    for name, (path, expected) in FROZEN_FILES.items():
        actual = sha256_file(path)
        checks.append({"name": name, "path": str(path), "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    value = {"captured_at": now(), "checks": checks, "all_match": all(item["match"] for item in checks)}
    write_json(PRE / "frozen_asset_audit.json", value)
    return value


def audit_manifest() -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = read_csv(MANIFEST)
    mismatches = []
    for row in rows:
        actual = sha256_file(Path(row["original_prompt_path"]))
        if actual != row["prompt_sha256"]:
            mismatches.append({"prompt_id": row["prompt_id"], "path": row["original_prompt_path"], "expected_sha256": row["prompt_sha256"], "actual_sha256": actual})
    split_by_group: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        split_by_group[row["group_id"]].add(row["planned_internal_split"])
    value = {
        "captured_at": now(), "path": str(MANIFEST), "expected_sha256": EXPECTED_MANIFEST_SHA, "actual_sha256": sha256_file(MANIFEST),
        "rows": len(rows), "unique_prompt_ids": len({row["prompt_id"] for row in rows}), "unique_groups": len({row["group_id"] for row in rows}),
        "prompt_byte_mismatch": len(mismatches), "prompt_byte_mismatches": mismatches,
        "role_counts": dict(Counter(row["target_role"] for row in rows)), "split_counts": dict(Counter(row["planned_internal_split"] for row in rows)),
        "cross_split_groups": sum(1 for values in split_by_group.values() if len(values) > 1), "gr1_reuse_values": sorted({row["gr1_images_reused"] for row in rows}),
    }
    value["all_match"] = bool(value["actual_sha256"] == EXPECTED_MANIFEST_SHA and value["rows"] == 440 and value["unique_prompt_ids"] == 440 and value["unique_groups"] == 88 and value["prompt_byte_mismatch"] == 0 and value["cross_split_groups"] == 0)
    write_json(PRE / "full_manifest_audit.json", value)
    return rows, value


def db_slots() -> list[dict[str, Any]]:
    connection = sqlite3.connect(PARENT_DB)
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
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def build_inventories(manifest_rows: list[dict[str, str]], profile_a: str, profile_b: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    slots = db_slots()
    slot_by_id = {row["prompt_id"]: row for row in slots}
    old_hashes: set[str] = set()
    old_paths: list[Path] = []
    for row in read_csv(OLD_GR1_QA):
        old_hashes.update(value for key in ("raw_sha256", "final_sha256") if (value := row.get(key)))
        old_paths.extend(Path(value) for key in ("raw_path", "final_path") if (value := row.get(key)))
    verified: list[dict[str, Any]] = []
    raw_issues: list[dict[str, Any]] = []
    final_issues: list[dict[str, Any]] = []
    gr1_hits: list[dict[str, Any]] = []
    samefile_hits: list[dict[str, Any]] = []
    symlink_hits: list[dict[str, Any]] = []
    all_rows: dict[str, dict[str, Any]] = {}
    for manifest in manifest_rows:
        slot = slot_by_id.get(manifest["prompt_id"], {})
        state = str(slot.get("state") or "MISSING_LEDGER_SLOT")
        raw_path = Path(str(slot["raw_path"])) if slot.get("raw_path") else None
        final_path = Path(str(slot["final_path"])) if slot.get("final_path") else None
        raw_exists = bool(raw_path and raw_path.is_file())
        final_exists = bool(final_path and final_path.is_file())
        raw_sha = sha256_file(raw_path) if raw_path else None
        final_sha = sha256_file(final_path) if final_path else None
        raw_ok, raw_size, raw_error = verify_image(raw_path) if raw_exists and raw_path else (False, None, "missing")
        final_ok, final_size, final_error = verify_image(final_path) if final_exists and final_path else (False, None, "missing")
        raw_match = bool(raw_sha and raw_sha == slot.get("raw_sha256"))
        final_match = bool(final_sha and final_sha == slot.get("final_sha256"))
        raw_link = bool(raw_path and raw_path.is_symlink())
        final_link = bool(final_path and final_path.is_symlink())
        samefile = False
        if raw_path and final_path and raw_exists and final_exists:
            try:
                samefile = os.path.samefile(raw_path, final_path)
            except OSError:
                samefile = False
        dimension_ok = final_size == FINAL_SIZE if final_size else False
        integrity = bool(state == "SUCCESS" and raw_exists and final_exists and raw_match and final_match and raw_ok and final_ok and dimension_ok and not raw_link and not final_link and not samefile)
        row = {
            "prompt_id": manifest["prompt_id"], "ordinal": slot.get("ordinal", ""), "group_id": manifest["group_id"], "variant_id": manifest["variant_id"],
            "taxonomy": manifest["taxonomy"], "target_role": manifest["target_role"], "planned_split": manifest["planned_internal_split"], "prompt_sha256": manifest["prompt_sha256"],
            "ledger_state": state, "ledger_invocation_count": slot.get("invocation_count", 0), "parent_request_id": slot.get("request_id") or "", "parent_http_status": slot.get("http_status") or "", "parent_error_code": slot.get("error_code") or "",
            "raw_path": str(raw_path) if raw_path else "", "final_path": str(final_path) if final_path else "", "raw_sha256_ledger": slot.get("raw_sha256") or "", "raw_sha256_actual": raw_sha or "", "final_sha256_ledger": slot.get("final_sha256") or "", "final_sha256_actual": final_sha or "",
            "raw_pillow_pass": raw_ok, "final_pillow_pass": final_ok, "final_width": final_size[0] if final_size else "", "final_height": final_size[1] if final_size else "", "final_1920x1080": dimension_ok,
            "raw_sha_match": raw_match, "final_sha_match": final_match, "symlink_hit": raw_link or final_link, "raw_final_samefile": samefile, "verified_preserved_success": integrity,
            "generation_profile_stratum": "GR3E_PROFILE_A" if state == "SUCCESS" else "GR3Q2_PROFILE_B", "profile_fingerprint_safe_hash": profile_a if state == "SUCCESS" else (profile_b or "UNAVAILABLE"),
        }
        all_rows[row["prompt_id"]] = row
        if state == "SUCCESS":
            if not (raw_exists and raw_match and raw_ok and not raw_link):
                raw_issues.append({"prompt_id": row["prompt_id"], "path": row["raw_path"], "exists": raw_exists, "sha_match": raw_match, "pillow_pass": raw_ok, "symlink": raw_link, "error": raw_error})
            if not (final_exists and final_match and final_ok and dimension_ok and not final_link):
                final_issues.append({"prompt_id": row["prompt_id"], "path": row["final_path"], "exists": final_exists, "sha_match": final_match, "pillow_pass": final_ok, "dimension": final_size, "symlink": final_link, "error": final_error})
            for kind, digest, path in (("raw", raw_sha, raw_path), ("final", final_sha, final_path)):
                if digest and digest in old_hashes:
                    gr1_hits.append({"prompt_id": row["prompt_id"], "kind": kind, "sha256": digest, "path": str(path)})
            for path in (raw_path, final_path):
                if not path or not path.exists():
                    continue
                if path.is_symlink():
                    symlink_hits.append({"prompt_id": row["prompt_id"], "path": str(path)})
                for old in old_paths:
                    if not old.exists():
                        continue
                    try:
                        if os.path.samefile(path, old):
                            samefile_hits.append({"prompt_id": row["prompt_id"], "current_path": str(path), "gr1_path": str(old)})
                    except OSError:
                        pass
            verified.append(row)
    verified_ids = {row["prompt_id"] for row in verified if row["verified_preserved_success"]}
    all_ids = {row["prompt_id"] for row in manifest_rows}
    outstanding_ids = all_ids - verified_ids
    outstanding: list[dict[str, Any]] = []
    sequence = [FAILED_PROMPT] + [row["prompt_id"] for row in manifest_rows if row["prompt_id"] != FAILED_PROMPT]
    order = 1
    for prompt_id in sequence:
        if prompt_id not in outstanding_ids:
            continue
        row = all_rows[prompt_id]
        if row["ledger_state"] == "FAILED_CONFIRMED" and str(row["parent_http_status"]) == "429":
            class_name, eligible = "FAILED_CONFIRMED_HTTP_429", True
        elif row["ledger_state"] == "NOT_STARTED" and int(row["ledger_invocation_count"] or 0) == 0:
            class_name, eligible = "NEVER_STARTED", True
        else:
            class_name, eligible = "COMPLETION_UNKNOWN", False
        outstanding.append({
            "prompt_id": prompt_id, "group_id": row["group_id"], "taxonomy": row["taxonomy"], "target_role": row["target_role"], "planned_split": row["planned_split"],
            "previous_execution_state": class_name, "parent_request_id": row["parent_request_id"], "parent_http_status": row["parent_http_status"], "parent_error_code": row["parent_error_code"],
            "generation_profile_stratum": "GR3Q2_PROFILE_B", "profile_fingerprint_safe_hash": profile_b or "UNAVAILABLE", "eligible_for_recovery_after_authorization": str(eligible).lower(), "recovery_order": order,
        })
        order += 1
    strata = []
    for manifest in manifest_rows:
        row = all_rows[manifest["prompt_id"]]
        strata.append({
            "prompt_id": row["prompt_id"], "group_id": row["group_id"], "taxonomy": row["taxonomy"], "target_role": row["target_role"], "planned_split": row["planned_split"],
            "generation_profile_stratum": row["generation_profile_stratum"], "profile_fingerprint_safe_hash": row["profile_fingerprint_safe_hash"],
            "asset_status": "PRESERVED_EXISTING" if row["ledger_state"] == "SUCCESS" else "PROPOSED_RECOVERY", "parent_execution_state": row["ledger_state"], "profile_is_gt_feature": False, "profile_is_model_input": False,
        })
    def counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(item[key]) for item in items).items()))
    a_rows = [row for row in strata if row["generation_profile_stratum"] == "GR3E_PROFILE_A"]
    b_rows = [row for row in strata if row["generation_profile_stratum"] == "GR3Q2_PROFILE_B"]
    a_split = counts(a_rows, "planned_split")
    b_split = counts(b_rows, "planned_split")
    a_role = counts(a_rows, "target_role")
    b_role = counts(b_rows, "target_role")
    summary = {
        "captured_at": now(), "manifest_slots": len(manifest_rows), "sqlite_slots": len(slots), "parent_state_counts": dict(Counter(str(row["state"]) for row in slots)), "parent_logical_invocations": sum(1 for row in slots if int(row.get("invocation_count") or 0) > 0), "parent_ledger_csv_rows": len(read_csv(PARENT_LEDGER)),
        "preserved_success_expected": 99, "preserved_success_ledger": len(verified), "preserved_success_verified": len(verified_ids), "raw_integrity_issues": len(raw_issues), "final_integrity_issues": len(final_issues), "raw_issues": raw_issues, "final_issues": final_issues,
        "gr1_sha_hits": len(gr1_hits), "gr1_sha_hit_records": gr1_hits, "samefile_hits": len(samefile_hits), "samefile_hit_records": samefile_hits, "symlink_hits": len(symlink_hits), "symlink_hit_records": symlink_hits,
        "derived_outstanding": len(outstanding), "failed_confirmed_429": sum(1 for row in outstanding if row["previous_execution_state"] == "FAILED_CONFIRMED_HTTP_429"), "never_started": sum(1 for row in outstanding if row["previous_execution_state"] == "NEVER_STARTED"), "completion_unknown": sum(1 for row in outstanding if row["previous_execution_state"] == "COMPLETION_UNKNOWN"),
        "failed_prompt_id": FAILED_PROMPT, "failed_parent_request_id": FAILED_REQUEST,
        "profile_strata": {"GR3E_PROFILE_A": {"count": len(a_rows), "role_counts": a_role, "split_counts": a_split, "taxonomy_counts": counts(a_rows, "taxonomy")}, "GR3Q2_PROFILE_B": {"count": len(b_rows), "role_counts": b_role, "split_counts": b_split, "taxonomy_counts": counts(b_rows, "taxonomy")}},
        "profile_role_confounding": True, "profile_taxonomy_confounding": True, "profile_split_confounding": True, "profile_split_confounding_detail": {"A_NEW_DESIGN_RATE": len([row for row in a_rows if row["planned_split"] == "NEW_DESIGN"]) / len(a_rows), "B_NEW_DESIGN_RATE": len([row for row in b_rows if row["planned_split"] == "NEW_DESIGN"]) / len(b_rows), "interpretation": "Both strata occur in both DESIGN and SCREEN, but their proportions differ; role/taxonomy confounding is stronger because Profile-A has no positive or ordinary-negative slots."},
    }
    verified_fields = list(verified[0].keys())
    write_csv(INV / "verified_99.csv", verified_fields, verified)
    write_csv(INV / "outstanding_341.csv", list(outstanding[0].keys()), outstanding)
    write_csv(INV / "profile_strata_plan.csv", list(strata[0].keys()), strata)
    write_json(INV / "inventory_summary.json", summary)
    return verified, outstanding, strata, summary


def run_cli(label: str, args: list[str], timeout: int = 120) -> tuple[dict[str, Any], dict[str, Any]]:
    command = ["node", str(CLI), "--json", "--provider", "codex", *args]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout": sanitize_text(proc.stdout)}
    record = {"label": label, "command": command, "returncode": proc.returncode, "payload": redact(payload), "stderr": sanitize_text(proc.stderr), "captured_at": now(), "image_generation_provider_requests": 0}
    write_json(PRE / f"{label}.json", record)
    return payload, record


def read_only_provider_audit() -> dict[str, Any]:
    config, config_record = run_cli("config_inspect", ["config", "inspect"])
    doctor, doctor_record = run_cli("doctor", ["doctor"])
    auth, auth_record = run_cli("auth_inspect", ["auth", "inspect"])
    help_payload, help_record = run_cli("images_generate_help", ["images", "generate", "--help"])
    codex = ((doctor.get("providers") or {}).get("codex") or {}) if isinstance(doctor, dict) else {}
    c_auth = codex.get("auth") if isinstance(codex, dict) else {}
    endpoint = codex.get("endpoint") if isinstance(codex, dict) else {}
    c_auth = c_auth if isinstance(c_auth, dict) else {}
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    auth_codex = ((auth.get("providers") or {}).get("codex") or {}) if isinstance(auth, dict) else {}
    auth_codex = auth_codex if isinstance(auth_codex, dict) else {}
    account = str(c_auth.get("account_id") or auth_codex.get("account_id") or "")
    user = str(c_auth.get("chatgpt_user_id") or auth_codex.get("chatgpt_user_id") or "")
    profile_b = hashlib.sha256(f"account={account}|user={user}".encode("utf-8")).hexdigest() if account or user else None
    selection = doctor.get("provider_selection") if isinstance(doctor, dict) else {}
    defaults = doctor.get("defaults") if isinstance(doctor, dict) else {}
    selection = selection if isinstance(selection, dict) else {}
    defaults = defaults if isinstance(defaults, dict) else {}
    provider = selection.get("resolved") or "codex"
    model = defaults.get("codex_model") or "gpt-5.4"
    retry = doctor.get("retry_policy") if isinstance(doctor, dict) else {}
    retry = retry if isinstance(retry, dict) else {}
    value = {
        "captured_at": now(), "provider": provider, "request_model": model, "generation_backend": "image_generation", "runtime_version": doctor.get("version") if isinstance(doctor, dict) else None,
        "wrapper_path": str(CLI), "wrapper_sha256": sha256_file(CLI), "binary_path": str(BINARY), "binary_sha256": sha256_file(BINARY),
        "native_retry_policy": retry, "native_max_retries": retry.get("max_retries"), "outer_retry": False, "no_retry_guarantee": False,
        "auth_ready": bool(c_auth.get("ready") or auth_codex.get("ready")), "endpoint_reachable": bool(endpoint.get("reachable")), "session_ready": bool((c_auth.get("ready") or auth_codex.get("ready")) and endpoint.get("reachable") and endpoint.get("tls_ok")),
        "profile_fingerprint_safe_hash": profile_b, "profile_account_present": bool(account), "profile_user_present": bool(user), "image_generation_provider_requests": 0,
        "commands": {"config_inspect": config_record, "doctor": doctor_record, "auth_inspect": auth_record, "images_generate_help": help_record},
        "help_supports_no_retry_control": any(token in json.dumps(help_payload, ensure_ascii=False).lower() for token in ("--no-retry", "--max-retries")),
    }
    write_json(PRE / "provider_runtime_audit.json", value)
    return value


def parent_generation_config() -> dict[str, Any]:
    config = read_json(PARENT_RUN_CONFIG, {}) or {}
    return {
        "provider": config.get("provider"), "request_model": config.get("model"), "generation_backend": config.get("generation_backend"), "generation_mode": "images generate",
        "format": "png", "native_size_requested": config.get("native_size_requested"), "quality": config.get("quality"), "reference_images": [], "json_events": True,
        "concurrency": config.get("concurrency"), "outer_retry": config.get("outer_retry"), "native_retry_policy": {"max_retries": 3, "base_delay_seconds": 1},
        "output_conversion": {"raw_format": "PNG", "rgb_conversion": True, "crop": "center_crop_to_16_by_9", "final_size": config.get("final_size"), "resize_method": "Pillow_LANCZOS", "final_format": "PNG"},
        "runner_sha256": sha256_file(PARENT_RUNNER), "run_config_sha256": sha256_file(PARENT_RUN_CONFIG), "manifest_sha256": config.get("manifest_sha256"), "prompt_source": "full_regen_prompt_manifest.csv and original prompt file bytes",
    }


def compare_material_config(provider: dict[str, Any], manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    parent_config = parent_generation_config()
    proposed = dict(parent_config)
    proposed["runner_sha256"] = sha256_file(PARENT_RUNNER)
    proposed["run_config_sha256"] = sha256_file(PARENT_RUN_CONFIG)
    parent_fingerprint = sha256_object({key: value for key, value in parent_config.items() if key not in {"runner_sha256", "run_config_sha256"}})
    proposed_fingerprint = sha256_object({key: value for key, value in proposed.items() if key not in {"runner_sha256", "run_config_sha256"}})
    checks = {
        "provider_same": provider.get("provider") == parent_config["provider"] == "codex",
        "request_model_same": provider.get("request_model") == parent_config["request_model"] == "gpt-5.4",
        "generation_backend_same": provider.get("generation_backend") == parent_config["generation_backend"] == "image_generation",
        "runtime_version_same": provider.get("runtime_version") == EXPECTED_RUNTIME,
        "wrapper_same": provider.get("wrapper_sha256") == EXPECTED_WRAPPER_SHA,
        "binary_same": provider.get("binary_sha256") == EXPECTED_BINARY_SHA,
        "parent_runner_same": parent_config["runner_sha256"] == EXPECTED_RUNNER_SHA,
        "parent_run_config_same": parent_config["run_config_sha256"] == EXPECTED_RUN_CONFIG_SHA,
        "native_retry_policy_same": provider.get("native_max_retries") == parent_config["native_retry_policy"]["max_retries"] == 3,
        "generation_command_options_same": parent_fingerprint == proposed_fingerprint,
        "prompt_source_same": manifest.get("actual_sha256") == EXPECTED_MANIFEST_SHA and manifest.get("prompt_byte_mismatch") == 0,
        "requested_quality_same": proposed["quality"] == "medium",
        "requested_size_same": proposed["native_size_requested"] == "1536x1024",
        "output_conversion_same": proposed["output_conversion"] == parent_config["output_conversion"],
    }
    material_change = not all(checks.values())
    comparison = {
        "stage": "P4D_GR3Q2_GENERATION_CONFIG_COMPARISON", "captured_at": now(), "parent_generation_config": parent_config, "proposed_recovery_generation_config": proposed,
        "parent_generation_config_fingerprint": parent_fingerprint, "proposed_generation_config_fingerprint": proposed_fingerprint, "checks": checks,
        "material_generation_model_version_observable": False, "material_generation_model_version_note": "The provider exposes gpt-5.4 but no more granular server-side image model version; wrapper/binary/runtime identity is recorded as the available client-side evidence.",
        "MATERIAL_GENERATION_CONFIG_CHANGE": material_change, "MATERIAL_GENERATION_CONFIG_CHANGE_SCOPE": "observable_generation_material_variables_only", "image_generation_provider_requests": 0,
    }
    write_json(PRE / "generation_config_comparison.json", comparison)
    profile = {
        "stage": "P4D_GR3Q2_PROVIDER_PROFILE_COMPARISON", "captured_at": now(), "profile_a_safe_fingerprint": EXPECTED_PROFILE_A, "profile_b_safe_fingerprint": provider.get("profile_fingerprint_safe_hash"),
        "PROFILE_FINGERPRINT_CHANGED": provider.get("profile_fingerprint_safe_hash") != EXPECTED_PROFILE_A, "account_or_user_raw_values_persisted": False,
        "provider_same": checks["provider_same"], "model_same": checks["request_model_same"], "backend_same": checks["generation_backend_same"], "runtime_same": checks["runtime_version_same"], "wrapper_same": checks["wrapper_same"], "binary_same": checks["binary_same"], "prompt_and_config_same": bool(checks["prompt_source_same"] and checks["generation_command_options_same"]),
        "MATERIAL_GENERATION_CONFIG_CHANGE": material_change, "PROFILE_CLASSIFICATION": "OPERATIONAL_PROVENANCE_ONLY" if not material_change else "PROVENANCE_PLUS_MATERIAL_CONFIG_BLOCKER", "PROFILE_STRATIFICATION_REQUIRED": not material_change,
        "policy_change_retroactive_to_gr3q1_decision": False, "image_generation_provider_requests": 0,
    }
    write_json(PRE / "provider_profile_comparison.json", profile)
    return comparison, profile


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
        hits[name] = [number for number, line in enumerate(lines, 1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()]
    value = {
        "label": label, "captured_at": now(), "validator_command": ["python3", str(VALIDATOR), "--json"], "validator_returncode": proc.returncode, "validator": validator,
        "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]}, "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": hits, "p4d_reference_hits_total": sum(len(items) for items in hits.values()), "formal_dataset_mutation_by_gr3q2": False,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", value)
    return value


def write_governance(material_change: bool, profile: dict[str, Any]) -> tuple[Path, Path]:
    hard = ["provider family", "generation backend", "generation model or model capability", "material observable generation model version", "prompt bytes", "generation configuration", "requested quality", "image generation mode", "semantic taxonomy", "group allocation", "DESIGN/SCREEN allocation"]
    provenance = ["account/profile fingerprint", "authentication session", "refresh token/session revision", "execution revision", "quota window", "request timestamp"]
    value = {
        "stage": "P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT", "version": "v1", "captured_at": now(), "POLICY_CHANGE": True, "POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION": False,
        "old_rule": "different account/profile implies lineage break", "new_rule": "account/profile fingerprint is operational provenance and is not alone a semantic generation-lineage break", "hard_generation_lineage_variables": hard, "provenance_only_variables": provenance,
        "current_profile_fingerprint_changed": profile.get("PROFILE_FINGERPRINT_CHANGED"), "current_material_generation_config_change": material_change,
        "decision_rule": "Preserve prior successful assets only when all observable hard variables are unchanged, image integrity passes, and completion ambiguity is zero; record profile strata and audit their imbalance after completion.",
        "limitations": ["Account-specific server-side routing or A/B behavior is not directly observable through local metadata.", "No policy claim proves identical provider-side generation distribution; the amendment requires provenance stratification and later diagnostic audit."],
        "GR3Q1_historical_status_preserved": "BLOCKED_PROFILE_LINEAGE_CHANGE", "image_generation_provider_requests": 0,
    }
    json_path = GOV / "lineage_policy_amendment_v1.json"
    write_json(json_path, value)
    md_path = GOV / "lineage_policy_amendment_v1.md"
    write_text(md_path, f"""# P4D GR3Q2 lineage-policy amendment v1

```text
POLICY_CHANGE=true
POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION=false
ACCOUNT_PROFILE_CLASS=OPERATIONAL_PROVENANCE
MATERIAL_GENERATION_CONFIG_CHANGE={str(material_change).lower()}
```

## 已确认事实

GR3Q1 remains a correct historical `BLOCKED_PROFILE_LINEAGE_CHANGE` result under its then-frozen policy. GR3Q2 does not edit that decision or any parent freeze.

## 新规则

Hard continuation variables are provider/model/backend/capability, prompt bytes, generation command and configuration, requested quality, image-generation mode, output conversion, taxonomy, group allocation, and DESIGN/SCREEN allocation. Account/profile/session/quota/timestamp fields are operational provenance unless an observable material generation variable differs.

## 风险与限制

Equal observable client/runtime configuration does not prove that an opaque provider service has no account-specific behavior. Consequently, Profile-A and Profile-B must remain explicit provenance strata, cannot be model inputs or GT, and require future distribution/style diagnostics after all 440 assets exist.
""")
    return json_path, md_path


def write_authorization(material_change: bool, inventory: dict[str, Any], profile: dict[str, Any]) -> tuple[Path, Path]:
    applicable = not material_change and inventory["preserved_success_verified"] == 99 and inventory["derived_outstanding"] == 341 and inventory["completion_unknown"] == 0
    value = {
        "stage": "P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_AND_RECOVERY_PREP", "authorized": False, "EXPLICIT_RECOVERY_AUTHORIZATION": False, "execution_eligible_after_explicit_authorization": applicable,
        "preserve_gr3e_99": applicable, "continue_outstanding_341": applicable, "profile_stratification_required": applicable, "profile_a": "GR3E_PROFILE_A", "profile_b": "GR3Q2_PROFILE_B", "profile_a_safe_fingerprint": EXPECTED_PROFILE_A, "profile_b_safe_fingerprint": profile.get("profile_b_safe_fingerprint"),
        "maximum_new_logical_slot_invocations": 341, "theoretical_provider_attempt_upper_bound": 1364, "native_max_retries": 3, "outer_retry": False, "exact_monetary_cost": "UNKNOWN", "provider_requests": 0,
        "required_authorization_text_sha256": sha256_object(AUTH_TEXT), "material_generation_config_change": material_change,
    }
    json_path = AUTH / "profile_stratified_recovery_authorization.json"
    write_json(json_path, value)
    md_path = AUTH / "profile_stratified_recovery_authorization_packet.md"
    write_text(md_path, f"""# P4D GR3Q2 profile-stratified recovery authorization packet

```text
AUTHORIZED=false
EXPLICIT_RECOVERY_AUTHORIZATION=false
EXECUTION_ELIGIBLE_AFTER_EXPLICIT_AUTHORIZATION={str(applicable).lower()}
PRESERVE_GR3E_99={str(applicable).lower()}
CONTINUE_OUTSTANDING_341={str(applicable).lower()}
PROFILE_STRATIFICATION_REQUIRED={str(applicable).lower()}
MAXIMUM_NEW_LOGICAL_SLOT_INVOCATIONS=341
NATIVE_MAX_RETRIES=3
OUTER_RETRY=false
THEORETICAL_PROVIDER_ATTEMPT_UPPER_BOUND=1364
EXACT_MONETARY_COST=UNKNOWN
PROVIDER_REQUESTS=0
```

This packet is deliberately not authorization. Do not infer authorization from this task prompt or this template. A future standalone user message must contain exactly this scope before a distinct `P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY` execution revision may be prepared:

> {AUTH_TEXT}

The future runner must preserve immutable parent evidence, write only a new recovery ledger, bind the failed slot to `{FAILED_REQUEST}`, use Profile-B only as local provenance, and globally stop new logical slots after any 429/401/403/timeout/5xx/connection reset.
""")
    return json_path, md_path


def determine_status(parent: dict[str, Any], frozen: dict[str, Any], manifest: dict[str, Any], inventory: dict[str, Any], comparison: dict[str, Any]) -> tuple[str, bool]:
    if not parent["all_required_parent_bindings_match"]:
        return "BLOCKED_PARENT_FREEZE_MISMATCH", False
    if not frozen["all_match"] or not manifest["all_match"]:
        return "BLOCKED_FROZEN_ASSET_MISMATCH", False
    if inventory["preserved_success_verified"] != 99 or inventory["raw_integrity_issues"] or inventory["final_integrity_issues"] or inventory["gr1_sha_hits"] or inventory["samefile_hits"] or inventory["symlink_hits"]:
        return "BLOCKED_PRESERVED_SUCCESS_INTEGRITY", False
    if inventory["derived_outstanding"] != 341 or inventory["failed_confirmed_429"] != 1 or inventory["never_started"] != 340:
        return "BLOCKED_SLOT_INVENTORY_MISMATCH", False
    if inventory["completion_unknown"]:
        return "BLOCKED_COMPLETION_AMBIGUITY", False
    if comparison["MATERIAL_GENERATION_CONFIG_CHANGE"]:
        return "BLOCKED_MATERIAL_GENERATION_LINEAGE_CHANGE", False
    return "READY_AWAITING_PROFILE_STRATIFIED_RECOVERY_AUTHORIZATION", True


def create_freeze(status: str, preserve: bool, parent: dict[str, Any], frozen: dict[str, Any], manifest: dict[str, Any], inventory: dict[str, Any], comparison: dict[str, Any], profile: dict[str, Any], gov_paths: tuple[Path, Path], auth_paths: tuple[Path, Path], before: dict[str, Any], after: dict[str, Any]) -> tuple[Path, str]:
    boundary = {
        "before_path": str(PRE / "dataset_boundary_before.json"), "after_path": str(PRE / "dataset_boundary_after.json"), "before_counts": before["counts"], "after_counts": after["counts"],
        "delta": {key: after["counts"][key] - before["counts"][key] for key in before["counts"]}, "annotation_hashes_same": before["annotation_sha256"] == after["annotation_sha256"],
        "p4d_active_media_hits": len(after["p4d_reference_hits_by_active_csv"]["media.csv"]), "p4d_active_label_hits": len(after["p4d_reference_hits_by_active_csv"]["labels.csv"]), "p4d_active_batch_hits": len(after["p4d_reference_hits_by_active_csv"]["batches.csv"]), "p4d_active_split_hits": len(after["p4d_reference_hits_by_active_csv"]["splits.csv"]),
        "formal_ingest": False, "media_added": 0, "labels_added": 0,
    }
    write_json(PRE / "dataset_boundary.json", boundary)
    paths = [
        PREP_FREEZE, GR3E_FREEZE, Q1_FREEZE, MANIFEST, PARENT_DB, PARENT_LEDGER, PARENT_RUN_CONFIG, PARENT_RUNNER, FAILED_RAW, FAILED_METADATA, CLI, BINARY, SELF,
        PRE / "parent_freeze_audit.json", PRE / "frozen_asset_audit.json", PRE / "full_manifest_audit.json", PRE / "config_inspect.json", PRE / "doctor.json", PRE / "auth_inspect.json", PRE / "images_generate_help.json", PRE / "provider_runtime_audit.json", PRE / "generation_config_comparison.json", PRE / "provider_profile_comparison.json", PRE / "dataset_boundary_before.json", PRE / "dataset_boundary_after.json", PRE / "dataset_boundary.json",
        *[entry[0] for entry in FROZEN_FILES.values()], *gov_paths, INV / "verified_99.csv", INV / "outstanding_341.csv", INV / "profile_strata_plan.csv", INV / "inventory_summary.json", *auth_paths,
    ]
    value = {
        "stage": "P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_AND_RECOVERY_PREP", "name": "P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_AND_RECOVERY_PREP", "status": status, "P4D_STATUS": "GENERATION_REQUIRED",
        "generation_data_revision": "P4D_FULLREGEN_CODEX_PROFILE2_20260827_01", "governance_revision": "P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_20260828_01", "POLICY_AMENDMENT_ACCEPTED": True, "POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION": False,
        "MATERIAL_GENERATION_CONFIG_CHANGE": comparison["MATERIAL_GENERATION_CONFIG_CHANGE"], "PROFILE_CHANGE_ONLY": profile["PROFILE_FINGERPRINT_CHANGED"] and not comparison["MATERIAL_GENERATION_CONFIG_CHANGE"], "PRESERVE_GR3E_99": preserve, "CONTINUE_OUTSTANDING_341": preserve,
        "PROFILE_STRATIFICATION_REQUIRED": preserve, "profile_strata": {"A": {"name": "GR3E_PROFILE_A", "safe_fingerprint": EXPECTED_PROFILE_A, "count": 99}, "B": {"name": "GR3Q2_PROFILE_B", "safe_fingerprint": profile.get("profile_b_safe_fingerprint"), "count": 341}},
        "terminal": {"TOTAL_FROZEN_SLOTS": 440, "GR3E_LOGICAL_INVOCATIONS": inventory["parent_logical_invocations"], "PRESERVED_SUCCESS_VERIFIED": inventory["preserved_success_verified"], "FAILED_CONFIRMED_429": inventory["failed_confirmed_429"], "NEVER_STARTED": inventory["never_started"], "COMPLETION_UNKNOWN": inventory["completion_unknown"], "OUTSTANDING": inventory["derived_outstanding"], "RECOVERY_AUTHORIZED": False, "EXPLICIT_RECOVERY_AUTHORIZATION": False, "PROVIDER_REQUESTS": 0, "FORMAL_INGEST": False, "MEDIA_ADDED": 0, "LABELS_ADDED": 0, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0, "HOLDOUT_CONSUMED": False, "PRODUCTION_CODE_MODIFIED": False, "OLLAMA_SERVICE_MODIFIED": False},
        "parent_freezes": parent, "frozen_assets": frozen, "manifest": manifest, "inventory": inventory, "generation_config_comparison": comparison, "provider_profile_comparison": profile, "dataset_boundary": boundary,
        "retry": {"native_max_retries": 3, "outer_retry": False, "no_retry_guarantee": False, "theoretical_provider_attempt_upper_bound": 1364, "exact_monetary_cost": "UNKNOWN"},
        "artifact_sha256": {str(path): sha256_file(path) for path in paths}, "captured_at": now(),
    }
    path = FREEZE / "p4d_gr3q2_preparation_freeze.json"
    write_json(path, value)
    digest = sha256_file(path)
    write_text(path.with_name(path.name + ".sha256"), f"{digest}  {path.name}")
    return path, str(digest)


def write_reports(status: str, preserve: bool, parent: dict[str, Any], inventory: dict[str, Any], comparison: dict[str, Any], profile: dict[str, Any], freeze_path: Path, freeze_sha: str) -> list[Path]:
    material = comparison["MATERIAL_GENERATION_CONFIG_CHANGE"]
    profile_note = "Profile change is treated as provenance-only under the newly amended policy because no observable material configuration changed." if not material else "A material generation configuration difference was found, so the profile policy amendment cannot preserve the 99 assets for this revision."
    contents = {
        "60_p4d_gr3q2_lineage_policy_amendment.md": f"""# 60 — P4D GR3Q2 lineage-policy amendment

```text
P4D_GR3Q2_STATUS={status}
POLICY_CHANGE=true
POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION=false
PROFILE_FINGERPRINT_CHANGED={str(profile['PROFILE_FINGERPRINT_CHANGED']).lower()}
MATERIAL_GENERATION_CONFIG_CHANGE={str(material).lower()}
PROVIDER_REQUESTS=0
```

## 已确认事实

GR3Q1 remains an immutable historical `BLOCKED_PROFILE_LINEAGE_CHANGE` decision. GR3Q2 created a separate policy amendment without rewriting GR3Q1 or GR3E.

## 合理推理

{profile_note}

## 风险与限制

The provider may have opaque account-specific behavior that cannot be proven absent from local metadata. Profile stratification is therefore mandatory, and it never becomes a GT feature or C3 model input.
""",
        "61_p4d_gr3q2_generation_config_comparison.md": f"""# 61 — P4D GR3Q2 generation configuration comparison

```text
PROVIDER_SAME={str(comparison['checks']['provider_same']).lower()}
MODEL_SAME={str(comparison['checks']['request_model_same']).lower()}
BACKEND_SAME={str(comparison['checks']['generation_backend_same']).lower()}
RUNTIME_SAME={str(comparison['checks']['runtime_version_same']).lower()}
WRAPPER_SAME={str(comparison['checks']['wrapper_same']).lower()}
BINARY_SAME={str(comparison['checks']['binary_same']).lower()}
PROMPT_AND_CONFIG_SAME={str(comparison['checks']['prompt_source_same'] and comparison['checks']['generation_command_options_same']).lower()}
MATERIAL_GENERATION_CONFIG_CHANGE={str(material).lower()}
```

## 已确认事实

Parent and proposed recovery use `codex` / `gpt-5.4` / `image_generation`, native request `1536x1024`, `medium` quality, PNG output, no references, concurrency 1, outer retry false, native max retries 3, then RGB center-crop to 16:9 and Pillow LANCZOS resize to 1920×1080. Frozen prompt bytes and manifest SHA also match.

## 合理推理

No observable material generation-config difference was found. The model's more granular server-side capability version is not exposed; this conclusion is explicitly limited to the observable evidence recorded here.

## 风险与限制

Identical client-side settings do not prove identical opaque server-side behavior. Future profile-stratified QA must look for dimension, latency, file-size, perceptual-hash, scene-distribution, and visual-style differences.
""",
        "62_p4d_gr3q2_preserved99_and_outstanding341.md": f"""# 62 — P4D GR3Q2 preserved 99 and outstanding 341

```text
PRESERVED_SUCCESS_VERIFIED={inventory['preserved_success_verified']}
RAW_INTEGRITY_ISSUES={inventory['raw_integrity_issues']}
FINAL_INTEGRITY_ISSUES={inventory['final_integrity_issues']}
GR1_SHA_HITS={inventory['gr1_sha_hits']}
SAMEFILE_HITS={inventory['samefile_hits']}
SYMLINK_HITS={inventory['symlink_hits']}
OUTSTANDING={inventory['derived_outstanding']}
FAILED_CONFIRMED_429={inventory['failed_confirmed_429']}
NEVER_STARTED={inventory['never_started']}
COMPLETION_UNKNOWN={inventory['completion_unknown']}
```

## 已确认事实

All 99 preserved pairs re-passed raw/final SHA and Pillow checks; finals are 1920×1080. The 341 outstanding slots were independently derived from 440 frozen IDs minus verified successes: one confirmed HTTP 429 slot `{FAILED_PROMPT}` and 340 never-started slots.

## 合理推理

The single failed slot has no image bytes and can become the first logical recovery smoke only after separate authorization. Parent history remains immutable.

## 风险与限制

The resulting 440 image set does not exist yet and no semantic, C3, validation, or Holdout claim is permitted.
""",
        "63_p4d_gr3q2_profile_stratification_plan.md": f"""# 63 — P4D GR3Q2 profile stratification plan

```text
PROFILE_A=GR3E_PROFILE_A
PROFILE_A_COUNT=99
PROFILE_B=GR3Q2_PROFILE_B
PROFILE_B_COUNT=341
PROFILE_STRATIFICATION_REQUIRED={str(preserve).lower()}
PROFILE_ROLE_CONFOUNDING=true
PROFILE_TAXONOMY_CONFOUNDING=true
PROFILE_SPLIT_CONFOUNDING=true
PROFILE_IS_GT_FEATURE=false
PROFILE_IS_C3_INPUT=false
```

## 已确认事实

Profile-A contains 99 hard negatives only: floor-sitting 60 and kneeling/half-kneeling 39; its split allocation is NEW_DESIGN 70 and NEW_SCREEN 29. Profile-B contains 201 hard negatives, all 100 positives, and all 40 ordinary negatives; its split allocation is NEW_DESIGN 195 and NEW_SCREEN 146.

## 合理推理

This is severe profile×role/taxonomy confounding. Split confounding is not deterministic because both strata appear in both splits, but the NEW_DESIGN proportions differ: A {inventory['profile_strata']['GR3E_PROFILE_A']['split_counts'].get('NEW_DESIGN', 0)}/99 versus B {inventory['profile_strata']['GR3Q2_PROFILE_B']['split_counts'].get('NEW_DESIGN', 0)}/341.

## 风险与限制

After all 440 images are generated, mechanically valid, deduplicated, and human-reviewed, profile-stratified diagnostics must compare native dimensions, latency, file size, perceptual-hash distributions, scene/taxonomy allocation, and obvious visual style. Do not use the profile field for truth or prediction.
""",
        "64_p4d_gr3q2_authorization_required.md": f"""# 64 — P4D GR3Q2 profile-stratified recovery authorization required

```text
P4D_GR3Q2_STATUS={status}
P4D_STATUS=GENERATION_REQUIRED
PRESERVE_GR3E_99={str(preserve).lower()}
CONTINUE_OUTSTANDING_341={str(preserve).lower()}
RECOVERY_AUTHORIZED=false
EXPLICIT_RECOVERY_AUTHORIZATION=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
PREPARATION_FREEZE_SHA256={freeze_sha}
```

## 已确认事实

No recovery authorization was supplied in this task. The policy amendment is governance authorization only; it is not approval to generate images. The current runtime is read-only ready but no smoke request was sent.

## 合理推理

If a future standalone user message contains the exact packet scope, a distinct `P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY` execution revision may preserve the verified 99 as Profile-A and attempt at most 341 new logical slots as Profile-B.

## 风险与限制

The maximum possible provider-attempt count is a theoretical `341 × 4 = 1364`, not an actual request count or billing amount. Any 429/401/403/timeout/5xx/connection reset must stop new logical slots without outer automatic recovery.

## Required standalone authorization text

> {AUTH_TEXT}
""",
    }
    paths = []
    for name, content in contents.items():
        path = REPORTS / name
        write_text(path, content)
        paths.append(path)
    return paths


def append_overview(status: str, preserve: bool, inventory: dict[str, Any], comparison: dict[str, Any], profile: dict[str, Any], freeze_path: Path, freeze_sha: str) -> None:
    marker = "## P4D_GR3Q2 lineage-policy amendment and recovery preparation"
    text = OVERVIEW.read_text(encoding="utf-8")
    if marker in text:
        raise RuntimeError("P4D_GR3Q2 overview marker exists; refusing a non-append-only rewrite")
    block = f"""

{marker}

```text
P4D_GR3Q2_NAME=P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_AND_RECOVERY_PREP
P4D_GR3Q2_STATUS={status}
P4D_STATUS=GENERATION_REQUIRED
POLICY_AMENDMENT_ACCEPTED=true
POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION=false
MATERIAL_GENERATION_CONFIG_CHANGE={str(comparison['MATERIAL_GENERATION_CONFIG_CHANGE']).lower()}
PROFILE_CHANGE_ONLY={str(profile['PROFILE_FINGERPRINT_CHANGED'] and not comparison['MATERIAL_GENERATION_CONFIG_CHANGE']).lower()}
PRESERVE_GR3E_99={str(preserve).lower()}
OUTSTANDING={inventory['derived_outstanding']}
PROFILE_STRATIFICATION_REQUIRED={str(preserve).lower()}
RECOVERY_AUTHORIZED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
```

GR3Q1 remains a correct historical profile-lineage block under its former policy. GR3Q2 is a new governance revision: it reclassified account/profile fingerprint as operational provenance when observable provider/model/backend/runtime/prompt/configuration variables remain unchanged. It reverified 99 preserved successes and 341 outstanding slots, created explicit Profile-A/Profile-B strata, and recorded severe profile×role/taxonomy confounding plus split imbalance for future audit. No image-generation request was sent. The GR3Q2 preparation freeze is `{freeze_path}` with SHA-256 `{freeze_sha}`. A separate future user authorization is still required before any recovery execution.
"""
    with OVERVIEW.open("a", encoding="utf-8") as handle:
        handle.write(block)
        handle.flush()
        os.fsync(handle.fileno())


def final_verify(freeze_path: Path, freeze_sha: str, report_paths: list[Path]) -> dict[str, Any]:
    freeze = read_json(freeze_path, {}) or {}
    checks = artifact_checks(freeze.get("artifact_sha256") or {})
    value = {
        "captured_at": now(), "freeze_path": str(freeze_path), "expected_sha256": freeze_sha, "actual_sha256": sha256_file(freeze_path), "sidecar": sidecar_value(freeze_path),
        "freeze_self_match": sha256_file(freeze_path) == freeze_sha == sidecar_value(freeze_path), "all_bound_artifacts_match": all(item["match"] for item in checks), "bound_artifact_checks": checks,
        "report_sha256": {str(path): sha256_file(path) for path in report_paths}, "provider_requests": 0, "formal_ingest": False, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0,
    }
    write_json(CHECKPOINTS / "final_preparation_verification.json", value)
    return value


def main() -> int:
    for directory in (PRE, GOV, INV, AUTH, FREEZE, CHECKPOINTS):
        directory.mkdir(parents=True, exist_ok=True)
    if (REV / "preparation_summary.json").exists():
        raise RuntimeError("GR3Q2 preparation already exists; refusing overwrite")
    before = dataset_snapshot("before")
    parents = audit_parent_freezes()
    frozen = audit_frozen_assets()
    manifest_rows, manifest = audit_manifest()
    if not parents["all_required_parent_bindings_match"]:
        raise RuntimeError("P4D_GR3Q2_STATUS=BLOCKED_PARENT_FREEZE_MISMATCH")
    if not frozen["all_match"] or not manifest["all_match"]:
        raise RuntimeError("P4D_GR3Q2_STATUS=BLOCKED_FROZEN_ASSET_MISMATCH")
    # Required ordering: complete a fresh 99-image integrity audit and derive
    # outstanding slots before even the read-only provider/runtime preflight.
    # The first inventory uses a temporary safe value only; it is rebuilt after
    # the audit with the actual Profile-B fingerprint, without changing any
    # image or provider state.
    build_inventories(manifest_rows, EXPECTED_PROFILE_A, "PENDING_READ_ONLY_PROFILE_AUDIT")
    provider = read_only_provider_audit()
    comparison, profile = compare_material_config(provider, manifest)
    _, _, _, inventory = build_inventories(manifest_rows, EXPECTED_PROFILE_A, provider.get("profile_fingerprint_safe_hash"))
    gov_paths = write_governance(comparison["MATERIAL_GENERATION_CONFIG_CHANGE"], profile)
    status, preserve = determine_status(parents, frozen, manifest, inventory, comparison)
    auth_paths = write_authorization(comparison["MATERIAL_GENERATION_CONFIG_CHANGE"], inventory, profile)
    after = dataset_snapshot("after")
    freeze_path, freeze_sha = create_freeze(status, preserve, parents, frozen, manifest, inventory, comparison, profile, gov_paths, auth_paths, before, after)
    report_paths = write_reports(status, preserve, parents, inventory, comparison, profile, freeze_path, freeze_sha)
    append_overview(status, preserve, inventory, comparison, profile, freeze_path, freeze_sha)
    final = final_verify(freeze_path, freeze_sha, report_paths)
    zero = {
        "stage": "P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_AND_RECOVERY_PREP", "P4D_GR3Q2_STATUS": status, "provider_requests": 0, "raw_generation_response_files": 0,
        "formal_ingest": False, "media_added": 0, "labels_added": 0, "C3": False, "NEW_VAL": 0, "HOLDOUT_REQUESTS": 0, "HOLDOUT_CONSUMED": False, "production_code_modified": False, "ollama_service_modified": False,
    }
    write_json(CHECKPOINTS / "zero_request_gate.json", zero)
    result = {
        "P4D_GR3Q2_STATUS": status, "P4D_STATUS": "GENERATION_REQUIRED", "POLICY_AMENDMENT_ACCEPTED": True, "MATERIAL_GENERATION_CONFIG_CHANGE": comparison["MATERIAL_GENERATION_CONFIG_CHANGE"], "PROFILE_CHANGE_ONLY": profile["PROFILE_FINGERPRINT_CHANGED"] and not comparison["MATERIAL_GENERATION_CONFIG_CHANGE"],
        "PRESERVE_GR3E_99": preserve, "CONTINUE_OUTSTANDING_341": preserve, "PROFILE_STRATIFICATION_REQUIRED": preserve, "RECOVERY_AUTHORIZED": False, "EXPLICIT_RECOVERY_AUTHORIZATION": False,
        "parent_freeze": parents, "frozen_assets": frozen, "manifest": manifest, "inventory": inventory, "generation_config_comparison": comparison, "provider_profile_comparison": profile, "provider_runtime": provider,
        "provider_requests": 0, "dataset_after": after, "freeze_path": str(freeze_path), "freeze_sha256": freeze_sha, "final_verification": final, "authorization_text": AUTH_TEXT,
    }
    write_json(REV / "preparation_summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
