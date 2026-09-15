#!/usr/bin/env python3
"""Read-only P2L preflight collector.

This script intentionally performs no server-side mutation. It records the
formal dataset validator, the fixed 11434 Ollama identity, and best-effort
read-only SSH inventories. SSH authentication failure is recorded as an
evidence-limited condition rather than treated as permission to modify the
remote host.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2 = BASE / "05_p2_hard_negative_semantic_optimization"
OUT = BASE / "06_p2l_remote_latency_forensics" / "00_preflight"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ENDPOINT = "http://192.168.20.62:11434"
EXPECTED_MODEL = "qwen3.5:4b"
EXPECTED_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fetch(path: str, timeout: float = 20.0) -> dict:
    url = ENDPOINT + path
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            parsed = json.loads(body.decode("utf-8"))
            return {
                "captured_at_utc": now(),
                "url": url,
                "http_code": int(resp.status),
                "body": parsed,
            }
    except Exception as exc:  # evidence must include failures, not hide them
        return {
            "captured_at_utc": now(),
            "url": url,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def ssh_inventory(command: str) -> tuple[int, str, str]:
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=no",
        "tiga@192.168.20.62",
        command,
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=25)
    return proc.returncode, proc.stdout, proc.stderr


def save_inventory(name: str, command: str) -> dict:
    rc, stdout, stderr = ssh_inventory(command)
    text = (
        f"captured_at_utc={now()}\n"
        f"target=tiga@192.168.20.62\n"
        f"command={command}\n"
        f"returncode={rc}\n"
        "--- stdout ---\n"
        f"{stdout}"
        "--- stderr ---\n"
        f"{stderr}"
    )
    (OUT / name).write_text(text)
    return {"file": name, "command": command, "returncode": rc, "stderr": stderr.strip()}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    version = fetch("/api/version", timeout=10)
    tags = fetch("/api/tags", timeout=20)
    ps = fetch("/api/ps", timeout=10)
    write_json(OUT / "ollama_version.json", version)
    write_json(OUT / "ollama_tags.json", tags)
    write_json(OUT / "ollama_ps_initial.json", ps)

    validator = subprocess.run(
        [sys.executable, str(DATASET / "tools/validate_dataset.py"), "--json"],
        cwd=str(DATASET),
        capture_output=True,
        text=True,
        timeout=180,
    )
    (OUT / "dataset_validator.json").write_text(validator.stdout)
    (OUT / "dataset_validator_stderr.txt").write_text(validator.stderr)

    inventories = [
        save_inventory(
            "gpu_inventory.txt",
            "nvidia-smi -L; nvidia-smi --query-gpu=index,uuid,name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free --format=csv",
        ),
        save_inventory(
            "gpu_processes_initial.txt",
            "nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv",
        ),
        save_inventory(
            "ollama_process_inventory.txt",
            "ps -eo pid,ppid,lstart,etime,cmd | grep -i '[o]llama'",
        ),
        save_inventory(
            "ollama_service_inventory.txt",
            "systemctl list-units --type=service --all | grep -i ollama",
        ),
    ]

    source_paths = {
        "p2_c3_prompt": P2 / "05_winner_freeze/p2_winner_prompt.txt",
        "p2_config": P2 / "03_candidates/p2_request_config.json",
        "p2_winner_config": P2 / "05_winner_freeze/p2_winner_config.json",
        "p2_runner": BASE / "tools/p2_inference_runner.py",
        "p2_materializer": BASE / "tools/p2_materialize_results.py",
        "p2_winner_freeze": P2 / "05_winner_freeze/p2_winner_freeze.json",
        "p2_screen_manifest": P2 / "01_internal_split/p2_screen_manifest.csv",
        "p2_val_manifest": BASE / "04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv",
        "p2_screen_predictions": P2 / "04_screening/C3/predictions.csv",
        "p2_screen_raw": P2 / "04_screening/C3/raw_responses.jsonl",
        "p2_screen_request_log": P2 / "04_screening/C3/request_log.jsonl",
        "p2_val_predictions": P2 / "06_val/predictions.csv",
        "p2_val_raw": P2 / "06_val/raw_responses.jsonl",
        "p2_val_request_log": P2 / "06_val/request_log.jsonl",
    }
    source_hashes = {}
    for key, path in source_paths.items():
        source_hashes[key] = {
            "path": str(path),
            "exists": path.exists(),
            "sha256": sha256(path) if path.exists() else None,
        }
    write_json(
        OUT / "source_hash_inventory.json",
        {"captured_at_utc": now(), "source_hashes": source_hashes},
    )

    models = tags.get("body", {}).get("models", []) if isinstance(tags.get("body"), dict) else []
    matching = [m for m in models if m.get("name") == EXPECTED_MODEL or m.get("model") == EXPECTED_MODEL]
    current_digest = matching[0].get("digest") if matching else None
    summary = {
        "captured_at_utc": now(),
        "endpoint": ENDPOINT,
        "endpoint_port": 11434,
        "expected_model": EXPECTED_MODEL,
        "expected_digest": EXPECTED_DIGEST,
        "observed_matching_models": matching,
        "model_identity_match": bool(matching and current_digest == EXPECTED_DIGEST),
        "dataset_validator_returncode": validator.returncode,
        "ssh_read_only_inventories": inventories,
        "ssh_access": all(item["returncode"] == 0 for item in inventories),
        "new_val_requests_allowed": False,
        "holdout_requests_allowed": False,
        "server_mutation_performed": False,
    }
    write_json(OUT / "preflight_summary.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # A changed model identity is a hard gate for new probes. Historical
    # analysis can still proceed, so the caller can inspect this output.
    return 0 if summary["model_identity_match"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
