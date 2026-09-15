#!/usr/bin/env python3
"""Best-effort read-only runtime snapshots for P2L probes.

The endpoint is queried directly on LAN.  Remote GPU/process snapshots use
SSH only for read-only commands.  Authentication failure is recorded as an
evidence limitation; this module never restarts, kills, unloads, or changes a
remote service.
"""

from __future__ import annotations

import csv
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
OUT = ROOT / "06_p2l_remote_latency_forensics/03_runtime_telemetry"
ENDPOINT = "http://192.168.20.62:11434"
SSH_TARGET = "tiga@192.168.20.62"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, obj: object) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()


def ssh_read(command: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=no",
            SSH_TARGET,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=25,
    )
    return proc.returncode, proc.stdout, proc.stderr


def api_ps(probe: str, phase: str) -> None:
    timestamp = utc()
    url = ENDPOINT + "/api/ps"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            append_jsonl(
                OUT / "api_ps_samples.jsonl",
                {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "url": url, "http_code": resp.status, "body": body},
            )
    except Exception as exc:
        append_jsonl(
            OUT / "api_ps_samples.jsonl",
            {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "url": url, "error_type": type(exc).__name__, "error": str(exc)},
        )


def append_csv(path: Path, fields: list[str], row: dict[str, object]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)
        f.flush()


def capture_gpu(probe: str, phase: str) -> None:
    timestamp = utc()
    fields = [
        "timestamp_utc", "probe", "phase", "host", "status", "gpu_index", "gpu_uuid", "name",
        "temperature_gpu", "utilization_gpu", "utilization_memory", "memory_total", "memory_used", "memory_free", "error",
    ]
    rc, out, err = ssh_read("nvidia-smi --query-gpu=index,uuid,name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free --format=csv,noheader,nounits")
    if rc != 0:
        append_csv(OUT / "nvidia_smi_samples.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "unavailable", "error": err.strip()})
        return
    for line in out.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 9:
            append_csv(OUT / "nvidia_smi_samples.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "parse_error", "error": line})
            continue
        append_csv(OUT / "nvidia_smi_samples.csv", fields, dict(zip(fields, [timestamp, probe, phase, SSH_TARGET, "ok", *parts[:9], ""])))


def capture_compute_processes(probe: str, phase: str) -> None:
    timestamp = utc()
    fields = ["timestamp_utc", "probe", "phase", "host", "status", "gpu_uuid", "pid", "process_name", "used_memory", "error"]
    rc, out, err = ssh_read("nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits")
    if rc != 0:
        append_csv(OUT / "process_samples.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "unavailable", "error": err.strip()})
        return
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        append_csv(OUT / "process_samples.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "ok", "error": "no_compute_processes_reported"})
        return
    for line in lines:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 4:
            append_csv(OUT / "process_samples.csv", fields, dict(zip(fields, [timestamp, probe, phase, SSH_TARGET, "ok", *parts[:4], ""])))
        else:
            append_csv(OUT / "process_samples.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "parse_error", "error": line})


def capture_ollama_processes(probe: str, phase: str) -> None:
    timestamp = utc()
    fields = ["timestamp_utc", "probe", "phase", "host", "status", "pid", "ppid", "lstart", "etime", "command", "error"]
    rc, out, err = ssh_read("ps -eo pid,ppid,lstart,etime,cmd | grep -i '[o]llama'")
    if rc != 0:
        append_csv(OUT / "ollama_pid_history.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "unavailable", "error": err.strip()})
        return
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines:
        append_csv(OUT / "ollama_pid_history.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "ok", "error": "no_ollama_process_reported"})
        return
    for line in lines:
        parts = line.split(None, 4)
        if len(parts) >= 5:
            append_csv(OUT / "ollama_pid_history.csv", fields, dict(zip(fields, [timestamp, probe, phase, SSH_TARGET, "ok", *parts[:4], parts[4], ""])))
        else:
            append_csv(OUT / "ollama_pid_history.csv", fields, {"timestamp_utc": timestamp, "probe": probe, "phase": phase, "host": SSH_TARGET, "status": "parse_error", "error": line})


def capture_snapshot(probe: str, phase: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    api_ps(probe, phase)
    capture_gpu(probe, phase)
    capture_compute_processes(probe, phase)
    capture_ollama_processes(probe, phase)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("probe")
    parser.add_argument("phase")
    args = parser.parse_args()
    capture_snapshot(args.probe, args.phase)
