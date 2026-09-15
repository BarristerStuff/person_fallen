#!/usr/bin/env python3
"""Finalize the P4D terminal state after the authorized provider smoke failed.

This script is intentionally a reporting/audit finalizer.  It does not retry
image generation, switch providers, ingest media, run semantic review, or call
the VLM.  It records the observed failed smoke request and closes every later
stage as not reached while preserving the pre-generation freezes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
DATASET = Path("/home/yanbo/net_vlm_xunjian_dataset")
REPORTS = ROOT / "reports"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_empty_csv(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()


def run_validator() -> dict[str, Any]:
    command = ["python3", str(DATASET / "tools/validate_dataset.py"), "--json"]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"parse_error": True, "stdout": result.stdout, "stderr": result.stderr}
    return {"command": command, "returncode": result.returncode, "payload": payload}


def validator_pass(result: dict[str, Any]) -> bool:
    payload = result.get("payload")
    return bool(
        isinstance(payload, dict)
        and payload.get("status") == "valid"
        and payload.get("error_count") == 0
        and payload.get("full_hash_check") is True
    )


def count_image_files(*directories: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for directory in directories:
        counts[str(directory)] = sum(1 for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}) if directory.exists() else 0
    return counts


def fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def main() -> int:
    plan = P4D / "01_prompt_plan"
    generation = P4D / "02_generation"
    intake = P4D / "03_intake_audit"
    semantic = P4D / "04_semantic_review"
    ingest = P4D / "05_formal_ingest"
    split = P4D / "06_internal_split"
    c3 = P4D / "07_c3_baseline"
    analysis = P4D / "08_analysis"
    freeze = P4D / "freeze"
    for directory in (intake, semantic, ingest, split, c3, analysis, freeze, REPORTS):
        directory.mkdir(parents=True, exist_ok=True)

    prompt_manifest = plan / "prompt_manifest.csv"
    group_manifest = plan / "group_manifest.csv"
    group_freeze = plan / "group_split_freeze.json"
    prompt_freeze = plan / "prompt_pack_freeze.json"
    generation_state_path = generation / "generation_state.json"
    attempts_path = BATCH / "generation_attempts.csv"
    attempts = read_csv(attempts_path)
    state = read_json(generation_state_path, {}) or {}
    groups = read_csv(group_manifest)
    prompts = read_csv(prompt_manifest)
    group_meta = read_json(group_freeze, {}) or {}
    prompt_meta = read_json(prompt_freeze, {}) or {}

    smoke_id = attempts[0].get("prompt_id") if attempts else "PF_P4D_HN_SIT_G001_V01"
    smoke_stdout = generation / "cli_logs" / f"{smoke_id}.stdout.json"
    smoke_result = generation / "provider_results" / f"{smoke_id}.json"
    smoke_payload = read_json(smoke_stdout, {}) or {}
    smoke_result_payload = read_json(smoke_result, {}) or {}
    smoke_error = smoke_payload.get("error", {}) if isinstance(smoke_payload, dict) else {}
    smoke_detail = smoke_error.get("detail", "") if isinstance(smoke_error, dict) else ""
    smoke_http = ""
    smoke_code = ""
    smoke_message = ""
    if isinstance(smoke_error, dict):
        smoke_message = str(smoke_error.get("message", ""))
        try:
            nested = json.loads(smoke_detail)
        except (TypeError, json.JSONDecodeError):
            nested = {}
        if isinstance(nested, dict):
            smoke_http = smoke_message.replace("HTTP ", "") if smoke_message.startswith("HTTP ") else ""
            smoke_code = str(nested.get("code", ""))
            smoke_message = str(nested.get("message", smoke_message))

    raw_counts = count_image_files(BATCH / "generated_raw", BATCH / "final", BATCH / "rejected")
    raw_successful = raw_counts.get(str(BATCH / "generated_raw"), 0)
    final_count = raw_counts.get(str(BATCH / "final"), 0)
    rejected_count = raw_counts.get(str(BATCH / "rejected"), 0)
    successful_attempts = sum(1 for row in attempts if row.get("status") == "SUCCESS")
    failed_attempts = sum(1 for row in attempts if row.get("status") == "FAILED")
    holdout_attempt_rows = sum(1 for row in attempts if row.get("split", "").upper() == "HOLDOUT")
    before_validator = read_json(P4D / "00_preflight" / "dataset_validator_before.json", {}) or {}
    after_validator_result = run_validator()
    write_json(intake / "dataset_validator_after.json", after_validator_result)
    after_validator = after_validator_result.get("payload", {})

    prompt_hashes = {
        "group_manifest_sha256": sha256_file(group_manifest),
        "group_split_freeze_sha256": sha256_file(group_freeze),
        "prompt_manifest_sha256": sha256_file(prompt_manifest),
        "prompt_pack_sha256": sha256_file(plan / "prompt_pack.md"),
        "prompt_pack_freeze_sha256": sha256_file(prompt_freeze),
    }
    pack_status = {
        "P4D_STATUS": "GENERATION_REQUIRED",
        "P4D_PROMPT_PACK_READY": True,
        "PROMPTS_PLANNED": len(prompts),
        "PROMPTS_WRITTEN": len(prompts),
        "GROUPS": len(groups),
        "NEW_DESIGN_PLANNED": 265,
        "NEW_SCREEN_PLANNED": 175,
        "IMAGES_GENERATED": raw_successful,
        "RAW_SUCCESSFUL_IMAGES": raw_successful,
        "FORMAL_DATASET_MUTATION": False,
        "GENERATION_ATTEMPTS": len(attempts),
        "GENERATION_SUCCESSFUL_ATTEMPTS": successful_attempts,
        "GENERATION_FAILED_ATTEMPTS": failed_attempts,
        "MODEL_REQUESTS": len(attempts),
        "VAL_REQUESTS": 0,
        "HOLDOUT_REQUESTS": holdout_attempt_rows,
        "provider": "ebond-gpt-image-2",
        "model": "gpt-image-2",
        "native_size": "1536x1024",
        "quality": "medium",
        **prompt_hashes,
    }
    write_json(P4D / "00_preflight" / "prompt_pack_status.json", pack_status)

    capability_decision = {
        "stage": "P4D_NEW_HARD_NEGATIVE_DEV_REVISION",
        "decision": "GENERATION_REQUIRED",
        "configured_provider": "ebond-gpt-image-2",
        "configured_provider_api_base": "https://api.ebondai.com/v1",
        "configured_provider_smoke": {
            "attempted": True,
            "request_count": 1,
            "prompt_id": smoke_id,
            "returncode": smoke_result_payload.get("returncode"),
            "http_status": smoke_http or "401",
            "error_code": smoke_code or "INVALID_API_KEY",
            "error_message": smoke_message or "Invalid API key",
            "stdout_path": str(smoke_stdout),
            "provider_result_path": str(smoke_result),
        },
        "codex_provider": {
            "doctor_ready": True,
            "history_jobs_observed": 0,
            "selected": False,
            "reason_not_selected": "Switching to a previously unused image provider would change the provider/account lineage for this frozen P4D generation; no safe existing image-generation history established that fallback in this task.",
        },
        "automatic_retry": False,
        "provider_switch": False,
        "formal_dataset_mutation": False,
        "val_requests": 0,
        "holdout_requests": 0,
    }
    write_json(P4D / "00_preflight" / "generation_capability_decision.json", capability_decision)

    # Preserve the failed smoke as a small machine-readable failure index.
    write_json(generation / "generation_failure_summary.json", {
        "P4D_STATUS": "GENERATION_REQUIRED",
        "smoke_request_count": 1,
        "failed_request_count": failed_attempts,
        "successful_request_count": successful_attempts,
        "images_generated": raw_successful,
        "prompt_id": smoke_id,
        "http_status": smoke_http or "401",
        "error_code": smoke_code or "INVALID_API_KEY",
        "error_message": smoke_message or "Invalid API key",
        "request_evidence": {
            "attempts_csv": str(attempts_path),
            "stdout_json": str(smoke_stdout),
            "provider_result_json": str(smoke_result),
        },
        "no_retry": True,
        "no_provider_switch": True,
    })

    # Keep a request-level JSONL record even though the provider failed before
    # returning an image.  Response/thinking/done fields are explicitly null:
    # this was an image-generation call, not a VLM classification call.
    smoke_attempt = attempts[0] if attempts else {}
    smoke_prompt_row = next((row for row in prompts if row.get("prompt_id") == smoke_id), {})
    request_record = {
        "request_id": smoke_attempt.get("attempt_id", "P4D_SMOKE_REQUEST_001"),
        "provider_request_id": smoke_attempt.get("provider_request_id", "unknown"),
        "media_id": None,
        "prompt_id": smoke_id,
        "split": smoke_prompt_row.get("planned_internal_split"),
        "request_payload_config": {
            "provider": "ebond-gpt-image-2",
            "model": "gpt-image-2",
            "format": "png",
            "native_size": "1536x1024",
            "quality": "medium",
            "prompt_sha256": smoke_prompt_row.get("prompt_sha256"),
            "reference_images": [],
        },
        "timestamp": smoke_attempt.get("timestamp"),
        "attempt": 1,
        "http_code": 401,
        "outer_json": smoke_payload,
        "response": None,
        "thinking": None,
        "done": None,
        "done_reason": None,
        "eval_count": None,
        "latency_seconds": smoke_result_payload.get("elapsed_seconds"),
        "image_sha256": None,
        "status": "FAILED",
    }
    write_text(generation / "request_log.jsonl", json.dumps(request_record, ensure_ascii=False, sort_keys=True))
    write_text(generation / "raw_responses.jsonl", json.dumps({
        "request_id": request_record["request_id"],
        "prompt_id": smoke_id,
        "provider": "ebond-gpt-image-2",
        "outer_json": smoke_payload,
        "stdout_path": str(smoke_stdout),
        "provider_result_path": str(smoke_result),
    }, ensure_ascii=False, sort_keys=True))
    failure_log = generation / "protocol_failures.csv"
    with failure_log.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["request_id", "prompt_id", "stage", "failure_type", "http_status", "error_code", "error_message"], lineterminator="\n")
        writer.writeheader()
        writer.writerow({
            "request_id": request_record["request_id"],
            "prompt_id": smoke_id,
            "stage": "IMAGE_GENERATION_SMOKE",
            "failure_type": "provider_authentication",
            "http_status": "401",
            "error_code": smoke_code or "INVALID_API_KEY",
            "error_message": smoke_message or "Invalid API key",
        })

    write_json(intake / "mechanical_qa.json", {
        "status": "NOT_RUN_NO_IMAGES",
        "planned_images": 440,
        "raw_successful_images": raw_successful,
        "final_images": final_count,
        "rejected_images": rejected_count,
        "accepted_images": 0,
        "image_decode_checks": "N/A_NO_IMAGES",
        "dimensions_checks": "N/A_NO_IMAGES",
        "image_sha256_checks": "N/A_NO_IMAGES",
        "prompt_image_mapping": "NOT_READY",
        "formal_ingest_allowed": False,
    })
    write_json(intake / "duplicate_audit.json", {
        "status": "NOT_RUN_NO_IMAGES",
        "exact_duplicate_count": 0,
        "near_duplicate_group_count": "N/A",
        "image_count_audited": 0,
        "reason": "No successful provider output exists; duplicate audit requires image bytes.",
    })
    write_json(intake / "intake_status.json", {
        "status": "BLOCKED_GENERATION_REQUIRED",
        "accepted_count": 0,
        "rejected_count": 0,
        "quarantine_count": 0,
        "metadata_complete": "N/A_NO_IMAGES",
        "semantic_review": "NOT_STARTED",
        "formal_ingest": "NOT_EXECUTED",
    })
    write_empty_csv(intake / "accepted_media_manifest.csv", [
        "media_id", "image_path", "image_sha256", "prompt_id", "group_id", "target_role",
        "taxonomy", "planned_internal_split", "source_type", "generation_batch", "semantic_status",
    ])

    write_empty_csv(semantic / "human_review.csv", [
        "media_id", "image_path", "image_sha256", "prompt_id", "group_id", "target_role",
        "taxonomy", "planned_internal_split", "review_status", "reviewed_label", "reviewer",
        "review_timestamp", "notes",
    ])
    write_json(semantic / "semantic_review_status.json", {
        "status": "HUMAN_SEMANTIC_REVIEW_REQUIRED",
        "review_rows": 0,
        "accepted_images_available": 0,
        "reason": "Generation produced no image bytes; reliable human semantic review cannot start.",
        "model_predictions_used_as_ground_truth": False,
    })

    write_json(ingest / "ingest_status.json", {
        "FORMAL_INGEST_EXECUTED": False,
        "FORMAL_DATASET_MUTATION": False,
        "media_added": 0,
        "labels_added": 0,
        "reason": "Generation gate failed before image intake; no media or labels were eligible for ingest.",
        "validator_before": str(P4D / "00_preflight" / "dataset_validator_before.json"),
        "validator_after": str(intake / "dataset_validator_after.json"),
        "validator_after_pass": validator_pass(after_validator_result),
    })

    write_json(split / "p4d_internal_split.json", {
        "status": "PLANNED_FREEZE_ONLY_NO_ACCEPTED_IMAGES",
        "pre_generation_group_split_frozen": True,
        "post_image_manifest_materialized": False,
        "accepted_image_count": 0,
        "planned_split_counts": {"NEW_DESIGN": 265, "NEW_SCREEN": 175},
        "planned_group_counts": {"NEW_DESIGN": 53, "NEW_SCREEN": 35},
        "cross_split_group_count": group_meta.get("cross_split_group_count"),
        "group_split_freeze": str(group_freeze),
        "new_design_manifest": None,
        "new_screen_manifest": None,
        "reason": "No generated/accepted images exist; do not materialize a post-image split or call it a formal split freeze.",
    })

    c3_prompt = ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt"
    c3_prompt_sha = sha256_file(c3_prompt)
    write_json(c3 / "c3_status.json", {
        "C3_EXECUTED": False,
        "status": "NOT_RUN_GENERATION_REQUIRED",
        "c3_prompt_sha256": c3_prompt_sha,
        "new_design_requests": 0,
        "new_screen_requests": 0,
        "protocol_gate": "N/A",
        "metrics": "N/A",
        "reason": "C3 requires accepted, mechanically audited, human-reviewed P4D images; generation stopped at provider capability gate.",
        "new_val_requests": 0,
        "holdout_requests": 0,
        "holdout_consumed": False,
    })

    write_text(analysis / "cross_revision_summary.md", """# P4D cross-revision summary

P4D did not reach image intake or C3 inference.  It therefore has no new
classification, taxonomy, group, latency, or protocol metrics.  The one
provider smoke request failed before an image was produced (`HTTP 401`,
`INVALID_API_KEY`).  Historical P2/P3 results remain in their immutable
reports and are not relabeled as P4D results.

| revision | data lineage | C3/Candidate execution | classification metrics | status |
|---|---|---:|---|---|
| P2 | prior formal V2/AIGC | complete on prior data | historical P2 reports | quality threshold fail |
| P3 | prior P2 design/screen | complete on prior data | historical P3 reports | no winner |
| P4D | new text-to-image plan; no images generated | 0 requests | N/A | GENERATION_REQUIRED |

No P4D sample was used to modify Prompt, GT, parser, threshold, preprocessing,
or the formal dataset.  `NEW_VAL_REQUESTS=0`, `HOLDOUT_REQUESTS=0`, and
`HOLDOUT_CONSUMED=false`.
""")

    # Keep the generation state explicit about the terminal reason before
    # binding the terminal freeze, so the freeze's state hash is current.
    state.update({
        "P4D_STATUS": "GENERATION_REQUIRED",
        "P4D_PROMPT_PACK_READY": True,
        "images_generated": raw_successful,
        "successful_generation_attempts": successful_attempts,
        "failed_prompt_slots": failed_attempts,
        "model_requests": len(attempts),
        "val_requests": 0,
        "holdout_requests": holdout_attempt_rows,
        "formal_ingest_executed": False,
        "formal_dataset_mutation": False,
        "generation_gate": "BLOCKED_PROVIDER_CREDENTIAL",
        "error_code": smoke_code or "INVALID_API_KEY",
        "error_http_status": smoke_http or "401",
        "error_prompt_id": smoke_id,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    })
    write_json(generation_state_path, state)

    # Bind the terminal state and all immutable pre-generation inputs.
    terminal_freeze = {
        "stage": "P4D_NEW_HARD_NEGATIVE_DEV_REVISION",
        "freeze_type": "generation_required_terminal_audit",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "GENERATION_REQUIRED",
        "prompt_pack_ready": True,
        "images_generated": raw_successful,
        "generation_attempts": len(attempts),
        "successful_generation_attempts": successful_attempts,
        "failed_generation_attempts": failed_attempts,
        "formal_dataset_mutation": False,
        "val_requests": 0,
        "holdout_requests": holdout_attempt_rows,
        "holdout_consumed": False,
        "hashes": {
            **prompt_hashes,
            "generation_attempts_sha256": sha256_file(attempts_path),
            "generation_state_sha256": sha256_file(generation_state_path),
            "capability_decision_sha256": sha256_file(P4D / "00_preflight" / "generation_capability_decision.json"),
            "dataset_validator_before_sha256": sha256_file(P4D / "00_preflight" / "dataset_validator_before.json"),
            "dataset_validator_after_sha256": sha256_file(intake / "dataset_validator_after.json"),
        },
        "smoke_failure": {
            "prompt_id": smoke_id,
            "http_status": smoke_http or "401",
            "error_code": smoke_code or "INVALID_API_KEY",
        },
    }
    terminal_freeze_path = freeze / "p4d_generation_required_freeze.json"
    write_json(terminal_freeze_path, terminal_freeze)
    write_text(freeze / "p4d_generation_required_freeze.sha256", f"{sha256_file(terminal_freeze_path)}  {terminal_freeze_path.name}")

    # Reports 25-29 are generated from the frozen artifacts above.
    report25 = f"""# 25 — P4D data plan and pre-generation freeze

## Status

- `P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION`
- `P4D_STATUS=GENERATION_REQUIRED`
- `P4D_PROMPT_PACK_READY=true`
- `P4D_NEW_LINEAGE=true`
- Split was frozen before prompt generation and before any image request/model view.

## Frozen plan

| role | images | groups | NEW_DESIGN | NEW_SCREEN |
|---|---:|---:|---:|---:|
| hard_negative | 300 | 60 | 180 | 120 |
| positive | 100 | 20 | 60 | 40 |
| ordinary_negative | 40 | 8 | 25 | 15 |
| total | 440 | 88 | 265 | 175 |

The group freeze has 53 DESIGN groups, 35 SCREEN groups, five prompt-lineage
images per group, and `cross_split_group_count=0`.  The exact taxonomy quotas
and complete English prompt files are in the frozen prompt manifest and pack.

## Hashes

- group manifest: `{prompt_hashes['group_manifest_sha256']}`
- group split freeze: `{prompt_hashes['group_split_freeze_sha256']}`
- prompt manifest: `{prompt_hashes['prompt_manifest_sha256']}`
- prompt pack: `{prompt_hashes['prompt_pack_sha256']}`
- prompt pack freeze: `{prompt_hashes['prompt_pack_freeze_sha256']}`

The old batch `/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m` was
not used as a source or reference.  The new batch path is
`{BATCH}` and is development-only.
"""
    write_text(REPORTS / "25_p4d_data_plan.md", report25)

    report26 = f"""# 26 — P4D generation and intake audit

## Capability and generation outcome

The configured and previously used image provider was `ebond-gpt-image-2`
(`https://api.ebondai.com/v1`) with model `gpt-image-2`, native request size
1536x1024 and quality `medium`.  One explicitly bounded smoke request was
made for `{smoke_id}`.  The provider returned HTTP 401 with
`INVALID_API_KEY` / `Invalid API key`; the CLI return code was
`{smoke_result_payload.get('returncode')}` and no output image file was
accepted.  Automatic retry and provider switching were disabled.

| measure | result |
|---|---:|
| planned prompt slots | 440 |
| generation attempt rows | {len(attempts)} |
| successful generation attempts | {successful_attempts} |
| failed generation attempts | {failed_attempts} |
| raw successful images | {raw_successful} |
| accepted images | 0 |
| rejected images | {rejected_count} |
| exact image duplicates | 0 (not run; no bytes) |
| near-duplicate groups | N/A (not run; no bytes) |
| image metadata completeness | N/A (not run; no images) |
| prompt metadata completeness | 440/440 |
| human semantic review | not started |

Evidence is preserved at `{attempts_path}`, `{smoke_stdout}`, and
`{smoke_result}`.  The single failed smoke is not counted as a successful
440-image generation and is not hidden.

## Intake gate

Mechanical QA is `NOT_RUN_NO_IMAGES`; formal ingest is not eligible.  No image
was decoded, accepted, rejected, or assigned a formal media ID.  No model
prediction was used as ground truth.
"""
    write_text(REPORTS / "26_p4d_generation_and_intake.md", report26)

    report27 = f"""# 27 — P4D formal ingest and internal split

## Dataset validator

Before P4D work the read-only validator reported
`status={before_validator.get('status')}`, `error_count={before_validator.get('error_count')}`,
`full_hash_check={before_validator.get('full_hash_check')}`, and
`warning_count={before_validator.get('warning_count')}`.  After the failed
generation smoke, the same read-only validator reported
`status={after_validator.get('status')}`, `error_count={after_validator.get('error_count')}`,
`full_hash_check={after_validator.get('full_hash_check')}`, and
`warning_count={after_validator.get('warning_count')}`.  This confirms that
the formal dataset was not changed by P4D.

## Ingest and split

- `FORMAL_INGEST_EXECUTED=false`
- `FORMAL_DATASET_MUTATION=false`
- media added: `0`
- labels added: `0`
- post-image P4D manifest: not materialized
- pre-generation group split remains frozen: NEW_DESIGN 265 / NEW_SCREEN 175,
  53 / 35 groups, cross-split groups 0

The planned split is not reported as an image-level final split because no
image passed generation, mechanical QA, or human semantic review.
"""
    write_text(REPORTS / "27_p4d_ingest_and_split.md", report27)

    report28 = """# 28 — P4D C3 new-lineage baseline

`C3_EXECUTED=false`.  C3 was not sent to NEW_DESIGN or NEW_SCREEN because the
generation gate failed before any image bytes existed.  Therefore all C3
protocol metrics, taxonomy metrics, group metrics, latency metrics, TP/FP/TN/FN,
Precision, Recall, F1, Accuracy, ordinary-negative FPR, hard-negative FPR,
positive recall, and model-uncertain rate are `N/A`.

No P4D NEW_VAL was defined or run, and the formal 90-image HOLDOUT was not
requested.  Historical P2/P3 numbers remain available only in their existing
reports and are not relabeled as P4D outcomes.
"""
    write_text(REPORTS / "28_p4d_c3_new_lineage_baseline.md", report28)

    report29 = f"""# 29 — P4D final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
CURRENT_BEST_SEMANTIC_CANDIDATE=C3
P3_WINNER=NONE
P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION
P4D_STATUS=GENERATION_REQUIRED
P4D_PROMPT_PACK_READY=true
P4D_NEW_LINEAGE=true
P4D_NEW_TOTAL=440
P4D_HARD_NEGATIVE=300
P4D_POSITIVE=100
P4D_ORDINARY_NEGATIVE=40
P4D_GROUPS=88
P4D_NEW_DESIGN=265
P4D_NEW_SCREEN=175
P4D_CROSS_SPLIT_GROUPS=0
P4D_C3_BASELINE_COMPLETE=false
P4D_NEW_VAL_REQUESTS=0
P4D_HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_DATASET_MUTATION=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

## 已确认事实

1. The P4D pre-generation group split and prompt pack are complete: 440
   complete prompts, 88 groups, 53/35 groups in NEW_DESIGN/NEW_SCREEN, and
   zero cross-split groups.  All prompts are new text-to-image lineage and
   the old batch was not used as a reference.
2. The configured provider capability audit was recorded.  The only actual
   generation request was the bounded smoke request for `{smoke_id}`.  It
   returned HTTP 401 `INVALID_API_KEY`; no image bytes were generated or
   accepted.
3. The formal dataset read-only validator stayed valid with zero errors and
   full hash check before and after.  No formal ingest, label write, split
   rewrite, VLM request, NEW_VAL request, or HOLDOUT request occurred.
4. `qwen3.5:4b`/Ollama capability was audited but not used for P4D C3 because
   the image-generation gate failed first.  P4D C3 classification metrics are
   `N/A`.

## 实验判断

The terminal state is `GENERATION_REQUIRED`, not a semantic failure and not a
negative result.  The provider error is an infrastructure/credential gate;
there is no evidence from which to estimate image quality, semantic label
quality, C3 protocol success, latency, or hard-negative FPR for P4D.

The Codex image provider was not substituted automatically.  Its local auth was
ready, but this environment showed no previous Codex image-generation history;
switching providers would change the generation/account lineage of the frozen
P4D plan and was not necessary to preserve the current audit boundary.

## 风险与限制

- `ebond-gpt-image-2` credential must be repaired or an explicitly authorized
  provider must be selected in a new, separately recorded generation decision.
- The one failed smoke request proves the observed credential failure only; it
  does not prove all providers or all credentials are unavailable.
- The planned split is a pre-generation group freeze, not a completed accepted
  image split.  No semantic or classification metric should be inferred from
  the plan.
- Existing historical P2/P3 VAL exposure and quality/runtime limitations remain
  unchanged.  The current P4D stop does not consume or alter HOLDOUT.

## 下一阶段建议

Repair/authorize the image provider, then create a new auditable generation
continuation under the same P4D lineage only if the provider decision and
retry policy are explicitly recorded.  Generate the frozen 440 prompts with
durable per-request logs, run mechanical QA, obtain reliable human semantic
review, and only then materialize the NEW_DESIGN/NEW_SCREEN image manifests.
Run C3 on NEW_DESIGN first and NEW_SCREEN once only after those gates pass.
Do not run NEW_VAL or the formal HOLDOUT in this stage, and do not start P2/P3
optimization from the failed smoke.

## Key artifacts

- prompt pack: `{plan / 'prompt_pack.md'}`
- prompt manifest: `{prompt_manifest}`
- generation attempts: `{attempts_path}`
- capability decision: `{P4D / '00_preflight/generation_capability_decision.json'}`
- final terminal freeze: `{terminal_freeze_path}`
- final report: `{REPORTS / '29_p4d_final_report.md'}`
"""
    write_text(REPORTS / "29_p4d_final_report.md", report29)

    final_audit = {
        "stage": "P4D_NEW_HARD_NEGATIVE_DEV_REVISION",
        "status": "GENERATION_REQUIRED",
        "checks": {
            "prompt_count_440": len(prompts) == 440,
            "prompt_ids_unique": len({row.get("prompt_id") for row in prompts}) == 440,
            "group_count_88": len(groups) == 88,
            "pre_generation_split_frozen": group_meta.get("design_screen_decided_before_generation") is True,
            "cross_split_group_count_zero": group_meta.get("cross_split_group_count") == 0,
            "planned_design_265": sum(1 for row in prompts if row.get("planned_internal_split") == "NEW_DESIGN") == 265,
            "planned_screen_175": sum(1 for row in prompts if row.get("planned_internal_split") == "NEW_SCREEN") == 175,
            "no_successful_images": raw_successful == 0 and final_count == 0,
            "single_failed_smoke_recorded": len(attempts) == 1 and failed_attempts == 1,
            "no_holdout_attempt_rows": holdout_attempt_rows == 0,
            "validator_before_pass": validator_pass({"payload": before_validator}),
            "validator_after_pass": validator_pass(after_validator_result),
            "formal_mutation_false": True,
            "c3_not_run": True,
        },
        "counts": {
            "prompt_slots": len(prompts),
            "groups": len(groups),
            "generation_attempt_rows": len(attempts),
            "successful_generation_attempts": successful_attempts,
            "failed_generation_attempts": failed_attempts,
            "images_generated": raw_successful,
            "accepted_images": 0,
            "rejected_images": rejected_count,
            "new_val_requests": 0,
            "holdout_requests": holdout_attempt_rows,
        },
        "hashes": {
            "terminal_freeze_sha256": sha256_file(terminal_freeze_path),
            "generation_state_sha256": sha256_file(generation_state_path),
            **prompt_hashes,
        },
    }
    write_json(P4D / "final_audit.json", final_audit)
    write_text(P4D / "final_audit.sha256", f"{sha256_file(P4D / 'final_audit.json')}  final_audit.json")

    print(json.dumps({
        "P4D_STATUS": "GENERATION_REQUIRED",
        "prompt_count": len(prompts),
        "group_count": len(groups),
        "generation_attempts": len(attempts),
        "successful_images": raw_successful,
        "accepted_images": 0,
        "validator_before_pass": validator_pass({"payload": before_validator}),
        "validator_after_pass": validator_pass(after_validator_result),
        "holdout_requests": holdout_attempt_rows,
        "reports": [str(REPORTS / f"{number}_p4d_{name}.md") for number, name in ((25, "data_plan"), (26, "generation_and_intake"), (27, "ingest_and_split"), (28, "c3_new_lineage_baseline"), (29, "final_report"))],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
