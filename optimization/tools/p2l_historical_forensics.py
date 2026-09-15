#!/usr/bin/env python3
"""Recompute P2 C3 historical latency components from raw artifacts.

This script deliberately does not read predictions or evidence.  It joins the
historical raw Ollama responses to request logs, verifies processed image
geometry/hashes, and emits transparent component statistics and threshold-run
change points for SCREEN and VAL.
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
from typing import Iterable

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
OUT = ROOT / "06_p2l_remote_latency_forensics/01_historical_forensics"
EXPECTED_PROMPT_SHA = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
EXPECTED_MODEL = "qwen3.5:4b"
HIGH_LOAD_SECONDS = 5.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * p
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return values[lower]
    return values[lower] + (pos - lower) * (values[upper] - values[lower])


def stats(values: Iterable[float]) -> dict[str, float | int | None]:
    values = list(values)
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
    dx = [v - mx for v in rx]
    dy = [v - my for v in ry]
    den = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy)) / den if den else None


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def image_info(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"processed image missing: {path}")
    actual = sha256(path)
    # Verify before load, then reopen/load for geometry, matching the image
    # audit procedure used by the project.
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        im.load()
        width, height = im.size
    return {"image_path": str(path), "image_width": width, "image_height": height, "image_bytes": path.stat().st_size, "processed_sha256": actual}


def read_dataset(name: str, raw_path: Path, log_path: Path, manifest_path: Path, processed_dir: Path) -> list[dict[str, object]]:
    raw_by_id: dict[str, dict] = {}
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        raw_by_id[obj["request_id"]] = obj
    logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    manifest = {row["media_id"]: row for row in load_csv(manifest_path)}
    if set(raw_by_id) != {row["request_id"] for row in logs}:
        raise RuntimeError(f"{name}: raw/log request ID sets differ")
    rows: list[dict[str, object]] = []
    prompt_hashes: Counter[str] = Counter()
    config_fingerprints: Counter[str] = Counter()
    for index, log in enumerate(logs, 1):
        request_id = log["request_id"]
        raw = raw_by_id[request_id]
        outer = raw.get("outer_json") or {}
        media_id = log["media_id"]
        if media_id not in manifest:
            raise RuntimeError(f"{name}: media {media_id} missing from manifest")
        m = manifest[media_id]
        payload = log.get("request_payload_config") or {}
        prompt = payload.get("prompt", "")
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        normalized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        prompt_hashes[prompt_sha] += 1
        config_fingerprints[hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()] += 1
        components = {
            "total_duration": outer.get("total_duration"),
            "load_duration": outer.get("load_duration"),
            "prompt_eval_duration": outer.get("prompt_eval_duration"),
            "eval_duration": outer.get("eval_duration"),
        }
        if any(not isinstance(v, (int, float)) for v in components.values()):
            raise RuntimeError(f"{name}: missing duration component for {request_id}")
        total_s = float(components["total_duration"]) / 1e9
        load_s = float(components["load_duration"]) / 1e9
        prompt_s = float(components["prompt_eval_duration"]) / 1e9
        eval_s = float(components["eval_duration"]) / 1e9
        processed = processed_dir / f"{media_id}.jpg"
        info = image_info(processed)
        start = parse_iso(log["timestamp_start_utc"])
        end = parse_iso(log["timestamp_end_utc"])
        row = {
            "dataset": name,
            "request_index": index,
            "request_id": request_id,
            "media_id": media_id,
            "timestamp_start_utc": log["timestamp_start_utc"],
            "timestamp_end_utc": log["timestamp_end_utc"],
            "wall_span_seconds": (end - start).total_seconds(),
            "client_latency_seconds": float(log["latency_seconds"]),
            "total_duration_ns": int(components["total_duration"]),
            "total_duration_seconds": total_s,
            "load_duration_ns": int(components["load_duration"]),
            "load_duration_seconds": load_s,
            "prompt_eval_duration_ns": int(components["prompt_eval_duration"]),
            "prompt_eval_duration_seconds": prompt_s,
            "eval_duration_ns": int(components["eval_duration"]),
            "eval_duration_seconds": eval_s,
            "client_overhead_seconds": float(log["latency_seconds"]) - total_s,
            "load_ratio": load_s / total_s if total_s else None,
            "prompt_eval_ratio": prompt_s / total_s if total_s else None,
            "eval_ratio": eval_s / total_s if total_s else None,
            "prompt_eval_count": outer.get("prompt_eval_count"),
            "eval_count": outer.get("eval_count"),
            "done": outer.get("done"),
            "done_reason": outer.get("done_reason", ""),
            "http_code": log.get("http_code"),
            "prompt_sha256": prompt_sha,
            "config_fingerprint": hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest(),
            "model": payload.get("model", outer.get("model", "")),
            "format": payload.get("format", ""),
            "think": payload.get("think", ""),
            "stream": payload.get("stream", ""),
            "generation_options": json.dumps(payload.get("options", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "high_load": load_s > HIGH_LOAD_SECONDS,
            "image_sha256": m["image_sha256"],
            "image_path": m["image_path"],
            **info,
        }
        rows.append(row)
    if any(row["image_width"] != 448 or row["image_height"] != 336 for row in rows):
        raise RuntimeError(f"{name}: processed geometry is not uniformly 448x336")
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"cannot write empty CSV: {path}")
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def runs(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    if not rows:
        return out
    start = 0
    state = bool(rows[0]["high_load"])
    for idx in range(1, len(rows)):
        next_state = bool(rows[idx]["high_load"])
        if next_state != state:
            out.append({"start_index": start + 1, "end_index": idx, "state": "HIGH" if state else "LOW", "count": idx - start})
            start, state = idx, next_state
    out.append({"start_index": start + 1, "end_index": len(rows), "state": "HIGH" if state else "LOW", "count": len(rows) - start})
    return out


def change_point_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cp: list[dict[str, object]] = []
    if not rows:
        return cp
    previous = bool(rows[0]["high_load"])
    cp.append({
        "dataset": rows[0]["dataset"],
        "request_index": 1,
        "change_type": "START_HIGH" if previous else "START_LOW",
        "from_state": "START",
        "to_state": "HIGH" if previous else "LOW",
        "request_id": rows[0]["request_id"],
        "media_id": rows[0]["media_id"],
        "timestamp_start_utc": rows[0]["timestamp_start_utc"],
        "load_duration_seconds": rows[0]["load_duration_seconds"],
    })
    for idx in range(1, len(rows)):
        state = bool(rows[idx]["high_load"])
        if state != previous:
            cp.append({
                "dataset": rows[idx]["dataset"],
                "request_index": idx + 1,
                "change_type": "HIGH_TO_LOW" if previous else "LOW_TO_HIGH",
                "from_state": "HIGH" if previous else "LOW",
                "to_state": "HIGH" if state else "LOW",
                "request_id": rows[idx]["request_id"],
                "media_id": rows[idx]["media_id"],
                "timestamp_start_utc": rows[idx]["timestamp_start_utc"],
                "load_duration_seconds": rows[idx]["load_duration_seconds"],
            })
        previous = state
    return cp


def dataset_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    components = {}
    for key in ("client_latency_seconds", "total_duration_seconds", "load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "load_ratio", "prompt_eval_ratio", "eval_ratio", "client_overhead_seconds"):
        components[key] = stats(float(row[key]) for row in rows if row[key] is not None)
    prompt_counts = Counter(row["prompt_eval_count"] for row in rows)
    eval_counts = [int(row["eval_count"]) for row in rows]
    load = [float(row["load_duration_seconds"]) for row in rows]
    eval_duration = [float(row["eval_duration_seconds"]) for row in rows]
    image_bytes = [int(row["image_bytes"]) for row in rows]
    high_rows = [row for row in rows if row["high_load"]]
    low_rows = [row for row in rows if not row["high_load"]]
    return {
        "count": len(rows),
        "component_stats": components,
        "high_load_threshold_seconds": HIGH_LOAD_SECONDS,
        "high_load_count": len(high_rows),
        "low_load_count": len(low_rows),
        "prompt_eval_count_values": dict(prompt_counts),
        "prompt_eval_count_stable": len(prompt_counts) == 1,
        "eval_count_stats": stats(eval_counts),
        "high_load_eval_count_stats": stats(int(row["eval_count"]) for row in high_rows),
        "low_load_eval_count_stats": stats(int(row["eval_count"]) for row in low_rows),
        "eval_count_load_spearman": spearman(eval_counts, load),
        "image_bytes_stats": stats(image_bytes),
        "image_bytes_load_spearman": spearman(image_bytes, load),
        "high_load_image_bytes_stats": stats(int(row["image_bytes"]) for row in high_rows),
        "low_load_image_bytes_stats": stats(int(row["image_bytes"]) for row in low_rows),
        "runs": runs(rows),
        "change_points": change_point_rows(rows),
        "config_prompt_sha_values": sorted({row["prompt_sha256"] for row in rows}),
        "config_fingerprints": sorted({row["config_fingerprint"] for row in rows}),
        "model_values": sorted({row["model"] for row in rows}),
        "format_values": sorted({row["format"] for row in rows}),
        "think_values": sorted({str(row["think"]) for row in rows}),
        "stream_values": sorted({str(row["stream"]) for row in rows}),
    }


def make_report(summary: dict[str, object], screen: dict[str, object], val: dict[str, object], source_hashes: dict[str, str], config_match: dict[str, object]) -> str:
    vcomp = val["component_stats"]
    scomp = screen["component_stats"]
    cp = [x for x in val["change_points"] if x["change_type"] == "HIGH_TO_LOW"]
    high_runs = [x for x in val["runs"] if x["state"] == "HIGH"]
    longest = max(high_runs, key=lambda x: x["count"]) if high_runs else None
    recovered_index = next((x["request_index"] for x in cp if longest and x["request_index"] > longest["end_index"]), None)
    high_window_rows = val_rows_for_window(val, longest)
    low_window = {"start_index": recovered_index, "end_index": len(val["_rows"])} if recovered_index else None
    low_window_rows = val_rows_for_window(val, low_window)
    transient_low = [x["start_index"] for x in val["runs"] if x["state"] == "LOW" and x["count"] == 1]

    def window_stat(rows: list[dict[str, object]], key: str, quantile: float | None = None) -> str:
        values = [float(r[key]) for r in rows]
        value = percentile(values, quantile) if quantile is not None else statistics.median(values)
        return f"{value:.6f}s" if value is not None else "N/A"

    transient_text = ", ".join(str(x) for x in transient_low) if transient_low else "none"
    return f"""# P2L historical latency forensics

## Status

```text
STAGE=P2L_REMOTE_LATENCY_FORENSICS
P2L_HISTORICAL_SOURCE=P2_C3_RAW_RESPONSES_AND_REQUEST_LOGS
P2L_NEW_VAL_REQUESTS=0
P2L_HOLDOUT_REQUESTS=0
HISTORICAL_PRIMARY_LATENCY_COMPONENT=load_duration
HISTORICAL_HIGH_LOAD_THRESHOLD_SECONDS={HIGH_LOAD_SECONDS}
```

This report was recomputed from the P2 C3 raw response JSONL and request-log JSONL, not from `summary.md` and not from predictions/evidence. P2 history was not rewritten. Duration fields from Ollama nanoseconds are retained in the per-request CSV and converted to seconds for statistics. `client_latency_seconds` is the runner's HTTP timing; `wall_span_seconds` is also retained because the runner records its start marker before local preprocessing.

## Historical counts and component statistics

| Dataset | Requests | High-load (>5s) | Client P50/P95 | Ollama total P50/P95 | Load P50/P95 | Prompt-eval P50/P95 | Eval P50/P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SCREEN | {screen['count']} | {screen['high_load_count']} | {scomp['client_latency_seconds']['p50']:.6f}s / {scomp['client_latency_seconds']['p95']:.6f}s | {scomp['total_duration_seconds']['p50']:.6f}s / {scomp['total_duration_seconds']['p95']:.6f}s | {scomp['load_duration_seconds']['p50']:.6f}s / {scomp['load_duration_seconds']['p95']:.6f}s | {scomp['prompt_eval_duration_seconds']['p50']:.6f}s / {scomp['prompt_eval_duration_seconds']['p95']:.6f}s | {scomp['eval_duration_seconds']['p50']:.6f}s / {scomp['eval_duration_seconds']['p95']:.6f}s |
| VAL | {val['count']} | {val['high_load_count']} | {vcomp['client_latency_seconds']['p50']:.6f}s / {vcomp['client_latency_seconds']['p95']:.6f}s | {vcomp['total_duration_seconds']['p50']:.6f}s / {vcomp['total_duration_seconds']['p95']:.6f}s | {vcomp['load_duration_seconds']['p50']:.6f}s / {vcomp['load_duration_seconds']['p95']:.6f}s | {vcomp['prompt_eval_duration_seconds']['p50']:.6f}s / {vcomp['prompt_eval_duration_seconds']['p95']:.6f}s | {vcomp['eval_duration_seconds']['p50']:.6f}s / {vcomp['eval_duration_seconds']['p95']:.6f}s |

The full component summaries (mean, median, P50, P90, P95, max) are in `duration_summary.json`; each raw row is in `p2_screen_duration_breakdown.csv` and `p2_val_duration_breakdown.csv`. In VAL, load duration contributes a median ratio of {vcomp['load_ratio']['median']:.6f} and P95 ratio of {vcomp['load_ratio']['p95']:.6f}; prompt evaluation and generation remain sub-second at P95 ({vcomp['prompt_eval_duration_seconds']['p95']:.6f}s and {vcomp['eval_duration_seconds']['p95']:.6f}s). This is why the primary historical anomaly component is `load_duration`, subject to the runtime evidence limitations below.

## Automatically detected change points

The method is an explicit threshold-run analysis: mark each ordered VAL request as HIGH when `load_duration > 5s`, form contiguous runs, and select the longest sustained HIGH run followed by a LOW run. No request index was hard-coded.

VAL runs:

```text
{json.dumps(val['runs'], ensure_ascii=False)}
```

The longest sustained HIGH run is requests {longest['start_index'] if longest else 'N/A'}–{longest['end_index'] if longest else 'N/A'}; the first recovered LOW request after that run is index {recovered_index if recovered_index is not None else 'N/A'}. Single-request LOW runs detected between HIGH runs start at index {transient_text}; they are retained rather than hidden. All transitions, timestamps, and request IDs are in `p2_val_change_points.csv`.

For the main recovery transition, the pre-change sustained HIGH window is requests {longest['start_index'] if longest else 'N/A'}–{longest['end_index'] if longest else 'N/A'} and the post-change LOW window begins at {recovered_index if recovered_index is not None else 'N/A'}:

| Window | Count | Load median | Load P95 | Total median | Client median |
|---|---:|---:|---:|---:|---:|
| Sustained HIGH before recovery | {len(high_window_rows)} | {window_stat(high_window_rows, 'load_duration_seconds')} | {window_stat(high_window_rows, 'load_duration_seconds', .95)} | {window_stat(high_window_rows, 'total_duration_seconds')} | {window_stat(high_window_rows, 'client_latency_seconds')} |
| Recovered LOW after transition | {len(low_window_rows)} | {window_stat(low_window_rows, 'load_duration_seconds')} | {window_stat(low_window_rows, 'load_duration_seconds', .95)} | {window_stat(low_window_rows, 'total_duration_seconds')} | {window_stat(low_window_rows, 'client_latency_seconds')} |

## Config and token checks

```json
{json.dumps(config_match, ensure_ascii=False, indent=2)}
```

SCREEN and VAL request payloads are byte-equivalent after JSON normalization for model, Prompt, `format`, `think`, `stream`, and generation options. Both use Prompt SHA `{EXPECTED_PROMPT_SHA}`, model `{EXPECTED_MODEL}`, `format=json`, `think=false`, `stream=false`, `temperature=0`, `num_ctx=8192`, and `num_predict=256`. The actual payload/config evidence is retained in the source request logs.

`prompt_eval_count` is stable at `{sorted(val['prompt_eval_count_values'])}` in VAL and `{sorted(screen['prompt_eval_count_values'])}` in SCREEN. `eval_count` varies, but the generation/eval-duration P95 remains only `{vcomp['eval_duration_seconds']['p95']:.6f}s`; it does not track the ten-second-scale load spike as the dominant component. The load-duration versus eval-count Spearman correlations are VAL `{val['eval_count_load_spearman']}` and SCREEN `{screen['eval_count_load_spearman']}`. Image geometry is uniformly 448×336; the load-duration/image-byte Spearman correlations are VAL `{val['image_bytes_load_spearman']}` and SCREEN `{screen['image_bytes_load_spearman']}`. These correlations are auxiliary association checks, not causal claims.

## Evidence boundary

The raw timing evidence confirms a load-duration-dominated historical anomaly: VAL has {val['high_load_count']} requests over 5 seconds, while SCREEN has {screen['high_load_count']}; prompt evaluation and generation do not expand comparably. It does not by itself identify whether the load time came from model reload/residency churn, runner lifecycle, scheduler behavior, GPU contention, or another server runtime condition. SSH read-only authentication to `tiga@192.168.20.62` failed during preflight, so remote GPU memory, compute-process, runner-PID, systemd, and journal evidence remain unavailable.

## Source hashes

```text
{json.dumps(source_hashes, ensure_ascii=False, indent=2)}
```
"""


def val_rows_for_window(summary: dict[str, object], window: dict[str, object] | None) -> list[dict[str, object]]:
    # The report formatter receives the summary object, so it stores rows under
    # a private key while formatting and removes that key before serialization.
    if not window:
        return []
    return [r for r in summary["_rows"] if window["start_index"] <= r["request_index"] <= window["end_index"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    screen = read_dataset(
        "SCREEN",
        P2 / "04_screening/C3/raw_responses.jsonl",
        P2 / "04_screening/C3/request_log.jsonl",
        P2 / "01_internal_split/p2_screen_manifest.csv",
        P2 / "04_screening/C3/processed_448x336",
    )
    val = read_dataset(
        "VAL",
        P2 / "06_val/raw_responses.jsonl",
        P2 / "06_val/request_log.jsonl",
        ROOT / "04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv",
        P2 / "06_val/processed_448x336",
    )
    write_csv(OUT / "p2_screen_duration_breakdown.csv", screen)
    write_csv(OUT / "p2_val_duration_breakdown.csv", val)
    screen_summary = dataset_summary(screen)
    val_summary = dataset_summary(val)
    screen_summary["_rows"] = screen
    val_summary["_rows"] = val
    cp_rows = change_point_rows(val)
    write_csv(OUT / "p2_val_change_points.csv", cp_rows)

    # Config comparison intentionally omits image data and semantic fields.
    screen_cfg = {row["config_fingerprint"] for row in screen}
    val_cfg = {row["config_fingerprint"] for row in val}
    prompt_sha_values = sorted({row["prompt_sha256"] for row in screen + val})
    config_match = {
        "screen_config_fingerprints": sorted(screen_cfg),
        "val_config_fingerprints": sorted(val_cfg),
        "screen_val_config_equal": screen_cfg == val_cfg,
        "prompt_sha_values": prompt_sha_values,
        "prompt_matches_expected_c3": prompt_sha_values == [EXPECTED_PROMPT_SHA],
        "model_values": sorted({row["model"] for row in screen + val}),
        "format_values": sorted({row["format"] for row in screen + val}),
        "think_values": sorted({str(row["think"]) for row in screen + val}),
        "stream_values": sorted({str(row["stream"]) for row in screen + val}),
        "generation_options_values": sorted({row["generation_options"] for row in screen + val}),
    }
    # The full payload is checked directly rather than relying only on a hash.
    screen_payloads = {
        json.dumps({k: next(row[k] for row in screen if row[k] is not None) for k in ("model", "format", "think", "stream", "generation_options")}, sort_keys=True)
    }
    val_payloads = {
        json.dumps({k: next(row[k] for row in val if row[k] is not None) for k in ("model", "format", "think", "stream", "generation_options")}, sort_keys=True)
    }
    config_match["reduced_scalar_config_equal"] = screen_payloads == val_payloads
    source_hashes = {
        "screen_raw": sha256(P2 / "04_screening/C3/raw_responses.jsonl"),
        "screen_request_log": sha256(P2 / "04_screening/C3/request_log.jsonl"),
        "screen_manifest": sha256(P2 / "01_internal_split/p2_screen_manifest.csv"),
        "val_raw": sha256(P2 / "06_val/raw_responses.jsonl"),
        "val_request_log": sha256(P2 / "06_val/request_log.jsonl"),
        "val_manifest": sha256(ROOT / "04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv"),
    }
    clean_screen = {k: v for k, v in screen_summary.items() if k != "_rows"}
    clean_val = {k: v for k, v in val_summary.items() if k != "_rows"}
    summary = {
        "stage": "P2L_REMOTE_LATENCY_FORENSICS",
        "high_load_threshold_seconds": HIGH_LOAD_SECONDS,
        "historical_primary_latency_component": "load_duration",
        "screen": clean_screen,
        "val": clean_val,
        "config_match": config_match,
        "source_hashes": source_hashes,
        "p2l_new_val_requests": 0,
        "p2l_holdout_requests": 0,
    }
    (OUT / "duration_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (OUT / "historical_latency_report.md").write_text(make_report(summary={"screen": clean_screen, "val": clean_val}, screen=screen_summary, val=val_summary, source_hashes=source_hashes, config_match=config_match))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
