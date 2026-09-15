#!/usr/bin/env python3
"""Bounded three-frame confirmation for robot-side posture decisions."""

from __future__ import annotations

from collections import Counter
from typing import Iterable


FRAME_DECISIONS = {
    "ALERT_GROUND_LYING",
    "ATTENTION_NEAR_GROUND",
    "NO_ALERT_NORMAL_POSE",
    "RECHECK_VISUAL_UNCERTAIN",
}


def temporal_decision(frames: Iterable[str]) -> dict[str, object]:
    values = list(frames)
    if not 1 <= len(values) <= 3 or any(item not in FRAME_DECISIONS for item in values):
        raise ValueError("temporal window must contain one to three valid frame decisions")
    counts = Counter(values)
    if counts["ALERT_GROUND_LYING"] >= 2:
        state = "ALARM_CONFIRMED"
    elif counts["NO_ALERT_NORMAL_POSE"] >= 2:
        state = "CLEAR_CONFIRMED"
    elif counts["ATTENTION_NEAR_GROUND"] >= 2:
        state = "ATTENTION_CONFIRMED"
    elif len(values) < 3:
        state = "RECAPTURE_REQUIRED"
    else:
        state = "ESCALATE_AMBIGUOUS"
    return {"temporal_state": state, "frame_count": len(values), "counts": dict(counts)}

