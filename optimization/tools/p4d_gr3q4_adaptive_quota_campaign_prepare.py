#!/usr/bin/env python3
"""Prepare the P4D GR3Q4 adaptive quota-window campaign.

This is a zero-provider-request preparation boundary.  It rebuilds the 102
verified current inventory from immutable parent evidence, derives the exact
338-slot outstanding set, produces a deterministic group-aware deficit-balanced
order and first-window plan, captures read-only runtime/time evidence, writes a
campaign authorization packet with ``authorized=false``, and seals a new
campaign revision.  It never calls ``images generate``.
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
EXEC = GR3 / "06_execution/quota_campaign_window_20260828_03"
PRE = EXEC / "00_preflight"
INV = EXEC / "01_inventory"
ORDER = EXEC / "02_order"
GOV = EXEC / "03_governance"
AUTH = EXEC / "04_authorization"
WINDOW = EXEC / "05_window_01"
WLEDGER = WINDOW / "ledger"
WPRE = WINDOW / "preflight"
WQA = WINDOW / "qa"
FREEZE = EXEC / "freeze"

MANIFEST = GR3 / "03_fullregen_plan/full_regen_prompt_manifest.csv"
GR3E_INV = GR3 / "06_execution/authorized_20260827_01/06_full_qa/current_generation_inventory.csv"
GR3E_LEDGER = GR3 / "06_execution/authorized_20260827_01/03_ledger/execution_ledger.csv"
Q2E_ROOT = GR3 / "06_execution/profile_stratified_recovery_20260828_01"
Q2E_LEDGER = Q2E_ROOT / "03_ledger/execution_ledger.csv"
Q2E_FREEZE = Q2E_ROOT / "freeze/p4d_gr3q2e_terminal_freeze.json"
Q2E_RAW_FAILURE = Q2E_ROOT / "04_raw_responses/P4D_GR3Q2E_RECOVERY_0004_PF_P4D_HN_KNEEL_G009_V03.json"
Q2E_RUN_CONFIG = Q2E_ROOT / "02_runner/run_config.json"
GR3Q3_ROOT = GR3 / "06_execution/quota_window_recovery_20260828_02"
GR3Q3_FREEZE = GR3Q3_ROOT / "freeze/p4d_gr3q3_terminal_freeze.json"
GR3Q3_RUNTIME = GR3Q3_ROOT / "00_preflight/provider_runtime_audit.json"
GR3Q3_QUOTA = GR3Q3_ROOT / "00_preflight/quota_reset_evidence.json"
GR1_QA = ROOT / "08_p4d_new_hard_negative_dev_revision/03_intake_audit/gr1_independent_mechanical_qa.csv"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")
SELF = Path(__file__).resolve()

EXPECTED_Q2E_FREEZE_SHA = "9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44"
EXPECTED_GR3Q3_FREEZE_SHA = "7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697"
EXPECTED_MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
EXPECTED_PARENT_FAILURE_SHA = "a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99"
EXPECTED_WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
EXPECTED_BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
EXPECTED_PROFILE_A = "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe"
EXPECTED_PROFILE_B = "d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190"
FAILED_PROMPT = "PF_P4D_HN_KNEEL_G009_V03"
FINAL_SIZE = (1920, 1080)
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
FIRST_WINDOW_CAP = 68
LATER_WINDOW_CAP = 70
PHYSICAL_GUARD = 80
RETRY_EVENT_GUARD = 5
MAX_WINDOWS = 5
SAFETY_MARGIN_SECONDS = 653

CAMPAIGN_AUTH_TEXT = (
    "我明确授权 person_fallen P4D_GR3 quota-window generation campaign：保留当前已经完整性验证通过的102张当前GR3 generation-lineage图像，"
    "继续处理冻结的338个 outstanding slots。授权最多5个由我手动启动的独立 quota-window execution revisions；第一个 window 最多68个 logical invocations，"
    "后续每个 window 最多70个；每个 window concurrency=1、outer_retry=false，同时接受 GPT Image 2 native max_retries=3、精确费用未知以及 quota/成本风险。"
    "任何 window 中 returned 429/401/403/5xx/timeout/connection error 立即停止；observed physical-attempt lower bound 达80或 native retry events 达5也主动停止。"
    "每个 window 必须独立 freeze，禁止后台等待、cron 或自动跨 window 执行。该授权只覆盖图像生成，不授权 formal ingest、C3、NEW_VAL、HOLDOUT 或生产集成。"
)


def iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


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
        try:
            raw = json.loads(proc.stdout)
        except Exception:
            raw = {"parse_error": True, "stdout_tail": sanitize_text(proc.stdout[-12000:])}
        record = {
            "label": label,
            "command": ["node", "<gpt-image-2-skill>", "--json", "--provider", "codex", *args],
            "returncode": proc.returncode,
            "payload": redact(raw),
            "stderr": sanitize_text(proc.stderr[-12000:]),
            "captured_at": iso(),
            "image_generation_provider_requests": 0,
        }
    except Exception as exc:
        raw = {"exception": f"{type(exc).__name__}: {exc}"}
        record = {"label": label, "command": ["node", "<gpt-image-2-skill>", "--json", "--provider", "codex", *args], "returncode": None, "payload": raw, "stderr": "", "captured_at": iso(), "image_generation_provider_requests": 0}
    write_json(PRE / f"{label}.json", record)
    return {"raw": raw, "record": record}


def q2e_freeze_audit() -> dict[str, Any]:
    d = read_json(Q2E_FREEZE, {}) or {}
    checks = []
    for path_text, expected in (d.get("artifact_sha256") or {}).items():
        actual = sha256_file(Path(path_text))
        checks.append({"path": path_text, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    actual = sha256_file(Q2E_FREEZE)
    result = {"captured_at": iso(), "path": str(Q2E_FREEZE), "expected_sha256": EXPECTED_Q2E_FREEZE_SHA, "actual_sha256": actual, "sidecar_sha256": sidecar_value(Q2E_FREEZE), "sidecar_match": actual == sidecar_value(Q2E_FREEZE) == EXPECTED_Q2E_FREEZE_SHA, "status": d.get("status"), "stage": d.get("stage"), "terminal_counts": (d.get("terminal") or {}).get("counts", {}), "bound_artifact_count": len(checks), "bound_artifacts": checks, "all_bound_artifacts_match": all(c["match"] for c in checks), "initial_binding_error_freeze_not_used": True}
    result["all_match"] = bool(result["sidecar_match"] and result["status"] == "STOPPED_BY_FAILURE_POLICY" and result["all_bound_artifacts_match"])
    write_json(PRE / "q2e_parent_freeze_audit.json", result)
    return result


def gr3q3_freeze_audit() -> dict[str, Any]:
    d = read_json(GR3Q3_FREEZE, {}) or {}
    checks = []
    for path_text, expected in (d.get("artifact_sha256") or {}).items():
        actual = sha256_file(Path(path_text))
        checks.append({"path": path_text, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    actual = sha256_file(GR3Q3_FREEZE)
    result = {"captured_at": iso(), "path": str(GR3Q3_FREEZE), "expected_sha256": EXPECTED_GR3Q3_FREEZE_SHA, "actual_sha256": actual, "sidecar_sha256": sidecar_value(GR3Q3_FREEZE), "sidecar_match": actual == sidecar_value(GR3Q3_FREEZE) == EXPECTED_GR3Q3_FREEZE_SHA, "status": d.get("status"), "stage": d.get("stage"), "current_success": (d.get("current_success_inventory") or {}).get("total"), "outstanding": (d.get("outstanding_inventory") or {}).get("total"), "bound_artifact_count": len(checks), "bound_artifacts": checks, "all_bound_artifacts_match": all(c["match"] for c in checks)}
    result["all_match"] = bool(result["sidecar_match"] and result["status"] == "WAITING_FOR_PROVIDER_QUOTA_RESET" and result["all_bound_artifacts_match"])
    write_json(PRE / "gr3q3_parent_freeze_audit.json", result)
    return result


def manifest_audit() -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = read_csv(MANIFEST)
    mismatches = []
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        actual = sha256_file(Path(row.get("original_prompt_path", "")))
        if actual != row.get("prompt_sha256"):
            mismatches.append({"prompt_id": row.get("prompt_id"), "expected": row.get("prompt_sha256"), "actual": actual})
        groups[row.get("group_id", "")].add(row.get("planned_internal_split", ""))
    value = {"captured_at": iso(), "path": str(MANIFEST), "expected_sha256": EXPECTED_MANIFEST_SHA, "actual_sha256": sha256_file(MANIFEST), "rows": len(rows), "unique_prompt_ids": len({r.get("prompt_id") for r in rows}), "unique_groups": len({r.get("group_id") for r in rows}), "prompt_byte_mismatch": len(mismatches), "prompt_byte_mismatches": mismatches, "role_counts": dict(Counter(r.get("target_role") for r in rows)), "split_counts": dict(Counter(r.get("planned_internal_split") for r in rows)), "cross_split_groups": sorted(g for g, s in groups.items() if len(s) > 1), "cross_split_group_count": sum(len(s) > 1 for s in groups.values())}
    value["all_match"] = bool(value["actual_sha256"] == EXPECTED_MANIFEST_SHA and value["rows"] == 440 and value["unique_prompt_ids"] == 440 and value["unique_groups"] == 88 and value["prompt_byte_mismatch"] == 0 and value["cross_split_group_count"] == 0 and value["role_counts"] == {"hard_negative": 300, "positive": 100, "ordinary_negative": 40} and value["split_counts"] == {"NEW_DESIGN": 265, "NEW_SCREEN": 175})
    write_json(PRE / "full_manifest_audit.json", value)
    return rows, value


def load_q2e_responses() -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted((Q2E_ROOT / "04_raw_responses").glob("*.json")):
        d = read_json(p, {}) or {}
        if d.get("prompt_id"):
            out[d["prompt_id"]] = d
    return out


def build_inventory(manifest_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    by_id = {r.get("prompt_id"): r for r in manifest_rows}
    gr3e = {r.get("prompt_id"): r for r in read_csv(GR3E_INV)}
    gr3e_ledger = {r.get("logical_slot_id"): r for r in read_csv(GR3E_LEDGER)}
    q2e = {r.get("logical_slot_id"): r for r in read_csv(Q2E_LEDGER)}
    q2e_resp = load_q2e_responses()
    source_rows: list[tuple[str, str, dict[str, str], dict[str, str], dict[str, Any]]] = []
    source_rows.extend((pid, "PROFILE_A", src, gr3e_ledger.get(pid, {}), {}) for pid, src in gr3e.items() if src.get("state") == "SUCCESS")
    source_rows.extend((pid, "PROFILE_B", src, src, q2e_resp.get(pid, {})) for pid, src in q2e.items() if src.get("state") == "SUCCESS_PROFILE_B")
    result, issues, seen = [], [], set()
    index_by_id = {r.get("prompt_id"): i for i, r in enumerate(manifest_rows)}
    for pid, profile, src, ledger, resp in source_rows:
        m = by_id.get(pid)
        if not m:
            issues.append({"prompt_id": pid, "issue": "not_in_manifest"})
            continue
        if pid in seen:
            issues.append({"prompt_id": pid, "issue": "duplicate_source"})
            continue
        seen.add(pid)
        if profile == "PROFILE_A":
            raw_text, final_text = src.get("raw_path", ""), src.get("final_path", "")
            raw_expected, final_expected = src.get("raw_sha256", ""), src.get("final_sha256", "")
            request_id, http_status, parent_state, parent_revision, profile_name = ledger.get("provider_request_id", ""), ledger.get("http_status", ""), "SUCCESS", "P4D_GR3E_AUTHORIZED_20260827_01", "GR3E_PROFILE_A"
        else:
            raw_text = resp.get("raw_path") or str(BATCH / "generated_raw" / f"{pid}.png")
            final_text = resp.get("final_path") or str(BATCH / "final" / f"{pid}.png")
            raw_expected, final_expected = src.get("raw_sha256", ""), src.get("final_sha256", "")
            request_id, http_status, parent_state, parent_revision, profile_name = src.get("provider_request_id", ""), src.get("http_status", ""), src.get("parent_state", ""), "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY_20260828_01", "GR3Q2_PROFILE_B"
        raw_path, final_path = Path(raw_text), Path(final_text)
        raw_actual, final_actual = sha256_file(raw_path), sha256_file(final_path)
        raw_ok, _, raw_err = verify_image(raw_path)
        final_ok, final_size, final_err = verify_image(final_path)
        raw_link, final_link = raw_path.is_symlink(), final_path.is_symlink()
        samefile = False
        if raw_path.is_file() and final_path.is_file():
            try:
                samefile = os.path.samefile(raw_path, final_path)
            except OSError:
                pass
        source_split = src.get("planned_split") or src.get("planned_internal_split")
        matches = all([m.get("group_id") == src.get("group_id", m.get("group_id")), m.get("variant_id") == src.get("variant_id", m.get("variant_id")), m.get("target_role") == src.get("target_role", m.get("target_role")), m.get("taxonomy") == src.get("taxonomy", m.get("taxonomy")), m.get("planned_internal_split") == source_split, m.get("prompt_sha256") == src.get("prompt_sha256", m.get("prompt_sha256"))])
        ok = bool(raw_actual == raw_expected and final_actual == final_expected and raw_ok and final_ok and final_size == FINAL_SIZE and not raw_link and not final_link and not samefile and matches)
        if not ok:
            issues.append({"prompt_id": pid, "profile": profile_name, "raw_error": raw_err, "final_error": final_err, "raw_sha_match": raw_actual == raw_expected, "final_sha_match": final_actual == final_expected, "final_size": final_size, "symlink": raw_link or final_link, "samefile": samefile, "manifest_match": matches})
        result.append({"prompt_id": pid, "ordinal": index_by_id[pid], "group_id": m.get("group_id"), "variant_id": m.get("variant_id"), "planned_split": m.get("planned_internal_split"), "target_role": m.get("target_role"), "taxonomy": m.get("taxonomy"), "event_label": m.get("target_event_label"), "prompt_sha256": m.get("prompt_sha256"), "generation_profile_stratum": profile_name, "parent_revision": parent_revision, "parent_state": parent_state, "parent_http_status": http_status, "parent_request_id": request_id, "raw_path": str(raw_path), "final_path": str(final_path), "raw_sha256_expected": raw_expected, "raw_sha256_actual": raw_actual or "", "final_sha256_expected": final_expected, "final_sha256_actual": final_actual or "", "raw_pillow_pass": raw_ok, "final_pillow_pass": final_ok, "final_width": final_size[0] if final_size else "", "final_height": final_size[1] if final_size else "", "raw_final_samefile": samefile, "symlink_hit": bool(raw_link or final_link), "verified_success": ok})
    verified = [r for r in result if r["verified_success"]]
    summary = {"captured_at": iso(), "expected_total": 102, "total_verified_success": len(verified), "unique_prompt_ids": len({r["prompt_id"] for r in verified}), "profile_strata": dict(Counter(r["generation_profile_stratum"] for r in verified)), "role_counts": dict(Counter(r["target_role"] for r in verified)), "split_counts": dict(Counter(r["planned_split"] for r in verified)), "taxonomy_counts": dict(Counter(r["taxonomy"] for r in verified)), "inventory_issues": issues, "all_verified": len(verified) == 102 and len({r["prompt_id"] for r in verified}) == 102 and not issues}
    fields = list(result[0].keys()) if result else ["prompt_id"]
    write_csv(INV / "current_verified_success_inventory.csv", fields, sorted(result, key=lambda x: int(x["ordinal"])))
    summary["inventory_csv_sha256"] = sha256_file(INV / "current_verified_success_inventory.csv")
    write_json(INV / "inventory_summary.json", summary)
    return verified, summary, {"manifest_by_id": by_id, "gr3e": gr3e, "q2e": q2e, "q2e_response": q2e_resp}


def gr1_audit(current: list[dict[str, Any]], manifest_rows: list[dict[str, str]]) -> dict[str, Any]:
    old_rows = read_csv(GR1_QA)
    old_hashes, old_paths = set(), []
    for r in old_rows:
        old_hashes.update(v for k in ("raw_sha256", "final_sha256") if (v := r.get(k)))
        old_paths.extend(Path(v) for k in ("raw_path", "final_path") if (v := r.get(k)))
    sha_hits, same_hits, symlink_hits = [], [], []
    for r in current:
        for kind in ("raw", "final"):
            digest = r.get(f"{kind}_sha256_actual")
            if digest in old_hashes:
                sha_hits.append({"prompt_id": r["prompt_id"], "kind": kind, "sha256": digest})
        for text in (r.get("raw_path", ""), r.get("final_path", "")):
            p = Path(text)
            if p.is_symlink():
                symlink_hits.append({"prompt_id": r["prompt_id"], "path": text})
            for old in old_paths:
                if p.is_file() and old.is_file():
                    try:
                        if os.path.samefile(p, old):
                            same_hits.append({"prompt_id": r["prompt_id"], "current_path": text, "gr1_path": str(old)})
                    except OSError:
                        pass
    value = {"captured_at": iso(), "gr1_qa_path": str(GR1_QA), "gr1_qa_rows": len(old_rows), "gr1_historical_pass_rows": sum(r.get("status") == "PASS" for r in old_rows), "manifest_gr1_reuse_values": sorted({r.get("gr1_images_reused") for r in manifest_rows}), "GR1_IMAGES_REUSED": 0, "GR1_SHA_HITS": len(sha_hits), "GR1_SAMEFILE_HITS": len(same_hits), "GR1_SYMLINK_HITS": len(symlink_hits), "sha_hits": sha_hits, "samefile_hits": same_hits, "symlink_hits": symlink_hits, "all_excluded": not sha_hits and not same_hits and not symlink_hits}
    write_json(INV / "gr1_exclusion_audit.json", value)
    return value


def build_outstanding(manifest_rows: list[dict[str, str]], verified: list[dict[str, Any]], sources: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    success = {r["prompt_id"] for r in verified}
    ordered = [r for r in manifest_rows if r.get("prompt_id") == FAILED_PROMPT] + [r for r in manifest_rows if r.get("prompt_id") != FAILED_PROMPT]
    rows = []
    for m in ordered:
        pid = m.get("prompt_id")
        if pid in success:
            continue
        g = sources["gr3e"].get(pid, {})
        q = sources["q2e"].get(pid, {})
        if pid == FAILED_PROMPT and q.get("state") == "FAILED_CONFIRMED_PROFILE_B":
            state, req, http, err = "FAILED_CONFIRMED_HTTP_429", q.get("provider_request_id") or "P4D_GR3Q2E_RECOVERY_0004_PF_P4D_HN_KNEEL_G009_V03", q.get("http_status") or "429", q.get("error_code") or "http_error"
        elif g.get("state") == "NOT_STARTED":
            state, req, http, err = "NEVER_STARTED", "", "", ""
        else:
            state, req, http, err = "COMPLETION_UNKNOWN", "", "", "unrecognized_parent_state"
        rows.append({"execution_candidate_order": len(rows) + 1, "prompt_id": pid, "original_manifest_ordinal": manifest_rows.index(m), "group_id": m.get("group_id"), "variant_id": m.get("variant_id"), "role": m.get("target_role"), "taxonomy": m.get("taxonomy"), "planned_split": m.get("planned_internal_split"), "prompt_path": m.get("original_prompt_path"), "prompt_sha256": m.get("prompt_sha256"), "parent_state": state, "parent_request_id": req, "parent_http_status": http, "parent_error_code": err})
    counts = Counter(r["parent_state"] for r in rows)
    value = {"captured_at": iso(), "total_outstanding": len(rows), "expected_outstanding": 338, "failed_confirmed_http_429": counts.get("FAILED_CONFIRMED_HTTP_429", 0), "never_started": counts.get("NEVER_STARTED", 0), "completion_unknown": counts.get("COMPLETION_UNKNOWN", 0), "role_counts": dict(Counter(r["role"] for r in rows)), "taxonomy_counts": dict(Counter(r["taxonomy"] for r in rows)), "split_counts": dict(Counter(r["planned_split"] for r in rows)), "first_prompt_id": rows[0]["prompt_id"] if rows else None, "exact_expected_state": len(rows) == 338 and counts.get("FAILED_CONFIRMED_HTTP_429", 0) == 1 and counts.get("NEVER_STARTED", 0) == 337 and counts.get("COMPLETION_UNKNOWN", 0) == 0}
    write_csv(INV / "outstanding_338.csv", list(rows[0].keys()) if rows else ["prompt_id"], rows)
    value["outstanding_csv_sha256"] = sha256_file(INV / "outstanding_338.csv")
    write_json(INV / "outstanding_summary.json", value)
    return rows, value


def adaptive_order(manifest_rows: list[dict[str, str]], verified: list[dict[str, Any]], outstanding: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in manifest_rows:
        by_group[r["group_id"]].append(r)
    success_ids = {r["prompt_id"] for r in verified}
    group_info = {}
    issues = []
    for ordinal, (gid, rows) in enumerate(by_group.items()):
        roles, taxes, splits = {r["target_role"] for r in rows}, {r["taxonomy"] for r in rows}, {r["planned_internal_split"] for r in rows}
        if len(roles) != 1 or len(taxes) != 1 or len(splits) != 1:
            issues.append({"group_id": gid, "issue": "non_uniform_group_dimensions"})
        group_info[gid] = {"rows": rows, "original_group_ordinal": min(int(next((r.get("ordinal", i) for i, r in enumerate(manifest_rows) if r.get("prompt_id") == rows[0].get("prompt_id")), ordinal)) for _ in [0]), "role": next(iter(roles)), "taxonomy": next(iter(taxes)), "split": next(iter(splits)), "success": sum(r["prompt_id"] in success_ids for r in rows), "outstanding": sum(r["prompt_id"] not in success_ids for r in rows)}
    partial = [g for g, info in group_info.items() if info["success"] > 0 and info["outstanding"] > 0]
    full = [g for g, info in group_info.items() if info["success"] == 0 and info["outstanding"] > 0]
    target_role = Counter(r["target_role"] for r in manifest_rows)
    target_tax = Counter(r["taxonomy"] for r in manifest_rows)
    target_split = Counter(r["planned_internal_split"] for r in manifest_rows)
    current_role = Counter(r["target_role"] for r in verified)
    current_tax = Counter(r["taxonomy"] for r in verified)
    current_split = Counter(r["planned_split"] for r in verified)
    scheduled_role, scheduled_tax, scheduled_split = Counter(current_role), Counter(current_tax), Counter(current_split)
    out_by_id = {r["prompt_id"]: r for r in outstanding}
    result = []
    group_order = []
    group_schedule = 0

    def add_slot(m: dict[str, str], reason: str, score: tuple[float, float, float, float, float] | None, group_rank: int) -> None:
        pid = m["prompt_id"]
        o = out_by_id[pid]
        row = {"execution_order": len(result) + 1, "prompt_id": pid, "group_id": m["group_id"], "variant_id": m["variant_id"], "role": m["target_role"], "taxonomy": m["taxonomy"], "planned_split": m["planned_internal_split"], "original_manifest_ordinal": manifest_rows.index(m), "current_group_success_count": group_info[m["group_id"]]["success"], "current_group_outstanding_count": group_info[m["group_id"]]["outstanding"], "parent_state": o["parent_state"], "selection_reason": reason, "group_selection_order": group_rank, "score_sum": f"{score[0]:.12f}" if score else "", "score_max": f"{score[1]:.12f}" if score else ""}
        result.append(row)
        scheduled_role[m["target_role"]] += 1
        scheduled_tax[m["taxonomy"]] += 1
        scheduled_split[m["planned_internal_split"]] += 1

    # Partial groups first, with the known confirmed failure first when present.
    for gid in sorted(partial, key=lambda g: (group_info[g]["original_group_ordinal"], g)):
        group_schedule += 1
        group_order.append({"group_id": gid, "kind": "PARTIAL_GROUP", "original_group_ordinal": group_info[gid]["original_group_ordinal"], "starting_success": group_info[gid]["success"], "starting_outstanding": group_info[gid]["outstanding"]})
        rows = [r for r in group_info[gid]["rows"] if r["prompt_id"] not in success_ids]
        rows.sort(key=lambda r: (0 if r["prompt_id"] == FAILED_PROMPT else 1, manifest_rows.index(r)))
        for r in rows:
            add_slot(r, "partial_group_completion" + (";confirmed_429_first" if r["prompt_id"] == FAILED_PROMPT else ""), None, group_schedule)

    remaining = set(full)
    while remaining:
        def score(gid: str) -> tuple[float, float, float, float, float]:
            info = group_info[gid]
            rr = max(0.0, (target_role[info["role"]] - scheduled_role[info["role"]]) / target_role[info["role"]])
            tr = max(0.0, (target_tax[info["taxonomy"]] - scheduled_tax[info["taxonomy"]]) / target_tax[info["taxonomy"]])
            sr = max(0.0, (target_split[info["split"]] - scheduled_split[info["split"]]) / target_split[info["split"]])
            return (rr + tr + sr, max(rr, tr, sr), rr, tr, sr)
        best = sorted(remaining, key=lambda g: (-score(g)[0], -score(g)[1], -score(g)[2], -score(g)[3], -score(g)[4], group_info[g]["original_group_ordinal"], g))[0]
        sc = score(best)
        group_schedule += 1
        info = group_info[best]
        group_order.append({"group_id": best, "kind": "FULL_OUTSTANDING_GROUP", "original_group_ordinal": info["original_group_ordinal"], "starting_success": info["success"], "starting_outstanding": info["outstanding"], "score_sum": round(sc[0], 12), "score_max": round(sc[1], 12), "role_deficit_ratio": round(sc[2], 12), "taxonomy_deficit_ratio": round(sc[3], 12), "split_deficit_ratio": round(sc[4], 12)})
        reason = f"deficit_balanced_round_robin;role={sc[2]:.6f};taxonomy={sc[3]:.6f};planned_split={sc[4]:.6f};score_sum={sc[0]:.6f}"
        for r in sorted(info["rows"], key=lambda x: manifest_rows.index(x)):
            add_slot(r, reason, sc, group_schedule)
        remaining.remove(best)

    expected_ids = {r["prompt_id"] for r in outstanding}
    order_summary = {"captured_at": iso(), "algorithm": "partial_groups_first_then_full_groups_deficit_balanced_round_robin", "tie_break": ["original_group_ordinal", "group_id"], "starting_success": {"total": len(verified), "role": dict(current_role), "taxonomy": dict(current_tax), "planned_split": dict(current_split)}, "frozen_targets": {"role": dict(target_role), "taxonomy": dict(target_tax), "planned_split": dict(target_split)}, "partial_group_count": len(partial), "partial_groups": [group_order[i] for i in range(len(partial))], "group_order": group_order, "adaptive_order_rows": len(result), "adaptive_order_unique_prompt_ids": len({r["prompt_id"] for r in result}), "first_order_prompt_id": result[0]["prompt_id"] if result else None, "order_exact_outstanding": len(result) == len(expected_ids) == 338 and {r["prompt_id"] for r in result} == expected_ids and not issues, "group_issues": issues}
    write_csv(ORDER / "adaptive_execution_order.csv", list(result[0].keys()) if result else ["execution_order", "prompt_id"], result)
    order_summary["adaptive_order_sha256"] = sha256_file(ORDER / "adaptive_execution_order.csv")
    window_rows = result[:FIRST_WINDOW_CAP]
    write_csv(ORDER / "first_window_68_plan.csv", ["window_planned_order", "window_id"] + [k for k in result[0].keys() if k not in {"execution_order", "window_planned_order", "window_id"}], [{"window_planned_order": i + 1, "window_id": "P4D_GR3Q4_WINDOW_01", **{k: v for k, v in row.items() if k not in {"execution_order"}}} for i, row in enumerate(window_rows)])
    order_summary["first_window"] = {"cap": FIRST_WINDOW_CAP, "planned_rows": len(window_rows), "planned_group_count": len({r["group_id"] for r in window_rows}), "planned_role_counts": dict(Counter(r["role"] for r in window_rows)), "planned_taxonomy_counts": dict(Counter(r["taxonomy"] for r in window_rows)), "planned_split_counts": dict(Counter(r["planned_split"] for r in window_rows)), "first_prompt_id": window_rows[0]["prompt_id"] if window_rows else None, "last_prompt_id": window_rows[-1]["prompt_id"] if window_rows else None, "partial_group_rows_in_window": sum(r["current_group_outstanding_count"] < 5 for r in window_rows)}
    write_json(ORDER / "adaptive_order_summary.json", order_summary)
    return result, order_summary


def quota_time_audit() -> tuple[dict[str, Any], dict[str, Any]]:
    q = read_json(GR3Q3_QUOTA, {}) or {}
    reset_epoch = q.get("resets_at_epoch")
    reset = datetime.fromtimestamp(int(reset_epoch), timezone.utc) if reset_epoch else None
    not_before = reset + timedelta(seconds=SAFETY_MARGIN_SECONDS) if reset else None
    evidence = {"captured_at": iso(), "source_path": str(GR3Q3_QUOTA), "source_sha256": sha256_file(GR3Q3_QUOTA), "parent_raw_failure_sha256": q.get("parent_raw_sha256"), "provider_error_type": q.get("provider_error_type"), "resets_at_epoch": reset_epoch, "resets_at_utc": reset.isoformat() if reset else None, "resets_at_local": reset.astimezone(LOCAL_TZ).isoformat() if reset else None, "resets_in_seconds": q.get("resets_in_seconds"), "safety_margin_seconds": SAFETY_MARGIN_SECONDS, "not_before_utc": not_before.isoformat() if not_before else None, "not_before_local": not_before.astimezone(LOCAL_TZ).isoformat() if not_before else None, "evidence_matches_expected": bool(q.get("parent_raw_sha256") == EXPECTED_PARENT_FAILURE_SHA and q.get("provider_error_type") == "usage_limit_reached" and reset_epoch == 1787914147)}
    write_json(PRE / "quota_window_evidence.json", evidence)
    now_local = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    gate = {"captured_at": iso(), "current_utc": now_local.astimezone(timezone.utc).isoformat(), "current_local": now_local.isoformat(), "not_before_utc": evidence["not_before_utc"], "not_before_local": evidence["not_before_local"], "time_gate_pass": bool(not_before and now_local >= not_before), "provider_requests": 0, "status_if_not_pass": "WAITING_FOR_PROVIDER_QUOTA_RESET"}
    write_json(PRE / "time_gate.json", gate)
    return evidence, gate


def provider_runtime_audit() -> dict[str, Any]:
    config = run_cli("config_inspect", ["config", "inspect"])
    doctor = run_cli("doctor", ["doctor"])
    auth = run_cli("auth_inspect", ["auth", "inspect"])
    help_result = run_cli("images_generate_help", ["images", "generate", "--help"])
    d = doctor["raw"] if isinstance(doctor["raw"], dict) else {}
    a = auth["raw"] if isinstance(auth["raw"], dict) else {}
    codex = ((d.get("providers") or {}).get("codex") or {})
    auth_codex = ((a.get("providers") or {}).get("codex") or {})
    auth_obj = codex.get("auth") or {}
    account = str(auth_obj.get("account_id") or auth_codex.get("account_id") or "")
    user = str(auth_obj.get("chatgpt_user_id") or auth_codex.get("chatgpt_user_id") or "")
    profile = hashlib.sha256(f"account={account}|user={user}".encode()).hexdigest() if account or user else None
    if profile == EXPECTED_PROFILE_A:
        stratum = "PROFILE_A_RESTORED"
    elif profile == EXPECTED_PROFILE_B:
        stratum = "PROFILE_B"
    else:
        stratum = "UNKNOWN_NEW_PROFILE_STRATUM"
    selection, defaults, endpoint, retry = d.get("provider_selection") or {}, d.get("defaults") or {}, codex.get("endpoint") or {}, d.get("retry_policy") or {}
    value = {"captured_at": iso(), "requested_provider": "codex", "resolved_provider": selection.get("resolved"), "provider": "codex", "request_model": defaults.get("codex_model"), "generation_backend": "image_generation", "runtime_version": d.get("version"), "wrapper_path": str(CLI), "wrapper_sha256": sha256_file(CLI), "binary_path": str(BINARY), "binary_sha256": sha256_file(BINARY), "native_retry_policy": retry, "native_max_retries": retry.get("max_retries"), "outer_retry": False, "auth_ready": bool(auth_obj.get("ready") or auth_codex.get("ready")), "endpoint_reachable": bool(endpoint.get("reachable")), "tls_ok": bool(endpoint.get("tls_ok")), "profile_fingerprint_safe_hash": profile, "active_profile_stratum": stratum, "profile_matches_a": profile == EXPECTED_PROFILE_A, "profile_matches_b": profile == EXPECTED_PROFILE_B, "raw_profile_values_persisted": False, "commands": {"config_inspect": config["record"], "doctor": doctor["record"], "auth_inspect": auth["record"], "images_generate_help": help_result["record"]}, "image_generation_provider_requests": 0}
    write_json(PRE / "provider_runtime_audit.json", value)
    return value


def dataset_snapshot(label: str) -> dict[str, Any]:
    try:
        p = subprocess.run(["python3", str(VALIDATOR), "--json"], capture_output=True, text=True, timeout=240, check=False)
        try:
            validator = json.loads(p.stdout)
        except Exception:
            validator = {"parse_error": True, "stdout_tail": p.stdout[-12000:], "stderr_tail": p.stderr[-4000:]}
        returncode = p.returncode
    except Exception as exc:
        validator, returncode = {"exception": f"{type(exc).__name__}: {exc}"}, None
    counts, hashes, hits = {}, {}, {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        hits[name] = [i for i, line in enumerate(lines, 1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()]
    value = {"label": label, "captured_at": iso(), "validator_command": ["python3", str(VALIDATOR), "--json"], "validator_returncode": returncode, "validator_status": validator.get("status") if isinstance(validator, dict) else None, "validator_error_count": validator.get("error_count") if isinstance(validator, dict) else None, "validator_full_hash_check": validator.get("full_hash_check") if isinstance(validator, dict) else None, "validator_warning_count": validator.get("warning_count") if isinstance(validator, dict) else None, "validator": validator, "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]}, "annotation_sha256": hashes, "p4d_reference_hits_by_active_csv": hits, "p4d_reference_hits_total": sum(len(v) for v in hits.values()), "formal_ingest": False, "media_added": 0, "labels_added": 0}
    write_json(PRE / f"dataset_boundary_{label}.json", value)
    return value


def write_campaign_authorization(order_summary: dict[str, Any], profile: dict[str, Any]) -> tuple[Path, Path]:
    auth_json = {"stage": "P4D_GR3_QUOTA_CAMPAIGN_AUTHORIZATION", "authorized": False, "explicit_campaign_authorization": False, "authorization_present": False, "source": "none_in_current_top_level_user_message", "template_is_authorization": False, "template_sha256": sha256_bytes(CAMPAIGN_AUTH_TEXT.encode()), "max_manual_windows": MAX_WINDOWS, "first_window_max_logical_invocations": FIRST_WINDOW_CAP, "later_window_default_max_logical_invocations": LATER_WINDOW_CAP, "concurrency": 1, "outer_retry": False, "native_max_retries": 3, "physical_attempt_lower_bound_guard": PHYSICAL_GUARD, "native_retry_scheduled_event_guard": RETRY_EVENT_GUARD, "no_background_execution": True, "no_cron": True, "no_sleep_to_next_window": True, "scope": "image_generation_only", "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0, "holdout_consumed": False, "current_verified_success": 102, "outstanding": 338, "active_profile_stratum_observed": profile.get("active_profile_stratum"), "profile_fingerprint_safe_hash": profile.get("profile_fingerprint_safe_hash"), "provider_requests_before_authorization": 0, "execution_eligible": False, "captured_at": iso()}
    jp = AUTH / "campaign_authorization.json"
    write_json(jp, auth_json)
    md = AUTH / "campaign_authorization_packet.md"
    text = f"""# P4D GR3 quota-window generation campaign authorization packet\n\n```text\nauthorized=false\nexplicit_campaign_authorization=false\nauthorization_present=false\ntemplate_is_authorization=false\nMAX_MANUAL_WINDOWS={MAX_WINDOWS}\nFIRST_WINDOW_MAX_LOGICAL_INVOCATIONS={FIRST_WINDOW_CAP}\nLATER_WINDOW_DEFAULT_MAX_LOGICAL_INVOCATIONS={LATER_WINDOW_CAP}\nCONCURRENCY=1\nOUTER_RETRY=false\nNATIVE_MAX_RETRIES=3\nPHYSICAL_ATTEMPT_LOWER_BOUND_GUARD={PHYSICAL_GUARD}\nNATIVE_RETRY_SCHEDULED_EVENT_GUARD={RETRY_EVENT_GUARD}\nNO_BACKGROUND_EXECUTION=true\nNO_CRON=true\nNO_SLEEP_TO_NEXT_WINDOW=true\nPROVIDER_REQUESTS=0\n```\n\n本 packet 是授权模板和治理记录，不是授权。当前顶层消息没有独立的等价 campaign authorization，因此不得创建 attestation、不得启动第一窗口，也不得把本段模板视为用户已同意。模板 SHA-256 为 `{auth_json['template_sha256']}`。\n\n用户未来必须在新的独立顶层消息中明确授权以下范围：\n\n> {CAMPAIGN_AUTH_TEXT}\n\n该模板只覆盖图像生成；每个 window 必须手动启动并独立 freeze。它不授权 formal ingest、C3、NEW_VAL、HOLDOUT、生产集成、后台等待、cron 或自动跨 window 执行。\n"""
    md.parent.mkdir(parents=True, exist_ok=True)
    with md.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    return jp, md


def create_window_artifacts(order: list[dict[str, Any]], runtime: dict[str, Any], quota: dict[str, Any], gate: dict[str, Any], manifest: dict[str, Any], current_summary: dict[str, Any], outstanding_summary: dict[str, Any]) -> dict[str, Path]:
    first = order[:FIRST_WINDOW_CAP]
    run_config = {"stage": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN", "revision_id": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN_20260828_03", "window_id": "P4D_GR3Q4_WINDOW_01", "provider": "codex", "request_model": "gpt-5.4", "generation_backend": "image_generation", "runtime_version": runtime.get("runtime_version"), "wrapper_sha256": runtime.get("wrapper_sha256"), "binary_sha256": runtime.get("binary_sha256"), "active_profile_stratum": runtime.get("active_profile_stratum"), "profile_fingerprint_safe_hash": runtime.get("profile_fingerprint_safe_hash"), "native_size_requested": "1536x1024", "quality": "medium", "format": "png", "final_size": "1920x1080", "output_conversion": {"crop": "controlled_16_by_9_crop", "resize_method": "Pillow_LANCZOS", "final_format": "PNG"}, "max_logical_invocations_this_window": FIRST_WINDOW_CAP, "later_window_default_max_logical_invocations": LATER_WINDOW_CAP, "max_observed_physical_attempt_lower_bound": PHYSICAL_GUARD, "max_native_retry_scheduled_events": RETRY_EVENT_GUARD, "concurrency": 1, "outer_retry": False, "native_max_retries": 3, "quota_not_before_local": gate.get("not_before_local"), "time_gate_pass": gate.get("time_gate_pass"), "authorization_present": False, "execution_eligible": False, "provider_requests": 0, "logical_invocations": 0, "logical_successes": 0, "logical_failures": 0, "physical_attempt_lower_bound": 0, "native_retry_scheduled_events": 0, "theoretical_max_attempts": FIRST_WINDOW_CAP * 4, "prompt_manifest_sha256": manifest.get("actual_sha256"), "current_inventory_sha256": current_summary.get("inventory_csv_sha256"), "outstanding_sha256": outstanding_summary.get("outstanding_csv_sha256"), "created_at": iso()}
    rp = WINDOW / "run_config.json"
    write_json(rp, run_config)
    window_fields = ["window_planned_order", "execution_order", "prompt_id", "group_id", "variant_id", "role", "taxonomy", "planned_split", "original_manifest_ordinal", "current_group_success_count", "current_group_outstanding_count", "parent_state", "selection_reason", "state", "invocation_count"]
    window_rows = [{"window_planned_order": i + 1, **{k: r.get(k, "") for k in window_fields[1:] if k not in {"state", "invocation_count"}}, "state": "NOT_STARTED", "invocation_count": 0} for i, r in enumerate(first)]
    lp = WLEDGER / "window_01_ledger.csv"
    write_csv(lp, window_fields, window_rows)
    dbp = WLEDGER / "window_01_execution.sqlite3"
    con = sqlite3.connect(dbp)
    columns = ["prompt_id TEXT PRIMARY KEY", "window_planned_order INTEGER UNIQUE NOT NULL", "execution_order INTEGER NOT NULL", "group_id TEXT NOT NULL", "variant_id TEXT NOT NULL", "role TEXT NOT NULL", "taxonomy TEXT NOT NULL", "planned_split TEXT NOT NULL", "original_manifest_ordinal INTEGER NOT NULL", "parent_state TEXT NOT NULL", "state TEXT NOT NULL", "invocation_count INTEGER NOT NULL DEFAULT 0", "provider_request_id TEXT", "http_status TEXT", "error_code TEXT", "raw_sha256 TEXT", "final_sha256 TEXT", "latency_seconds REAL", "native_retry_count INTEGER", "timestamp TEXT", "profile_stratum TEXT NOT NULL"]
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("CREATE TABLE slots (" + ",".join(columns) + ")")
        con.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, captured_at TEXT NOT NULL)")
        names = [c.split()[0] for c in columns]
        placeholders = ",".join("?" for _ in names)
        for r in window_rows:
            vals = [r["prompt_id"], r["window_planned_order"], r["execution_order"], r["group_id"], r["variant_id"], r["role"], r["taxonomy"], r["planned_split"], r["original_manifest_ordinal"], r["parent_state"], r["state"], r["invocation_count"], "", "", "", "", "", None, None, "", runtime.get("active_profile_stratum") or "UNKNOWN"]
            con.execute(f"INSERT INTO slots ({','.join(names)}) VALUES ({placeholders})", vals)
        con.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)", (None, "PREPARED_ZERO_REQUEST", json.dumps({"window_cap": FIRST_WINDOW_CAP, "provider_requests": 0, "time_gate_pass": gate.get("time_gate_pass"), "authorization_present": False}, sort_keys=True), iso()))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    req = WINDOW / "request_log.jsonl"
    raw = WINDOW / "raw_responses.jsonl"
    write_empty(req)
    write_empty(raw)
    write_json(WPRE / "provider_requests_before_execution.json", {"captured_at": iso(), "provider_requests": 0, "physical_attempts": 0, "request_log_lines": 0, "raw_response_lines": 0})
    write_json(WPRE / "group_checkpoint.json", {"captured_at": iso(), "status": "NOT_EXECUTED", "completed_group_count": 0, "current_total_success": current_summary.get("total_verified_success"), "window_logical_count": 0, "window_physical_attempt_lower_bound": 0, "window_native_retry_events": 0, "outstanding": outstanding_summary.get("total_outstanding"), "last_successful_prompt": None})
    write_json(WQA / "new_image_hash_manifest.json", {"captured_at": iso(), "status": "NOT_EXECUTED", "raw_count": 0, "final_count": 0, "images": [], "provider_requests": 0})
    write_json(WQA / "semantic_sentinel_manifest.json", {"captured_at": iso(), "SEMANTIC_SENTINEL_STATUS": "USER_REVIEW_OPTIONAL", "status": "NOT_EXECUTED", "groups_sampled": 0, "images": [], "codex_filled_human_conclusion": False})
    write_json(WQA / "window_summary.json", {"captured_at": iso(), "status": "NOT_EXECUTED", "window_cap": FIRST_WINDOW_CAP, "logical_invocations": 0, "logical_successes": 0, "logical_failures": 0, "physical_attempt_lower_bound": 0, "native_retry_scheduled_events": 0, "stop_reason": "WAITING_FOR_PROVIDER_QUOTA_RESET", "provider_requests": 0})
    return {"run_config": rp, "ledger_csv": lp, "ledger_db": dbp, "request_log": req, "raw_log": raw, "provider_before": WPRE / "provider_requests_before_execution.json", "group_checkpoint": WPRE / "group_checkpoint.json", "image_manifest": WQA / "new_image_hash_manifest.json", "sentinel_manifest": WQA / "semantic_sentinel_manifest.json", "window_summary": WQA / "window_summary.json"}


def dataset_boundary(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    value = {"captured_at": iso(), "before": {"path": str(PRE / "dataset_boundary_before_execution.json"), "counts": before["counts"], "annotation_sha256": before["annotation_sha256"]}, "after": {"path": str(PRE / "dataset_boundary_after_execution.json"), "counts": after["counts"], "annotation_sha256": after["annotation_sha256"]}, "counts_delta": {k: after["counts"][k] - before["counts"][k] for k in before["counts"]}, "annotation_hashes_same": before["annotation_sha256"] == after["annotation_sha256"], "p4d_active_reference_hits": after["p4d_reference_hits_total"], "formal_ingest": False, "media_added": 0, "labels_added": 0}
    write_json(PRE / "dataset_boundary_audit.json", value)
    return value


def main() -> int:
    if EXEC.exists() and any(EXEC.iterdir()):
        print(f"REFUSING_NONEMPTY_EXECUTION_DIRECTORY={EXEC}", file=sys.stderr)
        return 2
    for d in (PRE, INV, ORDER, GOV, AUTH, WINDOW, WLEDGER, WPRE, WQA, FREEZE):
        d.mkdir(parents=True, exist_ok=True)
    before = dataset_snapshot("before_execution")
    q2e = q2e_freeze_audit()
    q3 = gr3q3_freeze_audit()
    manifest_rows, manifest = manifest_audit()
    verified, current_summary, sources = build_inventory(manifest_rows)
    current_summary["inventory_csv_sha256"] = sha256_file(INV / "current_verified_success_inventory.csv")
    write_json(INV / "inventory_summary.json", current_summary)
    gr1 = gr1_audit(verified, manifest_rows)
    outstanding, outstanding_summary = build_outstanding(manifest_rows, verified, sources)
    outstanding_summary["outstanding_csv_sha256"] = sha256_file(INV / "outstanding_338.csv")
    write_json(INV / "outstanding_summary.json", outstanding_summary)
    adaptive, order_summary = adaptive_order(manifest_rows, verified, outstanding)
    quota, gate = quota_time_audit()
    runtime = provider_runtime_audit()
    auth_json_path, auth_md_path = write_campaign_authorization(order_summary, runtime)
    window_paths = create_window_artifacts(adaptive, runtime, quota, gate, manifest, current_summary, outstanding_summary)
    after = dataset_snapshot("after_execution")
    boundary = dataset_boundary(before, after)
    checks = {"q2e_parent_freeze_match": q2e["all_match"], "gr3q3_parent_freeze_match": q3["all_match"], "frozen_manifest_match": manifest["all_match"], "current_102_inventory_exact": current_summary["all_verified"] and current_summary["total_verified_success"] == 102, "gr1_exclusion_clean": gr1["all_excluded"], "outstanding_exact_338": outstanding_summary["exact_expected_state"], "adaptive_order_exact_outstanding": order_summary["order_exact_outstanding"], "quota_evidence_match": quota["evidence_matches_expected"], "dataset_before_valid": before.get("validator_status") == "valid" and before.get("validator_error_count") == 0 and before.get("validator_full_hash_check") is True, "dataset_after_valid": after.get("validator_status") == "valid" and after.get("validator_error_count") == 0 and after.get("validator_full_hash_check") is True, "dataset_unchanged": boundary["annotation_hashes_same"] and all(v == 0 for v in boundary["counts_delta"].values()), "active_p4d_refs_zero": boundary["p4d_active_reference_hits"] == 0, "provider_ready": runtime["auth_ready"] and runtime["endpoint_reachable"] and runtime["tls_ok"], "material_config_match": runtime["provider"] == "codex" and runtime["resolved_provider"] == "codex" and runtime["request_model"] == "gpt-5.4" and runtime["generation_backend"] == "image_generation" and runtime["runtime_version"] == "0.7.3" and runtime["wrapper_sha256"] == EXPECTED_WRAPPER_SHA and runtime["binary_sha256"] == EXPECTED_BINARY_SHA and runtime["native_max_retries"] == 3, "provider_requests_zero": True}
    prep = {"captured_at": iso(), "stage": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN", "checks": checks, "preparation_checks_pass": all(checks.values()), "time_gate_pass": gate["time_gate_pass"], "explicit_campaign_authorization": False, "active_profile_stratum": runtime.get("active_profile_stratum"), "profile_gate_requires_decision": runtime.get("active_profile_stratum") == "UNKNOWN_NEW_PROFILE_STRATUM", "execution_eligible": False, "provider_requests": 0, "blocking_reasons": (["WAITING_FOR_PROVIDER_QUOTA_RESET"] if not gate["time_gate_pass"] else ["AWAITING_CAMPAIGN_AUTHORIZATION"])}
    write_json(PRE / "preparation_gate.json", prep)
    status = "WAITING_FOR_PROVIDER_QUOTA_RESET" if not gate["time_gate_pass"] else ("PAUSED_NEW_PROFILE_STRATUM_DECISION_REQUIRED" if prep["profile_gate_requires_decision"] else "AWAITING_CAMPAIGN_AUTHORIZATION")
    terminal = {"stage": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN", "revision_id": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN_20260828_03", "status": status, "P4D_GR3Q2E_STATUS": "STOPPED_BY_FAILURE_POLICY", "P4D_GR3Q3_STATUS": "WAITING_FOR_PROVIDER_QUOTA_RESET", "P4D_STATUS": "GENERATION_REQUIRED", "starting_verified_success": current_summary["total_verified_success"], "starting_outstanding": outstanding_summary["total_outstanding"], "partial_group_count": order_summary["partial_group_count"], "adaptive_order_sha256": order_summary["adaptive_order_sha256"], "first_window": order_summary["first_window"], "window_logical_cap": FIRST_WINDOW_CAP, "later_window_default_cap": LATER_WINDOW_CAP, "physical_attempt_lower_bound_cap": PHYSICAL_GUARD, "native_retry_event_cap": RETRY_EVENT_GUARD, "window_logical_invocations": 0, "window_success": 0, "window_failure": 0, "native_retry_scheduled_events": 0, "physical_attempt_lower_bound": 0, "theoretical_max_attempts": FIRST_WINDOW_CAP * 4, "provider_requests": 0, "authorization_present": False, "time_gate_pass": gate["time_gate_pass"], "active_profile_stratum": runtime.get("active_profile_stratum"), "full_440_qa": "NOT_REACHED", "semantic_review": "NOT_EXECUTED", "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0, "holdout_consumed": False, "p4d_active_dataset_refs": 0, "new_images": 0, "production_code_modified": False, "ollama_modified": False, "no_background_execution": True, "no_cron": True, "no_sleep_to_next_window": True, "created_at": iso()}
    write_json(WINDOW / "terminal_summary.json", terminal)
    artifact_pairs: list[tuple[Path, str | None]] = [(Q2E_FREEZE, EXPECTED_Q2E_FREEZE_SHA), (GR3Q3_FREEZE, EXPECTED_GR3Q3_FREEZE_SHA), (MANIFEST, EXPECTED_MANIFEST_SHA), (INV / "current_verified_success_inventory.csv", current_summary["inventory_csv_sha256"]), (INV / "inventory_summary.json", sha256_file(INV / "inventory_summary.json")), (INV / "gr1_exclusion_audit.json", sha256_file(INV / "gr1_exclusion_audit.json")), (INV / "outstanding_338.csv", outstanding_summary["outstanding_csv_sha256"]), (INV / "outstanding_summary.json", sha256_file(INV / "outstanding_summary.json")), (ORDER / "adaptive_execution_order.csv", order_summary["adaptive_order_sha256"]), (ORDER / "first_window_68_plan.csv", sha256_file(ORDER / "first_window_68_plan.csv")), (ORDER / "adaptive_order_summary.json", sha256_file(ORDER / "adaptive_order_summary.json")), (PRE / "q2e_parent_freeze_audit.json", sha256_file(PRE / "q2e_parent_freeze_audit.json")), (PRE / "gr3q3_parent_freeze_audit.json", sha256_file(PRE / "gr3q3_parent_freeze_audit.json")), (PRE / "full_manifest_audit.json", sha256_file(PRE / "full_manifest_audit.json")), (PRE / "quota_window_evidence.json", sha256_file(PRE / "quota_window_evidence.json")), (PRE / "time_gate.json", sha256_file(PRE / "time_gate.json")), (PRE / "provider_runtime_audit.json", sha256_file(PRE / "provider_runtime_audit.json")), (PRE / "dataset_boundary_before_execution.json", sha256_file(PRE / "dataset_boundary_before_execution.json")), (PRE / "dataset_boundary_after_execution.json", sha256_file(PRE / "dataset_boundary_after_execution.json")), (PRE / "dataset_boundary_audit.json", sha256_file(PRE / "dataset_boundary_audit.json")), (PRE / "preparation_gate.json", sha256_file(PRE / "preparation_gate.json")), (auth_json_path, sha256_file(auth_json_path)), (auth_md_path, sha256_file(auth_md_path)), (window_paths["run_config"], sha256_file(window_paths["run_config"])), (window_paths["ledger_csv"], sha256_file(window_paths["ledger_csv"])), (window_paths["ledger_db"], sha256_file(window_paths["ledger_db"])), (window_paths["request_log"], sha256_file(window_paths["request_log"])), (window_paths["raw_log"], sha256_file(window_paths["raw_log"])), (window_paths["provider_before"], sha256_file(window_paths["provider_before"])), (window_paths["group_checkpoint"], sha256_file(window_paths["group_checkpoint"])), (window_paths["image_manifest"], sha256_file(window_paths["image_manifest"])), (window_paths["sentinel_manifest"], sha256_file(window_paths["sentinel_manifest"])), (window_paths["window_summary"], sha256_file(window_paths["window_summary"])), (WINDOW / "terminal_summary.json", sha256_file(WINDOW / "terminal_summary.json")), (SELF, sha256_file(SELF)), (CLI, EXPECTED_WRAPPER_SHA), (BINARY, EXPECTED_BINARY_SHA)]
    artifact_map = {str(p): (e if e is not None else sha256_file(p)) for p, e in artifact_pairs}
    freeze_obj = {"stage": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN", "name": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN", "revision_id": "P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN_20260828_03", "status": status, "P4D_GR3Q2E_STATUS": "STOPPED_BY_FAILURE_POLICY", "P4D_GR3Q3_STATUS": "WAITING_FOR_PROVIDER_QUOTA_RESET", "starting_verified_success": current_summary["total_verified_success"], "starting_outstanding": outstanding_summary["total_outstanding"], "partial_group_count": order_summary["partial_group_count"], "adaptive_execution_order_sha256": order_summary["adaptive_order_sha256"], "first_window_max_logical_invocations": FIRST_WINDOW_CAP, "later_window_default_max_logical_invocations": LATER_WINDOW_CAP, "physical_attempt_lower_bound_guard": PHYSICAL_GUARD, "native_retry_scheduled_event_guard": RETRY_EVENT_GUARD, "time_gate": gate, "authorization": read_json(auth_json_path, {}), "active_profile_stratum": runtime.get("active_profile_stratum"), "execution_not_executed": True, "provider_requests": 0, "physical_attempt_lower_bound": 0, "native_retry_scheduled_events": 0, "window_cap_reached": False, "full_440_qa": "NOT_REACHED", "semantic_review": "NOT_EXECUTED", "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0, "holdout_consumed": False, "p4d_active_dataset_refs": 0, "dataset_boundary": boundary, "parent_q2e_freeze_sha256": EXPECTED_Q2E_FREEZE_SHA, "parent_gr3q3_freeze_sha256": EXPECTED_GR3Q3_FREEZE_SHA, "frozen_440_manifest_sha256": EXPECTED_MANIFEST_SHA, "artifact_sha256": artifact_map, "created_at": iso()}
    fp = FREEZE / "p4d_gr3q4_terminal_freeze.json"
    write_json(fp, freeze_obj)
    fsha = sha256_file(fp)
    sp = fp.with_name(fp.name + ".sha256")
    with sp.open("w", encoding="utf-8") as f:
        f.write(f"{fsha}  {fp.name}\n")
        f.flush()
        os.fsync(f.fileno())
    checks_after = [{"path": p, "expected_sha256": e, "actual_sha256": sha256_file(Path(p)), "match": sha256_file(Path(p)) == e} for p, e in artifact_map.items()]
    verification = {"captured_at": iso(), "freeze_path": str(fp), "freeze_sha256": fsha, "sidecar_sha256": sidecar_value(fp), "sidecar_match": fsha == sidecar_value(fp), "bound_artifact_count": len(checks_after), "bound_artifacts": checks_after, "all_bound_artifacts_match": all(c["match"] for c in checks_after), "provider_requests_added": 0, "request_log_lines": 0, "raw_response_lines": 0, "all_pass": bool(fsha == sidecar_value(fp) and all(c["match"] for c in checks_after))}
    write_json(PRE / "terminal_freeze_verification.json", verification)
    print(json.dumps({"status": status, "provider_requests": 0, "starting_verified_success": current_summary["total_verified_success"], "starting_outstanding": outstanding_summary["total_outstanding"], "partial_group_count": order_summary["partial_group_count"], "adaptive_order_sha256": order_summary["adaptive_order_sha256"], "first_window_plan_rows": len(order_summary["first_window"]), "freeze": str(fp), "freeze_sha256": fsha, "time_gate_pass": gate["time_gate_pass"], "authorization_present": False}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
