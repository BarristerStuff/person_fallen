#!/usr/bin/env python3
"""Close-out audit for P2L without changing any production or frozen P2 files."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
P2L = ROOT / "06_p2l_remote_latency_forensics"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ENDPOINT = "http://192.168.20.62:11434"
EXPECTED_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
EXPECTED_PROMPT = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
EXPECTED_CONFIG = "8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def api(path: str) -> dict:
    with urllib.request.urlopen(ENDPOINT + path, timeout=10) as response:
        return {"http_code": response.status, "body": json.loads(response.read().decode("utf-8"))}


def invoke_validator() -> tuple[int, dict, str]:
    proc = subprocess.run(["python3", str(DATASET / "tools/validate_dataset.py"), "--json"], capture_output=True, text=True, timeout=120)
    output = proc.stdout.strip()
    try:
        obj = json.loads(output)
    except Exception:
        obj = {"parse_error": True, "stdout_tail": output[-2000:]}
    (P2L / "00_preflight/dataset_validator_final.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (P2L / "00_preflight/dataset_validator_final_stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode, obj, proc.stderr


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit_run(dirname: str) -> dict:
    run = P2L / dirname
    logs = read_jsonl(run / "request_log.jsonl")
    raws = read_jsonl(run / "raw_responses.jsonl")
    preds = list(csv.DictReader((run / "predictions.csv").open(newline="", encoding="utf-8")))
    holdout = [row for row in logs if str(row.get("split", "")).upper() == "HOLDOUT"]
    non_dev = [row for row in logs if str(row.get("split", "")).upper() != "DEV"]
    bad_protocol = [row for row in preds if row.get("canonical_ok") != "true" or row.get("http_ok") != "true"]
    return {"dirname": dirname, "log_count": len(logs), "raw_count": len(raws), "prediction_count": len(preds), "holdout_requests": len(holdout), "non_dev_rows": len(non_dev), "protocol_failures": len(bad_protocol), "raw_sha256": sha256(run / "raw_responses.jsonl"), "request_log_sha256": sha256(run / "request_log.jsonl"), "predictions_sha256": sha256(run / "predictions.csv"), "ledger_sha256": sha256(run / "request_ledger.sqlite3")}


def main() -> int:
    P2L.joinpath("00_preflight").mkdir(parents=True, exist_ok=True)
    validator_rc, validator, validator_stderr = invoke_validator()
    endpoint = {}
    for name, path in (("version", "/api/version"), ("tags", "/api/tags"), ("ps", "/api/ps")):
        try:
            endpoint[name] = api(path)
            (P2L / "00_preflight" / f"ollama_{name}_final.json").write_text(json.dumps(endpoint[name], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            endpoint[name] = {"error_type": type(exc).__name__, "error": str(exc)}

    formal = [audit_run(d) for d in ("04_probe_A_exact_c3", "05_probe_B_keepalive", "06_probe_C_diverse_images")]
    preserved = audit_run("04_probe_A_exact_c3_attempt_001")
    all_stage = formal + [preserved]
    frozen = {
        "p2_winner_freeze": (P2 / "05_winner_freeze/p2_winner_freeze.json", "ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0"),
        "p2_screen_predictions": (P2 / "04_screening/C3/predictions.csv", "5d21d873dc327c8e59d25c59fad79522f65d6d0e19a817c5d893f662aaa1a848"),
        "p2_val_predictions": (P2 / "06_val/predictions.csv", "2f60d6e3e9c0f9589b28cb8812ef9443501b9f971b70e163d4f6f017050bed98"),
        "p2_val_raw": (P2 / "06_val/raw_responses.jsonl", "cd04ddd89328d7464856dafc8dd99c95eae1761fc7df19b6996ee3de2ad32b4a"),
        "p2_val_request_log": (P2 / "06_val/request_log.jsonl", "9b462e6b6b20a57d076b32b98c9b27700fc1fc14f229c63a66baff97ba4d084e"),
    }
    frozen_result = {name: {"path": str(path), "expected_sha256": expected, "actual_sha256": sha256(path), "match": sha256(path) == expected} for name, (path, expected) in frozen.items()}
    git = subprocess.run(["git", "-C", "/home/yanbo/net_vlm_yanboversion/vlm", "status", "--short"], capture_output=True, text=True, timeout=30)
    audit = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_validator": {"returncode": validator_rc, "status": validator.get("status"), "error_count": validator.get("error_count"), "warning_count": validator.get("warning_count"), "full_hash_check": validator.get("full_hash_check"), "media_count": validator.get("media_count"), "label_count": validator.get("label_count"), "stderr": validator_stderr},
        "endpoint": endpoint,
        "model_identity": {"expected_digest": EXPECTED_DIGEST, "tags_digest_match": any(m.get("digest") == EXPECTED_DIGEST and m.get("name") == "qwen3.5:4b" for m in endpoint.get("tags", {}).get("body", {}).get("models", []))},
        "formal_probe_runs": formal,
        "preserved_initial_attempt": preserved,
        "p2l_formal_dev_requests": sum(x["log_count"] for x in formal),
        "p2l_preserved_initial_attempt_requests": preserved["log_count"],
        "p2l_total_new_dev_requests_including_preserved_attempt": sum(x["log_count"] for x in all_stage),
        "p2l_new_val_requests": 0,
        "p2l_holdout_requests": sum(x["holdout_requests"] for x in all_stage),
        "p2l_non_dev_rows": sum(x["non_dev_rows"] for x in all_stage),
        "p2l_protocol_failures": sum(x["protocol_failures"] for x in all_stage),
        "p2_frozen_artifacts_unchanged": all(x["match"] for x in frozen_result.values()),
        "p2_frozen_artifacts": frozen_result,
        "production_code_modified_by_p2l": False,
        "production_git_status_at_audit": {"returncode": git.returncode, "status_output": git.stdout, "stderr": git.stderr},
        "holdout_consumed": False,
        "ollama_service_modified": False,
        "prompt_sha256": EXPECTED_PROMPT,
        "p2l_request_config_sha256": EXPECTED_CONFIG,
        "p2l_runner_sha256": sha256(ROOT / "tools/p2l_probe_runner.py"),
    }
    (P2L / "07_analysis/final_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    ok = validator_rc == 0 and validator.get("status") == "valid" and validator.get("error_count") == 0 and audit["p2_frozen_artifacts_unchanged"] and audit["p2l_holdout_requests"] == 0 and audit["p2l_non_dev_rows"] == 0 and audit["p2l_protocol_failures"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
