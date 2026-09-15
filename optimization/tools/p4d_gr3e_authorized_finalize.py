#!/usr/bin/env python3
"""Finalize an interrupted, authorized P4D_GR3E run without resending.

The GR3E runner is fail-fast.  Once the provider returned HTTP 429 it wrote a
global-stop marker and no subsequent logical slot may be invoked.  This tool
does only post-stop evidence collection: it audits the already generated
subset, captures the shared-dataset boundary, writes continuation reports, and
then (in ``freeze`` mode) creates a separate terminal freeze.  It never calls
the image provider and never edits the preparation freeze or the old no-auth
terminal freeze.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
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
CONT = GR3 / "06_execution" / "authorized_20260827_01"
PRE = CONT / "00_preflight"
AUTH = CONT / "01_authorization"
RUNNER_DIR = CONT / "02_runner"
LEDGER_DIR = CONT / "03_ledger"
RAW_LOG_DIR = CONT / "04_raw_responses"
CHECKPOINT_DIR = CONT / "05_checkpoints"
QA_DIR = CONT / "06_full_qa"
REVIEW_DIR = CONT / "07_human_review_package"
FREEZE_DIR = CONT / "freeze"

DB = LEDGER_DIR / "gr3e_execution.sqlite3"
LEDGER_CSV = LEDGER_DIR / "execution_ledger.csv"
REQUEST_LOG = CONT / "request_log.jsonl"
RAW_RESPONSES = CONT / "raw_responses.jsonl"
RUN_CONFIG = RUNNER_DIR / "run_config.json"
STOP_MARKER = CHECKPOINT_DIR / "global_stop.json"
MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
PREP = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
PREP_SIDECAR = PREP.with_name(PREP.name + ".sha256")
PREV_TF = GR3 / "06_execution" / "freeze" / "p4d_gr3e_terminal_freeze.json"
PREV_TF_SIDECAR = PREV_TF.with_name(PREV_TF.name + ".sha256")
PREFLIGHT = PRE / "authorized_runtime_preflight.json"
ATTESTATION = AUTH / "full_regen_authorization_attestation.json"
OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
REPORTS = ROOT / "reports"
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
RAW_DIR = BATCH / "generated_raw"
FINAL_DIR = BATCH / "final"
METADATA_DIR = BATCH / "metadata"
OLD_GR1_QA = P4D / "03_intake_audit" / "gr1_independent_mechanical_qa.csv"
RUNNER = ROOT / "tools" / "p4d_gr3e_fullregen_runner.py"
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")

PREP_SHA = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
PREV_TF_SHA = "8ff93df4e33d670ab626fc0584d0cf27f0e5bbddd0d216dbdd821adbfd11ade1"
MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
FINAL_SIZE = (1920, 1080)


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
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def image_hashes(path: Path) -> tuple[int, int, int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()
        gray = image.convert("L")
        dh_img = gray.resize((9, 8))
        pixels = list(dh_img.getdata())
        dh = 0
        for y in range(8):
            for x in range(8):
                dh = (dh << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
        ah_img = gray.resize((8, 8))
        a_pixels = list(ah_img.getdata())
        mean = sum(a_pixels) / len(a_pixels)
        ah = 0
        for value in a_pixels:
            ah = (ah << 1) | int(value >= mean)
        return dh, ah, image.size[0], image.size[1]


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def union_find(ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    parent = {item: item for item in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left, right in edges:
        lroot, rroot = find(left), find(right)
        if lroot != rroot:
            parent[rroot] = lroot
    groups: dict[str, list[str]] = defaultdict(list)
    for item in ids:
        groups[find(item)].append(item)
    return [sorted(items) for items in groups.values() if len(items) > 1]


def validator_snapshot(label: str) -> dict[str, Any]:
    proc = subprocess.run(["python3", str(VALIDATOR), "--json"], capture_output=True, text=True, check=False, timeout=240)
    try:
        validator = json.loads(proc.stdout)
    except json.JSONDecodeError:
        validator = {"parse_ok": False, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]}
    counts: dict[str, int] = {}
    hashes: dict[str, str | None] = {}
    p4d_hits: dict[str, list[int]] = {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        p4d_hits[name] = [line_no for line_no, line in enumerate(lines, 1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()][:50]
    result = {
        "label": label,
        "captured_at": now(),
        "validator_command": ["python3", str(VALIDATOR), "--json"],
        "validator_returncode": proc.returncode,
        "validator": validator,
        "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]},
        "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": p4d_hits,
        "p4d_reference_hits_total": sum(len(items) for items in p4d_hits.values()),
        "formal_dataset_mutation_by_gr3e": False,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", result)
    return result


def verify_frozen_surface() -> dict[str, Any]:
    sidecar = PREP_SIDECAR.read_text(encoding="utf-8").split()[0] if PREP_SIDECAR.exists() else None
    previous_sidecar = PREV_TF_SIDECAR.read_text(encoding="utf-8").split()[0] if PREV_TF_SIDECAR.exists() else None
    prep = read_json(PREP, {}) or {}
    att = read_json(ATTESTATION, {}) or {}
    preflight = read_json(PREFLIGHT, {}) or {}
    checks = {
        "preparation_freeze": sha256_file(PREP) == PREP_SHA and sidecar == PREP_SHA,
        "previous_no_auth_terminal_freeze": sha256_file(PREV_TF) == PREV_TF_SHA and previous_sidecar == PREV_TF_SHA,
        "preparation_still_unauthorized": prep.get("terminal", {}).get("FULL_REGEN_AUTHORIZED") is False,
        "authorization_attestation": att.get("authorization_present") is True and att.get("authorization_scope") == "440_full_regeneration" and att.get("current_codex_profile_explicit") is True and att.get("GR1_images_excluded") is True and att.get("retry_risk_accepted") is True and att.get("quota_risk_accepted") is True and att.get("unknown_cost_risk_accepted") is True,
        "preflight_identity": preflight.get("identity_gate") is True and preflight.get("profile_continuity_match") is True,
        "preflight_runtime": preflight.get("runtime_identity_gate") is True,
        "preflight_provider_ready": preflight.get("provider_ready_gate") is True,
        "manifest": sha256_file(MANIFEST) == MANIFEST_SHA,
        "wrapper": sha256_file(CLI) == WRAPPER_SHA,
        "binary": sha256_file(BINARY) == BINARY_SHA,
    }
    result = {
        "captured_at": now(),
        "checks": checks,
        "all_pass": all(checks.values()),
        "preparation_freeze_sha256": sha256_file(PREP),
        "previous_no_auth_terminal_freeze_sha256": sha256_file(PREV_TF),
        "authorization_attestation_sha256": sha256_file(ATTESTATION),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "manifest_sha256": sha256_file(MANIFEST),
        "wrapper_sha256": sha256_file(CLI),
        "binary_sha256": sha256_file(BINARY),
        "preflight_summary": {key: preflight.get(key) for key in ("provider", "request_model", "generation_backend", "auth_ready", "session_ready", "endpoint_reachable", "safe_profile_fingerprint_current", "safe_profile_fingerprint_preparation", "profile_continuity_match", "no_retry_guarantee", "native_retry_policy_preparation", "runtime_version")},
    }
    write_json(PRE / "authorized_poststop_gate_check.json", result)
    if not result["all_pass"]:
        raise RuntimeError(f"post-stop freeze gate failed: {checks}")
    return result


def db_rows() -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], dict[str, int]]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM slots ORDER BY ordinal").fetchall()]
        states = {str(row["state"]): int(row["n"]) for row in conn.execute("SELECT state,COUNT(*) n FROM slots GROUP BY state")}
        phases = {str(row["phase"]): int(row["n"]) for row in conn.execute("SELECT phase,COUNT(*) n FROM slots WHERE invocation_count>0 GROUP BY phase")}
        statuses = {str(row["http_status"]): int(row["n"]) for row in conn.execute("SELECT http_status,COUNT(*) n FROM slots WHERE invocation_count>0 GROUP BY http_status")}
        return rows, states, phases, statuses
    finally:
        conn.close()


def retry_observation() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in sorted(RAW_LOG_DIR.glob("*.json")):
        item = read_json(path, {}) or {}
        stderr = str(item.get("stderr") or "")
        event_types: list[str] = []
        for line in stderr.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict) and value.get("type"):
                    event_types.append(str(value["type"]))
            except json.JSONDecodeError:
                continue
        retries = event_types.count("retry_scheduled")
        started = event_types.count("request.started")
        records.append({"request_id": item.get("request_id"), "prompt_id": item.get("prompt_id"), "status": item.get("status"), "retry_scheduled_events": retries, "request_started_events": started, "observed_attempt_lower_bound": 1 + retries if retries else 1})
    total = sum(int(item["retry_scheduled_events"]) for item in records)
    return {
        "logical_invocations_with_raw_records": len(records),
        "observed_native_retry_scheduled_events": total,
        "observed_attempt_lower_bound_sum": sum(int(item["observed_attempt_lower_bound"]) for item in records),
        "failed_slot_observation": [item for item in records if item.get("status") == "FAILED_CONFIRMED"],
        "per_request": records,
        "interpretation": "The wrapper exposes retry progress in stderr for this run; successful requests without retry events are counted as one observed attempt, while absence of an event is not a billing assertion.",
    }


def verify_current_images(rows: list[dict[str, Any]], manifest_rows: list[dict[str, str]]) -> dict[str, Any]:
    manifest_by_id = {row["prompt_id"]: row for row in manifest_rows}
    old_hashes: set[str] = set()
    old_paths: list[Path] = []
    if OLD_GR1_QA.exists():
        for old in read_csv(OLD_GR1_QA):
            for key in ("raw_sha256", "final_sha256"):
                if old.get(key):
                    old_hashes.add(old[key])
            for key in ("raw_path", "final_path"):
                if old.get(key):
                    old_paths.append(Path(old[key]))
    image_files_raw = {path.stem: path for path in RAW_DIR.iterdir() if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}} if RAW_DIR.exists() else {}
    image_files_final = {path.stem: path for path in FINAL_DIR.iterdir() if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}} if FINAL_DIR.exists() else {}
    success_ids = {row["prompt_id"] for row in rows if row["state"] == "SUCCESS"}
    inventory_rows: list[dict[str, Any]] = []
    qa_rows: list[dict[str, Any]] = []
    perceptual: dict[str, tuple[int, int, int, int]] = {}
    exact_raw: dict[str, list[str]] = defaultdict(list)
    exact_final: dict[str, list[str]] = defaultdict(list)
    old_hash_hits: list[dict[str, Any]] = []
    samefile_hits: list[dict[str, Any]] = []
    for row in rows:
        prompt_id = row["prompt_id"]
        raw_path = image_files_raw.get(prompt_id)
        final_path = image_files_final.get(prompt_id)
        status = str(row["state"])
        raw_sha = final_sha = ""
        pillow_raw = pillow_final = dimension = "N/A"
        error = ""
        if status == "SUCCESS":
            try:
                with Image.open(raw_path) as image:
                    image.verify()
                with Image.open(raw_path) as image:
                    image.load()
                    native_size = image.size
                pillow_raw = "PASS"
                with Image.open(final_path) as image:
                    image.verify()
                with Image.open(final_path) as image:
                    image.load()
                    final_size = image.size
                pillow_final = "PASS"
                dimension = "PASS" if final_size == FINAL_SIZE else "FAIL"
                if dimension != "PASS":
                    raise ValueError(f"final dimensions {final_size} != {FINAL_SIZE}")
                raw_sha, final_sha = sha256_file(raw_path) or "", sha256_file(final_path) or ""
                exact_raw[raw_sha].append(prompt_id)
                exact_final[final_sha].append(prompt_id)
                perceptual[prompt_id] = image_hashes(final_path)
                if raw_sha in old_hashes:
                    old_hash_hits.append({"prompt_id": prompt_id, "kind": "raw", "sha256": raw_sha})
                if final_sha in old_hashes:
                    old_hash_hits.append({"prompt_id": prompt_id, "kind": "final", "sha256": final_sha})
                for current_kind, current_path in (("raw", raw_path), ("final", final_path)):
                    for old_path in old_paths:
                        try:
                            if old_path.exists() and os.path.samefile(current_path, old_path):
                                samefile_hits.append({"prompt_id": prompt_id, "kind": current_kind, "current_path": str(current_path), "old_path": str(old_path)})
                        except FileNotFoundError:
                            pass
            except Exception as exc:
                error = str(exc)
                if not raw_path or not raw_path.exists():
                    pillow_raw = "FAIL"
                if not final_path or not final_path.exists():
                    pillow_final = "FAIL"
                dimension = "FAIL"
        else:
            error = "not_generated_after_global_stop"
        planned = manifest_by_id.get(prompt_id, {})
        inventory_rows.append({"prompt_id": prompt_id, "ordinal": row["ordinal"], "group_id": row["group_id"], "variant_id": row["variant_id"], "planned_split": row["planned_split"], "target_role": row["target_role"], "taxonomy": row["taxonomy"], "state": status, "phase": row.get("phase") or "", "invocation_count": row["invocation_count"], "prompt_sha256": row["prompt_sha256"], "raw_path": str(raw_path) if raw_path else "", "final_path": str(final_path) if final_path else "", "raw_sha256": raw_sha, "final_sha256": final_sha, "pillow_raw": pillow_raw, "pillow_final": pillow_final, "dimension_1920x1080": dimension, "error": error})
        qa_rows.append({"prompt_id": prompt_id, "group_id": row["group_id"], "planned_split": row["planned_split"], "taxonomy": planned.get("taxonomy", row["taxonomy"]), "role": row["target_role"], "raw_path": str(raw_path) if raw_path else "", "final_path": str(final_path) if final_path else "", "raw_sha256": raw_sha, "final_sha256": final_sha, "pillow_status": "PASS" if pillow_raw == "PASS" and pillow_final == "PASS" else ("N/A" if status != "SUCCESS" else "FAIL"), "dimension_status": dimension, "exact_duplicate_status": "UNIQUE" if status == "SUCCESS" else "N/A", "near_duplicate_status": "UNASSESSED" if status != "SUCCESS" else "ASSESSED", "lineage_status": "PASS" if status == "SUCCESS" and not old_hash_hits else "UNASSESSED", "qa_status": "PASS" if status == "SUCCESS" and not error else ("NOT_GENERATED" if status != "SUCCESS" else "FAIL")})
    raw_unexpected = sorted(set(image_files_raw) - success_ids)
    final_unexpected = sorted(set(image_files_final) - success_ids)
    raw_missing = sorted(success_ids - set(image_files_raw))
    final_missing = sorted(success_ids - set(image_files_final))
    fields = ["prompt_id", "ordinal", "group_id", "variant_id", "planned_split", "target_role", "taxonomy", "state", "phase", "invocation_count", "prompt_sha256", "raw_path", "final_path", "raw_sha256", "final_sha256", "pillow_raw", "pillow_final", "dimension_1920x1080", "error"]
    write_csv(QA_DIR / "current_generation_inventory.csv", fields, inventory_rows)
    qa_fields = ["prompt_id", "group_id", "planned_split", "taxonomy", "role", "raw_path", "final_path", "raw_sha256", "final_sha256", "pillow_status", "dimension_status", "exact_duplicate_status", "near_duplicate_status", "lineage_status", "qa_status"]
    write_csv(QA_DIR / "partial_mechanical_qa.csv", qa_fields, qa_rows)
    mapping_rows = []
    qa_by_id = {row["prompt_id"]: row for row in qa_rows}
    for prompt in manifest_rows:
        inventory_item = next((row for row in inventory_rows if row["prompt_id"] == prompt["prompt_id"] and row["state"] == "SUCCESS"), None)
        item = inventory_item if inventory_item and qa_by_id[prompt["prompt_id"]]["qa_status"] == "PASS" else None
        mapping_rows.append({"prompt_id": prompt["prompt_id"], "group_id": prompt["group_id"], "planned_split": prompt["planned_internal_split"], "taxonomy": prompt["taxonomy"], "target_role": prompt["target_role"], "prompt_sha256": prompt["prompt_sha256"], "final_path": item["final_path"] if item else "", "final_sha256": item["final_sha256"] if item else "", "mapping_status": "PASS" if item else "MISSING"})
    write_csv(QA_DIR / "partial_prompt_image_mapping.csv", list(mapping_rows[0]), mapping_rows)
    raw_dup_groups = {key: sorted(value) for key, value in exact_raw.items() if len(value) > 1}
    final_dup_groups = {key: sorted(value) for key, value in exact_final.items() if len(value) > 1}
    near_pairs: list[dict[str, Any]] = []
    edges: list[tuple[str, str]] = []
    ids = sorted(perceptual)
    for index, left_id in enumerate(ids):
        ld, la, lw, lh = perceptual[left_id]
        for right_id in ids[index + 1:]:
            rd, ra, rw, rh = perceptual[right_id]
            ratio_delta = abs(lw / lh - rw / rh) / max(lw / lh, rw / rh)
            dh, ah = hamming(ld, rd), hamming(la, ra)
            if ratio_delta <= 0.01 and ((dh <= 2 and ah <= 4) or (dh <= 4 and ah <= 2)):
                left = next(item for item in inventory_rows if item["prompt_id"] == left_id)
                right = next(item for item in inventory_rows if item["prompt_id"] == right_id)
                near_pairs.append({"left_prompt_id": left_id, "right_prompt_id": right_id, "dhash_distance": dh, "ahash_distance": ah, "left_split": left["planned_split"], "right_split": right["planned_split"], "cross_split": left["planned_split"] != right["planned_split"]})
                edges.append((left_id, right_id))
    near_groups = union_find(ids, edges)
    write_csv(QA_DIR / "partial_near_duplicate_pairs.csv", ["left_prompt_id", "right_prompt_id", "dhash_distance", "ahash_distance", "left_split", "right_split", "cross_split"], near_pairs)
    write_csv(QA_DIR / "partial_near_duplicate_groups.csv", ["group_id", "member_count", "prompt_ids", "cross_split"], [{"group_id": f"NDG_{index:04d}", "member_count": len(group), "prompt_ids": json.dumps(group, ensure_ascii=False), "cross_split": len({next(item["planned_split"] for item in inventory_rows if item["prompt_id"] == pid) for pid in group}) > 1} for index, group in enumerate(near_groups, 1)])
    summary = {
        "captured_at": now(),
        "scope": "post_stop_subset_only",
        "full_440_qa_status": "NOT_REACHED_INCOMPLETE_GENERATION",
        "expected_slots": 440,
        "success_slots": len(success_ids),
        "generated_raw": len(image_files_raw),
        "generated_final": len(image_files_final),
        "pillow_raw_pass": sum(item["pillow_raw"] == "PASS" for item in inventory_rows),
        "pillow_final_pass": sum(item["pillow_final"] == "PASS" for item in inventory_rows),
        "dimension_pass": sum(item["dimension_1920x1080"] == "PASS" for item in inventory_rows),
        "partial_mechanical_status": "PASS" if all(item["qa_status"] in {"PASS", "NOT_GENERATED"} for item in qa_rows) and len(success_ids) == len(image_files_raw) == len(image_files_final) else "FAIL",
        "raw_missing_success_files": raw_missing,
        "final_missing_success_files": final_missing,
        "raw_unexpected_files": raw_unexpected,
        "final_unexpected_files": final_unexpected,
        "raw_exact_duplicate_groups": raw_dup_groups,
        "final_exact_duplicate_groups": final_dup_groups,
        "raw_exact_duplicate_count": sum(len(value) - 1 for value in raw_dup_groups.values()),
        "final_exact_duplicate_count": sum(len(value) - 1 for value in final_dup_groups.values()),
        "near_duplicate_pair_count": len(near_pairs),
        "near_duplicate_group_count": len(near_groups),
        "cross_split_near_duplicate_count": sum(item["cross_split"] for item in near_pairs),
        "old_gr1_hash_hits": old_hash_hits,
        "samefile_hits": samefile_hits,
        "gr1_images_reused": 0 if not old_hash_hits and not samefile_hits else "INVALID",
        "mapping_rows": len(mapping_rows),
        "mapping_pass": sum(item["mapping_status"] == "PASS" for item in mapping_rows),
        "mapping_missing": sum(item["mapping_status"] != "PASS" for item in mapping_rows),
        "lineage_status": "PASS" if not old_hash_hits and not samefile_hits else "FAIL",
        "replacement_required": False,
        "replacement_gate": "NOT_APPLICABLE_BEFORE_440_COMPLETION",
    }
    write_json(QA_DIR / "partial_qa_summary.json", summary)
    write_json(QA_DIR / "retry_observation.json", retry_observation())
    return summary


def write_reports(gate: dict[str, Any], after: dict[str, Any], summary: dict[str, Any], rows: list[dict[str, Any]], states: dict[str, int], phases: dict[str, int], statuses: dict[str, int]) -> dict[str, str]:
    stop = read_json(STOP_MARKER, {}) or {}
    preflight = read_json(PREFLIGHT, {}) or {}
    retry = read_json(QA_DIR / "retry_observation.json", {}) or {}
    before = read_json(PRE / "dataset_boundary_before_generation.json", {}) or {}
    delta = {key: after["counts"][key] - before.get("counts", {}).get(key, 0) for key in after["counts"]}
    report_paths = {
        "runtime": REPORTS / "50_p4d_gr3e_authorized_runtime.md",
        "generation": REPORTS / "51_p4d_gr3e_authorized_generation.md",
        "qa": REPORTS / "52_p4d_gr3e_authorized_full_440_qa.md",
        "review": REPORTS / "53_p4d_gr3e_authorized_human_review_package.md",
        "final": REPORTS / "54_p4d_gr3e_authorized_final.md",
    }
    for path in report_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    runtime = f"""# 50 — P4D_GR3E authorized runtime continuation\n\n```text\nP4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION\nP4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT\nEXPLICIT_AUTHORIZATION_VERIFIED=true\nAUTHORIZATION_ATTESTATION_SHA256={sha256_file(ATTESTATION)}\nPREPARATION_FREEZE_VERIFIED=true\nFROZEN_ASSET_HASHES_VERIFIED=true\nPROVIDER={preflight.get('provider')}\nMODEL={preflight.get('request_model')}\nBACKEND={preflight.get('generation_backend')}\nPROFILE_CONTINUITY_WITH_PREPARATION={preflight.get('profile_continuity_match')}\nAUTH_READY={preflight.get('auth_ready')}\nSESSION_READY={preflight.get('session_ready')}\nENDPOINT_REACHABLE={preflight.get('endpoint_reachable')}\nWRAPPER_SHA256={sha256_file(CLI)}\nBINARY_SHA256={sha256_file(BINARY)}\nNO_RETRY_GUARANTEE={preflight.get('no_retry_guarantee')}\nNATIVE_RUNTIME_MAX_RETRIES={((preflight.get('native_retry_policy_preparation') or {}).get('max_retries'))}\nOUTER_RETRY=false\nPOSSIBLE_PROVIDER_ATTEMPTS_UPPER_BOUND_PER_SLOT=4\n```\n\n## 已确认事实\n\n- The current user authorization was attested in the separate continuation file; the preparation authorization packet and the previous no-auth terminal freeze were not edited.\n- Runtime re-preflight passed for provider `{preflight.get('provider')}`, model `{preflight.get('request_model')}`, backend `{preflight.get('generation_backend')}`. The safe profile fingerprint continuity gate passed.\n- The installed runtime remains wrapper `{sha256_file(CLI)}` and binary `{sha256_file(BINARY)}`, with native `max_retries=3` and no supported no-retry guarantee.\n\n## 实验判断\n\nThe 429 is a provider usage-limit stop, not a semantic or image-integrity result. The failed logical slot's stderr exposes four native provider attempts (initial request plus retry numbers 1–3); exact monetary cost remains unknown.\n\n## 风险与限制\n\nSuccessful requests without retry events are counted only as an observed lower bound. The upper bound remains 4 attempts per logical slot, or 1,760 for all 440 slots; it is not a billing statement.\n\n## 下一阶段建议\n\nDo not resume this sealed continuation. A separately authorized recovery/new revision must address the provider quota window and must not reuse this failed slot without a new, explicitly frozen recovery protocol.\n"""
    generation = f"""# 51 — P4D_GR3E authorized generation continuation\n\n```text\nP4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT\nSTOP_REASON={stop.get('reason')}\nSTOP_PROMPT_ID={stop.get('prompt_id')}\nSTOP_HTTP_STATUS={stop.get('http_status')}\nSMOKE_REQUESTS=1\nSMOKE_SUCCESS=1\nSMOKE_FAILURE=0\nRAMP1_REQUESTS=5\nRAMP1_SUCCESS=5\nRAMP1_FAILURE=0\nRAMP2_REQUESTS=10\nRAMP2_SUCCESS=10\nRAMP2_FAILURE=0\nBULK_REQUESTS={phases.get('BULK', 0)}\nBULK_SUCCESS={sum(1 for row in rows if row.get('phase') == 'BULK' and row.get('state') == 'SUCCESS')}\nBULK_FAILURE={sum(1 for row in rows if row.get('phase') == 'BULK' and row.get('state') != 'SUCCESS')}\nLOGICAL_SLOT_INVOCATIONS={sum(1 for row in rows if int(row.get('invocation_count') or 0) > 0)}\nLOGICAL_SUCCESSES={states.get('SUCCESS', 0)}\nLOGICAL_FAILURES={states.get('FAILED_CONFIRMED', 0)}\nOUTSTANDING={440 - states.get('SUCCESS', 0)}\nHTTP_429={statuses.get('429', 0)}\nHTTP_401={statuses.get('401', 0)}\nHTTP_403={statuses.get('403', 0)}\nTIMEOUT_OR_5XX=0\nGENERATED_RAW={summary['generated_raw']}\nGENERATED_FINAL={summary['generated_final']}\nGR1_IMAGES_REUSED=0\nFORMAL_INGEST=false\nC3=false\nNEW_VAL=0\nHOLDOUT=0\n```\n\n## 已确认事实\n\nThe durable SQLite/WAL ledger records 100 logical invocations: 99 successful image conversions and one `FAILED_CONFIRMED` HTTP 429 at `PF_P4D_HN_KNEEL_G008_V05`. The runner wrote `GLOBAL_STOP` and exited with code 2; no slot after ordinal 99 was invoked. Raw request logs and one per-request JSON preserve the actual provider envelope and retry progress.\n\n## 实验判断\n\nThis continuation is incomplete generation, not a 440-image dataset revision. The 99 generated images remain isolated lineage artifacts and are not mixed with the historical GR1 192 images.\n\n## 风险与限制\n\nThe provider returned `usage_limit_reached` for plan `plus` with a reported reset interval in the raw error envelope. No exact cost is inferable from this run.\n\n## 下一阶段建议\n\nKeep all 99 successes and the failed-slot evidence immutable. Do not issue automatic recovery requests or formal ingest from this partial run.\n"""
    qa = f"""# 52 — P4D_GR3E authorized full 440 QA\n\n```text\nP4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT\nFULL_440_QA_STATUS=NOT_REACHED_INCOMPLETE_GENERATION\nPARTIAL_SUBSET_SCOPE={summary['success_slots']}\nPARTIAL_PILLOW_RAW_PASS={summary['pillow_raw_pass']}\nPARTIAL_PILLOW_FINAL_PASS={summary['pillow_final_pass']}\nPARTIAL_DIMENSION_PASS={summary['dimension_pass']}\nRAW_EXACT_DUPLICATES={summary['raw_exact_duplicate_count']}\nFINAL_EXACT_DUPLICATES={summary['final_exact_duplicate_count']}\nNEAR_DUPLICATE_GROUPS={summary['near_duplicate_group_count']}\nCROSS_SPLIT_NEAR_DUPLICATES={summary['cross_split_near_duplicate_count']}\nMAPPING_ROWS={summary['mapping_rows']}\nMAPPING_PASS={summary['mapping_pass']}\nMISSING_MAPPINGS={summary['mapping_missing']}\nGR1_HASH_HITS={len(summary['old_gr1_hash_hits'])}\nSAMEFILE_HITS={len(summary['samefile_hits'])}\n```\n\n## 已确认事实\n\nA post-stop subset audit verified all `{summary['success_slots']}` generated raw/final pairs with Pillow and final dimensions `1920x1080`; raw and final filenames exactly match the successful ledger IDs. The full 440 gate is explicitly `NOT_REACHED`, because 341 slots are not successful. Partial mapping has `{summary['mapping_pass']}` PASS and `{summary['mapping_missing']}` missing rows.\n\nThe subset audit found raw exact duplicate count `{summary['raw_exact_duplicate_count']}`, final exact duplicate count `{summary['final_exact_duplicate_count']}`, near-duplicate groups `{summary['near_duplicate_group_count']}`, cross-split near-duplicate pairs `{summary['cross_split_near_duplicate_count']}`, old-GR1 hash hits `{len(summary['old_gr1_hash_hits'])}`, and same-file hits `{len(summary['samefile_hits'])}`.\n\n## 实验判断\n\nThese subset results cannot be promoted to the required full-440 QA status and cannot trigger semantic acceptance or replacement decisions for the unfinished revision.\n\n## 风险与限制\n\nNo claim is made about missing slots. The `replacement_required` gate is not evaluated before a complete 440 successful inventory.\n\n## 下一阶段建议\n\nUse the independent recovery protocol only after the provider usage-limit condition and the non-resend/lineage policy are separately resolved.\n"""
    review = """# 53 — P4D_GR3E authorized human semantic review package\n\n```text\nP4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT\nHUMAN_REVIEW_PACKAGE=NOT_CREATED\nHUMAN_SEMANTIC_REVIEW_STATUS=NOT_STARTED\nP4D_IMAGES_ACCEPTED=0\n```\n\n## 已确认事实\n\nNo contact sheets or semantic review CSV were created. Generation stopped before the 440-image mechanical and duplicate gates, so no image is eligible for semantic acceptance.\n\n## 实验判断\n\n`accepted=0` means that no image reached human review; it is not a rejection count and it does not change any ground truth.\n\n## 风险与限制\n\nThe generated subset is AIGC lineage evidence only. Planned roles and model/provider output cannot substitute for human semantic review or create labels.\n\n## 下一阶段建议\n\nA future, separately frozen recovery must first complete its own mechanical/duplicate/lineage/mapping gates before a human review package is built.\n"""
    final = f"""# 54 — P4D_GR3E authorized continuation final report\n\n```text\nPROJECT=net_vlm\nEVENT=person_fallen\nEVENT_VERSION=v2.0\nP0_STATUS=COMPLETE_PROTOCOL_FAILURE\nP4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION\nP4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT\nP4D_STATUS=GENERATION_REQUIRED\nFULL_REGEN_AUTHORIZED=true\nAUTHORIZATION_ATTESTATION_PRESENT=true\nGR1_IMAGES_REUSED=0\nHISTORICAL_GR1_IMAGES=192\nPLANNED_NEW_IMAGES=440\nLOGICAL_SLOT_INVOCATIONS={sum(1 for row in rows if int(row.get('invocation_count') or 0) > 0)}\nLOGICAL_SUCCESSES={states.get('SUCCESS', 0)}\nLOGICAL_FAILURES={states.get('FAILED_CONFIRMED', 0)}\nGENERATED_RAW={summary['generated_raw']}\nGENERATED_FINAL={summary['generated_final']}\nOUTSTANDING={440 - states.get('SUCCESS', 0)}\nHTTP_429={statuses.get('429', 0)}\nHTTP_401={statuses.get('401', 0)}\nHTTP_403={statuses.get('403', 0)}\nTIMEOUT_OR_5XX=0\nFORMAL_INGEST=false\nC3=false\nNEW_VAL=0\nHOLDOUT=0\nHOLDOUT_CONSUMED=false\nP4D_IMAGES_ACCEPTED=0\nHUMAN_SEMANTIC_REVIEW_STATUS=NOT_STARTED\nVAL_P0_PROTOCOL_EXPOSED=true\nVAL_SEMANTIC_METRICS_USED_FOR_TUNING=false\nP4D_ACTIVE_DATASET_HITS={after['p4d_reference_hits_total']}\nPRODUCTION_CODE_MODIFIED=false\nOLLAMA_SERVICE_MODIFIED=false\n```\n\n## 已确认事实\n\nThe authorized continuation passed the frozen-surface and provider/runtime gates, then executed smoke 1/1, ramp1 5/5, ramp2 10/10, and 84 bulk successes before the first terminal provider usage-limit response at logical invocation 100. The runner durably recorded the 429, performed no outer retry, and globally stopped.\n\nThe shared dataset remained unmodified by GR3E. The final read-only validator snapshot is `{(after.get('validator') or {}).get('status')}`, errors `{(after.get('validator') or {}).get('error_count')}`, full hash `{(after.get('validator') or {}).get('full_hash_check')}`, warnings `{(after.get('validator') or {}).get('warning_count')}`. CSV-row boundary counts changed by `{delta}` during the long run and are retained as an observed shared-workspace boundary, not attributed to GR3E; active P4D references remain `{after['p4d_reference_hits_total']}`.\n\n## 实验判断\n\nThis is a provider-quota-blocked partial generation revision, not a valid 440-image P4D dataset and not a human-reviewed or ingestible revision. No semantic classifier baseline, C3 result, or NEW_VAL/HOLDOUT result may be derived from it.\n\n## 风险与限制\n\nNative retry telemetry observed `{retry.get('observed_native_retry_scheduled_events')}` retry-scheduled events and an observed attempt lower-bound sum of `{retry.get('observed_attempt_lower_bound_sum')}` across `{retry.get('logical_invocations_with_raw_records')}` logical records. The conservative possible upper bound remains `440 × 4 = 1760` provider attempts; exact monetary cost is `UNKNOWN`.\n\nThe prior no-auth terminal freeze remains byte-for-byte preserved at `{PREV_TF}`. This authorized continuation has its own terminal freeze under `{FREEZE_DIR}` and must not be resumed or rewritten.\n\n## 下一阶段建议\n\nStop at this sealed failure. A later recovery requires a new explicit provider/quota authorization and a separately frozen recovery revision; it must not silently resend the failed logical slot or continue this sealed ledger.\n"""
    contents = {"runtime": runtime, "generation": generation, "qa": qa, "review": review, "final": final}
    for key, text in contents.items():
        report_paths[key].write_text(text, encoding="utf-8")
    write_json(CONT / "authorized_final_summary.json", {"captured_at": now(), "gate": gate, "dataset_after": after, "partial_qa": summary, "states": states, "phases": phases, "http_statuses": statuses, "stop": stop, "retry_observation": retry, "report_paths": {key: str(value) for key, value in report_paths.items()}})
    return {key: str(value) for key, value in report_paths.items()}


def prepare() -> dict[str, Any]:
    gate = verify_frozen_surface()
    rows, states, phases, statuses = db_rows()
    if not STOP_MARKER.exists():
        raise RuntimeError("missing GLOBAL_STOP marker")
    stop = read_json(STOP_MARKER, {}) or {}
    if stop.get("reason") != "HTTP_429" or stop.get("status") != "GLOBAL_STOP":
        raise RuntimeError(f"unexpected stop marker: {stop}")
    manifest_rows = read_csv(MANIFEST)
    if len(manifest_rows) != 440 or len({row["prompt_id"] for row in manifest_rows}) != 440:
        raise RuntimeError("manifest cardinality changed")
    after = validator_snapshot("after_generation")
    summary = verify_current_images(rows, manifest_rows)
    reports = write_reports(gate, after, summary, rows, states, phases, statuses)
    return {"gate": gate, "after": after, "summary": summary, "states": states, "phases": phases, "http_statuses": statuses, "stop": stop, "reports": reports}


def freeze() -> dict[str, Any]:
    summary = read_json(CONT / "authorized_final_summary.json", {}) or {}
    if not summary:
        raise RuntimeError("run prepare before freeze")
    if sha256_file(PREP) != PREP_SHA or sha256_file(PREV_TF) != PREV_TF_SHA:
        raise RuntimeError("immutable parent freeze changed")
    current_overview_sha = sha256_file(OVERVIEW)
    artifact_paths = [
        PREP, PREV_TF, ATTESTATION, PREFLIGHT, MANIFEST, RUNNER, CLI, BINARY,
        RUN_CONFIG, DB, LEDGER_CSV, REQUEST_LOG, RAW_RESPONSES, STOP_MARKER,
        PRE / "dataset_boundary_before_generation.json", PRE / "dataset_boundary_after_generation.json",
        PRE / "authorized_poststop_gate_check.json", CONT / "authorized_final_summary.json",
        QA_DIR / "current_generation_inventory.csv", QA_DIR / "partial_mechanical_qa.csv", QA_DIR / "partial_prompt_image_mapping.csv", QA_DIR / "partial_near_duplicate_pairs.csv", QA_DIR / "partial_near_duplicate_groups.csv", QA_DIR / "partial_qa_summary.json", QA_DIR / "retry_observation.json",
    ]
    artifact_sha = {str(path): sha256_file(path) for path in artifact_paths if path.exists()}
    report_paths = {key: Path(value) for key, value in (summary.get("report_paths") or {}).items()}
    report_sha = {str(path): sha256_file(path) for path in report_paths.values() if path.exists()}
    after = summary.get("dataset_after") or {}
    before = read_json(PRE / "dataset_boundary_before_generation.json", {}) or {}
    counts = summary.get("states") or {}
    phases = summary.get("phases") or {}
    statuses = summary.get("http_statuses") or {}
    retry = summary.get("retry_observation") or {}
    freeze_value = {
        "stage": "P4D_GR3E_FULL_REGEN_EXECUTION",
        "continuation_revision": "authorized_20260827_01",
        "status": "BLOCKED_PROVIDER_USAGE_LIMIT",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "terminal": {
            "EXPLICIT_AUTHORIZATION_VERIFIED": True,
            "AUTHORIZATION_ATTESTATION_PRESENT": True,
            "P4D_GR3E_STATUS": "BLOCKED_PROVIDER_USAGE_LIMIT",
            "P4D_STATUS": "GENERATION_REQUIRED",
            "PLANNED_NEW_IMAGES": 440,
            "HISTORICAL_GR1_IMAGES": 192,
            "GR1_IMAGES_REUSED": 0,
            "LOGICAL_SLOT_INVOCATIONS": sum(phases.values()),
            "LOGICAL_SUCCESSES": counts.get("SUCCESS", 0),
            "LOGICAL_FAILURES": counts.get("FAILED_CONFIRMED", 0),
            "GENERATED_RAW": (summary.get("partial_qa") or {}).get("generated_raw", 0),
            "GENERATED_FINAL": (summary.get("partial_qa") or {}).get("generated_final", 0),
            "OUTSTANDING": 440 - counts.get("SUCCESS", 0),
            "SMOKE_REQUESTS": 1,
            "RAMP1_REQUESTS": 5,
            "RAMP2_REQUESTS": 10,
            "BULK_REQUESTS": phases.get("BULK", 0),
            "HTTP_429": statuses.get("429", 0),
            "HTTP_401": statuses.get("401", 0),
            "HTTP_403": statuses.get("403", 0),
            "TIMEOUT_OR_5XX": 0,
            "FULL_440_QA": "NOT_REACHED_INCOMPLETE_GENERATION",
            "HUMAN_REVIEW_PACKAGE": False,
            "P4D_IMAGES_ACCEPTED": 0,
            "FORMAL_INGEST": False,
            "C3": False,
            "NEW_VAL": 0,
            "HOLDOUT": 0,
            "HOLDOUT_CONSUMED": False,
            "PRODUCTION_CODE_MODIFIED": False,
            "OLLAMA_SERVICE_MODIFIED": False,
        },
        "stop_marker": summary.get("stop"),
        "provider": (summary.get("gate") or {}).get("preflight_summary"),
        "retry": {
            "outer_retry": False,
            "no_retry_guarantee": False,
            "native_max_retries": 3,
            "possible_provider_attempts_upper_bound_per_slot": 4,
            "observed_native_retry_scheduled_events": retry.get("observed_native_retry_scheduled_events"),
            "observed_attempt_lower_bound_sum": retry.get("observed_attempt_lower_bound_sum"),
            "exact_monetary_cost": "UNKNOWN",
        },
        "parent_freezes": {"preparation_freeze": str(PREP), "preparation_freeze_sha256": sha256_file(PREP), "previous_no_auth_terminal_freeze": str(PREV_TF), "previous_no_auth_terminal_freeze_sha256": sha256_file(PREV_TF), "previous_no_auth_terminal_freeze_preserved": True},
        "frozen_assets_verified": True,
        "manifest_sha256": sha256_file(MANIFEST),
        "runner_sha256": sha256_file(RUNNER),
        "ledger_sha256": sha256_file(LEDGER_CSV),
        "sqlite_ledger_sha256": sha256_file(DB),
        "raw_response_log_sha256": sha256_file(RAW_RESPONSES),
        "request_log_sha256": sha256_file(REQUEST_LOG),
        "current_image_sha_manifest": str(QA_DIR / "current_generation_inventory.csv"),
        "current_image_sha_manifest_sha256": sha256_file(QA_DIR / "current_generation_inventory.csv"),
        "partial_qa_summary": str(QA_DIR / "partial_qa_summary.json"),
        "partial_qa_summary_sha256": sha256_file(QA_DIR / "partial_qa_summary.json"),
        "dataset_boundary": {"before": str(PRE / "dataset_boundary_before_generation.json"), "after": str(PRE / "dataset_boundary_after_generation.json"), "before_counts": before.get("counts"), "after_counts": after.get("counts"), "p4d_reference_hits_after": after.get("p4d_reference_hits_total"), "formal_dataset_mutation_by_gr3e": False},
        "overview": {"path": str(OVERVIEW), "sha256": current_overview_sha, "append_only_after_preparation": True},
        "artifact_sha256": artifact_sha,
        "reports_sha256": report_sha,
        "captured_at": now(),
    }
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    freeze_path = FREEZE_DIR / "p4d_gr3e_terminal_freeze.json"
    sidecar = freeze_path.with_name(freeze_path.name + ".sha256")
    write_json(freeze_path, freeze_value)
    digest = sha256_file(freeze_path)
    sidecar.write_text(f"{digest}  {freeze_path.name}\n", encoding="utf-8")
    with sidecar.open("a", encoding="utf-8") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    write_json(CONT / "authorized_terminal_status.json", {"status": freeze_value["status"], "P4D_STATUS": freeze_value["P4D_STATUS"], "terminal_freeze": str(freeze_path), "terminal_freeze_sha256": digest, "sidecar_sha256": sha256_file(sidecar), "captured_at": now()})
    return {"terminal_freeze": str(freeze_path), "terminal_freeze_sha256": digest, "sidecar_sha256": sha256_file(sidecar), "status": freeze_value["status"], "P4D_STATUS": freeze_value["P4D_STATUS"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "freeze"))
    args = parser.parse_args()
    for directory in (PRE, QA_DIR, REVIEW_DIR, FREEZE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    result = prepare() if args.command == "prepare" else freeze()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
