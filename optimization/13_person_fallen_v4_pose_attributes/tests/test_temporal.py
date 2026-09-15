#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "policy"))
from temporal_recheck import temporal_decision  # noqa: E402


class TemporalTests(unittest.TestCase):
    def test_two_alert_frames_confirm(self):
        result = temporal_decision(["ALERT_GROUND_LYING", "RECHECK_VISUAL_UNCERTAIN", "ALERT_GROUND_LYING"])
        self.assertEqual(result["temporal_state"], "ALARM_CONFIRMED")

    def test_two_clear_frames_confirm(self):
        result = temporal_decision(["NO_ALERT_NORMAL_POSE", "NO_ALERT_NORMAL_POSE"])
        self.assertEqual(result["temporal_state"], "CLEAR_CONFIRMED")

    def test_one_frame_requires_recapture(self):
        result = temporal_decision(["ALERT_GROUND_LYING"])
        self.assertEqual(result["temporal_state"], "RECAPTURE_REQUIRED")

    def test_three_way_conflict_escalates(self):
        result = temporal_decision([
            "ALERT_GROUND_LYING", "NO_ALERT_NORMAL_POSE", "RECHECK_VISUAL_UNCERTAIN"
        ])
        self.assertEqual(result["temporal_state"], "ESCALATE_AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()

