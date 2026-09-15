#!/usr/bin/env python3
"""Freeze the P4D group lineage and internal split before any image generation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")


SPECS = [
    ("hard_negative", "negative", "floor_sitting", "HN_SIT", 60, 12),
    ("hard_negative", "negative", "kneeling_half_kneeling", "HN_KNEEL", 60, 12),
    ("hard_negative", "negative", "pushup_plank", "HN_PLANK", 50, 10),
    ("hard_negative", "negative", "crawling_quadruped_support", "HN_CRAWL", 40, 8),
    ("hard_negative", "negative", "ground_maintenance", "HN_MAINT", 40, 8),
    ("hard_negative", "negative", "squat_crouch_deep_bend", "HN_SQUAT", 30, 6),
    ("hard_negative", "negative", "mixed_hard_negative", "HN_MIX", 20, 4),
    ("positive", "positive", "supine_ground_lying", "POS_SUPINE", 20, 4),
    ("positive", "positive", "prone_ground_lying", "POS_PRONE", 20, 4),
    ("positive", "positive", "side_lying", "POS_SIDE", 20, 4),
    ("positive", "positive", "curled_or_partially_occluded_lying", "POS_CURLED", 15, 3),
    ("positive", "positive", "intentional_ground_lying", "POS_INTENTIONAL", 10, 2),
    ("positive", "positive", "multi_person_one_lying", "POS_MULTI", 10, 2),
    ("positive", "positive", "horizontal_corridor_ground_lying", "POS_CORRIDOR", 5, 1),
    ("ordinary_negative", "negative", "standing_walking", "NEG_STAND", 20, 4),
    ("ordinary_negative", "negative", "chair_seated_normal_work", "NEG_CHAIR", 20, 4),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_groups() -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for target_role, target_label, taxonomy, prefix, image_count, group_count in SPECS:
        if image_count != group_count * 5:
            raise ValueError(f"{taxonomy}: image/group ratio is not five")
        design_count = round(group_count * 0.6)
        # The fixed quotas in the brief override rounding for this exact plan.
        if taxonomy == "floor_sitting":
            design_count = 7
        elif taxonomy == "kneeling_half_kneeling":
            design_count = 7
        elif taxonomy == "pushup_plank":
            design_count = 6
        elif taxonomy == "crawling_quadruped_support":
            design_count = 5
        elif taxonomy == "ground_maintenance":
            design_count = 5
        elif taxonomy == "squat_crouch_deep_bend":
            design_count = 4
        elif taxonomy == "mixed_hard_negative":
            design_count = 2
        elif taxonomy in {"supine_ground_lying", "prone_ground_lying", "side_lying"}:
            # Twelve positive groups are allocated to DESIGN while retaining
            # at least one SCREEN group for every positive taxonomy except the
            # single corridor group, which is deliberately SCREEN-only.
            design_count = {"supine_ground_lying": 3, "prone_ground_lying": 3, "side_lying": 2}[taxonomy]
        elif taxonomy == "curled_or_partially_occluded_lying":
            design_count = 2
        elif taxonomy in {"intentional_ground_lying", "multi_person_one_lying", "horizontal_corridor_ground_lying"}:
            design_count = {"intentional_ground_lying": 1, "multi_person_one_lying": 1, "horizontal_corridor_ground_lying": 0}[taxonomy]
        elif taxonomy in {"standing_walking", "chair_seated_normal_work"}:
            design_count = 2 if taxonomy == "standing_walking" else 3
        else:
            raise AssertionError(taxonomy)
        for index in range(1, group_count + 1):
            group_id = f"PF_P4D_{prefix}_G{index:03d}"
            groups.append(
                {
                    "group_id": group_id,
                    "prompt_family_id": group_id,
                    "target_role": target_role,
                    "target_event_label": target_label,
                    "taxonomy": taxonomy,
                    "group_variant_count": 5,
                    "taxonomy_group_index": index,
                    "taxonomy_group_count": group_count,
                    "planned_internal_split": "NEW_DESIGN" if index <= design_count else "NEW_SCREEN",
                    "planned_image_count": 5,
                    "generation_batch": "batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m",
                    "source_type": "ai_generated",
                    "usage_scope": "development_only",
                    "new_text_to_image_lineage": "true",
                }
            )
    return groups


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=P4D / "01_prompt_plan")
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    groups = build_groups()
    if len(groups) != 88 or sum(int(row["planned_image_count"]) for row in groups) != 440:
        raise RuntimeError("group plan cardinality mismatch")
    design_groups = [row for row in groups if row["planned_internal_split"] == "NEW_DESIGN"]
    screen_groups = [row for row in groups if row["planned_internal_split"] == "NEW_SCREEN"]
    if len(design_groups) != 53 or len(screen_groups) != 35:
        raise RuntimeError(f"unexpected split group counts: {len(design_groups)}, {len(screen_groups)}")
    if {row["group_id"] for row in design_groups} & {row["group_id"] for row in screen_groups}:
        raise RuntimeError("cross-split group leakage")

    fields = [
        "group_id", "prompt_family_id", "target_role", "target_event_label", "taxonomy",
        "group_variant_count", "taxonomy_group_index", "taxonomy_group_count",
        "planned_internal_split", "planned_image_count", "generation_batch",
        "source_type", "usage_scope", "new_text_to_image_lineage",
    ]
    group_csv = out / "group_manifest.csv"
    write_csv(group_csv, groups, fields)
    split_counts = {
        "NEW_DESIGN": {
            "groups": len(design_groups),
            "images": sum(int(row["planned_image_count"]) for row in design_groups),
        },
        "NEW_SCREEN": {
            "groups": len(screen_groups),
            "images": sum(int(row["planned_image_count"]) for row in screen_groups),
        },
    }
    taxonomy_counts: dict[str, dict[str, int]] = {}
    for row in groups:
        taxonomy = str(row["taxonomy"])
        bucket = taxonomy_counts.setdefault(taxonomy, {"groups": 0, "images": 0, "NEW_DESIGN_groups": 0, "NEW_DESIGN_images": 0, "NEW_SCREEN_groups": 0, "NEW_SCREEN_images": 0})
        split = str(row["planned_internal_split"])
        bucket["groups"] += 1
        bucket["images"] += int(row["planned_image_count"])
        bucket[f"{split}_groups"] += 1
        bucket[f"{split}_images"] += int(row["planned_image_count"])
    freeze = {
        "stage": "P4D_NEW_HARD_NEGATIVE_DEV_REVISION",
        "freeze_type": "pre_generation_group_split_freeze",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generation_batch": "batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m",
        "new_text_to_image_lineage": True,
        "group_count": len(groups),
        "images_planned": 440,
        "cross_split_group_count": 0,
        "split_counts": split_counts,
        "taxonomy_counts": taxonomy_counts,
        "design_screen_decided_before_generation": True,
        "c3_or_vlm_used_before_freeze": False,
        "old_batch_path": "/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m",
        "new_batch_path": str(BATCH),
        "formal_dataset_mutation": False,
        "val_requests": 0,
        "holdout_requests": 0,
        "group_manifest_sha256": sha256_file(group_csv),
    }
    freeze_json = out / "group_split_freeze.json"
    freeze_json.write_text(json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "group_manifest.sha256").write_text(f"{sha256_file(group_csv)}  {group_csv.name}\n", encoding="utf-8")
    (out / "group_split_freeze.sha256").write_text(f"{sha256_file(freeze_json)}  {freeze_json.name}\n", encoding="utf-8")
    readme = [
        "# P4D pre-generation group split freeze",
        "",
        "This manifest was written before any P4D image generation. Each group is a five-image prompt-lineage family.",
        "",
        f"- Groups: {len(groups)} (NEW_DESIGN={len(design_groups)}, NEW_SCREEN={len(screen_groups)})",
        f"- Images: {split_counts['NEW_DESIGN']['images']} DESIGN + {split_counts['NEW_SCREEN']['images']} SCREEN = 440",
        "- Cross-split group count: 0",
        "- C3/VLM used before freeze: false",
        "- Old batch is read-only; new batch has a dedicated path.",
    ]
    (out / "group_split_freeze.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(json.dumps({"group_count": len(groups), "design": split_counts["NEW_DESIGN"], "screen": split_counts["NEW_SCREEN"], "cross_split_group_count": 0, "group_manifest_sha256": freeze["group_manifest_sha256"], "freeze_sha256": sha256_file(freeze_json)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
