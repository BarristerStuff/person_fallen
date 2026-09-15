#!/usr/bin/env python3
"""Write the final, read-only validation report for the Codex v3 ingest."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path


DATASET_ROOT = Path("/home/yanbo/net_vlm_xunjian_dataset")
OPTIMIZATION_ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
MANIFEST_PATH = OPTIMIZATION_ROOT / "reports/person_fallen_v3_codex_ingest_manifest.csv"
REPORT_PATH = OPTIMIZATION_ROOT / "reports/person_fallen_v3_codex_final_validate.json"
Q9_FINAL = (
    OPTIMIZATION_ROOT
    / "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/"
    "06_execution/quota_campaign_window_06_gr3q9_authorized_20260831_02/08_final"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def count_broken_links(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_symlink() and not path.exists())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    validator = subprocess.run(
        [sys.executable, str(DATASET_ROOT / "tools/validate_dataset.py"), "--json"],
        cwd=DATASET_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        validation = json.loads(validator.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"validator did not return JSON: {exc}: {validator.stdout!r}")

    media_rows = read_csv(DATASET_ROOT / "01_annotations/media.csv")
    label_rows = read_csv(DATASET_ROOT / "01_annotations/labels.csv")
    manifest_rows = read_csv(MANIFEST_PATH)
    media_by_id = {row["media_id"]: row for row in media_rows}
    manifest_by_sha = {row["source_image_sha256"]: row for row in manifest_rows}

    pf_labels = [row for row in label_rows if row["event_name"] == "person_fallen"]
    pf_v2 = [row for row in pf_labels if row["event_definition_version"] == "v2.0"]
    pf_v3 = [row for row in pf_labels if row["event_definition_version"] == "v3.0"]
    v3_roles = Counter(row["sample_role"] for row in pf_v3)
    v3_media_ids = {row["media_id"] for row in pf_v3}
    v3_provenance_errors: list[str] = []
    for label in pf_v3:
        media = media_by_id.get(label["media_id"])
        if media is None:
            v3_provenance_errors.append(f"missing media for {label['media_id']}")
            continue
        manifest = manifest_by_sha.get(media["sha256"])
        if manifest is None:
            v3_provenance_errors.append(f"unmanifested sha for {label['media_id']}")
            continue
        if label["sample_role"] != manifest["sample_role"]:
            v3_provenance_errors.append(f"role mismatch for {label['media_id']}")
        if label["event_label"] != manifest["event_label"]:
            v3_provenance_errors.append(f"label mismatch for {label['media_id']}")
        for token in (
            "GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT",
            "HUMAN_SEMANTIC_REVIEW_REQUIRED=false",
            "prompt_id=",
            "taxonomy=",
            "generation_revision=",
            "planned_split=",
            "source_image_sha256=",
        ):
            if token not in label["evidence_description"]:
                v3_provenance_errors.append(f"{label['media_id']}: missing {token}")
        if media["source_type"] != "ai_generated":
            v3_provenance_errors.append(f"{label['media_id']}: source_type not ai_generated")
        media_path = DATASET_ROOT / media["relative_path"]
        if not media_path.is_file() or sha256(media_path) != media["sha256"]:
            v3_provenance_errors.append(f"{label['media_id']}: media missing or hash mismatch")

    sha_counts = Counter(row["sha256"] for row in media_rows)
    duplicate_media = sum(count - 1 for count in sha_counts.values() if count > 1)
    pair_counts = Counter((row["media_id"], row["event_name"]) for row in label_rows)
    label_conflicts = sum(count - 1 for count in pair_counts.values() if count > 1)

    pf_review_root = DATASET_ROOT / "02_review_by_event/person_fallen"
    pf_links = [path for path in pf_review_root.rglob("*") if path.is_symlink()]
    pf_broken = [path for path in pf_links if not path.exists()]
    review_roles = Counter(path.parent.name for path in pf_links)
    q9_final_files = [path for path in Q9_FINAL.glob("*") if path.is_file()]

    errors: list[str] = []
    if validation.get("status") != "valid" or validation.get("error_count") != 0:
        errors.append("dataset validator did not pass")
    if len(pf_v2) != 500:
        errors.append(f"expected 500 v2 labels, found {len(pf_v2)}")
    if len(pf_v3) != 202 or len(v3_media_ids) != 202:
        errors.append(f"expected 202 v3 labels/media, found {len(pf_v3)}/{len(v3_media_ids)}")
    if dict(v3_roles) != {"positive": 61, "negative": 20, "hard_negative": 121}:
        errors.append(f"unexpected v3 roles: {dict(v3_roles)}")
    if len(manifest_rows) != 202 or len(manifest_by_sha) != 202:
        errors.append("manifest is not 202 unique SHA rows")
    if v3_provenance_errors:
        errors.extend(v3_provenance_errors)
    if duplicate_media or label_conflicts:
        errors.append("duplicate media or label conflict found")
    if len(pf_links) != 702 or pf_broken:
        errors.append(f"person_fallen review links={len(pf_links)} broken={len(pf_broken)}")
    if review_roles != Counter({"positive": 261, "negative": 120, "hard_negative": 301, "uncertain": 20}):
        errors.append(f"unexpected person_fallen review roles: {dict(review_roles)}")

    report = {
        "validation": {
            "status": validation.get("status"),
            "error_count": validation.get("error_count"),
            "full_hash_check": validation.get("full_hash_check"),
            "media_count": validation.get("media_count"),
            "label_count": validation.get("label_count"),
            "warning_count": validation.get("warning_count"),
        },
        "person_fallen": {
            "labels_total": len(pf_labels),
            "v2_rows": len(pf_v2),
            "v3_rows": len(pf_v3),
            "v3_role_counts": dict(v3_roles),
            "v3_unique_media_ids": len(v3_media_ids),
            "v3_provenance_errors": v3_provenance_errors,
        },
        "integrity": {
            "duplicate_media": duplicate_media,
            "label_conflicts": label_conflicts,
            "broken_links_global": count_broken_links(DATASET_ROOT / "02_review_by_event"),
            "review_person_fallen_link_count": len(pf_links),
            "review_person_fallen_role_counts": dict(review_roles),
            "broken_person_fallen_links": len(pf_broken),
        },
        "ingest": {
            "clean_manifest_rows": len(manifest_rows),
            "clean_manifest_unique_sha256": len(manifest_by_sha),
            "q9_binding_blocked_not_ingested": 30,
            "q9_physical_final_files_available": len(q9_final_files),
        },
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
