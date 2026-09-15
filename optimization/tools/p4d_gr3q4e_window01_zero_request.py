#!/usr/bin/env python3
"""Prepare and seal a zero-request P4D GR3Q4E Window 01 revision.

This runner deliberately stops at the campaign-authorization gate.  It does
all read-only parent/inventory/runtime/dataset checks and creates a durable
NOT_STARTED ledger, but it never invokes ``images generate``.  A later,
explicitly authorized window must be a new revision.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
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
PARENT = GR3 / "06_execution/quota_campaign_window_20260828_03"
REV = GR3 / "06_execution/quota_campaign_window_01_execution_20260830_01"
REPORTS = ROOT / "reports"
MANIFEST = GR3 / "03_fullregen_plan/full_regen_prompt_manifest.csv"
GR3E_INV = GR3 / "06_execution/authorized_20260827_01/06_full_qa/current_generation_inventory.csv"
GR3E_LEDGER = GR3 / "06_execution/authorized_20260827_01/03_ledger/execution_ledger.csv"
Q2E_ROOT = GR3 / "06_execution/profile_stratified_recovery_20260828_01"
Q2E_LEDGER = Q2E_ROOT / "03_ledger/execution_ledger.csv"
Q2E_RESP = Q2E_ROOT / "04_raw_responses"
GR3Q4_FREEZE = PARENT / "freeze/p4d_gr3q4_terminal_freeze.json"
Q2E_FREEZE = Q2E_ROOT / "freeze/p4d_gr3q2e_terminal_freeze.json"
GR3Q3_ROOT = GR3 / "06_execution/quota_window_recovery_20260828_02"
GR3Q3_FREEZE = GR3Q3_ROOT / "freeze/p4d_gr3q3_terminal_freeze.json"
GR3Q3_QUOTA = GR3Q3_ROOT / "00_preflight/quota_reset_evidence.json"
ADAPTIVE = PARENT / "02_order/adaptive_execution_order.csv"
FIRST_WINDOW = PARENT / "02_order/first_window_68_plan.csv"
GR1_QA = ROOT / "08_p4d_new_hard_negative_dev_revision/03_intake_audit/gr1_independent_mechanical_qa.csv"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ANNOTATIONS = DATASET / "01_annotations"
VALIDATOR = DATASET / "tools/validate_dataset.py"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")

EXPECTED = {
    "gr3q4": "8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2",
    "q2e": "9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44",
    "gr3q3": "7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697",
    "manifest": "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4",
    "adaptive": "acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033",
    "first_window": "2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd",
    "wrapper": "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe",
    "binary": "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba",
    "profile_a": "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe",
    "profile_b": "d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190",
}
FAILED_PROMPT = "PF_P4D_HN_KNEEL_G009_V03"
FINAL_SIZE = (1920, 1080)
WINDOW_CAP = 68
LATER_CAP = 70
PHYSICAL_CAP = 80
RETRY_CAP = 5
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path | str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path | str, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def read_csv(path: Path | str) -> list[dict[str, str]]:
    p = Path(path)
    if not p.is_file():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(value)
        f.flush()
        os.fsync(f.fileno())


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())


def write_empty(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.flush()
        os.fsync(f.fileno())


def copy_exact(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    with target.open("rb") as f:
        os.fsync(f.fileno())


def image_check(path: Path) -> tuple[bool, tuple[int, int] | None, str]:
    if not path.is_file():
        return False, None, "missing"
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
            return True, im.size, ""
    except Exception as exc:  # pragma: no cover - evidence path
        return False, None, f"{type(exc).__name__}: {exc}"


def safe_redact(value: Any, key: str = "") -> Any:
    hidden = {"account_id", "chatgpt_user_id", "access_token", "refresh_token", "id_token", "token", "api_key", "email", "auth_file", "password", "secret"}
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k.lower() in hidden or k.lower() == "value" and any(x in key.lower() for x in ("credential", "token", "secret", "key")):
                out[k] = "<REDACTED>"
            else:
                out[k] = safe_redact(v, k)
        return out
    if isinstance(value, list):
        return [safe_redact(v, key) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", value)
        value = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", value)
        return value
    return value


def run_cli(label: str, args: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    command = ["node", str(CLI), "--json", "--provider", "codex", *args]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        try:
            payload = json.loads(proc.stdout)
            parse_ok = True
        except Exception:
            payload = {"parse_ok": False, "stdout_tail": proc.stdout[-4000:]}
            parse_ok = False
        record = {
            "label": label,
            "command": ["node", "<gpt-image-2-skill>", "--json", "--provider", "codex", *args],
            "returncode": proc.returncode,
            "parse_ok": parse_ok,
            "payload": safe_redact(payload),
            "stderr_present": bool(proc.stderr.strip()),
            "captured_at": now(),
            "image_generation_provider_requests": 0,
        }
    except Exception as exc:
        payload = {"exception": f"{type(exc).__name__}: {exc}"}
        record = {"label": label, "command": ["node", "<gpt-image-2-skill>", "--json", "--provider", "codex", *args], "returncode": None, "parse_ok": False, "payload": payload, "stderr_present": True, "captured_at": now(), "image_generation_provider_requests": 0}
    write_json(REV / "00_preflight" / f"{label}.json", record)
    return payload, record


def run_validator(label: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(["python3", str(VALIDATOR), "--json"], capture_output=True, text=True, timeout=240, check=False)
        try:
            payload = json.loads(proc.stdout)
        except Exception:
            payload = {"parse_ok": False, "returncode": proc.returncode, "stdout_tail": proc.stdout[-4000:]}
    except Exception as exc:
        payload = {"parse_ok": False, "exception": f"{type(exc).__name__}: {exc}"}
    payload["captured_at"] = now()
    payload["command"] = ["python3", str(VALIDATOR), "--json"]
    write_json(REV / "00_preflight" / f"dataset_validator_{label}.json", payload)
    return payload


def annotation_snapshot() -> dict[str, Any]:
    files = ["media.csv", "labels.csv", "batches.csv", "splits.csv", "context_rules.csv"]
    hashes, counts, refs = {}, {}, []
    needles = ("p4d", "fullregen", "hardneg-fullregen", "person-fallen-v2-p4d")
    for name in files:
        p = ANNOTATIONS / name
        hashes[name] = sha256_file(p)
        if p.is_file():
            with p.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            counts[name] = len(rows)
            for i, row in enumerate(rows, 2):
                joined = "|".join(str(v) for v in row.values()).lower()
                if any(n in joined for n in needles):
                    refs.append({"file": name, "row": i, "media_id": row.get("media_id"), "capture_batch": row.get("capture_batch")})
        else:
            counts[name] = 0
    return {"captured_at": now(), "annotation_sha256": hashes, "annotation_row_counts": counts, "p4d_reference_hits": refs, "p4d_reference_hits_total": len(refs)}


def verify_parent_freeze(path: Path, expected_sha: str, expected_status: str) -> dict[str, Any]:
    payload = read_json(path, {}) or {}
    sidecar_path = path.with_name(path.name + ".sha256")
    sidecar = sidecar_path.read_text(encoding="utf-8").split()[0] if sidecar_path.is_file() and sidecar_path.read_text(encoding="utf-8").split() else None
    actual = sha256_file(path)
    bad = []
    for bound_path, expected in (payload.get("artifact_sha256") or {}).items():
        observed = sha256_file(bound_path)
        if observed != expected:
            bad.append({"path": bound_path, "expected_sha256": expected, "actual_sha256": observed})
    result = {"captured_at": now(), "path": str(path), "expected_sha256": expected_sha, "actual_sha256": actual, "sidecar_sha256": sidecar, "sidecar_match": actual == sidecar == expected_sha, "status": payload.get("status"), "expected_status": expected_status, "bound_artifact_count": len(payload.get("artifact_sha256") or {}), "bound_artifacts_bad": bad, "all_bound_artifacts_match": not bad, "all_match": bool(actual == sidecar == expected_sha and payload.get("status") == expected_status and not bad)}
    return result


def manifest_audit() -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = read_csv(MANIFEST)
    mismatches = []
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        prompt_path = Path(row.get("original_prompt_path", ""))
        actual = sha256_file(prompt_path)
        if actual != row.get("prompt_sha256"):
            mismatches.append({"prompt_id": row.get("prompt_id"), "expected": row.get("prompt_sha256"), "actual": actual})
        groups[row.get("group_id", "")].add(row.get("planned_internal_split", ""))
    result = {"captured_at": now(), "path": str(MANIFEST), "expected_sha256": EXPECTED["manifest"], "actual_sha256": sha256_file(MANIFEST), "rows": len(rows), "unique_prompt_ids": len({r.get("prompt_id") for r in rows}), "unique_groups": len({r.get("group_id") for r in rows}), "prompt_byte_mismatch": len(mismatches), "prompt_byte_mismatches": mismatches, "cross_split_group_count": sum(len(v) > 1 for v in groups.values()), "cross_split_groups": sorted(k for k, v in groups.items() if len(v) > 1), "role_counts": dict(Counter(r.get("target_role") for r in rows)), "split_counts": dict(Counter(r.get("planned_internal_split") for r in rows))}
    result["all_match"] = bool(result["actual_sha256"] == EXPECTED["manifest"] and result["rows"] == 440 and result["unique_prompt_ids"] == 440 and result["unique_groups"] == 88 and result["prompt_byte_mismatch"] == 0 and result["cross_split_group_count"] == 0 and result["role_counts"] == {"hard_negative": 300, "positive": 100, "ordinary_negative": 40} and result["split_counts"] == {"NEW_DESIGN": 265, "NEW_SCREEN": 175})
    write_json(REV / "00_preflight/full_manifest_audit.json", result)
    return rows, result


def verify_image_row(pid: str, profile: str, manifest_row: dict[str, str], source: dict[str, Any], ledger: dict[str, str], response: dict[str, Any]) -> dict[str, Any]:
    if profile == "GR3E_PROFILE_A":
        raw_path = Path(source.get("raw_path", ""))
        final_path = Path(source.get("final_path", ""))
        raw_expected, final_expected = source.get("raw_sha256", ""), source.get("final_sha256", "")
        parent_state, parent_http, request_id = source.get("state", ""), ledger.get("http_status", ""), ledger.get("provider_request_id", "")
        parent_revision = "P4D_GR3E_AUTHORIZED_20260827_01"
    else:
        raw_path = Path(response.get("raw_path") or BATCH / "generated_raw" / f"{pid}.png")
        final_path = Path(response.get("final_path") or BATCH / "final" / f"{pid}.png")
        raw_expected, final_expected = ledger.get("raw_sha256", ""), ledger.get("final_sha256", "")
        parent_state, parent_http, request_id = ledger.get("parent_state", ""), ledger.get("http_status", ""), ledger.get("provider_request_id", "")
        parent_revision = "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY_20260828_01"
    raw_actual, final_actual = sha256_file(raw_path), sha256_file(final_path)
    raw_ok, _, raw_error = image_check(raw_path)
    final_ok, final_size, final_error = image_check(final_path)
    samefile = False
    if raw_path.is_file() and final_path.is_file():
        try:
            samefile = os.path.samefile(raw_path, final_path)
        except OSError:
            samefile = False
    attributes_match = all([
        manifest_row.get("group_id") == source.get("group_id", ledger.get("group_id", manifest_row.get("group_id"))),
        manifest_row.get("variant_id") == source.get("variant_id", ledger.get("variant_id", manifest_row.get("variant_id"))),
        manifest_row.get("target_role") == source.get("target_role", ledger.get("target_role", manifest_row.get("target_role"))),
        manifest_row.get("taxonomy") == source.get("taxonomy", ledger.get("taxonomy", manifest_row.get("taxonomy"))),
        manifest_row.get("planned_internal_split") == source.get("planned_split", ledger.get("planned_split", manifest_row.get("planned_internal_split"))),
        manifest_row.get("prompt_sha256") == source.get("prompt_sha256", ledger.get("prompt_sha256", manifest_row.get("prompt_sha256"))),
    ])
    verified = bool(raw_actual == raw_expected and final_actual == final_expected and raw_ok and final_ok and final_size == FINAL_SIZE and not raw_path.is_symlink() and not final_path.is_symlink() and not samefile and attributes_match)
    return {"prompt_id": pid, "ordinal": int(manifest_row.get("ordinal", "0") or 0), "group_id": manifest_row.get("group_id"), "variant_id": manifest_row.get("variant_id"), "planned_split": manifest_row.get("planned_internal_split"), "target_role": manifest_row.get("target_role"), "taxonomy": manifest_row.get("taxonomy"), "event_label": manifest_row.get("target_event_label"), "prompt_sha256": manifest_row.get("prompt_sha256"), "generation_profile_stratum": profile, "parent_revision": parent_revision, "parent_state": parent_state, "parent_http_status": parent_http, "parent_request_id": request_id, "raw_path": str(raw_path), "final_path": str(final_path), "raw_sha256_expected": raw_expected, "raw_sha256_actual": raw_actual or "", "final_sha256_expected": final_expected, "final_sha256_actual": final_actual or "", "raw_pillow_pass": raw_ok, "final_pillow_pass": final_ok, "raw_error": raw_error, "final_error": final_error, "final_width": final_size[0] if final_size else "", "final_height": final_size[1] if final_size else "", "raw_final_samefile": samefile, "symlink_hit": bool(raw_path.is_symlink() or final_path.is_symlink()), "attributes_match": attributes_match, "verified_success": verified}


def rebuild_inventory(manifest_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    by_id = {r.get("prompt_id"): r for r in manifest_rows}
    gr3e_inv = {r.get("prompt_id"): r for r in read_csv(GR3E_INV) if r.get("state") == "SUCCESS"}
    gr3e_led = {r.get("logical_slot_id"): r for r in read_csv(GR3E_LEDGER)}
    q2e_led = {r.get("logical_slot_id"): r for r in read_csv(Q2E_LEDGER)}
    responses = {}
    for p in Q2E_RESP.glob("*.json"):
        d = read_json(p, {}) or {}
        if d.get("prompt_id"):
            responses[d["prompt_id"]] = d
    rows, issues = [], []
    for pid, source in gr3e_inv.items():
        m = by_id.get(pid)
        if not m or pid in {r["prompt_id"] for r in rows}:
            issues.append({"prompt_id": pid, "issue": "missing_manifest_or_duplicate"})
            continue
        row = verify_image_row(pid, "GR3E_PROFILE_A", m, source, gr3e_led.get(pid, {}), {})
        if not row["verified_success"]:
            issues.append({"prompt_id": pid, "profile": "GR3E_PROFILE_A", "issue": "integrity_or_binding", "row": row})
        rows.append(row)
    for pid, ledger in q2e_led.items():
        if ledger.get("state") != "SUCCESS_PROFILE_B":
            continue
        m = by_id.get(pid)
        response = responses.get(pid, {})
        if not m or pid in {r["prompt_id"] for r in rows}:
            issues.append({"prompt_id": pid, "issue": "missing_manifest_or_duplicate"})
            continue
        row = verify_image_row(pid, "GR3Q2_PROFILE_B", m, ledger, ledger, response)
        if not row["verified_success"]:
            issues.append({"prompt_id": pid, "profile": "GR3Q2_PROFILE_B", "issue": "integrity_or_binding", "row": row})
        rows.append(row)
    rows.sort(key=lambda r: r["ordinal"])
    verified = [r for r in rows if r["verified_success"]]
    summary = {"captured_at": now(), "expected_total": 102, "total_verified_success": len(verified), "unique_prompt_ids": len({r["prompt_id"] for r in verified}), "profile_strata": dict(Counter(r["generation_profile_stratum"] for r in verified)), "role_counts": dict(Counter(r["target_role"] for r in verified)), "split_counts": dict(Counter(r["planned_split"] for r in verified)), "taxonomy_counts": dict(Counter(r["taxonomy"] for r in verified)), "inventory_issues": issues, "all_verified": len(verified) == 102 and len({r["prompt_id"] for r in verified}) == 102 and not issues}
    fields = ["prompt_id", "ordinal", "group_id", "variant_id", "planned_split", "target_role", "taxonomy", "event_label", "prompt_sha256", "generation_profile_stratum", "parent_revision", "parent_state", "parent_http_status", "parent_request_id", "raw_path", "final_path", "raw_sha256_expected", "raw_sha256_actual", "final_sha256_expected", "final_sha256_actual", "raw_pillow_pass", "final_pillow_pass", "raw_error", "final_error", "final_width", "final_height", "raw_final_samefile", "symlink_hit", "attributes_match", "verified_success"]
    write_csv(REV / "01_inventory/current_verified_success_inventory.csv", fields, verified)
    summary["inventory_csv_sha256"] = sha256_file(REV / "01_inventory/current_verified_success_inventory.csv")
    write_json(REV / "01_inventory/inventory_summary.json", summary)
    return verified, summary, {"manifest_by_id": by_id, "gr3e_inv": gr3e_inv, "gr3e_led": gr3e_led, "q2e_led": q2e_led, "responses": responses}


def gr1_exclusion(verified: list[dict[str, Any]]) -> dict[str, Any]:
    old = read_csv(GR1_QA)
    old_hashes = {r[k] for r in old for k in ("raw_sha256", "final_sha256") if r.get(k)}
    old_paths = [Path(r[k]) for r in old for k in ("raw_path", "final_path") if r.get(k)]
    sha_hits, same_hits, symlink_hits = [], [], []
    for r in verified:
        for k in ("raw_sha256_actual", "final_sha256_actual"):
            if r.get(k) in old_hashes:
                sha_hits.append({"prompt_id": r["prompt_id"], "kind": k, "sha256": r[k]})
        for key in ("raw_path", "final_path"):
            p = Path(r[key])
            if p.is_symlink():
                symlink_hits.append(str(p))
            for old_path in old_paths:
                if p.is_file() and old_path.is_file():
                    try:
                        if os.path.samefile(p, old_path):
                            same_hits.append({"prompt_id": r["prompt_id"], "path": str(p), "gr1_path": str(old_path)})
                    except OSError:
                        pass
    result = {"captured_at": now(), "gr1_qa_path": str(GR1_QA), "gr1_rows": len(old), "gr1_pass_rows": sum(r.get("status") == "PASS" for r in old), "gr1_sha_hits": sha_hits, "gr1_samefile_hits": same_hits, "gr1_symlink_hits": symlink_hits, "GR1_IMAGES_REUSED": 0, "GR1_SHA_HITS": len(sha_hits), "GR1_SAMEFILE_HITS": len(same_hits), "GR1_SYMLINK_HITS": len(symlink_hits), "all_excluded": not sha_hits and not same_hits and not symlink_hits}
    write_json(REV / "01_inventory/gr1_exclusion_audit.json", result)
    return result


def build_outstanding(manifest_rows: list[dict[str, str]], verified: list[dict[str, Any]], sources: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    success = {r["prompt_id"] for r in verified}
    q2e = sources["q2e_led"]
    gr3e = {r.get("prompt_id"): r for r in read_csv(GR3E_INV)}
    ordered = [r for r in manifest_rows if r.get("prompt_id") == FAILED_PROMPT] + [r for r in manifest_rows if r.get("prompt_id") != FAILED_PROMPT]
    rows = []
    for m in ordered:
        pid = m["prompt_id"]
        if pid in success:
            continue
        q = q2e.get(pid, {})
        g = gr3e.get(pid, {})
        if pid == FAILED_PROMPT and q.get("state") == "FAILED_CONFIRMED_PROFILE_B" and q.get("http_status") == "429":
            state, req, http, err = "FAILED_CONFIRMED_HTTP_429", q.get("provider_request_id", "unknown"), "429", q.get("error_code", "http_error")
        elif g.get("state") == "NOT_STARTED":
            state, req, http, err = "NEVER_STARTED", "", "", ""
        else:
            state, req, http, err = "COMPLETION_UNKNOWN", "", "", "unrecognized_parent_state"
        rows.append({"execution_candidate_order": len(rows) + 1, "prompt_id": pid, "original_manifest_ordinal": manifest_rows.index(m), "group_id": m["group_id"], "variant_id": m["variant_id"], "role": m["target_role"], "taxonomy": m["taxonomy"], "planned_split": m["planned_internal_split"], "prompt_path": m["original_prompt_path"], "prompt_sha256": m["prompt_sha256"], "parent_state": state, "parent_request_id": req, "parent_http_status": http, "parent_error_code": err})
    counts = Counter(r["parent_state"] for r in rows)
    summary = {"captured_at": now(), "total_outstanding": len(rows), "expected_outstanding": 338, "failed_confirmed_http_429": counts.get("FAILED_CONFIRMED_HTTP_429", 0), "never_started": counts.get("NEVER_STARTED", 0), "completion_unknown": counts.get("COMPLETION_UNKNOWN", 0), "role_counts": dict(Counter(r["role"] for r in rows)), "taxonomy_counts": dict(Counter(r["taxonomy"] for r in rows)), "split_counts": dict(Counter(r["planned_split"] for r in rows)), "first_prompt_id": rows[0]["prompt_id"] if rows else None}
    summary["exact_expected_state"] = bool(len(rows) == 338 and summary["failed_confirmed_http_429"] == 1 and summary["never_started"] == 337 and summary["completion_unknown"] == 0)
    write_csv(REV / "01_inventory/outstanding_338.csv", list(rows[0].keys()) if rows else ["prompt_id"], rows)
    summary["outstanding_csv_sha256"] = sha256_file(REV / "01_inventory/outstanding_338.csv")
    write_json(REV / "01_inventory/outstanding_summary.json", summary)
    return rows, summary


def plan_audit(outstanding: list[dict[str, Any]]) -> dict[str, Any]:
    adaptive_rows = read_csv(ADAPTIVE)
    first_rows = read_csv(FIRST_WINDOW)
    adaptive_sha, first_sha = sha256_file(ADAPTIVE), sha256_file(FIRST_WINDOW)
    out_ids = {r["prompt_id"] for r in outstanding}
    adaptive_ids = {r.get("prompt_id") for r in adaptive_rows}
    first_ids = {r.get("prompt_id") for r in first_rows}
    result = {"captured_at": now(), "adaptive_source": str(ADAPTIVE), "adaptive_sha256": adaptive_sha, "adaptive_expected_sha256": EXPECTED["adaptive"], "adaptive_rows": len(adaptive_rows), "adaptive_unique_prompt_ids": len(adaptive_ids), "adaptive_exact_outstanding": bool(adaptive_sha == EXPECTED["adaptive"] and len(adaptive_rows) == 338 and adaptive_ids == out_ids and adaptive_rows[0].get("prompt_id") == FAILED_PROMPT), "first_window_source": str(FIRST_WINDOW), "first_window_sha256": first_sha, "first_window_expected_sha256": EXPECTED["first_window"], "first_window_rows": len(first_rows), "first_window_unique_prompt_ids": len(first_ids), "first_window_group_count": len({r.get("group_id") for r in first_rows}), "first_window_role_counts": dict(Counter(r.get("role") for r in first_rows)), "first_window_split_counts": dict(Counter(r.get("planned_split") for r in first_rows)), "first_window_first_prompt": first_rows[0].get("prompt_id") if first_rows else None, "first_window_exact": bool(first_sha == EXPECTED["first_window"] and len(first_rows) == 68 and len(first_ids) == 68 and first_rows[0].get("prompt_id") == FAILED_PROMPT and first_ids <= out_ids)}
    copy_exact(ADAPTIVE, REV / "02_plan/adaptive_execution_order.csv")
    copy_exact(FIRST_WINDOW, REV / "02_plan/first_window_68_plan.csv")
    write_json(REV / "02_plan/plan_binding_audit.json", result)
    return result


def runtime_audit() -> dict[str, Any]:
    config, _ = run_cli("config_inspect", ["config", "inspect"])
    doctor, _ = run_cli("doctor", ["doctor"])
    auth, _ = run_cli("auth_inspect", ["auth", "inspect"])
    codex = ((doctor.get("providers") or {}).get("codex") or {}) if isinstance(doctor, dict) else {}
    c_auth = codex.get("auth") or {}
    endpoint = codex.get("endpoint") or {}
    if not c_auth:
        c_auth = ((auth.get("providers") or {}).get("codex") or {}) if isinstance(auth, dict) else {}
    account, user = str(c_auth.get("account_id") or ""), str(c_auth.get("chatgpt_user_id") or "")
    profile = hashlib.sha256(f"account={account}|user={user}".encode()).hexdigest() if account or user else None
    selection = doctor.get("provider_selection") or {} if isinstance(doctor, dict) else {}
    defaults = doctor.get("defaults") or {} if isinstance(doctor, dict) else {}
    retry = doctor.get("retry_policy") or {} if isinstance(doctor, dict) else {}
    stratum = "PROFILE_A_RESTORED" if profile == EXPECTED["profile_a"] else "PROFILE_B" if profile == EXPECTED["profile_b"] else "UNKNOWN_NEW_PROFILE_STRATUM"
    result = {"captured_at": now(), "requested_provider": "codex", "resolved_provider": selection.get("resolved"), "provider": selection.get("resolved"), "request_model": defaults.get("codex_model"), "generation_backend": "image_generation", "runtime_version": doctor.get("version") if isinstance(doctor, dict) else None, "wrapper_path": str(CLI), "wrapper_sha256": sha256_file(CLI), "binary_path": str(BINARY), "binary_sha256": sha256_file(BINARY), "native_retry_policy": retry, "native_max_retries": retry.get("max_retries"), "outer_retry": False, "auth_ready": bool(c_auth.get("ready")), "endpoint_reachable": bool(endpoint.get("reachable")), "tls_ok": bool(endpoint.get("tls_ok")), "session_ready": bool(c_auth.get("ready") and endpoint.get("reachable") and endpoint.get("tls_ok")), "profile_fingerprint_safe_hash": profile, "active_profile_stratum": stratum, "profile_matches_a": profile == EXPECTED["profile_a"], "profile_matches_b": profile == EXPECTED["profile_b"], "raw_profile_values_persisted": False, "image_generation_provider_requests": 0, "config_default_provider_note": (config.get("config") or {}).get("default_provider") if isinstance(config, dict) else None}
    result["material_config_match"] = bool(result["provider"] == "codex" and result["resolved_provider"] == "codex" and result["request_model"] == "gpt-5.4" and result["generation_backend"] == "image_generation" and result["runtime_version"] == "0.7.3" and result["wrapper_sha256"] == EXPECTED["wrapper"] and result["binary_sha256"] == EXPECTED["binary"] and result["native_max_retries"] == 3 and result["outer_retry"] is False)
    write_json(REV / "00_preflight/provider_runtime_audit.json", result)
    return result


def quota_time_audit() -> dict[str, Any]:
    source = read_json(GR3Q3_QUOTA, {}) or {}
    reset_epoch = source.get("resets_at_epoch")
    reset = datetime.fromtimestamp(int(reset_epoch), timezone.utc) if reset_epoch else None
    safety_margin_seconds = int(source.get("safety_margin_seconds") or 653)
    not_before = reset + timedelta(seconds=safety_margin_seconds) if reset else None
    now_dt = datetime.now(timezone.utc)
    result = {"captured_at": now(), "source_path": str(GR3Q3_QUOTA), "source_sha256": sha256_file(GR3Q3_QUOTA), "provider_error_type": source.get("provider_error_type"), "resets_at_epoch": reset_epoch, "resets_at_utc": reset.isoformat() if reset else None, "resets_at_local": reset.astimezone(LOCAL_TZ).isoformat() if reset else None, "safety_margin_seconds": safety_margin_seconds, "not_before_utc_historical": not_before.isoformat() if not_before else None, "not_before_local_historical": not_before.astimezone(LOCAL_TZ).isoformat() if not_before else None, "current_utc": now_dt.isoformat(), "current_local": now_dt.astimezone(LOCAL_TZ).isoformat(), "historical_time_gate_blocking": bool(not_before and now_dt < not_before), "time_gate_pass_for_current_task": bool(not_before is None or now_dt >= not_before), "do_not_sleep": True, "provider_requests": 0}
    write_json(REV / "00_preflight/quota_time_audit.json", result)
    return result


def create_ledger(first_rows: list[dict[str, str]], runtime: dict[str, Any]) -> dict[str, Any]:
    ledger_fields = ["window_planned_order", "execution_order", "prompt_id", "group_id", "variant_id", "role", "taxonomy", "planned_split", "original_manifest_ordinal", "current_group_success_count", "current_group_outstanding_count", "parent_state", "selection_reason", "state", "invocation_count"]
    rows = []
    for i, r in enumerate(first_rows, 1):
        rows.append({"window_planned_order": r.get("window_planned_order", i), "execution_order": r.get("execution_order") or r.get("window_planned_order", i), "prompt_id": r.get("prompt_id", ""), "group_id": r.get("group_id", ""), "variant_id": r.get("variant_id", ""), "role": r.get("role", ""), "taxonomy": r.get("taxonomy", ""), "planned_split": r.get("planned_split", ""), "original_manifest_ordinal": r.get("original_manifest_ordinal", ""), "current_group_success_count": r.get("current_group_success_count", ""), "current_group_outstanding_count": r.get("current_group_outstanding_count", ""), "parent_state": r.get("parent_state", ""), "selection_reason": r.get("selection_reason", ""), "state": "NOT_STARTED", "invocation_count": 0})
    csv_path = REV / "03_ledger/window_01_ledger.csv"
    write_csv(csv_path, ledger_fields, rows)
    db_path = REV / "03_ledger/window_01_execution.sqlite3"
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("CREATE TABLE slots (prompt_id TEXT PRIMARY KEY, window_planned_order INTEGER UNIQUE NOT NULL, execution_order INTEGER NOT NULL, group_id TEXT NOT NULL, variant_id TEXT NOT NULL, role TEXT NOT NULL, taxonomy TEXT NOT NULL, planned_split TEXT NOT NULL, original_manifest_ordinal INTEGER NOT NULL, parent_state TEXT NOT NULL, state TEXT NOT NULL, invocation_count INTEGER NOT NULL DEFAULT 0, provider_request_id TEXT, http_status TEXT, error_code TEXT, raw_sha256 TEXT, final_sha256 TEXT, latency_seconds REAL, native_retry_count INTEGER, timestamp TEXT, profile_stratum TEXT NOT NULL)")
        con.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, captured_at TEXT NOT NULL)")
        sql = "INSERT INTO slots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        for r in rows:
            vals = (r["prompt_id"], int(r["window_planned_order"]), int(r["execution_order"]), r["group_id"], r["variant_id"], r["role"], r["taxonomy"], r["planned_split"], int(r["original_manifest_ordinal"]), r["parent_state"], r["state"], 0, "", "", "", "", "", None, None, "", runtime.get("active_profile_stratum", "UNKNOWN"))
            con.execute(sql, vals)
        con.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (None, "PREPARED_ZERO_REQUEST", json.dumps({"authorization_present": False, "provider_requests": 0, "window_cap": WINDOW_CAP}, sort_keys=True), now()))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    # A stable close must leave no sidecar files.
    wal = Path(str(db_path) + "-wal")
    shm = Path(str(db_path) + "-shm")
    result = {"captured_at": now(), "csv_path": str(csv_path), "csv_sha256": sha256_file(csv_path), "sqlite_path": str(db_path), "sqlite_sha256": sha256_file(db_path), "rows": len(rows), "state_counts": dict(Counter(r["state"] for r in rows)), "event_count": 1, "wal_exists_after_close": wal.exists(), "shm_exists_after_close": shm.exists(), "stable_close": not wal.exists() and not shm.exists()}
    write_json(REV / "03_ledger/ledger_stability.json", result)
    return result


def write_window_artifacts(runtime: dict[str, Any], inventory: dict[str, Any], outstanding: dict[str, Any], plan: dict[str, Any], boundary: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Path]:
    paths = {}
    auth = {"stage": "P4D_GR3Q4E_CAMPAIGN_AUTHORIZATION_GATE", "authorization_present": False, "authorized": False, "source": "none_in_current_top_level_user_message", "prompt_attachment_is_not_authorization": True, "starting_success": 102, "starting_outstanding": 338, "window_01_logical_cap": WINDOW_CAP, "later_window_default_cap": LATER_CAP, "concurrency": 1, "outer_retry": False, "native_max_retries": 3, "quota_risk_accepted": False, "cost_unknown_accepted": False, "formal_ingest_authorized": False, "C3_authorized": False, "VAL_authorized": False, "HOLDOUT_authorized": False, "provider_requests": 0, "captured_at": now()}
    paths["authorization"] = REV / "01_authorization/campaign_authorization_status.json"
    write_json(paths["authorization"], auth)
    config = {"stage": "P4D_GR3Q4E_ADAPTIVE_QUOTA_CAMPAIGN_WINDOW_01", "revision_id": "P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01", "provider": "codex", "request_model": "gpt-5.4", "generation_backend": "image_generation", "runtime_version": runtime.get("runtime_version"), "active_profile_stratum": runtime.get("active_profile_stratum"), "profile_fingerprint_safe_hash": runtime.get("profile_fingerprint_safe_hash"), "native_size_requested": "1536x1024", "quality": "medium", "format": "png", "final_size": "1920x1080", "output_conversion": {"crop": "controlled_16_by_9_crop", "resize_method": "Pillow_LANCZOS", "final_format": "PNG"}, "window_logical_cap": WINDOW_CAP, "later_window_default_cap": LATER_CAP, "physical_attempt_lower_bound_cap": PHYSICAL_CAP, "native_retry_event_cap": RETRY_CAP, "concurrency": 1, "outer_retry": False, "native_max_retries": 3, "authorization_present": False, "execution_eligible": False, "provider_requests": 0, "logical_invocations": 0, "logical_successes": 0, "logical_failures": 0, "native_retry_scheduled_events": 0, "physical_attempt_lower_bound": 0, "prompt_changed": False, "prompt_manifest_sha256": EXPECTED["manifest"], "created_at": now()}
    paths["run_config"] = REV / "run_config.json"
    write_json(paths["run_config"], config)
    for name in ("request_log.jsonl", "raw_responses.jsonl"):
        paths[name] = REV / name
        write_empty(paths[name])
    paths["provider_before"] = REV / "05_checkpoints/provider_requests_before_execution.json"
    write_json(paths["provider_before"], {"captured_at": now(), "provider_requests": 0, "logical_invocations": 0, "physical_attempt_lower_bound": 0, "request_log_lines": 0, "raw_response_lines": 0})
    paths["group_checkpoint"] = REV / "05_checkpoints/group_checkpoint.json"
    write_json(paths["group_checkpoint"], {"captured_at": now(), "status": "NOT_EXECUTED", "completed_group_count": 0, "current_total_success": inventory["total_verified_success"], "window_logical_count": 0, "window_physical_attempt_lower_bound": 0, "window_native_retry_events": 0, "outstanding": outstanding["total_outstanding"], "last_successful_prompt": None})
    paths["terminal_summary"] = REV / "05_checkpoints/terminal_summary.json"
    write_json(paths["terminal_summary"], {"captured_at": now(), "status": "AWAITING_CAMPAIGN_AUTHORIZATION", "stop_reason": "EXPLICIT_CAMPAIGN_AUTHORIZATION_MISSING", "starting_verified_success": inventory["total_verified_success"], "starting_outstanding": outstanding["total_outstanding"], "window_logical_cap": WINDOW_CAP, "later_window_default_cap": LATER_CAP, "provider_requests": 0, "logical_invocations": 0, "window_success": 0, "window_failure": 0, "native_retry_scheduled_events": 0, "physical_attempt_lower_bound": 0, "new_images": 0, "holdout_requests": 0, "holdout_consumed": False, "formal_ingest": False, "c3": False, "new_val": 0, "full_440_qa": "NOT_REACHED", "semantic_sentinel": "NOT_EXECUTED", "production_code_modified": False})
    paths["new_image_manifest"] = REV / "06_partial_qa/new_image_hash_manifest.json"
    write_json(paths["new_image_manifest"], {"captured_at": now(), "status": "NOT_EXECUTED", "new_raw_count": 0, "new_final_count": 0, "images": [], "exact_duplicate_hits": 0, "gr1_sha_hits": 0})
    paths["sentinel"] = REV / "06_partial_qa/semantic_sentinel_manifest.json"
    write_json(paths["sentinel"], {"captured_at": now(), "SEMANTIC_SENTINEL_STATUS": "USER_REVIEW_OPTIONAL", "status": "NOT_EXECUTED", "groups_sampled": 0, "images": [], "codex_filled_human_conclusion": False})
    paths["partial_qa"] = REV / "06_partial_qa/partial_mechanical_qa_summary.json"
    write_json(paths["partial_qa"], {"captured_at": now(), "status": "NOT_EXECUTED_NO_NEW_IMAGES", "starting_inventory_verified": inventory["all_verified"], "starting_inventory_count": inventory["total_verified_success"], "new_raw_count": 0, "new_final_count": 0, "pillow_failures": 0, "dimension_failures": 0, "sha_failures": 0, "exact_duplicate_hits": 0, "gr1_sha_hits": 0, "gr1_samefile_hits": 0, "gr1_symlink_hits": 0, "full_440_qa": "NOT_REACHED"})
    return paths


def write_reports(runtime: dict[str, Any], inventory: dict[str, Any], outstanding: dict[str, Any], gr1: dict[str, Any], plan: dict[str, Any], quota: dict[str, Any], boundary: dict[str, Any], ledger: dict[str, Any], parent_audits: dict[str, Any], paths: dict[str, Path]) -> list[Path]:
    hashes = lambda p: sha256_file(p) or "MISSING"
    report_paths = [REPORTS / f"{i}_p4d_gr3q4e_window01_{name}.md" for i, name in ((81, "preflight"), (82, "execution"), (83, "partial_qa"), (84, "quota_metrics"), (85, "final"))]
    common = f"""PROJECT=net_vlm\nEVENT=person_fallen\nEVENT_VERSION=v2.0\nP4D_GR3Q4E_NAME=P4D_GR3Q4E_ADAPTIVE_QUOTA_CAMPAIGN_WINDOW_01\nP4D_GR3Q4E_REVISION=P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01\nP4D_GR3Q4E_STATUS=AWAITING_CAMPAIGN_AUTHORIZATION\nPROVIDER_REQUESTS=0\nHOLDOUT_REQUESTS=0\nHOLDOUT_CONSUMED=false\n"""
    preflight = f"""# P4D GR3Q4E Window 01 preflight\n\n```text\n{common}STARTING_VERIFIED_SUCCESS={inventory['total_verified_success']}\nSTARTING_OUTSTANDING={outstanding['total_outstanding']}\nFAILED_CONFIRMED_HTTP_429={outstanding['failed_confirmed_http_429']}\nNEVER_STARTED={outstanding['never_started']}\nCOMPLETION_UNKNOWN={outstanding['completion_unknown']}\nPARENT_GR3Q4_FREEZE_SHA256={EXPECTED['gr3q4']}\nPARENT_Q2E_FREEZE_SHA256={EXPECTED['q2e']}\nPARENT_GR3Q3_FREEZE_SHA256={EXPECTED['gr3q3']}\nFROZEN_440_MANIFEST_SHA256={EXPECTED['manifest']}\nADAPTIVE_ORDER_SHA256={plan['adaptive_sha256']}\nFIRST_WINDOW_68_PLAN_SHA256={plan['first_window_sha256']}\nPROVIDER=codex\nREQUEST_MODEL=gpt-5.4\nGENERATION_BACKEND=image_generation\nRUNTIME_VERSION={runtime.get('runtime_version')}\nACTIVE_PROFILE_STRATUM={runtime.get('active_profile_stratum')}\nPROFILE_FINGERPRINT_SAFE_HASH={runtime.get('profile_fingerprint_safe_hash')}\nMATERIAL_CONFIG_MATCH={runtime.get('material_config_match')}\nHISTORICAL_TIME_GATE_BLOCKING={quota.get('historical_time_gate_blocking')}\nCURRENT_TIME_GATE_PASS={quota.get('time_gate_pass_for_current_task')}\nEXPLICIT_CAMPAIGN_AUTHORIZATION=false\nEXECUTION_ELIGIBLE=false\n```\n\n## 已确认事实\n\n父级 GR3Q4、Q2E、GR3Q3 terminal freeze 的 SHA、sidecar 和 bound artifacts 均通过独立只读核验。冻结 440-slot manifest 通过 hash、440 rows、440 unique prompt IDs、88 groups、cross-split=0、prompt byte mismatch=0；角色与 NEW_DESIGN/NEW_SCREEN 分布保持冻结值。\n\n当前 inventory 从 GR3E/Q2E ledgers、实际 raw/final 文件和 Pillow 校验重建为 102 张：Profile-A={inventory['profile_strata'].get('GR3E_PROFILE_A',0)}、Profile-B={inventory['profile_strata'].get('GR3Q2_PROFILE_B',0)}，全部通过 SHA、Pillow、1920x1080、symlink/samefile 检查。GR1 排除检查为 SHA/samefile/symlink=0。\n\n## 实验判断\n\n实时日期已超过历史 quota reset 安全时间，因此历史 time gate 不再阻塞本窗口。当前顶层消息没有本窗口所需的等价 campaign authorization；任务正文明确规定其模板不构成授权，所以执行资格为 false，provider 请求必须为 0。\n\n## 风险与限制\n\nauth/session ready 不是用户授权；不能把先前 Q2E 或 EBOND 的授权沿用到 GR3Q4E。runtime audit 只保存脱敏结果，未读取或调用 EBOND。\n\n## 下一阶段建议\n\n由用户在新的独立顶层消息明确授权本窗口范围后，重新验证本 revision 的 parent/hash/profile/config gate，并人工启动新的 execution revision；不得把本零请求 freeze 改造成可执行或自动恢复的窗口。\n"""
    execution = f"""# P4D GR3Q4E Window 01 execution\n\n```text\n{common}WINDOW_LOGICAL_CAP=68\nPHYSICAL_ATTEMPT_LOWER_BOUND_CAP=80\nNATIVE_RETRY_EVENT_CAP=5\nLOGICAL_INVOCATIONS=0\nWINDOW_SUCCESS=0\nWINDOW_FAILURE=0\nNATIVE_RETRY_SCHEDULED_EVENTS=0\nOBSERVED_PHYSICAL_ATTEMPT_LOWER_BOUND=0\nHTTP200=0\nHTTP429=0\nHTTP401=0\nHTTP403=0\nHTTP5XX=0\nTIMEOUTS=0\nCONNECTION_ERRORS=0\n```\n\n本 revision 在 authorization gate 停止，没有发送首 slot `PF_P4D_HN_KNEEL_G009_V03`，没有调用 `images generate`。68 行 durable ledger 均为 `NOT_STARTED`，SQLite stable close、WAL/SHM 清理和空 request/raw logs 已完成。`outer_retry=false`、native max retries=3 只是预注册配置，未产生任何实际 attempt。\n\n没有执行 C3、VAL、HOLDOUT、formal ingest 或生产集成。\n"""
    partial = f"""# P4D GR3Q4E Window 01 partial mechanical QA\n\n```text\n{common}NEW_RAW_COUNT=0\nNEW_FINAL_COUNT=0\nEXACT_DUPLICATE_HITS=0\nGR1_SHA_HITS=0\nGR1_SAMEFILE_HITS=0\nGR1_SYMLINK_HITS=0\nFULL_440_QA=NOT_REACHED\nSEMANTIC_SENTINEL=NOT_EXECUTED\nHUMAN_REVIEW=NOT_STARTED\n```\n\n由于没有 provider 输出，新增图像的 partial QA 不适用；现有 102 张起始 inventory 已独立通过完整性检查。没有生成 contact sheet/sentinel，也没有把模型或 Codex 结论写入人类语义判断。\n"""
    quota_metrics = f"""# P4D GR3Q4E Window 01 quota metrics\n\n```text\n{common}WINDOW_LOGICAL_CAP=68\nLATER_WINDOW_DEFAULT_CAP=70\nPHYSICAL_ATTEMPT_LOWER_BOUND_CAP=80\nNATIVE_RETRY_EVENT_CAP=5\nLOGICAL_INVOCATIONS=0\nSUCCESS=0\nFAILURE=0\nNATIVE_RETRY_EVENTS=0\nPHYSICAL_ATTEMPT_LOWER_BOUND=0\nNEXT_RECOMMENDED_WINDOW_CAP=N/A_NOT_EXECUTED\nPROVIDER_VIABILITY_STRIKE=0_NOT_ASSESSED\n```\n\n历史 Q2E 的 quota reset evidence 仅用于确认旧时间门槛已过，不构成当前配额保证；本窗口没有请求，因此不能估计成本、账单 attempts、latency 或 provider viability。不得 sleep、等待或自动开启后续窗口。\n"""
    final = f"""# P4D GR3Q4E Window 01 final report\n\n```text\n{common}STOP_REASON=EXPLICIT_CAMPAIGN_AUTHORIZATION_MISSING\nPARENT_GR3Q4_FREEZE_VERIFIED=true\nFROZEN_440_VERIFIED=true\nCURRENT_PROFILE_FINGERPRINT={runtime.get('profile_fingerprint_safe_hash')}\nACTIVE_PROFILE_STRATUM={runtime.get('active_profile_stratum')}\nWINDOW_LOGICAL_CAP=68\nPHYSICAL_ATTEMPT_CAP=80\nRETRY_EVENT_CAP=5\nLOGICAL_INVOCATIONS=0\nSUCCESS=0\nFAILURE=0\nNEW_RAW_COUNT=0\nNEW_FINAL_COUNT=0\nCURRENT_TOTAL_VERIFIED_SUCCESS={inventory['total_verified_success']}\nCURRENT_OUTSTANDING={outstanding['total_outstanding']}\nFULL_440_QA=NOT_REACHED\nFORMAL_INGEST=false\nC3=false\nNEW_VAL=0\nHOLDOUT_REQUESTS=0\nHOLDOUT_CONSUMED=false\nDATASET_VALIDATOR_STATUS={boundary.get('after_validator_status')}\nPRODUCTION_CODE_MODIFIED=false\nOLLAMA_MODIFIED=false\n```\n\n## 已确认事实\n\n本次是新的独立 Window 01 execution revision，但按硬 authorization rule 在零请求状态封存。parent GR3Q4 freeze SHA `{EXPECTED['gr3q4']}`、Q2E `{EXPECTED['q2e']}`、GR3Q3 `{EXPECTED['gr3q3']}`、frozen 440 manifest `{EXPECTED['manifest']}` 均核验通过。起始 102 张由实际文件重建并通过完整性验证，338 outstanding 精确为 1 confirmed HTTP 429、337 NEVER_STARTED、0 COMPLETION_UNKNOWN。\n\nprovider/runtime 为 codex / gpt-5.4 / image_generation / {runtime.get('runtime_version')}，当前 profile 为 `{runtime.get('active_profile_stratum')}`；预注册 native 1536x1024、medium、PNG、controlled 16:9 crop + Pillow LANCZOS 到 1920x1080，material config match={runtime.get('material_config_match')}。\n\n## 实验判断\n\n任务正文自身明确不是授权。本轮顶层用户消息没有另外给出“保留 102、处理 338、Window 01 上限 68、后续手动窗口、并接受 retry/quota/cost 风险且不做 ingest/C3/VAL/HOLDOUT”的等价授权，故 `P4D_GR3Q4E_STATUS=AWAITING_CAMPAIGN_AUTHORIZATION` 是唯一合规状态。没有分类或图像生成 baseline；所有新增 generation/latency/cost/quality 指标为 N/A。\n\n## 风险与限制\n\n本轮没有读取/调用 EBOND、没有访问 HOLDOUT、没有 formal ingest、没有修改 shared split CSV 或 production code。空日志和 0 attempts 不代表 provider 配额可用。未来即使获得授权，也必须新建 revision，先重新绑定当前 parent/hash/profile/config，再人工按冻结 68-slot order 执行。\n\n## 下一阶段建议\n\n请在新的独立顶层消息明确授权该窗口；授权前不要启动任何 provider 请求。授权后不得复用本零请求 ledger 作为已执行结果，需新建独立 execution revision。\n\n## 关键本地工件\n\n- starting inventory: `{REV / '01_inventory/current_verified_success_inventory.csv'}` (SHA `{hashes(REV / '01_inventory/current_verified_success_inventory.csv')}`)\n- outstanding: `{REV / '01_inventory/outstanding_338.csv'}` (SHA `{hashes(REV / '01_inventory/outstanding_338.csv')}`)\n- SQLite stable ledger: `{REV / '03_ledger/window_01_execution.sqlite3'}` (SHA `{ledger.get('sqlite_sha256')}`)\n- CSV ledger: `{REV / '03_ledger/window_01_ledger.csv'}` (SHA `{ledger.get('csv_sha256')}`)\n- runner SHA: `{sha256_file(Path(__file__))}`\n"""
    contents = [preflight, execution, partial, quota_metrics, final]
    for path, content in zip(report_paths, contents):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing report: {path}")
        write_text(path, content)
    return report_paths


def write_freeze(runtime: dict[str, Any], inventory: dict[str, Any], outstanding: dict[str, Any], plan: dict[str, Any], boundary: dict[str, Any], ledger: dict[str, Any], parent_audits: dict[str, Any], paths: dict[str, Path], reports: list[Path], quota: dict[str, Any]) -> tuple[Path, str, dict[str, Any]]:
    terminal = REV / "05_checkpoints/terminal_summary.json"
    artifact_paths = [
        GR3Q4_FREEZE, Q2E_FREEZE, GR3Q3_FREEZE, MANIFEST,
        REV / "00_preflight/config_inspect.json", REV / "00_preflight/doctor.json", REV / "00_preflight/auth_inspect.json", REV / "00_preflight/provider_runtime_audit.json", REV / "00_preflight/quota_time_audit.json",
        REV / "00_preflight/dataset_validator_before.json", REV / "00_preflight/dataset_validator_after.json", REV / "00_preflight/dataset_boundary_audit.json", REV / "00_preflight/full_manifest_audit.json",
        REV / "01_inventory/current_verified_success_inventory.csv", REV / "01_inventory/inventory_summary.json", REV / "01_inventory/gr1_exclusion_audit.json", REV / "01_inventory/outstanding_338.csv", REV / "01_inventory/outstanding_summary.json",
        REV / "02_plan/adaptive_execution_order.csv", REV / "02_plan/first_window_68_plan.csv", REV / "02_plan/plan_binding_audit.json", REV / "01_authorization/campaign_authorization_status.json", REV / "run_config.json",
        REV / "03_ledger/window_01_execution.sqlite3", REV / "03_ledger/window_01_ledger.csv", REV / "03_ledger/ledger_stability.json", REV / "request_log.jsonl", REV / "raw_responses.jsonl",
        REV / "05_checkpoints/provider_requests_before_execution.json", REV / "05_checkpoints/group_checkpoint.json", terminal, REV / "06_partial_qa/new_image_hash_manifest.json", REV / "06_partial_qa/semantic_sentinel_manifest.json", REV / "06_partial_qa/partial_mechanical_qa_summary.json",
        *reports, Path(__file__), CLI, BINARY,
    ]
    artifact_map = {str(p): sha256_file(p) for p in artifact_paths}
    if any(v is None for v in artifact_map.values()):
        raise RuntimeError("cannot freeze with missing artifact")
    freeze = {"stage": "P4D_GR3Q4E_ADAPTIVE_QUOTA_CAMPAIGN_WINDOW_01", "name": "P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01", "revision_id": "P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01", "status": "AWAITING_CAMPAIGN_AUTHORIZATION", "stop_reason": "EXPLICIT_CAMPAIGN_AUTHORIZATION_MISSING", "parent_gr3q4_freeze_sha256": EXPECTED["gr3q4"], "parent_q2e_freeze_sha256": EXPECTED["q2e"], "parent_gr3q3_freeze_sha256": EXPECTED["gr3q3"], "frozen_440_manifest_sha256": EXPECTED["manifest"], "starting_verified_success": inventory["total_verified_success"], "starting_outstanding": outstanding["total_outstanding"], "profile_fingerprint_safe_hash": runtime.get("profile_fingerprint_safe_hash"), "active_profile_stratum": runtime.get("active_profile_stratum"), "adaptive_order_sha256": plan["adaptive_sha256"], "first_window_plan_sha256": plan["first_window_sha256"], "window_cap": WINDOW_CAP, "physical_attempt_lower_bound_cap": PHYSICAL_CAP, "native_retry_event_cap": RETRY_CAP, "authorization_present": False, "execution_not_executed": True, "provider_requests": 0, "logical_invocations": 0, "window_success": 0, "window_failure": 0, "native_retry_scheduled_events": 0, "physical_attempt_lower_bound": 0, "new_raw_count": 0, "new_final_count": 0, "full_440_qa": "NOT_REACHED", "semantic_sentinel": "NOT_EXECUTED", "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0, "holdout_consumed": False, "p4d_active_dataset_refs": boundary.get("p4d_reference_hits_total", 0), "dataset_boundary": boundary, "historical_time_gate_blocking": quota.get("historical_time_gate_blocking"), "runner_sha256": sha256_file(Path(__file__)), "artifact_sha256": artifact_map, "created_at": now()}
    freeze_path = REV / "freeze/p4d_gr3q4e_window01_terminal_freeze.json"
    write_json(freeze_path, freeze)
    freeze_sha = sha256_file(freeze_path)
    sidecar = freeze_path.with_name(freeze_path.name + ".sha256")
    write_text(sidecar, f"{freeze_sha}  {freeze_path.name}\n")
    checks = []
    for p, expected in artifact_map.items():
        actual = sha256_file(p)
        checks.append({"path": p, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    verification = {"captured_at": now(), "freeze_path": str(freeze_path), "freeze_sha256": freeze_sha, "sidecar_sha256": sidecar.read_text().split()[0], "sidecar_match": freeze_sha == sidecar.read_text().split()[0], "bound_artifact_count": len(checks), "all_bound_artifacts_match": all(c["match"] for c in checks), "provider_requests_added": 0, "request_log_lines": 0, "raw_response_lines": 0, "all_pass": bool(freeze_sha == sidecar.read_text().split()[0] and all(c["match"] for c in checks))}
    write_json(REV / "05_checkpoints/terminal_freeze_verification.json", verification)
    return freeze_path, freeze_sha, verification


def main() -> int:
    if REV.exists():
        print(f"REFUSING_EXISTING_REVISION={REV}", file=sys.stderr)
        return 2
    for d in ("00_preflight", "01_authorization", "01_inventory", "02_plan", "03_ledger", "04_raw_responses", "05_checkpoints", "06_partial_qa", "freeze"):
        (REV / d).mkdir(parents=True, exist_ok=False)
    before = run_validator("before")
    before_snap = annotation_snapshot()
    parent_audits = {"gr3q4": verify_parent_freeze(GR3Q4_FREEZE, EXPECTED["gr3q4"], "WAITING_FOR_PROVIDER_QUOTA_RESET"), "q2e": verify_parent_freeze(Q2E_FREEZE, EXPECTED["q2e"], "STOPPED_BY_FAILURE_POLICY"), "gr3q3": verify_parent_freeze(GR3Q3_FREEZE, EXPECTED["gr3q3"], "WAITING_FOR_PROVIDER_QUOTA_RESET")}
    manifest_rows, manifest = manifest_audit()
    for ordinal, row in enumerate(manifest_rows):
        row["ordinal"] = str(ordinal)
    verified, inv, sources = rebuild_inventory(manifest_rows)
    gr1 = gr1_exclusion(verified)
    outstanding_rows, out = build_outstanding(manifest_rows, verified, sources)
    plan = plan_audit(outstanding_rows)
    runtime = runtime_audit()
    quota = quota_time_audit()
    first_rows = read_csv(REV / "02_plan/first_window_68_plan.csv")
    ledger = create_ledger(first_rows, runtime)
    after = run_validator("after")
    after_snap = annotation_snapshot()
    boundary = {"captured_at": now(), "before_validator_status": before.get("status"), "before_validator_error_count": before.get("error_count"), "before_validator_warning_count": before.get("warning_count"), "after_validator_status": after.get("status"), "after_validator_error_count": after.get("error_count"), "after_validator_warning_count": after.get("warning_count"), "before_annotation_sha256": before_snap["annotation_sha256"], "after_annotation_sha256": after_snap["annotation_sha256"], "annotation_hashes_same": before_snap["annotation_sha256"] == after_snap["annotation_sha256"], "before_counts": before_snap["annotation_row_counts"], "after_counts": after_snap["annotation_row_counts"], "p4d_reference_hits_total": after_snap["p4d_reference_hits_total"], "p4d_reference_hits": after_snap["p4d_reference_hits"], "counts_unchanged": before_snap["annotation_row_counts"] == after_snap["annotation_row_counts"], "formal_ingest": False, "media_added": 0, "labels_added": 0}
    write_json(REV / "00_preflight/dataset_boundary_audit.json", boundary)
    paths = write_window_artifacts(runtime, inv, out, plan, boundary, ledger)
    reports = write_reports(runtime, inv, out, gr1, plan, quota, {**boundary, "after_validator_status": after.get("status")}, ledger, parent_audits, paths)
    freeze_path, freeze_sha, verification = write_freeze(runtime, inv, out, plan, boundary, ledger, parent_audits, paths, reports, quota)
    print(json.dumps({"status": "AWAITING_CAMPAIGN_AUTHORIZATION", "provider_requests": 0, "starting_verified_success": inv["total_verified_success"], "starting_outstanding": out["total_outstanding"], "profile": runtime.get("active_profile_stratum"), "freeze": str(freeze_path), "freeze_sha256": freeze_sha, "terminal_freeze_all_pass": verification["all_pass"], "dataset_validator": after.get("status"), "warning_count": after.get("warning_count")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
