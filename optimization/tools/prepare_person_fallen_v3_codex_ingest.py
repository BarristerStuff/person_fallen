#!/usr/bin/env python3
"""Build immutable, SHA-verified inputs for person_fallen v3 Codex intake."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


OPT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
AUDIT = OPT / "reports/person_fallen_codex_ingest_audit.csv"
OUT = OPT / "reports/person_fallen_v3_codex_ingest_manifest.csv"
GROUPS = OPT / "reports/person_fallen_v3_codex_media_groups.csv"
PREFLIGHT = OPT / "reports/person_fallen_v3_codex_ingest_preflight.json"
STAGING = OPT / "intake_staging/person_fallen_v3_codex_clean"
CAPTURE_BATCH = "20260902_person_fallen_v3_codex_clean"
SOURCE_REFERENCE = str(OUT)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_image(path: Path) -> None:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    source_rows = [
        row
        for row in read_csv(AUDIT)
        if row["disposition"] == "PENDING_V3_VERSION_GATE"
    ]
    if len(source_rows) != 202:
        raise RuntimeError(f"expected exactly 202 clean rows, found {len(source_rows)}")
    if len({row["source_image_sha256"] for row in source_rows}) != 202:
        raise RuntimeError("clean intake source contains exact SHA256 duplicates")
    output: list[dict[str, str]] = []
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        source = Path(row["source_image_path"])
        if not source.is_file():
            raise RuntimeError(f"missing source image: {source}")
        actual = digest(source)
        if actual != row["source_image_sha256"]:
            raise RuntimeError(f"SHA256 mismatch for {source}")
        verify_image(source)
        if not (
            row["clean_manifest_bound"] == "true"
            and row["remap_sha_binding_count"] == "1"
            and row["source_provenance_status"]
            == "P4D_FAST_CLOSE_PROVENANCE_MECHANICAL_LINEAGE_PASS"
        ):
            raise RuntimeError(f"frozen clean/remap/provenance binding failed: {row['prompt_id']}")
        record = {
            "prompt_id": row["prompt_id"],
            "generation_group_id": row["group_id"],
            "taxonomy": row["taxonomy"],
            "v3_split": row["v3_split"],
            "event_name": "person_fallen",
            "event_definition_version": "v3.0",
            "gt_type": "PROMPT_DERIVED_SYNTHETIC_GT",
            "human_semantic_review_required": "false",
            "event_label": row["ingest_event_label"],
            "sample_role": row["ingest_sample_role"],
            "source_image_path": str(source),
            "source_image_sha256": actual,
            "capture_batch": CAPTURE_BATCH,
            "source_type": "ai_generated",
            "input_type": "real_single_view",
            "usage_scope": "development_only",
            "source_reference": SOURCE_REFERENCE,
            "generation_provider": "codex",
            "generation_runtime": "CODEX_SAFE_STAGED_CV_V1",
            "generation_revision": "P4D_FAST_CLOSE_CLEAN_LINEAGE_20260901",
            "frozen_remap_source": "/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_remap_manifest.csv",
        }
        output.append(record)
        groups[record["generation_group_id"]].append(record)
    output.sort(key=lambda row: row["prompt_id"])
    role_counts = Counter(row["sample_role"] for row in output)
    if role_counts != Counter({"positive": 61, "hard_negative": 121, "negative": 20}):
        raise RuntimeError(f"unexpected frozen v3 role counts: {dict(role_counts)}")

    group_rows: list[dict[str, str]] = []
    for group_id, rows in sorted(groups.items()):
        shared_fields = ["taxonomy", "v3_split", "event_label", "sample_role"]
        for field in shared_fields:
            if len({row[field] for row in rows}) != 1:
                raise RuntimeError(f"group {group_id} is not homogeneous for {field}")
        stage_dir = STAGING / group_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        for row in rows:
            stage_file = stage_dir / Path(row["source_image_path"]).name
            source = Path(row["source_image_path"])
            if stage_file.exists():
                if digest(stage_file) != row["source_image_sha256"]:
                    raise RuntimeError(f"staging path collision with different bytes: {stage_file}")
            else:
                os.link(source, stage_file)
            row["staging_path"] = str(stage_file)
        exemplar = rows[0]
        notes = (
            "person_fallen v3.0; GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT; "
            "HUMAN_SEMANTIC_REVIEW_REQUIRED=false; provider=codex; "
            "runtime=CODEX_SAFE_STAGED_CV_V1; "
            f"generation_revision={exemplar['generation_revision']}; "
            f"generation_group_id={group_id}; taxonomy={exemplar['taxonomy']}; "
            f"planned_split={exemplar['v3_split']}; "
            f"item_provenance_manifest={OUT}"
        )
        group_rows.append(
            {
                "generation_group_id": group_id,
                "staging_directory": str(stage_dir),
                "image_count": str(len(rows)),
                "taxonomy": exemplar["taxonomy"],
                "v3_split": exemplar["v3_split"],
                "event_label": exemplar["event_label"],
                "sample_role": exemplar["sample_role"],
                "capture_batch": CAPTURE_BATCH,
                "scenario_id": group_id,
                "source_reference": SOURCE_REFERENCE,
                "notes": notes,
            }
        )
    write_csv(OUT, output)
    write_csv(GROUPS, group_rows)
    PREFLIGHT.write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "PASS",
                "clean_rows": len(output),
                "unique_sha256": len({row["source_image_sha256"] for row in output}),
                "role_counts": dict(sorted(role_counts.items())),
                "group_count": len(group_rows),
                "v3_split_counts": dict(sorted(Counter(row["v3_split"] for row in output).items())),
                "source_audit": str(AUDIT),
                "manifest": str(OUT),
                "group_manifest": str(GROUPS),
                "staging_root": str(STAGING),
                "q9_included": False,
                "model_prediction_used_as_gt": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    print(PREFLIGHT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
