#!/usr/bin/env python3
"""Seal Q6's post-preparation, zero-provider-request supplements once."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
Q6 = ROOT / '08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_03_gr3q6_20260831_02'
INITIAL = Q6 / 'freeze/p4d_gr3q6_preparation_freeze.json'
OUT = Q6 / 'freeze/p4d_gr3q6_preparation_supplement_freeze.json'
VERIFY = Q6 / '05_checkpoints/preparation_supplement_verification.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    with temp.open('rb') as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)


def main() -> None:
    if OUT.exists() or Path(str(OUT) + '.sha256').exists() or VERIFY.exists():
        raise RuntimeError('supplement seal already exists; immutable once written')
    initial = json.loads(INITIAL.read_text(encoding='utf-8'))
    initial_checks = {path: sha256(Path(path)) == expected for path, expected in initial['artifact_sha256'].items()}
    if not all(initial_checks.values()):
        raise RuntimeError('initial Q6 preparation freeze integrity mismatch')
    if Path(str(INITIAL) + '.sha256').read_text(encoding='utf-8').split()[0] != sha256(INITIAL):
        raise RuntimeError('initial Q6 preparation sidecar mismatch')
    ledger = Q6 / '03_ledger/gr3q6.sqlite3'
    db = sqlite3.connect(ledger)
    try:
        state_counts = dict(db.execute('SELECT state, COUNT(*) FROM slots GROUP BY state'))
        metadata = dict(db.execute('SELECT key, value FROM metadata'))
        checkpoint = db.execute('PRAGMA wal_checkpoint(FULL)').fetchone()
    finally:
        db.close()
    if state_counts != {'NOT_STARTED': 33} or metadata.get('authorization_present') != 'false':
        raise RuntimeError(f'unsafe ledger state: {state_counts!r}, authorized={metadata.get("authorization_present")!r}')
    artifacts = [
        INITIAL,
        Path(str(INITIAL) + '.sha256'),
        Q6 / 'retry_event_parser_v2.py',
        Q6 / 'p4d_gr3q6_runner.py',
        ledger,
        Q6 / '00_preflight/q5_retry_telemetry_erratum.json',
        Q6 / '00_preflight/provider_runtime.json',
        Q6 / '01_inventory/current_verified_success_142.csv',
        Q6 / '01_inventory/outstanding_298.csv',
        Q6 / '02_plan/q6_balanced_window_33_plan.csv',
        Q6 / '02_plan/q6_plan_audit.json',
        Q6 / '05_checkpoints/authorization_gate.json',
        ROOT / 'reports/95_p4d_gr3q5_retry_telemetry_erratum.md',
        ROOT / 'reports/96_p4d_gr3q6_preflight_and_reset.md',
        ROOT / 'reports/97_p4d_gr3q6_balanced_33_plan.md',
        ROOT / 'reports/100_p4d_gr3q6_final.md',
        ROOT / 'PERSON_FALLEN_V2.md',
        Path(__file__),
    ]
    freeze = {
        'stage': 'P4D_GR3Q6_BALANCED_QUOTA_RESET_RECOVERY',
        'kind': 'PREPARATION_SUPPLEMENT_FREEZE',
        'status': 'AWAITING_Q6_GENERATION_AUTHORIZATION',
        'provider_requests': 0,
        'logical_invocations': 0,
        'parent_q5_freeze_sha256': initial['parent_q5_freeze_sha256'],
        'initial_preparation_freeze_sha256': sha256(INITIAL),
        'initial_preparation_freeze_verified': True,
        'ledger_state_counts': state_counts,
        'ledger_wal_checkpoint': list(checkpoint),
        'reports_98_99_absent_reason': 'execution_and_partial_qa_not_run_without_authorization',
        'artifact_sha256': {str(path): sha256(path) for path in artifacts},
    }
    atomic_json(OUT, freeze)
    digest = sha256(OUT)
    sidecar = Path(str(OUT) + '.sha256')
    sidecar.write_text(f'{digest}  {OUT.name}\n', encoding='utf-8')
    with sidecar.open('rb') as handle:
        os.fsync(handle.fileno())
    verification = {
        'freeze_sha256': digest,
        'sidecar_match': sidecar.read_text(encoding='utf-8').split()[0] == digest,
        'bound_artifact_count': len(freeze['artifact_sha256']),
        'all_bound_artifacts_match': all(sha256(Path(path)) == expected for path, expected in freeze['artifact_sha256'].items()),
        'status': freeze['status'],
        'provider_requests': 0,
        'logical_invocations': 0,
    }
    atomic_json(VERIFY, verification)
    print(json.dumps(verification, sort_keys=True))


if __name__ == '__main__':
    main()
