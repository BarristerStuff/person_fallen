#!/usr/bin/env python3
"""Execute one bounded official-tool phase for the frozen v3 Codex intake."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


OPT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
INGEST = DATASET / "tools/ingest_media.py"
GROUPS = OPT / "reports/person_fallen_v3_codex_media_groups.csv"
ITEMS = OPT / "reports/person_fallen_v3_codex_ingest_manifest.csv"
LABEL_MANIFEST = OPT / "reports/person_fallen_v3_codex_label_manifest.csv"
LEDGER = OPT / "reports/person_fallen_v3_codex_ingest_execution_ledger.jsonl"
LABEL_HEADER = [
    "media_id", "event_name", "event_label", "sample_role",
    "evidence_description", "reviewer", "review_status",
    "event_definition_version",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def append_ledger(phase: str, payload: dict[str, object]) -> None:
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        **payload,
    }
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def call(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, text=True, capture_output=True)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"official tool emitted non-JSON (exit={result.returncode}): {result.stderr}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"official tool failed: {data}")
    return data


def media_command(group: dict[str, str], dry_run: bool) -> list[str]:
    command = [
        sys.executable, str(INGEST), "add",
        "--input", group["staging_directory"],
        "--source-type", "ai_generated",
        "--input-type", "real_single_view",
        "--capture-batch", group["capture_batch"],
        "--scenario-id", group["scenario_id"],
        "--capture-date", "2026-09-02",
        "--location-or-source", "Codex P4D clean frozen generation lineage; item provenance retained in source reference manifest",
        "--staged-or-natural", "staged",
        "--source-reference", group["source_reference"],
        "--usage-allowed", "unknown",
        "--usage-scope", "development_only",
        "--is-original", "yes",
        "--quality-status", "pass",
        "--notes", group["notes"],
        "--recursive", "--json",
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def run_media(dry_run: bool) -> None:
    phase = "media_dry_run" if dry_run else "media_ingest"
    groups = read_csv(GROUPS)
    results: list[dict[str, object]] = []
    for group in groups:
        result = call(media_command(group, dry_run))
        expected = int(group["image_count"])
        if int(result.get("input_count", -1)) != expected:
            raise RuntimeError(f"{group['generation_group_id']}: input count mismatch: {result}")
        if int(result.get("new_media_count", -1)) != expected:
            raise RuntimeError(f"{group['generation_group_id']}: new media mismatch: {result}")
        if int(result.get("duplicate_reused_count", -1)) != 0:
            raise RuntimeError(f"{group['generation_group_id']}: unexpected duplicate: {result}")
        if result.get("warnings"):
            raise RuntimeError(f"{group['generation_group_id']}: warnings are not accepted: {result}")
        results.append({"generation_group_id": group["generation_group_id"], "result": result})
    append_ledger(phase, {
        "status": "PASS",
        "group_count": len(groups),
        "image_count": sum(int(group["image_count"]) for group in groups),
        "results": results,
    })
    print(json.dumps({"phase": phase, "status": "PASS", "groups": len(groups)}, ensure_ascii=False))


def build_label_manifest() -> None:
    items = read_csv(ITEMS)
    media = read_csv(DATASET / "01_annotations/media.csv")
    by_sha: dict[str, list[dict[str, str]]] = {}
    for row in media:
        by_sha.setdefault(row["sha256"], []).append(row)
    rows: list[dict[str, str]] = []
    for item in items:
        matches = by_sha.get(item["source_image_sha256"], [])
        if len(matches) != 1:
            raise RuntimeError(f"expected one dataset media SHA match for {item['prompt_id']}, found {len(matches)}")
        evidence = (
            "GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT; "
            "HUMAN_SEMANTIC_REVIEW_REQUIRED=false; "
            f"prompt_id={item['prompt_id']}; taxonomy={item['taxonomy']}; "
            f"generation_group_id={item['generation_group_id']}; "
            f"generation_revision={item['generation_revision']}; "
            f"planned_split={item['v3_split']}; source_image_sha256={item['source_image_sha256']}; "
            f"source_image_path={item['source_image_path']}; "
            f"frozen_remap={item['frozen_remap_source']}"
        )
        rows.append({
            "media_id": matches[0]["media_id"],
            "event_name": "person_fallen",
            "event_label": item["event_label"],
            "sample_role": item["sample_role"],
            "evidence_description": evidence,
            "reviewer": "",
            "review_status": "unreviewed",
            "event_definition_version": "v3.0",
        })
    if len(rows) != 202 or len({row["media_id"] for row in rows}) != 202:
        raise RuntimeError("label manifest does not contain 202 unique new media IDs")
    with LABEL_MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    sha = hashlib.sha256(LABEL_MANIFEST.read_bytes()).hexdigest()
    append_ledger("build_label_manifest", {
        "status": "PASS", "label_count": len(rows), "manifest": str(LABEL_MANIFEST), "sha256": sha,
    })
    print(json.dumps({"phase": "build_label_manifest", "status": "PASS", "labels": len(rows), "sha256": sha}))


def run_labels(dry_run: bool) -> None:
    phase = "label_dry_run" if dry_run else "label_ingest"
    command = [sys.executable, str(INGEST), "add-label-manifest", "--input", str(LABEL_MANIFEST), "--json"]
    if dry_run:
        command.append("--dry-run")
    result = call(command)
    if int(result.get("input_count", -1)) != 202:
        raise RuntimeError(f"label manifest input count mismatch: {result}")
    if int(result.get("new_label_count", -1)) != 202:
        raise RuntimeError(f"label manifest new count mismatch: {result}")
    if int(result.get("already_exists_count", -1)) != 0:
        raise RuntimeError(f"label manifest unexpected existing label: {result}")
    if result.get("warnings"):
        raise RuntimeError(f"label manifest warnings are not accepted: {result}")
    append_ledger(phase, {"status": "PASS", "result": result})
    print(json.dumps({"phase": phase, "status": "PASS", "labels": 202}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["media-dry-run", "media-ingest", "build-label-manifest", "label-dry-run", "label-ingest"])
    args = parser.parse_args()
    if args.phase == "media-dry-run":
        run_media(True)
    elif args.phase == "media-ingest":
        run_media(False)
    elif args.phase == "build-label-manifest":
        build_label_manifest()
    elif args.phase == "label-dry-run":
        run_labels(True)
    else:
        run_labels(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
