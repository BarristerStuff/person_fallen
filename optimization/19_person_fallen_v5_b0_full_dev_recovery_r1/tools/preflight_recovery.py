"""Offline recovery preflight. No Ollama, no VAL/Holdout content, no inference."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
V5 = BASE / "17_person_fallen_v5_target_attributes"
OLD = BASE / "18_person_fallen_v5_full_dev_extension"

sys.path.insert(0, str(ROOT / "adapters"))
from reuse_v5_b0 import load_reuse_records, sha256  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    output = ROOT / "reports/preflight_recovery.json"
    if output.exists():
        raise RuntimeError("recovery preflight already exists; refusing overwrite")
    old_preflight = read_json(ROOT / "reports/preflight_old_extension.json")
    expected_zero = {"old_claimed_count": 0, "old_completed_count": 0, "old_raw_count": 0, "old_active_count": 0, "old_jsonl_count": 0}
    for key, expected in expected_zero.items():
        if old_preflight.get(key) != expected:
            raise RuntimeError(f"old extension unexpected state: {key}")
    if old_preflight.get("old_execution_process_lines"):
        raise RuntimeError("old extension process still active")
    if (ROOT / "eval/full_dev").exists():
        raise RuntimeError("recovery eval already exists")
    if (BASE / "19_person_fallen_v5_b0_full_dev_recovery_r2").exists():
        raise RuntimeError("R2 directory exists; do not create it")

    freeze = load_reuse_records()[1]
    reuse = read_json(ROOT / "manifests/reuse115_records.json")
    direct, _ = load_reuse_records()
    if json.dumps(reuse, ensure_ascii=False, sort_keys=True, allow_nan=False) != json.dumps(direct, ensure_ascii=False, sort_keys=True, allow_nan=False):
        raise RuntimeError("materialized reuse does not equal direct V5-B0 replay")
    if len(reuse) != 115:
        raise RuntimeError("reuse count mismatch")
    full = read_json(ROOT / "manifests/full_dev_manifest.json")
    new = read_json(ROOT / "manifests/new321_manifest.json")
    if len(full) != 436 or len(new) != 321:
        raise RuntimeError("manifest count mismatch")
    if len({row["item_id"] for row in full}) != 436 or len({row["request_id"] for row in full}) != 436:
        raise RuntimeError("full manifest identity duplicate")
    if len({row["item_id"] for row in new}) != 321 or [row["request_id"] for row in new] != [f"V5_B0_FULLDEV_EXTENSION_{i:04d}" for i in range(1, 322)]:
        raise RuntimeError("new manifest request identity/order mismatch")
    if {row["item_id"] for row in reuse} != {row["item_id"] for row in full if row["result_source"] == "REUSE_V5_B0_PILOT"}:
        raise RuntimeError("reuse/full identity mismatch")
    if any(row["item_id"] == "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05" for row in full):
        raise RuntimeError("known regression leaked into full DEV")
    source_audit = read_json(ROOT / "reports/source_audit.json")
    if source_audit.get("counts", {}).get("full_dev") != 436 or source_audit.get("counts", {}).get("reused_v5_b0") != 115 or source_audit.get("counts", {}).get("new_inference") != 321:
        raise RuntimeError("source audit counts mismatch")
    # Snapshot only process metadata; dynamic /api/ps is not checked here.
    ps = subprocess.run(["ps", "-eo", "pid,ppid,stat,etime,args"], capture_output=True, text=True, check=True).stdout
    relevant = [line for line in ps.splitlines() if "person_fallen_v5_b0_full_dev_recovery_r1" in line and "grep" not in line]
    report = {
        "status": "PASS_RECOVERY_PREFLIGHT_NO_INFERENCE",
        "candidate": "V5-B0-TARGET-ATTRIBUTES",
        "execution_id": "PERSON_FALLEN_V5_B0_FULL_DEV_RECOVERY_R1_20260909",
        "old_extension_state": old_preflight,
        "old_extension_immutable_evidence": {"freeze_sha256": sha256(OLD / "freeze/EXTENSION_FREEZE.json"), "path": str(OLD)},
        "v5_b0_freeze_sha256": sha256(V5 / "freeze/EXECUTION_FREEZE.json"),
        "v5_b0_freeze_binding_count": len(freeze.get("bindings", {})),
        "reuse_count": len(reuse),
        "full_dev_count": len(full),
        "new_count": len(new),
        "new_request_order": ["normal_negative", "ground_lying", "auxiliary_attention", "visual_uncertain"],
        "new_request_count_by_stratum": {stratum: sum(row["evaluation_stratum"] == stratum for row in new) for stratum in ["normal_negative", "ground_lying", "auxiliary_attention", "visual_uncertain"]},
        "runtime_process_relevant_lines": relevant,
        "VAL_images_read": 0,
        "VAL_predictions_read": 0,
        "VAL_evidence_read": 0,
        "HOLDOUT_read": 0,
        "model_requests_this_recovery": 0,
        "model_preflight_done": False,
        "source_fields_changed": False,
        "GT_relabelled": False,
        "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED",
    }
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({k: report[k] for k in ["status", "reuse_count", "full_dev_count", "new_count", "v5_b0_freeze_binding_count", "model_requests_this_recovery"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
