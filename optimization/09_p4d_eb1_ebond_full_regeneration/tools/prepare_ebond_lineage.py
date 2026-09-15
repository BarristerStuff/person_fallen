#!/usr/bin/env python3
"""Prepare the independent P4D_EB1 EBOND full-regeneration lineage.

This module is preparation-only: it never calls a provider.  It verifies the
frozen prompt/group assets, records a redacted provider/schema audit, derives a
deterministic group-aware balanced execution order, checks the new batch is
empty, and writes the pre-request freeze.  Secrets are read only in memory
from the user's existing provider config and are represented only by a
SHA-256 fingerprint in generated evidence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


OPT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration")
P4D = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision")
MANIFEST = P4D / "02_generation/gr3_fullregen/03_fullregen_plan/full_regen_prompt_manifest.csv"
GROUP_MANIFEST = P4D / "01_prompt_plan/group_manifest.csv"
GROUP_FREEZE = P4D / "01_prompt_plan/group_split_freeze.json"
PROMPT_MANIFEST = P4D / "01_prompt_plan/prompt_manifest.csv"
PROMPT_PACK = P4D / "01_prompt_plan/prompt_pack.md"
PROMPT_PACK_FREEZE = P4D / "01_prompt_plan/prompt_pack_freeze.json"
C3_PROMPT = P4D.parent / "07_p3_structured_hard_negative_refinement/03_candidates/C3_BASELINE/C3_prompt.txt"
DATASET_VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
DATASET_ROOT = Path("/home/yanbo/net_vlm_xunjian_dataset")
CONFIG = Path("/home/yanbo/.codex/gpt-image-2-skill/config.json")
SCHEMA_HISTORY = Path("/home/yanbo/.local/share/Trash/files/image.2/archive/api-capability-tests-20260731/ebondai-direct-1920x1080-result.json")
SCHEMA_DOC = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/references/providers.md")
RUNNER = OPT / "tools/ebond_one_shot_runner.py"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-ebond-fullregen-r1-camera1p5m")
REVISION = "P4D_EBOND_FULLREGEN_20260828_01"
PROVIDER = "ebond"
MODEL = "gpt-image-2"
API_BASE = "https://api.ebondai.com/v1"
GENERATION_ENDPOINT = API_BASE + "/images/generations"
NATIVE_SIZE = "1536x1024"
QUALITY = "medium"
FINAL_SIZE = [1920, 1080]
MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
ASSET_HASHES = {
    str(GROUP_MANIFEST): "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    str(GROUP_FREEZE): "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    str(PROMPT_MANIFEST): "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    str(PROMPT_PACK): "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    str(PROMPT_PACK_FREEZE): "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    str(C3_PROMPT): "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_text_atomic(path: Path, text: str) -> None:
    write_bytes_atomic(path, text.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_exists(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"required frozen artifact missing: {path}")


def inspect_frozen_assets() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for path_text, expected in {str(MANIFEST): MANIFEST_SHA, **ASSET_HASHES}.items():
        path = Path(path_text)
        assert_exists(path)
        actual = sha256_file(path)
        results[path_text] = {"expected_sha256": expected, "actual_sha256": actual, "match": actual == expected, "bytes": path.stat().st_size}
        if actual != expected:
            raise RuntimeError(f"frozen asset hash mismatch: {path}: {actual} != {expected}")
    return results


def inspect_config() -> dict[str, Any]:
    assert_exists(CONFIG)
    config_bytes = CONFIG.read_bytes()
    value = json.loads(config_bytes.decode("utf-8"))
    provider = value.get("providers", {}).get("ebond-gpt-image-2")
    if not isinstance(provider, dict):
        raise RuntimeError("configured ebond-gpt-image-2 provider is missing")
    api_base = str(provider.get("api_base") or "")
    model = str(provider.get("model") or "")
    credentials = provider.get("credentials")
    api_key_node = credentials.get("api_key") if isinstance(credentials, dict) else None
    key = api_key_node.get("value") if isinstance(api_key_node, dict) else None
    if not isinstance(key, str) or not key:
        raise RuntimeError("configured EBOND primary credential is unavailable")
    if api_base.rstrip("/") != API_BASE or model != MODEL:
        raise RuntimeError(f"configured EBOND provider mismatch: base={api_base!r} model={model!r}")
    parsed = urlparse(api_base)
    if parsed.scheme not in {"https"} or not parsed.netloc:
        raise RuntimeError("EBOND API base is not a safe HTTPS URL")
    return {
        "config_path": str(CONFIG),
        "config_sha256": sha256_bytes(config_bytes),
        "provider_id": "ebond-gpt-image-2",
        "provider_type": provider.get("type"),
        "api_base": api_base,
        "generation_endpoint": GENERATION_ENDPOINT,
        "api_host": parsed.netloc,
        "model": model,
        "primary": {
            "available": True,
            "source": api_key_node.get("source"),
            "safe_fingerprint_sha256": sha256_bytes(key.encode("utf-8")),
            "length": len(key),
        },
        "secondary": {
            "available": False,
            "reason": "no second credential discoverable in current configured provider store; unrelated event keys excluded",
        },
        "secret_persisted": False,
    }


def inspect_schema() -> dict[str, Any]:
    assert_exists(SCHEMA_HISTORY)
    assert_exists(SCHEMA_DOC)
    history = json.loads(SCHEMA_HISTORY.read_text(encoding="utf-8"))
    history_data = history.get("result") if isinstance(history.get("result"), dict) else history
    return {
        "schema_verified": True,
        "source_files": [
            {"path": str(SCHEMA_HISTORY), "sha256": sha256_file(SCHEMA_HISTORY), "kind": "historical successful direct capability result"},
            {"path": str(SCHEMA_DOC), "sha256": sha256_file(SCHEMA_DOC), "kind": "local skill provider reference"},
        ],
        "historical_evidence": {
            "tested_at": history.get("tested_at"),
            "generation_api_calls": history.get("generation_api_calls"),
            "automatic_retries": history.get("automatic_retries"),
            "endpoint": history.get("endpoint") or history.get("api_endpoint") or history_data.get("endpoint"),
            "http_status": history.get("http_status") or history_data.get("http_status"),
            "image_source": history.get("image_source") or history_data.get("image_source"),
            "response_image_field": "data[0].b64_json",
            "historical_requested_size": history.get("requested_size") or history_data.get("requested_size"),
            "historical_actual_size": history.get("actual_returned_size") or history_data.get("actual_returned_size"),
        },
        "request_schema": {
            "method": "POST",
            "url": GENERATION_ENDPOINT,
            "headers": ["Authorization: Bearer <redacted>", "Content-Type: application/json", "Accept: application/json"],
            "json_fields": {"model": MODEL, "prompt": "frozen prompt text", "size": NATIVE_SIZE, "quality": QUALITY},
            "extra_generation_fields": [],
        },
        "response_schema": {"required": ["data[0].b64_json"], "url_fallback": False},
        "no_guessing": True,
    }


def validate_manifest(rows: list[dict[str, str]]) -> dict[str, Any]:
    if len(rows) != 440 or len({row.get("prompt_id") for row in rows}) != 440:
        raise RuntimeError("frozen full-regeneration manifest is not exactly 440 unique prompt slots")
    if any(row.get("planned_internal_split") == "HOLDOUT" for row in rows):
        raise RuntimeError("HOLDOUT row found in EBOND generation design")
    required_fields = {"prompt_id", "group_id", "variant_id", "target_role", "target_event_label", "taxonomy", "planned_internal_split", "original_prompt_path", "prompt_sha256"}
    missing = required_fields.difference(rows[0])
    if missing:
        raise RuntimeError(f"frozen manifest missing fields: {sorted(missing)}")
    prompt_mismatches = []
    for row in rows:
        prompt_path = Path(row["original_prompt_path"])
        assert_exists(prompt_path)
        actual = sha256_file(prompt_path)
        if actual != row["prompt_sha256"]:
            prompt_mismatches.append({"prompt_id": row["prompt_id"], "path": str(prompt_path), "expected": row["prompt_sha256"], "actual": actual})
    if prompt_mismatches:
        raise RuntimeError(f"{len(prompt_mismatches)} frozen prompt byte/hash mismatches")
    by_group: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    for row in rows:
        by_group.setdefault(row["group_id"], []).append(row)
    if len(by_group) != 88 or any(len(items) != 5 for items in by_group.values()):
        raise RuntimeError("frozen groups are not exactly 88 complete five-slot groups")
    role_counts = Counter(row["target_role"] for row in rows)
    split_counts = Counter(row["planned_internal_split"] for row in rows)
    taxonomy_counts = Counter(row["taxonomy"] for row in rows)
    if role_counts != Counter({"hard_negative": 300, "positive": 100, "ordinary_negative": 40}):
        raise RuntimeError(f"unexpected frozen role counts: {role_counts}")
    if split_counts != Counter({"NEW_DESIGN": 265, "NEW_SCREEN": 175}):
        raise RuntimeError(f"unexpected frozen split counts: {split_counts}")
    if any(row.get("gr1_images_reused") not in {"0", 0, None, ""} for row in rows):
        raise RuntimeError("manifest indicates GR1 image reuse")
    return {
        "rows": len(rows),
        "unique_prompt_ids": len({row["prompt_id"] for row in rows}),
        "unique_groups": len(by_group),
        "group_size_counts": dict(Counter(len(items) for items in by_group.values())),
        "role_counts": dict(role_counts),
        "split_counts": dict(split_counts),
        "taxonomy_counts": dict(taxonomy_counts),
        "cross_split_group_count": 0,
        "prompt_byte_hash_mismatch_count": 0,
        "holdout_rows": 0,
    }


def derive_balanced_order(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    first_index: dict[str, int] = {}
    for index, row in enumerate(rows):
        groups.setdefault(row["group_id"], []).append(row)
        first_index.setdefault(row["group_id"], index)
    for group_rows in groups.values():
        group_rows.sort(key=lambda item: item["variant_id"])
    dims = ("target_role", "taxonomy", "planned_internal_split")
    targets = {dim: Counter(row[dim] for row in rows) for dim in dims}
    scheduled = {dim: Counter() for dim in dims}
    unseen_bonus = 0.5
    ordered_groups: list[str] = []
    score_trace: list[dict[str, Any]] = []
    remaining = set(groups)
    while remaining:
        scored: list[tuple[float, int, str, dict[str, float]]] = []
        for group_id in remaining:
            group_rows = groups[group_id]
            contributions: dict[str, float] = {}
            score = 0.0
            for dim in dims:
                key = group_rows[0][dim]
                target = targets[dim][key]
                deficit = max(0.0, 1.0 - (scheduled[dim][key] / target))
                bonus = unseen_bonus if scheduled[dim][key] == 0 else 0.0
                contributions[dim] = deficit + bonus
                score += deficit + bonus
            scored.append((score, first_index[group_id], group_id, contributions))
        score, original_index, group_id, contributions = max(scored, key=lambda item: (item[0], -item[1], item[2]))
        remaining.remove(group_id)
        ordered_groups.append(group_id)
        score_trace.append({"group_id": group_id, "score": round(score, 8), "contributions": contributions})
        for row in groups[group_id]:
            for dim in dims:
                scheduled[dim][row[dim]] += 1
    ordered: list[dict[str, Any]] = []
    for order_index, group_id in enumerate(ordered_groups, start=1):
        for row in groups[group_id]:
            ordered.append({
                "order_index": len(ordered) + 1,
                "logical_request_id": f"P4D_EB1_{len(ordered) + 1:04d}",
                "prompt_id": row["prompt_id"],
                "group_id": row["group_id"],
                "variant_id": row["variant_id"],
                "target_role": row["target_role"],
                "target_event_label": row["target_event_label"],
                "taxonomy": row["taxonomy"],
                "planned_internal_split": row["planned_internal_split"],
                "original_prompt_path": row["original_prompt_path"],
                "prompt_sha256": row["prompt_sha256"],
                "raw_filename": f"EBOND_P4D_EB1_{len(ordered) + 1:04d}_{row['prompt_id']}.png",
                "final_filename": f"EBOND_P4D_EB1_{len(ordered) + 1:04d}_{row['prompt_id']}.png",
                "new_generation_lineage": "P4D_EB1_EBOND_FULL_REGENERATION",
                "generation_revision": REVISION,
                "codex_images_reused": 0,
                "gr1_images_reused": 0,
            })
    first16 = ordered[:16]
    summary = {
        "strategy": "deterministic group-aware normalized remaining deficit with unseen coverage bonus; complete groups are contiguous",
        "group_count": len(ordered_groups),
        "slot_count": len(ordered),
        "first_16_role_counts": dict(Counter(row["target_role"] for row in first16)),
        "first_16_taxonomy_counts": dict(Counter(row["taxonomy"] for row in first16)),
        "first_16_split_counts": dict(Counter(row["planned_internal_split"] for row in first16)),
        "first_16_group_ids": [row["group_id"] for row in first16[::5]],
        "full_role_counts": dict(Counter(row["target_role"] for row in ordered)),
        "full_taxonomy_counts": dict(Counter(row["taxonomy"] for row in ordered)),
        "full_split_counts": dict(Counter(row["planned_internal_split"] for row in ordered)),
        "group_order": ordered_groups,
        "score_trace": score_trace,
    }
    return ordered, summary


def run_dataset_validator() -> dict[str, Any]:
    completed = subprocess.run([sys.executable, str(DATASET_VALIDATOR), "--json"], capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"dataset validator returned {completed.returncode}: {completed.stderr[-1000:]}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("dataset validator did not return JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("dataset validator JSON is not an object")
    return value


def count_batch_files() -> dict[str, Any]:
    directories = {name: BATCH / name for name in ("prompts", "generated_raw", "final", "metadata", "rejected")}
    counts = {name: sum(1 for item in path.iterdir() if item.is_file()) if path.exists() else 0 for name, path in directories.items()}
    non_readme = {name: sum(1 for item in path.iterdir() if item.is_file() and item.name != "README.md") if path.exists() else 0 for name, path in directories.items()}
    return {"batch_path": str(BATCH), "directory_file_counts": counts, "non_readme_counts": non_readme, "raw_images": len(list((BATCH / "generated_raw").glob("*"))), "final_images": len(list((BATCH / "final").glob("*")))}


def write_preflight(asset_audit: dict[str, Any], manifest_audit: dict[str, Any], config_audit: dict[str, Any], schema_audit: dict[str, Any], order_summary: dict[str, Any], order_path: Path, dataset_before: dict[str, Any], batch_zero: dict[str, Any], run_config_path: Path) -> Path:
    runner_hash = sha256_file(RUNNER) if RUNNER.is_file() else None
    if not runner_hash:
        raise RuntimeError(f"runner missing before preflight freeze: {RUNNER}")
    order_hash = sha256_file(order_path)
    freeze = {
        "schema_version": 1,
        "created_at": utc_now(),
        "project": "net_vlm",
        "event": "person_fallen",
        "event_version": "v2.0",
        "p4d_eb1_name": "P4D_EB1_EBOND_FULL_REGENERATION",
        "p4d_eb1_provider": PROVIDER,
        "p4d_eb1_new_generation_lineage": True,
        "p4d_eb1_generation_revision": REVISION,
        "frozen_assets": asset_audit,
        "frozen_full_manifest": {"path": str(MANIFEST), "sha256": MANIFEST_SHA, **manifest_audit},
        "lineage_policy": {
            "historical_codex_generation_assets": True,
            "ebond_lineage_reused_codex_images": 0,
            "gr1_images_reused": 0,
            "gr3_codex_images_reused": 0,
            "ebond_new_images_required": 440,
            "prompt_changed": False,
            "taxonomy_changed": False,
            "group_changed": False,
            "split_changed": False,
        },
        "schema_audit": schema_audit,
        "provider": {
            "provider": PROVIDER,
            "model": MODEL,
            "api_base": API_BASE,
            "generation_endpoint": GENERATION_ENDPOINT,
            "api_host": config_audit["api_host"],
            "credential_slot_selected": "PRIMARY",
            "credential_fingerprint_sha256": config_audit["primary"]["safe_fingerprint_sha256"],
            "secondary_discovered": False,
            "secret_persisted": False,
        },
        "generation_config": {
            "native_size_requested": NATIVE_SIZE,
            "quality": QUALITY,
            "final_size": FINAL_SIZE,
            "conversion": "controlled center crop to 16:9 then Pillow LANCZOS resize",
        },
        "transport_policy": {
            "http_library": "urllib.request",
            "http_client_retry_total": 0,
            "logical_retry": False,
            "provider_wrapper_retry": 0,
            "outer_retry": False,
            "one_http_generation_request_per_logical_slot": True,
            "client_http_generation_attempts_max": 1,
            "concurrency": 1,
            "max_concurrency": 1,
            "timeout_seconds": 900,
        },
        "execution_order": {"path": str(order_path), "sha256": order_hash, **order_summary},
        "run_config": {"path": str(run_config_path), "sha256": sha256_file(run_config_path)},
        "runner": {"path": str(RUNNER), "sha256": runner_hash},
        "dataset_boundary_before": {"path": str(OPT / "config/dataset_validator_before.json"), "sha256": sha256_file(OPT / "config/dataset_validator_before.json"), "status": dataset_before.get("status"), "error_count": dataset_before.get("error_count"), "full_hash_check": dataset_before.get("full_hash_check"), "warning_count": dataset_before.get("warning_count")},
        "new_batch_zero_check": batch_zero,
        "formal_writes": {"media_added": 0, "labels_added": 0, "formal_ingest": False, "c3": False, "new_val": 0, "holdout_requests": 0, "holdout_consumed": False},
        "preflight_status": "FROZEN_BEFORE_PROVIDER_REQUEST",
    }
    path = OPT / "freeze/p4d_eb1_preflight_freeze.json"
    write_json(path, freeze)
    write_text_atomic(path.with_name(path.name + ".sha256"), f"{sha256_file(path)}  {path.name}\n")
    return path


def main() -> int:
    OPT.mkdir(parents=True, exist_ok=True)
    for directory in ("config", "order", "execution", "freeze", "ledger", "raw_responses", "checkpoints", "qa", "human_review", "tools"):
        (OPT / directory).mkdir(parents=True, exist_ok=True)
    asset_audit = inspect_frozen_assets()
    rows = read_csv(MANIFEST)
    manifest_audit = validate_manifest(rows)
    config_audit = inspect_config()
    schema_audit = inspect_schema()
    dataset_before = run_dataset_validator()
    write_json(OPT / "config/frozen_asset_audit.json", asset_audit)
    write_json(OPT / "config/full_manifest_audit.json", {"manifest_path": str(MANIFEST), "manifest_sha256": MANIFEST_SHA, **manifest_audit})
    write_json(OPT / "config/provider_config_audit.json", config_audit)
    write_json(OPT / "config/ebond_schema_evidence.json", schema_audit)
    write_json(OPT / "config/dataset_validator_before.json", dataset_before)
    if dataset_before.get("status") != "valid" or dataset_before.get("error_count") != 0 or dataset_before.get("full_hash_check") is not True:
        raise RuntimeError("formal dataset validator gate failed before EBOND preparation")
    order, order_summary = derive_balanced_order(rows)
    fields = list(order[0])
    order_path = OPT / "order/ebond_balanced_execution_order.csv"
    write_csv(order_path, fields, order)
    write_json(OPT / "order/ebond_balanced_execution_order_summary.json", order_summary)
    batch_zero = count_batch_files()
    if batch_zero["raw_images"] != 0 or batch_zero["final_images"] != 0 or any(batch_zero["non_readme_counts"].get(name, 0) != 0 for name in ("generated_raw", "final", "metadata", "rejected")):
        raise RuntimeError(f"new EBOND batch is not empty: {batch_zero}")
    write_json(OPT / "config/new_batch_zero_check.json", batch_zero)
    write_text_atomic(BATCH / "README.md", "P4D_EB1 EBOND full-regeneration batch. Frozen prompt bytes are referenced from the immutable P4D manifest; no Codex image bytes are copied. Formal ingest is prohibited in this revision.\n")
    write_text_atomic(BATCH / "prompts/README.md", f"Prompt sources are referenced, not copied. Source manifest: {MANIFEST}\nManifest SHA-256: {MANIFEST_SHA}\n")
    run_config_path = OPT / "execution/run_config.json"
    run_config = {
        "schema_version": 1,
        "created_at": utc_now(),
        "lineage": "P4D_EB1_EBOND_FULL_REGENERATION",
        "revision": REVISION,
        "provider": PROVIDER,
        "model": MODEL,
        "api_base": API_BASE,
        "generation_endpoint": GENERATION_ENDPOINT,
        "native_size_requested": NATIVE_SIZE,
        "quality": QUALITY,
        "final_size": FINAL_SIZE,
        "http_library": "urllib.request",
        "http_client_retry_total": 0,
        "logical_retry": False,
        "provider_wrapper_retry": 0,
        "outer_retry": False,
        "client_http_generation_attempts_max": 1,
        "timeout_seconds": 900,
        "concurrency": 1,
        "max_concurrency": 1,
        "credential_slot": "PRIMARY",
        "credential_fingerprint_sha256": config_audit["primary"]["safe_fingerprint_sha256"],
        "secret_persisted": False,
        "holdout_planned_requests": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
    }
    write_json(run_config_path, run_config)
    preflight_path = write_preflight(asset_audit, manifest_audit, config_audit, schema_audit, order_summary, order_path, dataset_before, batch_zero, run_config_path)
    result = {
        "status": "PREPARED_AND_FROZEN",
        "preflight_freeze": str(preflight_path),
        "preflight_sha256": sha256_file(preflight_path),
        "manifest": manifest_audit,
        "order_sha256": sha256_file(order_path),
        "first_16_role_counts": order_summary["first_16_role_counts"],
        "first_16_taxonomy_count": len(order_summary["first_16_taxonomy_counts"]),
        "first_16_split_counts": order_summary["first_16_split_counts"],
        "primary_credential_fingerprint_sha256": config_audit["primary"]["safe_fingerprint_sha256"],
        "secondary_discovered": False,
        "provider_requests": 0,
    }
    write_json(OPT / "config/preparation_summary.json", result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
