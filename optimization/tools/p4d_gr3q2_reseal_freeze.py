#!/usr/bin/env python3
"""Preserve and repair a locally-invalid GR3Q2 preparation freeze binding.

No provider, dataset, image, model, or parent artifact is touched.  The first
GR3Q2 freeze is retained byte-for-byte as a binding-error artifact because a
duplicate zero-request preparation overwrote several files after it was made.
This tool writes a new canonical sidecar-bound freeze over the current GR3Q2
freeze path only after rebinding stable local artifacts and proving their SHA
matches.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
REV = ROOT / "08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/lineage_policy_amendment_20260828_01"
FREEZE = REV / "freeze" / "p4d_gr3q2_preparation_freeze.json"
SIDECAR = FREEZE.with_name(FREEZE.name + ".sha256")
CHECKPOINTS = REV / "05_checkpoints"
SUMMARY = REV / "preparation_summary.json"
PREP_TOOL = ROOT / "tools" / "p4d_gr3q2_prepare.py"
SELF = ROOT / "tools" / "p4d_gr3q2_reseal_freeze.py"
INITIAL_COPY = FREEZE.with_name("p4d_gr3q2_preparation_freeze_initial_binding_error.json")
INITIAL_SIDECAR_COPY = FREEZE.with_name("p4d_gr3q2_preparation_freeze_initial_binding_error.original_sidecar.txt")
INITIAL_AUDIT = CHECKPOINTS / "initial_freeze_binding_error_audit.json"
TERMINAL = CHECKPOINTS / "resealed_preparation_terminal.json"
FINAL_VERIFY = CHECKPOINTS / "resealed_final_verification.json"


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


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    if INITIAL_COPY.exists() or INITIAL_AUDIT.exists():
        raise RuntimeError("initial binding-error evidence already exists; refusing reseal overwrite")
    original_bytes = FREEZE.read_bytes()
    original_sidecar = SIDECAR.read_text(encoding="utf-8")
    original = json.loads(original_bytes.decode("utf-8"))
    if original.get("status") != "READY_AWAITING_PROFILE_STRATIFIED_RECOVERY_AUTHORIZATION":
        raise RuntimeError("unexpected GR3Q2 status")
    if (original.get("terminal") or {}).get("PROVIDER_REQUESTS") != 0:
        raise RuntimeError("provider request count is not zero")
    original_checks = []
    for raw_path, expected in (original.get("artifact_sha256") or {}).items():
        actual = sha(Path(raw_path))
        original_checks.append({"path": raw_path, "expected": expected, "actual": actual, "match": actual == expected})
    mismatches = [item for item in original_checks if not item["match"]]
    if not mismatches:
        raise RuntimeError("original freeze unexpectedly has no binding error")
    write_bytes(INITIAL_COPY, original_bytes)
    write_text(INITIAL_SIDECAR_COPY, original_sidecar)
    audit = {
        "captured_at": now(), "reason": "duplicate zero-request preparation rewrote local artifacts after initial freeze creation", "initial_freeze_path": str(FREEZE),
        "initial_freeze_sha256": hashlib.sha256(original_bytes).hexdigest(), "initial_sidecar_value": original_sidecar.split()[0], "initial_sidecar_match": hashlib.sha256(original_bytes).hexdigest() == original_sidecar.split()[0],
        "initial_freeze_preserved_copy": str(INITIAL_COPY), "initial_freeze_preserved_copy_sha256": sha(INITIAL_COPY), "initial_sidecar_preserved_copy": str(INITIAL_SIDECAR_COPY),
        "bound_artifact_count": len(original_checks), "mismatch_count": len(mismatches), "mismatches": mismatches,
        "provider_requests": 0, "formal_ingest": False, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0,
    }
    write_json(INITIAL_AUDIT, audit)

    stable = dict(original.get("artifact_sha256") or {})
    for raw_path in list(stable):
        stable[raw_path] = sha(Path(raw_path))
    stable[str(PREP_TOOL)] = sha(PREP_TOOL)
    stable[str(SELF)] = sha(SELF)
    stable[str(INITIAL_COPY)] = sha(INITIAL_COPY)
    stable[str(INITIAL_SIDECAR_COPY)] = sha(INITIAL_SIDECAR_COPY)
    stable[str(INITIAL_AUDIT)] = sha(INITIAL_AUDIT)
    repaired = dict(original)
    repaired["artifact_sha256"] = dict(sorted(stable.items()))
    repaired["freeze_binding_revision"] = "RESEALED_AFTER_INITIAL_LOCAL_BINDING_ERROR"
    repaired["initial_binding_error"] = {
        "initial_freeze_preserved": str(INITIAL_COPY), "initial_freeze_sha256": sha(INITIAL_COPY), "initial_binding_error_audit": str(INITIAL_AUDIT), "initial_binding_error_audit_sha256": sha(INITIAL_AUDIT), "mismatch_count": len(mismatches),
        "reason": "local duplicate preparation artifact rewrite; no provider/image/dataset action",
    }
    repaired["resealed_at"] = now()
    write_json(FREEZE, repaired)
    digest = sha(FREEZE)
    write_text(SIDECAR, f"{digest}  {FREEZE.name}\n")

    final_checks = []
    for raw_path, expected in repaired["artifact_sha256"].items():
        actual = sha(Path(raw_path))
        final_checks.append({"path": raw_path, "expected": expected, "actual": actual, "match": actual == expected})
    terminal = {
        "captured_at": now(), "P4D_GR3Q2_STATUS": repaired["status"], "P4D_STATUS": repaired["P4D_STATUS"], "freeze_binding_revision": repaired["freeze_binding_revision"],
        "canonical_freeze": str(FREEZE), "canonical_freeze_sha256": digest, "canonical_sidecar_sha256": sha(SIDECAR), "canonical_sidecar_value": SIDECAR.read_text(encoding="utf-8").split()[0],
        "all_bound_artifacts_match": all(item["match"] for item in final_checks), "bound_artifact_count": len(final_checks), "provider_requests": 0,
        "formal_ingest": False, "C3": False, "NEW_VAL": 0, "HOLDOUT": 0, "HOLDOUT_CONSUMED": False,
    }
    write_json(TERMINAL, terminal)
    final = {"captured_at": now(), **terminal, "bound_artifact_checks": final_checks, "freeze_self_match": sha(FREEZE) == digest == SIDECAR.read_text(encoding="utf-8").split()[0]}
    write_json(FINAL_VERIFY, final)
    summary = read(SUMMARY)
    summary["freeze_path"] = str(FREEZE)
    summary["freeze_sha256"] = digest
    summary["initial_freeze_binding_error"] = audit
    summary["resealed_final_verification"] = final
    write_json(SUMMARY, summary)
    print(json.dumps({"status": terminal["P4D_GR3Q2_STATUS"], "freeze_sha256": digest, "mismatch_count_initial": len(mismatches), "bound_artifacts": len(final_checks), "all_bound_artifacts_match": terminal["all_bound_artifacts_match"], "provider_requests": 0}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
