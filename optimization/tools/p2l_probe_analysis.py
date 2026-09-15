#!/usr/bin/env python3
"""Independent P2L probe and historical latency aggregation.

Timing values for the probes are joined from raw response wrappers and request
logs.  The historical rows are the raw-derived, hash-verified breakdowns
emitted by p2l_historical_forensics.py; that script is the source audit for the
historical P2 C3 rows and does not consume predictions/evidence.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2L = ROOT / "06_p2l_remote_latency_forensics"
HIST = P2L / "01_historical_forensics"
OUT = P2L / "07_analysis"
HIGH_LOAD = 5.0
WARM_GATE = 1.852084


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return vals[lo]
    return vals[lo] + (pos - lo) * (vals[hi] - vals[lo])


def stats(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = rank
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    dx, dy = [v - mx for v in rx], [v - my for v in ry]
    den = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy)) / den if den else None


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = list(rows[0].keys()) if rows else ["scope"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_probe(probe: str, dirname: str, manifest_name: str) -> list[dict[str, object]]:
    run_dir = P2L / dirname
    raw_by_id = {}
    for line in (run_dir / "raw_responses.jsonl").read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        raw_by_id[obj["request_id"]] = obj
    logs = [json.loads(line) for line in (run_dir / "request_log.jsonl").read_text(encoding="utf-8").splitlines()]
    manifest = {row["media_id"]: row for row in load_csv(P2L / "02_diagnostic_manifest" / manifest_name)}
    if set(raw_by_id) != {row["request_id"] for row in logs}:
        raise RuntimeError(f"{probe}: raw/log ID mismatch")
    rows: list[dict[str, object]] = []
    for index, log in enumerate(logs, 1):
        raw = raw_by_id[log["request_id"]]
        outer = raw.get("outer_json") or {}
        wrapper_path = run_dir / "responses" / f"{log['request_id']}.json"
        wrapper = json.loads(wrapper_path.read_text(encoding="utf-8")) if wrapper_path.exists() else {}
        media_id = log["media_id"]
        if media_id not in manifest:
            raise RuntimeError(f"{probe}: manifest missing {media_id}")
        m = manifest[media_id]
        payload = log.get("request_payload_config") or {}
        keep_alive = payload.get("keep_alive")
        config_without_keep_alive = dict(payload)
        config_without_keep_alive.pop("keep_alive", None)
        config_fp = hashlib.sha256(json.dumps(config_without_keep_alive, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        durations = {name: outer.get(name) for name in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}
        if any(not isinstance(v, (int, float)) for v in durations.values()):
            raise RuntimeError(f"{probe}: missing duration in {log['request_id']}")
        total = float(durations["total_duration"]) / 1e9
        load = float(durations["load_duration"]) / 1e9
        prompt_eval = float(durations["prompt_eval_duration"]) / 1e9
        evaluation = float(durations["eval_duration"]) / 1e9
        start, end = parse_iso(log["timestamp_start_utc"]), parse_iso(log["timestamp_end_utc"])
        rows.append({
            "source": "probe",
            "dataset": "DEV",
            "probe": probe,
            "request_index": index,
            "request_id": log["request_id"],
            "media_id": media_id,
            "split": log.get("split", "DEV"),
            "sample_role": m.get("sample_role", ""),
            "scenario_id": m.get("scenario_id", ""),
            "group_id": m.get("group_id", ""),
            "timestamp_start_utc": log["timestamp_start_utc"],
            "timestamp_end_utc": log["timestamp_end_utc"],
            "wall_span_seconds": (end - start).total_seconds(),
            "client_latency_seconds": float(log["latency_seconds"]),
            "total_duration_seconds": total,
            "load_duration_seconds": load,
            "prompt_eval_duration_seconds": prompt_eval,
            "eval_duration_seconds": evaluation,
            "client_overhead_seconds": float(log["latency_seconds"]) - total,
            "load_ratio": load / total if total else None,
            "prompt_eval_ratio": prompt_eval / total if total else None,
            "eval_ratio": evaluation / total if total else None,
            "prompt_eval_count": outer.get("prompt_eval_count"),
            "eval_count": outer.get("eval_count"),
            "done": outer.get("done"),
            "done_reason": outer.get("done_reason", ""),
            "http_code": log.get("http_code"),
            "prompt_sha256": hashlib.sha256(str(payload.get("prompt", "")).encode("utf-8")).hexdigest(),
            "config_fingerprint_without_keep_alive": config_fp,
            "keep_alive": keep_alive or "omitted",
            "image_sha256": m["image_sha256"],
            "image_path": m["image_path"],
            "image_bytes": int(wrapper.get("processed_bytes") or log.get("processed_bytes") or 0) if (wrapper.get("processed_bytes") or log.get("processed_bytes")) else None,
            "high_load": load > HIGH_LOAD,
        })
    return rows


def read_historical(dataset: str) -> list[dict[str, object]]:
    path = HIST / ("p2_screen_duration_breakdown.csv" if dataset == "SCREEN" else "p2_val_duration_breakdown.csv")
    rows = []
    for row in load_csv(path):
        rows.append({
            "source": "historical_raw_derived",
            "dataset": dataset,
            "probe": "P2_C3_" + dataset,
            "request_index": int(row["request_index"]),
            "request_id": row["request_id"],
            "media_id": row["media_id"],
            "split": dataset,
            "sample_role": "",
            "scenario_id": "",
            "group_id": "",
            "timestamp_start_utc": row["timestamp_start_utc"],
            "timestamp_end_utc": row["timestamp_end_utc"],
            "wall_span_seconds": float(row["wall_span_seconds"]),
            "client_latency_seconds": float(row["client_latency_seconds"]),
            "total_duration_seconds": float(row["total_duration_seconds"]),
            "load_duration_seconds": float(row["load_duration_seconds"]),
            "prompt_eval_duration_seconds": float(row["prompt_eval_duration_seconds"]),
            "eval_duration_seconds": float(row["eval_duration_seconds"]),
            "client_overhead_seconds": float(row["client_overhead_seconds"]),
            "load_ratio": float(row["load_ratio"]),
            "prompt_eval_ratio": float(row["prompt_eval_ratio"]),
            "eval_ratio": float(row["eval_ratio"]),
            "prompt_eval_count": int(row["prompt_eval_count"]),
            "eval_count": int(row["eval_count"]),
            "done": row["done"],
            "done_reason": row["done_reason"],
            "http_code": row["http_code"],
            "prompt_sha256": row["prompt_sha256"],
            "config_fingerprint_without_keep_alive": row["config_fingerprint"],
            "keep_alive": "historical_omitted",
            "image_sha256": row["image_sha256"],
            "image_path": row["image_path"],
            "image_bytes": int(row["image_bytes"]),
            "high_load": row["high_load"].lower() == "true",
        })
    return rows


def component_rows(scope: str, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    mapping = {
        "client": "client_latency_seconds",
        "total": "total_duration_seconds",
        "load": "load_duration_seconds",
        "prompt_eval": "prompt_eval_duration_seconds",
        "eval": "eval_duration_seconds",
        "client_overhead": "client_overhead_seconds",
        "load_ratio": "load_ratio",
        "prompt_eval_ratio": "prompt_eval_ratio",
        "eval_ratio": "eval_ratio",
    }
    out = []
    for component, key in mapping.items():
        values = [float(row[key]) for row in rows if row[key] is not None]
        s = stats(values)
        out.append({"scope": scope, "component": component, **s})
    return out


def probe_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    prompt_counts = Counter(int(row["prompt_eval_count"]) for row in rows)
    return {
        "count": len(rows),
        "high_load_count": sum(bool(row["high_load"]) for row in rows),
        "protocol_count": len(rows),
        "prompt_eval_count_values": dict(prompt_counts),
        "prompt_eval_count_stable": len(prompt_counts) == 1,
        "components": {name: stats([float(row[key]) for row in rows]) for name, key in {
            "client": "client_latency_seconds", "total": "total_duration_seconds", "load": "load_duration_seconds", "prompt_eval": "prompt_eval_duration_seconds", "eval": "eval_duration_seconds"
        }.items()},
        "first_request": {k: rows[0][k] for k in ("request_index", "media_id", "client_latency_seconds", "load_duration_seconds", "high_load")} if rows else None,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    historical_screen = read_historical("SCREEN")
    historical_val = read_historical("VAL")
    probes = {
        "P2L_A": read_probe("P2L_A", "04_probe_A_exact_c3", "p2l_fixed_image_manifest.csv"),
        "P2L_B": read_probe("P2L_B", "05_probe_B_keepalive", "p2l_fixed_image_manifest.csv"),
        "P2L_C": read_probe("P2L_C", "06_probe_C_diverse_images", "p2l_diverse_manifest.csv"),
    }
    preserved_attempt = read_probe("P2L_A_ATTEMPT_001", "04_probe_A_exact_c3_attempt_001", "p2l_fixed_image_manifest.csv")
    # The time-series artifact is globally ordered by the recorded request
    # start timestamp, not grouped by dataset/probe.
    all_rows = sorted(historical_screen + historical_val + sum(probes.values(), []) + preserved_attempt, key=lambda row: parse_iso(str(row["timestamp_start_utc"])))
    # Remote telemetry was unavailable because SSH authentication failed. Keep
    # explicit alignment columns rather than silently dropping them.
    for row in all_rows:
        row.update({"gpu_memory_used": "unavailable", "gpu_memory_free": "unavailable", "gpu_utilization_gpu": "unavailable", "gpu_utilization_memory": "unavailable", "runner_pid": "unavailable"})
    fields = ["source", "dataset", "probe", "request_index", "request_id", "media_id", "split", "sample_role", "scenario_id", "group_id", "timestamp_start_utc", "timestamp_end_utc", "wall_span_seconds", "client_latency_seconds", "total_duration_seconds", "load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "client_overhead_seconds", "load_ratio", "prompt_eval_ratio", "eval_ratio", "prompt_eval_count", "eval_count", "done", "done_reason", "http_code", "prompt_sha256", "config_fingerprint_without_keep_alive", "keep_alive", "image_sha256", "image_path", "image_bytes", "high_load", "gpu_memory_used", "gpu_memory_free", "gpu_utilization_gpu", "gpu_utilization_memory", "runner_pid"]
    write_csv(OUT / "all_requests.csv", all_rows, fields)
    components = component_rows("HISTORICAL_SCREEN", historical_screen) + component_rows("HISTORICAL_VAL", historical_val)
    for name, rows in {**probes, "P2L_A_ATTEMPT_001": preserved_attempt}.items():
        components.extend(component_rows(name, rows))
    warm_rows = [row for name, rows in probes.items() if name in {"P2L_A", "P2L_C"} for row in rows if not bool(row["high_load"])]
    components.extend(component_rows("CURRENT_C3_WARM_A_LOW_PLUS_C", warm_rows))
    write_csv(OUT / "latency_components.csv", components)

    high_val = [r for r in historical_val if bool(r["high_load"])]
    low_val = [r for r in historical_val if not bool(r["high_load"])]
    historical_anomaly_sustained = any(sum(bool(r["high_load"]) for r in historical_val[i:i+10]) == 10 for i in range(max(0, len(historical_val) - 9)))
    current_high = sum(sum(bool(r["high_load"]) for r in rows) for rows in probes.values())
    current_sustained = any(sum(bool(r["high_load"]) for r in rows[i:i+3]) == 3 for rows in probes.values() for i in range(max(0, len(rows) - 2)))
    warm_stats = stats([float(r["client_latency_seconds"]) for r in warm_rows])
    p2l_summary = {
        "p2l_status": "COMPLETE",
        "p2l_anomaly_reproduced": current_sustained,
        "historical_screen": {"count": len(historical_screen), "high_load_count": sum(bool(r["high_load"]) for r in historical_screen)},
        "historical_val": {"count": len(historical_val), "high_load_count": len(high_val), "low_load_count": len(low_val)},
        "probes": {name: probe_summary(rows) for name, rows in probes.items()},
        "preserved_initial_attempt": probe_summary(preserved_attempt),
        "current_c3_warm_a_low_plus_c": {"count": len(warm_rows), "client": warm_stats, "gate_seconds": WARM_GATE, "gate_pass": bool(warm_stats["p95"] is not None and warm_stats["p95"] <= WARM_GATE)},
        "current_c3_warm_runtime_healthy": bool(warm_stats["p95"] is not None and warm_stats["p95"] <= WARM_GATE),
        "historical_anomaly_currently_not_reproduced": not current_sustained,
        "historical_anomaly_sustained": historical_anomaly_sustained,
        "current_high_load_requests": current_high,
        "current_sustained_high_load": current_sustained,
        "historical_primary_latency_component": "load_duration",
        "prompt_eval_count_historical_values": sorted({int(r["prompt_eval_count"]) for r in historical_screen + historical_val}),
        "prompt_eval_count_probe_values": sorted({int(r["prompt_eval_count"]) for r in sum(probes.values(), [])}),
        "probe_correlations": {
            name: {
                "eval_count_load_spearman": spearman([int(r["eval_count"]) for r in rows], [float(r["load_duration_seconds"]) for r in rows]),
                "image_bytes_load_spearman": spearman([int(r["image_bytes"]) for r in rows if r["image_bytes"] is not None], [float(r["load_duration_seconds"]) for r in rows if r["image_bytes"] is not None]),
            } for name, rows in probes.items()
        },
        "probe_config_fingerprints_without_keep_alive": {name: sorted({str(r["config_fingerprint_without_keep_alive"]) for r in rows}) for name, rows in probes.items()},
        "probe_exact_c3_config_equal_ignoring_keep_alive": len({str(r["config_fingerprint_without_keep_alive"]) for rows in probes.values() for r in rows}) == 1,
        "eval_count_interpretation": "variable generation token count, but eval_duration is sub-second and does not explain the multi-second load-dominated tail",
        "new_val_requests": 0,
        "holdout_requests": 0,
    }
    summary_text = json.dumps(p2l_summary, ensure_ascii=False, indent=2) + "\n"
    (OUT / "forensic_summary.json").write_text(summary_text, encoding="utf-8")
    (OUT / "final_forensic_summary.json").write_text(summary_text, encoding="utf-8")

    hypotheses = [
        {"hypothesis": "H1_model_residency_or_reload_churn", "status": "PARTIALLY_SUPPORTED", "evidence_for": "VAL has 63/100 load>5s with a long high run; /api/ps changed from empty to loaded before/after A; formal A first request load>5s while later A/B/C rows are low", "evidence_against_or_missing": "No remote service/GPU/runner telemetry; current probes do not reproduce a sustained high-load run; B is sequential after A so not causal"},
        {"hypothesis": "H2_gpu_contention_or_vram_pressure", "status": "UNRESOLVED", "evidence_for": "Load-dominated historical tail is compatible with resource contention", "evidence_against_or_missing": "nvidia-smi and process inventories unavailable because SSH authentication failed; no utilization/VRAM time series"},
        {"hypothesis": "H3_runner_lifecycle_or_scheduler", "status": "UNRESOLVED", "evidence_for": "A cold transition and historical threshold runs could be scheduler/lifecycle related", "evidence_against_or_missing": "Remote runner PID and service/journal evidence unavailable; local sequential runner had no retry/concurrency change"},
        {"hypothesis": "H4_request_or_image_dependent_cost", "status": "NOT_SUPPORTED", "evidence_for": "C spans 16 diverse DEV images", "evidence_against_or_missing": "C load stays 0.440-0.555s with no high-load rows; A repeats one exact image with only its first row high"},
        {"hypothesis": "H5_prompt_or_generation_cost", "status": "NOT_SUPPORTED", "evidence_for": "None", "evidence_against_or_missing": "prompt_eval_count is stable at 598; prompt_eval/eval P95 remain sub-second while VAL tail is load-dominated"},
        {"hypothesis": "H6_client_or_network_transport", "status": "NOT_SUPPORTED", "evidence_for": "None", "evidence_against_or_missing": "Historical and probe client latency tracks Ollama total closely; client overhead is approximately milliseconds, not seconds"},
        {"hypothesis": "H7_other_remote_runtime_anomaly", "status": "UNRESOLVED", "evidence_for": "A real historical high-load state transition exists", "evidence_against_or_missing": "Specific daemon/GPU/process cause cannot be isolated without authorized remote telemetry"},
    ]
    write_csv(OUT / "hypothesis_matrix.csv", hypotheses, ["hypothesis", "status", "evidence_for", "evidence_against_or_missing"])

    anomaly_rows = [row for row in all_rows if bool(row["high_load"])]
    write_csv(OUT / "anomaly_requests.csv", anomaly_rows, fields)
    change_points = []
    for row in load_csv(HIST / "p2_val_change_points.csv"):
        change_points.append({"source": "historical_p2_val", **row})
    for name, rows in {**probes, "P2L_A_ATTEMPT_001": preserved_attempt}.items():
        previous = None
        for row in rows:
            state = "HIGH" if bool(row["high_load"]) else "LOW"
            if previous is None or state != previous:
                change_points.append({"source": "p2l_probe", "probe": name, "request_index": row["request_index"], "change_type": "START_" + state if previous is None else previous + "_TO_" + state, "from_state": "START" if previous is None else previous, "to_state": state, "request_id": row["request_id"], "media_id": row["media_id"], "timestamp_start_utc": row["timestamp_start_utc"], "load_duration_seconds": row["load_duration_seconds"]})
            previous = state
    change_points.sort(key=lambda row: parse_iso(str(row["timestamp_start_utc"])))
    write_csv(OUT / "change_point_analysis.csv", change_points, ["source", "dataset", "probe", "request_index", "change_type", "from_state", "to_state", "request_id", "media_id", "timestamp_start_utc", "load_duration_seconds"])

    telemetry = []
    ps_path = P2L / "03_runtime_telemetry/api_ps_samples.jsonl"
    for line in ps_path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        models = obj.get("body", {}).get("models", []) if obj.get("http_code") == 200 else []
        telemetry.append({"timestamp_utc": obj.get("timestamp_utc"), "probe": obj.get("probe"), "phase": obj.get("phase"), "http_code": obj.get("http_code"), "model_loaded": bool(models), "model_count": len(models), "model_digest": models[0].get("digest") if models else "", "size_vram": models[0].get("size_vram") if models else "", "expires_at": models[0].get("expires_at") if models else ""})
    write_csv(OUT / "api_ps_timeline.csv", telemetry, ["timestamp_utc", "probe", "phase", "http_code", "model_loaded", "model_count", "model_digest", "size_vram", "expires_at"])

    meta = {
        "historical_inputs": [str(HIST / "p2_screen_duration_breakdown.csv"), str(HIST / "p2_val_duration_breakdown.csv"), str(HIST / "p2_val_change_points.csv")],
        "historical_forensics_script": str(ROOT / "tools/p2l_historical_forensics.py"),
        "probe_inputs": [str(P2L / d / "raw_responses.jsonl") for d in ("04_probe_A_exact_c3", "05_probe_B_keepalive", "06_probe_C_diverse_images", "04_probe_A_exact_c3_attempt_001")],
        "probe_request_logs": [str(P2L / d / "request_log.jsonl") for d in ("04_probe_A_exact_c3", "05_probe_B_keepalive", "06_probe_C_diverse_images", "04_probe_A_exact_c3_attempt_001")],
        "output_sha256": {},
    }
    for path in (OUT / "all_requests.csv", OUT / "latency_components.csv", OUT / "hypothesis_matrix.csv", OUT / "anomaly_requests.csv", OUT / "change_point_analysis.csv", OUT / "api_ps_timeline.csv", OUT / "forensic_summary.json", OUT / "final_forensic_summary.json"):
        meta["output_sha256"][path.name] = sha256(path)
    (OUT / "analysis_manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(p2l_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
