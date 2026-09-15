"""Create the immutable R1 execution freeze after all offline checks.

This script is intentionally separate from the formal runner. It performs no
model request and refuses to overwrite any freeze or execution directory.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
V5 = BASE / "17_person_fallen_v5_target_attributes"
V13 = BASE / "13_person_fallen_v4_pose_attributes"
FREEZE = ROOT / "freeze/RECOVERY_FREEZE.json"
FREEZE_SHA = ROOT / "freeze/RECOVERY_FREEZE.sha256"

sys.path.insert(0, str(ROOT / "adapters"))
from reuse_v5_b0 import load_reuse_records, sha256  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from full_dev_metrics import validate_manifest  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def bind(bindings: dict[str, str], path: Path) -> None:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"cannot bind missing file: {path}")
    digest = sha256(path)
    prior = bindings.get(str(path))
    if prior is not None and prior != digest:
        raise ValueError(f"binding changed during freeze build: {path}")
    bindings[str(path)] = digest


def bind_tree(bindings: dict[str, str], directory: Path, *, include_suffixes: set[str] | None = None) -> None:
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file():
            continue
        if include_suffixes is not None and path.suffix not in include_suffixes:
            continue
        bind(bindings, path)


def main() -> None:
    if FREEZE.exists() or FREEZE_SHA.exists():
        raise RuntimeError("recovery freeze already exists; no overwrite")
    if (ROOT / "eval/full_dev").exists():
        raise RuntimeError("formal eval already exists; freeze must precede execution")
    preflight = read_json(ROOT / "reports/preflight_recovery.json")
    if preflight.get("status") != "PASS_RECOVERY_PREFLIGHT_NO_INFERENCE" or preflight.get("model_requests_this_recovery") != 0:
        raise RuntimeError("offline recovery preflight not passed")
    val_audit = read_json(ROOT / "reports/legacy_val_exposure_audit.json")
    if val_audit.get("overlap", {}).get("media_id_overlap") != 100 or val_audit.get("overlap", {}).get("image_sha256_overlap") != 100:
        raise RuntimeError("legacy VAL exposure audit mismatch")
    if val_audit.get("p1r_summary", {}).get("p1r_val_is_pristine") is not False:
        raise RuntimeError("legacy VAL is not explicitly marked historically exposed")
    reuse_records, v5_freeze = load_reuse_records()
    if len(reuse_records) != 115:
        raise RuntimeError("V5-B0 reuse count mismatch")
    full_manifest = read_json(ROOT / "manifests/full_dev_manifest.json")
    new_manifest = read_json(ROOT / "manifests/new321_manifest.json")
    errors = validate_manifest(full_manifest)
    if errors:
        raise RuntimeError(f"full DEV manifest invalid: {errors[:3]}")
    if len(new_manifest) != 321 or [row["request_id"] for row in new_manifest] != [f"V5_B0_FULLDEV_EXTENSION_{i:04d}" for i in range(1, 322)]:
        raise RuntimeError("new321 manifest identity/order mismatch")
    if any(row["item_id"] == "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05" for row in full_manifest):
        raise RuntimeError("known regression leaked into full DEV")
    test_summary = read_json(ROOT / "reports/offline_test_summary.json")
    if test_summary.get("failures", 1) != 0 or test_summary.get("errors", 1) != 0 or test_summary.get("skipped", 1) != 0:
        raise RuntimeError("offline test summary not clean")
    if not (ROOT / "reports/fake_e2e_report.json").is_file() or read_json(ROOT / "reports/fake_e2e_report.json").get("status") != "PASS_FAKE_TRANSPORT_FULL_E2E":
        raise RuntimeError("fake E2E not passed")
    ollama = read_json(ROOT / "reports/ollama_preflight.json")
    selected = [m for m in ollama.get("tags", {}).get("models", []) if m.get("name") == "qwen3.5:4b"]
    if len(selected) != 1 or selected[0].get("digest") != "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd":
        raise RuntimeError("Ollama preflight model mismatch")
    if ollama.get("version", {}).get("version") != "0.23.2":
        raise RuntimeError("Ollama preflight version mismatch")

    bindings: dict[str, str] = {}
    # Preserve and directly bind every original V5-B0 freeze artifact.
    for path_text, expected in v5_freeze["bindings"].items():
        path = Path(path_text)
        if sha256(path) != expected:
            raise RuntimeError(f"original V5-B0 binding changed: {path}")
        bindings[str(path.resolve())] = expected
    for path in [
        V5 / "freeze/EXECUTION_FREEZE.json", V5 / "freeze/EXECUTION_FREEZE.sha256",
        V5 / "prompt/target_attributes.txt", V5 / "schema/target_attributes.json",
        V5 / "policy/target_policy.py", V5 / "tools/contracts.py",
        V5 / "manifests/pilot115.csv", V5 / "eval/pilot/output.jsonl",
        V5 / "eval/pilot/predictions.csv", V5 / "eval/pilot/summary.json",
        V5 / "eval/pilot/COMPLETION_LOCK.json",
        V13 / "manifests/v4_full_dev_436.csv", V13 / "manifests/v4_full_dev_crop_manifest.csv",
        ROOT / "protocol/recovery_plan.json", ROOT / "manifests/full_dev_manifest.csv",
        ROOT / "manifests/full_dev_manifest.json", ROOT / "manifests/reuse115_manifest.csv",
        ROOT / "manifests/reuse115_manifest.json", ROOT / "manifests/reuse115_records.json",
        ROOT / "manifests/new321_manifest.csv", ROOT / "manifests/new321_manifest.json",
        ROOT / "manifests/input_binding_inventory.json", ROOT / "reports/source_audit.json",
        ROOT / "reports/reuse_inventory_audit.json", ROOT / "reports/preflight_old_extension.json",
        ROOT / "reports/preflight_recovery.json", ROOT / "reports/legacy_val_exposure_audit.json",
        ROOT / "reports/fake_e2e_report.json", ROOT / "reports/offline_test_summary.json",
        ROOT / "reports/pre_execution_review.json", ROOT / "reports/reuse_replay_audit.json",
        ROOT / "reports/pre_freeze_fix_audit.json", ROOT / "reports/offline_tests.txt",
        ROOT / "reports/ollama_preflight.json", ROOT / "tools/recovery_runner.py",
        ROOT / "tools/full_dev_metrics.py", ROOT / "tools/build_recovery_manifest.py",
        ROOT / "tools/prepare_reuse.py", ROOT / "tools/preflight_recovery.py",
        ROOT / "tools/audit_legacy_val_exposure.py", ROOT / "tools/run_fake_e2e.py",
        ROOT / "tools/freeze_recovery.py", ROOT / "adapters/reuse_v5_b0.py",
    ]:
        bind(bindings, path)
    # Every source resource referenced by the normalized DEV manifest is bound.
    inventory = read_json(ROOT / "manifests/input_binding_inventory.json")
    for path_text, record in inventory.get("resource_bindings", {}).items():
        path = Path(path_text)
        if sha256(path) != record["sha256"]:
            raise RuntimeError(f"input inventory binding changed: {path}")
        bindings[str(path.resolve())] = record["sha256"]
    # Bind all recovery source/test code, but not future eval output or terminal reports.
    bind_tree(bindings, ROOT / "tests")
    # Explicitly bind old extension failure evidence as read-only historical evidence.
    old = BASE / "18_person_fallen_v5_full_dev_extension"
    for path in [old / "freeze/EXTENSION_FREEZE.json", old / "freeze/EXTENSION_FREEZE.sha256", old / "reports/terminal_protocol_incomplete.json", old / "eval/console.log"]:
        bind(bindings, path)
    # Bind only legacy VAL metadata files and summary; never any VAL image/prompt/prediction.
    for path in [
        BASE / "11_person_fallen_v3_revision/remap/person_fallen_v3_val_manifest.csv",
        BASE / "04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv",
        BASE / "04_p1r_freeze_binding_recovery/val/summary.json",
    ]:
        bind(bindings, path)

    plan = read_json(ROOT / "protocol/recovery_plan.json")
    freeze = {
        "status": "IMMUTABLE_RECOVERY_FREEZE",
        "candidate": "V5-B0-TARGET-ATTRIBUTES",
        "execution": "FULL_DEV_RECOVERY_R1",
        "execution_id": "PERSON_FALLEN_V5_B0_FULL_DEV_RECOVERY_R1_20260909",
        "purpose": "Same V5-B0 engineering recovery; not a new semantic candidate",
        "original_v5_b0_freeze_sha256": sha256(V5 / "freeze/EXECUTION_FREEZE.json"),
        "model": plan["model"],
        "budget": {"reused": 115, "new_max": 321, "full_dev_total": 436},
        "request_order": ["normal_negative", "ground_lying", "auxiliary_attention", "visual_uncertain"],
        "gates": plan["gates"],
        "early_stop": plan["early_stop"],
        "bindings": dict(sorted(bindings.items())),
        "binding_count": len(bindings),
        "source_policy": {"GT_TYPE": "PROMPT_DERIVED_SYNTHETIC_GT", "HUMAN_SEMANTIC_REVIEW_REQUIRED_FOR_SYNTHETIC_DEVELOPMENT": False, "MODEL_PREDICTION_USED_AS_GT": False},
        "VAL_POLICY": {"model_requests": 0, "images_read": 0, "predictions_read": 0, "status": "HISTORICALLY_EXPOSED_NOT_PRISTINE"},
        "HOLDOUT_POLICY": {"requests": 0, "images_read": 0, "consumed": False},
        "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED",
        "robot_control_requests": 0,
        "no_dynamic_api_ps_hard_binding": True,
    }
    data = (json.dumps(freeze, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with FREEZE.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    freeze_hash = hashlib.sha256(data).hexdigest()
    with FREEZE_SHA.open("xb") as handle:
        handle.write((freeze_hash + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())
    # Freeze only implementation/manifest/test sources; leave reports/eval writable for results.
    for directory in [ROOT / "protocol", ROOT / "manifests", ROOT / "adapters", ROOT / "tools", ROOT / "tests"]:
        for path in directory.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
    FREEZE.chmod(0o444)
    FREEZE_SHA.chmod(0o444)
    print(json.dumps({"status": freeze["status"], "freeze_sha256": freeze_hash, "binding_count": len(bindings)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
