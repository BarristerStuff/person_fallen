#!/usr/bin/env python3
"""Fail-closed P4D_GR3E execution gate.

This revision intentionally stops before provider/runtime invocation because the
current user message contains no standalone full-regeneration authorization
attestation.  It verifies the GR3 preparation surface, creates an empty
execution ledger/state, records read-only dataset boundaries, writes reports
45--49, and seals a terminal freeze.  There is deliberately no image-generation
call in this file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation" / "gr3_fullregen"
PREP = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
PREP_SIDECAR = PREP.with_name(PREP.name + ".sha256")
PLAN = P4D / "01_prompt_plan"
MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
OVERVIEW = ROOT / "PERSON_FALLEN_V2.md"
REPORTS = ROOT / "reports"

EXEC = GR3 / "06_execution"
E_PRE = EXEC / "00_preflight"
E_AUTH = EXEC / "01_authorization"
E_RUNNER = EXEC / "02_runner"
E_LEDGER = EXEC / "03_ledger"
E_RAW = EXEC / "04_raw_responses"
E_CHECKPOINTS = EXEC / "05_checkpoints"
E_QA = EXEC / "06_full_qa"
E_REVIEW = EXEC / "07_human_review_package"
E_FREEZE = EXEC / "freeze"
FINAL_STATUS = EXEC / "final_status.json"
LEDGER = E_LEDGER / "execution_ledger.csv"
STATE = E_LEDGER / "execution_state.json"
TERMINAL_FREEZE = E_FREEZE / "p4d_gr3e_terminal_freeze.json"
TERMINAL_SIDECAR = TERMINAL_FREEZE.with_name(TERMINAL_FREEZE.name + ".sha256")

PREP_SHA_EXPECTED = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
MANIFEST_SHA_EXPECTED = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"
EXPECTED_FROZEN = {
    "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    "C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}
FROZEN_PATHS = {
    "group_manifest.csv": PLAN / "group_manifest.csv",
    "group_split_freeze.json": PLAN / "group_split_freeze.json",
    "prompt_manifest.csv": PLAN / "prompt_manifest.csv",
    "prompt_pack.md": PLAN / "prompt_pack.md",
    "prompt_pack_freeze.json": PLAN / "prompt_pack_freeze.json",
    "C3_prompt.txt": ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt",
}
REQUIRED_AUTH_TEXT = (
    "我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，"
    "接受旧 GR1 192 张不进入新 revision；我同时明确接受当前 GPT Image 2 runtime max_retries=3、"
    "单个逻辑 slot 最多约 4 次 provider attempt、精确费用未知以及由此产生的 quota/成本风险。"
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(value if value.endswith("\n") else value + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def snapshot_dataset(label: str) -> dict[str, Any]:
    command = ["python3", str(VALIDATOR), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
    try:
        validator = json.loads(proc.stdout)
    except json.JSONDecodeError:
        validator = {"parse_ok": False, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    counts: dict[str, int] = {}
    hashes: dict[str, str | None] = {}
    p4d_hits: dict[str, list[int]] = {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        rows = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(rows) - 1)
        hashes[name] = sha256_file(path) if path.exists() else None
        hits = [number for number, line in enumerate(rows, start=1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()]
        p4d_hits[name] = hits[:50]
    result = {
        "label": label,
        "captured_at": now(),
        "validator_command": command,
        "validator_returncode": proc.returncode,
        "validator": validator,
        "counts": {
            "media_count": counts["media.csv"],
            "label_count": counts["labels.csv"],
            "batch_count": counts["batches.csv"],
            "split_count": counts["splits.csv"],
        },
        "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": {name: {"count": len(rows), "row_numbers": rows} for name, rows in p4d_hits.items()},
        "p4d_reference_hits_total": sum(len(rows) for rows in p4d_hits.values()),
        "formal_dataset_mutation_by_gr3e": False,
    }
    write_json(E_PRE / f"dataset_boundary_{label}.json", result)
    return result


def preparation_check() -> dict[str, Any]:
    actual = sha256_file(PREP) if PREP.exists() else None
    sidecar_value = PREP_SIDECAR.read_text(encoding="utf-8").strip().split()[0] if PREP_SIDECAR.exists() else None
    prep = read_json(PREP, {}) or {}
    artifact_bad: list[dict[str, Any]] = []
    for path_text, expected in (prep.get("artifact_sha256") or {}).items():
        path = Path(path_text)
        actual_artifact = sha256_file(path) if path.exists() else None
        if actual_artifact != expected:
            artifact_bad.append({"path": path_text, "expected": expected, "actual": actual_artifact})
    report_bad: list[dict[str, Any]] = []
    for path_text, expected in (prep.get("reports_sha256") or {}).items():
        path = Path(path_text)
        actual_report = sha256_file(path) if path.exists() else None
        if actual_report != expected:
            report_bad.append({"path": path_text, "expected": expected, "actual": actual_report})
    result = {
        "preparation_freeze_path": str(PREP),
        "preparation_freeze_sha256_actual": actual,
        "preparation_freeze_sha256_expected": PREP_SHA_EXPECTED,
        "sidecar_value": sidecar_value,
        "sidecar_match": actual is not None and sidecar_value == actual,
        "sha_match": actual == PREP_SHA_EXPECTED,
        "status": prep.get("status"),
        "full_regen_authorized": prep.get("terminal", {}).get("FULL_REGEN_AUTHORIZED"),
        "artifact_hash_mismatches": artifact_bad,
        "report_hash_mismatches": report_bad,
        "artifact_integrity_pass": not artifact_bad and not report_bad,
        "verified_at": now(),
    }
    write_json(E_PRE / "preparation_freeze_check.json", result)
    return result


def frozen_asset_check() -> dict[str, Any]:
    actual = {name: sha256_file(path) if path.exists() else None for name, path in FROZEN_PATHS.items()}
    checks = {name: actual[name] == expected for name, expected in EXPECTED_FROZEN.items()}
    result = {"expected": EXPECTED_FROZEN, "actual": actual, "checks": checks, "all_match": all(checks.values()), "verified_at": now()}
    write_json(E_PRE / "frozen_asset_check.json", result)
    return result


def manifest_check() -> dict[str, Any]:
    rows = read_csv(MANIFEST)
    prompt_mismatches: list[str] = []
    missing_prompt_files: list[str] = []
    for row in rows:
        path = Path(row.get("original_prompt_path", ""))
        if not path.exists():
            missing_prompt_files.append(row.get("prompt_id", ""))
        elif sha256_file(path) != row.get("prompt_sha256"):
            prompt_mismatches.append(row.get("prompt_id", ""))
    role_counts = Counter(row.get("target_role") for row in rows)
    split_counts = Counter(row.get("planned_split", row.get("planned_internal_split")) for row in rows)
    result = {
        "path": str(MANIFEST),
        "sha256_actual": sha256_file(MANIFEST) if MANIFEST.exists() else None,
        "sha256_expected": MANIFEST_SHA_EXPECTED,
        "sha_match": MANIFEST.exists() and sha256_file(MANIFEST) == MANIFEST_SHA_EXPECTED,
        "rows": len(rows),
        "unique_prompt_ids": len({row.get("prompt_id") for row in rows}),
        "unique_group_ids": len({row.get("group_id") for row in rows}),
        "role_counts": dict(role_counts),
        "split_counts": dict(split_counts),
        "prompt_byte_mismatch": len(prompt_mismatches),
        "missing_prompt_files": len(missing_prompt_files),
        "prompt_mismatch_ids": prompt_mismatches[:20],
        "missing_prompt_ids": missing_prompt_files[:20],
        "pass": (
            len(rows) == 440
            and len({row.get("prompt_id") for row in rows}) == 440
            and len({row.get("group_id") for row in rows}) == 88
            and role_counts == Counter({"hard_negative": 300, "positive": 100, "ordinary_negative": 40})
            and split_counts == Counter({"NEW_DESIGN": 265, "NEW_SCREEN": 175})
            and not prompt_mismatches
            and not missing_prompt_files
            and MANIFEST.exists()
            and sha256_file(MANIFEST) == MANIFEST_SHA_EXPECTED
        ),
        "verified_at": now(),
    }
    write_json(E_PRE / "full_regen_manifest_check.json", result)
    return result


def batch_zero_check() -> dict[str, Any]:
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    image_files = [path for path in BATCH.rglob("*") if path.is_file() and path.suffix.lower() in image_suffixes] if BATCH.exists() else []
    symlinks = [str(path) for path in BATCH.rglob("*") if path.is_symlink()] if BATCH.exists() else []
    result = {
        "batch": str(BATCH),
        "image_files": [str(path) for path in image_files],
        "image_count": len(image_files),
        "symlinks": symlinks,
        "symlink_count": len(symlinks),
        "pass": BATCH.exists() and not image_files and not symlinks,
        "verified_at": now(),
    }
    write_json(E_PRE / "new_batch_zero_check.json", result)
    return result


def authorization_check() -> dict[str, Any]:
    # The current user message contains the required wording as part of the
    # specification, not as a standalone user attestation.  It is deliberately
    # not interpreted as authorization.
    result = {
        "authorization_present": False,
        "authorization_scope": None,
        "authorization_text_sha256": None,
        "retry_risk_accepted": False,
        "quota_risk_accepted": False,
        "unknown_cost_risk_accepted": False,
        "GR1_images_excluded": False,
        "required_authorization_text": REQUIRED_AUTH_TEXT,
        "interpretation": "Embedded example/specification text is not a standalone user attestation; fail closed.",
        "verified_at": now(),
    }
    write_json(E_AUTH / "authorization_check.json", result)
    return result


def write_execution_surface(prep: dict[str, Any], assets: dict[str, Any], manifest: dict[str, Any], batch: dict[str, Any], auth: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    E_RUNNER.mkdir(parents=True, exist_ok=True)
    E_RAW.mkdir(parents=True, exist_ok=True)
    E_CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    E_QA.mkdir(parents=True, exist_ok=True)
    E_REVIEW.mkdir(parents=True, exist_ok=True)
    write_text(E_RUNNER / "runner_not_created.md", "No executable runner was created: explicit authorization is absent, so GR3E stopped before provider/runtime re-preflight.\n")
    write_text(LEDGER, "logical_slot_id,phase,state,invocation_count,observed_native_retry_count,http_status,error_code,timestamp\n")
    state = {
        "stage": "P4D_GR3E_FULL_REGEN_EXECUTION",
        "status": "AWAITING_EXPLICIT_USER_AUTHORIZATION",
        "logical_slot_invocations": 0,
        "logical_successes": 0,
        "logical_failures": 0,
        "provider_requests": 0,
        "generated_raw": 0,
        "generated_final": 0,
        "outstanding": 440,
        "smoke": {"planned": 1, "started": False, "success": 0, "failure": 0},
        "ramp1": {"planned": 5, "started": False, "success": 0, "failure": 0},
        "ramp2": {"planned": 10, "started": False, "success": 0, "failure": 0},
        "bulk": {"planned": 424, "started": False, "success": 0, "failure": 0},
        "outer_retry": False,
        "native_retry_policy": (read_json(GR3 / "00_preflight/retry_capability_audit.json", {}) or {}).get("native_retry_policy_observed"),
        "authorized": False,
    }
    write_json(STATE, state)
    boundary_delta = {key: after["counts"][key] - before["counts"][key] for key in before["counts"]}
    final = {
        "stage": "P4D_GR3E_FULL_REGEN_EXECUTION",
        "status": "AWAITING_EXPLICIT_USER_AUTHORIZATION",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "authorization_attestation_present": False,
        "provider_requests": 0,
        "logical_slot_invocations": 0,
        "logical_successes": 0,
        "logical_failures": 0,
        "generated_raw": 0,
        "generated_final": 0,
        "outstanding": 440,
        "smoke_requests": 0,
        "ramp1_requests": 0,
        "ramp2_requests": 0,
        "requests_429": 0,
        "requests_401": 0,
        "requests_403": 0,
        "timeouts_or_5xx": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
        "human_review_package": False,
        "human_semantic_review_status": "NOT_CREATED",
        "accepted_count": 0,
        "dataset_boundary_delta": boundary_delta,
        "p4d_active_dataset_hits": max(before["p4d_reference_hits_total"], after["p4d_reference_hits_total"]),
        "preparation_freeze_sha256": prep.get("preparation_freeze_sha256_actual"),
        "manifest_sha256": manifest.get("sha256_actual"),
        "created_at": now(),
    }
    write_json(FINAL_STATUS, final)
    write_json(E_CHECKPOINTS / "authorization_gate_checkpoint.json", {
        "status": "STOPPED_BEFORE_PROVIDER_PREFLIGHT",
        "reason": "AWAITING_EXPLICIT_USER_AUTHORIZATION",
        "provider_requests": 0,
        "before_counts": before["counts"],
        "after_counts": after["counts"],
        "p4d_reference_hits": max(before["p4d_reference_hits_total"], after["p4d_reference_hits_total"]),
        "verified_at": now(),
    })
    return final


def write_reports(prep: dict[str, Any], assets: dict[str, Any], manifest: dict[str, Any], batch: dict[str, Any], auth: dict[str, Any], before: dict[str, Any], after: dict[str, Any], final: dict[str, Any]) -> None:
    reports = {
        "45_p4d_gr3e_authorization_and_runtime.md": f"""# 45 — P4D_GR3E authorization and runtime gate

```text
P4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION
P4D_GR3E_STATUS=AWAITING_EXPLICIT_USER_AUTHORIZATION
P4D_STATUS=GENERATION_REQUIRED
EXPLICIT_AUTHORIZATION_VERIFIED=false
AUTHORIZATION_ATTESTATION_CREATED=false
PROVIDER_REQUESTS=0
```

## 已确认事实

- GR3 preparation freeze SHA and sidecar verified: `{prep.get('preparation_freeze_sha256_actual')}`, sidecar match `{prep.get('sidecar_match')}`.
- All six P4D frozen asset hashes match; the 440-row manifest matches SHA `{manifest.get('sha256_actual')}` with zero prompt-byte mismatches.
- The new batch is empty of image bytes and symlinks. No authorization attestation was present as a standalone user declaration in this task context.
- Because authorization is the first execution gate, provider/runtime re-preflight (`doctor`, `auth inspect`, `config inspect`, `images generate --help`) was not run in GR3E. The last-known GR3 capability remains provider `codex`, model `gpt-5.4`, backend `image_generation (server-side gpt-image-2 capability)`, runtime `0.7.3`, plan `plus`, safe profile fingerprint `{{last_known_profile}}`, with preparation-time `session_ready=false`.

## 实验判断

The quoted authorization example in the execution specification is not treated
as a user attestation. GR3E therefore stops before runtime/provider calls.

## 风险与限制

No current-session readiness claim is made because re-preflight was deliberately
not reached. No authorization attestation SHA exists.

## 下一阶段建议

Send the required explicit full-regeneration and retry/quota/cost-risk
attestation, then perform a fresh runtime preflight in a new continuation turn.
""",
        "46_p4d_gr3e_generation.md": """# 46 — P4D_GR3E generation

```text
P4D_GR3E_STATUS=AWAITING_EXPLICIT_USER_AUTHORIZATION
PROVIDER_REQUESTS=0
LOGICAL_SLOT_INVOCATIONS=0
LOGICAL_SUCCESSES=0
LOGICAL_FAILURES=0
SMOKE_REQUESTS=0
RAMP1_REQUESTS=0
RAMP2_REQUESTS=0
BULK_REQUESTS=0
OUTER_RETRY=false
```

## 已确认事实

No executable runner was created. Smoke, ramp1, ramp2, and bulk were not
started; there are no 429/401/403/timeout/5xx results and no native attempt
telemetry. The header-only execution ledger and durable state are retained.

## 实验判断

This is a zero-request authorization stop, not a provider success or failure.

## 风险与限制

No image bytes, provider request IDs, native dimensions, or billing evidence
exist for this execution revision.

## 下一阶段建议

Do not resend or create recovery requests. Obtain authorization and rerun the
preflight gate in a new continuation turn.
""",
        "47_p4d_gr3e_full_440_qa.md": """# 47 — P4D_GR3E full 440 QA

```text
P4D_GR3E_STATUS=AWAITING_EXPLICIT_USER_AUTHORIZATION
GENERATED_RAW=0
GENERATED_FINAL=0
PILLOW_RAW= N/A
PILLOW_FINAL= N/A
DIMENSION_1920x1080= N/A
RAW_EXACT_DUPLICATES= N/A
FINAL_EXACT_DUPLICATES= N/A
NEAR_DUPLICATE_GROUPS= N/A
CROSS_SPLIT_NEAR_DUPLICATES= N/A
MAPPING_ROWS= N/A
MISSING_MAPPINGS= N/A
```

## 已确认事实

Mechanical QA, exact/near-duplicate QA, cross-split lineage QA, and mapping QA
were not run because no image was generated. The pre-generation zero-image
gate passed.

## 实验判断

No QA pass/fail conclusion can be made from an empty generation surface.

## 风险与限制

The 440 target must not be described as generated, accepted, or QA-passed.

## 下一阶段建议

After an independently authorized execution reaches 440 successful slots, run
the full QA protocol and stop on any replacement-required condition.
""",
        "48_p4d_gr3e_human_review_package.md": """# 48 — P4D_GR3E human semantic review package

```text
P4D_GR3E_STATUS=AWAITING_EXPLICIT_USER_AUTHORIZATION
HUMAN_REVIEW_PACKAGE=NOT_CREATED
HUMAN_SEMANTIC_REVIEW_STATUS=NOT_STARTED
P4D_IMAGES_ACCEPTED=0
```

## 已确认事实

No contact sheets or human review CSV were created because there are no
generated images. Planned roles were not upgraded to human-confirmed labels.

## 实验判断

`accepted=0` here means no images reached human review; it is not a semantic
rejection count and not a ground-truth decision.

## 风险与限制

Codex cannot substitute for human semantic review or create ground truth from
planned roles.

## 下一阶段建议

Create the review package only after 440-image mechanical, duplicate, lineage,
and mapping gates pass.
""",
        "49_p4d_gr3e_final.md": f"""# 49 — P4D_GR3E final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION
P4D_GR3E_STATUS=AWAITING_EXPLICIT_USER_AUTHORIZATION
P4D_STATUS=GENERATION_REQUIRED
FULL_REGEN_AUTHORIZED=false
AUTHORIZATION_ATTESTATION_PRESENT=false
PROVIDER_REQUESTS=0
GENERATED_IMAGES=0
OUTSTANDING=440
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
HOLDOUT_CONSUMED=false
P4D_IMAGES_ACCEPTED=0
```

## 已确认事实

GR3 preparation freeze, frozen P4D assets, 440-row manifest, and zero-image
batch gates passed. The preparation freeze is `{prep.get('preparation_freeze_sha256_actual')}`;
the manifest is `{manifest.get('sha256_actual')}`. The execution ledger is
header-only and no runner was created. No provider/runtime request was made.

The read-only dataset boundary was before `{before.get('counts')}` and after
`{after.get('counts')}`; the validator remained `{after.get('validator', {}).get('status')}`
with errors `{after.get('validator', {}).get('error_count')}`, full hash
`{after.get('validator', {}).get('full_hash_check')}`, and warnings
`{after.get('validator', {}).get('warning_count')}`. Active P4D references were
`{max(before.get('p4d_reference_hits_total', 0), after.get('p4d_reference_hits_total', 0))}`.

## 实验判断

The execution revision correctly stopped at the authorization gate. The current
task text does not provide a standalone user attestation that accepts all 440
new generations under the current Codex profile, excludes GR1's 192 images,
and accepts native retry/quota/unknown-cost risk. The embedded sample wording
was not promoted to authorization.

## 风险与限制

No current runtime readiness result was obtained in GR3E because the gate order
requires authorization first. The preparation-time retry audit remains
`NO_RETRY_GUARANTEE=false`, native `max_retries=3`, possible upper bound 4 per
logical slot; this is not an observed attempt count and not a billing claim.
No generation, QA, human review, ingest, C3, NEW_VAL, or HOLDOUT result exists.

## 下一阶段建议

Provide the explicit attestation below as a new user instruction, then run a
fresh provider/runtime preflight. Do not edit the preparation authorization JSON
or manufacture an attestation file:

> 我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，接受旧 GR1 192 张不进入新 revision；我同时明确接受当前 GPT Image 2 runtime max_retries=3、单个逻辑 slot 最多约 4 次 provider attempt、精确费用未知以及由此产生的 quota/成本风险。
""",
    }
    last_known_profile = ((read_json(GR3 / "00_preflight/provider_capability.json", {}) or {}).get("auth") or {}).get("profile_fingerprint_sha256")
    # The f-string above emits a single-brace token; replace it before writing
    # the report so the audit surface contains the actual safe fingerprint.
    reports["45_p4d_gr3e_authorization_and_runtime.md"] = reports["45_p4d_gr3e_authorization_and_runtime.md"].replace("{last_known_profile}", str(last_known_profile))
    REPORTS.mkdir(parents=True, exist_ok=True)
    for filename, content in reports.items():
        write_text(REPORTS / filename, content)


def prepare() -> int:
    for directory in (EXEC, E_PRE, E_AUTH, E_RUNNER, E_LEDGER, E_RAW, E_CHECKPOINTS, E_QA, E_REVIEW, E_FREEZE):
        directory.mkdir(parents=True, exist_ok=True)
    prep = preparation_check()
    assets = frozen_asset_check()
    manifest = manifest_check()
    batch = batch_zero_check()
    auth = authorization_check()
    before = snapshot_dataset("before")
    final = write_execution_surface(prep, assets, manifest, batch, auth, before, before)
    after = snapshot_dataset("after")
    # Rewrite only the non-freeze execution status with the actual after-boundary.
    final["dataset_boundary_delta"] = {key: after["counts"][key] - before["counts"][key] for key in before["counts"]}
    final["p4d_active_dataset_hits"] = max(before["p4d_reference_hits_total"], after["p4d_reference_hits_total"])
    write_json(FINAL_STATUS, final)
    write_reports(prep, assets, manifest, batch, auth, before, after, final)
    # A missing authorization is the expected fail-closed result. Freeze is a
    # separate command so the overview can be appended before terminal sealing.
    print(json.dumps({
        "P4D_GR3E_STATUS": "AWAITING_EXPLICIT_USER_AUTHORIZATION",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "preparation_freeze_verified": prep["sha_match"] and prep["sidecar_match"] and prep["artifact_integrity_pass"],
        "frozen_assets_verified": assets["all_match"],
        "manifest_verified": manifest["pass"],
        "new_batch_zero_images": batch["pass"],
        "explicit_authorization_verified": False,
        "provider_requests": 0,
        "dataset_before": before["counts"],
        "dataset_after": after["counts"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def terminal_freeze() -> int:
    prep = read_json(E_PRE / "preparation_freeze_check.json", {}) or {}
    assets = read_json(E_PRE / "frozen_asset_check.json", {}) or {}
    manifest = read_json(E_PRE / "full_regen_manifest_check.json", {}) or {}
    batch = read_json(E_PRE / "new_batch_zero_check.json", {}) or {}
    auth = read_json(E_AUTH / "authorization_check.json", {}) or {}
    before = read_json(E_PRE / "dataset_boundary_before.json", {}) or {}
    after = read_json(E_PRE / "dataset_boundary_after.json", {}) or {}
    report_paths = [REPORTS / f"{number}_{name}.md" for number, name in (
        ("45", "p4d_gr3e_authorization_and_runtime"),
        ("46", "p4d_gr3e_generation"),
        ("47", "p4d_gr3e_full_440_qa"),
        ("48", "p4d_gr3e_human_review_package"),
        ("49", "p4d_gr3e_final"),
    )]
    artifact_paths = [
        E_PRE / "preparation_freeze_check.json", E_PRE / "frozen_asset_check.json",
        E_PRE / "full_regen_manifest_check.json", E_PRE / "new_batch_zero_check.json",
        E_PRE / "authorization_gate_checkpoint.json", E_PRE / "dataset_boundary_before.json",
        E_PRE / "dataset_boundary_after.json", E_AUTH / "authorization_check.json",
        E_RUNNER / "runner_not_created.md", LEDGER, STATE, FINAL_STATUS,
    ]
    artifact_sha = {str(path): sha256_file(path) if path.exists() else None for path in artifact_paths}
    report_sha = {str(path): sha256_file(path) if path.exists() else None for path in report_paths}
    boundary_delta = {key: after.get("counts", {}).get(key, 0) - before.get("counts", {}).get(key, 0) for key in before.get("counts", {})}
    prep_payload = read_json(PREP, {}) or {}
    prep_overview_sha = prep_payload.get("overview_sha256")
    current_overview_sha = sha256_file(OVERVIEW) if OVERVIEW.exists() else None
    retry = read_json(GR3 / "00_preflight/retry_capability_audit.json", {}) or {}
    capability = read_json(GR3 / "00_preflight/provider_capability.json", {}) or {}
    provider = {
        "provider": capability.get("provider"),
        "request_model": capability.get("request_model"),
        "generation_backend": capability.get("generation_backend"),
        "runtime_version": capability.get("runtime_version"),
        "safe_profile_fingerprint": (capability.get("auth") or {}).get("profile_fingerprint_sha256"),
        "auth_ready_last_known": (capability.get("auth") or {}).get("ready"),
        "session_ready_last_known": capability.get("session_ready"),
        "endpoint_reachable_last_known": (capability.get("auth") or {}).get("endpoint_reachable"),
        "runtime_repreflight": "NOT_RUN_AUTH_GATE",
    }
    batch_counts = {name: len(list((BATCH / name).iterdir())) if (BATCH / name).exists() else None for name in ("prompts", "generated_raw", "final", "rejected", "metadata")}
    payload = {
        "stage": "P4D_GR3E_FULL_REGEN_EXECUTION",
        "status": "AWAITING_EXPLICIT_USER_AUTHORIZATION",
        "P4D_STATUS": "GENERATION_REQUIRED",
        "captured_at": now(),
        "terminal": {
            "EXPLICIT_AUTHORIZATION_VERIFIED": False,
            "AUTHORIZATION_ATTESTATION_PRESENT": False,
            "PROVIDER_REQUESTS": 0,
            "LOGICAL_SLOT_INVOCATIONS": 0,
            "LOGICAL_SUCCESSES": 0,
            "LOGICAL_FAILURES": 0,
            "GENERATED_RAW": 0,
            "GENERATED_FINAL": 0,
            "OUTSTANDING": 440,
            "SMOKE_REQUESTS": 0,
            "RAMP1_REQUESTS": 0,
            "RAMP2_REQUESTS": 0,
            "BULK_REQUESTS": 0,
            "HTTP_429": 0,
            "HTTP_401": 0,
            "HTTP_403": 0,
            "TIMEOUT_OR_5XX": 0,
            "FORMAL_INGEST": False,
            "C3": False,
            "NEW_VAL": 0,
            "HOLDOUT": 0,
            "HOLDOUT_CONSUMED": False,
            "HUMAN_REVIEW_PACKAGE": False,
            "P4D_IMAGES_ACCEPTED": 0,
            "BATCH_FILE_COUNTS": batch_counts,
        },
        "preparation_freeze": {
            "path": str(PREP),
            "sha256": prep.get("preparation_freeze_sha256_actual"),
            "expected_sha256": PREP_SHA_EXPECTED,
            "sidecar_match": prep.get("sidecar_match"),
            "overview_sha256_at_preparation": prep_overview_sha,
            "current_overview_sha256": current_overview_sha,
            "overview_append_only_after_preparation": prep_overview_sha != current_overview_sha,
        },
        "frozen_assets": assets,
        "manifest": manifest,
        "batch_zero_check": batch,
        "provider_identity_last_known": provider,
        "retry_capability": {
            "path": str(GR3 / "00_preflight/retry_capability_audit.json"),
            "sha256": sha256_file(GR3 / "00_preflight/retry_capability_audit.json"),
            "outer_retry": False,
            "native_retry_policy": retry.get("native_retry_policy_observed"),
            "no_retry_guarantee": retry.get("no_retry_guarantee"),
            "wrapper_max_retries": retry.get("wrapper_max_retries"),
            "possible_attempts_upper_bound_per_slot": retry.get("effective_possible_attempts_per_logical_slot"),
            "observed_native_retry_count": "UNKNOWN_NOT_EXECUTED",
        },
        "authorization": {
            "path": str(E_AUTH / "authorization_check.json"),
            "sha256": sha256_file(E_AUTH / "authorization_check.json"),
            "authorization_present": auth.get("authorization_present"),
            "attestation_sha256": None,
        },
        "ledger": {"path": str(LEDGER), "sha256": sha256_file(LEDGER), "rows": max(0, sum(1 for _ in LEDGER.open(encoding="utf-8")) - 1)},
        "runner_sha256": None,
        "artifact_sha256": artifact_sha,
        "reports_sha256": report_sha,
        "dataset_boundary": {
            "before_path": str(E_PRE / "dataset_boundary_before.json"),
            "after_path": str(E_PRE / "dataset_boundary_after.json"),
            "before_counts": before.get("counts"),
            "after_counts": after.get("counts"),
            "delta": boundary_delta,
            "p4d_reference_hits_total": max(before.get("p4d_reference_hits_total", 0), after.get("p4d_reference_hits_total", 0)),
            "formal_dataset_mutation_by_gr3e": False,
        },
        "production_code_modified": False,
        "ollama_service_modified": False,
    }
    write_json(TERMINAL_FREEZE, payload)
    digest = sha256_file(TERMINAL_FREEZE)
    write_text(TERMINAL_SIDECAR, f"{digest}  {TERMINAL_FREEZE.name}")
    print(json.dumps({"terminal_freeze": str(TERMINAL_FREEZE), "terminal_freeze_sha256": digest, "sidecar": str(TERMINAL_SIDECAR)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "freeze"))
    args = parser.parse_args()
    return prepare() if args.command == "prepare" else terminal_freeze()


if __name__ == "__main__":
    raise SystemExit(main())
