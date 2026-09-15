import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prep = load("v5_prepare", ROOT / "tools/prepare_v5_dev.py")
route = load("v5_route", ROOT / "policy/routing_contract.py")


class RoutingContract(unittest.TestCase):
    def test_secondary_cannot_create_alert(self):
        for primary in (route.NORMAL, route.ATTENTION, route.RECHECK):
            for secondary in route.SCENE_REVIEW_STATES:
                self.assertNotEqual(route.route_first_frame(primary, secondary), route.ALERT)

    def test_primary_alert_preserved(self):
        for secondary in route.SCENE_REVIEW_STATES:
            self.assertEqual(route.route_first_frame(route.ALERT, secondary), route.ALERT)

    def test_missing_or_uncertain_cannot_silently_clear(self):
        for secondary in (None, "uncertain"):
            self.assertEqual(route.route_first_frame(route.NORMAL, secondary), route.RECHECK)

    def test_possible_other_person_requests_reobservation(self):
        self.assertEqual(route.route_first_frame(route.NORMAL, "candidate_present"), route.RECHECK)

    def test_clear_negative_keeps_normal(self):
        self.assertEqual(route.route_first_frame(route.NORMAL, "candidate_absent"), route.NORMAL)

    def test_primary_recheck_cannot_be_cleared(self):
        self.assertEqual(route.route_first_frame(route.RECHECK, "candidate_absent"), route.RECHECK)

    def test_unknown_enums_fail(self):
        with self.assertRaises(ValueError):
            route.route_first_frame("bad", "uncertain")
        with self.assertRaises(ValueError):
            route.route_first_frame(route.NORMAL, "yes")


class MetricContract(unittest.TestCase):
    def setUp(self):
        self.source = [
            {"item_id": "ground", "ground_truth": "positive", "expected_v4_outcome": prep.ALERT, "taxonomy": "side_lying"},
            {"item_id": "sit", "ground_truth": "negative", "expected_v4_outcome": prep.NORMAL, "taxonomy": "floor_sitting"},
            {"item_id": "crawl", "ground_truth": "positive", "expected_v4_outcome": prep.ATTENTION, "taxonomy": "crawling_quadruped_support"},
            {"item_id": "uncertain", "ground_truth": "uncertain", "expected_v4_outcome": prep.RECHECK, "taxonomy": "person_unconfirmable"},
        ]
        self.pred = [{"item_id": r["item_id"], "frame_decision": prep.ALERT} for r in self.source]

    def test_attention_not_ground_lying(self):
        result = prep.summarize(self.source, self.pred)
        self.assertEqual(result["ground_lying"]["count"], 1)
        self.assertEqual(result["auxiliary_attention"]["count"], 1)

    def test_uncertain_not_determinate_negative(self):
        result = prep.summarize(self.source, self.pred)
        self.assertEqual(result["normal_negative"]["count"], 1)
        self.assertEqual(result["visual_uncertain"]["count"], 1)

    def test_floor_sitting_counts_as_negative_false_positive(self):
        result = prep.summarize(self.source, self.pred)
        self.assertEqual(result["normal_negative"]["alert_count"], 1)
        self.assertEqual(result["floor_sitting"]["alert_rate"], 1.0)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            prep.summarize(self.source, self.pred + [self.pred[0]])

    def test_incomplete_predictions_rejected(self):
        with self.assertRaises(ValueError):
            prep.summarize(self.source, self.pred[:-1])

    def test_gt_conflict_rejected(self):
        row = dict(self.source[1], expected_v4_outcome=prep.ALERT)
        with self.assertRaises(ValueError):
            prep.classify(row)


if __name__ == "__main__":
    unittest.main()
