#!/usr/bin/env python3
"""Build the isolated person_fallen v3.0 prompt-derived synthetic-GT lineage.

This tool never edits v2 manifests, formal dataset CSVs, generated source
images, or the production repository.  It reads frozen prompt/group metadata
and writes a new v3 remap/audit package plus v3 DEV/SCREEN/VAL manifests.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


V2_ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
OUT = V2_ROOT / "11_person_fallen_v3_revision"
V2_MANIFEST = V2_ROOT / "01_data/frozen_manifest.csv"
P4D_PLAN = V2_ROOT / "08_p4d_new_hard_negative_dev_revision/01_prompt_plan/prompt_manifest.csv"
P4D_FAST = V2_ROOT / "10_fast_close/fast_close_clean_manifest.csv"
P4D_SAFE = V2_ROOT / (
    "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/"
    "quota_campaign_window_07_gr3q10_authorized_20260901_01/06_partial_qa/"
    "safe_executable_outstanding.csv"
)
P4D_Q9_PLAN = V2_ROOT / (
    "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/"
    "quota_campaign_window_06_gr3q9_authorized_20260831_01/02_plan/"
    "q9_hard_negative_balanced_30_plan.csv"
)
P4D_Q10_PLAN = V2_ROOT / (
    "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/"
    "quota_campaign_window_07_gr3q10_authorized_20260901_01/02_runner/"
    "q10_balanced_complete_group_30_plan.csv"
)
P4D_Q10_DB = V2_ROOT / (
    "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/"
    "quota_campaign_window_07_gr3q10_authorized_20260901_01/03_ledger/"
    "gr3q10_execution.sqlite3"
)
P4D_UNKNOWN = V2_ROOT / (
    "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/"
    "quota_campaign_window_07_gr3q10_authorized_20260901_01/06_partial_qa/"
    "completion_unknown_quarantine.csv"
)
V3_PROMPT = OUT / "prompt/V3-C0_prompt.txt"


V2_TAXONOMY = {
    "pf_v2_aigc_p01-supine-on-floor": "supine_ground_lying",
    "pf_v2_aigc_p02-supine-on-floor": "supine_ground_lying",
    "pf_v2_aigc_p03-prone-on-floor": "prone_ground_lying",
    "pf_v2_aigc_p04-prone-on-floor": "prone_ground_lying",
    "pf_v2_aigc_p05-side-lying-on-floor": "side_lying",
    "pf_v2_aigc_p06-side-lying-on-floor": "side_lying",
    "pf_v2_aigc_p07-irregular-sprawled-posture": "irregular_sprawled_lying",
    "pf_v2_aigc_p08-irregular-sprawled-posture": "curled_or_sprawled_lying",
    "pf_v2_aigc_p09-partially-occluded-fallen-person": "partially_occluded_lying",
    "pf_v2_aigc_p10-partially-occluded-fallen-person": "partially_occluded_lying",
    "pf_v2_aigc_p11-small-target-far-distance": "small_target_ground_lying",
    "pf_v2_aigc_p12-small-target-far-distance": "small_target_ground_lying",
    "pf_v2_aigc_p13-multi-person-scene-with-one-lying-person": "multi_person_one_lying",
    "pf_v2_aigc_p14-multi-person-scene-with-one-lying-person": "multi_person_one_lying",
    "pf_v2_aigc_p15-low-light-shadow-mild-blur": "low_light_ground_lying",
    "pf_v2_aigc_p16-low-light-shadow-mild-blur": "low_light_ground_lying",
    "pf_v2_aigc_p17-abnormal-support-surface": "abnormal_nonrest_support",
    "pf_v2_aigc_p18-abnormal-support-surface": "abnormal_nonrest_support",
    "pf_v2_aigc_p19-active-voluntary-lying-on-ground": "intentional_ground_lying",
    "pf_v2_aigc_p20-static-lying-on-ground": "static_ground_lying",
    "pf_v2_aigc_n01-normal-standing": "standing",
    "pf_v2_aigc_n02-normal-walking": "walking",
    "pf_v2_aigc_n03-normal-seated-on-chair-stool": "chair_sitting",
    "pf_v2_aigc_n04-normal-seated-on-chair-stool": "chair_sitting",
    "pf_v2_aigc_n05-normal-work-activity": "ordinary_work",
    "pf_v2_aigc_n06-normal-work-activity": "ordinary_work",
    "pf_v2_aigc_n07-mild-bending": "bending",
    "pf_v2_aigc_n08-multi-person-normal-activity": "ordinary_multi_activity",
    "pf_v2_aigc_n09-empty-ordinary-environment": "no_person",
    "pf_v2_aigc_n10-empty-ordinary-environment": "no_person",
    "pf_v2_aigc_h01-sitting-on-floor": "floor_sitting",
    "pf_v2_aigc_h02-sitting-on-floor": "floor_sitting",
    "pf_v2_aigc_h03-kneeling": "kneeling_half_kneeling",
    "pf_v2_aigc_h04-kneeling": "kneeling_half_kneeling",
    "pf_v2_aigc_h05-squatting": "squat_crouch_deep_bend",
    "pf_v2_aigc_h06-squatting": "squat_crouch_deep_bend",
    "pf_v2_aigc_h07-deep-bending-picking-up-items": "bending_pickup",
    "pf_v2_aigc_h08-deep-bending-picking-up-items": "bending_pickup",
    "pf_v2_aigc_h09-exercise-push-up-plank": "pushup_plank",
    "pf_v2_aigc_h10-exercise-push-up-plank": "pushup_plank",
    # h11 is crawling/reaching with active support but does not state repair,
    # maintenance, or installation; under v3 it is positive.
    "pf_v2_aigc_h11-crawling-under-equipment-inspection": "crawling_without_explicit_maintenance",
    "pf_v2_aigc_h12-crawling-under-equipment-inspection": "crawling_explicit_maintenance",
    "pf_v2_aigc_h13-normal-lying-on-bed": "bed_normal_rest",
    "pf_v2_aigc_h14-normal-lying-on-bed": "bed_normal_rest",
    "pf_v2_aigc_h15-normal-lying-on-sofa-or-recliner": "sofa_normal_rest",
    "pf_v2_aigc_h16-dummy-mannequin-poster": "clear_non_person_depiction",
    "pf_v2_aigc_h17-partial-body-causing-illusion": "partial_body_unconfirmable",
    "pf_v2_aigc_h18-screen-mirror-photo-depiction": "clear_non_person_depiction",
    "pf_v2_aigc_u01-severely-occluded-tiny-blurry": "person_unconfirmable",
    "pf_v2_aigc_u02-unclear-support-surface-partial-body": "person_unconfirmable",
}

POSITIVE_TAXA = {
    "supine_ground_lying",
    "prone_ground_lying",
    "side_lying",
    "irregular_sprawled_lying",
    "curled_or_sprawled_lying",
    "partially_occluded_lying",
    "small_target_ground_lying",
    "multi_person_one_lying",
    "low_light_ground_lying",
    "abnormal_nonrest_support",
    "intentional_ground_lying",
    "static_ground_lying",
    "pushup_plank",
    "crawling_without_explicit_maintenance",
    # Frozen P4D taxonomy names.
    "curled_or_partially_occluded_lying",
    "crawling_quadruped_support",
    "horizontal_corridor_ground_lying",
}
UNCERTAIN_TAXA = {"partial_body_unconfirmable", "person_unconfirmable"}

FIELDS = [
    "item_id",
    "source_family",
    "prompt_id",
    "media_id",
    "group_id",
    "source_split",
    "v3_split",
    "old_role",
    "old_label",
    "taxonomy",
    "prompt_path",
    "prompt_sha256_expected",
    "prompt_sha256_actual",
    "source_image_path",
    "source_image_sha256_expected",
    "source_image_sha256_actual",
    "source_image_sha_basis",
    "source_asset_status",
    "source_provenance_status",
    "remap_rule",
    "prompt_semantics_check",
    "new_label",
    "gt_type",
    "gt_source",
    "human_semantic_review_required",
    "metric_stratum",
    "formal_v3_evaluation",
    "evaluation_exclusion_reason",
]

SPLIT_FIELDS = [
    "item_id",
    "source_family",
    "prompt_id",
    "media_id",
    "group_id",
    "source_split",
    "v3_split",
    "image_path",
    "image_sha256",
    "image_sha_basis",
    "prompt_path",
    "prompt_sha256",
    "taxonomy",
    "old_role",
    "old_label",
    "ground_truth",
    "metric_stratum",
    "source_provenance_status",
    "gt_type",
    "gt_source",
    "human_semantic_review_required",
    "formal_v3_evaluation",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prompt_id_from_filename(filename: str) -> str:
    return Path(filename).stem


def semantic_excerpt(prompt: str) -> str:
    return " ".join(prompt.split())[:320]


def classify_prompt(taxonomy: str, prompt: str) -> tuple[str, str, str]:
    """Return (new label, deterministic rule, semantic check).

    The taxonomy is the frozen planned semantic role.  The prompt text is
    checked for the decisive cue; it is never inferred from the image.
    """
    low = prompt.lower()
    if taxonomy in UNCERTAIN_TAXA:
        if not any(word in low for word in ("occlud", "small", "blur", "partial", "only part", "obscure", "unclear", "hard to tell")):
            raise ValueError(f"uncertain taxonomy lacks uncertainty cue: {taxonomy}")
        return "uncertain", "V3_PRIORITY_CANNOT_CONFIRM_REAL_PERSON", "PASS_EXPLICIT_UNCERTAINTY_CUE"
    if taxonomy == "clear_non_person_depiction":
        if not any(word in low for word in ("mannequin", "dummy", "poster", "screen", "mirror", "photo")):
            raise ValueError("non-person taxonomy lacks explicit non-person cue")
        return "negative", "V3_CLEAR_NON_PERSON_IS_NEGATIVE", "PASS_EXPLICIT_NON_PERSON_CUE"
    if taxonomy in POSITIVE_TAXA:
        required = {
            "pushup_plank": ("push-up", "pushup", "plank", "exercise"),
            "crawling_without_explicit_maintenance": ("crawling", "hands and knees", "active support"),
            "crawling_quadruped_support": ("crawling", "quadruped", "hands and knees", "four-point", "active support"),
            "prone_ground_lying": ("prone", "face-down", "lying", "ground"),
        }.get(taxonomy, ("lying", "horizontal", "prone", "supine", "side", "ground", "floor", "face-up"))
        if not any(word in low for word in required):
            raise ValueError(f"positive taxonomy lacks decisive posture cue: {taxonomy}")
        return "positive", f"V3_{taxonomy.upper()}_POSITIVE", "PASS_EXPLICIT_POSTURE_CUE"
    if taxonomy == "crawling_explicit_maintenance":
        if not any(word in low for word in ("inspect", "repair", "maintenance", "install", "fixture", "tool")):
            raise ValueError("maintenance taxonomy lacks explicit work cue")
        return "negative", "V3_EXPLICIT_MAINTENANCE_REPAIR_INSTALLATION_NEGATIVE", "PASS_EXPLICIT_WORK_CONTEXT"
    if taxonomy == "mixed_hard_negative":
        # Mixed prompts are accepted only when their frozen text contains a
        # decisive, non-conflicting negative context.  Otherwise they fail
        # closed as EXCLUDE_PROTOCOL_AMBIGUOUS.
        negative_cues = (
            "sofa", "bed", "recliner", "normal rest", "rest support", "standing",
            "walking", "sitting", "kneeling", "squat", "bending", "repair",
            "maintenance", "install", "supported yoga", "bolster", "mannequin",
            "screen-person", "no real person", "normal non-alert",
        )
        positive_cues = (
            "lying on the ground", "lying on the floor", "crawling", "push-up",
            "plank", "prone on the floor", "supine on the floor", "side-lying",
        )
        positive_negated = any(
            phrase in low
            for phrase in (
                "no real person is lying",
                "no real person is crawling",
                "not a person lying",
                "not a person crawling",
                "not a person lying on an abnormal",
                "not passively down",
            )
        )
        if any(word in low for word in negative_cues) and (not any(word in low for word in positive_cues) or positive_negated):
            return "negative", "V3_MIXED_PROMPT_EXPLICIT_NEGATIVE_CONTEXT", "PASS_MIXED_EXPLICIT_NEGATIVE"
        raise ValueError("mixed prompt has no unambiguous v3 negative cue")
    negative_cues = {
        "floor_sitting": ("sitting", "seated"),
        "kneeling_half_kneeling": ("kneeling", "half-kneeling", "one-knee kneel", "both knees", "knees"),
        "squat_crouch_deep_bend": ("squat", "crouch", "deep", "pelvis low", "feet planted", "wide supported stance", "hips above"),
        "bending_pickup": ("bending", "picking", "pickup"),
        "bed_normal_rest": ("bed", "sleeping surface", "normal resting"),
        "sofa_normal_rest": ("sofa", "recliner", "normal resting"),
        "standing": ("standing",),
        "walking": ("walking",),
        "chair_sitting": ("chair", "sitting"),
        "ordinary_work": ("work", "checking", "organizing", "carrying"),
        "ordinary_multi_activity": ("standing", "talking", "moving"),
        "bending": ("bending", "leaning"),
        "no_person": ("no person", "no people", "empty"),
        "ground_maintenance": ("inspect", "repair", "maintenance", "tool", "fixture", "floor"),
        "chair_seated_normal_work": ("chair", "seated", "sitting"),
        "standing_walking": ("standing", "walking", "upright"),
    }
    cues = negative_cues.get(taxonomy)
    if cues is None:
        raise ValueError(f"no deterministic taxonomy rule: {taxonomy}")
    if not any(word in low for word in cues):
        raise ValueError(f"negative taxonomy lacks decisive cue: {taxonomy}")
    return "negative", f"V3_{taxonomy.upper()}_NEGATIVE", "PASS_EXPLICIT_NEGATIVE_CUE"


def metric_stratum(old_role: str, new_label: str) -> str:
    if new_label == "positive":
        return "positive"
    if new_label == "uncertain":
        return "uncertain"
    if old_role == "hard_negative":
        return "hard_negative"
    if old_role in {"negative", "ordinary_negative"}:
        return "ordinary_negative"
    return "other_negative"


def verify_image(path: Path, expected_sha: str) -> str:
    if not path.is_file():
        raise RuntimeError(f"image missing: {path}")
    actual = sha256(path)
    if actual != expected_sha:
        raise RuntimeError(f"image sha mismatch: {path}")
    with Image.open(path) as image:
        image.verify()
    return actual


def remap_row(
    *,
    item_id: str,
    source_family: str,
    prompt_id: str,
    media_id: str,
    group_id: str,
    source_split: str,
    v3_split: str,
    old_role: str,
    old_label: str,
    taxonomy: str,
    prompt_path: Path,
    prompt_expected: str,
    image_path: Path | None,
    image_expected: str,
    image_sha_basis: str,
    source_asset_status: str,
    source_provenance_status: str,
    formal: bool,
    exclusion_reason: str,
) -> dict[str, str]:
    prompt_actual = sha256(prompt_path)
    if prompt_actual != prompt_expected:
        raise RuntimeError(f"prompt sha mismatch: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8")
    new_label, rule, semantic_check = classify_prompt(taxonomy, prompt)
    image_actual = ""
    if image_path is not None:
        image_actual = verify_image(image_path, image_expected)
    return {
        "item_id": item_id,
        "source_family": source_family,
        "prompt_id": prompt_id,
        "media_id": media_id,
        "group_id": group_id,
        "source_split": source_split,
        "v3_split": v3_split,
        "old_role": old_role,
        "old_label": old_label,
        "taxonomy": taxonomy,
        "prompt_path": str(prompt_path),
        "prompt_sha256_expected": prompt_expected,
        "prompt_sha256_actual": prompt_actual,
        "source_image_path": str(image_path) if image_path is not None else "",
        "source_image_sha256_expected": image_expected,
        "source_image_sha256_actual": image_actual,
        "source_image_sha_basis": image_sha_basis,
        "source_asset_status": source_asset_status,
        "source_provenance_status": source_provenance_status,
        "remap_rule": rule,
        "prompt_semantics_check": semantic_check,
        "new_label": new_label,
        "gt_type": "PROMPT_DERIVED_SYNTHETIC_GT",
        "gt_source": "FROZEN_GENERATION_PROMPT_AND_PLANNED_ROLE",
        "human_semantic_review_required": "false",
        "metric_stratum": metric_stratum(old_role, new_label),
        "formal_v3_evaluation": "true" if formal else "false",
        "evaluation_exclusion_reason": exclusion_reason,
    }


def build_v2_rows() -> list[dict[str, str]]:
    rows = load_csv(V2_MANIFEST)
    if len(rows) != 500:
        raise RuntimeError(f"unexpected v2 source row count: {len(rows)}")
    output: list[dict[str, str]] = []
    for row in rows:
        taxonomy = V2_TAXONOMY.get(row["scenario_id"])
        if taxonomy is None:
            raise RuntimeError(f"v2 scenario taxonomy missing: {row['scenario_id']}")
        prompt_path = Path(row["prompt_path"])
        image_path = Path(row["source_image_path"])
        formal = row["split"] in {"DEV", "VAL"}
        v3_split = {"DEV": "V3_DEV", "VAL": "V3_VAL", "HOLDOUT": "EXCLUDE_FINAL_HOLDOUT"}[row["split"]]
        exclusion = "" if formal else "FINAL_HOLDOUT_RESERVED_AND_NOT_USED_BY_V3"
        output.append(
            remap_row(
                item_id=f"V2_ORIGINAL::{row['media_id']}",
                source_family="V2_ORIGINAL_SYNTHETIC_500",
                prompt_id=prompt_id_from_filename(row["prompt_filename"]),
                media_id=row["media_id"],
                group_id=row["group_id"],
                source_split=row["split"],
                v3_split=v3_split,
                old_role=row["sample_role"],
                old_label=row["event_label"],
                taxonomy=taxonomy,
                prompt_path=prompt_path,
                prompt_expected=row["prompt_sha256"],
                image_path=image_path,
                image_expected=row["image_sha256"],
                image_sha_basis="FROZEN_V2_MANIFEST_EXPECTED_AND_ACTUAL",
                source_asset_status="REUSABLE_V2_NON_HOLDOUT" if formal else "FINAL_HOLDOUT_RESERVED",
                source_provenance_status="FROZEN_V2_PROMPT_IMAGE_MAPPING_PASS",
                formal=formal,
                exclusion_reason=exclusion,
            )
        )
    return output


def load_q10_states() -> tuple[set[str], set[str]]:
    connection = sqlite3.connect(P4D_Q10_DB)
    rows = connection.execute("SELECT prompt_id,state FROM slots").fetchall()
    connection.close()
    failed = {prompt_id for prompt_id, state in rows if state == "FAILED_CONFIRMED"}
    not_started = {prompt_id for prompt_id, state in rows if state == "NOT_STARTED"}
    if failed != {"PF_P4D_HN_PLANK_G002_V02"}:
        raise RuntimeError(f"unexpected q10 failed set: {sorted(failed)}")
    if len(not_started) != 23:
        raise RuntimeError(f"unexpected q10 not-started count: {len(not_started)}")
    return failed, not_started


def build_p4d_rows() -> tuple[list[dict[str, str]], dict[str, int]]:
    plan = load_csv(P4D_PLAN)
    fast = {row["prompt_id"]: row for row in load_csv(P4D_FAST)}
    q9 = {row["prompt_id"] for row in load_csv(P4D_Q9_PLAN)}
    q10_plan = {row["prompt_id"] for row in load_csv(P4D_Q10_PLAN)}
    q10_failed, q10_not_started = load_q10_states()
    safe = {row["prompt_id"] for row in load_csv(P4D_SAFE)}
    unknown = {row["prompt_id"] for row in load_csv(P4D_UNKNOWN)}
    plan_ids = {row["prompt_id"] for row in plan}
    if len(plan) != 440 or len(plan_ids) != 440:
        raise RuntimeError("P4D frozen prompt plan is not 440 unique rows")
    if len(fast) != 202 or q9 != {row["prompt_id"] for row in load_csv(P4D_Q9_PLAN)}:
        raise RuntimeError("P4D clean/Q9 inventory shape mismatch")
    if not q9.isdisjoint(fast):
        raise RuntimeError("Q9 binding-blocked rows overlap clean fast-close rows")
    if not q10_failed.issubset(q10_plan) or not q10_not_started.issubset(q10_plan):
        raise RuntimeError("Q10 terminal states are not in the frozen Q10 plan")
    if not q10_failed.issubset(safe) or not q10_not_started.issubset(safe):
        raise RuntimeError("Q10 failed/not-started rows missing from safe outstanding inventory")
    if not unknown.isdisjoint(safe):
        raise RuntimeError("completion-unknown row unexpectedly appears in safe outstanding inventory")
    fast_ids = set(fast)
    if not (q9 | safe | fast_ids | unknown) == plan_ids:
        missing = sorted(plan_ids - (q9 | safe | fast_ids | unknown))
        extra = sorted((q9 | safe | fast_ids | unknown) - plan_ids)
        raise RuntimeError(f"P4D accounting mismatch missing={missing[:3]} extra={extra[:3]}")
    safe_other = safe - q10_failed - q10_not_started
    accounting = {
        "P4D_FROZEN_PLAN_TOTAL": len(plan_ids),
        "P4D_REUSABLE_CLEAN": len(fast),
        "P4D_Q9_BINDING_BLOCKED": len(q9),
        "P4D_COMPLETION_UNKNOWN": len(unknown),
        "P4D_Q10_FAILED_CONFIRMED": len(q10_failed),
        "P4D_Q10_NOT_STARTED": len(q10_not_started),
        "P4D_OTHER_SAFE_OUTSTANDING": len(safe_other),
        "P4D_SAFE_OUTSTANDING_TOTAL": len(safe),
    }
    if sum(accounting[k] for k in ("P4D_REUSABLE_CLEAN", "P4D_Q9_BINDING_BLOCKED", "P4D_COMPLETION_UNKNOWN", "P4D_Q10_FAILED_CONFIRMED", "P4D_Q10_NOT_STARTED", "P4D_OTHER_SAFE_OUTSTANDING")) != 440:
        raise RuntimeError(f"P4D accounting does not sum to 440: {accounting}")

    output: list[dict[str, str]] = []
    for row in plan:
        prompt_path = Path(row["prompt_path"])
        prompt_id = row["prompt_id"]
        source_status = ""
        source_provenance = ""
        image_path: Path | None = None
        image_expected = ""
        formal = False
        v3_split = "EXCLUDE_NOT_REUSABLE"
        exclusion = ""
        if prompt_id in fast:
            fast_row = fast[prompt_id]
            source_status = "REUSABLE_P4D_CLEAN_FAST_CLOSE"
            source_provenance = "P4D_FAST_CLOSE_PROVENANCE_MECHANICAL_LINEAGE_PASS"
            image_path = Path(fast_row["final_path"])
            image_expected = fast_row["final_sha256_expected"] or fast_row["final_sha256_actual"]
            image_sha_basis = (
                "FAST_CLOSE_EXPECTED_AND_ACTUAL"
                if fast_row["final_sha256_expected"]
                else "FAST_CLOSE_CURRENT_REHASH_EXPECTED_FIELD_EMPTY"
            )
            formal = True
            v3_split = "V3_DEV" if row["planned_internal_split"] == "NEW_DESIGN" else "V3_SCREEN"
        elif prompt_id in q9:
            source_status = "Q9_BINDING_BLOCKED"
            source_provenance = "Q9_POSTRUN_CONFIG_BINDING_MISMATCH"
            v3_split = "AUXILIARY_DIAGNOSTIC_ONLY"
            exclusion = "Q9_BINDING_BLOCKED_NOT_FORMAL_V3_MAIN_METRICS"
            image_sha_basis = "NOT_APPLICABLE_NO_FORMAL_IMAGE"
        elif prompt_id in unknown:
            source_status = "COMPLETION_UNKNOWN_QUARANTINED"
            source_provenance = "COMPLETION_UNKNOWN_FAIL_CLOSED"
            exclusion = "COMPLETION_UNKNOWN_EXCLUDED_AND_NOT_RESENT"
            image_sha_basis = "NOT_APPLICABLE_NO_FORMAL_IMAGE"
        elif prompt_id in q10_failed:
            source_status = "FAILED_CONFIRMED"
            source_provenance = "Q10_HTTP429_USAGE_LIMIT_REACHED"
            exclusion = "FAILED_CONFIRMED_EXCLUDED_AND_NOT_RESENT"
            image_sha_basis = "NOT_APPLICABLE_NO_FORMAL_IMAGE"
        elif prompt_id in q10_not_started:
            source_status = "NOT_STARTED"
            source_provenance = "Q10_TERMINAL_NOT_STARTED"
            exclusion = "NOT_STARTED_EXCLUDED_AND_NOT_RESENT"
            image_sha_basis = "NOT_APPLICABLE_NO_FORMAL_IMAGE"
        elif prompt_id in safe_other:
            source_status = "UNEXECUTED_OR_NOT_REUSABLE"
            source_provenance = "SAFE_OUTSTANDING_NOT_CLEAN_ASSET"
            exclusion = "NO_VERIFIED_REUSABLE_CLEAN_ASSET"
            image_sha_basis = "NOT_APPLICABLE_NO_FORMAL_IMAGE"
        else:
            raise RuntimeError(f"unclassified P4D prompt: {prompt_id}")
        output.append(
            remap_row(
                item_id=f"P4D_PLAN::{prompt_id}",
                source_family="P4D_FROZEN_PLAN_440",
                prompt_id=prompt_id,
                media_id="",
                group_id=row["group_id"],
                source_split=row["planned_internal_split"],
                v3_split=v3_split,
                old_role=row["target_role"],
                old_label=row["target_event_label"],
                taxonomy=row["taxonomy"],
                prompt_path=prompt_path,
                prompt_expected=row["prompt_sha256"],
                image_path=image_path,
                image_expected=image_expected,
                image_sha_basis=image_sha_basis,
                source_asset_status=source_status,
                source_provenance_status=source_provenance,
                formal=formal,
                exclusion_reason=exclusion,
            )
        )
    return output, accounting


def split_manifest_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "item_id": row["item_id"],
        "source_family": row["source_family"],
        "prompt_id": row["prompt_id"],
        "media_id": row["media_id"],
        "group_id": row["group_id"],
        "source_split": row["source_split"],
        "v3_split": row["v3_split"],
        "image_path": row["source_image_path"],
        "image_sha256": row["source_image_sha256_expected"],
        "image_sha_basis": row["source_image_sha_basis"],
        "prompt_path": row["prompt_path"],
        "prompt_sha256": row["prompt_sha256_actual"],
        "taxonomy": row["taxonomy"],
        "old_role": row["old_role"],
        "old_label": row["old_label"],
        "ground_truth": row["new_label"],
        "metric_stratum": row["metric_stratum"],
        "source_provenance_status": row["source_provenance_status"],
        "gt_type": row["gt_type"],
        "gt_source": row["gt_source"],
        "human_semantic_review_required": row["human_semantic_review_required"],
        "formal_v3_evaluation": row["formal_v3_evaluation"],
    }


def main() -> None:
    for required in (V2_MANIFEST, P4D_PLAN, P4D_FAST, P4D_SAFE, P4D_Q9_PLAN, P4D_Q10_PLAN, P4D_Q10_DB, P4D_UNKNOWN, V3_PROMPT):
        if not required.is_file():
            raise SystemExit(f"V3_REMAP_INPUT_MISSING={required}")
    v2_rows = build_v2_rows()
    p4d_rows, p4d_accounting = build_p4d_rows()
    rows = v2_rows + p4d_rows
    if len(rows) != 940 or len({row["item_id"] for row in rows}) != 940:
        raise SystemExit("V3_REMAP_TOTAL_OR_UNIQUENESS_MISMATCH")

    formal = [row for row in rows if row["formal_v3_evaluation"] == "true"]
    for split in ("V3_DEV", "V3_SCREEN", "V3_VAL"):
        group_ids = {row["group_id"] for row in formal if row["v3_split"] == split}
        if not group_ids:
            raise SystemExit(f"V3_SPLIT_EMPTY={split}")
    group_to_splits: dict[str, set[str]] = defaultdict(set)
    for row in formal:
        group_to_splits[row["group_id"]].add(row["v3_split"])
    leakage = {group: sorted(splits) for group, splits in group_to_splits.items() if len(splits) > 1}
    if leakage:
        raise SystemExit(f"V3_GROUP_SPLIT_LEAKAGE={leakage}")
    if any(row["source_image_path"] == "" for row in formal):
        raise SystemExit("V3_FORMAL_ROW_WITHOUT_IMAGE")
    if any(row["new_label"] not in {"positive", "negative", "uncertain"} for row in rows):
        raise SystemExit("V3_REMAP_LABEL_INVALID")

    write_csv(OUT / "remap/person_fallen_v3_remap_manifest.csv", rows, FIELDS)
    for split in ("V3_DEV", "V3_SCREEN", "V3_VAL"):
        subset = [split_manifest_row(row) for row in formal if row["v3_split"] == split]
        write_csv(OUT / f"remap/person_fallen_v3_{split[3:].lower()}_manifest.csv", subset, SPLIT_FIELDS)

    counts = {
        "all_remap_rows": len(rows),
        "v2_original_rows": len(v2_rows),
        "p4d_plan_rows": len(p4d_rows),
        "formal_v3_rows": len(formal),
        "formal_by_split": dict(sorted(Counter(row["v3_split"] for row in formal).items())),
        "all_new_label": dict(sorted(Counter(row["new_label"] for row in rows).items())),
        "formal_new_label": dict(sorted(Counter(row["new_label"] for row in formal).items())),
        "formal_by_source_family": dict(sorted(Counter(row["source_family"] for row in formal).items())),
        "formal_by_taxonomy": dict(sorted(Counter(row["taxonomy"] for row in formal).items())),
        "formal_by_metric_stratum": dict(sorted(Counter(row["metric_stratum"] for row in formal).items())),
        "formal_by_image_sha_basis": dict(sorted(Counter(row["source_image_sha_basis"] for row in formal).items())),
        "excluded_by_status": dict(sorted(Counter(row["source_asset_status"] for row in rows if row["formal_v3_evaluation"] != "true").items())),
    }
    audit = {
        "status": "PASS",
        "revision_id": "PERSON_FALLEN_V3_ANOMALOUS_NEAR_GROUND_20260901_01",
        "event_name": "person_fallen",
        "event_definition_version": "v3.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_hashes": {
            "v2_frozen_manifest_sha256": sha256(V2_MANIFEST),
            "p4d_frozen_prompt_plan_sha256": sha256(P4D_PLAN),
            "p4d_fast_close_manifest_sha256": sha256(P4D_FAST),
            "p4d_safe_outstanding_sha256": sha256(P4D_SAFE),
            "p4d_q9_plan_sha256": sha256(P4D_Q9_PLAN),
            "p4d_q10_plan_sha256": sha256(P4D_Q10_PLAN),
            "p4d_q10_ledger_sha256": sha256(P4D_Q10_DB),
            "v3_prompt_sha256": sha256(V3_PROMPT),
        },
        "counts": counts,
        "p4d_accounting": p4d_accounting,
        "gt_policy": {
            "GT_TYPE": "PROMPT_DERIVED_SYNTHETIC_GT",
            "GT_SOURCE": "FROZEN_GENERATION_PROMPT_AND_PLANNED_ROLE",
            "HUMAN_SEMANTIC_REVIEW_REQUIRED": False,
            "model_prediction_used_as_gt": False,
            "formal_scope": "AI-generated development/screening/synthetic validation only",
        },
        "protocol_ambiguity": {
            "count": sum(row["v3_split"] == "EXCLUDE_PROTOCOL_AMBIGUOUS" for row in rows),
            "items": [row["item_id"] for row in rows if row["v3_split"] == "EXCLUDE_PROTOCOL_AMBIGUOUS"],
        },
        "group_integrity": {
            "formal_unique_group_count": len(group_to_splits),
            "cross_split_group_count": len(leakage),
            "cross_split_groups": leakage,
        },
        "holdout_boundary": {
            "v2_holdout_rows": sum(row["source_split"] == "HOLDOUT" for row in v2_rows),
            "v2_holdout_in_formal_v3": False,
            "final_holdout_executed": False,
            "holdout_consumed": False,
        },
        "q9_boundary": {
            "q9_rows": p4d_accounting["P4D_Q9_BINDING_BLOCKED"],
            "formal_main_metrics": False,
            "use": "AUXILIARY_DIAGNOSTIC_ONLY",
        },
        "old_p4d_generation": {
            "target_slots": 440,
            "STOP_FURTHER_P4D_GENERATION": True,
            "OLD_P4D_440_REQUIREMENT": "SUPERSEDED_FOR_PERSON_FALLEN_V3",
            "q10_q11_or_unknown_resend": False,
        },
        "source_read_only_boundary": {
            "v2_files_modified": False,
            "production_directory_modified": False,
            "formal_dataset_csv_modified": False,
        },
    }
    write_json(OUT / "remap/person_fallen_v3_remap_audit.json", audit)
    print(json.dumps({"V3_REMAP_STATUS": "PASS", "counts": counts, "p4d_accounting": p4d_accounting}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
