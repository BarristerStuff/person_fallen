import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAN = ROOT / "manifests"
AUDIT = ROOT / "reports/source_audit.json"
BUILD = ROOT / "tools/build_manifests.py"


def load_csv(name):
    with (MAN / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class ManifestTests(unittest.TestCase):
    def test_pilot_shape_and_strata(self):
        rows = load_csv("pilot156.csv")
        self.assertEqual(len(rows), 156)
        self.assertEqual(len({r["item_id"] for r in rows}), 156)
        self.assertEqual({r["evaluation_stratum"] for r in rows}, {"normal_negative", "ground_lying", "auxiliary_attention"})
        self.assertEqual(sum(r["evaluation_stratum"] == "normal_negative" for r in rows), 55)
        self.assertEqual(sum(r["evaluation_stratum"] == "ground_lying" for r in rows), 60)
        self.assertEqual(sum(r["evaluation_stratum"] == "auxiliary_attention" for r in rows), 41)
        self.assertEqual(sum(r["taxonomy"] == "multi_person_one_lying" for r in rows), 5)
        self.assertTrue(all(r["expected_outcome"] == "ALERT_GROUND_LYING" for r in rows if r["taxonomy"] == "multi_person_one_lying"))
        self.assertEqual(len({r["group_id"] for r in rows if r["taxonomy"] == "multi_person_one_lying"}), 1)

    def test_required_fields_and_view_bindings(self):
        rows = load_csv("pilot156.csv") + load_csv("regression1.csv")
        required = {"item_id", "source_split", "expected_outcome", "ground_truth", "taxonomy", "group_id", "image_path", "prompt_path", "image_sha256", "prompt_sha256", "full_view_sha256", "crop_view_sha256", "person_detected", "view_count", "operational_id", "evaluation_stratum", "experiment_role", "phase", "request_id"}
        for row in rows:
            self.assertTrue(required <= row.keys())
            self.assertEqual(row["view_count"], "2")
            for key in ("image_sha256", "prompt_sha256", "full_view_sha256", "crop_view_sha256"):
                self.assertTrue(row[key])

    def test_regression_exact_binding(self):
        rows = load_csv("regression1.csv")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["operational_id"], "PFV4_SCREEN_0066")
        self.assertEqual(row["item_id"], "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05")
        self.assertEqual(row["expected_outcome"], row["expected_high_priority"])
        self.assertEqual(row["expected_outcome"], "ALERT_GROUND_LYING")
        self.assertEqual(row["experiment_role"], "KNOWN_FAILURE_DEVELOPMENT_REGRESSION")

    def test_audit_scope_and_counts(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["counts"]["total"], 157)
        for key in ("network", "model", "ollama", "val_holdout_read", "human_review", "localization_validation"):
            self.assertFalse(audit["scope"][key])

    def test_refuses_overwrite(self):
        result = subprocess.run([sys.executable, str(BUILD)], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)


if __name__ == "__main__":
    unittest.main()
