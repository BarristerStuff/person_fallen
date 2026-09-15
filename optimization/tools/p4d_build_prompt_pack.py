#!/usr/bin/env python3
"""Build 440 complete, new-lineage P4D prompts from the pre-frozen group plan."""

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
OLD_BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m")

SCENES = [
    ("factory corridor", "a broad factory corridor with safety rails, distant machinery, and a clean industrial floor"),
    ("industrial aisle", "a long industrial aisle between storage racks and workstations"),
    ("warehouse passage", "a warehouse passage with pallets, shelving, and clear floor markings"),
    ("office corridor", "an office corridor with glass partitions, doors, and practical overhead lights"),
    ("public lobby", "a public lobby with reception furniture, columns, and a durable tiled floor"),
    ("parking garage", "an indoor parking garage with concrete pillars, parked vehicles, and lane markings"),
    ("service hallway", "a narrow service hallway with utility doors, pipes, and a non-glossy floor"),
    ("loading area", "a covered loading area with dock equipment, carts, and a wide concrete surface"),
    ("campus paved walkway", "a paved campus walkway beside a building with benches and planted edges"),
    ("building entrance", "a building entrance with vestibule doors, matting, and visible architectural depth"),
    ("utility room passage", "a utility-room passage with cabinets, conduits, and inspection access panels"),
    ("large indoor public area", "a large indoor public area with varied furniture, open sightlines, and realistic foot traffic cues"),
]
LIGHTING = [
    "neutral indoor illumination",
    "cool industrial ceiling light",
    "warm practical interior light",
    "slightly dim but readable ambient light",
    "soft mixed light from fixtures and daylight spill",
    "partial shadow from nearby structure with clear subject detail",
    "moderate backlight balanced by usable foreground fill",
]
ANGLES = ["front-oblique", "left-oblique", "right-oblique", "moderate side", "slightly distant oblique", "near-medium oblique", "rear-oblique", "off-axis corridor view"]
DISTANCES = ["medium distance", "near-medium distance", "slightly distant framing", "moderate camera distance", "medium-wide framing", "closer inspection distance"]
PEOPLE = [
    "a middle-aged woman with a sturdy build wearing dark work trousers and a muted green jacket",
    "a young adult man with a slim build wearing a navy polo shirt and khaki trousers",
    "an older adult man with a stocky build wearing a charcoal cardigan and practical shoes",
    "a young adult woman with an athletic build wearing a pale sweater and black trousers",
    "a tall adult with a broad build wearing a reflective work vest over neutral clothing",
    "a shorter adult with a compact build wearing a blue hoodie and gray trousers",
    "a middle-aged adult with a medium build wearing a tan utility jacket and dark jeans",
    "an adult with a curvy build wearing a burgundy coat and straight-leg trousers",
    "a young adult with a medium build wearing a light work shirt and dark cargo trousers",
    "an older adult woman with a small build wearing a beige coat and comfortable shoes",
]
CLOTHING = [
    "subdued gray and olive clothing",
    "blue and charcoal clothing",
    "brown and cream clothing",
    "black and teal clothing",
    "muted orange workwear accents",
    "dark red and denim clothing",
    "light neutral clothing",
    "purple and gray casual clothing",
]
FLOORS = ["matte concrete", "industrial vinyl", "large neutral tiles", "rubberized safety flooring", "painted loading-bay concrete", "dull stone flooring"]
MINOR_LAYOUTS = [
    "with a cart near one edge and ample negative space around the subject",
    "with a few tools and boxes placed naturally in the background",
    "with a doorway and structural lines creating depth without blocking the subject",
    "with subtle floor reflections and realistic perspective lines",
    "with a safety rail and a distant worker-shaped silhouette that is not the subject",
    "with practical clutter kept behind the subject and no foreground obstruction",
    "with a column or partition partly framing one side of the image",
    "with clean floor markings that do not form symbols or labels",
]
HARD_POSES = {
    "floor_sitting": [
        "seated directly on the floor with the pelvis and buttocks bearing weight, torso upright, knees bent, and both lower legs visibly arranged in a seated configuration",
        "sitting cross-legged on the floor with the hips grounded and the chest upright rather than horizontal",
        "sitting with legs extended forward, pelvis on the floor, and the back supported lightly by posture rather than lying flat",
        "sitting on one bent leg with the other leg extended, the hips low but the torso clearly non-horizontal",
        "seated on the floor while sorting a small work item, with the pelvis grounded and the head and chest raised",
    ],
    "kneeling_half_kneeling": [
        "kneeling on both knees with shins and knees actively supporting the body while the torso remains upright",
        "in a half-kneeling stance with one knee down, the other foot planted, and the chest lifted above the floor",
        "kneeling beside a low object and reaching forward, with knee and shin support visible and the torso not lying down",
        "repairing something from a one-knee kneel, with hips and legs supporting the posture and shoulders held above the ground",
        "in a stable kneeling pose facing slightly away from the camera, with neither the chest nor pelvis spread horizontally on the floor",
    ],
    "pushup_plank": [
        "holding a high plank with straight arms, palms under the shoulders, toes on the floor, and the abdomen lifted between active supports",
        "at the top of a push-up with hands and toes bearing the load and the chest visibly held off the floor",
        "holding a forearm plank with both forearms and toes supporting the body and the torso suspended rather than resting on the ground",
        "at the lower phase of a push-up but still actively supported by hands and toes, with clear space beneath the chest",
        "performing a controlled plank beside a marked work area, with hands and feet providing active support and no passive ground rest",
    ],
    "crawling_quadruped_support": [
        "crawling on hands and knees with four-point support visible and the abdomen and torso lifted clear of the floor",
        "moving in a quadruped posture with both hands and both feet supporting the body, not resting horizontally",
        "reaching forward while on hands and knees, with active limb support and a raised torso",
        "crawling under a low fixture with hands and knees carrying the weight while the body remains a supported non-lying posture",
        "pausing in a three-point crawling stance with one hand reaching, knees and the opposite hand visibly supporting the body",
    ],
    "ground_maintenance": [
        "kneeling while inspecting a floor fixture with one hand holding a tool, hips and knees supporting the body and torso elevated",
        "crouching to clean a low surface with a cloth, feet and bent legs bearing weight rather than a horizontal body on the floor",
        "leaning forward from a supported squat to install a cable near the floor, with both feet or knees visibly stabilizing the pose",
        "checking a drain cover from a one-knee repair posture, with the torso angled forward but not lying down",
        "performing a careful floor inspection beside equipment, supported by bent legs and one hand while the chest remains above ground",
    ],
    "squat_crouch_deep_bend": [
        "holding a deep squat with both feet planted, knees bent, and the pelvis low but still supported by the legs",
        "crouching near the floor with heels and feet bearing weight and the torso angled forward without becoming horizontal",
        "bending deeply to pick up a small object, with straight or bent legs visibly supporting the person",
        "reaching toward the floor from a wide supported stance, hips above the ground and no part of the torso lying flat",
        "pausing in a compact crouch beside a box, with the lower body supporting the pose and shoulders above the floor",
    ],
}
POS_POSES = {
    "supine_ground_lying": [
        "lying fully horizontal on the back on the floor, with the head, shoulders, torso, pelvis, and legs visibly supported by the ground",
        "supine on the floor with the body extended from head to heels and the front of the body facing upward",
        "resting flat on the back across the ground, with a clearly horizontal torso and both legs down on the floor",
        "lying on the floor face-up in an unmistakably horizontal posture, arms and hips supported by the ground",
        "a person already formed into a full back-lying position on the floor, with no seated or standing support relationship",
    ],
    "prone_ground_lying": [
        "lying fully horizontal face-down on the floor, with the chest, abdomen, pelvis, and legs supported by the ground",
        "prone on the ground with the back visible and the entire body extended in a clear horizontal position",
        "resting face-down across the floor, head turned slightly to one side and torso unmistakably supported by the ground",
        "lying flat on the stomach on the floor with arms and legs spread naturally and the body axis horizontal",
        "a person already formed into a full prone ground-lying posture, with no active limb support lifting the torso",
    ],
    "side_lying": [
        "lying horizontally on one side on the floor, with the shoulder, hip, and legs forming a clear side-lying profile",
        "resting in a fully formed side-lying position on the ground with the torso and pelvis supported by the floor",
        "horizontal lateral body posture on the floor, knees slightly bent but the trunk and hips clearly down",
        "lying on the left or right side across the ground, with the body axis parallel to the floor and no seated support",
        "a person already settled into an unmistakable side-lying pose on the floor, partly angled toward the camera",
    ],
    "curled_or_partially_occluded_lying": [
        "lying curled on the floor with knees drawn in, while the horizontal torso and hip support relationship remains clearly visible",
        "partly occluded by a low foreground object but visibly lying horizontally on the ground with the trunk and pelvis down",
        "curled in a compact floor-lying posture, with enough of the shoulder, hip, and legs visible to show full ground support",
        "lying on the ground in a tucked side posture with one limb partly hidden, but the body remains unmistakably horizontal",
        "a partially obscured person already lying on the floor, with the visible torso and hips clearly supported by the ground",
    ],
    "intentional_ground_lying": [
        "intentionally resting flat on the floor for a safe break, with the whole body horizontal and supported by the ground",
        "deliberately lying on the floor to stretch, with the torso, pelvis, and legs visibly down in a complete horizontal posture",
        "voluntarily taking a short rest on the ground, fully face-up and clearly supported by the floor",
        "choosing to lie on the floor during a calm indoor break, body extended horizontally rather than seated or kneeling",
        "an intentional floor-rest scene with a person already lying horizontally on the ground and no active support under the torso",
    ],
    "multi_person_one_lying": [
        "two people are present: one person is clearly lying horizontally on the floor while the other remains standing nearby",
        "three people are present: exactly one person is fully supported horizontally by the ground and the others are upright observers",
        "a small group occupies the scene, with one unmistakably prone person on the floor and the remaining people standing or walking",
        "two workers share the area, one already lying horizontally on the floor and the other upright near a doorway",
        "multiple people are visible, but only one person has a complete horizontal ground-supported body posture",
    ],
    "horizontal_corridor_ground_lying": [
        "a person is already lying horizontally across the corridor floor, with the full body visible from head to feet and supported by the ground",
        "a clear ground-lying figure extends along the inspection corridor, torso and pelvis flat on the floor in a horizontal posture",
        "the main subject is fully prone on the corridor floor, visibly horizontal and not supported by furniture or active limbs",
        "a person lies across the paved passage in a complete horizontal ground posture, with sufficient distance to show the whole body",
        "the corridor view contains one unmistakably horizontal person on the floor, body axis and ground contact clearly visible",
    ],
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def variant_attrs(group_number: int, variant: int) -> dict[str, str]:
    key = group_number * 7 + variant
    scene_name, scene_desc = SCENES[key % len(SCENES)]
    return {
        "scene_type": scene_name,
        "scene_description": scene_desc,
        "lighting": LIGHTING[(key * 3) % len(LIGHTING)],
        "camera_angle": ANGLES[(key * 5) % len(ANGLES)],
        "distance": DISTANCES[(key * 7) % len(DISTANCES)],
        "person_description": PEOPLE[(key * 11) % len(PEOPLE)],
        "clothing": CLOTHING[(key * 13) % len(CLOTHING)],
        "floor": FLOORS[(key * 17) % len(FLOORS)],
        "layout": MINOR_LAYOUTS[(key * 19) % len(MINOR_LAYOUTS)],
    }


def mixed_pose(variant: int) -> tuple[str, str, str]:
    choices = [
        ("normal sofa rest", "reclining on an ordinary sofa in a staff break room, with the sofa visibly supporting the body", "staff break room"),
        ("supported yoga", "holding a supported yoga stretch with a bolster and hands carrying the load, torso not passively down", "quiet multipurpose room"),
        ("perspective illusion", "standing behind a low barrier so perspective makes the body appear close to the floor while the person remains upright", "parking garage"),
        ("mannequin or screen-person confounder", "a life-size mannequin or person depicted on a display screen is visible while no real person is lying on the ground", "training display area"),
        ("normal bed rest", "reclining on a normal bed in a rest area, with the mattress visibly supporting the body", "first-aid rest room"),
    ]
    return choices[variant % len(choices)]


def build_prompt(row: dict[str, str], variant: int) -> tuple[str, dict[str, str]]:
    group_number = int(row["taxonomy_group_index"])
    attrs = variant_attrs(group_number, variant)
    taxonomy = row["taxonomy"]
    target_role = row["target_role"]
    if target_role == "hard_negative":
        if taxonomy == "mixed_hard_negative":
            mixed_name, mixed_clause, mixed_scene = mixed_pose(variant)
            attrs["scene_type"] = mixed_scene
            attrs["scene_description"] = f"a realistic {mixed_scene} arranged for an inspection camera"
            subject_clause = f"This is the {mixed_name} variation: {mixed_clause}. The visual target is a normal non-alert scene, not a person lying on an abnormal support surface."
        else:
            pose = HARD_POSES[taxonomy][variant]
            subject_clause = f"The visible subject is {attrs['person_description']}; the person is wearing {attrs['clothing']} and is {pose}."
    elif target_role == "positive":
        pose = POS_POSES[taxonomy][variant]
        if taxonomy == "multi_person_one_lying":
            subject_clause = f"The scene has {pose}; the lying subject is {attrs['person_description']} in {attrs['clothing']}, while the other people have different ordinary clothing."
        else:
            subject_clause = f"The main subject is {attrs['person_description']} in {attrs['clothing']}, and {pose}."
    elif taxonomy == "standing_walking":
        standing = [
            "walking naturally through the scene with both feet on the floor and the torso upright",
            "standing beside a workstation with weight carried through the legs",
            "moving past a doorway in a normal upright stride",
            "standing and checking a handheld item while remaining fully upright",
            "walking across the open area with a relaxed upright posture",
        ][variant]
        subject_clause = f"The visible subject is {attrs['person_description']} in {attrs['clothing']}, {standing}."
    elif taxonomy == "chair_seated_normal_work":
        seated = [
            "seated normally on a stable office chair with the chair supporting the pelvis and the torso upright",
            "sitting at a workbench on a chair with both feet down and the back above the seat",
            "seated normally on a public chair while reading, with the chair clearly supporting the body",
            "working at a desk from a standard chair, hips supported by the seat and torso non-horizontal",
            "sitting on a sturdy chair near the wall, with legs and seat support plainly visible",
        ][variant]
        subject_clause = f"The visible subject is {attrs['person_description']} in {attrs['clothing']}, {seated}."
    else:
        raise ValueError(f"unknown target role/taxonomy: {target_role}/{taxonomy}")

    prompt = (
        f"Create one photorealistic 1920x1080 landscape frame from a fixed safety-inspection camera mounted about 1.5 meters above the floor. "
        f"The camera observes {attrs['scene_description']} with {attrs['floor']} and {attrs['lighting']}. "
        f"Use a {attrs['camera_angle']} view at {attrs['distance']}; keep natural perspective, realistic scale, and enough surrounding context to judge body support. "
        f"{subject_clause} The composition should be a plausible unedited inspection-camera capture, with the subject clearly visible and {attrs['layout']}. "
        "Use ordinary photographic detail and restrained contrast rather than a cinematic or advertising look. Do not add any text, caption, watermark, logo, warning label, overlay, bounding box, arrow, circle, or artificial annotation."
    )
    return prompt, attrs


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p4d-root", type=Path, default=P4D)
    parser.add_argument("--batch-root", type=Path, default=BATCH)
    args = parser.parse_args()
    p4d_root = args.p4d_root
    batch = args.batch_root
    plan_dir = p4d_root / "01_prompt_plan"
    group_path = plan_dir / "group_manifest.csv"
    freeze_path = plan_dir / "group_split_freeze.json"
    if not group_path.exists() or not freeze_path.exists():
        raise RuntimeError("pre-generation group split freeze is missing")
    groups = read_csv(group_path)
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("design_screen_decided_before_generation") is not True or freeze.get("cross_split_group_count") != 0:
        raise RuntimeError("group freeze does not prove pre-generation split and zero leakage")
    if len(groups) != 88 or sum(int(row["planned_image_count"]) for row in groups) != 440:
        raise RuntimeError("group freeze cardinality mismatch")

    prompt_dir = batch / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    markdown: list[str] = [
        "# P4D new hard-negative revision prompt pack",
        "",
        "Every entry below is a complete English prompt. Group split was frozen before this pack was written and before any image request.",
        "",
        "- Batch: `batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m`",
        "- New text-to-image lineage: `true`",
        "- Target images: 440 (hard-negative 300, positive 100, ordinary-negative 40)",
        "- Internal split: NEW_DESIGN 265 / NEW_SCREEN 175",
        "- Group split leakage: 0",
        "- No old image is used as a reference and no old prompt bytes are copied.",
        "",
    ]
    section_names = {"hard_negative": "Hard Negative", "positive": "Positive", "ordinary_negative": "Ordinary Negative"}
    for role in ["hard_negative", "positive", "ordinary_negative"]:
        markdown.append(f"## {section_names[role]}")
        markdown.append("")
        role_groups = [g for g in groups if g["target_role"] == role]
        for group in role_groups:
            markdown.append(f"### {group['group_id']} — {group['taxonomy']} — {group['planned_internal_split']}")
            markdown.append("")
            for variant_index in range(1, 6):
                prompt_id = f"{group['group_id']}_V{variant_index:02d}"
                prompt, attrs = build_prompt(group, variant_index - 1)
                file_name = f"{prompt_id}.txt"
                prompt_path = prompt_dir / file_name
                data = (prompt + "\n").encode("utf-8")
                prompt_path.write_bytes(data)
                row = {
                    "prompt_id": prompt_id,
                    "group_id": group["group_id"],
                    "variant_id": f"V{variant_index:02d}",
                    "target_role": role,
                    "target_event_label": group["target_event_label"],
                    "taxonomy": group["taxonomy"],
                    "planned_internal_split": group["planned_internal_split"],
                    "camera_height": "1.5m_approx",
                    "target_width": 1920,
                    "target_height": 1080,
                    "aspect_ratio": "16:9",
                    "scene_type": attrs["scene_type"],
                    "lighting": attrs["lighting"],
                    "camera_angle": attrs["camera_angle"],
                    "person_count": 2 if group["taxonomy"] == "multi_person_one_lying" and variant_index in {1, 4} else (3 if group["taxonomy"] == "multi_person_one_lying" else 1),
                    "pose_variant": variant_index,
                    "prompt_path": str(prompt_path),
                    "prompt_sha256": sha256_bytes(data),
                    "generation_batch": group["generation_batch"],
                    "prompt_family_id": group["prompt_family_id"],
                    "new_text_to_image_lineage": "true",
                }
                rows.append(row)
                markdown.extend([f"#### {prompt_id}", "", f"**Group:** `{group['group_id']}`  ", f"**Planned split:** `{group['planned_internal_split']}`  ", f"**Prompt SHA-256:** `{row['prompt_sha256']}`", "", prompt, ""])

    if len(rows) != 440 or len({row["prompt_id"] for row in rows}) != 440:
        raise RuntimeError("prompt cardinality or uniqueness mismatch")
    if len({row["group_id"] for row in rows}) != 88:
        raise RuntimeError("prompt group cardinality mismatch")
    by_split = {split: sum(1 for row in rows if row["planned_internal_split"] == split) for split in ["NEW_DESIGN", "NEW_SCREEN"]}
    if by_split != {"NEW_DESIGN": 265, "NEW_SCREEN": 175}:
        raise RuntimeError(f"prompt split counts mismatch: {by_split}")

    manifest_fields = [
        "prompt_id", "group_id", "variant_id", "target_role", "target_event_label", "taxonomy",
        "planned_internal_split", "camera_height", "target_width", "target_height", "aspect_ratio",
        "scene_type", "lighting", "camera_angle", "person_count", "pose_variant", "prompt_path",
        "prompt_sha256", "generation_batch", "prompt_family_id", "new_text_to_image_lineage",
    ]
    manifest_path = plan_dir / "prompt_manifest.csv"
    write_csv(manifest_path, rows, manifest_fields)
    pack_path = plan_dir / "prompt_pack.md"
    pack_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")

    old_hashes = set()
    old_prompt_count = 0
    for old_prompt in sorted((OLD_BATCH / "prompts").glob("*.txt")):
        old_hashes.add(sha256_file(old_prompt))
        old_prompt_count += 1
    exact_old_matches = [row["prompt_id"] for row in rows if row["prompt_sha256"] in old_hashes]
    if exact_old_matches:
        raise RuntimeError(f"new prompt bytes exactly match old prompt(s): {exact_old_matches[:5]}")

    pack_hash = sha256_file(pack_path)
    manifest_hash = sha256_file(manifest_path)
    (plan_dir / "prompt_pack.sha256").write_text(f"{pack_hash}  {pack_path.name}\n", encoding="utf-8")
    (plan_dir / "prompt_manifest.sha256").write_text(f"{manifest_hash}  {manifest_path.name}\n", encoding="utf-8")
    freeze_out = {
        "stage": "P4D_NEW_HARD_NEGATIVE_DEV_REVISION",
        "freeze_type": "prompt_pack_freeze_after_pre_generation_group_split",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generation_batch": "batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m",
        "prompt_count": len(rows),
        "group_count": len(groups),
        "split_counts": {"NEW_DESIGN": 265, "NEW_SCREEN": 175},
        "role_counts": {
            "hard_negative": sum(1 for row in rows if row["target_role"] == "hard_negative"),
            "positive": sum(1 for row in rows if row["target_role"] == "positive"),
            "ordinary_negative": sum(1 for row in rows if row["target_role"] == "ordinary_negative"),
        },
        "group_split_freeze_sha256": sha256_file(freeze_path),
        "group_manifest_sha256": sha256_file(group_path),
        "prompt_pack_sha256": pack_hash,
        "prompt_manifest_sha256": manifest_hash,
        "old_prompt_count_audited": old_prompt_count,
        "exact_old_prompt_matches": len(exact_old_matches),
        "new_text_to_image_lineage": True,
        "old_images_as_references": False,
        "model_or_c3_used_before_prompt_freeze": False,
        "images_generated": 0,
        "formal_dataset_mutation": False,
        "val_requests": 0,
        "holdout_requests": 0,
    }
    (plan_dir / "prompt_pack_freeze.json").write_text(json.dumps(freeze_out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (plan_dir / "prompt_pack_freeze.sha256").write_text(f"{sha256_file(plan_dir / 'prompt_pack_freeze.json')}  prompt_pack_freeze.json\n", encoding="utf-8")
    (batch / "generation_attempts.csv").write_text("attempt_id,prompt_id,timestamp,provider,model,model_version,seed,provider_request_id,status,output_path,notes\n", encoding="utf-8")
    (batch / "README.md").write_text(
        "# P4D staged generation batch\n\n"
        "This directory is dedicated to `batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m`.\n"
        "The group split and 440-prompt pack were frozen before any image request.\n"
        "Images are development-only and require mechanical QA plus reliable human semantic review before formal ingest.\n",
        encoding="utf-8",
    )
    metadata = {
        "generation_batch": "batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m",
        "source_type": "ai_generated",
        "usage_scope": "development_only",
        "generation_model": "gpt-image-2",
        "generation_model_version": "gpt-image-2",
        "target_size": "1920x1080",
        "camera_height_approx_m": 1.5,
        "seed_policy": "provider_reported_or_unknown; never fabricated",
        "group_split_freeze": str(freeze_path),
        "prompt_pack_freeze": str(plan_dir / "prompt_pack_freeze.json"),
    }
    (batch / "metadata" / "lineage.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = {
        "P4D_PROMPT_PACK_READY": True,
        "P4D_STATUS": "GENERATION_REQUIRED",
        "PROMPTS_PLANNED": 440,
        "PROMPTS_WRITTEN": len(rows),
        "GROUPS": 88,
        "NEW_DESIGN_PLANNED": 265,
        "NEW_SCREEN_PLANNED": 175,
        "IMAGES_GENERATED": 0,
        "FORMAL_DATASET_MUTATION": False,
        "MODEL_REQUESTS": 0,
        "VAL_REQUESTS": 0,
        "HOLDOUT_REQUESTS": 0,
    }
    (p4d_root / "00_preflight" / "prompt_pack_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**status, "prompt_pack_sha256": pack_hash, "prompt_manifest_sha256": manifest_hash, "prompt_freeze_sha256": sha256_file(plan_dir / "prompt_pack_freeze.json"), "exact_old_prompt_matches": len(exact_old_matches)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
