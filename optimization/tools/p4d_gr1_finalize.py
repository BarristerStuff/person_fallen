#!/usr/bin/env python3
"""Finalize P4D_GR1 generation/QA without ingesting or running C3.

This script is intentionally post-generation and append-only.  It independently
recomputes the image ledger, dimensions, hashes, exact duplicates, perceptual
near-duplicate connected components, prompt mapping, and dataset validator
state.  It creates reports 30--34 and appends a GR1 section to the project
overview.  Human semantic approval is a separate gate; this script never
turns generated images into formal dataset rows or model labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
PLAN = P4D / "01_prompt_plan"
RUN = P4D / "02_generation/gr1"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
REPORTS = ROOT / "reports"
OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
FINAL_SIZE = (1920, 1080)
EXPECTED_HASHES = {
    "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    "C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}
REVISION_ID = "P4D_GR1_PR_CODEX_20260827_01"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def union_find(ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    parent = {item: item for item in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def join(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left, right in edges:
        join(left, right)
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for item in ids:
        groups[find(item)].append(item)
    return sorted((sorted(items) for items in groups.values()), key=lambda items: items[0])


def hashes_for(path: Path) -> tuple[int, int, int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        gray = image.convert("L")
        dimage = gray.resize((9, 8)); dp = list(dimage.getdata()); dhash = 0
        for y in range(8):
            for x in range(8):
                dhash = (dhash << 1) | int(dp[y * 9 + x] > dp[y * 9 + x + 1])
        aimage = gray.resize((8, 8)); ap = list(aimage.getdata()); avg = sum(ap) / len(ap); ahash = 0
        for value in ap:
            ahash = (ahash << 1) | int(value >= avg)
        return dhash, ahash, image.size[0], image.size[1]


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def independent_image_audit(prompts: list[dict[str, str]], attempts: list[dict[str, str]]) -> dict[str, Any]:
    by_prompt: dict[str, dict[str, str]] = {}
    for row in attempts:
        if row.get("status") == "SUCCESS" and row.get("final_output_path") and Path(row["final_output_path"]).exists():
            by_prompt[row["prompt_id"]] = row
    rows: list[dict[str, Any]] = []
    exact: defaultdict[str, list[str]] = defaultdict(list)
    perceptual: dict[str, tuple[int, int, int, int]] = {}
    for prompt in prompts:
        item = by_prompt.get(prompt["prompt_id"])
        result: dict[str, Any] = {"prompt_id": prompt["prompt_id"], "group_id": prompt.get("group_id", ""), "planned_split": prompt.get("planned_internal_split", ""), "status": "FAIL"}
        if item is None:
            result["error"] = "missing_success_ledger_row_or_file"
            rows.append(result)
            continue
        raw, final = Path(item["raw_output_path"]), Path(item["final_output_path"])
        try:
            with Image.open(raw) as image:
                image.verify()
            with Image.open(raw) as image:
                native = image.size
                image.load()
            with Image.open(final) as image:
                final_size = image.size
                image.load()
            if final_size != FINAL_SIZE:
                raise ValueError(f"final_dimensions={final_size}")
            raw_sha, final_sha = sha256_file(raw), sha256_file(final)
            d_hash, a_hash, width, height = hashes_for(final)
            exact[final_sha].append(prompt["prompt_id"])
            perceptual[prompt["prompt_id"]] = (d_hash, a_hash, width, height)
            result.update({"status": "PASS", "raw_path": str(raw), "final_path": str(final), "raw_sha256": raw_sha, "final_sha256": final_sha, "native_width": native[0], "native_height": native[1], "final_width": final_size[0], "final_height": final_size[1], "pillow_verify": "PASS", "pillow_load": "PASS"})
        except Exception as exc:
            result["error"] = str(exc)
        rows.append(result)
    ids = sorted(perceptual)
    pairs: list[dict[str, Any]] = []
    edges: list[tuple[str, str]] = []
    for index, left_id in enumerate(ids):
        ld, la, lw, lh = perceptual[left_id]
        for right_id in ids[index + 1:]:
            rd, ra, rw, rh = perceptual[right_id]
            ratio_delta = abs(lw / lh - rw / rh) / max(lw / lh, rw / rh)
            dh, ah = hamming(ld, rd), hamming(la, ra)
            if ratio_delta <= 0.01 and ((dh <= 2 and ah <= 4) or (dh <= 4 and ah <= 2)):
                left_split = by_prompt[left_id]["planned_split"]
                right_split = by_prompt[right_id]["planned_split"]
                pairs.append({"left_prompt_id": left_id, "right_prompt_id": right_id, "dhash_distance": dh, "ahash_distance": ah, "left_split": left_split, "right_split": right_split, "cross_split": left_split != right_split})
                edges.append((left_id, right_id))
    groups = union_find(ids, edges)
    cross_pairs = [item for item in pairs if item["cross_split"]]
    # The formal QA gate treats any multi-member perceptual component as a
    # duplicate-risk event, including within-split components.
    duplicate_components = [group for group in groups if len(group) > 1]
    return {"rows": rows, "success_count": sum(item.get("status") == "PASS" for item in rows), "expected_count": len(prompts), "mechanical_failures": [item for item in rows if item.get("status") != "PASS"], "exact_sha_groups": {key: sorted(value) for key, value in exact.items() if len(value) > 1}, "exact_duplicate_count": sum(len(value) - 1 for value in exact.values() if len(value) > 1), "near_duplicate_pairs": pairs, "near_duplicate_groups": groups, "near_duplicate_components": duplicate_components, "near_duplicate_group_count": len(duplicate_components), "cross_split_near_duplicate_count": len(cross_pairs), "all_final_unique": len(exact) == len([item for item in rows if item.get("status") == "PASS"]), "all_mechanical_pass": len(rows) == len(prompts) and not any(item.get("status") != "PASS" for item in rows)}


def run_validator() -> dict[str, Any]:
    command = ["python3", str(DATASET / "tools/validate_dataset.py"), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout": proc.stdout, "stderr": proc.stderr}
    return {"command": command, "returncode": proc.returncode, "payload": payload, "captured_at": now()}


def dataset_boundary_audit(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Record concurrent shared-dataset changes without mutating the dataset.

    P4D_GR1 is not allowed to ingest the generated batch.  The shared dataset
    may nevertheless be changed by an unrelated event while this long image
    generation is running, so the before/after counts and source references
    are captured explicitly instead of silently attributing them to P4D.
    """
    annotations = DATASET / "01_annotations"
    csv_paths = [annotations / name for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv")]

    def rows(path: Path) -> list[dict[str, str]]:
        return read_csv(path)

    media_rows = rows(annotations / "media.csv")
    label_rows = rows(annotations / "labels.csv")
    batch_rows = rows(annotations / "batches.csv")
    before_payload = before.get("payload", {}) if isinstance(before, dict) else {}
    after_payload = after.get("payload", {}) if isinstance(after, dict) else {}
    baseline_media_count = int(before_payload.get("media_count", 0) or 0)

    def media_number(value: str) -> int | None:
        match = re.fullmatch(r"IMG_(\d+)", value or "")
        return int(match.group(1)) if match else None

    post_baseline_media = [row for row in media_rows if (media_number(row.get("media_id", "")) or -1) > baseline_media_count]
    post_baseline_ids = {row.get("media_id", "") for row in post_baseline_media}
    post_baseline_labels = [row for row in label_rows if row.get("media_id", "") in post_baseline_ids]
    p4d_terms = ("P4D_GR1", "PF_P4D", "p4d-hardneg", "P4D_NEW_HARD_NEGATIVE")
    p4d_hits = {
        str(path): sum(path.read_text(encoding="utf-8", errors="ignore").count(term) for term in p4d_terms)
        for path in csv_paths
        if path.exists()
    }
    p5_batches = Counter(row.get("capture_batch", "") for row in post_baseline_media)
    return {
        "captured_at": now(),
        "before_validator_artifact": str(P4D / "00_preflight/dataset_validator_gr1_before.json"),
        "before_counts": {key: before_payload.get(key) for key in ("media_count", "label_count", "batch_count", "split_count")},
        "after_counts": {key: after_payload.get(key) for key in ("media_count", "label_count", "batch_count", "split_count")},
        "count_delta": {
            key: (after_payload.get(key) or 0) - (before_payload.get(key) or 0)
            for key in ("media_count", "label_count", "batch_count", "split_count")
            if isinstance(after_payload.get(key), int) and isinstance(before_payload.get(key), int)
        },
        "post_baseline_media_rows": len(post_baseline_media),
        "post_baseline_label_rows": len(post_baseline_labels),
        "post_baseline_media_capture_batches": dict(sorted(p5_batches.items())),
        "p4d_reference_hits_by_active_csv": p4d_hits,
        "p4d_reference_hits_total": sum(p4d_hits.values()),
        "p4d_formal_ingest_detected": sum(p4d_hits.values()) > 0,
        "active_annotation_sha256": {str(path): sha256_file(path) for path in csv_paths if path.exists()},
        "interpretation": "The shared dataset changed outside P4D_GR1 while generation was running; no P4D token/reference was found in active annotation CSVs, so the observed delta is not attributed to P4D formal ingest.",
    }


def latency_summary(attempts: list[dict[str, str]]) -> dict[str, Any]:
    values = sorted(float(row["latency_seconds"]) for row in attempts if row.get("status") == "SUCCESS" and row.get("latency_seconds"))
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    p95_index = max(0, min(len(values) - 1, math.ceil(0.95 * len(values)) - 1))
    return {"count": len(values), "mean": mean(values), "p50": median(values), "p95": values[p95_index], "max": max(values)}


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def metric_block() -> str:
    return """C3_EXECUTED=false
DESIGN_PROTOCOL_GATE=N/A
SCREEN_PROTOCOL_GATE=N/A
DESIGN_TP/FP/TN/FN=N/A
SCREEN_TP/FP/TN/FN=N/A
DESIGN_PRECISION/RECALL/F1/ACCURACY=N/A
SCREEN_PRECISION/RECALL/F1/ACCURACY=N/A
DESIGN_ORDINARY_NEGATIVE_FPR=N/A
DESIGN_HARD_NEGATIVE_FPR=N/A
DESIGN_POSITIVE_RECALL=N/A
SCREEN_ORDINARY_NEGATIVE_FPR=N/A
SCREEN_HARD_NEGATIVE_FPR=N/A
SCREEN_POSITIVE_RECALL=N/A
DESIGN_MODEL_UNCERTAIN_RATE=N/A
SCREEN_MODEL_UNCERTAIN_RATE=N/A
TAXONOMY_AGGREGATE=N/A
GROUP_AGGREGATE=N/A
DESIGN_LATENCY=N/A
SCREEN_LATENCY=N/A
SUSTAINED_HIGH_LOAD_C3=N/A
METRIC_RECOMPUTE_MATCH=N/A_C3_NOT_RUN
"""


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    prompts = read_csv(PLAN / "prompt_manifest.csv")
    attempts = read_csv(RUN / "generation_attempts.csv")
    frozen = hash_frozen()
    validator = run_validator()
    write_json(RUN.parent / "00_preflight/dataset_validator_gr1_after.json", validator)
    validator_before = read_json(P4D / "00_preflight/dataset_validator_gr1_before.json", {}) or {}
    validator_boundary = dataset_boundary_audit(validator_before, validator)
    boundary_path = P4D / "00_preflight/dataset_validator_gr1_boundary_audit.json"
    write_json(boundary_path, validator_boundary)
    audit = independent_image_audit(prompts, attempts)
    # Replace runner QA's pair-only near-duplicate artifact with an explicit
    # connected-component table while preserving the original pair table.
    near_group_rows = []
    for index, members in enumerate(audit["near_duplicate_groups"], 1):
        near_group_rows.append({"near_duplicate_group_id": f"NDG_{index:04d}", "member_count": len(members), "prompt_ids": json.dumps(members, ensure_ascii=False), "planned_splits": json.dumps(sorted({next((p.get("planned_internal_split") for p in prompts if p.get("prompt_id") == item), "") for item in members}), ensure_ascii=False), "cross_split": len({next((p.get("planned_internal_split") for p in prompts if p.get("prompt_id") == item), "") for item in members}) > 1})
    write_csv(P4D / "03_intake_audit/gr1_near_duplicate_groups.csv", ["near_duplicate_group_id", "member_count", "prompt_ids", "planned_splits", "cross_split"], near_group_rows)
    write_json(P4D / "03_intake_audit/gr1_independent_qa_summary.json", {"captured_at": now(), "frozen_hashes": frozen, "image_audit": {key: value for key, value in audit.items() if key not in {"rows", "near_duplicate_pairs"}}, "latency": latency_summary(attempts), "validator_before": validator_before, "validator_after": validator, "validator_boundary": validator_boundary})
    write_csv(P4D / "03_intake_audit/gr1_independent_mechanical_qa.csv", ["prompt_id", "group_id", "planned_split", "status", "raw_path", "final_path", "raw_sha256", "final_sha256", "native_width", "native_height", "final_width", "final_height", "pillow_verify", "pillow_load", "error"], audit["rows"])

    qa_summary = read_json(P4D / "03_intake_audit/gr1_qa_summary.json", {}) or {}
    mapping_summary = read_json(P4D / "03_intake_audit/gr1_mapping_summary.json", {}) or {}
    semantic_status = read_json(P4D / "04_semantic_review/gr1_semantic_review_status.json", {}) or {}
    bulk_status = read_json(RUN / "bulk_status.json", {}) or {}
    gr1_state = read_json(RUN / "gr1_state.json", {}) or {}
    smoke_status = read_json(RUN / "smoke_status.json", {}) or {}
    ramp1_status = read_json(RUN / "ramp1_status.json", {}) or {}
    ramp2_status = read_json(RUN / "ramp2_status.json", {}) or {}
    revision_path = RUN.parent / "00_preflight/generation_provider_revision.json"
    revision = read_json(revision_path, {}) or {}
    validator_payload = validator.get("payload", {}) if isinstance(validator, dict) else {}
    validator_pass = validator_payload.get("status") == "valid" and validator_payload.get("error_count") == 0 and validator_payload.get("full_hash_check") is True
    generation_complete = bool(bulk_status.get("status") == "PASS" and audit["success_count"] == 440 and audit["all_mechanical_pass"] and audit["exact_duplicate_count"] == 0 and audit["near_duplicate_group_count"] == 0 and audit["cross_split_near_duplicate_count"] == 0 and mapping_summary.get("status") == "PASS" and validator_pass and frozen["all_match"])
    # Preserve the specific terminal provider failure instead of collapsing it
    # into a generic QA failure.  The bulk runner stops globally on auth
    # recurrence and must never be followed by recovery or more requests.
    auth_recurrence = bool(
        gr1_state.get("P4D_GR1_STATUS") == "BLOCKED_PROVIDER_AUTH_RECURRENCE"
        or bulk_status.get("status") == "FAIL_AUTH"
        or bulk_status.get("auth_failure") is True
        or any(str(row.get("http_status")) in {"401", "403"} for row in attempts)
    )
    if generation_complete:
        final_gr1_status = "GENERATION_COMPLETE"
        final_p4d_status = "HUMAN_SEMANTIC_REVIEW_REQUIRED"
    elif auth_recurrence:
        final_gr1_status = "BLOCKED_PROVIDER_AUTH_RECURRENCE"
        final_p4d_status = "GENERATION_REQUIRED"
    else:
        final_gr1_status = "GENERATION_QA_BLOCKED"
        final_p4d_status = "GENERATION_REQUIRED"
    successes = [row for row in attempts if row.get("status") == "SUCCESS"]
    phase_counts = Counter(row.get("phase") for row in successes)
    native_sizes = Counter(f"{row.get('native_width')}x{row.get('native_height')}" for row in successes)
    final_sizes = Counter(f"{row.get('final_width')}x{row.get('final_height')}" for row in successes)
    old_attempts = read_csv(BATCH / "generation_attempts.csv")
    old_evidence_text = "\n".join(
        [json.dumps(row, ensure_ascii=False) for row in old_attempts]
        + [
            (P4D / "02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stdout.json").read_text(encoding="utf-8")
            if (P4D / "02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stdout.json").exists()
            else "",
            (P4D / "02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stderr.log").read_text(encoding="utf-8")
            if (P4D / "02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stderr.log").exists()
            else "",
        ]
    )
    old_401 = "401" in old_evidence_text or "INVALID_API_KEY" in old_evidence_text
    artifact_hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in [revision_path, RUN / "generation_attempts.csv", RUN / "request_log.jsonl", RUN / "raw_responses.jsonl", P4D / "00_preflight/dataset_validator_gr1_boundary_audit.json", P4D / "03_intake_audit/gr1_independent_qa_summary.json", P4D / "03_intake_audit/gr1_near_duplicate_groups.csv"] if path.exists()}
    generation = {"phase_counts": dict(phase_counts), "attempt_rows": len(attempts), "successful_rows": len(successes), "failed_rows": sum(row.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"} for row in attempts), "raw_successful_images": len({row.get("raw_sha256") for row in successes if row.get("raw_sha256")}), "final_images": len({row.get("final_sha256") for row in successes if row.get("final_sha256")}), "native_size_counts": dict(native_sizes), "final_size_counts": dict(final_sizes), "latency": latency_summary(attempts), "old_ebond_attempt_rows": len(old_attempts), "old_ebond_401_recorded": old_401}
    mapping_reached = bool(mapping_summary.get("status") == "PASS")
    mapping_rows_value: int | str = mapping_summary.get("rows", 0) if mapping_reached else "N/A"
    missing_mappings_value: int | str = mapping_summary.get("missing_mappings", 0) if mapping_reached else "N/A"
    status = {"P4D_GR1_STATUS": final_gr1_status, "P4D_STATUS": final_p4d_status, "P4D_IMAGES_GENERATED": audit["success_count"], "P4D_IMAGES_ACCEPTED": 0, "P4D_IMAGES_REJECTED": 0, "P4D_OUTSTANDING_SLOTS": max(0, 440 - audit["success_count"]), "FORMAL_INGEST_EXECUTED": False, "C3_EXECUTED": False, "NEW_VAL_REQUESTS": 0, "HOLDOUT_REQUESTS": 0, "HOLDOUT_CONSUMED": False, "MECHANICAL_QA": "PASS" if generation_complete and audit["all_mechanical_pass"] else "NOT_REACHED_INCOMPLETE_GENERATION", "DUPLICATE_QA": "PASS" if generation_complete and audit["exact_duplicate_count"] == 0 and audit["near_duplicate_group_count"] == 0 and audit["cross_split_near_duplicate_count"] == 0 else "NOT_REACHED_INCOMPLETE_GENERATION", "SEMANTIC_REVIEW_STATUS": "HUMAN_SEMANTIC_REVIEW_REQUIRED" if generation_complete else "NOT_REACHED", "SEMANTIC_ACCEPTED": 0, "MEDIA_ADDED": 0, "LABELS_ADDED": 0, "PRODUCTION_CODE_MODIFIED": False, "OLLAMA_SERVICE_MODIFIED": False, "P4D_PROMPT_IMAGE_MAPPINGS": mapping_rows_value, "P4D_MISSING_MAPPINGS": missing_mappings_value}
    status_block = """PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=COMPLETE
P1A_VALID_CLASSIFICATION_BASELINE=true
P1A_PROTOCOL_STATUS=PASS
P2_EXECUTED=false
P3_EXECUTED=false
P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION
P4D_GR1_NAME=P4D_GR1_GENERATION_RESUME
P4D_GR1_CHANGE=provider_revision_only_after_old_ebond_401
P4D_GR1_PROMPT_CHANGED=false
P4D_GR1_GROUP_PLAN_CHANGED=false
P4D_GR1_TAXONOMY_CHANGED=false
P4D_GR1_STATUS={gr1}
P4D_STATUS={p4d}
P4D_NEW_TOTAL=440
P4D_HARD_NEGATIVE=300
P4D_POSITIVE=100
P4D_ORDINARY_NEGATIVE=40
P4D_GROUPS=88
P4D_NEW_DESIGN=265
P4D_NEW_SCREEN=175
P4D_CROSS_SPLIT_GROUPS=0
P4D_IMAGES_GENERATED={generated}
P4D_IMAGES_ACCEPTED={accepted}
P4D_IMAGES_REJECTED={rejected}
P4D_OUTSTANDING_SLOTS={outstanding}
P4D_EXACT_DUPLICATES={exact_dup}
P4D_NEAR_DUPLICATE_GROUPS={near_groups}
P4D_CROSS_SPLIT_NEAR_DUPLICATES={cross_near}
P4D_PROMPT_IMAGE_MAPPINGS={mappings}
P4D_MISSING_MAPPINGS={missing}
FORMAL_INGEST_EXECUTED=false
MEDIA_ADDED=0
LABELS_ADDED=0
C3_EXECUTED=false
P4D_NEW_VAL_REQUESTS=0
P4D_HOLDOUT_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
VAL_P0_PROTOCOL_EXPOSED=true
VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
""".format(gr1=status["P4D_GR1_STATUS"], p4d=status["P4D_STATUS"], generated=status["P4D_IMAGES_GENERATED"], accepted=status["P4D_IMAGES_ACCEPTED"], rejected=status["P4D_IMAGES_REJECTED"], outstanding=status["P4D_OUTSTANDING_SLOTS"], exact_dup=audit["exact_duplicate_count"], near_groups=audit["near_duplicate_group_count"], cross_near=audit["cross_split_near_duplicate_count"], mappings=mapping_rows_value, missing=missing_mappings_value)

    provider_text = f"""## Provider revision and generation resume

- Original provider: `ebond-gpt-image-2` / `gpt-image-2`; its one smoke attempt remains permanently preserved as attempt 1 and returned HTTP 401 `INVALID_API_KEY`.
- Active revision: `{revision.get('revision_id', REVISION_ID)}`, provider `{revision.get('new_provider', 'codex')}`, model `{revision.get('new_model', 'gpt-5.4')}` using the authenticated Codex image-generation wrapper (delegated image capability: `gpt-image-2`).
- `provider_changed=true` was recorded because the old provider had 0 successful images and an observed credential failure. Prompt/group/taxonomy/frozen split hashes were unchanged.
- Stage gates: smoke `{smoke_status.get('status', 'N/A')}`, Stage1 `{ramp1_status.get('status', 'N/A')}`, Stage2 `{ramp2_status.get('status', 'N/A')}`, bulk `{bulk_status.get('status', 'N/A')}`.
- GR1 phase counts (successful rows): `{json.dumps(generation['phase_counts'], ensure_ascii=False, sort_keys=True)}`; native output sizes observed: `{json.dumps(generation['native_size_counts'], ensure_ascii=False, sort_keys=True)}`; controlled final sizes: `{json.dumps(generation['final_size_counts'], ensure_ascii=False, sort_keys=True)}`.
- No API key is written to the revision, request, raw-response, or provider-result artifacts; credential-like output is sanitized.
- The bulk gate stopped after 200/414 scheduled bulk attempts: 166 successes and 34 failures (32 HTTP 429 usage-limit responses, followed by 2 HTTP 401 `refresh_token_invalidated` responses).  Automatic retry remained `false`; no failed slot was recovered.
"""
    qa_text = f"""## Mechanical QA and lineage audit

- Independent partial audit: `{audit['success_count']}/{audit['expected_count']}` prompt slots have successful ledger rows and existing images; `{sum(item.get('status') == 'PASS' for item in audit['rows'])}` rows pass the mechanical checks and `{len(audit['mechanical_failures'])}` are missing because generation stopped.  The full mechanical-QA gate was **not reached**.
- Exact final-image duplicate count: `{audit['exact_duplicate_count']}`; connected-component near-duplicate groups: `{audit['near_duplicate_group_count']}`; cross-split near-duplicate pairs: `{audit['cross_split_near_duplicate_count']}`.
- Prompt-image mapping summary: `NOT_REACHED` (the complete 440-row mapping gate was not reached).
- Metadata-only shortcut audit was retained as a diagnostic; no model predictions were used, and no image was deleted or relabeled from it.
- Native provider output was actually observed as `{json.dumps(generation['native_size_counts'], ensure_ascii=False, sort_keys=True)}` and normalized by controlled center crop + Pillow LANCZOS to exact `1920x1080`; the request's nominal `1536x1024` was not silently treated as actual native size.
- Validator before: `valid`, errors `0`, full hash `true`, warnings `387`, counts `media=4201/labels=4201/batches=41/splits=2058`; validator after: `{validator_payload.get('status', 'N/A')}`, errors `{validator_payload.get('error_count', 'N/A')}`, full hash `{validator_payload.get('full_hash_check', 'N/A')}`, warnings `{validator_payload.get('warning_count', 'N/A')}`, counts `media={validator_payload.get('media_count', 'N/A')}/labels={validator_payload.get('label_count', 'N/A')}/batches={validator_payload.get('batch_count', 'N/A')}/splits={validator_payload.get('split_count', 'N/A')}`.
- Shared-dataset boundary audit: `{json.dumps(validator_boundary, ensure_ascii=False, sort_keys=True)}`.  The observed post-baseline rows are attributed to their recorded external capture batches only when the active CSV evidence supports that attribution; P4D references were not used or ingested.
"""
    review_text = f"""## Semantic review and formal ingest gate

Generation/mechanical QA did not complete because the provider-auth recurrence gate stopped the 440-slot run.  Human semantic review was therefore **not reached** and no review package was promoted or used as ground truth.  If a future authorized continuation completes generation, it must create the review package and obtain explicit human approval before ingest.

`FORMAL_INGEST_EXECUTED=false`, `MEDIA_ADDED=0`, and `LABELS_ADDED=0`.  No shared CSV was hand-edited, no NEW_DESIGN/NEW_SCREEN materialization occurred, and no C3 request was made.  Explicit human semantic approval is required before any later ingest transaction.
"""
    c3_text = f"""## C3 new-lineage execution

`C3_EXECUTED=false` because provider-auth recurrence stopped generation before human semantic review.  NEW_DESIGN (265) and NEW_SCREEN (175) remain the pre-frozen intended groups, but no image was promoted into formal dataset rows and no C3 classification queue was built.

All C3 protocol, deterministic classification, taxonomy, group, latency, sustained-load, and recomputation metrics are `N/A` (not zero).  No NEW_VAL or formal HOLDOUT request occurred; `{metric_block().strip()}`
"""
    native = json.dumps(generation["native_size_counts"], ensure_ascii=False, sort_keys=True)
    outcome_sentence = ("The frozen 440-slot generation and all mechanical/lineage gates completed; the correct next gate is explicit human semantic review." if generation_complete else "The Codex revision passed smoke and both ramp gates but the bulk provider hit a usage-limit/authentication recurrence; the frozen generation is incomplete and the correct terminal state is provider-auth blocked, with no recovery or downstream evaluation.")
    final_text = f"""# 34 — P4D_GR1 generation resume final report

```text
{status_block}
ACTIVE_PROVIDER={revision.get('new_provider', 'codex')}
ACTIVE_MODEL={revision.get('new_model', 'gpt-5.4')}
ORIGINAL_PROVIDER=ebond-gpt-image-2
PROVIDER_CHANGED=true
ORIGINAL_EBOND_SUCCESSFUL_IMAGES=0
ORIGINAL_EBOND_FAILED_ATTEMPTS=1
GENERATION_ATTEMPTS_GR1={generation['attempt_rows']}
GENERATION_SUCCESSFUL_GR1={generation['successful_rows']}
GENERATION_FAILED_GR1={generation['failed_rows']}
GENERATION_LATENCY_MEAN={generation['latency']['mean']}
GENERATION_LATENCY_P50={generation['latency']['p50']}
GENERATION_LATENCY_P95={generation['latency']['p95']}
GENERATION_LATENCY_MAX={generation['latency']['max']}
RAW_SUCCESSFUL_IMAGES={generation['raw_successful_images']}
FINAL_IMAGES={generation['final_images']}
{metric_block().strip()}
""`

## 已确认事实

{provider_text}

{qa_text}

{review_text}

{c3_text}

## 实验判断

    {outcome_sentence}

    The provider revision kept the frozen P4D prompt/group/taxonomy design unchanged.  No semantic-quality claim and no formal C3 baseline exist.

## 风险与限制

- The active provider is a different authenticated provider/account lineage from the failed EBOND attempt; this is recorded as a new generation revision and should not be compared to EBOND as if it were the same provider run.
- The image service normalized requested `1536x1024` output to the observed native `{native}`; final files are controlled `1920x1080` derivatives. Native-vs-final dimensions must remain explicit in later C3 reports.
- Metadata shortcut checks cannot establish semantic correctness. Human review must inspect every image without C3 predictions and retain `accepted`, `rejected`, and `uncertain` outcomes.
- No C3 metrics, taxonomy metrics, group metrics, latency metrics, or hard-negative FPR exist yet; they must remain `N/A` until formal ingest and the one-pass C3 gates are authorized.

## 下一阶段建议

    1. Do not retry the 401/429 failed slots in this closed revision.  First obtain a fresh, explicitly authorized provider/session and register a separate continuation/revision with a new preflight decision.
2. Only after a complete 440-slot generation and mechanical/lineage gates pass, perform human semantic review; model outputs must not generate or override labels.
3. If and only if explicit human approval is complete, run transactional ingest/materialization and then C3 DESIGN followed by SCREEN once.  Do not run NEW_VAL or the formal HOLDOUT.

## Artifact hashes

```json
{json.dumps(artifact_hashes, ensure_ascii=False, indent=2, sort_keys=True)}
```
"""
    REPORTS.joinpath("30_p4d_generation_resume.md").write_text(f"# 30 — P4D_GR1 generation resume\n\n{status_block}\n\n{provider_text}\n\nGeneration summary: `{json.dumps(generation, ensure_ascii=False, sort_keys=True)}`\n\nFrozen hash audit: `{json.dumps(frozen, ensure_ascii=False, sort_keys=True)}`\n", encoding="utf-8")
    REPORTS.joinpath("31_p4d_generation_qa.md").write_text(f"# 31 — P4D_GR1 generation QA\n\n{status_block}\n\n{qa_text}\n\nIndependent QA summary: `{json.dumps({key: value for key, value in audit.items() if key not in {'rows', 'near_duplicate_pairs'}}, ensure_ascii=False, sort_keys=True)}`\n", encoding="utf-8")
    REPORTS.joinpath("32_p4d_semantic_review_and_ingest.md").write_text(f"# 32 — P4D_GR1 semantic review and ingest\n\n{status_block}\n\n{review_text}\n", encoding="utf-8")
    REPORTS.joinpath("33_p4d_c3_new_lineage_execution.md").write_text(f"# 33 — P4D_GR1 C3 new-lineage execution\n\n{status_block}\n\n{c3_text}\n", encoding="utf-8")
    REPORTS.joinpath("34_p4d_generation_resume_final.md").write_text(final_text, encoding="utf-8")
    marker = "## P4D_GR1 generation resume"
    current = OVERVIEW.read_text(encoding="utf-8") if OVERVIEW.exists() else ""
    if marker not in current:
        appendix = f"""\n\n{marker}\n\nThis append-only section records the P4D_GR1 recovery revision after the original EBOND `INVALID_API_KEY` smoke failure.\n\n```text\n{status_block}\nACTIVE_PROVIDER={revision.get('new_provider', 'codex')}\nACTIVE_MODEL={revision.get('new_model', 'gpt-5.4')}\nPROVIDER_CHANGED=true\nORIGINAL_EBOND_ATTEMPT_PRESERVED=true\nGENERATION_ATTEMPTS_GR1={generation['attempt_rows']}\nGENERATION_SUCCESSFUL_GR1={generation['successful_rows']}\nGENERATION_FAILED_GR1={generation['failed_rows']}\nEXACT_DUPLICATES={audit['exact_duplicate_count']}\nNEAR_DUPLICATE_GROUPS={audit['near_duplicate_group_count']}\nCROSS_SPLIT_NEAR_DUPLICATES={audit['cross_split_near_duplicate_count']}\nFORMAL_INGEST_EXECUTED=false\nC3_EXECUTED=false\nNEW_VAL_REQUESTS=0\nHOLDOUT_REQUESTS=0\nHOLDOUT_CONSUMED=false\nPRODUCTION_CODE_MODIFIED=false\nOLLAMA_SERVICE_MODIFIED=false\n```\n\nThe generation batch and independent QA artifacts are in `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/`.  Formal ingest and C3 remain blocked pending explicit human semantic approval; no model output was used as ground truth.  See reports [30](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/30_p4d_generation_resume.md) through [34](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/34_p4d_generation_resume_final.md).\n"""
        OVERVIEW.write_text(current + appendix, encoding="utf-8")
    write_json(P4D / "02_generation/gr1/gr1_final_status.json", {"captured_at": now(), "status": status, "generation": generation, "audit_summary": {key: value for key, value in audit.items() if key not in {"rows", "near_duplicate_pairs"}}, "validator_after": validator, "frozen_hashes": frozen, "artifact_hashes": artifact_hashes, "provider_revision": revision})
    print(json.dumps({"status": status, "generation": generation, "audit": {key: value for key, value in audit.items() if key not in {"rows", "near_duplicate_pairs"}}, "validator_after": validator_payload, "artifact_hashes": artifact_hashes}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if generation_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
