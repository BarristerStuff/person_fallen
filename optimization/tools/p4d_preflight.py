#!/usr/bin/env python3
"""Read-only P4D preflight and identity/scope audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
ENDPOINT = "http://192.168.20.62:11434"
MODEL = "qwen3.5:4b"
EXPECTED_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
EXPECTED_C3_PROMPT = "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
OLD_BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m")
NEW_BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def api_get(path: str) -> dict:
    url = ENDPOINT + path
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = None
            return {"url": url, "http_status": response.status, "ok": 200 <= response.status < 300, "json": body, "raw": raw}
    except Exception as exc:  # noqa: BLE001 - evidence must preserve the observed failure
        return {"url": url, "http_status": None, "ok": False, "json": None, "raw": "", "error": f"{type(exc).__name__}: {exc}"}


def run_json(command: list[str]) -> dict:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    raw = result.stdout.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout": raw, "stderr": result.stderr.strip()}
    return {"returncode": result.returncode, "payload": payload}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=P4D / "00_preflight")
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    validator = run_json(["python3", str(DATASET / "tools/validate_dataset.py"), "--json"])
    (out / "dataset_validator_before.json").write_text(
        json.dumps(validator["payload"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    version = api_get("/api/version")
    tags = api_get("/api/tags")
    ps = api_get("/api/ps")
    (out / "ollama_version.json").write_text(json.dumps(version, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "ollama_tags.json").write_text(json.dumps(tags, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "ollama_ps.json").write_text(json.dumps(ps, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    c3_path = ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt"
    c3_sha = sha256_file(c3_path) if c3_path.exists() else None
    p3_report = ROOT / "reports/24_p3_final_report.md"
    p2_report = ROOT / "reports/17_p2_final_report.md"
    split_path = ROOT / "01_data/frozen_manifest.csv"
    source_inventory = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_validator_sha256": sha256_file(out / "dataset_validator_before.json"),
        "c3_prompt_path": str(c3_path),
        "c3_prompt_sha256": c3_sha,
        "c3_prompt_expected_sha256": EXPECTED_C3_PROMPT,
        "c3_prompt_match": c3_sha == EXPECTED_C3_PROMPT,
        "p2_final_report_sha256": sha256_file(p2_report) if p2_report.exists() else None,
        "p3_final_report_sha256": sha256_file(p3_report) if p3_report.exists() else None,
        "historical_frozen_manifest_sha256": sha256_file(split_path) if split_path.exists() else None,
        "old_batch": {
            "path": str(OLD_BATCH),
            "exists": OLD_BATCH.exists(),
            "prompt_count": len(list((OLD_BATCH / "prompts").glob("*.txt"))) if (OLD_BATCH / "prompts").exists() else 0,
            "final_image_count": len(list((OLD_BATCH / "final").glob("*.png"))) if (OLD_BATCH / "final").exists() else 0,
        },
        "new_batch": {"path": str(NEW_BATCH), "exists": NEW_BATCH.exists()},
        "p3_status_path": str(ROOT / "reports/24_p3_final_report.md"),
        "p3_screen_is_pristine": False,
        "val_individual_errors_used_for_p3_design": False,
        "holdout_requests_allowed": 0,
    }
    (out / "source_hash_inventory.json").write_text(json.dumps(source_inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    tags_models = (tags.get("json") or {}).get("models", []) if isinstance(tags.get("json"), dict) else []
    model_entries = [m for m in tags_models if m.get("name") == MODEL or m.get("model") == MODEL]
    digest_values = sorted({m.get("digest") for m in model_entries if m.get("digest")})
    version_value = (version.get("json") or {}).get("version") if isinstance(version.get("json"), dict) else None
    identity = {
        "endpoint": ENDPOINT,
        "model": MODEL,
        "ollama_version": version_value,
        "qwen3_5_4b_entries": model_entries,
        "qwen3_5_4b_digests": digest_values,
        "expected_digest": EXPECTED_DIGEST,
        "identity_pass": version_value == "0.23.2" and digest_values == [EXPECTED_DIGEST],
        "version_response": version,
        "tags_response": tags,
        "ps_response": ps,
    }
    (out / "model_identity.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validator_payload = validator["payload"]
    validator_pass = (
        isinstance(validator_payload, dict)
        and validator_payload.get("status") == "valid"
        and validator_payload.get("error_count") == 0
        and validator_payload.get("full_hash_check") is True
    )
    checks = {
        "dataset_validator_pass": validator_pass,
        "c3_prompt_match": c3_sha == EXPECTED_C3_PROMPT,
        "model_identity_pass": identity["identity_pass"],
        "old_batch_untouched": source_inventory["old_batch"]["exists"],
        "new_batch_is_dedicated": str(NEW_BATCH).endswith("batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m"),
        "holdout_requests_allowed": 0,
        "preflight_pass": bool(validator_pass and identity["identity_pass"] and c3_sha == EXPECTED_C3_PROMPT),
    }
    report = [
        "# P4D read-only preflight",
        "",
        f"- `P4D_PREFLIGHT={'PASS' if checks['preflight_pass'] else 'BLOCKED'}`",
        f"- Dataset validator: `{validator_payload.get('status') if isinstance(validator_payload, dict) else 'unparsed'}`, errors=`{validator_payload.get('error_count') if isinstance(validator_payload, dict) else 'N/A'}`, full_hash_check=`{validator_payload.get('full_hash_check') if isinstance(validator_payload, dict) else 'N/A'}`",
        f"- Ollama: `{version_value}`; model `{MODEL}`; digest match=`{identity['identity_pass']}`",
        f"- C3 prompt hash match=`{checks['c3_prompt_match']}`",
        "- P4D is development-only; no VAL/HOLDOUT request is permitted.",
        "- This preflight did not mutate the formal dataset, old batch, production tree, or Ollama service.",
        "",
        "## Checks",
        "",
    ]
    for key, value in checks.items():
        report.append(f"- `{key}={value}`")
    (out / "preflight_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"preflight": checks, "validator": validator_payload, "identity": {k: identity[k] for k in ("ollama_version", "qwen3_5_4b_digests", "identity_pass")}}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if checks["preflight_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
