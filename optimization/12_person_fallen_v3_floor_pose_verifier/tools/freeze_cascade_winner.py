#!/usr/bin/env python3
"""Freeze the sole DEV-passing floor-pose cascade before SCREEN/VAL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "protocol/cascade_config.json"
PROMPT = ROOT / "prompt/V3-CASCADE-S2-C0_prompt.txt"
RUNNER = ROOT / "tools/run_cascade.py"
MANIFESTS = ROOT / "manifests"
FREEZE = ROOT / "freeze/person_fallen_v3_cascade_dev_winner.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", choices=["V3-CASCADE-448", "V3-CASCADE-896"])
    parser.add_argument("--dev-summary", default="")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    summary_path = Path(args.dev_summary) if args.dev_summary else ROOT / f"eval/runs/dev_{args.candidate}/summary.json"
    if not summary_path.is_file():
        raise SystemExit("CASCADE_WINNER_FREEZE_DEV_SUMMARY_MISSING")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "COMPLETE" or summary.get("phase") != "dev" or summary.get("candidate") != args.candidate or summary.get("gate", {}).get("pass") is not True:
        raise SystemExit("CASCADE_WINNER_FREEZE_DEV_GATE_NOT_PASS")
    if summary.get("holdout_requests") != 0 or summary.get("holdout_consumed") is not False:
        raise SystemExit("CASCADE_WINNER_FREEZE_HOLDOUT_BOUNDARY_INVALID")
    if summary.get("config_sha256") != sha256(CONFIG) or summary.get("stage2_prompt_sha256") != sha256(PROMPT) or summary.get("runner_sha256") != sha256(RUNNER):
        raise SystemExit("CASCADE_WINNER_FREEZE_BINDING_MISMATCH")
    freeze = {
        "status": "WINNER_FROZEN_FOR_SCREEN_AND_VAL",
        "revision_id": cfg["revision_id"],
        "event_name": "person_fallen",
        "event_definition_version": "v3.0",
        "winner_candidate": args.candidate,
        "stage1_candidate": "V3-C0-448",
        "stage1_resolution": [448, 336],
        "stage2_resolution": cfg["stage2"]["candidate_resolutions"][args.candidate],
        "winner_dev_gate_pass": True,
        "winner_dev_summary_path": str(summary_path),
        "winner_dev_summary_sha256": sha256(summary_path),
        "dev_manifest_sha256": sha256(MANIFESTS / "dev_full_manifest.csv"),
        "screen_manifest_sha256": sha256(MANIFESTS / "screen_full_manifest.csv"),
        "val_manifest_sha256": sha256(MANIFESTS / "val_full_manifest.csv"),
        "stage2_prompt_sha256": sha256(PROMPT),
        "config_sha256": sha256(CONFIG),
        "runner_sha256": sha256(RUNNER),
        "selection_rule": "freeze V3-CASCADE-448 immediately if it passes; otherwise V3-CASCADE-896 is permitted only when DEV summary marks fallback_eligible_stage2_896=true and it passes",
        "screen_and_val_locked": True,
        "phase_locked": True,
        "post_winner_tuning_allowed": False,
        "final_holdout_executed": False,
        "holdout_consumed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat()
    }
    if FREEZE.is_file():
        existing = json.loads(FREEZE.read_text(encoding="utf-8"))
        if existing != freeze:
            raise SystemExit("CASCADE_WINNER_FREEZE_ALREADY_EXISTS_DIFFERENT")
    else:
        write_json(FREEZE, freeze)
    print(json.dumps(freeze, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
