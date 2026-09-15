#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_v4_full_dev as runner  # noqa: E402


def row(gt, decision_key, expected, stratum, taxonomy):
    decision = {
        "alert": "ALERT_GROUND_LYING",
        "no_alert": "NO_ALERT_NORMAL_POSE",
        "recheck": "RECHECK_VISUAL_UNCERTAIN",
        "attention": "ATTENTION_NEAR_GROUND",
    }[decision_key]
    return {
        "ground_truth": gt,
        "predicted_label": runner.predicted_label(decision),
        "expected_v4_outcome": expected,
        "metric_stratum": stratum,
        "taxonomy": taxonomy,
        "frame_decision": decision,
        "strict_json_ok": True,
        "exact_expected_outcome": False,
        "inference_source": "NEW_MODEL_REQUEST",
        "latency_seconds": 1.0,
        "pose": "unknown",
    }


class FullDevMetricTests(unittest.TestCase):
    def test_uncertain_is_conservatively_an_error_for_determinate_gt(self):
        rows = [
            row("positive", "alert", "ALERT_GROUND_LYING", "positive", "lying_ok"),
            row("positive", "attention", "ATTENTION_NEAR_GROUND", "positive", "crawl_ok"),
            row("positive", "recheck", "ALERT_GROUND_LYING", "positive", "lying_recheck"),
            row("negative", "no_alert", "NO_ALERT_NORMAL_POSE", "ordinary_negative", "walk_ok"),
            row("negative", "recheck", "NO_ALERT_NORMAL_POSE", "hard_negative", "sit_recheck"),
            row("uncertain", "recheck", "RECHECK_VISUAL_UNCERTAIN", "uncertain", "ambiguous"),
        ]
        rows[0]["exact_expected_outcome"] = True
        rows[1]["exact_expected_outcome"] = True
        rows[3]["exact_expected_outcome"] = True
        rows[5]["exact_expected_outcome"] = True
        plan = {"gate": {
            "precision_min": 0.0, "recall_min": 0.0,
            "hard_negative_fpr_max": 1.0, "ordinary_negative_fpr_max": 1.0,
            "strict_json_success_min": 1.0, "detector_coverage_min": 0.0,
        }}
        result = runner.summarize(rows, plan, {"person_detection_coverage": 1.0}, 0, 6)
        metrics = result["metrics"]
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["tn"], metrics["fn"]), (2, 1, 1, 1))
        self.assertEqual(metrics["hard_negative_fp"], 1)
        self.assertEqual(metrics["ordinary_negative_fp"], 0)
        self.assertEqual(metrics["determinate_recheck_count"], 2)

    def test_binary_mapping_keeps_attention_positive(self):
        self.assertEqual(runner.predicted_label("ATTENTION_NEAR_GROUND"), "positive")
        self.assertEqual(runner.predicted_label("ALERT_GROUND_LYING"), "positive")
        self.assertEqual(runner.predicted_label("NO_ALERT_NORMAL_POSE"), "negative")
        self.assertEqual(runner.predicted_label("RECHECK_VISUAL_UNCERTAIN"), "uncertain")

    def test_cache_requires_identical_view_hashes(self):
        current = [{
            "item_id": "x", "image_sha256": "source", "full_view_sha256": "full",
            "crop_view_sha256": "crop", "person_detected": "true", "view_count": "2",
        }]
        cache = {"x": {"crop": dict(current[0])}}
        self.assertEqual(runner.verify_cache_compatibility(current, cache, 1), 1)
        current[0]["crop_view_sha256"] = "changed"
        with self.assertRaises(RuntimeError):
            runner.verify_cache_compatibility(current, cache, 1)


if __name__ == "__main__":
    unittest.main()
