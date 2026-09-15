#!/usr/bin/env python3
"""Write auditable P3 run-config and auxiliary candidate artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
CFG = P3 / "03_candidates/p3_request_config.json"
RUNNER = ROOT / "tools/p3_inference_runner.py"
LAUNCHER = ROOT / "tools/p3_s1_shared_runner.py"
FREEZE = P3 / "03_candidates/candidate_freeze.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["media_id"]
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)


def copy_once(src: Path, dst: Path) -> None:
    if dst.exists():
        if sha(dst) != sha(src):
            raise SystemExit(f"P3_DERIVED_COPY_HASH_MISMATCH:{dst}")
        return
    shutil.copyfile(src, dst)
    with dst.open("rb") as handle:
        os.fsync(handle.fileno())


def main() -> None:
    design_src = P2 / "01_internal_split/p2_design_manifest.csv"
    screen_src = P2 / "01_internal_split/p2_screen_manifest.csv"
    design_dst = P3 / "01_c3_design_baseline/manifest.csv"
    screen_dst = P3 / "05_screen/manifest.csv"
    copy_once(design_src, design_dst); copy_once(screen_src, screen_dst)
    design_rows = load_csv(design_dst)
    design_predictions = load_csv(P3 / "01_c3_design_baseline/predictions.csv")
    for name, subset in [
        ("false_positives.csv", [r for r in design_predictions if r["event_label"] == "0" and r["predicted_status"] == "positive"]),
        ("false_negatives.csv", [r for r in design_predictions if r["event_label"] == "1" and r["predicted_status"] != "positive"]),
        ("model_uncertain.csv", [r for r in design_predictions if r["event_label"] in {"0", "1"} and r["predicted_status"] == "uncertain"]),
    ]:
        write_csv(P3 / "01_c3_design_baseline" / name, subset)

    common = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT", "event_name": "person_fallen", "event_definition_version": "v2.0",
        "model": "qwen3.5:4b", "model_digest": "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd", "ollama_version": "0.23.2", "endpoint": "http://192.168.20.62:11434",
        "request_config_path": str(CFG), "request_config_sha256": sha(CFG), "runner_path": str(RUNNER), "runner_sha256": sha(RUNNER),
        "preprocess": "letterbox_448x336_jpeg_q70", "parser": "response_only", "thinking_fallback": False,
        "stream": False, "format": "json", "think": False, "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 256}, "concurrency": 1, "automatic_retry": False,
        "val_requests": 0, "holdout_requests": 0,
    }
    write_json(P3 / "01_c3_design_baseline/run_config.json", {**common, "phase": "design", "candidate": "C3_BASELINE", "prompt_path": str(P3 / "03_candidates/C3_BASELINE/C3_prompt.txt"), "prompt_sha256": sha(P3 / "03_candidates/C3_BASELINE/C3_prompt.txt"), "manifest_path": str(design_dst), "manifest_sha256": sha(design_dst), "planned_requests": len(design_rows), "new_requests": len(design_rows)})
    canary_manifest = P3 / "04_canary/canary_manifest.csv"
    canary_cfg = {**common, "phase": "canary", "candidate": "S1_STRUCTURED", "shared_candidate_views": ["S1_DIRECT", "S1_RULE"], "prompt_path": str(P3 / "03_candidates/S1_STRUCTURED/S1_prompt.txt"), "prompt_sha256": sha(P3 / "03_candidates/S1_STRUCTURED/S1_prompt.txt"), "schema_path": str(P3 / "03_candidates/S1_STRUCTURED/S1_schema.json"), "schema_sha256": sha(P3 / "03_candidates/S1_STRUCTURED/S1_schema.json"), "rule_path": str(P3 / "03_candidates/S1_STRUCTURED/S1_rule.json"), "rule_sha256": sha(P3 / "03_candidates/S1_STRUCTURED/S1_rule.json"), "manifest_path": str(canary_manifest), "manifest_sha256": sha(canary_manifest), "candidate_freeze_path": str(FREEZE), "candidate_freeze_sha256": sha(FREEZE), "launcher_path": str(LAUNCHER), "launcher_sha256": sha(LAUNCHER), "planned_requests": 12, "new_requests": 12}
    write_json(P3 / "04_canary/run_config.json", canary_cfg)
    screen_cfg = {**canary_cfg, "phase": "screen", "manifest_path": str(screen_dst), "manifest_sha256": sha(screen_dst), "planned_requests": 120, "new_requests": 120}
    write_json(P3 / "05_screen/S1_STRUCTURED/run_config.json", screen_cfg)
    for variant in ["S1_DIRECT", "S1_RULE"]:
        write_json(P3 / "05_screen" / variant / "run_config.json", {"derived_offline": True, "variant": variant, "source_stream": str(P3 / "05_screen/S1_STRUCTURED"), "source_stream_predictions_sha256": sha(P3 / "05_screen/S1_STRUCTURED/predictions.csv"), "candidate_freeze_path": str(FREEZE), "candidate_freeze_sha256": sha(FREEZE), "model_requests": 0, "val_requests": 0, "holdout_requests": 0})
    readme = """# P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT

- status: `SCREENING_COMPLETE_NO_WINNER`
- design source: `P2_DESIGN`
- screen source: `P2_SCREEN` (adaptive, `screen_is_pristine=false`)
- new DEV requests: 322 (190 C3 DESIGN + 12 canary + 120 S1 SCREEN)
- new VAL requests: 0
- HOLDOUT requests: 0; consumed: false
- candidate freeze SHA-256: `{freeze_sha}`
- OPTIONAL_S2: not created

`S1_DIRECT` and `S1_RULE` are offline projections of one `S1_STRUCTURED`
response stream; no second VLM verifier was used.
""".format(freeze_sha=sha(FREEZE))
    write_atomic = P3 / "README.md"
    tmp_readme = write_atomic.with_suffix(write_atomic.suffix + ".tmp")
    with tmp_readme.open("w", encoding="utf-8") as handle:
        handle.write(readme); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp_readme, write_atomic)
    print(json.dumps({"run_configs_written": True, "design_manifest_sha256": sha(design_dst), "screen_manifest_sha256": sha(screen_dst), "launcher_sha256": sha(LAUNCHER)}, sort_keys=True))


if __name__ == "__main__":
    main()
