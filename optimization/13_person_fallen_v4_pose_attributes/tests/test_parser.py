#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_v4_diagnostic as runner  # noqa: E402


class ParserTests(unittest.TestCase):
    def valid(self):
        return {
            "person_visible": "yes", "pose": "floor_sitting",
            "torso_orientation": "upright", "torso_ground_contact": "partial",
            "head_shoulders_above_hips": "yes", "support_surface": "floor",
            "explicit_work_evidence": "no", "visual_quality": "clear",
            "evidence": "person visibly seated",
        }

    def test_strict_outer_response(self):
        value, error = runner.parse_outer(json.dumps({"done": True, "response": json.dumps(self.valid())}))
        self.assertEqual(error, "")
        self.assertEqual(value["pose"], "floor_sitting")

    def test_extra_key_fails(self):
        value = self.valid(); value["alarm"] = True
        parsed, error = runner.parse_outer(json.dumps({"done": True, "response": json.dumps(value)}))
        self.assertIsNone(parsed)
        self.assertIn("STRICT_PARSE_FAILURE", error)

    def test_invalid_enum_fails(self):
        value = self.valid(); value["pose"] = "sitting_maybe"
        parsed, error = runner.parse_outer(json.dumps({"done": True, "response": json.dumps(value)}))
        self.assertIsNone(parsed)
        self.assertIn("STRICT_PARSE_FAILURE", error)

    def test_incomplete_outer_response_fails(self):
        parsed, error = runner.parse_outer(json.dumps({"done": False, "response": json.dumps(self.valid())}))
        self.assertIsNone(parsed)
        self.assertEqual(error, "OUTER_RESPONSE_NOT_COMPLETE")


if __name__ == "__main__":
    unittest.main()
