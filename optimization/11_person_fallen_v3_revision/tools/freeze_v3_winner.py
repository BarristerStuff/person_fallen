#!/usr/bin/env python3
"""Freeze the only DEV-passing v3 candidate before SCREEN/VAL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMAP = ROOT / "remap"
CONFIG = ROOT / "protocol/v3_eval_config.json"
PROMPT = ROOT / "prompt/V3-C0_prompt.txt"
RUNNER = ROOT / "tools/run_v3_eval.py"
FREEZE = ROOT / "freeze/person_fallen_v3_dev_winner.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", choices=["V3-C0-448", "V3-C0-896"])
    parser.add_argument("--dev-summary", default="")
    args = parser.parse_args()
    resolution = {"V3-C0-448": [448, 336], "V3-C0-896": [896, 672]}[args.candidate]
    summary_path = Path(args.dev_summary) if args.dev_summary else ROOT / f"eval/runs/dev_{args.candidate}/summary.json"
    dev_manifest = REMAP / "person_fallen_v3_dev_manifest.csv"
    screen_manifest = REMAP / "person_fallen_v3_screen_manifest.csv"
    val_manifest = REMAP / "person_fallen_v3_val_manifest.csv"
    if not summary_path.is_file():
        raise SystemExit("V3_WINNER_FREEZE_DEV_SUMMARY_MISSING")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "COMPLETE" or summary.get("phase") != "dev" or summary.get("candidate") != args.candidate:
        raise SystemExit("V3_WINNER_FREEZE_DEV_SUMMARY_INVALID")
    if summary.get("gate", {}).get("pass") is not True:
        raise SystemExit("V3_WINNER_FREEZE_DEV_GATE_NOT_PASS")
    if summary.get("resolution") != f"{resolution[0]}x{resolution[1]}":
        raise SystemExit("V3_WINNER_FREEZE_RESOLUTION_MISMATCH")
    if summary.get("manifest_sha256") != sha256(dev_manifest):
        raise SystemExit("V3_WINNER_FREEZE_DEV_MANIFEST_MISMATCH")
    if summary.get("prompt_sha256") != sha256(PROMPT) or summary.get("config_sha256") != sha256(CONFIG) or summary.get("runner_sha256") != sha256(RUNNER):
        raise SystemExit("V3_WINNER_FREEZE_RUN_BINDING_MISMATCH")
    if summary.get("holdout_requests") != 0 or summary.get("holdout_consumed") is not False:
        raise SystemExit("V3_WINNER_FREEZE_HOLDOUT_BOUNDARY_INVALID")
    freeze = {
        "status": "WINNER_FROZEN_FOR_SCREEN_AND_VAL",
        "revision_id": "PERSON_FALLEN_V3_ANOMALOUS_NEAR_GROUND_20260901_01",
        "event_name": "person_fallen",
        "event_definition_version": "v3.0",
        "winner_candidate_id": args.candidate,
        "winner_resolution": resolution,
        "winner_dev_gate_pass": True,
        "winner_dev_summary_path": str(summary_path),
        "winner_dev_summary_sha256": sha256(summary_path),
        "dev_manifest_sha256": sha256(dev_manifest),
        "screen_manifest_sha256": sha256(screen_manifest),
        "val_manifest_sha256": sha256(val_manifest),
        "prompt_sha256": sha256(PROMPT),
        "config_sha256": sha256(CONFIG),
        "runner_sha256": sha256(RUNNER),
        "selection_rule": "only candidate that passes every preregistered DEV gate; no higher resolution if 448 passes",
        "screen_and_val_locked": True,
        "phase_locked": True,
        "post_winner_tuning_allowed": False,
        "final_holdout_executed": False,
        "holdout_consumed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if FREEZE.is_file():
        existing = json.loads(FREEZE.read_text(encoding="utf-8"))
        if existing != freeze:
            raise SystemExit("V3_WINNER_FREEZE_ALREADY_EXISTS_DIFFERENT")
    else:
        FREEZE.parent.mkdir(parents=True, exist_ok=True)
        write_json(FREEZE, freeze)
    print(json.dumps(freeze, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
