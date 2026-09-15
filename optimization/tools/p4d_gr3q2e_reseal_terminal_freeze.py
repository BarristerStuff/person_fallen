#!/usr/bin/env python3
"""Re-seal a stopped P4D_GR3Q2E terminal freeze after SQLite close.

The runner's terminal freeze was written while its SQLite connection was still
open.  SQLite's normal final close/checkpoint changed the main database bytes,
so this tool preserves the original freeze and sidecar, records the one binding
error, then rebinds the canonical freeze to the stable post-close database.
This tool performs no provider, image, dataset, or model operation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
EXEC = ROOT / "08_p4d_new_hard_negative_dev_revision" / "02_generation" / "gr3_fullregen" / "06_execution" / "profile_stratified_recovery_20260828_01"
CANON = EXEC / "freeze" / "p4d_gr3q2e_terminal_freeze.json"
SIDECAR = CANON.with_name(CANON.name + ".sha256")
DB = EXEC / "03_ledger" / "p4d_gr3q2e_execution.sqlite3"
CHECKPOINTS = EXEC / "05_checkpoints"
AUDIT = CHECKPOINTS / "initial_terminal_freeze_binding_error_audit.json"
VERIFY = CHECKPOINTS / "resealed_terminal_freeze_verification.json"
INITIAL = EXEC / "freeze" / "p4d_gr3q2e_terminal_freeze_initial_binding_error.json"
INITIAL_SIDECAR = EXEC / "freeze" / "p4d_gr3q2e_terminal_freeze_initial_binding_error.original_sidecar.txt"
RESEAL_SCRIPT = Path(__file__).resolve()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    if not CANON.is_file() or not SIDECAR.is_file() or not DB.is_file():
        raise RuntimeError("terminal freeze, sidecar, or SQLite database is missing")

    original_bytes = CANON.read_bytes()
    original_sidecar = SIDECAR.read_text(encoding="utf-8")
    original = json.loads(original_bytes.decode("utf-8"))
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    original_sidecar_value = original_sidecar.split()[0] if original_sidecar.split() else None

    mismatches: list[dict[str, Any]] = []
    for raw_path, expected in (original.get("artifact_sha256") or {}).items():
        target = Path(raw_path)
        actual = sha(target)
        if actual != expected:
            mismatches.append({"path": raw_path, "expected": expected, "actual": actual})
    if len(mismatches) != 1 or mismatches[0]["path"] != str(DB):
        raise RuntimeError(f"expected exactly one SQLite binding mismatch, found {mismatches}")
    if original.get("status") != "STOPPED_BY_FAILURE_POLICY":
        raise RuntimeError(f"unexpected terminal status: {original.get('status')}")
    terminal = ((original.get("terminal") or {}).get("stop_marker") or {})
    if terminal.get("status") != "GLOBAL_STOP" or terminal.get("reason") != "HTTP_429":
        raise RuntimeError(f"unexpected stop marker: {terminal}")

    # Preserve the original bytes and sidecar exactly before replacing the
    # canonical path.  These copies are explicitly audit-only evidence.
    if INITIAL.exists() and INITIAL.read_bytes() != original_bytes:
        raise RuntimeError("initial terminal-freeze preservation path already differs")
    if INITIAL_SIDECAR.exists() and INITIAL_SIDECAR.read_text(encoding="utf-8") != original_sidecar:
        raise RuntimeError("initial terminal sidecar preservation path already differs")
    if not INITIAL.exists():
        write_bytes(INITIAL, original_bytes)
    if not INITIAL_SIDECAR.exists():
        write_text(INITIAL_SIDECAR, original_sidecar)

    audit = {
        "stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY",
        "captured_at": now(),
        "kind": "INITIAL_TERMINAL_FREEZE_BINDING_ERROR",
        "original_terminal_freeze_path": str(CANON),
        "original_terminal_freeze_sha256": original_sha,
        "original_sidecar_value": original_sidecar_value,
        "mismatches_before_reseal": mismatches,
        "mismatch_count": len(mismatches),
        "reason": "terminal freeze hashed the SQLite main file while the runner connection was still open; normal SQLite close/checkpoint changed stable database bytes afterward",
        "provider_requests_added_by_reseal": 0,
        "images_generated_by_reseal": 0,
        "dataset_mutation_by_reseal": False,
        "initial_bytes_preserved_at": str(INITIAL),
        "initial_sidecar_preserved_at": str(INITIAL_SIDECAR),
    }
    write_json(AUDIT, audit)

    current_db_sha = sha(DB)
    if not current_db_sha:
        raise RuntimeError("SQLite database disappeared before reseal")
    resealed = copy.deepcopy(original)
    resealed["freeze_binding_revision"] = "RESEALED_AFTER_SQLITE_CLOSE_BINDING_ERROR"
    resealed["initial_binding_error"] = {
        "original_freeze_sha256": original_sha,
        "mismatch_count": len(mismatches),
        "mismatch_path": str(DB),
        "audit_path": str(AUDIT),
        "preserved_original_freeze_path": str(INITIAL),
        "provider_requests_added": 0,
    }
    bindings = dict(resealed.get("artifact_sha256") or {})
    bindings[str(DB)] = current_db_sha
    bindings[str(AUDIT)] = sha(AUDIT)
    bindings[str(INITIAL)] = sha(INITIAL)
    bindings[str(INITIAL_SIDECAR)] = sha(INITIAL_SIDECAR)
    bindings[str(RESEAL_SCRIPT)] = sha(RESEAL_SCRIPT)
    if any(value is None for value in bindings.values()):
        raise RuntimeError("a reseal artifact is missing")
    resealed["artifact_sha256"] = bindings
    write_json(CANON, resealed)
    canonical_sha = sha(CANON)
    if not canonical_sha:
        raise RuntimeError("canonical freeze could not be hashed")
    write_text(SIDECAR, f"{canonical_sha}  {CANON.name}\n")

    checks = []
    for raw_path, expected in bindings.items():
        target = Path(raw_path)
        actual = sha(target)
        checks.append({"path": raw_path, "expected": expected, "actual": actual, "match": actual == expected})
    verification = {
        "stage": "P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY",
        "captured_at": now(),
        "canonical_terminal_freeze_path": str(CANON),
        "canonical_terminal_freeze_sha256": canonical_sha,
        "canonical_sidecar_value": SIDECAR.read_text(encoding="utf-8").split()[0],
        "freeze_self_match": canonical_sha == SIDECAR.read_text(encoding="utf-8").split()[0],
        "bound_artifact_count": len(checks),
        "bad_artifacts": [item for item in checks if not item["match"]],
        "all_bound_artifacts_match": all(item["match"] for item in checks),
        "provider_requests_added_by_reseal": 0,
        "status": resealed.get("status"),
        "stop_reason": (resealed.get("terminal") or {}).get("stop_marker", {}).get("reason"),
    }
    verification["all_pass"] = bool(verification["freeze_self_match"] and verification["all_bound_artifacts_match"] and verification["status"] == "STOPPED_BY_FAILURE_POLICY" and verification["stop_reason"] == "HTTP_429")
    write_json(VERIFY, verification)
    print(json.dumps({"canonical_terminal_freeze_sha256": canonical_sha, "initial_terminal_freeze_sha256": original_sha, "initial_mismatch_count": len(mismatches), "bound_artifact_count": len(checks), "all_bound_artifacts_match": verification["all_bound_artifacts_match"], "provider_requests_added": 0, "status": resealed.get("status")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise SystemExit(2)
