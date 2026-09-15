#!/usr/bin/env python3
"""Reseal the GR3Q1 preparation after a profile-lineage blocker is confirmed.

The initial preparation intentionally computed provider continuity late, after
the image/slot audits.  This finalizer marks its conditional recovery packet
and plan non-executable, binds the original frozen assets directly, and
refreshes only the GR3Q1 preparation freeze/checkpoints.  It performs no CLI,
provider, dataset, model, or image operations.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation" / "gr3_fullregen"
REV = GR3 / "06_execution" / "quota_recovery_20260827_01"
FREEZE = REV / "freeze" / "p4d_gr3q1_preparation_freeze.json"
SUMMARY = REV / "preparation_summary.json"
VERIFY = REV / "05_checkpoints" / "final_preparation_verification.json"
TERMINAL = REV / "05_checkpoints" / "blocked_profile_lineage_terminal.json"
TOOL = ROOT / "tools" / "p4d_gr3q1_prepare.py"
FINALIZER = ROOT / "tools" / "p4d_gr3q1_finalize_blocked.py"

FROZEN = [
    P4D / "01_prompt_plan" / "group_manifest.csv",
    P4D / "01_prompt_plan" / "group_split_freeze.json",
    P4D / "01_prompt_plan" / "prompt_manifest.csv",
    P4D / "01_prompt_plan" / "prompt_pack.md",
    P4D / "01_prompt_plan" / "prompt_pack_freeze.json",
    ROOT / "07_p3_structured_hard_negative_refinement" / "03_candidates" / "C3_BASELINE" / "C3_prompt.txt",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, value: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    freeze = read(FREEZE)
    if freeze.get("status") != "BLOCKED_PROFILE_LINEAGE_CHANGE" or freeze.get("continuation_compatible") is not False:
        raise RuntimeError("refusing to finalize a non-profile-lineage blocker")
    provider = freeze.get("provider_runtime") or {}
    if provider.get("profile_continuity") is not False:
        raise RuntimeError("freeze does not contain the expected failed profile gate")
    if (freeze.get("terminal") or {}).get("PROVIDER_REQUESTS") != 0:
        raise RuntimeError("provider request count is not zero")
    artifacts = dict(freeze.get("artifact_sha256") or {})
    for raw_path in list(artifacts):
        path = Path(raw_path)
        artifacts[raw_path] = sha(path)
    for path in [*FROZEN, TOOL, FINALIZER]:
        artifacts[str(path)] = sha(path)
    freeze["artifact_sha256"] = dict(sorted(artifacts.items()))
    freeze["authorization_gate"] = {
        "quota_recovery_authorized": False,
        "quota_recovery_execution_eligible": False,
        "conditional_template_applicability": "NOT_APPLICABLE_PROFILE_LINEAGE_CHANGE",
        "invalid_reason": "PROFILE_LINEAGE_CHANGE",
        "next_valid_lifecycle": "NEW_FULL_REGENERATION_LINEAGE_440",
    }
    freeze["risk_boundary"] = {
        "preserved_99_status": "HISTORICAL_GR3E_LINEAGE_ONLY",
        "mix_with_current_profile_images_permitted": False,
        "provider_requests": 0,
        "exact_monetary_cost": "UNKNOWN",
    }
    freeze["resealed_at"] = now()
    write(FREEZE, freeze)
    digest = sha(FREEZE)
    sidecar = FREEZE.with_name(FREEZE.name + ".sha256")
    write_text(sidecar, f"{digest}  {FREEZE.name}\n")

    binding_checks = []
    for raw_path, expected in freeze["artifact_sha256"].items():
        actual = sha(Path(raw_path))
        binding_checks.append({"path": raw_path, "expected": expected, "actual": actual, "match": actual == expected})
    terminal = {
        "captured_at": now(),
        "P4D_GR3Q1_STATUS": "BLOCKED_PROFILE_LINEAGE_CHANGE",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "CONTINUATION_COMPATIBLE": False,
        "QUOTA_RECOVERY_AUTHORIZED": False,
        "QUOTA_RECOVERY_EXECUTION_ELIGIBLE": False,
        "PRESERVED_GR3E_SUCCESS": 99,
        "OUTSTANDING": 341,
        "PROVIDER_REQUESTS": 0,
        "FORMAL_INGEST": False,
        "C3": False,
        "NEW_VAL": 0,
        "HOLDOUT": 0,
        "preparation_freeze": str(FREEZE),
        "preparation_freeze_sha256": digest,
        "preparation_sidecar_sha256": sha(sidecar),
        "all_bound_artifacts_match": all(item["match"] for item in binding_checks),
        "next_valid_lifecycle": "NEW_FULL_REGENERATION_LINEAGE_440",
    }
    write(TERMINAL, terminal)

    verify = read(VERIFY) if VERIFY.exists() else {}
    verify.update({
        "captured_at": now(),
        "preparation_freeze_sha256_expected": digest,
        "preparation_freeze_sha256_actual": sha(FREEZE),
        "sidecar_value": sidecar.read_text(encoding="utf-8").split()[0],
        "freeze_self_match": sha(FREEZE) == digest == sidecar.read_text(encoding="utf-8").split()[0],
        "all_bound_artifacts_match": terminal["all_bound_artifacts_match"],
        "bound_artifact_checks": binding_checks,
        "provider_requests": 0,
        "status": "BLOCKED_PROFILE_LINEAGE_CHANGE",
        "continuation_compatible": False,
    })
    write(VERIFY, verify)

    summary = read(SUMMARY) if SUMMARY.exists() else {}
    summary.update({
        "P4D_GR3Q1_STATUS": "BLOCKED_PROFILE_LINEAGE_CHANGE",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "CONTINUATION_COMPATIBLE": False,
        "quota_recovery_authorized": False,
        "quota_recovery_execution_eligible": False,
        "provider_requests": 0,
        "freeze_sha256": digest,
        "final_verification": verify,
        "blocked_reason": "PROFILE_LINEAGE_CHANGE",
        "next_valid_lifecycle": "NEW_FULL_REGENERATION_LINEAGE_440",
    })
    write(SUMMARY, summary)
    print(json.dumps(terminal, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
