#!/usr/bin/env python3
"""Deterministic mapping from visible pose attributes to frame decisions."""

from __future__ import annotations

from typing import Any


POSES = {
    "standing", "walking", "chair_sitting", "floor_sitting", "kneeling",
    "squat_crouch", "bending", "crawling", "pushup_plank", "supine",
    "side_lying", "prone", "curled_lying", "other_near_ground", "unknown",
}
ENUMS = {
    "person_visible": {"yes", "no", "uncertain"},
    "pose": POSES,
    "torso_orientation": {"upright", "inclined", "horizontal", "unknown"},
    "torso_ground_contact": {"none", "partial", "broad", "unknown"},
    "head_shoulders_above_hips": {"yes", "no", "unknown"},
    "support_surface": {"floor", "chair", "bed_sofa", "unknown"},
    "explicit_work_evidence": {"yes", "no", "unknown"},
    "visual_quality": {"clear", "insufficient"},
}
EXPECTED_KEYS = {*ENUMS, "evidence"}
NO_ALERT_POSES = {
    "standing", "walking", "chair_sitting", "kneeling", "squat_crouch", "bending"
}
LYING_POSES = {"supine", "side_lying", "prone", "curled_lying"}
ATTENTION_POSES = {"crawling", "pushup_plank", "other_near_ground"}


class AttributeContractError(ValueError):
    """Raised when model attributes violate the frozen contract."""


def validate_attributes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS:
        raise AttributeContractError("strict attribute keys mismatch")
    normalized: dict[str, str] = {}
    for key, allowed in ENUMS.items():
        item = value.get(key)
        if not isinstance(item, str) or item not in allowed:
            raise AttributeContractError(f"invalid {key}: {item!r}")
        normalized[key] = item
    evidence = value.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise AttributeContractError("evidence must be a non-empty string")
    normalized["evidence"] = evidence.strip()
    return normalized


def decision(name: str, reason: str) -> dict[str, str]:
    return {"frame_decision": name, "reason_code": reason}


def map_attributes(raw: Any, *, detector_person_found: bool = True) -> dict[str, str]:
    """Map validated attributes without probabilistic or text-evidence rules."""
    try:
        value = validate_attributes(raw)
    except AttributeContractError as exc:
        return decision("RECHECK_VISUAL_UNCERTAIN", f"ATTRIBUTE_CONTRACT_ERROR:{exc}")

    if not detector_person_found:
        return decision("RECHECK_VISUAL_UNCERTAIN", "NO_RELIABLE_PERSON_CROP")
    if value["person_visible"] != "yes" or value["visual_quality"] != "clear":
        return decision("RECHECK_VISUAL_UNCERTAIN", "VISIBILITY_OR_QUALITY_INSUFFICIENT")
    if value["support_surface"] == "bed_sofa":
        return decision("NO_ALERT_NORMAL_POSE", "NORMAL_REST_SUPPORT")
    if value["explicit_work_evidence"] == "yes":
        return decision("NO_ALERT_NORMAL_POSE", "EXPLICIT_WORK_CONTEXT")

    pose = value["pose"]
    orientation = value["torso_orientation"]
    contact = value["torso_ground_contact"]
    head_above = value["head_shoulders_above_hips"]

    if pose == "floor_sitting":
        if head_above == "yes" and orientation in {"upright", "inclined"} and contact in {"none", "partial"}:
            return decision("NO_ALERT_NORMAL_POSE", "CLEAR_FLOOR_SITTING")
        return decision("RECHECK_VISUAL_UNCERTAIN", "FLOOR_SITTING_ATTRIBUTE_CONFLICT")

    if pose in NO_ALERT_POSES:
        if orientation == "horizontal" and contact == "broad":
            return decision("RECHECK_VISUAL_UNCERTAIN", "NORMAL_POSE_ATTRIBUTE_CONFLICT")
        return decision("NO_ALERT_NORMAL_POSE", f"CLEAR_NORMAL_POSE:{pose}")

    if pose in LYING_POSES:
        return decision("ALERT_GROUND_LYING", f"CLEAR_LYING_POSE:{pose}")
    if pose in ATTENTION_POSES:
        return decision("ATTENTION_NEAR_GROUND", f"CLEAR_NEAR_GROUND_POSE:{pose}")
    if orientation == "horizontal" and contact == "broad":
        return decision("ALERT_GROUND_LYING", "HORIZONTAL_BROAD_TORSO_CONTACT")
    return decision("RECHECK_VISUAL_UNCERTAIN", "UNRESOLVED_ATTRIBUTES")

