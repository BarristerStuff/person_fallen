"""Read-only, fail-closed adapter for the already completed V5-B0 pilot.

This module deliberately imports the semantic parser and policy from the original
V5-B0 directory by absolute path. It never calls a model and never reads VAL or
Holdout resources.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

RECOVERY_ROOT = Path(__file__).resolve().parents[1]
BASE = RECOVERY_ROOT.parent
V5_ROOT = BASE / "17_person_fallen_v5_target_attributes"
V13_ROOT = BASE / "13_person_fallen_v4_pose_attributes"
V5_FREEZE = V5_ROOT / "freeze/EXECUTION_FREEZE.json"
V5_FREEZE_SHA = V5_ROOT / "freeze/EXECUTION_FREEZE.sha256"
PILOT_MANIFEST = V5_ROOT / "manifests/pilot115.csv"
PILOT_OUTPUT_JSONL = V5_ROOT / "eval/pilot/output.jsonl"
PILOT_PREDICTIONS = V5_ROOT / "eval/pilot/predictions.csv"
PILOT_LOCK = V5_ROOT / "eval/pilot/COMPLETION_LOCK.json"
PILOT_SUMMARY = V5_ROOT / "eval/pilot/summary.json"
PILOT_REQUESTS = V5_ROOT / "eval/pilot/requests"
FULL_MANIFEST = V13_ROOT / "manifests/v4_full_dev_436.csv"
FULL_CROP_MANIFEST = V13_ROOT / "manifests/v4_full_dev_crop_manifest.csv"

STRATUM_MAP = {
    "ALERT_GROUND_LYING": "ground_lying",
    "NO_ALERT_NORMAL_POSE": "normal_negative",
    "ATTENTION_NEAR_GROUND": "auxiliary_attention",
    "RECHECK_VISUAL_UNCERTAIN": "visual_uncertain",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"blank JSONL line at {path}:{line_number}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line is not an object at {path}:{line_number}")
            rows.append(value)
    return rows


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_semantics():
    # Unique names prevent accidental same-name module collisions with recovery code.
    contracts = load_module("v5b_original_contracts_recovery", V5_ROOT / "tools/contracts.py")
    policy = load_module("v5b_original_target_policy_recovery", V5_ROOT / "policy/target_policy.py")
    return contracts, policy


def verify_v5_freeze() -> dict[str, Any]:
    freeze = read_json(V5_FREEZE)
    expected_freeze_hash = V5_FREEZE_SHA.read_text(encoding="utf-8").strip()
    actual_freeze_hash = sha256(V5_FREEZE)
    if expected_freeze_hash != actual_freeze_hash:
        raise ValueError("V5-B0 freeze SHA file mismatch")
    if freeze.get("candidate") != "V5-B0-TARGET-ATTRIBUTES":
        raise ValueError("unexpected V5-B0 candidate")
    if freeze.get("status") != "IMMUTABLE_EXECUTION_FREEZE":
        raise ValueError("V5-B0 freeze is not immutable")
    if freeze.get("EVALUATION_MODE") != "NEW_TARGET_ATTRIBUTES_ONLY":
        raise ValueError("V5-B0 evaluation mode mismatch")
    if freeze.get("CACHED_PRIMARY_USED_FOR_FINAL_DECISION") is not False:
        raise ValueError("V5-B0 cache decision flag mismatch")
    if freeze.get("budget", {}).get("pilot") != 115:
        raise ValueError("V5-B0 pilot budget mismatch")
    model = freeze.get("model", {})
    expected = {
        "endpoint": "http://192.168.20.62:11434",
        "name": "qwen3.5:4b",
        "digest": "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd",
        "ollama_version": "0.23.2",
        "think": False,
        "stream": False,
        "temperature": 0,
        "num_ctx": 8192,
        "num_predict": 768,
        "concurrency": 1,
        "automatic_retry": False,
        "resend_completion_unknown": False,
    }
    for key, value in expected.items():
        if model.get(key) != value:
            raise ValueError(f"V5-B0 model binding mismatch: {key}")
    bindings = freeze.get("bindings")
    if not isinstance(bindings, dict) or len(bindings) != 505:
        raise ValueError("V5-B0 freeze does not contain the expected 505 bindings")
    failures = []
    for path_text, expected_hash in bindings.items():
        path = Path(path_text)
        try:
            actual = sha256(path)
        except OSError as exc:
            failures.append((path_text, "missing", str(exc)))
            continue
        if actual != expected_hash:
            failures.append((path_text, expected_hash, actual))
    if failures:
        raise ValueError(f"V5-B0 freeze binding failures: {failures[:3]}")
    return freeze


def _index(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError(f"{label} duplicate/missing {key}: {value}")
        result[value] = row
    return result


def _same(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True, allow_nan=False) == json.dumps(
        right, ensure_ascii=False, sort_keys=True, allow_nan=False
    )


def _verify_file_hash(path_text: str, expected: str) -> None:
    path = Path(path_text)
    if sha256(path) != expected:
        raise ValueError(f"V5-B0 pilot input hash mismatch: {path}")


def load_reuse_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    freeze = verify_v5_freeze()
    pilot_manifest = read_csv(PILOT_MANIFEST)
    pilot_output = read_jsonl(PILOT_OUTPUT_JSONL)
    pilot_predictions = read_csv(PILOT_PREDICTIONS)
    pilot_lock = read_json(PILOT_LOCK)
    full = _index(read_csv(FULL_MANIFEST), "item_id", "full DEV")
    crop = _index(read_csv(FULL_CROP_MANIFEST), "item_id", "full crop")
    manifest = _index(pilot_manifest, "item_id", "V5-B0 pilot manifest")
    output = _index(pilot_output, "item_id", "V5-B0 pilot output")
    prediction = _index(pilot_predictions, "item_id", "V5-B0 pilot predictions")
    if len(pilot_manifest) != 115 or len(pilot_output) != 115 or len(pilot_predictions) != 115:
        raise ValueError("V5-B0 pilot does not have exactly 115 rows")
    if pilot_lock.get("status") != "COMPLETE" or pilot_lock.get("requests") != 115:
        raise ValueError("V5-B0 pilot completion lock mismatch")
    if sha256(PILOT_SUMMARY) != pilot_lock.get("summary_sha256"):
        raise ValueError("V5-B0 pilot summary lock mismatch")
    if sha256(PILOT_PREDICTIONS) != pilot_lock.get("predictions_sha256"):
        raise ValueError("V5-B0 pilot predictions lock mismatch")
    contracts, policy = load_semantics()
    records: list[dict[str, Any]] = []
    seen_requests: set[str] = set()
    for item_id, source in manifest.items():
        if item_id not in full or item_id not in crop or item_id not in output or item_id not in prediction:
            raise ValueError(f"pilot item missing from one of the bound sources: {item_id}")
        if source.get("v3_split") != "V3_DEV":
            raise ValueError(f"pilot row is not DEV: {item_id}")
        for key in ("image_sha256", "full_view_sha256", "crop_view_sha256", "person_detected", "view_count"):
            if source.get(key) != full[item_id].get(key, source.get(key)):
                # full source does not carry view fields; only compare fields present there.
                if key in full[item_id]:
                    raise ValueError(f"pilot/full source mismatch {key}: {item_id}")
            if key in crop[item_id] and source.get(key) != crop[item_id].get(key):
                raise ValueError(f"pilot/crop source mismatch {key}: {item_id}")
        for path_key, hash_key in (
            ("image_path", "image_sha256"),
            ("prompt_path", "prompt_sha256"),
            ("full_view_path", "full_view_sha256"),
            ("crop_view_path", "crop_view_sha256"),
        ):
            _verify_file_hash(source[path_key], source[hash_key])
        old = output[item_id]
        pred = prediction[item_id]
        request_id = old.get("request_id")
        if not isinstance(request_id, str) or request_id in seen_requests:
            raise ValueError(f"pilot request identity mismatch: {item_id}")
        seen_requests.add(request_id)
        if old.get("state") != "completed" or old.get("http_status") != 200:
            raise ValueError(f"pilot request not completed: {item_id}")
        if old.get("strict_json_ok") is not True or old.get("source_binding_ok") is not True:
            raise ValueError(f"pilot request attestation mismatch: {item_id}")
        if old.get("done") is not True or old.get("done_reason") != "stop":
            raise ValueError(f"pilot completion metadata mismatch: {item_id}")
        if old.get("completion_unknown") is not False or old.get("transport_error") not in (None, ""):
            raise ValueError(f"pilot transport metadata mismatch: {item_id}")
        if old.get("EVALUATION_MODE") != "NEW_TARGET_ATTRIBUTES_ONLY" or old.get("CACHED_PRIMARY_USED_FOR_FINAL_DECISION") is not False:
            raise ValueError(f"pilot mode metadata mismatch: {item_id}")
        if old.get("model_binding") != freeze["model"]:
            raise ValueError(f"pilot model binding mismatch: {item_id}")
        raw_path = Path(old.get("raw_response_path", ""))
        if not raw_path.is_file():
            raise ValueError(f"pilot raw response missing: {item_id}")
        raw_hash = sha256(raw_path)
        if raw_hash != old.get("raw_response_sha256"):
            raise ValueError(f"pilot raw response hash mismatch: {item_id}")
        outer, parsed = contracts.parse_response(raw_path.read_bytes())
        if parsed != old.get("parsed"):
            raise ValueError(f"pilot parsed output mismatch: {item_id}")
        replay = policy.evaluate(parsed)
        saved_replay = {key: old.get(key) for key in ("person_decisions", "image_decision", "image_reason")}
        if replay != saved_replay:
            raise ValueError(f"pilot policy replay mismatch: {item_id}")
        for key in ("item_id", "request_id", "image_decision", "image_reason", "strict_json_ok", "source_binding_ok"):
            if key == "item_id":
                expected = item_id
            elif key == "request_id":
                expected = request_id
            elif key in pred:
                expected = pred[key]
            else:
                continue
            actual = old.get(key)
            if key in pred and key not in ("item_id", "request_id"):
                # CSV stores booleans and JSON values as strings; compare canonical values below.
                if key == "strict_json_ok":
                    if str(actual).lower() != str(expected).lower():
                        raise ValueError(f"pilot CSV mismatch {key}: {item_id}")
                elif key == "source_binding_ok":
                    if str(actual).lower() != str(expected).lower():
                        raise ValueError(f"pilot CSV mismatch {key}: {item_id}")
                elif str(actual) != str(expected):
                    raise ValueError(f"pilot CSV mismatch {key}: {item_id}")
            elif actual != expected:
                raise ValueError(f"pilot output identity mismatch {key}: {item_id}")
        # Verify the request ledger files, without treating the historical regression as pilot.
        request_dir = PILOT_REQUESTS / request_id
        claimed = read_json(request_dir / "claimed.json")
        completed = read_json(request_dir / "completed.json")
        if claimed.get("request_id") != request_id or completed.get("request_id") != request_id:
            raise ValueError(f"pilot request ledger identity mismatch: {item_id}")
        if completed.get("raw_response_sha256") != raw_hash:
            raise ValueError(f"pilot completed/raw hash mismatch: {item_id}")
        if completed.get("parsed") != parsed or completed.get("image_decision") != old.get("image_decision"):
            raise ValueError(f"pilot completed/output mismatch: {item_id}")
        stratum = source.get("experiment_stratum")
        if stratum not in ("ground_lying", "normal_negative"):
            raise ValueError(f"unexpected pilot stratum: {item_id}")
        normalized = {
            "item_id": item_id,
            "operational_id": source.get("operational_id", old.get("operational_id")),
            "taxonomy": source["taxonomy"],
            "group_id": source["group_id"],
            "source_split": source["source_split"],
            "v3_split": source["v3_split"],
            "ground_truth": source["ground_truth"],
            "expected_v4_outcome": source["expected_v4_outcome"],
            "evaluation_stratum": stratum,
            "result_source": "REUSE_V5_B0_PILOT",
            "inference_source": "REUSE_V5_B0_PILOT",
            "request_id": request_id,
            "original_request_id": request_id,
            "source_image_sha256": source["image_sha256"],
            "image_sha256": source["image_sha256"],
            "full_view_sha256": source["full_view_sha256"],
            "crop_view_sha256": source["crop_view_sha256"],
            "view_count": int(source["view_count"]),
            "person_detected": source["person_detected"],
            "prompt_sha256": old["prompt_sha256"],
            "schema_sha256": old["schema_sha256"],
            "person_policy_sha256": old["person_policy_sha256"],
            "scene_aggregation_sha256": old["scene_aggregation_sha256"],
            "model_binding": old["model_binding"],
            "source_binding_ok": True,
            "strict_json_ok": True,
            "parsed": parsed,
            "person_decisions": old["person_decisions"],
            "image_decision": old["image_decision"],
            "image_reason": old["image_reason"],
            "latency_seconds": float(old["latency_seconds"]),
            "latency_source": "HISTORICAL_V5_B0_PILOT",
            "historical_latency_seconds": float(old["latency_seconds"]),
            "eval_count": old.get("eval_count"),
            "original_raw_response_sha256": raw_hash,
            "original_raw_response_path": str(raw_path),
            "EVALUATION_MODE": "SAME_V5_B0_EXACT_RESULT_REUSE_PLUS_NEW_INFERENCE",
            "LEGACY_V4_CACHE_USED_FOR_DECISION": False,
            "CACHED_PRIMARY_USED_FOR_FINAL_DECISION": False,
        }
        # The outer response must itself be complete and the model identity exact.
        if outer.get("done") is not True or outer.get("done_reason") != "stop":
            raise ValueError(f"pilot outer response incomplete: {item_id}")
        records.append(normalized)
    if len(records) != 115:
        raise ValueError("normalized V5-B0 reuse count is not 115")
    return records, freeze
