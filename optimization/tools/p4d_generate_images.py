#!/usr/bin/env python3
"""Run one-at-a-time P4D image generation with durable attempt evidence."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
NODE = "node"
CLI = "/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs"
PROVIDER = "ebond-gpt-image-2"
MODEL = "gpt-image-2"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def nested_values(value: Any, wanted: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in wanted and child not in (None, ""):
                found.append(str(child))
            found.extend(nested_values(child, wanted))
    elif isinstance(value, list):
        for child in value:
            found.extend(nested_values(child, wanted))
    return found


def parse_json_stdout(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"raw_json": value}
    except json.JSONDecodeError:
        # Preserve the complete CLI output while still exposing an error object.
        return {"ok": False, "parse_error": True, "raw_stdout": raw}


def append_attempt(path: Path, row: dict[str, Any]) -> None:
    fields = ["attempt_id", "prompt_id", "timestamp", "provider", "model", "model_version", "seed", "provider_request_id", "status", "output_path", "notes"]
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})
        handle.flush()
        os.fsync(handle.fileno())


def existing_status(attempts_path: Path) -> dict[str, str]:
    if not attempts_path.exists():
        return {}
    statuses: dict[str, str] = {}
    with attempts_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            prompt_id = row.get("prompt_id", "")
            if prompt_id:
                statuses[prompt_id] = row.get("status", "")
    return statuses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="maximum new prompt requests; 0 means all remaining")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--provider", default=PROVIDER)
    parser.add_argument("--native-size", default="1536x1024")
    parser.add_argument("--quality", default="medium")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.provider != PROVIDER:
        parser.error(f"provider is frozen to {PROVIDER}")

    plan_dir = P4D / "01_prompt_plan"
    manifest_path = plan_dir / "prompt_manifest.csv"
    pack_freeze = plan_dir / "prompt_pack_freeze.json"
    group_freeze = plan_dir / "group_split_freeze.json"
    if not manifest_path.exists() or not pack_freeze.exists() or not group_freeze.exists():
        raise RuntimeError("P4D prompt/group freeze artifacts are required before generation")
    pack_meta = json.loads(pack_freeze.read_text(encoding="utf-8"))
    group_meta = json.loads(group_freeze.read_text(encoding="utf-8"))
    if pack_meta.get("prompt_count") != 440 or pack_meta.get("images_generated") != 0:
        raise RuntimeError("prompt pack is missing or generation state is not initial")
    if group_meta.get("design_screen_decided_before_generation") is not True or group_meta.get("cross_split_group_count") != 0:
        raise RuntimeError("pre-generation group freeze is not valid")
    rows = read_rows(manifest_path)
    if len(rows) != 440 or len({row["prompt_id"] for row in rows}) != 440:
        raise RuntimeError("prompt manifest cardinality/uniqueness mismatch")

    attempts_path = BATCH / "generation_attempts.csv"
    logs_dir = P4D / "02_generation" / "cli_logs"
    result_dir = P4D / "02_generation" / "provider_results"
    logs_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    BATCH.mkdir(parents=True, exist_ok=True)
    lock_path = P4D / "02_generation" / ".generation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("another P4D generation runner holds the lock") from exc

    try:
        statuses = existing_status(attempts_path)
        pending = []
        for row in rows:
            prompt_id = row["prompt_id"]
            output_path = BATCH / "generated_raw" / f"{prompt_id}.png"
            if statuses.get(prompt_id) == "SUCCESS" and output_path.exists():
                continue
            pending.append((row, output_path))
        if args.limit:
            pending = pending[: args.limit]
        print(json.dumps({"pending_before_run": len(pending), "limit": args.limit, "provider": args.provider, "native_size": args.native_size, "quality": args.quality}, ensure_ascii=False, sort_keys=True))

        completed = 0
        failed = 0
        for row, output_path in pending:
            prompt_id = row["prompt_id"]
            prompt_path = Path(row["prompt_path"])
            prompt = prompt_path.read_text(encoding="utf-8").rstrip("\n")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path = logs_dir / f"{prompt_id}.stdout.json"
            stderr_path = logs_dir / f"{prompt_id}.stderr.log"
            result_path = result_dir / f"{prompt_id}.json"
            command = [
                NODE, CLI, "--json", "--json-events", "--provider", args.provider,
                "images", "generate", "--model", MODEL, "--prompt", prompt,
                "--out", str(output_path), "--format", "png", "--size", args.native_size,
                "--quality", args.quality,
            ]
            start = time.monotonic()
            try:
                proc = subprocess.run(command, check=False, capture_output=True, text=True, timeout=args.timeout)
                elapsed = time.monotonic() - start
                stdout_path.write_text(proc.stdout, encoding="utf-8")
                stderr_path.write_text(proc.stderr, encoding="utf-8")
                payload = parse_json_stdout(proc.stdout)
                result_path.write_text(json.dumps({"prompt_id": prompt_id, "elapsed_seconds": elapsed, "returncode": proc.returncode, "payload": payload}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                success = proc.returncode == 0 and payload.get("ok") is True and output_path.exists() and output_path.stat().st_size > 0
                request_ids = nested_values(payload, {"provider_request_id", "request_id", "id"})
                provider_id = request_ids[0] if request_ids else "unknown"
                seed_values = nested_values(payload, {"seed"})
                seed = seed_values[0] if seed_values else "unknown"
                notes = f"returncode={proc.returncode};elapsed_seconds={elapsed:.3f};native_size={args.native_size};prompt_sha256={row['prompt_sha256']}"
                if not success:
                    notes += ";provider_result_not_accepted"
                status = "SUCCESS" if success else "FAILED"
            except subprocess.TimeoutExpired as exc:
                elapsed = time.monotonic() - start
                stdout_path.write_text((exc.stdout or ""), encoding="utf-8")
                stderr_path.write_text((exc.stderr or ""), encoding="utf-8")
                payload = {"ok": False, "timeout": True, "timeout_seconds": args.timeout}
                result_path.write_text(json.dumps({"prompt_id": prompt_id, "elapsed_seconds": elapsed, "returncode": None, "payload": payload}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                provider_id = "unknown"
                seed = "unknown"
                notes = f"timeout_seconds={args.timeout};prompt_sha256={row['prompt_sha256']}"
                status = "FAILED"

            attempt_id = f"P4D_GEN_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{prompt_id}"
            append_attempt(attempts_path, {
                "attempt_id": attempt_id,
                "prompt_id": prompt_id,
                "timestamp": now(),
                "provider": args.provider,
                "model": MODEL,
                "model_version": MODEL,
                "seed": seed,
                "provider_request_id": provider_id,
                "status": status,
                "output_path": str(output_path) if status == "SUCCESS" else "",
                "notes": notes,
            })
            if status == "SUCCESS":
                completed += 1
                print(json.dumps({"prompt_id": prompt_id, "status": status, "output": str(output_path), "sha256": sha256_file(output_path)}, ensure_ascii=False, sort_keys=True), flush=True)
            else:
                failed += 1
                print(json.dumps({"prompt_id": prompt_id, "status": status, "output": str(output_path), "notes": notes}, ensure_ascii=False, sort_keys=True), flush=True)

        all_statuses = existing_status(attempts_path)
        success_count = sum(1 for row in rows if all_statuses.get(row["prompt_id"]) == "SUCCESS" and (BATCH / "generated_raw" / f"{row['prompt_id']}.png").exists())
        failed_count = sum(1 for row in rows if all_statuses.get(row["prompt_id"]) == "FAILED")
        state = {
            "stage": "P4D_NEW_HARD_NEGATIVE_DEV_REVISION",
            "provider": args.provider,
            "model": MODEL,
            "native_size": args.native_size,
            "quality": args.quality,
            "prompt_count": 440,
            "attempt_rows": sum(1 for _ in attempts_path.open(encoding="utf-8")) - 1 if attempts_path.exists() else 0,
            "successful_generation_attempts": success_count,
            "failed_prompt_slots": failed_count,
            "images_generated": success_count,
            "formal_ingest_executed": False,
            "model_requests": sum(1 for row in rows if row["prompt_id"] in all_statuses),
            "val_requests": 0,
            "holdout_requests": 0,
            "updated_at": now(),
        }
        (P4D / "02_generation" / "generation_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"run_completed": completed, "run_failed": failed, **state}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if failed == 0 else 2
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # preserve a concise machine-readable failure
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        raise
