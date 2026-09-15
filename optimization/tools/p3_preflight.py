#!/usr/bin/env python3
"""P3 read-only preflight and source/freeze identity audit.

This script only reads the formal dataset, P2 frozen artifacts, and the
remote Ollama identity endpoints.  It writes evidence under the new P3
workspace and refuses to continue when a required historical binding is not
exactly the one recorded by P2.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ENDPOINT = "http://192.168.20.62:11434"
EXPECTED_MODEL = "qwen3.5:4b"
EXPECTED_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
EXPECTED_C3_PROMPT = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
EXPECTED_P2_WINNER_FREEZE = "ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0"


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        if isinstance(data, str):
            handle.write(data)
        else:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def fetch_json(url: str) -> dict:
    try:
        req = request.Request(url, headers={"Accept": "application/json"})
        with request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return {
                "ok": True,
                "url": url,
                "http_status": response.status,
                "raw": raw,
                "json": json.loads(raw),
            }
    except Exception as exc:  # preserve the failure as evidence; caller gates it
        return {
            "ok": False,
            "url": url,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    out = P3 / "00_preflight"
    out.mkdir(parents=True, exist_ok=True)

    validator_cmd = [
        "python3",
        str(DATASET / "tools/validate_dataset.py"),
        "--json",
    ]
    validator_proc = subprocess.run(
        validator_cmd, capture_output=True, text=True, check=False
    )
    try:
        validator_json = json.loads(validator_proc.stdout)
    except json.JSONDecodeError:
        validator_json = {
            "parse_error": True,
            "stdout": validator_proc.stdout,
            "stderr": validator_proc.stderr,
        }
    validator_json["command"] = " ".join(validator_cmd)
    validator_json["returncode"] = validator_proc.returncode
    write_atomic(out / "dataset_validator.json", validator_json)

    identity = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT,
        "version": fetch_json(ENDPOINT + "/api/version"),
        "tags": fetch_json(ENDPOINT + "/api/tags"),
        "ps": fetch_json(ENDPOINT + "/api/ps"),
    }
    identity["expected_model"] = EXPECTED_MODEL
    identity["expected_digest"] = EXPECTED_DIGEST
    models = identity["tags"].get("json", {}).get("models", []) if identity["tags"].get("ok") else []
    matching = [m for m in models if m.get("name") == EXPECTED_MODEL or m.get("model") == EXPECTED_MODEL]
    identity["matching_models"] = matching
    identity["model_identity_pass"] = bool(
        matching and matching[0].get("digest") == EXPECTED_DIGEST
    )
    write_atomic(out / "model_identity.json", identity)

    required = {
        "c3_prompt": P2 / "03_candidates/C3/C3_prompt.txt",
        "p2_winner_freeze": P2 / "05_winner_freeze/p2_winner_freeze.json",
        "p2_request_config": P2 / "03_candidates/p2_request_config.json",
        "p2_internal_split": P2 / "01_internal_split/p2_internal_split.json",
        "p2_internal_split_verification": P2 / "01_internal_split/p2_internal_split_verification.json",
        "p2_design_manifest": P2 / "01_internal_split/p2_design_manifest.csv",
        "p2_screen_manifest": P2 / "01_internal_split/p2_screen_manifest.csv",
        "p2_screen_predictions": P2 / "04_screening/C3/predictions.csv",
        "p2_screen_summary": P2 / "04_screening/C3/summary.json",
        "frozen_splits": ROOT / "01_data/frozen_splits.csv",
        "p2l_final_audit": ROOT / "06_p2l_remote_latency_forensics/07_analysis/final_audit.json",
    }
    source_inventory = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {name: {"path": str(path), "sha256": sha(path)} for name, path in required.items()},
        "expected": {
            "c3_prompt_sha256": EXPECTED_C3_PROMPT,
            "p2_winner_freeze_sha256": EXPECTED_P2_WINNER_FREEZE,
            "model_digest": EXPECTED_DIGEST,
        },
    }
    design_path = required["p2_design_manifest"]
    screen_path = required["p2_screen_manifest"]
    errors: list[str] = []
    if source_inventory["files"]["c3_prompt"]["sha256"] != EXPECTED_C3_PROMPT:
        errors.append("C3_PROMPT_HASH_MISMATCH")
    if source_inventory["files"]["p2_winner_freeze"]["sha256"] != EXPECTED_P2_WINNER_FREEZE:
        errors.append("P2_WINNER_FREEZE_HASH_MISMATCH")
    for name, path in required.items():
        if source_inventory["files"][name]["sha256"] is None:
            errors.append(name.upper() + "_MISSING")

    design = load_csv(design_path) if design_path.is_file() else []
    screen = load_csv(screen_path) if screen_path.is_file() else []
    design_ids = {r.get("media_id") for r in design}
    screen_ids = {r.get("media_id") for r in screen}
    design_groups = {r.get("group_id") for r in design}
    screen_groups = {r.get("group_id") for r in screen}
    split_audit = {
        "design_rows": len(design),
        "screen_rows": len(screen),
        "design_unique_media": len(design_ids),
        "screen_unique_media": len(screen_ids),
        "design_unique_groups": len(design_groups),
        "screen_unique_groups": len(screen_groups),
        "design_original_splits": sorted({r.get("original_split") for r in design}),
        "screen_original_splits": sorted({r.get("original_split") for r in screen}),
        "design_roles": sorted({r.get("p2_internal_role") for r in design}),
        "screen_roles": sorted({r.get("p2_internal_role") for r in screen}),
        "design_screen_media_overlap": sorted(design_ids & screen_ids),
        "design_screen_group_overlap": sorted(design_groups & screen_groups),
        "design_holdout_rows": sum((r.get("original_split") or r.get("split")) == "HOLDOUT" for r in design),
        "screen_holdout_rows": sum((r.get("original_split") or r.get("split")) == "HOLDOUT" for r in screen),
        "design_val_rows": sum((r.get("original_split") or r.get("split")) == "VAL" for r in design),
        "screen_val_rows": sum((r.get("original_split") or r.get("split")) == "VAL" for r in screen),
    }
    source_inventory["split_audit"] = split_audit
    errors.extend(
        [
            "DESIGN_COUNT_INVALID" if len(design) != 190 else "",
            "SCREEN_COUNT_INVALID" if len(screen) != 120 else "",
            "DESIGN_MEDIA_DUPLICATE" if len(design_ids) != len(design) else "",
            "SCREEN_MEDIA_DUPLICATE" if len(screen_ids) != len(screen) else "",
            "DESIGN_SCREEN_MEDIA_OVERLAP" if design_ids & screen_ids else "",
            "DESIGN_SCREEN_GROUP_OVERLAP" if design_groups & screen_groups else "",
            "DESIGN_HOLDOUT_PRESENT" if split_audit["design_holdout_rows"] else "",
            "SCREEN_HOLDOUT_PRESENT" if split_audit["screen_holdout_rows"] else "",
            "DESIGN_VAL_PRESENT" if split_audit["design_val_rows"] else "",
            "SCREEN_VAL_PRESENT" if split_audit["screen_val_rows"] else "",
        ]
    )
    source_inventory["errors"] = [e for e in errors if e]
    source_inventory["preflight_source_gate"] = not source_inventory["errors"]
    write_atomic(out / "source_hash_inventory.json", source_inventory)

    lines = [
        "# P3 preflight report",
        "",
        f"checked_at_utc: {source_inventory['checked_at_utc']}",
        "",
        "## 已确认事实",
        "",
        f"- dataset validator returncode={validator_proc.returncode}; status={validator_json.get('status')}; errors={validator_json.get('error_count')}; warnings={validator_json.get('warning_count')}; full_hash_check={validator_json.get('full_hash_check')}",
        f"- model identity pass={identity['model_identity_pass']}; Ollama version={identity.get('version', {}).get('json', {}).get('version')}; qwen3.5:4b digest={matching[0].get('digest') if matching else None}",
        f"- P2 DESIGN rows={len(design)}, SCREEN rows={len(screen)}, media overlap={len(design_ids & screen_ids)}, group overlap={len(design_groups & screen_groups)}",
        f"- P2 C3 prompt SHA={source_inventory['files']['c3_prompt']['sha256']}",
        f"- P2 winner freeze SHA={source_inventory['files']['p2_winner_freeze']['sha256']}",
        "",
        "## 独立判断",
        "",
        "- P3 只使用 P2_DESIGN 进行 C3 residual forensic 和 candidate design；P2_SCREEN 仅在 candidate freeze 后用于 adaptive screening。",
        "- 本阶段不运行 VAL，不读取 P2 SCREEN/VAL 个体错误，不请求 HOLDOUT。",
        "",
        "## 风险与停止条件",
        "",
        "- 若 source_hash_inventory.errors 非空，或 model_identity_pass=false，P3 必须 BLOCKED，不得发起正式图片请求。",
        "- 当前 validator 的 387 条 warning 记录为既有数据集 warning；本阶段不修改正式数据集。",
    ]
    write_atomic(out / "preflight_report.md", "\n".join(lines) + "\n")
    print(json.dumps({
        "P3_PREFLIGHT": "PASS" if source_inventory["preflight_source_gate"] and identity["model_identity_pass"] and validator_json.get("status") == "valid" and validator_json.get("error_count") == 0 else "BLOCKED",
        "source_errors": source_inventory["errors"],
        "model_identity_pass": identity["model_identity_pass"],
        "dataset_status": validator_json.get("status"),
        "dataset_error_count": validator_json.get("error_count"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if source_inventory["preflight_source_gate"] and identity["model_identity_pass"] and validator_json.get("status") == "valid" and validator_json.get("error_count") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
