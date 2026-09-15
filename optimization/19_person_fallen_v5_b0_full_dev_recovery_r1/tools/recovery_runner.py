"""Main-agent-only V5-B0 full-DEV recovery runner.

The semantic implementation is imported directly from the immutable V5-B0
candidate (stage 17). This runner only repairs execution bookkeeping and adds
no semantic rule, prompt, model, detector, or image transformation.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
V5_ROOT = BASE / "17_person_fallen_v5_target_attributes"
ADAPTER_DIR = ROOT / "adapters"
V5_CONTRACTS_PATH = V5_ROOT / "tools/contracts.py"
V5_POLICY_PATH = V5_ROOT / "policy/target_policy.py"
V5_PROMPT = V5_ROOT / "prompt/target_attributes.txt"
V5_SCHEMA = V5_ROOT / "schema/target_attributes.json"
FREEZE_PATH = ROOT / "freeze/RECOVERY_FREEZE.json"
FREEZE_SHA_PATH = ROOT / "freeze/RECOVERY_FREEZE.sha256"
FULL_MANIFEST_PATH = ROOT / "manifests/full_dev_manifest.json"
NEW_MANIFEST_PATH = ROOT / "manifests/new321_manifest.json"
REUSE_RECORDS_PATH = ROOT / "manifests/reuse115_records.json"

ENDPOINT = "http://192.168.20.62:11434"
MODEL = "qwen3.5:4b"
DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
OLLAMA_VERSION = "0.23.2"
MODEL_OPTIONS = {
    "endpoint": ENDPOINT,
    "name": MODEL,
    "digest": DIGEST,
    "ollama_version": OLLAMA_VERSION,
    "think": False,
    "stream": False,
    "temperature": 0,
    "num_ctx": 8192,
    "num_predict": 768,
    "concurrency": 1,
    "timeout_seconds": 120,
    "automatic_retry": False,
    "resend_completion_unknown": False,
    "api": "/api/generate",
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"blank JSONL line: {path}:{line_number}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line is not object: {path}:{line_number}")
            rows.append(value)
    return rows


def write_exclusive(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def replace_json(path: Path, value: Any) -> None:
    """Replace a mutable progress/report file, never a request/raw/source file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_bytes_exclusive(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Names are deliberately unique and point to stage 17 absolute files.
V5_CONTRACTS = load_module("person_fallen_v5_b0_original_contracts_recovery_r1", V5_CONTRACTS_PATH)
V5_POLICY = load_module("person_fallen_v5_b0_original_policy_recovery_r1", V5_POLICY_PATH)

# Local metric module is mutable only before freeze and is frozen before formal execution.
sys.path.insert(0, str(ROOT / "tools"))
from full_dev_metrics import early_stop_trigger, summarize_complete, summarize_partial, validate_manifest  # noqa: E402


class ProtocolIncomplete(RuntimeError):
    pass


class EarlyStop(RuntimeError):
    def __init__(self, trigger: str, summary: dict[str, Any]):
        super().__init__(trigger)
        self.trigger = trigger
        self.summary = summary


def verify_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"input SHA mismatch: {path}")


def verify_recovery_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.is_file() or not FREEZE_SHA_PATH.is_file():
        raise ValueError("recovery freeze missing")
    if sha256(FREEZE_PATH) != FREEZE_SHA_PATH.read_text(encoding="utf-8").strip():
        raise ValueError("recovery freeze SHA mismatch")
    freeze = read_json(FREEZE_PATH)
    if freeze.get("status") != "IMMUTABLE_RECOVERY_FREEZE":
        raise ValueError("recovery freeze status mismatch")
    if freeze.get("candidate") != "V5-B0-TARGET-ATTRIBUTES":
        raise ValueError("recovery candidate mismatch")
    if freeze.get("execution_id") != "PERSON_FALLEN_V5_B0_FULL_DEV_RECOVERY_R1_20260909":
        raise ValueError("recovery execution identity mismatch")
    if freeze.get("model") != MODEL_OPTIONS:
        raise ValueError("recovery model/options mismatch")
    if freeze.get("budget") != {"reused": 115, "new_max": 321, "full_dev_total": 436}:
        raise ValueError("recovery budget mismatch")
    bindings = freeze.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise ValueError("recovery freeze bindings missing")
    for path_text, expected in bindings.items():
        verify_hash(Path(path_text), expected)
    return freeze


def check_runtime_preflight() -> dict[str, Any]:
    """Direct GET snapshots. /api/ps is recorded but not a cross-time identity gate."""
    snapshots: dict[str, Any] = {"captured_at_utc": utc(), "endpoint": ENDPOINT}
    for suffix in ("tags", "version", "ps"):
        completed = subprocess.run(
            ["curl", "--noproxy", "*", "-fsS", "--max-time", "10", ENDPOINT + "/api/" + suffix],
            check=True,
            capture_output=True,
        )
        raw = completed.stdout.decode("utf-8")
        snapshots[suffix + "_raw"] = raw
        snapshots[suffix] = json.loads(raw)
    models = [item for item in snapshots["tags"].get("models", []) if isinstance(item, dict) and item.get("name") == MODEL]
    if len(models) != 1 or models[0].get("digest") != DIGEST:
        raise ValueError("Ollama model name/digest mismatch")
    if snapshots["version"].get("version") != OLLAMA_VERSION:
        raise ValueError("Ollama version mismatch")
    snapshots["selected_model"] = models[0]
    snapshots["status"] = "PASS"
    return snapshots


def build_payload(prompt: str, schema: dict[str, Any], image_bytes: list[bytes]) -> bytes:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "images": [base64.b64encode(image).decode("ascii") for image in image_bytes],
        "think": False,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 768},
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def call_model(payload: bytes) -> dict[str, Any]:
    started = time.monotonic()
    req = request.Request(
        ENDPOINT + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    raw = b""
    try:
        # Empty ProxyHandler and no redirect handler ensure direct endpoint use.
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, *_args, **_kwargs):
                return None
        opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=120) as response:
            raw = response.read()
            return {"http_status": response.status, "raw": raw, "latency_seconds": time.monotonic() - started, "completion_unknown": False, "transport_error": None}
    except error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:
            raw = b""
        return {"http_status": exc.code, "raw": raw, "latency_seconds": time.monotonic() - started, "completion_unknown": False, "transport_error": repr(exc)}
    except (error.URLError, TimeoutError, OSError) as exc:
        return {"http_status": None, "raw": raw, "latency_seconds": time.monotonic() - started, "completion_unknown": True, "transport_error": repr(exc)}


def load_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_input_row(row: dict[str, Any]) -> None:
    if row.get("phase") != "full_dev":
        raise ValueError(f"unexpected row phase: {row.get('item_id')}")
    if row.get("result_source") != "NEW_INFERENCE":
        raise ValueError(f"runner received non-new row: {row.get('item_id')}")
    for path_key, hash_key in (("image_path", "image_sha256"), ("prompt_path", "prompt_sha256"), ("full_view_path", "full_view_sha256"), ("crop_view_path", "crop_view_sha256")):
        verify_hash(Path(row[path_key]), row[hash_key])
    if row.get("v3_split") != "V3_DEV":
        raise ValueError(f"non-DEV row: {row.get('item_id')}")
    if "VAL" in str(row.get("source_split", "")).upper() or "HOLDOUT" in str(row.get("source_split", "")).upper():
        raise ValueError(f"forbidden split: {row.get('item_id')}")
    expected_views = 2 if row.get("person_detected") == "true" else 1
    if int(row.get("view_count", -1)) != expected_views:
        raise ValueError(f"view count mismatch: {row.get('item_id')}")


def _normalize_reuse(records: list[dict[str, Any]], full_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    full = {row["item_id"]: row for row in full_manifest}
    if len(records) != 115:
        raise ValueError("reuse records are not 115")
    result = []
    for record in records:
        item = record.get("item_id")
        if item not in full:
            raise ValueError(f"reuse item absent from full manifest: {item}")
        row = full[item]
        if record.get("result_source") != "REUSE_V5_B0_PILOT" or record.get("inference_source") != "REUSE_V5_B0_PILOT":
            raise ValueError(f"reuse source marker mismatch: {item}")
        for key in ("request_id", "operational_id", "taxonomy", "group_id", "source_split", "v3_split", "evaluation_stratum", "source_image_sha256", "full_view_sha256", "crop_view_sha256", "person_detected", "view_count"):
            if key in row and key in record:
                expected = int(record[key]) if key == "view_count" else record[key]
                actual = int(row[key]) if key == "view_count" else row[key]
                # Reuse record request_id is original pilot ID while manifest also preserves it.
                if expected != actual:
                    raise ValueError(f"reuse/full mismatch {key}: {item}")
        if record.get("strict_json_ok") is not True or record.get("source_binding_ok") is not True:
            raise ValueError(f"reuse validity mismatch: {item}")
        result.append(record)
    if len({record["item_id"] for record in result}) != 115:
        raise ValueError("duplicate reuse item")
    return result


def _persist_output_line(path: Path, record: dict[str, Any]) -> None:
    append_jsonl(path, record)


def _write_predictions(path: Path, outputs: list[dict[str, Any]]) -> None:
    fields = [
        "item_id", "request_id", "operational_id", "evaluation_stratum", "result_source", "inference_source",
        "taxonomy", "group_id", "source_split", "v3_split", "source_image_sha256", "full_view_sha256",
        "crop_view_sha256", "person_detected", "view_count", "source_binding_ok", "strict_json_ok",
        "parsed_json", "person_decisions_json", "image_decision", "image_reason", "latency_seconds",
        "latency_source", "eval_count", "original_request_id", "original_raw_response_sha256",
    ]
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in outputs:
            writer.writerow({
                "item_id": row.get("item_id"), "request_id": row.get("request_id"), "operational_id": row.get("operational_id"),
                "evaluation_stratum": row.get("evaluation_stratum"), "result_source": row.get("result_source"), "inference_source": row.get("inference_source"),
                "taxonomy": row.get("taxonomy"), "group_id": row.get("group_id"), "source_split": row.get("source_split"), "v3_split": row.get("v3_split"),
                "source_image_sha256": row.get("source_image_sha256"), "full_view_sha256": row.get("full_view_sha256"), "crop_view_sha256": row.get("crop_view_sha256"),
                "person_detected": row.get("person_detected"), "view_count": row.get("view_count"), "source_binding_ok": row.get("source_binding_ok"),
                "strict_json_ok": row.get("strict_json_ok"), "parsed_json": json.dumps(row.get("parsed"), ensure_ascii=False, separators=(",", ":")),
                "person_decisions_json": json.dumps(row.get("person_decisions"), ensure_ascii=False, separators=(",", ":")), "image_decision": row.get("image_decision"),
                "image_reason": row.get("image_reason"), "latency_seconds": row.get("latency_seconds"), "latency_source": row.get("latency_source", "NEW_INFERENCE"),
                "eval_count": row.get("eval_count"), "original_request_id": row.get("original_request_id", ""), "original_raw_response_sha256": row.get("original_raw_response_sha256", ""),
            })
        handle.flush()
        os.fsync(handle.fileno())


def execute_full_dev(
    *,
    output_run_dir: Path,
    transport: Callable[[bytes, str, dict[str, Any]], dict[str, Any]] | None = None,
    preflight: Callable[[], dict[str, Any]] | None = None,
    enforce_recovery_freeze: bool = True,
) -> dict[str, Any]:
    """Execute exactly the fixed full-DEV extension, or a fully simulated copy.

    Formal invocation uses the default root, direct Ollama transport, and freeze
    enforcement. Tests inject a fake transport and a temporary output directory;
    they still consume the real recovery manifests and reuse records.
    """
    if output_run_dir.exists():
        raise ValueError("existing full-DEV execution; overwrite/resume forbidden")
    if enforce_recovery_freeze:
        freeze = verify_recovery_freeze()
    else:
        freeze = {"model": MODEL_OPTIONS, "status": "TEST_ONLY_NO_FREEZE"}
    full_manifest = read_json(FULL_MANIFEST_PATH)
    new_manifest = read_json(NEW_MANIFEST_PATH)
    manifest_errors = validate_manifest(full_manifest)
    if manifest_errors:
        raise ValueError(f"unified manifest invalid: {manifest_errors[:3]}")
    if len(new_manifest) != 321 or any(row.get("result_source") != "NEW_INFERENCE" for row in new_manifest):
        raise ValueError("new321 manifest invalid")
    if [row["request_id"] for row in new_manifest] != [f"V5_B0_FULLDEV_EXTENSION_{i:04d}" for i in range(1, 322)]:
        raise ValueError("new request order/IDs invalid")
    reuse_records, _ = load_reuse_from_materialized()
    reuse_records = _normalize_reuse(reuse_records, full_manifest)
    outputs = list(reuse_records)
    new_records: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    # Create the stage parent and then the stage/request directories before any claim.
    output_run_dir.parent.mkdir(parents=True, exist_ok=True)
    output_run_dir.mkdir(parents=False, exist_ok=False)
    requests_dir = output_run_dir / "requests"
    requests_dir.mkdir(parents=False, exist_ok=False)
    write_exclusive(output_run_dir / "STARTED.lock", {"status": "ACTIVE", "started_at_utc": utc(), "resend_forbidden": True, "expected_new_requests": 321})
    output_jsonl = output_run_dir / "output.jsonl"
    events_jsonl = output_run_dir / "request_events.jsonl"
    for record in reuse_records:
        _persist_output_line(output_jsonl, record)
    replace_json(output_run_dir / "partial_metrics.json", summarize_partial(full_manifest, outputs, [], attempted_count=0))
    if preflight is not None:
        # Runtime snapshot is an output artifact, not a frozen source and not a /api/ps hard gate.
        write_exclusive(output_run_dir / "runtime_preflight.json", preflight())
    prompt = V5_PROMPT.read_text(encoding="utf-8")
    schema = read_json(V5_SCHEMA)
    call = transport
    if call is None:
        call = lambda payload, _request_id, _row: call_model(payload)  # noqa: E731
    try:
        for row in new_manifest:
            validate_input_row(row)
            request_id = row["request_id"]
            view_bytes = [Path(row["full_view_path"]).read_bytes()]
            if row["person_detected"] == "true":
                view_bytes.append(Path(row["crop_view_path"]).read_bytes())
            payload = build_payload(prompt, schema, view_bytes)
            request_dir = requests_dir / request_id
            request_dir.mkdir(parents=False, exist_ok=False)
            claim = {
                "state": "claimed", "phase": "full_dev_extension", "request_id": request_id,
                "item_id": row["item_id"], "operational_id": row["operational_id"], "evaluation_stratum": row["evaluation_stratum"],
                "source_image_sha256": row["image_sha256"], "full_view_sha256": row["full_view_sha256"], "crop_view_sha256": row["crop_view_sha256"],
                "view_count": int(row["view_count"]), "view_order": ["full_scene", "person_crop"] if row["person_detected"] == "true" else ["full_scene"],
                "prompt_sha256": sha256(V5_PROMPT), "schema_sha256": sha256(V5_SCHEMA), "policy_sha256": sha256(V5_POLICY_PATH),
                "contracts_sha256": sha256(V5_CONTRACTS_PATH), "model": MODEL_OPTIONS, "freeze_sha256": sha256(FREEZE_PATH) if FREEZE_PATH.exists() else None,
                "payload_sha256": hashlib.sha256(payload).hexdigest(), "claimed_timestamp": utc(),
            }
            write_exclusive(request_dir / "claimed.json", claim)
            append_jsonl(events_jsonl, claim)
            result = call(payload, request_id, row)
            raw = result.get("raw", b"")
            if not isinstance(raw, bytes):
                raw = bytes(raw)
            write_bytes_exclusive(request_dir / "response.raw", raw)
            transport_record = {
                **claim, "state": "received", "http_status": result.get("http_status"), "latency_seconds": result.get("latency_seconds"),
                "completion_unknown": result.get("completion_unknown"), "transport_error": result.get("transport_error"),
                "raw_response_sha256": sha256(request_dir / "response.raw"), "raw_response_path": str(request_dir / "response.raw"), "received_timestamp": utc(),
            }
            write_exclusive(request_dir / "transport.json", transport_record)
            attempts.append(transport_record)
            if result.get("completion_unknown") or result.get("http_status") != 200:
                failure = {**transport_record, "state": "protocol_failure", "failure_code": "COMPLETION_UNKNOWN" if result.get("completion_unknown") else "HTTP_FAILURE", "failure_timestamp": utc()}
                write_exclusive(request_dir / "failure.json", failure)
                append_jsonl(events_jsonl, failure)
                replace_json(output_run_dir / "partial_metrics.json", summarize_partial(full_manifest, outputs, new_records, attempted_count=len(attempts), protocol_failures=[failure]))
                raise ProtocolIncomplete("V5_B0_FULL_DEV_PROTOCOL_INCOMPLETE_NO_RETRY")
            try:
                outer, parsed = V5_CONTRACTS.parse_response(raw)
            except Exception as exc:
                failure = {**transport_record, "state": "protocol_failure", "failure_code": "STRICT_JSON_OR_SCHEMA_FAILURE", "parse_error": str(exc), "failure_timestamp": utc()}
                write_exclusive(request_dir / "failure.json", failure)
                append_jsonl(events_jsonl, failure)
                replace_json(output_run_dir / "partial_metrics.json", summarize_partial(full_manifest, outputs, new_records, attempted_count=len(attempts), protocol_failures=[failure]))
                raise ProtocolIncomplete("V5_B0_FULL_DEV_PROTOCOL_INCOMPLETE_NO_RETRY")
            decision = V5_POLICY.evaluate(parsed)
            completed = {
                **claim, "state": "completed", "inference_source": "NEW_INFERENCE", "result_source": "NEW_INFERENCE",
                "item_id": row["item_id"], "operational_id": row["operational_id"], "taxonomy": row["taxonomy"], "group_id": row["group_id"],
                "source_split": row["source_split"], "v3_split": row["v3_split"], "ground_truth": row["ground_truth"], "expected_v4_outcome": row["expected_v4_outcome"],
                "evaluation_stratum": row["evaluation_stratum"], "source_image_sha256": row["image_sha256"], "image_sha256": row["image_sha256"],
                "full_view_sha256": row["full_view_sha256"], "crop_view_sha256": row["crop_view_sha256"], "person_detected": row["person_detected"], "view_count": int(row["view_count"]),
                "source_binding_ok": True, "strict_json_ok": True, "done": outer.get("done"), "done_reason": outer.get("done_reason"), "eval_count": outer.get("eval_count"),
                "parsed": parsed, **decision, "http_status": result["http_status"], "completion_unknown": False, "transport_error": None,
                "raw_response_sha256": transport_record["raw_response_sha256"], "raw_response_path": transport_record["raw_response_path"],
                "latency_seconds": float(result["latency_seconds"]), "latency_source": "NEW_INFERENCE", "received_timestamp": transport_record["received_timestamp"],
                "completed_timestamp": utc(), "EVALUATION_MODE": "SAME_V5_B0_EXACT_RESULT_REUSE_PLUS_NEW_INFERENCE", "LEGACY_V4_CACHE_USED_FOR_DECISION": False,
                "CACHED_PRIMARY_USED_FOR_FINAL_DECISION": False,
            }
            write_exclusive(request_dir / "completed.json", completed)
            append_jsonl(events_jsonl, completed)
            new_records.append(completed)
            outputs.append(completed)
            _persist_output_line(output_jsonl, completed)
            partial = summarize_partial(full_manifest, outputs, new_records, attempted_count=len(attempts))
            replace_json(output_run_dir / "partial_metrics.json", partial)
            trigger = early_stop_trigger(full_manifest, outputs)
            if trigger:
                stop = {"status": "V5_B0_FULL_DEV_EARLY_GATE_FAIL", "trigger": trigger, "new_requests_claimed": len(attempts), "new_requests_completed": len(new_records), "new_requests_unknown": 0, "new_requests_not_started": 321 - len(attempts), "partial_summary": partial, "timestamp": utc()}
                write_exclusive(output_run_dir / "EARLY_STOP.json", stop)
                append_jsonl(events_jsonl, {"state": "early_stop", **stop})
                raise EarlyStop(trigger, partial)
            print(f"[{len(new_records)}/321] {request_id} {row['evaluation_stratum']} -> {completed['image_decision']}", flush=True)
        # Only after all 321 new rows are completed can complete metrics be formed.
        complete = summarize_complete(full_manifest, outputs, new_records)
        replace_json(output_run_dir / "summary.json", complete)
        _write_predictions(output_run_dir / "predictions.csv", outputs)
        lock = {"status": "COMPLETE", "gate": complete["FULL_DEV_GATE"], "summary_sha256": sha256(output_run_dir / "summary.json"), "predictions_sha256": sha256(output_run_dir / "predictions.csv"), "reused_results": 115, "new_requests": 321, "completed_at_utc": utc()}
        write_exclusive(output_run_dir / "COMPLETION_LOCK.json", lock)
        return complete
    except EarlyStop:
        raise
    except ProtocolIncomplete as exc:
        protocol = {"status": "V5_B0_FULL_DEV_PROTOCOL_INCOMPLETE_NO_RETRY", "error": str(exc), "new_requests_claimed": len(attempts), "new_requests_completed": len(new_records), "new_requests_unknown": sum(item.get("completion_unknown") is True for item in attempts), "new_requests_not_started": 321 - len(attempts), "completed_full_dev": False, "timestamp": utc()}
        if not (output_run_dir / "PROTOCOL_INCOMPLETE.json").exists():
            write_exclusive(output_run_dir / "PROTOCOL_INCOMPLETE.json", protocol)
        raise
    except Exception:
        # Preserve an explicit failure marker without pretending it is a model result.
        if not (output_run_dir / "RUNNER_ERROR.json").exists():
            write_exclusive(output_run_dir / "RUNNER_ERROR.json", {"status": "RUNNER_ERROR_NO_RESUME", "new_requests_claimed": len(attempts), "new_requests_completed": len(new_records), "timestamp": utc()})
        raise


def load_reuse_from_materialized() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not REUSE_RECORDS_PATH.is_file():
        raise ValueError("materialized reuse records missing")
    records = read_json(REUSE_RECORDS_PATH)
    # Adapter replays original parser/policy and all 505 V5 bindings.
    sys.path.insert(0, str(ADAPTER_DIR))
    from reuse_v5_b0 import load_reuse_records  # noqa: E402
    replayed, freeze = load_reuse_records()
    if json.dumps(records, ensure_ascii=False, sort_keys=True, allow_nan=False) != json.dumps(replayed, ensure_ascii=False, sort_keys=True, allow_nan=False):
        raise ValueError("materialized reuse records differ from direct V5-B0 replay")
    return records, freeze


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", nargs="?", default="full_dev")
    args = parser.parse_args()
    if args.stage != "full_dev":
        print(json.dumps({"status": "UNAUTHORIZED_STAGE", "allowed": ["full_dev"], "requested": args.stage}), file=sys.stderr)
        return 2
    try:
        check = check_runtime_preflight()
        result = execute_full_dev(output_run_dir=ROOT / "eval/full_dev", preflight=lambda: check, enforce_recovery_freeze=True)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except EarlyStop as exc:
        print(json.dumps({"status": "V5_B0_FULL_DEV_EARLY_GATE_FAIL", "trigger": exc.trigger, "summary": exc.summary}, ensure_ascii=False), file=sys.stderr)
        return 3
    except ProtocolIncomplete as exc:
        print(json.dumps({"status": "V5_B0_FULL_DEV_PROTOCOL_INCOMPLETE_NO_RETRY", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4
    except Exception as exc:
        print(json.dumps({"status": "FAILED_BEFORE_OR_DURING_EXECUTION", "error": repr(exc)}, ensure_ascii=False), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
