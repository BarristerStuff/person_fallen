"""Offline, fail-closed V5 metrics. No I/O, imports of inference, or policy replay.

summarize accepts three sequences of dictionaries (not manifest file wrappers).
Unknown phases raise ValueError; data/protocol defects produce gate='FAIL' with
validation_errors. Ratios are fractions in [0, 1], with manifest denominators;
zero denominators produce None. Percentiles use linear interpolation (n-1)*p.

strict_JSON_success requires the upstream strict_json_ok attestation AND an
independent parsed-object shape check. source_hash_binding_success checks the
source_binding_ok attestation and output/completed-record consistency; this
function cannot independently hash image bytes or reparse unavailable raw bytes.
No localization or semantic correctness is inferred from a non-null bbox.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import math
import re

ALERT = "ALERT_GROUND_LYING"
RECHECK = "RECHECK_VISUAL_UNCERTAIN"
NORMAL = "NO_ALERT_NORMAL_POSE"
ATTENTION = "ATTENTION_NEAR_GROUND"
DECISIONS = (ALERT, RECHECK, NORMAL, ATTENTION)
REGRESSION_ITEM = "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05"
REGRESSION_OPERATIONAL_ID = "PFV4_SCREEN_0066"
MULTI_TAXONOMY = "multi_person_one_lying"
ENUMS = {
    "person_visible": {"yes", "no", "uncertain"},
    "pose": {"standing", "walking", "chair_sitting", "floor_sitting", "kneeling",
             "squat_crouch", "bending", "crawling", "pushup_plank", "supine",
             "side_lying", "prone", "curled_lying", "other_near_ground", "unknown"},
    "torso_orientation": {"upright", "inclined", "horizontal", "unknown"},
    "torso_ground_contact": {"none", "partial", "broad", "unknown"},
    "head_shoulders_above_hips": {"yes", "no", "unknown"},
    "support_surface": {"floor", "chair", "bed_sofa", "unknown"},
    "explicit_work_evidence": {"yes", "no", "unknown"},
    "visual_quality": {"clear", "insufficient"},
}
PERSON_KEYS = set(ENUMS) | {"evidence", "person_id", "bbox_1000"}
OUTPUT_KEYS = {
    "phase", "request_id", "item_id", "operational_id", "source_binding_ok",
    "strict_json_ok", "http_status", "parsed", "person_decisions",
    "image_decision", "image_reason", "latency_seconds",
}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _member(value, choices):
    return isinstance(value, str) and value in choices


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _person_id(value):
    # Matches the local target_attributes schema and contracts validator.
    return type(value) is int and 1 <= value <= 3


def _same(left, right):
    try:
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
            right, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        return False


def _timestamp(value):
    if _finite(value):
        return float(value)
    if _text(value):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                return stamp.timestamp()
        except (ValueError, OverflowError):
            pass
    return None


def _parsed_errors(parsed):
    if not isinstance(parsed, dict) or set(parsed) != {"scene_coverage", "people"}:
        return ["parsed must have exactly scene_coverage and people"]
    errors = []
    if not _member(parsed["scene_coverage"], {"complete", "incomplete", "unknown"}):
        errors.append("invalid scene_coverage")
    people = parsed["people"]
    if not isinstance(people, list):
        return errors + ["people must be an array"]
    if len(people) > 3:
        errors.append("people array exceeds maximum of 3")
    ids = set()
    for i, person in enumerate(people):
        prefix = f"people[{i}]"
        if not isinstance(person, dict) or set(person) != PERSON_KEYS:
            errors.append(f"{prefix}: expected exactly 11 person fields")
            continue
        pid = person["person_id"]
        if not _person_id(pid):
            errors.append(f"{prefix}: invalid person_id")
        elif pid in ids:
            errors.append(f"{prefix}: duplicate person_id")
        else:
            ids.add(pid)
        for name, choices in ENUMS.items():
            if not _member(person[name], choices):
                errors.append(f"{prefix}: invalid {name}")
        if not _text(person["evidence"]):
            errors.append(f"{prefix}: empty evidence")
        box = person["bbox_1000"]
        if box is not None and not (
            isinstance(box, list) and len(box) == 4
            and all(type(v) is int and 0 <= v <= 1000 for v in box)
            and box[0] < box[2] and box[1] < box[3]
        ):
            errors.append(f"{prefix}: invalid bbox_1000")
    return errors


def _output_errors(row):
    errors = []
    missing = OUTPUT_KEYS - set(row)
    if missing:
        errors.append("missing output fields: " + ",".join(sorted(missing)))
    if not _text(row.get("operational_id")):
        errors.append("missing operational_id")
    if type(row.get("http_status")) is not int or row["http_status"] != 200:
        errors.append("http_status must be integer 200")
    if row.get("strict_json_ok") is not True:
        errors.append("strict_json_ok must be true")
    if row.get("source_binding_ok") is not True:
        errors.append("source_binding_ok must be true")
    if not _finite(row.get("latency_seconds")) or row["latency_seconds"] < 0:
        errors.append("latency_seconds must be finite and nonnegative")
    if not _member(row.get("image_decision"), DECISIONS):
        errors.append("invalid image_decision")
    if not _text(row.get("image_reason")):
        errors.append("empty image_reason")
    parsed_errors = _parsed_errors(row.get("parsed"))
    errors.extend(parsed_errors)
    decisions = row.get("person_decisions")
    if not isinstance(decisions, list):
        errors.append("person_decisions must be an array")
    else:
        ids = []
        for entry in decisions:
            if not isinstance(entry, dict) or set(entry) != {"person_id", "decision", "reason"}:
                errors.append("invalid person_decision fields")
                continue
            if not _person_id(entry["person_id"]):
                errors.append("invalid decision person_id")
            else:
                ids.append(entry["person_id"])
            if not _member(entry["decision"], DECISIONS) or not _text(entry["reason"]):
                errors.append("invalid person decision/reason")
        if len(ids) != len(set(ids)):
            errors.append("duplicate decision person_id")
        if not parsed_errors:
            expected = {person["person_id"] for person in row["parsed"]["people"]}
            if len(ids) != len(decisions) or set(ids) != expected:
                errors.append("person_decisions must cover each parsed person exactly once")
        any_alert = any(isinstance(d, dict) and d.get("decision") == ALERT for d in decisions)
        if any_alert != (row.get("image_decision") == ALERT):
            errors.append("image/person ALERT aggregation mismatch")
    return errors


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def _ratio(count, denominator):
    return count / denominator if denominator else None


def summarize(phase, manifest_rows, output_rows, request_records):
    """Return auditable counts and gate checks; never create/alter decisions.

    Request IDs must be the exact phase-specific fixed set. Row order is not
    significant. Every supplied output field, including additional log fields,
    must also be present and identical in its completed record. A malformed or
    failed request is included in new_model_requests, never silently filtered.
    Only unique, fully validated, manifest-bound output/record pairs contribute
    to decision counts and distributions. Manifest counts remain denominators.
    """
    if not _member(phase, {"pilot", "regression"}):
        raise ValueError("phase must be explicitly 'pilot' or 'regression'")
    for name, rows in (("manifest_rows", manifest_rows), ("output_rows", output_rows),
                       ("request_records", request_records)):
        if not isinstance(rows, (list, tuple)):
            raise ValueError(f"{name} must be a sequence of row dictionaries")
    expected_count = 115 if phase == "pilot" else 1
    expected_ids = {f"V5_B0_{phase.upper()}_{i:04d}" for i in range(1, expected_count + 1)}
    errors = []

    def index_rows(rows, label):
        indexed = {}
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{label}[{i}]: row must be an object")
                continue
            rid = row.get("request_id")
            if not _text(rid):
                errors.append(f"{label}[{i}]: missing/invalid request_id")
                continue
            indexed.setdefault(rid, []).append(row)
            if row.get("phase") != phase:
                errors.append(f"{label}/{rid}: missing or mismatched phase")
        for rid, duplicates in indexed.items():
            if len(duplicates) != 1:
                errors.append(f"{label}/{rid}: duplicate request_id ({len(duplicates)})")
        if set(indexed) != expected_ids:
            errors.append(f"{label}: request_id set differs from fixed {phase} request set")
        for field in ("item_id", "operational_id"):
            values = [r.get(field) for r in rows if isinstance(r, dict) and _text(r.get(field))]
            if len(values) != len(set(values)):
                errors.append(f"{label}: duplicate {field}")
        return indexed

    manifests = index_rows(manifest_rows, "manifest")
    outputs = index_rows(output_rows, "output")
    records = index_rows(request_records, "request")
    manifest_valid = {}
    for rid, entries in manifests.items():
        row = entries[0]
        row_errors = []
        for field in ("item_id", "group_id", "taxonomy", "ground_truth", "expected_v4_outcome"):
            if not _text(row.get(field)):
                row_errors.append(f"missing/invalid {field}")
        stratum = row.get("experiment_stratum")
        if not _member(stratum, {"ground_lying", "normal_negative"}):
            row_errors.append("invalid experiment_stratum")
        else:
            if row.get("ground_truth") != ("positive" if stratum == "ground_lying" else "negative"):
                row_errors.append("ground_truth conflicts with experiment_stratum")
            if row.get("expected_v4_outcome") != (ALERT if stratum == "ground_lying" else NORMAL):
                row_errors.append("expected_v4_outcome conflicts with experiment_stratum")
            if stratum == "normal_negative" and row.get("taxonomy") != "floor_sitting":
                row_errors.append("normal_negative must be floor_sitting for this experiment")
        if row.get("taxonomy") == MULTI_TAXONOMY and stratum != "ground_lying":
            row_errors.append("multi-person subset must belong to ground_lying")
        # Reject forbidden partitions if provenance metadata is supplied. No files are opened.
        for field in ("source_split", "v3_split", "split", "partition"):
            split = row.get(field)
            if isinstance(split, str) and re.search(r"val|holdout", split, re.IGNORECASE):
                row_errors.append(f"forbidden partition in {field}")
        errors.extend(f"manifest/{rid}: {e}" for e in row_errors)
        manifest_valid[rid] = not row_errors and row.get("phase") == phase and rid in expected_ids

    valid = {}
    strict_count = binding_count = completed_count = 0
    for rid, entries in records.items():
        if len(entries) == 1 and entries[0].get("state") == "completed":
            completed_count += 1
    for rid, entries in outputs.items():
        if len(entries) != 1:
            continue
        row = entries[0]
        row_errors = _output_errors(row)
        manifest_entries = manifests.get(rid, [])
        record_entries = records.get(rid, [])
        identity_ok = len(manifest_entries) == 1 and manifest_valid.get(rid, False)
        if identity_ok:
            manifest = manifest_entries[0]
            if row.get("phase") != phase or row.get("item_id") != manifest.get("item_id"):
                identity_ok = False
            if "operational_id" in manifest and row.get("operational_id") != manifest["operational_id"]:
                identity_ok = False
            # Historical generation prompt_sha256 is NOT this run's prompt hash.
            # Compare source-image/view hashes only, including the runner's alias.
            for output_key, manifest_key in (
                ("source_image_sha256", "image_sha256"), ("image_sha256", "image_sha256"),
                ("full_view_sha256", "full_view_sha256"), ("crop_view_sha256", "crop_view_sha256"),
            ):
                if output_key in row and manifest_key in manifest and not _same(row[output_key], manifest[manifest_key]):
                    identity_ok = False
        if not identity_ok:
            row_errors.append("output identity/source does not bind to a unique valid manifest row")
        record_ok = len(record_entries) == 1
        if record_ok:
            record = record_entries[0]
            if record.get("state") != "completed":
                record_ok = False
                row_errors.append("request state is not completed")
            # Optional runner metadata must not contradict successful fresh completion.
            for field, expected in (("done", True), ("done_reason", "stop"),
                                    ("completion_unknown", False),
                                    ("CACHED_PRIMARY_USED_FOR_FINAL_DECISION", False),
                                    ("EVALUATION_MODE", "NEW_TARGET_ATTRIBUTES_ONLY")):
                if field in record and not _same(record[field], expected):
                    record_ok = False
                    row_errors.append(f"contradictory completion metadata: {field}")
            for field in ("transport_error", "parse_error", "error"):
                if record.get(field) not in (None, "", False):
                    record_ok = False
                    row_errors.append(f"request contains failure metadata: {field}")
            raw_hash = record.get("raw_response_sha256")
            if not isinstance(raw_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", raw_hash):
                record_ok = False
                row_errors.append("missing/invalid raw_response_sha256")
            stamps = [_timestamp(record.get(key)) for key in (
                "claimed_timestamp", "received_timestamp", "completed_timestamp")]
            if any(t is None for t in stamps) or not (stamps[0] <= stamps[1] <= stamps[2]):
                record_ok = False
                row_errors.append("missing/invalid/out-of-order request timestamps")
            for key, value in row.items():
                if key not in record or not _same(value, record[key]):
                    record_ok = False
                    row_errors.append(f"completed/output mismatch: {key}")
        else:
            row_errors.append("missing or duplicate completed record")
        bound = identity_ok and record_ok
        strict_ok = row.get("strict_json_ok") is True and not _parsed_errors(row.get("parsed"))
        strict_count += int(bound and strict_ok)
        binding_count += int(bound and row.get("source_binding_ok") is True)
        if not row_errors and bound:
            valid[rid] = row
        errors.extend(f"output/{rid}: {e}" for e in row_errors)

    ground = [r for r in manifest_rows if isinstance(r, dict) and r.get("experiment_stratum") == "ground_lying"]
    floor = [r for r in manifest_rows if isinstance(r, dict) and r.get("experiment_stratum") == "normal_negative" and r.get("taxonomy") == "floor_sitting"]
    multi = [r for r in ground if r.get("taxonomy") == MULTI_TAXONOMY]

    def decision_counts(rows):
        # Duplicate manifest rows cannot multiply a response's numerator.
        ids = {r["request_id"] for r in rows if _text(r.get("request_id"))}
        counts = Counter(valid[rid]["image_decision"] for rid in ids if rid in valid)
        return {d: counts[d] for d in DECISIONS}

    ground_counts, floor_counts, multi_counts = map(decision_counts, (ground, floor, multi))
    distribution_fields = ("pose", "support_surface", "torso_ground_contact", "torso_orientation")
    distributions = {field: Counter() for field in distribution_fields}
    people_counts, coverage_counts = Counter(), Counter()
    bbox_null_count = 0
    for row in valid.values():
        parsed = row["parsed"]
        people_counts[str(len(parsed["people"]))] += 1
        coverage_counts[parsed["scene_coverage"]] += 1
        for person in parsed["people"]:
            bbox_null_count += int(person["bbox_1000"] is None)
            for field in distribution_fields:
                distributions[field][person[field]] += 1
    def valid_row(row):
        rid = row.get("request_id")
        return valid.get(rid) if _text(rid) else None

    multi_details = [{
        "request_id": row.get("request_id"), "item_id": row.get("item_id"),
        "group_id": row.get("group_id"),
        "people_count": len(valid_row(row)["parsed"]["people"]) if valid_row(row) else None,
        "image_decision": valid_row(row)["image_decision"] if valid_row(row) else None,
    } for row in multi]
    multi_group_count = len({r["group_id"] for r in multi if _text(r.get("group_id"))})
    latencies = [row["latency_seconds"] for row in valid.values()]
    denominator = len(manifest_rows)
    checks = {
        "manifest_rows_exact": denominator == expected_count,
        "output_rows_exact": len(output_rows) == expected_count,
        "new_model_requests_exact": len(request_records) == expected_count,
        "completed_requests_exact": completed_count == expected_count,
        "row_integrity_and_protocol": not errors,
        "valid_responses_exact": len(valid) == expected_count,
        "strict_JSON_all": strict_count == expected_count and denominator == expected_count,
        "source_hash_binding_all": binding_count == expected_count and denominator == expected_count,
    }
    result = {
        "phase": phase, "rows": denominator, "expected_rows": expected_count,
        "output_rows": len(output_rows), "new_model_requests": len(request_records),
        "completed_requests": completed_count, "valid_responses": len(valid),
        "ground_lying_count": len(ground), "ground_lying_ALERT_count": ground_counts[ALERT],
        "ground_lying_ALERT_recall": _ratio(ground_counts[ALERT], len(ground)),
        "ground_lying_ALERT_RECHECK_count": ground_counts[ALERT] + ground_counts[RECHECK],
        "ground_lying_ALERT_RECHECK_coverage": _ratio(ground_counts[ALERT] + ground_counts[RECHECK], len(ground)),
        "ground_lying_decision_counts": ground_counts,
        "floor_sitting_count": len(floor), "floor_sitting_decision_counts": floor_counts,
        "multi_person_rows": len(multi), "multi_person_group_count": multi_group_count,
        "multi_person_ALERT_count": multi_counts[ALERT], "multi_person_details": multi_details,
        "people_count_distribution": dict(sorted(people_counts.items())),
        "scene_coverage_distribution": dict(sorted(coverage_counts.items())),
        "bbox_null_count": bbox_null_count,
        "person_attribute_distributions": {k: dict(sorted(v.items())) for k, v in distributions.items()},
        "strict_JSON_success": _ratio(strict_count, denominator),
        "strict_JSON_success_count": strict_count, "strict_JSON_denominator": denominator,
        "source_hash_binding_success": _ratio(binding_count, denominator),
        "source_hash_binding_success_count": binding_count, "source_hash_binding_denominator": denominator,
        "latency_p50": _percentile(latencies, 0.50), "latency_p95": _percentile(latencies, 0.95),
        "latency_count": len(latencies), "latency_units": "seconds",
        "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED",
        "verification_scope": "offline supplied rows only; strict raw JSON parsing and image hash binding are upstream attestations corroborated against completed records; raw bytes, image content, and request freshness are not independently verified",
        "validation_errors": errors,
    }
    for short, decision in (("ALERT", ALERT), ("RECHECK", RECHECK), ("NO_ALERT", NORMAL), ("ATTENTION", ATTENTION)):
        result[f"floor_sitting_{short}_count"] = floor_counts[decision]
    if phase == "pilot":
        checks.update({
            "ground_lying_60": len(ground) == 60,
            "floor_sitting_55": len(floor) == 55,
            "ground_ALERT_at_least_57": ground_counts[ALERT] >= 57,
            "ground_ALERT_RECHECK_60": ground_counts[ALERT] + ground_counts[RECHECK] == 60,
            "floor_ALERT_0": floor_counts[ALERT] == 0,
            "floor_RECHECK_at_most_5": floor_counts[RECHECK] <= 5,
            "floor_NO_ALERT_at_least_50": floor_counts[NORMAL] >= 50,
            "multi_person_rows_5": len(multi) == 5,
            "multi_person_single_group": multi_group_count == 1,
            "multi_person_ALERT_5": multi_counts[ALERT] == 5,
        })
    else:
        target_manifest = manifest_rows[0] if len(manifest_rows) == 1 and isinstance(manifest_rows[0], dict) else {}
        target = next(iter(valid.values())) if len(valid) == 1 else None
        people = target["parsed"]["people"] if target else []
        decisions = target["person_decisions"] if target else []
        target_counts = Counter(d["decision"] for d in decisions)
        final = target["image_decision"] if target else None
        checks.update({
            "regression_target_identity": target_manifest.get("item_id") == REGRESSION_ITEM and target_manifest.get("operational_id") == REGRESSION_OPERATIONAL_ID and bool(target) and target["operational_id"] == REGRESSION_OPERATIONAL_ID,
            "regression_ground_lying": len(ground) == 1,
            "regression_at_least_2_unique_people": len(people) >= 2 and len({p["person_id"] for p in people}) == len(people),
            "regression_person_ALERT": target_counts[ALERT] >= 1,
            "regression_image_ALERT": final == ALERT,
        })
        result.update({
            "target_item_id": REGRESSION_ITEM, "target_operational_id": REGRESSION_OPERATIONAL_ID,
            "target_people_count": len(people), "target_unique_person_id_count": len({p["person_id"] for p in people}),
            "target_person_decision_counts": {d: target_counts[d] for d in DECISIONS},
            "target_person_decisions": decisions, "target_final": final,
            "target_image_decision": final, "target_image_reason": target["image_reason"] if target else None,
        })
    result["gate_checks"] = checks
    result["gate"] = "PASS" if all(checks.values()) else "FAIL"
    return result
