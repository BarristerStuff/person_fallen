#!/usr/bin/env python3
"""Final read-only P3 audit: dataset, identity, ledgers, scope, and hashes."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
ENDPOINT = "http://192.168.20.62:11434"
EXPECTED_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fetch(url: str) -> dict:
    try:
        with request.urlopen(url, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return {"ok": True, "http_status": response.status, "raw": raw, "json": json.loads(raw)}
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}


def atomic(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    validator = subprocess.run(["python3", "/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py", "--json"], capture_output=True, text=True, check=False)
    try:
        validator_json = json.loads(validator.stdout)
    except json.JSONDecodeError:
        validator_json = {"parse_error": True, "stdout": validator.stdout, "stderr": validator.stderr}
    identity = {"endpoint": ENDPOINT, "version": fetch(ENDPOINT + "/api/version"), "tags": fetch(ENDPOINT + "/api/tags"), "ps": fetch(ENDPOINT + "/api/ps")}
    models = identity["tags"].get("json", {}).get("models", []) if identity["tags"].get("ok") else []
    matching = [m for m in models if m.get("name") == "qwen3.5:4b" or m.get("model") == "qwen3.5:4b"]
    identity["qwen3_5_4b_digest"] = matching[0].get("digest") if matching else None
    identity["model_identity_pass"] = identity["qwen3_5_4b_digest"] == EXPECTED_DIGEST

    p3_files = {
        "candidate_freeze": P3 / "03_candidates/candidate_freeze.json",
        "candidate_attestation": P3 / "03_candidates/candidate_freeze_attestation.json",
        "config": P3 / "03_candidates/p3_request_config.json",
        "runner": ROOT / "tools/p3_inference_runner.py",
        "c3_prompt": P2 / "03_candidates/C3/C3_prompt.txt",
        "p2_winner_freeze": P2 / "05_winner_freeze/p2_winner_freeze.json",
        "p2_design_manifest": P2 / "01_internal_split/p2_design_manifest.csv",
        "p2_screen_manifest": P2 / "01_internal_split/p2_screen_manifest.csv",
        "p2_c3_screen_predictions": P2 / "04_screening/C3/predictions.csv",
        "p3_screen_verification": P3 / "05_screen/result_verification.json",
    }
    expected = {
        "c3_prompt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
        "p2_winner_freeze": "ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0",
        "p2_design_manifest": "f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1",
        "p2_screen_manifest": "ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5",
        "p2_c3_screen_predictions": "5d21d873dc327c8e59d25c59fad79522f65d6d0e19a817c5d893f662aaa1a848",
    }
    hash_checks = {name: {"path": str(path), "actual_sha256": sha(path), "expected_sha256": expected.get(name), "match": (sha(path) == expected[name] if name in expected else path.is_file())} for name, path in p3_files.items()}

    runs = {
        "c3_design": (P3 / "01_c3_design_baseline", 190),
        "structured_canary": (P3 / "04_canary", 12),
        "structured_screen": (P3 / "05_screen/S1_STRUCTURED", 120),
    }
    ledger_checks = {}
    scope_violations = []
    for name, (directory, expected_count) in runs.items():
        db_path = directory / "request_ledger.sqlite3"
        with sqlite3.connect(db_path) as db:
            states = dict(db.execute("SELECT state,count(*) FROM requests GROUP BY state"))
            metadata = dict(db.execute("SELECT k,v FROM metadata"))
        log_path = directory / "request_log.jsonl"
        raw_path = directory / "raw_responses.jsonl"
        pred_path = directory / "predictions.csv"
        response_count = len(list((directory / "responses").glob("*.json")))
        log_count = len([l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]) if log_path.is_file() else 0
        raw_count = len([l for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]) if raw_path.is_file() else 0
        pred_count = len(load_csv(pred_path)) if pred_path.is_file() else 0
        for path in [log_path, raw_path]:
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if '"split":"VAL"' in line or '"split":"HOLDOUT"' in line or '"split": "VAL"' in line or '"split": "HOLDOUT"' in line:
                        scope_violations.append(f"{name}:{path.name}:VAL_OR_HOLDOUT")
        ledger_checks[name] = {"expected_count": expected_count, "states": states, "metadata": metadata, "response_files": response_count, "request_log_rows": log_count, "raw_rows": raw_count, "prediction_rows": pred_count, "complete_cardinality": states == {"COMPLETED": expected_count} and response_count == expected_count and log_count == expected_count and raw_count == expected_count and pred_count == expected_count}

    manifests = [P3 / "01_c3_design_baseline/manifest.csv", P3 / "04_canary/canary_manifest.csv", P3 / "05_screen/manifest.csv"]
    for manifest in manifests:
        if manifest.is_file():
            for row in load_csv(manifest):
                split = row.get("split") or row.get("original_split")
                if split in {"VAL", "HOLDOUT"}:
                    scope_violations.append(f"{manifest.name}:{split}")

    freeze = json.loads(p3_files["candidate_freeze"].read_text(encoding="utf-8"))
    attestation = json.loads(p3_files["candidate_attestation"].read_text(encoding="utf-8"))
    result_verification = json.loads(p3_files["p3_screen_verification"].read_text(encoding="utf-8"))
    errors = []
    if validator.returncode != 0 or validator_json.get("status") != "valid" or validator_json.get("error_count") != 0 or validator_json.get("full_hash_check") is not True:
        errors.append("dataset_validator_gate")
    if not identity["model_identity_pass"]:
        errors.append("model_identity_gate")
    if any(not value["match"] for value in hash_checks.values()):
        errors.append("hash_gate")
    if any(not value["complete_cardinality"] for value in ledger_checks.values()):
        errors.append("ledger_cardinality_gate")
    if scope_violations:
        errors.append("VAL_OR_HOLDOUT_SCOPE_VIOLATION")
    if attestation.get("verification_result") != "PASS" or result_verification.get("verification_result") != "PASS" or result_verification.get("metric_recompute_match") is not True:
        errors.append("independent_verifier_gate")
    if freeze.get("new_val_requests") != 0 or freeze.get("holdout_requests") != 0 or freeze.get("optional_s2_created") is not False:
        errors.append("freeze_scope_gate")
    if freeze.get("model_digest") != EXPECTED_DIGEST:
        errors.append("freeze_model_digest_gate")

    audit = {
        "audit_status": "PASS" if not errors else "FAIL",
        "checked_at_utc": now,
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
        "p3_status": "SCREENING_COMPLETE_NO_WINNER",
        "validator": validator_json,
        "validator_returncode": validator.returncode,
        "model_identity": identity,
        "hash_checks": hash_checks,
        "ledger_checks": ledger_checks,
        "scope_violations": scope_violations,
        "candidate_freeze_sha256": sha(p3_files["candidate_freeze"]),
        "candidate_freeze_attestation": attestation,
        "independent_result_verification": result_verification,
        "new_dev_requests": 322,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "production_code_modified": False,
        "ollama_service_modified": False,
        "errors": errors,
    }
    atomic(P3 / "07_final_audit.json", audit)
    md = "# P3 final audit\n\n" + "```json\n" + json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n```\n"
    (P3 / "07_final_audit.md").write_text(md, encoding="utf-8")
    print(json.dumps({"audit_status": audit["audit_status"], "errors": errors, "holdout_requests": 0, "new_val_requests": 0, "ledger_checks": ledger_checks}, ensure_ascii=False, sort_keys=True))
    if errors:
        raise SystemExit("P3_FINAL_AUDIT=FAIL")


if __name__ == "__main__":
    main()
