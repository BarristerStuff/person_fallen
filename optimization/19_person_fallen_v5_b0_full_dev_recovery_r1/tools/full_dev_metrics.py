"""Correct full-DEV partial/complete metrics and irreversible stop rules.

This module performs no network calls and never changes model decisions. It uses
only the normalized recovery manifest and persisted V5-B0/new result records.
"""
from __future__ import annotations

from collections import Counter
import json
import math
import statistics
from typing import Any, Iterable

ALERT = "ALERT_GROUND_LYING"
RECHECK = "RECHECK_VISUAL_UNCERTAIN"
NORMAL = "NO_ALERT_NORMAL_POSE"
ATTENTION = "ATTENTION_NEAR_GROUND"
DECISIONS = {ALERT, RECHECK, NORMAL, ATTENTION}
STRATA = {"ground_lying", "normal_negative", "auxiliary_attention", "visual_uncertain"}
EXPECTED_STRATA = Counter({"ground_lying": 145, "normal_negative": 230, "auxiliary_attention": 41, "visual_uncertain": 20})
EXPECTED_TOTAL = 436
EXPECTED_REUSE = 115
EXPECTED_NEW = 321


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _counter(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(row.get(key) for row in rows))


def _index(rows: list[dict[str, Any]], label: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    indexed: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{label}[{number}] is not an object")
            continue
        item = row.get("item_id")
        if not isinstance(item, str) or not item:
            errors.append(f"{label}[{number}] missing item_id")
            continue
        if item in indexed:
            errors.append(f"{label} duplicate item_id {item}")
        indexed[item] = row
    return indexed, errors


def validate_manifest(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if len(rows) != EXPECTED_TOTAL:
        errors.append(f"full manifest row count {len(rows)} != {EXPECTED_TOTAL}")
    ids, id_errors = _index(rows, "manifest")
    errors.extend(id_errors)
    request_ids: list[str] = []
    counts = Counter()
    reuse = new = 0
    for item, row in ids.items():
        for field in ("request_id", "operational_id", "taxonomy", "group_id", "source_split", "v3_split", "evaluation_stratum", "result_source"):
            if not isinstance(row.get(field), str) or not row[field]:
                errors.append(f"manifest/{item} missing {field}")
        if row.get("evaluation_stratum") not in STRATA:
            errors.append(f"manifest/{item} invalid evaluation_stratum")
        else:
            counts[row["evaluation_stratum"]] += 1
        if row.get("result_source") == "REUSE_V5_B0_PILOT":
            reuse += 1
            if not row.get("request_id", "").startswith("V5_B0_PILOT_"):
                errors.append(f"manifest/{item} invalid reuse request id")
        elif row.get("result_source") == "NEW_INFERENCE":
            new += 1
            if not row.get("request_id", "").startswith("V5_B0_FULLDEV_EXTENSION_"):
                errors.append(f"manifest/{item} invalid new request id")
        else:
            errors.append(f"manifest/{item} invalid result_source")
        request_ids.append(row.get("request_id"))
        if row.get("v3_split") != "V3_DEV":
            errors.append(f"manifest/{item} is not V3_DEV")
        if "VAL" in str(row.get("source_split", "")).upper() or "HOLDOUT" in str(row.get("source_split", "")).upper():
            errors.append(f"manifest/{item} forbidden split")
    if len(request_ids) != len(set(request_ids)):
        errors.append("manifest duplicate request_id")
    if counts != EXPECTED_STRATA:
        errors.append(f"manifest strata mismatch {counts} != {EXPECTED_STRATA}")
    if reuse != EXPECTED_REUSE or new != EXPECTED_NEW:
        errors.append(f"manifest reuse/new mismatch {reuse}/{new}")
    floor = [r for r in rows if r.get("taxonomy") == "floor_sitting"]
    if len(floor) != 55 or any(r.get("evaluation_stratum") != "normal_negative" for r in floor):
        errors.append("floor_sitting is not exactly 55 normal-negative rows")
    # The known regression is not allowed in the full DEV manifest.
    if any(r.get("item_id") == "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05" for r in rows):
        errors.append("known regression leaked into full DEV")
    return errors


def _person_shape_errors(person: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(person, dict):
        return [f"{prefix} is not an object"]
    required = {"person_id", "bbox_1000", "person_visible", "pose", "torso_orientation", "torso_ground_contact", "head_shoulders_above_hips", "support_surface", "explicit_work_evidence", "visual_quality", "evidence"}
    if set(person) != required:
        errors.append(f"{prefix} exact-key mismatch")
        return errors
    if type(person["person_id"]) is not int or not 1 <= person["person_id"] <= 3:
        errors.append(f"{prefix} invalid person_id")
    box = person["bbox_1000"]
    if box is not None and not (isinstance(box, list) and len(box) == 4 and all(type(x) is int and 0 <= x <= 1000 for x in box) and box[0] < box[2] and box[1] < box[3]):
        errors.append(f"{prefix} invalid bbox")
    enums = {
        "person_visible": {"yes", "no", "uncertain"},
        "pose": {"standing", "walking", "chair_sitting", "floor_sitting", "kneeling", "squat_crouch", "bending", "crawling", "pushup_plank", "supine", "side_lying", "prone", "curled_lying", "other_near_ground", "unknown"},
        "torso_orientation": {"upright", "inclined", "horizontal", "unknown"},
        "torso_ground_contact": {"none", "partial", "broad", "unknown"},
        "head_shoulders_above_hips": {"yes", "no", "unknown"},
        "support_surface": {"floor", "chair", "bed_sofa", "unknown"},
        "explicit_work_evidence": {"yes", "no", "unknown"},
        "visual_quality": {"clear", "insufficient"},
    }
    for key, allowed in enums.items():
        if person.get(key) not in allowed:
            errors.append(f"{prefix} invalid {key}")
    if not isinstance(person.get("evidence"), str) or not person["evidence"].strip():
        errors.append(f"{prefix} empty evidence")
    return errors


def validate_output_record(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("item_id", "request_id", "operational_id", "taxonomy", "group_id", "evaluation_stratum", "result_source", "image_decision", "image_reason", "source_image_sha256", "full_view_sha256", "crop_view_sha256"):
        if not isinstance(row.get(field), str) or not row[field]:
            errors.append(f"output missing {field}")
    if row.get("image_decision") not in DECISIONS:
        errors.append("output invalid image_decision")
    if row.get("source_binding_ok") is not True:
        errors.append("output source_binding_ok is not true")
    if row.get("strict_json_ok") is not True:
        errors.append("output strict_json_ok is not true")
    if not _finite_number(row.get("latency_seconds")) or row["latency_seconds"] < 0:
        errors.append("output latency invalid")
    parsed = row.get("parsed")
    if not isinstance(parsed, dict) or set(parsed) != {"scene_coverage", "people"}:
        errors.append("output parsed top-level mismatch")
    else:
        if parsed["scene_coverage"] not in {"complete", "incomplete", "unknown"}:
            errors.append("output scene_coverage invalid")
        if not isinstance(parsed["people"], list) or len(parsed["people"]) > 3:
            errors.append("output people array invalid")
        else:
            person_ids = []
            for i, person in enumerate(parsed["people"]):
                errors.extend(_person_shape_errors(person, f"people[{i}]"))
                if isinstance(person, dict):
                    person_ids.append(person.get("person_id"))
            if len(person_ids) != len(set(person_ids)):
                errors.append("output duplicate person_id")
    decisions = row.get("person_decisions")
    if not isinstance(decisions, list):
        errors.append("output person_decisions is not a list")
    else:
        decision_ids = []
        for decision in decisions:
            if not isinstance(decision, dict) or set(decision) != {"person_id", "decision", "reason"}:
                errors.append("output person decision shape mismatch")
                continue
            decision_ids.append(decision.get("person_id"))
            if decision.get("decision") not in DECISIONS or not isinstance(decision.get("reason"), str) or not decision["reason"]:
                errors.append("output person decision value invalid")
        if len(decision_ids) != len(set(decision_ids)):
            errors.append("output duplicate person decision id")
        if isinstance(parsed, dict) and isinstance(parsed.get("people"), list) and not errors:
            if set(decision_ids) != {p["person_id"] for p in parsed["people"]}:
                errors.append("person decisions do not cover parsed people")
        if any(d.get("decision") == ALERT for d in decisions if isinstance(d, dict)) != (row.get("image_decision") == ALERT):
            errors.append("image decision does not aggregate person decisions")
    return errors


def _observed_counts(manifest: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    output = {row["item_id"]: row for row in outputs}
    result: dict[str, dict[str, int]] = {}
    for stratum in ["ground_lying", "normal_negative", "auxiliary_attention", "visual_uncertain"]:
        rows = [row for row in manifest if row.get("evaluation_stratum") == stratum and row.get("item_id") in output]
        result[stratum] = {decision: sum(output[row["item_id"]]["image_decision"] == decision for row in rows) for decision in DECISIONS}
        result[stratum]["observed"] = len(rows)
        result[stratum]["pending"] = sum(row.get("evaluation_stratum") == stratum for row in manifest) - len(rows)
    return result


def early_stop_trigger(manifest: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> str | None:
    """Return only a pre-registered irreversible trigger, based on observed rows."""
    counts = _observed_counts(manifest, outputs)
    normal = counts["normal_negative"]
    ground = counts["ground_lying"]
    auxiliary = counts["auxiliary_attention"]
    if normal[ALERT] >= 1:
        return "A_DETERMINATE_NEGATIVE_ALERT"
    if normal[RECHECK] >= 24:
        return "B_NORMAL_NEGATIVE_RECHECK_REACHED_24"
    if ground[NORMAL] + ground[ATTENTION] >= 1:
        return "C_GROUND_NO_ALERT_OR_ATTENTION"
    observed_non_alert = ground[RECHECK] + ground[NORMAL] + ground[ATTENTION]
    max_possible_final_alert = ground[ALERT] + ground["pending"]
    if observed_non_alert >= 8 or max_possible_final_alert < 138:
        return "D_GROUND_NON_ALERT_RECALL_IMPOSSIBLE"
    if auxiliary[ALERT] >= 1:
        return "E_AUXILIARY_HIGH_PRIORITY_ALERT"
    return None


def _base_validation(manifest: list[dict[str, Any]], outputs: list[dict[str, Any]], request_records: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    errors = validate_manifest(manifest)
    output_map, output_errors = _index(outputs, "output")
    errors.extend(output_errors)
    request_map, request_errors = _index(request_records, "request")
    errors.extend(request_errors)
    manifest_map = {row["item_id"]: row for row in manifest if isinstance(row, dict) and row.get("item_id")}
    for item_id, output in output_map.items():
        errors.extend(f"output/{item_id}: {e}" for e in validate_output_record(output))
        m = manifest_map.get(item_id)
        if m is None:
            errors.append(f"output/{item_id} not in manifest")
            continue
        for field in ("request_id", "operational_id", "evaluation_stratum", "source_image_sha256", "full_view_sha256", "crop_view_sha256"):
            if field in output and field in m and output[field] != m[field]:
                errors.append(f"output/{item_id} mismatch {field}")
        if output.get("result_source") != m.get("result_source"):
            errors.append(f"output/{item_id} result_source mismatch")
    for request_id, request in request_map.items():
        if request.get("state") not in {"completed", "protocol_failure"}:
            errors.append(f"request/{request_id} invalid state")
        if request.get("state") == "completed":
            if request.get("done") is not True or request.get("done_reason") != "stop":
                errors.append(f"request/{request_id} completion metadata invalid")
            if request.get("strict_json_ok") is not True:
                errors.append(f"request/{request_id} strict_json false")
            if request.get("source_binding_ok") is not True:
                errors.append(f"request/{request_id} binding false")
            if request.get("request_id") not in {row.get("request_id") for row in outputs}:
                errors.append(f"request/{request_id} has no output")
    return errors, output_map, request_map


def _distributions(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    people_counts = Counter()
    coverages = Counter()
    bbox_null = 0
    attr = {key: Counter() for key in ("pose", "support_surface", "torso_ground_contact", "torso_orientation")}
    conflict_reasons = Counter()
    for row in outputs:
        parsed = row.get("parsed", {})
        people = parsed.get("people", []) if isinstance(parsed, dict) else []
        people_counts[str(len(people))] += 1
        if isinstance(parsed, dict):
            coverages[parsed.get("scene_coverage")] += 1
        for person in people:
            if person.get("bbox_1000") is None:
                bbox_null += 1
            for key in attr:
                attr[key][person.get(key)] += 1
        for decision in row.get("person_decisions", []):
            reason = decision.get("reason", "")
            if "CONFLICT" in reason or "UNRESOLVED" in reason or "UNRELIABLE" in reason or "WITHOUT" in reason:
                conflict_reasons[reason] += 1
    return {"people_count_distribution": dict(sorted(people_counts.items())), "scene_coverage_distribution": dict(sorted(coverages.items())), "bbox_null_count": bbox_null, "person_attribute_distributions": {key: dict(sorted(value.items())) for key, value in attr.items()}, "person_conflict_reason_distribution": dict(sorted(conflict_reasons.items()))}


def summarize_partial(manifest: list[dict[str, Any]], outputs: list[dict[str, Any]], request_records: list[dict[str, Any]], *, attempted_count: int | None = None, protocol_failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Summarize observed rows only; never fills pending rows with a decision."""
    errors, output_map, request_map = _base_validation(manifest, outputs, request_records)
    if len(output_map) > EXPECTED_TOTAL:
        errors.append("too many output rows")
    reuse_observed = sum(row.get("result_source") == "REUSE_V5_B0_PILOT" for row in outputs)
    new_observed = sum(row.get("result_source") == "NEW_INFERENCE" for row in outputs)
    counts = _observed_counts(manifest, outputs)
    ground, normal, floor, aux, uncertain = (counts[key] for key in ("ground_lying", "normal_negative", "normal_negative", "auxiliary_attention", "visual_uncertain"))
    floor_rows = [row for row in manifest if row.get("taxonomy") == "floor_sitting"]
    floor_ids = {row["item_id"] for row in floor_rows}
    floor_out = [row for row in outputs if row.get("item_id") in floor_ids]
    floor_counts = {decision: sum(row["image_decision"] == decision for row in floor_out) for decision in DECISIONS}
    trigger = early_stop_trigger(manifest, outputs)
    attempted = attempted_count if attempted_count is not None else len(request_records)
    latencies = [float(row["latency_seconds"]) for row in request_records if row.get("state") == "completed" and _finite_number(row.get("latency_seconds"))]
    eval_counts = [row["eval_count"] for row in request_records if row.get("state") == "completed" and type(row.get("eval_count")) is int]
    observed = {key: value["observed"] for key, value in counts.items()}
    pending = {key: value["pending"] for key, value in counts.items()}
    max_ground_alert = ground[ALERT] + ground["pending"]
    result = {
        "status": "PARTIAL_OBSERVED_ONLY",
        "full_dev_expected_rows": EXPECTED_TOTAL,
        "V5_B0_REUSED_RESULTS": reuse_observed,
        "new_results_observed": new_observed,
        "new_requests_claimed": attempted,
        "new_requests_completed": sum(request.get("state") == "completed" for request in request_map.values()),
        "new_requests_unknown": sum(request.get("completion_unknown") is True for request in request_map.values()),
        "new_requests_not_started": max(0, EXPECTED_NEW - attempted),
        "completed_full_dev": False,
        "observed_rows": len(output_map),
        "pending_rows": EXPECTED_TOTAL - len(output_map),
        "observed_by_stratum": observed,
        "pending_by_stratum": pending,
        "max_possible_final_ground_alert": max_ground_alert,
        "ground_lying": {"observed": ground["observed"], "pending": ground["pending"], "ALERT": ground[ALERT], "RECHECK": ground[RECHECK], "NO_ALERT": ground[NORMAL], "ATTENTION": ground[ATTENTION], "ALERT_recall_observed": ground[ALERT] / ground["observed"] if ground["observed"] else None, "ALERT_RECHECK_coverage_observed": (ground[ALERT] + ground[RECHECK]) / ground["observed"] if ground["observed"] else None},
        "normal_negative": {"observed": normal["observed"], "pending": normal["pending"], "ALERT": normal[ALERT], "RECHECK": normal[RECHECK], "NO_ALERT": normal[NORMAL], "ATTENTION": normal[ATTENTION], "ALERT_FPR_observed": normal[ALERT] / normal["observed"] if normal["observed"] else None, "total_RECHECK_rate_observed": normal[RECHECK] / normal["observed"] if normal["observed"] else None},
        "floor_sitting": {"count": 55, "observed": len(floor_out), "pending": 55 - len(floor_out), "ALERT": floor_counts[ALERT], "RECHECK": floor_counts[RECHECK], "NO_ALERT": floor_counts[NORMAL], "ATTENTION": floor_counts[ATTENTION]},
        "auxiliary_attention": {"observed": aux["observed"], "pending": aux["pending"], "ALERT": aux[ALERT], "RECHECK": aux[RECHECK], "NO_ALERT": aux[NORMAL], "ATTENTION": aux[ATTENTION]},
        "visual_uncertain_distribution": {"observed": uncertain["observed"], "pending": uncertain["pending"], "ALERT": uncertain[ALERT], "RECHECK": uncertain[RECHECK], "NO_ALERT": uncertain[NORMAL], "ATTENTION": uncertain[ATTENTION]},
        "by_taxonomy_observed": {taxonomy: dict(Counter(row.get("image_decision") for row in outputs if row.get("taxonomy") == taxonomy)) for taxonomy in sorted({row.get("taxonomy") for row in outputs if isinstance(row.get("taxonomy"), str) and row.get("taxonomy")})},
        **_distributions(outputs),
        "new_request_latency_p50": _pct(latencies, .50), "new_request_latency_p95": _pct(latencies, .95), "new_request_latency_p99": _pct(latencies, .99),
        "new_request_output_token_statistics": {"count": len(eval_counts), "min": min(eval_counts) if eval_counts else None, "max": max(eval_counts) if eval_counts else None, "mean": statistics.mean(eval_counts) if eval_counts else None},
        "protocol_failures": protocol_failures or [], "validation_errors": errors, "early_stop_trigger": trigger, "FULL_DEV_GATE": "NOT_EVALUATED_PARTIAL", "LEGACY_V4_CACHE_USED_FOR_DECISION": False, "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED", "known_regression": "PREVIOUS_PASS_NOT_RERUN",
    }
    return result


def summarize_complete(manifest: list[dict[str, Any]], outputs: list[dict[str, Any]], request_records: list[dict[str, Any]]) -> dict[str, Any]:
    result = summarize_partial(manifest, outputs, request_records, attempted_count=len(request_records))
    errors = list(result["validation_errors"])
    if len(outputs) != EXPECTED_TOTAL:
        errors.append("complete output count is not 436")
    if result["V5_B0_REUSED_RESULTS"] != EXPECTED_REUSE or result["new_results_observed"] != EXPECTED_NEW:
        errors.append("complete reuse/new count mismatch")
    if result["new_requests_completed"] != EXPECTED_NEW or result["new_requests_unknown"] != 0:
        errors.append("complete request count/state mismatch")
    g, n, f, a = result["ground_lying"], result["normal_negative"], result["floor_sitting"], result["auxiliary_attention"]
    checks = {
        "rows_exact": len(outputs) == EXPECTED_TOTAL,
        "ground_count": g["observed"] == 145,
        "ground_alert_min": g["ALERT"] >= 138,
        "ground_alert_recheck_coverage": g["ALERT"] + g["RECHECK"] == 145,
        "ground_no_alert_zero": g["NO_ALERT"] == 0,
        "ground_attention_zero": g["ATTENTION"] == 0,
        "normal_count": n["observed"] == 230,
        "normal_alert_zero": n["ALERT"] == 0,
        "normal_recheck_max": n["RECHECK"] <= 23,
        "floor_count": f["count"] == 55,
        "floor_alert_zero": f["ALERT"] == 0,
        "floor_recheck_max": f["RECHECK"] <= 5,
        "floor_no_alert_min": f["NO_ALERT"] >= 50,
        "auxiliary_alert_zero": a["ALERT"] == 0,
        "strict_json_all": result["observed_rows"] == EXPECTED_TOTAL and not any("strict_json" in error for error in errors),
        "source_cache_binding_all": result["observed_rows"] == EXPECTED_TOTAL and not any("binding" in error for error in errors),
        "no_validation_errors": not errors,
    }
    result["validation_errors"] = errors
    result["gate_checks"] = checks
    result["FULL_DEV_GATE"] = "PASS" if all(checks.values()) else "FAIL"
    result["status"] = "COMPLETE"
    result["completed_full_dev"] = True
    return result
