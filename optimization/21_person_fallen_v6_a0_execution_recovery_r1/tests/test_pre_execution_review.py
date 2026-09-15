import json
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "tools/recovery_runner.py").read_text()
PLAN = json.loads((ROOT / "protocol/execution_plan.json").read_text())
REMAINING = json.loads((ROOT / "manifests/full_dev_remaining.json").read_text())
COMBINED = json.loads((ROOT / "manifests/full_dev_combined.json").read_text())


class PreExecutionReview(unittest.TestCase):
    def test_budget_and_manifest_accounting(self):
        budget = PLAN["budget"]
        self.assertEqual(budget["pilot"] + budget["regression"] + budget["full_dev_remaining"], 437)
        self.assertEqual(len(REMAINING), 280)
        self.assertEqual(len(COMBINED), 436)
        self.assertEqual(sum(r.get("phase") == "pilot_reused" for r in COMBINED), 156)
        self.assertEqual(sum(r.get("result_source") == "REUSE_V6_PILOT" for r in COMBINED), 156)
        self.assertEqual(sum(r.get("result_source") == "NEW_INFERENCE" for r in COMBINED), 280)
        self.assertEqual(Counter(r["evaluation_stratum"] for r in REMAINING),
                         Counter({"normal_negative": 175, "ground_lying": 85, "visual_uncertain": 20}))
        for key in ("request_id", "item_id", "operational_id"):
            self.assertEqual(len({r[key] for r in REMAINING}), 280)
            self.assertEqual(len({r[key] for r in COMBINED}), 436)

    def test_required_stage_artifacts_are_missing_in_21(self):
        # This is an audit assertion: recovery_runner references these paths, but they are
        # not present in the current 21 recovery directory.
        for rel in (
            "freeze/RECOVERY_FREEZE.json",
            "freeze/RECOVERY_FREEZE.sha256",
            "eval/pilot/summary.json",
            "eval/regression/summary.json",
        ):
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_full_is_not_gated_by_full_pilot_reuse_and_has_wrong_summary_phase(self):
        self.assertIn("load_manifest(phase)", RUNNER)
        self.assertIn("full_dev_remaining.json", RUNNER)
        self.assertNotIn("full_dev_combined.json", RUNNER)
        self.assertNotIn("REUSE_V6_PILOT", RUNNER)
        self.assertIn("summarize('pilot' if phase=='pilot' else 'regression',rows,outputs,reqs)", RUNNER)

    def test_early_stop_is_declared_but_not_enforced(self):
        self.assertIn("early-stop", RUNNER)
        self.assertNotRegex(RUNNER, r"early_stop|normal_recheck_total|ground_non_alert|auxiliary_alert")

    def test_no_retry_and_completion_unknown_are_fail_closed(self):
        self.assertIn("V6_A0_PROTOCOL_INCOMPLETE_NO_RETRY", RUNNER)
        self.assertIn("res['completion_unknown']", RUNNER)
        plan_text = (ROOT / "protocol/execution_plan.json").read_text()
        self.assertIn('"resend_completion_unknown":false', plan_text)

    def test_jsonl_writer_is_one_record_per_line_and_runner_emits_claim_completion_output(self):
        contracts = (ROOT / "adapters/contracts.py").read_text()
        self.assertIn("json.dumps(o,ensure_ascii=False,allow_nan=False)+'\\n'", contracts)
        self.assertEqual(RUNNER.count("append_jsonl(d/'request_events.jsonl',"), 2)
        self.assertIn("append_jsonl(d/'output.jsonl',rec)", RUNNER)
        self.assertIn("'done':True", RUNNER)
        self.assertIn("'done_reason':'stop'", RUNNER)

    def test_cli_is_not_offline_safe_and_fake_transport_is_not_a_cli_mode(self):
        self.assertIn("curl", RUNNER)
        self.assertIn("preflight()", RUNNER)
        self.assertIn("def run_phase(phase,transport=None,run_root=None,freeze_override=None)", RUNNER)
        # argparse exposes only phase; transport injection is programmatic, not CLI-selectable.
        self.assertEqual(re.findall(r"p\.add_argument\([^\n]+", RUNNER)[-1],
                         "p.add_argument('phase',choices=['pilot','regression','full']);a=p.parse_args()")

    def test_protocol_parser_rejects_incomplete_or_wrong_model(self):
        import sys
        sys.path.insert(0, str(ROOT / "adapters"))
        from contracts import parse
        valid = {
            "done": True,
            "done_reason": "stop",
            "model": "qwen3.5:4b",
            "response": json.dumps({"scene_coverage": "complete", "people": []}),
        }
        parse(json.dumps(valid).encode())
        for patch in ({"done": False}, {"done_reason": "length"}, {"model": "wrong"}):
            bad = dict(valid)
            bad.update(patch)
            with self.assertRaises(ValueError):
                parse(json.dumps(bad).encode())

    def test_declared_fake_e2e_is_offline_and_only_covers_157_requests(self):
        fake = (ROOT / "tools/run_fake_e2e.py").read_text()
        self.assertIn("run_phase('pilot',fake", fake)
        self.assertIn("run_phase('regression',fake", fake)
        self.assertNotIn("run_phase('full'", fake)
        self.assertIn("'requests':157", fake)
        self.assertNotIn("curl", fake)
        self.assertNotIn("/api/", fake)

    def test_fake_e2e_does_not_prove_regression_dependency_when_freeze_override_is_used(self):
        self.assertIn("if phase=='regression' and freeze_override is None", RUNNER)
        fake = (ROOT / "tools/run_fake_e2e.py").read_text()
        self.assertIn("rr.run_phase('regression',fake,Path(td)/'regression',f)", fake)

    def test_full_path_is_not_a_full_budget_or_gate_execution(self):
        self.assertIn("else ROOT/'manifests/full_dev_remaining.json'", RUNNER)
        self.assertIn("'gate':'NOT_EVALUATED_PARTIAL'", RUNNER)
        self.assertNotIn("full_dev_combined", RUNNER)
        self.assertNotIn("early_stop", RUNNER)

    def test_val_holdout_and_detector_budgets_are_zero_and_not_in_manifests(self):
        self.assertEqual(PLAN["budget"]["val"], 0)
        self.assertEqual(PLAN["budget"]["holdout"], 0)
        self.assertEqual(PLAN["budget"]["detector"], 0)
        self.assertFalse(PLAN["val_holdout_allowed"])
        for row in REMAINING:
            self.assertEqual(row["phase"], "full_dev_remaining")
            self.assertEqual(row["result_source"], "NEW_INFERENCE")


if __name__ == "__main__":
    unittest.main()
