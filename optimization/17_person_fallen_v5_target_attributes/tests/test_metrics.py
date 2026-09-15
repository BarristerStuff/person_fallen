"""Synthetic-only tests: no filesystem inputs, network, inference or policy imports.

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <R>/tests -p test_metrics.py -v
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

# Resolve exactly this experiment's module even if another tools package is loaded.
_SPEC = importlib.util.spec_from_file_location(
    "v5_offline_metrics_under_test", Path(__file__).resolve().parents[1] / "tools" / "metrics.py")
metrics = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(metrics)
ALERT, RECHECK, NORMAL, ATTENTION = metrics.DECISIONS


def person(pid=1, pose="supine"):
    return {
        "person_id": pid, "bbox_1000": [100, 200, 700, 900],
        "person_visible": "yes", "pose": pose, "torso_orientation": "horizontal",
        "torso_ground_contact": "broad", "head_shoulders_above_hips": "no",
        "support_surface": "floor", "explicit_work_evidence": "no",
        "visual_quality": "clear", "evidence": "synthetic fixture, not inference",
    }


def completed(output):
    return dict(deepcopy(output), state="completed", raw_response_sha256="a" * 64,
                claimed_timestamp="2026-09-09T01:00:00+00:00",
                received_timestamp="2026-09-09T01:00:01+00:00",
                completed_timestamp="2026-09-09T01:00:02+00:00")


def fixtures(phase="pilot", ground_alerts=57, floor_rechecks=5):
    manifests, outputs = [], []
    for i in range(1, (115 if phase == "pilot" else 1) + 1):
        ground = phase == "regression" or i <= 60
        multi = phase == "pilot" and i <= 5
        rid = f"V5_B0_{phase.upper()}_{i:04d}"
        item = metrics.REGRESSION_ITEM if phase == "regression" else f"SYNTHETIC_ITEM_{i:04d}"
        oid = metrics.REGRESSION_OPERATIONAL_ID if phase == "regression" else f"SYNTHETIC_OP_{i:04d}"
        manifests.append({
            "phase": phase, "request_id": rid, "item_id": item, "operational_id": oid,
            "group_id": "synthetic_multi_group" if multi else f"synthetic_group_{i}",
            "taxonomy": metrics.MULTI_TAXONOMY if multi else ("supine_ground_lying" if ground else "floor_sitting"),
            "ground_truth": "positive" if ground else "negative",
            "expected_v4_outcome": ALERT if ground else NORMAL,
            "experiment_stratum": "ground_lying" if ground else "normal_negative",
        })
        decision = (ALERT if i <= ground_alerts else RECHECK) if ground else (RECHECK if i <= 60 + floor_rechecks else NORMAL)
        people = [person()]
        if multi or phase == "regression":
            people.append(person(2, "standing"))
        outputs.append({
            "phase": phase, "request_id": rid, "item_id": item, "operational_id": oid,
            "source_binding_ok": True, "strict_json_ok": True, "http_status": 200,
            "parsed": {"scene_coverage": "complete", "people": people},
            "person_decisions": [
                {"person_id": p["person_id"], "decision": decision if j == 0 else NORMAL,
                 "reason": "synthetic fixture"} for j, p in enumerate(people)],
            "image_decision": decision, "image_reason": "synthetic fixture",
            "latency_seconds": float(i), "fixture_log": {"synthetic": True},
        })
    return manifests, outputs, [completed(row) for row in outputs]


def synchronize(data, i=0):
    data[2][i] = completed(data[1][i])


def set_decision(data, i, decision):
    data[1][i]["image_decision"] = decision
    data[1][i]["person_decisions"][0]["decision"] = decision
    synchronize(data, i)


class MetricsTests(unittest.TestCase):
    def summary(self, data=None, phase="pilot"):
        return metrics.summarize(phase, *(data if data is not None else fixtures(phase)))

    def assert_fail(self, data, check=None, phase="pilot"):
        result = self.summary(data, phase)
        self.assertEqual(result["gate"], "FAIL", result)
        if check:
            self.assertFalse(result["gate_checks"][check], result)
        return result

    def test_exact_boundary_pass_and_all_requested_metrics(self):
        result = self.summary()
        self.assertEqual(result["gate"], "PASS", result["validation_errors"])
        for key in ("rows", "new_model_requests", "valid_responses"):
            self.assertEqual(result[key], 115)
        self.assertEqual(result["ground_lying_count"], 60)
        self.assertEqual(result["ground_lying_ALERT_count"], 57)
        self.assertEqual(result["ground_lying_ALERT_recall"], 57 / 60)
        self.assertEqual(result["ground_lying_ALERT_RECHECK_coverage"], 1)
        self.assertEqual(result["floor_sitting_count"], 55)
        self.assertEqual(result["floor_sitting_decision_counts"], {ALERT: 0, RECHECK: 5, NORMAL: 50, ATTENTION: 0})
        self.assertEqual(result["multi_person_rows"], 5)
        self.assertEqual(result["multi_person_group_count"], 1)
        self.assertEqual(result["multi_person_ALERT_count"], 5)
        self.assertEqual([d["people_count"] for d in result["multi_person_details"]], [2] * 5)
        self.assertEqual(result["people_count_distribution"], {"1": 110, "2": 5})
        self.assertEqual(result["scene_coverage_distribution"], {"complete": 115})
        self.assertEqual(result["person_attribute_distributions"]["pose"], {"standing": 5, "supine": 115})
        for field in ("support_surface", "torso_ground_contact", "torso_orientation"):
            self.assertEqual(sum(result["person_attribute_distributions"][field].values()), 120)
        self.assertEqual(result["bbox_null_count"], 0)
        self.assertEqual(result["strict_JSON_success"], 1)
        self.assertEqual(result["source_hash_binding_success"], 1)
        self.assertEqual(result["latency_p50"], 58)
        self.assertAlmostEqual(result["latency_p95"], 109.3)
        self.assertEqual(result["OBJECT_LOCALIZATION_ACCURACY"], "UNVERIFIED")
        json.dumps(result, allow_nan=False)

    def test_56_versus_57_alerts(self):
        self.assert_fail(fixtures(ground_alerts=56), "ground_ALERT_at_least_57")
        self.assertEqual(self.summary(fixtures(ground_alerts=57))["gate"], "PASS")
        self.assertEqual(self.summary(fixtures(ground_alerts=60))["gate"], "PASS")

    def test_5_versus_6_floor_rechecks(self):
        self.assertEqual(self.summary(fixtures(floor_rechecks=5))["gate"], "PASS")
        result = self.assert_fail(fixtures(floor_rechecks=6), "floor_RECHECK_at_most_5")
        self.assertFalse(result["gate_checks"]["floor_NO_ALERT_at_least_50"])

    def test_floor_false_alert(self):
        data = fixtures()
        set_decision(data, 60, ALERT)
        self.assert_fail(data, "floor_ALERT_0")

    def test_recheck_never_counts_as_alert(self):
        result = self.summary(fixtures(ground_alerts=5))
        self.assertEqual(result["ground_lying_ALERT_count"], 5)
        self.assertEqual(result["ground_lying_ALERT_RECHECK_coverage"], 1)
        self.assertEqual(result["gate"], "FAIL")

    def test_attention_does_not_cover_ground(self):
        data = fixtures()
        set_decision(data, 59, ATTENTION)
        result = self.assert_fail(data, "ground_ALERT_RECHECK_60")
        self.assertEqual(result["ground_lying_ALERT_RECHECK_coverage"], 59 / 60)

    def test_attention_does_not_count_as_floor_normal(self):
        data = fixtures()
        set_decision(data, 65, ATTENTION)
        result = self.assert_fail(data, "floor_NO_ALERT_at_least_50")
        self.assertEqual(result["floor_sitting_NO_ALERT_count"], 49)
        self.assertEqual(result["floor_sitting_ATTENTION_count"], 1)

    def test_multi_group_must_be_one(self):
        data = fixtures()
        data[0][0]["group_id"] = "different_group"
        self.assert_fail(data, "multi_person_single_group")

    def test_multi_five_and_all_alert(self):
        data = fixtures()
        set_decision(data, 0, RECHECK)
        result = self.assert_fail(data, "multi_person_ALERT_5")
        self.assertEqual(result["multi_person_ALERT_count"], 4)
        data = fixtures()
        data[0][0]["taxonomy"] = "supine_ground_lying"
        self.assert_fail(data, "multi_person_rows_5")

    def test_missing_response_keeps_manifest_denominators(self):
        data = fixtures(ground_alerts=60)
        del data[1][0]
        result = self.assert_fail(data, "output_rows_exact")
        self.assertEqual(result["rows"], 115)
        self.assertEqual(result["new_model_requests"], 115)
        self.assertEqual(result["valid_responses"], 114)
        self.assertEqual(result["ground_lying_ALERT_recall"], 59 / 60)
        self.assertEqual(result["strict_JSON_success"], 114 / 115)
        self.assertEqual(result["source_hash_binding_success"], 114 / 115)
        self.assertIsNone(result["multi_person_details"][0]["people_count"])

    def test_empty_no_vacuous_pass(self):
        result = self.assert_fail(([], [], []))
        for key in ("ground_lying_ALERT_recall", "strict_JSON_success", "source_hash_binding_success", "latency_p50", "latency_p95"):
            self.assertIsNone(result[key])
        self.assertEqual(result["new_model_requests"], 0)
        json.dumps(result, allow_nan=False)

    def test_missing_completed(self):
        data = fixtures()
        data[2].pop()
        self.assert_fail(data, "new_model_requests_exact")

    def test_partial_manifest_and_matching_outputs_still_fail(self):
        data = fixtures()
        data = tuple(rows[:114] for rows in data)
        self.assert_fail(data, "manifest_rows_exact")

    def test_duplicate_each_stream_and_same_count_replacement(self):
        for stream in range(3):
            for replace in (False, True):
                with self.subTest(stream=stream, replace=replace):
                    data = fixtures()
                    if replace:
                        data[stream][-1] = deepcopy(data[stream][0])
                    else:
                        data[stream].append(deepcopy(data[stream][0]))
                    result = self.assert_fail(data, "row_integrity_and_protocol")
                    self.assertTrue(any("duplicate" in e for e in result["validation_errors"]))

    def test_duplicate_item_and_operational_id_rejected(self):
        for field in ("item_id", "operational_id"):
            with self.subTest(field=field):
                data = fixtures()
                for rows in data:
                    rows[1][field] = rows[0][field]
                self.assert_fail(data, "row_integrity_and_protocol")

    def test_failed_or_pending_request_not_filtered(self):
        for state in ("failed", "claimed", "received", None):
            with self.subTest(state=state):
                data = fixtures()
                data[2][0]["state"] = state
                result = self.assert_fail(data, "completed_requests_exact")
                self.assertEqual(result["new_model_requests"], 115)
                self.assertEqual(result["valid_responses"], 114)

    def test_protocol_false_flags_http_and_missing_fields(self):
        mutations = (("strict_json_ok", False), ("strict_json_ok", 1),
                     ("source_binding_ok", False), ("source_binding_ok", "true"),
                     ("http_status", 500), ("http_status", "200"),
                     ("image_decision", "INVALID"), ("image_reason", ""),
                     ("latency_seconds", -1), ("latency_seconds", float("nan")),
                     ("latency_seconds", float("inf")), ("latency_seconds", True))
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                data = fixtures()
                data[1][0][field] = value
                synchronize(data)
                self.assert_fail(data, "row_integrity_and_protocol")
        for field in metrics.OUTPUT_KEYS:
            with self.subTest(missing=field):
                data = fixtures()
                del data[1][0][field]
                synchronize(data)
                self.assert_fail(data, "row_integrity_and_protocol")

    def test_parsed_contract_cannot_be_bypassed_by_true_flag(self):
        for field, value in (("pose", "invented"), ("bbox_1000", [0, 0, 1001, 100]),
                             ("bbox_1000", [100, 0, 0, 100]), ("bbox_1000", [0.0, 0, 100, 100]),
                             ("bbox_1000", [False, 0, 100, 100]), ("evidence", ""),
                             ("person_id", ""), ("person_id", True), ("person_id", []), ("person_id", "1"), ("person_id", 0), ("person_id", 4)):
            with self.subTest(field=field, value=value):
                data = fixtures()
                data[1][0]["parsed"]["people"][0][field] = value
                synchronize(data)
                result = self.assert_fail(data)
                self.assertEqual(result["strict_JSON_success_count"], 114)
        data = fixtures()
        data[1][0]["parsed"]["people"][0]["extra"] = "field"
        synchronize(data)
        self.assert_fail(data)

    def test_malformed_parsed_shapes(self):
        for parsed in (None, [], {}, {"scene_coverage": "complete", "people": {}},
                       {"scene_coverage": "invalid", "people": []},
                       {"scene_coverage": "complete", "people": [None]}):
            with self.subTest(parsed=parsed):
                data = fixtures()
                data[1][0]["parsed"] = parsed
                synchronize(data)
                self.assert_fail(data)

    def test_per_person_ids_and_decisions_exact_cover(self):
        for mutation in ("duplicate_person", "duplicate_decision", "missing_decision", "extra_decision", "wrong_id", "wrong_image"):
            with self.subTest(mutation=mutation):
                data = fixtures()
                row = data[1][0]
                if mutation == "duplicate_person":
                    row["parsed"]["people"][1]["person_id"] = 1
                elif mutation == "duplicate_decision":
                    row["person_decisions"][1]["person_id"] = 1
                elif mutation == "missing_decision":
                    row["person_decisions"].pop()
                elif mutation == "extra_decision":
                    row["person_decisions"].append({"person_id": 3, "decision": NORMAL, "reason": "synthetic"})
                elif mutation == "wrong_id":
                    row["person_decisions"][1]["person_id"] = 3
                else:
                    row["image_decision"] = NORMAL
                synchronize(data)
                self.assert_fail(data)

    def test_every_output_field_must_match_completed_including_logs(self):
        for field in ("item_id", "parsed", "image_decision", "latency_seconds", "source_binding_ok", "fixture_log"):
            with self.subTest(field=field):
                data = fixtures()
                data[2][0][field] = "tampered"
                self.assert_fail(data, "row_integrity_and_protocol")
        data = fixtures()
        del data[2][0]["fixture_log"]
        self.assert_fail(data)

    def test_manifest_identity_and_hash_mismatch(self):
        for field in ("item_id", "operational_id"):
            data = fixtures()
            data[0][0][field] = "wrong"
            self.assert_fail(data)
        data = fixtures()
        data[0][0]["image_sha256"] = "b" * 64
        data[1][0]["image_sha256"] = "c" * 64
        synchronize(data)
        self.assert_fail(data)

    def test_completed_hash_and_timestamps_required_ordered(self):
        for field in ("raw_response_sha256", "claimed_timestamp", "received_timestamp", "completed_timestamp"):
            data = fixtures()
            del data[2][0][field]
            self.assert_fail(data)
        for value in ("not-a-hash", "a" * 63, None):
            data = fixtures()
            data[2][0]["raw_response_sha256"] = value
            self.assert_fail(data)
        data = fixtures()
        data[2][0]["received_timestamp"] = "2026-09-09T02:00:00Z"
        self.assert_fail(data)
        data = fixtures()
        data[2][0]["claimed_timestamp"] = "2026-09-09T01:00:00"  # ambiguous timezone
        self.assert_fail(data)
        data = fixtures()
        for row in data[2]:
            row.update(claimed_timestamp=1, received_timestamp=2, completed_timestamp=3)
        self.assertEqual(self.summary(data)["gate"], "PASS")

    def test_phase_rejected_at_entry_and_per_row(self):
        for phase in (None, "", "val", "holdout", "PILOT", [], {}):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                metrics.summarize(phase, [], [], [])
        for stream in range(3):
            for value in (None, "regression", "unknown"):
                data = fixtures()
                data[stream][0]["phase"] = value
                self.assert_fail(data)
            data = fixtures()
            del data[stream][0]["phase"]
            self.assert_fail(data)

    def test_fixed_request_id_namespace(self):
        data = fixtures()
        for rows in data:
            rows[0]["request_id"] = "V5_B0_PILOT_9999"
        self.assert_fail(data, "row_integrity_and_protocol")

    def test_manifest_metadata_required_and_strata_truth_consistent(self):
        for field in ("item_id", "group_id", "taxonomy", "ground_truth", "expected_v4_outcome", "experiment_stratum"):
            with self.subTest(field=field):
                data = fixtures()
                del data[0][0][field]
                self.assert_fail(data)
        for field, value in (("ground_truth", "negative"), ("expected_v4_outcome", NORMAL),
                             ("experiment_stratum", "normal_negative"), ("source_split", "NEW_VAL"),
                             ("v3_split", "V3_HOLDOUT")):
            data = fixtures()
            data[0][0][field] = value
            self.assert_fail(data)
        data = fixtures()
        data[0][60]["taxonomy"] = "standing_walking"
        self.assert_fail(data, "floor_sitting_55")

    def test_distributions_null_bbox_and_coverage_not_localization_accuracy(self):
        data = fixtures()
        data[1][0]["parsed"]["people"][0]["bbox_1000"] = None
        data[1][0]["parsed"]["scene_coverage"] = "incomplete"
        synchronize(data)
        data[1][1]["parsed"]["scene_coverage"] = "unknown"
        synchronize(data, 1)
        result = self.summary(data)
        self.assertEqual(result["gate"], "PASS")
        self.assertEqual(result["bbox_null_count"], 1)
        self.assertEqual(result["scene_coverage_distribution"], {"complete": 113, "incomplete": 1, "unknown": 1})
        self.assertEqual(result["OBJECT_LOCALIZATION_ACCURACY"], "UNVERIFIED")

    def test_no_input_mutation_and_order_independent(self):
        data = fixtures()
        before = deepcopy(data)
        baseline = self.summary(data)
        self.assertEqual(data, before)
        reordered = (data[0], list(reversed(data[1])), data[2][50:] + data[2][:50])
        self.assertEqual(self.summary(reordered), baseline)

    def test_regression_pass_reports_target_not_pilot_gate(self):
        result = self.summary(phase="regression")
        self.assertEqual(result["gate"], "PASS", result["validation_errors"])
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["target_item_id"], metrics.REGRESSION_ITEM)
        self.assertEqual(result["target_operational_id"], "PFV4_SCREEN_0066")
        self.assertEqual(result["target_people_count"], 2)
        self.assertEqual(result["target_unique_person_id_count"], 2)
        self.assertEqual(result["target_person_decision_counts"][ALERT], 1)
        self.assertEqual(result["target_person_decision_counts"][NORMAL], 1)
        self.assertEqual(result["target_final"], ALERT)
        self.assertEqual(result["latency_p50"], 1)
        self.assertEqual(result["latency_p95"], 1)
        self.assertNotIn("ground_lying_60", result["gate_checks"])

    def test_regression_wrong_target_item_or_operational_id(self):
        for field in ("item_id", "operational_id"):
            data = fixtures("regression")
            for rows in data:
                rows[0][field] = "WRONG_TARGET"
            self.assert_fail(data, "regression_target_identity", "regression")

    def test_regression_single_person_duplicate_person_or_no_alert(self):
        data = fixtures("regression")
        data[1][0]["parsed"]["people"].pop()
        data[1][0]["person_decisions"].pop()
        synchronize(data)
        self.assert_fail(data, "regression_at_least_2_unique_people", "regression")
        data = fixtures("regression")
        data[1][0]["parsed"]["people"][1]["person_id"] = 1
        synchronize(data)
        self.assert_fail(data, "row_integrity_and_protocol", "regression")
        for decision in (RECHECK, NORMAL, ATTENTION):
            data = fixtures("regression")
            set_decision(data, 0, decision)
            self.assert_fail(data, "regression_person_ALERT", "regression")

    def test_regression_partial_failed_or_duplicate_cannot_pass(self):
        for change in ("missing", "failed", "duplicate"):
            data = fixtures("regression")
            if change == "missing":
                data[1].clear()
            elif change == "failed":
                data[2][0]["state"] = "failed"
            else:
                data[2].append(deepcopy(data[2][0]))
            self.assert_fail(data, phase="regression")


    def test_schema_max_three_people(self):
        data = fixtures()
        data[1][0]["parsed"]["people"].extend([person(3), person(4)])
        data[1][0]["person_decisions"].extend([
            {"person_id": i, "decision": NORMAL, "reason": "synthetic"} for i in (3, 4)])
        synchronize(data)
        self.assert_fail(data, "strict_JSON_all")

    def test_historical_prompt_hash_is_not_runtime_prompt_hash(self):
        data = fixtures()
        for manifest, output in zip(data[0], data[1]):
            manifest.update(image_sha256="a" * 64, full_view_sha256="b" * 64,
                            crop_view_sha256="c" * 64, prompt_sha256="d" * 64)
            output.update(source_image_sha256="a" * 64, full_view_sha256="b" * 64,
                          crop_view_sha256="c" * 64, prompt_sha256="e" * 64)
        for i in range(115):
            synchronize(data, i)
        self.assertEqual(self.summary(data)["gate"], "PASS")
        data[1][0]["source_image_sha256"] = "f" * 64
        synchronize(data)
        self.assert_fail(data, "source_hash_binding_all")

    def test_contradictory_optional_completion_and_cached_metadata(self):
        for field, value in (("done", False), ("done", 1), ("done_reason", "length"),
                             ("completion_unknown", True), ("transport_error", "timeout"),
                             ("parse_error", "truncated"), ("error", "failed"),
                             ("CACHED_PRIMARY_USED_FOR_FINAL_DECISION", True),
                             ("EVALUATION_MODE", "CACHED")):
            with self.subTest(field=field):
                data = fixtures()
                data[2][0][field] = value
                self.assert_fail(data, "row_integrity_and_protocol")

    def test_bad_identity_types_and_extreme_numbers_fail_closed(self):
        for field, value in (("request_id", []), ("item_id", {}), ("group_id", [])):
            data = fixtures()
            data[0][0][field] = value
            self.assert_fail(data)
        data = fixtures()
        data[1][0]["latency_seconds"] = 10 ** 500
        synchronize(data)
        self.assert_fail(data)

    def test_malformed_rows_and_container_types(self):
        for stream in range(3):
            data = fixtures()
            data[stream][0] = None
            self.assert_fail(data)
        with self.assertRaises(ValueError):
            metrics.summarize("pilot", {"rows": []}, [], [])


if __name__ == "__main__":
    unittest.main()
