#!/usr/bin/env python3
"""Read-only SHA/provenance audit for the person_fallen Codex P4D intake.

This produces reports in the optimization workspace only.  It never accesses a
Holdout media file, changes the shared dataset, sends a provider request, or
uses a model prediction as ground truth.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


OPT_ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
DATASET_ROOT = Path("/home/yanbo/net_vlm_xunjian_dataset")
FAST_CLOSE = OPT_ROOT / "10_fast_close" / "fast_close_clean_manifest.csv"
V3_REMAP = (
    OPT_ROOT
    / "11_person_fallen_v3_revision"
    / "remap"
    / "person_fallen_v3_remap_manifest.csv"
)
OUT_CSV = OPT_ROOT / "reports" / "person_fallen_codex_ingest_audit.csv"
OUT_MD = OPT_ROOT / "reports" / "person_fallen_codex_ingest_audit.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_ok(path: Path) -> tuple[bool, str]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
        return True, ""
    except Exception as exc:  # report a path-scoped diagnostic, never repair it
        return False, f"{type(exc).__name__}: {exc}"


def role_for_remap(row: dict[str, str]) -> tuple[str, str]:
    label = row["new_label"]
    stratum = row["metric_stratum"]
    if label == "positive":
        return "1", "positive"
    if label == "negative" and stratum == "hard_negative":
        return "0", "hard_negative"
    if label == "negative":
        return "0", "negative"
    if label == "uncertain":
        return "uncertain", "uncertain"
    raise ValueError(f"unsupported frozen remap label/stratum: {label}/{stratum}")


def main() -> int:
    clean = read_csv(FAST_CLOSE)
    remap = read_csv(V3_REMAP)
    media = read_csv(DATASET_ROOT / "01_annotations" / "media.csv")
    labels = read_csv(DATASET_ROOT / "01_annotations" / "labels.csv")

    p4d = [row for row in remap if row["source_family"] == "P4D_FROZEN_PLAN_440"]
    original = [row for row in remap if row["source_family"] == "V2_ORIGINAL_SYNTHETIC_500"]
    clean_by_sha = {row["final_sha256_actual"]: row for row in clean}
    if len(clean_by_sha) != len(clean):
        raise RuntimeError("fast-close clean manifest contains duplicate final SHA256")
    remap_by_sha: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in p4d:
        remap_by_sha[row["source_image_sha256_actual"]].append(row)
    media_by_sha: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in media:
        media_by_sha[row["sha256"]].append(row)
    labels_by_media: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in labels:
        labels_by_media[row["media_id"]].append(row)

    output: list[dict[str, str]] = []
    clean_sha_set = set(clean_by_sha)
    source_on_disk: dict[str, dict[str, bool]] = {}
    all_source_rows = original + [row for row in p4d if row["source_asset_status"] == "REUSABLE_P4D_CLEAN_FAST_CLOSE"]
    for row in all_source_rows:
        expected = row["source_image_sha256_actual"]
        if expected in source_on_disk:
            continue
        path = Path(row["source_image_path"])
        exists = path.is_file()
        actual = sha256(path) if exists else ""
        pillow_ok, pillow_error = image_ok(path) if exists else (False, "missing")
        source_on_disk[expected] = {
            "exists": exists,
            "sha_ok": exists and actual == expected,
            "pillow_ok": pillow_ok,
            "pillow_error": pillow_error,
        }

    for row in p4d:
        expected = row["source_image_sha256_actual"]
        path = Path(row["source_image_path"])
        status = row["source_asset_status"]
        clean_row = clean_by_sha.get(expected)
        disk = source_on_disk.get(expected)
        if disk is None:
            exists = path.is_file()
            actual = sha256(path) if exists else ""
            pillow_ok, pillow_error = image_ok(path) if exists else (False, "missing")
            disk = {
                "exists": exists,
                "sha_ok": exists and actual == expected,
                "pillow_ok": pillow_ok,
                "pillow_error": pillow_error,
            }
        existing_media = media_by_sha.get(expected, [])
        existing_pf_labels = [
            label
            for item in existing_media
            for label in labels_by_media[item["media_id"]]
            if label["event_name"] == "person_fallen"
        ]
        try:
            event_label, sample_role = role_for_remap(row)
        except ValueError:
            event_label, sample_role = "", ""
        clean_binding_ok = (
            clean_row is not None
            and len(remap_by_sha[expected]) == 1
            and clean_row["provenance_status"] == "PASS"
            and clean_row["prompt_lineage_status"] == "PASS"
            and clean_row["sha_integrity_status"] == "PASS"
            and clean_row["mechanical_status"] == "PASS"
            and disk["exists"]
            and disk["sha_ok"]
            and disk["pillow_ok"]
        )
        if status == "Q9_BINDING_BLOCKED":
            disposition = "EXCLUDED_BINDING_BLOCKED"
        elif status == "COMPLETION_UNKNOWN_QUARANTINED":
            disposition = "EXCLUDED_COMPLETION_UNKNOWN"
        elif status == "FAILED_CONFIRMED":
            disposition = "EXCLUDED_FAILED_CONFIRMED"
        elif status == "NOT_STARTED":
            disposition = "EXCLUDED_NOT_STARTED"
        elif status != "REUSABLE_P4D_CLEAN_FAST_CLOSE":
            disposition = "EXCLUDED_NOT_CLEAN_LINEAGE"
        elif not clean_binding_ok:
            disposition = "EXCLUDED_INVALID_OR_UNBOUND"
        elif existing_pf_labels:
            disposition = "ALREADY_INGESTED_PERSON_FALLEN"
        elif existing_media:
            disposition = "PENDING_REUSE_EXISTING_MEDIA_ADD_LABEL"
        else:
            disposition = "PENDING_V3_VERSION_GATE"
        output.append(
            {
                "prompt_id": row["prompt_id"],
                "group_id": row["group_id"],
                "taxonomy": row["taxonomy"],
                "v3_split": row["v3_split"],
                "frozen_gt": row["new_label"],
                "frozen_metric_stratum": row["metric_stratum"],
                "ingest_event_label": event_label,
                "ingest_sample_role": sample_role,
                "source_asset_status": status,
                "source_provenance_status": row["source_provenance_status"],
                "source_image_path": row["source_image_path"],
                "source_image_sha256": expected,
                "file_exists": str(disk["exists"]).lower(),
                "sha256_matches_frozen": str(disk["sha_ok"]).lower(),
                "pillow_ok": str(disk["pillow_ok"]).lower(),
                "pillow_error": disk["pillow_error"],
                "clean_manifest_bound": str(clean_row is not None).lower(),
                "remap_sha_binding_count": str(len(remap_by_sha[expected])),
                "dataset_matching_media_ids": ";".join(item["media_id"] for item in existing_media),
                "dataset_person_fallen_label_versions": ";".join(sorted({label["event_definition_version"] for label in existing_pf_labels})),
                "disposition": disposition,
            }
        )

    output.sort(key=lambda row: row["prompt_id"])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)

    counts = Counter(row["disposition"] for row in output)
    original_disk = Counter(
        "valid" if item["exists"] and item["sha_ok"] and item["pillow_ok"] else "invalid"
        for expected, item in source_on_disk.items()
        if expected not in clean_sha_set
    )
    clean_disk = Counter(
        "valid" if item["exists"] and item["sha_ok"] and item["pillow_ok"] else "invalid"
        for expected, item in source_on_disk.items()
        if expected in clean_sha_set
    )
    formal = [row for row in remap if row["formal_v3_evaluation"] == "true"]
    pf_labels = [row for row in labels if row["event_name"] == "person_fallen"]
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_v3": dict(sorted(Counter(row["v3_split"] for row in formal).items())),
        "formal_v3_total": len(formal),
        "v2_original_files_on_disk_valid": original_disk["valid"],
        "clean_files_on_disk_valid": clean_disk["valid"],
        "person_fallen_images_on_disk": original_disk["valid"] + clean_disk["valid"],
        "codex_generated_success_ledger": counts["PENDING_V3_VERSION_GATE"] + counts["ALREADY_INGESTED_PERSON_FALLEN"] + counts["PENDING_REUSE_EXISTING_MEDIA_ADD_LABEL"] + sum(1 for row in output if row["disposition"] == "EXCLUDED_BINDING_BLOCKED"),
        "codex_clean_success": sum(1 for row in output if row["clean_manifest_bound"] == "true"),
        "codex_binding_blocked_excluded": counts["EXCLUDED_BINDING_BLOCKED"],
        "completion_unknown": counts["EXCLUDED_COMPLETION_UNKNOWN"],
        "failed_confirmed": counts["EXCLUDED_FAILED_CONFIRMED"],
        "not_started": counts["EXCLUDED_NOT_STARTED"],
        "other_not_clean_lineage": counts["EXCLUDED_NOT_CLEAN_LINEAGE"],
        "dataset_before": {
            "media_count": len(media),
            "label_count": len(labels),
            "person_fallen_media_count": len({row["media_id"] for row in pf_labels}),
            "person_fallen_label_count": len(pf_labels),
            "person_fallen_roles": dict(sorted(Counter(row["sample_role"] for row in pf_labels).items())),
            "person_fallen_versions": dict(sorted(Counter(row["event_definition_version"] for row in pf_labels).items())),
        },
        "clean_dispositions": dict(sorted(counts.items())),
        "version_gate": {
            "requested_new_label_version": "v3.0",
            "current_validator_person_fallen_version": "v2.0",
            "official_add_label_can_emit_requested_v3": False,
            "safe_formal_ingest_performed": False,
            "reason": "Current official add-label derives person_fallen event_definition_version from validator.EVENT_DEFINITION_VERSIONS, which is v2.0; a v3.0 row would be rejected by current validation.",
        },
    }
    md = [
        "# person_fallen Codex ingest audit",
        "",
        "This is a SHA- and frozen-remap-derived inventory. No unified-dataset write, provider request, Holdout access, model inference, or production-project change was performed.",
        "",
        "## Formal v3 remap", "",
        f"- V3_DEV={summary['formal_v3'].get('V3_DEV', 0)}; V3_SCREEN={summary['formal_v3'].get('V3_SCREEN', 0)}; V3_VAL={summary['formal_v3'].get('V3_VAL', 0)}; total={summary['formal_v3_total']}.",
        f"- Existing V2 source images valid on disk: {summary['v2_original_files_on_disk_valid']}.",
        f"- Clean Codex P4D images valid on disk: {summary['clean_files_on_disk_valid']}.",
        f"- person_fallen images on disk (V2 original + clean P4D): {summary['person_fallen_images_on_disk']}.",
        "",
        "## P4D disposition", "",
        f"- Codex ledger successes: {summary['codex_generated_success_ledger']} (clean={summary['codex_clean_success']}, binding-blocked={summary['codex_binding_blocked_excluded']}).",
        f"- completion-unknown={summary['completion_unknown']}; failed-confirmed={summary['failed_confirmed']}; terminal not-started={summary['not_started']}; other unexecuted/not-clean={summary['other_not_clean_lineage']}.",
        f"- Clean already in unified dataset by SHA: {counts['ALREADY_INGESTED_PERSON_FALLEN']}; clean pending as new media: {counts['PENDING_V3_VERSION_GATE']}; clean pending reuse existing media: {counts['PENDING_REUSE_EXISTING_MEDIA_ADD_LABEL']}.",
        "",
        "## Current formal-ingest gate", "",
        "**BLOCKED — no mutation performed.** The requested new labels must be `event_definition_version=v3.0`, but the current official `ingest_media.py add-label` derives `person_fallen` as `v2.0`, and `validate_dataset.py` rejects any other version. Writing via that command would silently create v2.0 labels; hand-writing v3.0 would fail validation. A separately authorized versioned-dataset-tool change is required before the official dry-run and ingest can proceed.",
        "",
        "## Evidence", "",
        f"- Detailed row audit: `{OUT_CSV}`",
        f"- Frozen clean manifest: `{FAST_CLOSE}`",
        f"- Frozen v3 remap: `{V3_REMAP}`",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
