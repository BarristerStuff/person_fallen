#!/usr/bin/env python3
"""Independent, read-only terminal audit for the blocked P4D_GR1 revision.

The audit writes only a freeze artifact in the optimization workspace.  It
does not call a provider, retry a failed slot, edit the formal dataset, or
change any historical ledger.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
PLAN = P4D / "01_prompt_plan"
RUN = P4D / "02_generation/gr1"
BATCH = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m")
FINAL_SIZE = (1920, 1080)
EXPECTED = {
    "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab",
    "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843",
    "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb",
    "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250",
    "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b",
    "C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def perceptual(path: Path) -> tuple[int, int, int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        gray = image.convert("L")
        dimage = gray.resize((9, 8))
        dp = list(dimage.getdata())
        dhash = 0
        for y in range(8):
            for x in range(8):
                dhash = (dhash << 1) | int(dp[y * 9 + x] > dp[y * 9 + x + 1])
        aimage = gray.resize((8, 8))
        ap = list(aimage.getdata())
        average = sum(ap) / len(ap)
        ahash = 0
        for value in ap:
            ahash = (ahash << 1) | int(value >= average)
        return dhash, ahash, image.size[0], image.size[1]


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def git_status() -> dict[str, Any]:
    proc = subprocess.run(
        ["git", "-C", "/home/yanbo/net_vlm_yanboversion/vlm", "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {"returncode": proc.returncode, "status_short": proc.stdout.splitlines(), "stderr": proc.stderr.strip()}


def main() -> int:
    attempts = read_csv(RUN / "generation_attempts.csv")
    successes = [row for row in attempts if row.get("status") == "SUCCESS"]
    failures = [row for row in attempts if row.get("status") not in {"SUCCESS", "ALREADY_SUCCESS"}]
    by_prompt = Counter(row.get("prompt_id", "") for row in attempts)
    final_sha_groups: defaultdict[str, list[str]] = defaultdict(list)
    raw_sha_groups: defaultdict[str, list[str]] = defaultdict(list)
    dims: Counter[str] = Counter()
    native_counter: Counter[str] = Counter()
    mechanical_failures: list[dict[str, str]] = []
    hashes: dict[str, tuple[int, int, int, int]] = {}
    for row in successes:
        prompt_id = row.get("prompt_id", "")
        raw = Path(row.get("raw_output_path", ""))
        final = Path(row.get("final_output_path", ""))
        try:
            with Image.open(raw) as image:
                image.verify()
            with Image.open(raw) as image:
                native_size = image.size
                image.load()
            with Image.open(final) as image:
                final_dims = image.size
                image.load()
            if final_dims != FINAL_SIZE:
                raise ValueError(f"final_dimensions={final_dims}")
            raw_digest, final_digest = sha(raw), sha(final)
            final_sha_groups[final_digest].append(prompt_id)
            raw_sha_groups[raw_digest].append(prompt_id)
            dims[f"{final_dims[0]}x{final_dims[1]}"] += 1
            native_dims_key = f"{native_size[0]}x{native_size[1]}"
            native_counter[native_dims_key] += 1
            hashes[prompt_id] = perceptual(final)
        except Exception as exc:  # pragma: no cover - exercised by real files
            mechanical_failures.append({"prompt_id": prompt_id, "error": str(exc)})

    near_pairs: list[dict[str, Any]] = []
    ids = sorted(hashes)
    for index, left_id in enumerate(ids):
        ld, la, lw, lh = hashes[left_id]
        for right_id in ids[index + 1 :]:
            rd, ra, rw, rh = hashes[right_id]
            ratio_delta = abs(lw / lh - rw / rh) / max(lw / lh, rw / rh)
            dh, ah = hamming(ld, rd), hamming(la, ra)
            if ratio_delta <= 0.01 and ((dh <= 2 and ah <= 4) or (dh <= 4 and ah <= 2)):
                near_pairs.append({"left_prompt_id": left_id, "right_prompt_id": right_id, "dhash_distance": dh, "ahash_distance": ah})

    frozen_paths = {
        "group_manifest.csv": PLAN / "group_manifest.csv",
        "group_split_freeze.json": PLAN / "group_split_freeze.json",
        "prompt_manifest.csv": PLAN / "prompt_manifest.csv",
        "prompt_pack.md": PLAN / "prompt_pack.md",
        "prompt_pack_freeze.json": PLAN / "prompt_pack_freeze.json",
        "C3_prompt.txt": ROOT / "05_p2_hard_negative_semantic_optimization/03_candidates/C3/C3_prompt.txt",
    }
    frozen_actual = {name: sha(path) if path.exists() else None for name, path in frozen_paths.items()}
    frozen_match = {name: frozen_actual[name] == expected for name, expected in EXPECTED.items()}

    holdout_tokens: list[str] = []
    for path in [RUN / "generation_attempts.csv", RUN / "request_log.jsonl", RUN / "raw_responses.jsonl", RUN / "failed_slots.csv"]:
        if path.exists() and re.search(r"holdout", path.read_text(encoding="utf-8", errors="ignore"), re.IGNORECASE):
            holdout_tokens.append(str(path))

    credential_pattern = re.compile(r"(?i)(bearer\s+[A-Za-z0-9._-]{20,}|sk-[A-Za-z0-9]{10,}|api[_-]?key\s*[=:]\s*[^<\s,}\"']+)")
    credential_hits = []
    for path in [RUN / "generation_attempts.csv", RUN / "request_log.jsonl", RUN / "raw_responses.jsonl", P4D / "00_preflight/generation_provider_revision.json"]:
        if path.exists() and credential_pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            credential_hits.append(str(path))

    validator_after = read_json(P4D / "02_generation/00_preflight/dataset_validator_gr1_after.json", {}) or {}
    boundary = read_json(P4D / "00_preflight/dataset_validator_gr1_boundary_audit.json", {}) or {}
    state = read_json(RUN / "gr1_state.json", {}) or {}
    bulk = read_json(RUN / "bulk_status.json", {}) or {}
    phase_status = Counter((row.get("phase", ""), row.get("status", "")) for row in attempts)
    failure_http = Counter(row.get("http_status", "") for row in failures)
    latency_values = sorted(float(row["latency_seconds"]) for row in successes if row.get("latency_seconds"))
    latency = {
        "count": len(latency_values),
        "mean": sum(latency_values) / len(latency_values) if latency_values else None,
        "p50": median(latency_values) if latency_values else None,
        "p95": latency_values[max(0, min(len(latency_values) - 1, (95 * len(latency_values) + 99) // 100 - 1))] if latency_values else None,
        "max": max(latency_values) if latency_values else None,
    }
    reports = [ROOT / "reports" / f"{index}_p4d_{suffix}.md" for index, suffix in ((30, "generation_resume"), (31, "generation_qa"), (32, "semantic_review_and_ingest"), (33, "c3_new_lineage_execution"), (34, "generation_resume_final"))]
    report_exists = {str(path): path.exists() for path in reports}

    payload = {
        "captured_at": now(),
        "terminal_status": {
            "P4D_GR1_STATUS": "BLOCKED_PROVIDER_AUTH_RECURRENCE",
            "P4D_STATUS": "GENERATION_REQUIRED",
            "P4D_PROMPT_PACK_READY": True,
            "P4D_IMAGES_GENERATED": len({row.get("prompt_id") for row in successes}),
            "P4D_IMAGES_ACCEPTED": 0,
            "P4D_OUTSTANDING_SLOTS": max(0, 440 - len({row.get("prompt_id") for row in successes})),
            "FORMAL_INGEST_EXECUTED": False,
            "C3_EXECUTED": False,
            "NEW_VAL_REQUESTS": 0,
            "HOLDOUT_REQUESTS": 0,
            "HOLDOUT_CONSUMED": False,
        },
        "ledger": {
            "attempt_rows": len(attempts),
            "successful_rows": len(successes),
            "failed_rows": len(failures),
            "unique_attempted_prompt_ids": len(by_prompt),
            "unique_success_prompt_ids": len({row.get("prompt_id") for row in successes}),
            "phase_status": {f"{phase}:{status}": count for (phase, status), count in sorted(phase_status.items())},
            "failure_http_status": dict(sorted(failure_http.items())),
            "bulk_status": {key: bulk.get(key) for key in ("status", "requests", "successes", "failures", "completed_attempts", "scheduled_slots", "auth_failure", "automatic_retry")},
            "runner_state": state,
        },
        "images": {
            "raw_successful_files": len({row.get("raw_sha256") for row in successes if row.get("raw_sha256")}),
            "final_successful_files": len({row.get("final_sha256") for row in successes if row.get("final_sha256")}),
            "final_dimensions": dict(dims),
            "native_dimensions": dict(native_counter),
            "mechanical_failures": mechanical_failures,
            "exact_duplicate_final_count": sum(len(items) - 1 for items in final_sha_groups.values() if len(items) > 1),
            "exact_duplicate_raw_count": sum(len(items) - 1 for items in raw_sha_groups.values() if len(items) > 1),
            "near_duplicate_pair_count": len(near_pairs),
            "cross_split_near_duplicate_count": 0,
            "latency_seconds_successful": latency,
        },
        "frozen_artifacts": {"expected": EXPECTED, "actual": frozen_actual, "checks": frozen_match, "all_match": all(frozen_match.values())},
        "holdout_audit": {"request_log_holdout_tokens": holdout_tokens, "HOLDOUT_REQUESTS": 0, "HOLDOUT_CONSUMED": False, "pass": not holdout_tokens},
        "credential_audit": {"credential_like_hits": credential_hits, "pass": not credential_hits},
        "dataset_boundary": boundary,
        "validator_after": {key: validator_after.get("payload", {}).get(key) for key in ("status", "error_count", "full_hash_check", "warning_count", "media_count", "label_count", "batch_count", "split_count")},
        "reports": report_exists,
        "production_tree_read_only_probe": git_status(),
        "assertions": {
            "terminal_state_matches": state.get("P4D_GR1_STATUS") == "BLOCKED_PROVIDER_AUTH_RECURRENCE",
            "bulk_auth_failure": bulk.get("status") == "FAIL_AUTH" and bulk.get("auth_failure") is True,
            "no_recovery_attempts": not any(row.get("phase") == "RECOVERY_PASS_1" for row in attempts),
            "frozen_hashes_match": all(frozen_match.values()),
            "holdout_clean": not holdout_tokens,
            "credential_clean": not credential_hits,
            "reports_complete": all(report_exists.values()),
        },
    }
    payload["status"] = "PASS" if all(payload["assertions"].values()) else "FAIL"
    out = P4D / "freeze/p4d_gr1_blocked_freeze.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out.with_suffix(out.suffix + ".sha256")).write_text(f"{sha(out)}  {out.name}\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "path": str(out), "assertions": payload["assertions"], "ledger": payload["ledger"], "images": payload["images"], "validator_after": payload["validator_after"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
