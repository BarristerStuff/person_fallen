#!/usr/bin/env python3
"""P2 preflight and blind, group-disjoint DEV internal split.

This program intentionally never parses P1A or P1R prediction rows. Historical
prediction files are byte-hashed only. It is safe to run before candidate
freeze without exposing SCREEN outcomes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
PREFLIGHT = P2 / "00_preflight"
SPLIT_DIR = P2 / "01_internal_split"
DEV_MANIFEST = ROOT / "03_p1a_think_false_protocol/dev/dev_manifest.csv"
SPLIT_SEED = "PERSON_FALLEN_V2_P2_INTERNAL_SPLIT_V1"

EXPECTED = {
    "prompt": "b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4",
    "frozen_splits": "16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a",
    "frozen_manifest": "771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6",
    "p1a_dev_predictions": "5d67e80d753ed71ae33cf9c222a8793b829c60a0bc1ff5ee09085518bf9d359b",
    "p1a_dev_manifest": "7f8ff256a8da3cc6451e1ec3f6a842dc9b3eb6f4080e4fb5a1a49dda9bc7d7d8",
    "p1r_val_manifest": "f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762",
    "p1r_val_predictions": "7f221795f9a21febd47d5861ee58492dbef6eb00a1032ea240bc1c536de1e38b",
}
FILES = {
    "prompt": ROOT / "00_definition/p0_prompt.txt",
    "frozen_splits": ROOT / "01_data/frozen_splits.csv",
    "frozen_manifest": ROOT / "01_data/frozen_manifest.csv",
    "p1a_dev_predictions": ROOT / "03_p1a_think_false_protocol/dev/predictions.csv",
    "p1a_dev_manifest": DEV_MANIFEST,
    "p1r_val_manifest": ROOT / "04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv",
    "p1r_val_predictions": ROOT / "04_p1r_freeze_binding_recovery/val/predictions.csv",
}
MODEL_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def fetch_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def role_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return dict(sorted(Counter(row["sample_role"] for row in rows).items()))


def main() -> None:
    for directory in [PREFLIGHT, SPLIT_DIR, P2 / "02_forensics", P2 / "03_candidates", P2 / "04_screening", P2 / "05_winner_freeze", P2 / "06_val"]:
        directory.mkdir(parents=True, exist_ok=True)

    actual = {name: sha256(path) for name, path in FILES.items()}
    mismatches = {name: {"expected": EXPECTED[name], "actual": actual[name]} for name in EXPECTED if actual[name] != EXPECTED[name]}
    if mismatches:
        raise SystemExit("P2_STATUS=BLOCKED_HISTORY_HASH_MISMATCH " + json.dumps(mismatches, sort_keys=True))

    validator = json.loads(subprocess.check_output(["python3", str(DATASET / "tools/validate_dataset.py"), "--json"], text=True))
    if validator.get("status") != "valid" or validator.get("error_count") != 0 or not validator.get("full_hash_check"):
        raise SystemExit("P2_STATUS=BLOCKED_DATASET_VALIDATOR")

    version = fetch_json("http://192.168.20.62:11434/api/version")
    tags = fetch_json("http://192.168.20.62:11434/api/tags")
    models = [item for item in tags.get("models", []) if item.get("name") == "qwen3.5:4b"]
    if len(models) != 1 or models[0].get("digest") != MODEL_DIGEST:
        raise SystemExit("P2_STATUS=BLOCKED_MODEL_IDENTITY_CHANGED")

    now = datetime.now(timezone.utc).isoformat()
    atomic_json(PREFLIGHT / "dataset_validator_before.json", validator)
    atomic_json(PREFLIGHT / "model_identity.json", {"captured_at_utc": now, "ollama_version": version.get("version"), "model": models[0]})
    atomic_json(PREFLIGHT / "source_hash_inventory.json", {"captured_at_utc": now, "hashes": {name: {"path": str(FILES[name]), "sha256": actual[name], "expected_sha256": EXPECTED[name], "match": True} for name in FILES}})

    with DEV_MANIFEST.open(newline="", encoding="utf-8") as handle:
        dev = list(csv.DictReader(handle))
    if len(dev) != 310 or len({row["media_id"] for row in dev}) != 310 or any(row["split"] != "DEV" for row in dev):
        raise SystemExit("P2_STATUS=BLOCKED_DEV_MANIFEST_SHAPE")

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in dev:
        groups[row["group_id"]].append(row)
    if len(groups) != 31:
        raise SystemExit("P2_STATUS=BLOCKED_DEV_GROUP_COUNT")
    mixed = {group: sorted({row["sample_role"] for row in rows}) for group, rows in groups.items() if len({row["sample_role"] for row in rows}) != 1}
    if mixed:
        raise SystemExit("P2_STATUS=BLOCKED_MIXED_ROLE_GROUPS " + json.dumps(mixed, sort_keys=True))

    by_role: dict[str, list[str]] = defaultdict(list)
    for group, rows in groups.items():
        by_role[rows[0]["sample_role"]].append(group)
    for role in by_role:
        by_role[role].sort(key=lambda group: hashlib.sha256(f"{SPLIT_SEED}|{role}|{group}".encode()).hexdigest())
    target_design_groups = {role: round(len(group_ids) * 0.60) for role, group_ids in by_role.items()}
    if sum(target_design_groups.values()) != 19:
        raise SystemExit("P2_STATUS=BLOCKED_INTERNAL_SPLIT_ROUNDING")
    design_groups = {group for role, group_ids in by_role.items() for group in group_ids[: target_design_groups[role]]}
    screen_groups = set(groups) - design_groups
    if design_groups & screen_groups or len(design_groups) != 19 or len(screen_groups) != 12:
        raise SystemExit("P2_STATUS=BLOCKED_INTERNAL_SPLIT_GROUP_LEAKAGE")

    fields = ["media_id", "image_path", "image_sha256", "event_label", "sample_role", "scenario_id", "group_id", "original_split", "p2_internal_role", "source_type"]
    def convert(row: dict[str, str], internal_role: str) -> dict[str, str]:
        image_path = row["source_image_path"]
        if not Path(image_path).is_file() or sha256(Path(image_path)) != row["image_sha256"]:
            raise SystemExit("P2_STATUS=BLOCKED_IMAGE_HASH_MISMATCH")
        return {
            "media_id": row["media_id"],
            "image_path": image_path,
            "image_sha256": row["image_sha256"],
            "event_label": row["event_label"],
            "sample_role": row["sample_role"],
            "scenario_id": row["scenario_id"],
            "group_id": row["group_id"],
            "original_split": row["split"],
            "p2_internal_role": internal_role,
            "source_type": row["source_type"],
        }
    design = [convert(row, "P2_DESIGN") for row in dev if row["group_id"] in design_groups]
    screen = [convert(row, "P2_SCREEN") for row in dev if row["group_id"] in screen_groups]
    design.sort(key=lambda row: row["media_id"])
    screen.sort(key=lambda row: row["media_id"])

    design_path = SPLIT_DIR / "p2_design_manifest.csv"
    screen_path = SPLIT_DIR / "p2_screen_manifest.csv"
    split_path = SPLIT_DIR / "p2_internal_split.json"
    if split_path.exists() or design_path.exists() or screen_path.exists():
        raise SystemExit("P2_STATUS=BLOCKED_INTERNAL_SPLIT_ALREADY_EXISTS")
    atomic_csv(design_path, fields, design)
    atomic_csv(screen_path, fields, screen)
    split_record = {
        "stage": "P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION",
        "split_seed": SPLIT_SEED,
        "source_dev_manifest_path": str(DEV_MANIFEST),
        "source_dev_manifest_sha256": actual["p1a_dev_manifest"],
        "design_manifest_path": str(design_path),
        "design_manifest_sha256": sha256(design_path),
        "screen_manifest_path": str(screen_path),
        "screen_manifest_sha256": sha256(screen_path),
        "dev_rows": len(dev),
        "dev_group_count": len(groups),
        "design_rows": len(design),
        "design_group_count": len(design_groups),
        "screen_rows": len(screen),
        "screen_group_count": len(screen_groups),
        "cross_design_screen_group_count": len(design_groups & screen_groups),
        "design_role_counts": role_counts(design),
        "screen_role_counts": role_counts(screen),
        "screen_blind_before_candidate_freeze": True,
        "p1a_prediction_rows_read_before_split": 0,
        "val_individual_rows_read_before_split": 0,
        "holdout_rows": 0,
    }
    atomic_json(split_path, split_record)
    split_sha = sha256(split_path)
    sidecar = SPLIT_DIR / "p2_internal_split.sha256"
    with sidecar.open("x", encoding="utf-8") as handle:
        handle.write(f"{split_sha}  p2_internal_split.json\n")
        handle.flush()
        os.fsync(handle.fileno())
    verification = {
        "verification_result": "PASS",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "internal_split_sha256": split_sha,
        "design_manifest_sha256": sha256(design_path),
        "screen_manifest_sha256": sha256(screen_path),
        "design_screen_group_overlap": sorted(design_groups & screen_groups),
        "screen_blind_before_candidate_freeze": True,
        "holdout_rows": 0,
    }
    atomic_json(SPLIT_DIR / "p2_internal_split_verification.json", verification)
    print(json.dumps({"P2_PREFLIGHT": "PASS", "P2_INTERNAL_SPLIT": "PASS", **split_record, "p2_internal_split_sha256": split_sha}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
