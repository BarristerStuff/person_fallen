#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "policy"))
from deterministic_policy import map_attributes  # noqa: E402


def attributes(**changes):
    value = {
        "person_visible": "yes", "pose": "floor_sitting",
        "torso_orientation": "inclined", "torso_ground_contact": "partial",
        "head_shoulders_above_hips": "yes", "support_surface": "floor",
        "explicit_work_evidence": "no", "visual_quality": "clear",
        "evidence": "visible posture facts",
    }
    value.update(changes)
    return value


class PolicyTests(unittest.TestCase):
    def test_leaning_floor_sitting_is_no_alert(self):
        self.assertEqual(map_attributes(attributes())["frame_decision"], "NO_ALERT_NORMAL_POSE")

    def test_floor_sitting_conflict_rechecks(self):
        value = attributes(torso_orientation="horizontal", torso_ground_contact="broad")
        self.assertEqual(map_attributes(value)["frame_decision"], "RECHECK_VISUAL_UNCERTAIN")

    def test_clear_lying_alerts(self):
        value = attributes(pose="side_lying", torso_orientation="horizontal",
                           torso_ground_contact="broad", head_shoulders_above_hips="no")
        self.assertEqual(map_attributes(value)["frame_decision"], "ALERT_GROUND_LYING")

    def test_crawling_is_lower_priority_attention(self):
        value = attributes(pose="crawling", torso_orientation="inclined",
                           torso_ground_contact="none", head_shoulders_above_hips="no")
        self.assertEqual(map_attributes(value)["frame_decision"], "ATTENTION_NEAR_GROUND")

    def test_explicit_maintenance_suppresses(self):
        value = attributes(pose="prone", torso_orientation="horizontal",
                           torso_ground_contact="broad", explicit_work_evidence="yes")
        self.assertEqual(map_attributes(value)["frame_decision"], "NO_ALERT_NORMAL_POSE")

    def test_missing_crop_rechecks(self):
        self.assertEqual(map_attributes(attributes(), detector_person_found=False)["frame_decision"],
                         "RECHECK_VISUAL_UNCERTAIN")

    def test_extra_key_fails_closed(self):
        value = attributes(extra="bad")
        self.assertEqual(map_attributes(value)["frame_decision"], "RECHECK_VISUAL_UNCERTAIN")


if __name__ == "__main__":
    unittest.main()

