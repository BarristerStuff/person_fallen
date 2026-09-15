#!/usr/bin/env python3
"""Freeze the P3 S1 candidates before any SCREEN request."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
DESIGN_MANIFEST = P2 / "01_internal_split/p2_design_manifest.csv"
SCREEN_MANIFEST = P2 / "01_internal_split/p2_screen_manifest.csv"
CANARY = P3 / "04_canary/canary_manifest.csv"
REGISTRY = P3 / "03_candidates/candidate_registry.csv"
FREEZE = P3 / "03_candidates/candidate_freeze.json"
FREEZE_SHA = P3 / "03_candidates/candidate_freeze.sha256"
CONFIG = P3 / "03_candidates/p3_request_config.json"
RUNNER = ROOT / "tools/p3_inference_runner.py"
C3_PROMPT = P3 / "03_candidates/C3_BASELINE/C3_prompt.txt"
S1_DIR = P3 / "03_candidates/S1_STRUCTURED"
EXPECTED_C3_PROMPT = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
EXPECTED_P2_WINNER_FREEZE = "ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def exclusive_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    if path.exists():
        raise SystemExit(f"P3_CANDIDATE_ARTIFACT_ALREADY_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def exclusive_json(path: Path, obj: object) -> None:
    if path.exists():
        raise SystemExit(f"P3_CANDIDATE_ARTIFACT_ALREADY_EXISTS:{path}")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    if sha(C3_PROMPT) != EXPECTED_C3_PROMPT:
        raise SystemExit("P3_STATUS=BLOCKED_C3_FREEZE_MISMATCH")
    p2_winner_freeze = P2 / "05_winner_freeze/p2_winner_freeze.json"
    if sha(p2_winner_freeze) != EXPECTED_P2_WINNER_FREEZE:
        raise SystemExit("P3_STATUS=BLOCKED_C3_FREEZE_MISMATCH")
    design = read_csv(DESIGN_MANIFEST)
    screen = read_csv(SCREEN_MANIFEST)
    if len(design) != 190 or len(screen) != 120:
        raise SystemExit("P3_CANDIDATE_FREEZE_MANIFEST_COUNT_INVALID")
    if {r["media_id"] for r in design} & {r["media_id"] for r in screen}:
        raise SystemExit("P3_CANDIDATE_FREEZE_MEDIA_LEAKAGE")
    if {r["group_id"] for r in design} & {r["group_id"] for r in screen}:
        raise SystemExit("P3_CANDIDATE_FREEZE_GROUP_LEAKAGE")
    if any((r.get("original_split") or r.get("split")) in {"VAL", "HOLDOUT"} for r in design + screen):
        raise SystemExit("P3_CANDIDATE_FREEZE_VAL_HOLDOUT_PRESENT")

    # Fixed, deterministic DESIGN-only canary: 3 positive, 2 ordinary
    # negative, 5 hard negative, 2 GT-uncertain.  For deterministic roles,
    # take one row per scenario/group to maximize group coverage.
    selected: list[dict[str, str]] = []
    for role, count in [("positive", 3), ("negative", 2), ("hard_negative", 5)]:
        seen: set[str] = set()
        candidates = sorted((r for r in design if r["sample_role"] == role), key=lambda r: (r["scenario_id"], r["media_id"]))
        for row in candidates:
            if row["scenario_id"] in seen:
                continue
            selected.append(row)
            seen.add(row["scenario_id"])
            if len(seen) == count:
                break
        if len(seen) != count:
            raise SystemExit(f"P3_CANARY_QUOTA_UNSATISFIED:{role}")
    selected.extend(sorted((r for r in design if r["sample_role"] == "uncertain"), key=lambda r: r["media_id"])[:2])
    if len(selected) != 12:
        raise SystemExit("P3_CANARY_COUNT_INVALID")
    canary_fields = ["media_id", "image_path", "image_sha256", "event_label", "sample_role", "scenario_id", "group_id", "original_split", "p2_internal_role", "source_type", "canary_role"]
    canary_rows = [{**row, "canary_role": "P3_STRUCTURED_CANARY"} for row in selected]
    exclusive_csv(CANARY, canary_rows, canary_fields)

    prompt = S1_DIR / "S1_prompt.txt"
    schema = S1_DIR / "S1_schema.json"
    rule = S1_DIR / "S1_rule.json"
    for path in [prompt, schema, rule]:
        if not path.is_file():
            raise SystemExit(f"P3_CANDIDATE_ASSET_MISSING:{path}")
    registry_fields = ["candidate_id", "status", "prompt_path", "prompt_sha256", "schema_path", "schema_sha256", "rule_path", "rule_sha256", "response_stream", "candidate_eligible_for_screen", "design_forensic_categories_targeted", "design_rationale"]
    registry_rows = [
        {"candidate_id": "C3_BASELINE", "status": "BASELINE_REUSE", "prompt_path": str(C3_PROMPT), "prompt_sha256": sha(C3_PROMPT), "schema_path": "", "schema_sha256": "", "rule_path": "", "rule_sha256": "", "response_stream": "historical_p2_screen_reuse_only", "candidate_eligible_for_screen": "false", "design_forensic_categories_targeted": "baseline", "design_rationale": "P2 C3 baseline; no new structured request for C3 SCREEN"},
        {"candidate_id": "S1_DIRECT", "status": "FROZEN", "prompt_path": str(prompt), "prompt_sha256": sha(prompt), "schema_path": str(schema), "schema_sha256": sha(schema), "rule_path": str(rule), "rule_sha256": sha(rule), "response_stream": "S1_STRUCTURED_SHARED", "candidate_eligible_for_screen": "true", "design_forensic_categories_targeted": "kneeling_or_half_kneeling;exercise_pushup_or_plank", "design_rationale": "Explicit real-person, support-surface, torso/pelvis, active-support, and posture fields; direct model adjudication"},
        {"candidate_id": "S1_RULE", "status": "FROZEN", "prompt_path": str(prompt), "prompt_sha256": sha(prompt), "schema_path": str(schema), "schema_sha256": sha(schema), "rule_path": str(rule), "rule_sha256": sha(rule), "response_stream": "S1_STRUCTURED_SHARED", "candidate_eligible_for_screen": "true", "design_forensic_categories_targeted": "kneeling_or_half_kneeling;exercise_pushup_or_plank", "design_rationale": "Same single S1 response; frozen deterministic evidence rule adjudication"},
        {"candidate_id": "OPTIONAL_S2", "status": "NOT_CREATED", "prompt_path": "", "prompt_sha256": "", "schema_path": "", "schema_sha256": "", "rule_path": "", "rule_sha256": "", "response_stream": "none", "candidate_eligible_for_screen": "false", "design_forensic_categories_targeted": "", "design_rationale": "S1 schema covers the observed DESIGN mechanism; P3 limit is one optional S2 and it is not needed"},
    ]
    exclusive_csv(REGISTRY, registry_rows, registry_fields)

    freeze = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
        "family": "HARD_NEGATIVE_REFINEMENT",
        "event_name": "person_fallen",
        "event_definition_version": "v2.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": "qwen3.5:4b",
        "model_digest": "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd",
        "ollama_version": "0.23.2",
        "endpoint": "http://192.168.20.62:11434",
        "preprocess": "letterbox_448x336_jpeg_q70",
        "parser": "response_only",
        "thinking_fallback": False,
        "request_config_path": str(CONFIG),
        "config_sha256": sha(CONFIG),
        "runner_path": str(RUNNER),
        "runner_sha256": sha(RUNNER),
        "design_manifest_path": str(DESIGN_MANIFEST),
        "design_manifest_sha256": sha(DESIGN_MANIFEST),
        "screen_manifest_path": str(SCREEN_MANIFEST),
        "screen_manifest_sha256": sha(SCREEN_MANIFEST),
        "canary_manifest_path": str(CANARY),
        "canary_manifest_sha256": sha(CANARY),
        "p2_winner_freeze_path": str(p2_winner_freeze),
        "p2_winner_freeze_sha256": sha(p2_winner_freeze),
        "p2_c3_screen_predictions_path": str(P2 / "04_screening/C3/predictions.csv"),
        "p2_c3_screen_predictions_sha256": sha(P2 / "04_screening/C3/predictions.csv"),
        "candidate_registry_path": str(REGISTRY),
        "candidate_registry_sha256": sha(REGISTRY),
        "screen_blind_before_candidate_freeze": True,
        "p2_screen_individual_errors_used_for_p3_design": False,
        "val_individual_errors_used_for_p3_design": False,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "optional_s2_created": False,
        "candidates": {},
    }
    for row in registry_rows:
        freeze["candidates"][row["candidate_id"]] = {
            "status": row["status"],
            "candidate_eligible_for_screen": row["candidate_eligible_for_screen"] == "true",
            "prompt_path": row["prompt_path"] or None,
            "prompt_sha256": row["prompt_sha256"] or None,
            "schema_path": row["schema_path"] or None,
            "schema_sha256": row["schema_sha256"] or None,
            "rule_path": row["rule_path"] or None,
            "rule_sha256": row["rule_sha256"] or None,
            "response_stream": row["response_stream"],
        }
    exclusive_json(FREEZE, freeze)
    freeze_hash = sha(FREEZE)
    with FREEZE_SHA.open("x", encoding="utf-8") as handle:
        handle.write(f"{freeze_hash}  candidate_freeze.json\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps({"P3_CANDIDATE_FREEZE": "CREATED", "candidate_freeze_sha256": freeze_hash, "canary_rows": len(canary_rows), "optional_s2_created": False}, sort_keys=True))


if __name__ == "__main__":
    main()
