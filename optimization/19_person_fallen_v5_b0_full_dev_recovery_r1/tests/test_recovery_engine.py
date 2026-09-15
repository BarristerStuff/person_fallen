"""Offline recovery tests. No network, Ollama, VAL/Holdout, or detector calls."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "adapters"))
import full_dev_metrics as metrics  # noqa: E402
import recovery_runner as runner  # noqa: E402
from reuse_v5_b0 import load_reuse_records  # noqa: E402


FULL = json.loads((ROOT / "manifests/full_dev_manifest.json").read_text())
NEW = json.loads((ROOT / "manifests/new321_manifest.json").read_text())
REUSE = json.loads((ROOT / "manifests/reuse115_records.json").read_text())


def fake_parsed(stratum: str) -> dict:
    person = {
        "person_id": 1,
        "bbox_1000": [100, 100, 500, 900],
        "person_visible": "yes",
        "pose": "floor_sitting",
        "torso_orientation": "upright",
        "torso_ground_contact": "partial",
        "head_shoulders_above_hips": "yes",
        "support_surface": "floor",
        "explicit_work_evidence": "no",
        "visual_quality": "clear",
        "evidence": "Offline fake transport visible person.",
    }
    if stratum == "ground_lying":
        person.update(pose="supine", torso_orientation="horizontal", torso_ground_contact="broad", head_shoulders_above_hips="no")
    elif stratum == "auxiliary_attention":
        person.update(pose="crawling", torso_orientation="inclined", torso_ground_contact="partial", head_shoulders_above_hips="no")
    elif stratum == "visual_uncertain":
        person.update(pose="unknown", torso_orientation="unknown", torso_ground_contact="unknown", head_shoulders_above_hips="unknown", support_surface="unknown", visual_quality="insufficient")
    return {"scene_coverage": "complete", "people": [person]}


def fake_output(row: dict, decision: str, *, result_source: str = "NEW_INFERENCE") -> dict:
    parsed = fake_parsed(row["evaluation_stratum"])
    parsed["people"][0]["pose"] = "floor_sitting" if decision == metrics.NORMAL else parsed["people"][0]["pose"]
    pdec = decision
    return {
        "item_id": row["item_id"], "request_id": row["request_id"], "operational_id": row["operational_id"],
        "evaluation_stratum": row["evaluation_stratum"], "result_source": result_source,
        "inference_source": result_source, "source_image_sha256": row["image_sha256"], "full_view_sha256": row["full_view_sha256"],
        "crop_view_sha256": row["crop_view_sha256"], "source_binding_ok": True, "strict_json_ok": True,
        "latency_seconds": 1.0, "image_decision": decision, "image_reason": "offline fixture",
        "parsed": parsed, "person_decisions": [{"person_id": 1, "decision": pdec, "reason": "offline fixture"}],
    }


def request_record(output: dict, *, state: str = "completed") -> dict:
    return {**output, "state": state, "done": state == "completed", "done_reason": "stop" if state == "completed" else None,
            "completion_unknown": False, "transport_error": None, "raw_response_sha256": "a" * 64,
            "claimed_timestamp": "2026-09-09T00:00:00+00:00", "received_timestamp": "2026-09-09T00:00:01+00:00",
            "completed_timestamp": "2026-09-09T00:00:02+00:00", "eval_count": 100}


class RecoveryMetricsTests(unittest.TestCase):
    def test_unified_manifest_and_counts(self):
        self.assertEqual(metrics.validate_manifest(FULL), [])
        self.assertEqual(len(FULL), 436)
        self.assertEqual(len(REUSE), 115)
        self.assertEqual(len(NEW), 321)
        from collections import Counter
        self.assertEqual(Counter(row["evaluation_stratum"] for row in FULL), metrics.EXPECTED_STRATA)
        self.assertEqual(sum(row["taxonomy"] == "floor_sitting" for row in FULL), 55)
        self.assertNotIn("v5_stratum", FULL[0])
        self.assertNotIn("experiment_stratum", FULL[0])
        self.assertNotIn("P4D_PLAN::PF_P4D_POS_CURLED_G003_V05", {row["item_id"] for row in FULL})

    def test_reuse_is_v5_b0_not_v4(self):
        direct, freeze = load_reuse_records()
        self.assertEqual(direct, REUSE)
        self.assertTrue(all(row["result_source"] == "REUSE_V5_B0_PILOT" for row in REUSE))
        self.assertTrue(all(row["inference_source"] == "REUSE_V5_B0_PILOT" for row in REUSE))
        self.assertEqual(freeze["candidate"], "V5-B0-TARGET-ATTRIBUTES")

    def test_pending_ground_not_counted_as_non_alert(self):
        partial = metrics.summarize_partial(FULL, REUSE, [], attempted_count=0)
        self.assertEqual(partial["ground_lying"]["observed"], 60)
        self.assertEqual(partial["ground_lying"]["pending"], 85)
        self.assertEqual(partial["ground_lying"]["NO_ALERT"], 0)
        self.assertEqual(partial["ground_lying"]["ATTENTION"], 0)
        self.assertEqual(partial["max_possible_final_ground_alert"], 145)
        self.assertIsNone(partial["early_stop_trigger"])
        self.assertEqual(partial["FULL_DEV_GATE"], "NOT_EVALUATED_PARTIAL")

    def test_normal_recheck_23_no_stop_24_stop_including_reuse_five(self):
        outputs = list(REUSE)
        requests = []
        normal = [row for row in NEW if row["evaluation_stratum"] == "normal_negative"]
        for row in normal[:18]:
            out = fake_output(row, metrics.RECHECK)
            outputs.append(out); requests.append(request_record(out))
        self.assertIsNone(metrics.early_stop_trigger(FULL, outputs))
        out = fake_output(normal[18], metrics.RECHECK); outputs.append(out); requests.append(request_record(out))
        self.assertEqual(metrics.early_stop_trigger(FULL, outputs), "B_NORMAL_NEGATIVE_RECHECK_REACHED_24")

    def test_normal_alert_stops(self):
        row = next(row for row in NEW if row["evaluation_stratum"] == "normal_negative")
        self.assertEqual(metrics.early_stop_trigger(FULL, REUSE + [fake_output(row, metrics.ALERT)]), "A_DETERMINATE_NEGATIVE_ALERT")

    def test_ground_nonalert_threshold_uses_observed_values(self):
        grounds = [row for row in FULL if row["evaluation_stratum"] == "ground_lying"]
        # 137 observed alerts + 7 observed rechecks + 1 pending: max possible alert is 138; no stop.
        outputs = [fake_output(row, metrics.ALERT) for row in grounds[:137]]
        outputs += [fake_output(row, metrics.RECHECK) for row in grounds[137:144]]
        self.assertIsNone(metrics.early_stop_trigger(FULL, outputs))
        outputs.append(fake_output(grounds[144], metrics.RECHECK))
        self.assertEqual(metrics.early_stop_trigger(FULL, outputs), "D_GROUND_NON_ALERT_RECALL_IMPOSSIBLE")

    def test_ground_noalert_attention_and_aux_alert_stop(self):
        ground = next(row for row in NEW if row["evaluation_stratum"] == "ground_lying")
        aux = next(row for row in NEW if row["evaluation_stratum"] == "auxiliary_attention")
        self.assertEqual(metrics.early_stop_trigger(FULL, [*REUSE, fake_output(ground, metrics.NORMAL)]), "C_GROUND_NO_ALERT_OR_ATTENTION")
        self.assertEqual(metrics.early_stop_trigger(FULL, [*REUSE, fake_output(aux, metrics.ALERT)]), "E_AUXILIARY_HIGH_PRIORITY_ALERT")

    def test_partial_invalid_and_complete_gate_not_pass(self):
        row = next(row for row in NEW if row["evaluation_stratum"] == "normal_negative")
        out = fake_output(row, metrics.NORMAL)
        bad = copy.deepcopy(out); bad["source_binding_ok"] = False
        part = metrics.summarize_partial(FULL, REUSE + [bad], [request_record(bad)], attempted_count=1)
        self.assertTrue(part["validation_errors"])
        self.assertEqual(part["FULL_DEV_GATE"], "NOT_EVALUATED_PARTIAL")
        incomplete = metrics.summarize_complete(FULL, REUSE + [out], [request_record(out)])
        self.assertNotEqual(incomplete["FULL_DEV_GATE"], "PASS")


class RecoveryRunnerTests(unittest.TestCase):
    def test_fake_transport_complete_e2e_nested_parent_and_jsonl(self):
        calls = []
        def transport(payload, request_id, row):
            calls.append((payload, request_id, row["item_id"]))
            outer = {"model": runner.MODEL, "done": True, "done_reason": "stop", "eval_count": 100, "response": json.dumps(fake_parsed(row["evaluation_stratum"]), ensure_ascii=False)}
            return {"http_status": 200, "raw": json.dumps(outer, ensure_ascii=False).encode(), "latency_seconds": .001, "completion_unknown": False, "transport_error": None}
        with tempfile.TemporaryDirectory(prefix="pf_recovery_fake_", dir="/tmp") as td:
            target = Path(td) / "nested/eval/full_dev"
            with contextlib.redirect_stdout(io.StringIO()):
                result = runner.execute_full_dev(output_run_dir=target, transport=transport, preflight=None, enforce_recovery_freeze=False)
            self.assertEqual(len(calls), 321)
            self.assertEqual(result["FULL_DEV_GATE"], "PASS")
            lines = (target / "output.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 436)
            self.assertTrue(all(isinstance(json.loads(line), dict) for line in lines))
            self.assertTrue((target / "requests").is_dir())
            self.assertTrue((target / "COMPLETION_LOCK.json").is_file())
            self.assertFalse((target / "requests" / "V5_B0_FULLDEV_EXTENSION_0001" / "response.raw").read_bytes() == b"")
            payload = json.loads(calls[0][0])
            serialized = json.dumps(payload)
            self.assertNotIn("taxonomy", serialized)
            self.assertNotIn("item_id", serialized)
            self.assertNotIn(NEW[0]["item_id"], serialized)
            self.assertNotIn(NEW[0]["image_path"], serialized)
            self.assertNotIn(NEW[0]["ground_truth"], serialized)
            self.assertNotIn(NEW[0]["expected_v4_outcome"], serialized)

    def test_runner_irreversible_recheck_early_stop_persists_partial_only(self):
        calls = []
        def transport(payload, request_id, row):
            calls.append(request_id)
            person = {"person_id": 1, "bbox_1000": None, "person_visible": "uncertain", "pose": "unknown", "torso_orientation": "unknown", "torso_ground_contact": "unknown", "head_shoulders_above_hips": "unknown", "support_surface": "unknown", "explicit_work_evidence": "unknown", "visual_quality": "insufficient", "evidence": "offline uncertain"}
            outer = {"model": runner.MODEL, "done": True, "done_reason": "stop", "eval_count": 50, "response": json.dumps({"scene_coverage": "complete", "people": [person]})}
            return {"http_status": 200, "raw": json.dumps(outer).encode(), "latency_seconds": .001, "completion_unknown": False, "transport_error": None}
        with tempfile.TemporaryDirectory(prefix="pf_recovery_early_", dir="/tmp") as td:
            target = Path(td) / "nested/full_dev"
            with self.assertRaises(runner.EarlyStop) as caught:
                with contextlib.redirect_stdout(io.StringIO()): runner.execute_full_dev(output_run_dir=target, transport=transport, preflight=None, enforce_recovery_freeze=False)
            self.assertEqual(caught.exception.trigger, "B_NORMAL_NEGATIVE_RECHECK_REACHED_24")
            self.assertEqual(len(calls), 19)
            stop = json.loads((target / "EARLY_STOP.json").read_text())
            partial = json.loads((target / "partial_metrics.json").read_text())
            self.assertEqual(stop["new_requests_claimed"], 19)
            self.assertEqual(stop["new_requests_not_started"], 302)
            self.assertEqual(partial["normal_negative"]["RECHECK"], 24)
            self.assertEqual(partial["ground_lying"]["observed"], 60)
            self.assertEqual(partial["ground_lying"]["pending"], 85)
            self.assertFalse((target / "COMPLETION_LOCK.json").exists())
            self.assertEqual(len((target / "output.jsonl").read_text().splitlines()), 134)

    def test_protocol_failure_no_retry_no_completion_lock(self):
        calls = []
        def fail(payload, request_id, row):
            calls.append(request_id)
            return {"http_status": None, "raw": b"partial", "latency_seconds": .001, "completion_unknown": True, "transport_error": "fake"}
        with tempfile.TemporaryDirectory(prefix="pf_recovery_fail_", dir="/tmp") as td:
            target = Path(td) / "nested/full_dev"
            with self.assertRaises(runner.ProtocolIncomplete):
                with contextlib.redirect_stdout(io.StringIO()): runner.execute_full_dev(output_run_dir=target, transport=fail, preflight=None, enforce_recovery_freeze=False)
            self.assertEqual(len(calls), 1)
            self.assertFalse((target / "COMPLETION_LOCK.json").exists())
            self.assertTrue((target / "PROTOCOL_INCOMPLETE.json").exists())
            self.assertTrue((target / "requests" / calls[0] / "response.raw").read_bytes() == b"partial")
            with self.assertRaises(ValueError): runner.execute_full_dev(output_run_dir=target, transport=fail, preflight=None, enforce_recovery_freeze=False)
            self.assertEqual(len(calls), 1)

    def test_ps_snapshot_not_used_as_hard_gate(self):
        tags = {"models": [{"name": runner.MODEL, "digest": runner.DIGEST}]}
        responses = {"tags": json.dumps(tags).encode(), "version": b'{"version":"0.23.2"}', "ps": b'{"models":[]}' }
        calls = []
        def fake_run(cmd, **kwargs):
            suffix = cmd[-1].split("/api/")[-1]; calls.append(suffix)
            class Result: stdout = responses[suffix]
            return Result()
        with patch.object(runner.subprocess, "run", side_effect=fake_run):
            result = runner.check_runtime_preflight()
        self.assertEqual(calls, ["tags", "version", "ps"])
        self.assertEqual(result["status"], "PASS")

    def test_forbidden_stages_rejected_without_network(self):
        for stage in ["val", "holdout", "screen", "full_dev_extension", "full_dev436"]:
            with patch.object(runner, "check_runtime_preflight", side_effect=AssertionError("network must not be called")):
                with patch.object(sys, "argv", ["recovery_runner.py", stage]):
                    self.assertEqual(runner.main(), 2)

    def test_reuse_and_new_request_identity_are_disjoint(self):
        reuse_ids = {row["request_id"] for row in REUSE}
        new_ids = {row["request_id"] for row in NEW}
        self.assertFalse(reuse_ids & new_ids)
        self.assertEqual(len(reuse_ids), 115); self.assertEqual(len(new_ids), 321)

    def test_duplicate_request_id_manifest_is_rejected(self):
        bad = copy.deepcopy(FULL)
        bad[1]["request_id"] = bad[0]["request_id"]
        self.assertTrue(metrics.validate_manifest(bad))

    def test_source_split_and_gt_fields_are_not_rewritten(self):
        import csv
        source_path = ROOT.parent / "13_person_fallen_v4_pose_attributes/manifests/v4_full_dev_436.csv"
        with source_path.open(newline="") as handle:
            source = {row["item_id"]: row for row in csv.DictReader(handle)}
        reuse_items = {x["item_id"] for x in REUSE}
        for row in FULL:
            if row["item_id"] not in reuse_items:
                continue
            original = source[row["item_id"]]
            for key in ("source_split", "v3_split", "ground_truth", "taxonomy", "group_id", "image_sha256", "prompt_sha256"):
                self.assertEqual(row[key], original[key], (row["item_id"], key))
        self.assertEqual({row["v3_split"] for row in FULL}, {"V3_DEV"})
        self.assertTrue(all(row["ground_truth"] in {"positive", "negative", "uncertain"} for row in FULL))


if __name__ == "__main__":
    unittest.main()
