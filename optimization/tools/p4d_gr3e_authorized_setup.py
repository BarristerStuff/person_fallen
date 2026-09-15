#!/usr/bin/env python3
"""Authorize and re-preflight the P4D_GR3E continuation revision.

The earlier GR3E no-authorization terminal freeze is immutable.  This helper
creates a separate authorized continuation surface beneath
``06_execution/authorized_20260827_01`` and performs no image generation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation" / "gr3_fullregen"
PREP = GR3 / "freeze" / "p4d_gr3_preparation_freeze.json"
PREP_SIDECAR = PREP.with_name(PREP.name + ".sha256")
PREV_EXEC = GR3 / "06_execution"
PREV_TF = PREV_EXEC / "freeze" / "p4d_gr3e_terminal_freeze.json"
PREV_TF_SIDECAR = PREV_TF.with_name(PREV_TF.name + ".sha256")
CONT = PREV_EXEC / "authorized_20260827_01"
PRE = CONT / "00_preflight"
AUTH = CONT / "01_authorization"
RUNNER_DIR = CONT / "02_runner"
LEDGER_DIR = CONT / "03_ledger"
RAW_LOG_DIR = CONT / "04_raw_responses"
CHECKPOINT_DIR = CONT / "05_checkpoints"
QA_DIR = CONT / "06_full_qa"
REVIEW_DIR = CONT / "07_human_review_package"
FREEZE_DIR = CONT / "freeze"

CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
PREP_CAPABILITY = GR3 / "00_preflight" / "provider_capability.json"
PREP_RETRY = GR3 / "00_preflight" / "retry_capability_audit.json"
MANIFEST = GR3 / "03_fullregen_plan" / "full_regen_prompt_manifest.csv"
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m")
DATASET_VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")

PREP_SHA = "a637a289b1a657a33fe777b97f5f769815b307c5404a47d48f9f2644123c415f"
PREV_TF_SHA = "8ff93df4e33d670ab626fc0584d0cf27f0e5bbddd0d216dbdd821adbfd11ade1"
WRAPPER_SHA = "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe"
BINARY_SHA = "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba"
RETRY_SHA = "ba0de95b8f5939b5479d293128081d6e00d1bc5b82bb7a2f00d62045e1894619"
MANIFEST_SHA = "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"

# This is the exact standalone authorization received in the current user
# message.  It is deliberately distinct from the embedded example in the
# earlier task specification.
AUTH_TEXT = (
    "我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，"
    "接受旧 GR1 192 张不进入新 revision；我同时明确接受当前 GPT Image 2 runtime max_retries=3、"
    "单个逻辑 slot 最多约 4 次 provider attempt、精确费用未知以及由此产生的 quota/成本风险。"
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
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


def sanitize(text: str) -> str:
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,}\"']+", r"\1<REDACTED>", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{20,}", r"\1<REDACTED>", text)
    return text


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"parse_error": True, "raw_stdout": sanitize(text)}


def require_parent_freezes() -> dict[str, Any]:
    actual_prep = sha256_file(PREP)
    sidecar = PREP_SIDECAR.read_text(encoding="utf-8").split()[0] if PREP_SIDECAR.exists() else None
    actual_prev = sha256_file(PREV_TF)
    prev_sidecar = PREV_TF_SIDECAR.read_text(encoding="utf-8").split()[0] if PREV_TF_SIDECAR.exists() else None
    prep = read_json(PREP, {}) or {}
    prev = read_json(PREV_TF, {}) or {}
    if actual_prep != PREP_SHA or sidecar != actual_prep:
        raise RuntimeError("P4D_GR3 preparation freeze mismatch")
    if actual_prev != PREV_TF_SHA or prev_sidecar != actual_prev:
        raise RuntimeError("previous GR3E no-authorization terminal freeze mismatch")
    if prev.get("status") != "AWAITING_EXPLICIT_USER_AUTHORIZATION" or prev.get("terminal", {}).get("PROVIDER_REQUESTS") != 0:
        raise RuntimeError("previous GR3E freeze is not the expected zero-request authorization stop")
    if prep.get("terminal", {}).get("FULL_REGEN_AUTHORIZED") is not False:
        raise RuntimeError("preparation authorization packet changed unexpectedly")
    return {
        "preparation_freeze_sha256": actual_prep,
        "preparation_sidecar_match": sidecar == actual_prep,
        "previous_terminal_freeze_sha256": actual_prev,
        "previous_terminal_sidecar_match": prev_sidecar == actual_prev,
        "previous_terminal_status": prev.get("status"),
        "previous_provider_requests": prev.get("terminal", {}).get("PROVIDER_REQUESTS"),
        "verified_at": now(),
    }


def zero_batch_check() -> dict[str, Any]:
    suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    images = [str(p) for p in BATCH.rglob("*") if p.is_file() and p.suffix.lower() in suffixes] if BATCH.exists() else []
    links = [str(p) for p in BATCH.rglob("*") if p.is_symlink()] if BATCH.exists() else []
    value = {"batch": str(BATCH), "image_count": len(images), "symlink_count": len(links), "images": images[:20], "symlinks": links[:20], "pass": BATCH.exists() and not images and not links, "verified_at": now()}
    write_json(PRE / "new_batch_zero_check.json", value)
    if not value["pass"]:
        raise RuntimeError("new GR3 batch is not empty")
    return value


def authorization_attestation(parent: dict[str, Any]) -> dict[str, Any]:
    AUTH.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(AUTH_TEXT.encode("utf-8")).hexdigest()
    value = {
        "stage": "P4D_GR3E_FULL_REGEN_EXECUTION",
        "continuation_revision": "authorized_20260827_01",
        "authorization_present": True,
        "authorization_scope": "440_full_regeneration",
        "source": "standalone_current_user_message",
        "authorization_text": AUTH_TEXT,
        "authorization_text_sha256": digest,
        "authorization_timestamp": now(),
        "current_codex_profile_explicit": True,
        "slots_440_explicit": True,
        "GR1_images_excluded": True,
        "retry_risk_accepted": True,
        "quota_risk_accepted": True,
        "unknown_cost_risk_accepted": True,
        "outer_retry": False,
        "historical_no_auth_terminal_freeze": parent,
        "verified_at": now(),
    }
    path = AUTH / "full_regen_authorization_attestation.json"
    write_json(path, value)
    value["path"] = str(path)
    value["sha256"] = sha256_file(path)
    write_json(AUTH / "attestation_check.json", value)
    return value


def dataset_snapshot(label: str) -> dict[str, Any]:
    command = ["python3", str(DATASET_VALIDATOR), "--json"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)
    payload = parse_json(proc.stdout)
    counts: dict[str, int] = {}
    hashes: dict[str, str | None] = {}
    hits: dict[str, list[int]] = {}
    for name in ("media.csv", "labels.csv", "batches.csv", "splits.csv"):
        path = ANNOTATIONS / name
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        counts[name] = max(0, len(lines) - 1)
        hashes[name] = sha256_file(path)
        hits[name] = [index for index, line in enumerate(lines, start=1) if "p4d" in line.lower() or "person-fallen-v2-p4d" in line.lower()][:50]
    value = {
        "label": label,
        "captured_at": now(),
        "validator_command": command,
        "validator_returncode": proc.returncode,
        "validator": payload,
        "counts": {"media_count": counts["media.csv"], "label_count": counts["labels.csv"], "batch_count": counts["batches.csv"], "split_count": counts["splits.csv"]},
        "annotation_sha256": hashes,
        "p4d_reference_hits_by_active_csv": {name: rows for name, rows in hits.items()},
        "p4d_reference_hits_total": sum(len(rows) for rows in hits.values()),
        "formal_dataset_mutation_by_gr3e": False,
    }
    write_json(PRE / f"dataset_boundary_{label}.json", value)
    return value


def run_cli(label: str, args: list[str], timeout: int = 120) -> dict[str, Any]:
    # Pin the provider explicitly; config's default is intentionally unrelated
    # (ebond-gpt-image-2) and must never silently select the execution backend.
    command = ["node", str(CLI), "--json", "--provider", "codex", *args]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    stdout = sanitize(proc.stdout)
    stderr = sanitize(proc.stderr)
    value = {"label": label, "command": command, "returncode": proc.returncode, "stdout": stdout, "stderr": stderr, "payload": parse_json(stdout), "captured_at": now()}
    write_json(PRE / f"{label}.json", value)
    return value


def provider_preflight() -> dict[str, Any]:
    parent = require_parent_freezes()
    capability_before = read_json(PREP_CAPABILITY, {}) or {}
    retry_before = read_json(PREP_RETRY, {}) or {}
    commands = {
        "config_inspect": run_cli("config_inspect", ["config", "inspect"]),
        "doctor": run_cli("doctor", ["doctor"]),
        "auth_inspect": run_cli("auth_inspect", ["auth", "inspect"]),
        "images_generate_help": run_cli("images_generate_help", ["images", "generate", "--help"]),
    }
    wrapper_actual = sha256_file(CLI)
    binary_path = Path(str((read_json(GR3 / "00_preflight/retry_capability_audit.json", {}) or {}).get("binary_path", "/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")))
    binary_actual = sha256_file(binary_path)
    version_proc = subprocess.run([str(binary_path), "--version"], capture_output=True, text=True, check=False, timeout=30) if binary_path.exists() else None
    version_probe = {"returncode": version_proc.returncode, "stdout": sanitize(version_proc.stdout), "stderr": sanitize(version_proc.stderr)} if version_proc else {"returncode": None, "stdout": "", "stderr": "binary_missing"}
    # `binary --version` is not a supported command in this runtime and
    # returns an invalid_command envelope whose message contains the version.
    doctor_payload = commands["doctor"].get("payload") or {}
    auth_payload = commands["auth_inspect"].get("payload") or {}
    config_payload = commands["config_inspect"].get("payload") or {}
    # The authoritative runtime version is the successful doctor payload.
    version = {"doctor_version": doctor_payload.get("version"), "binary_probe": version_probe}
    # The CLI has changed envelope shapes over time.  Keep full redacted
    # payloads and derive readiness with conservative recursive lookup.
    def find(value: Any, keys: set[str]) -> list[Any]:
        result: list[Any] = []
        if isinstance(value, dict):
            for key, child in value.items():
                if key in keys:
                    result.append(child)
                result.extend(find(child, keys))
        elif isinstance(value, list):
            for child in value:
                result.extend(find(child, keys))
        return result

    provider_names = find(doctor_payload, {"provider"}) + find(auth_payload, {"provider"})
    codex_doctor = ((doctor_payload.get("providers") or {}).get("codex") or {}) if isinstance(doctor_payload, dict) else {}
    codex_auth = codex_doctor.get("auth") if isinstance(codex_doctor, dict) else {}
    codex_endpoint = codex_doctor.get("endpoint") if isinstance(codex_doctor, dict) else {}
    codex_auth = codex_auth if isinstance(codex_auth, dict) else {}
    codex_endpoint = codex_endpoint if isinstance(codex_endpoint, dict) else {}
    auth_payload_codex = ((auth_payload.get("providers") or {}).get("codex") or {}) if isinstance(auth_payload, dict) else {}
    auth_payload_codex = auth_payload_codex if isinstance(auth_payload_codex, dict) else {}
    # Preparation uses SHA256("account=<id>|user=<id>") as its safe profile
    # fingerprint.  Recompute the same non-secret identity from current doctor
    # output; never persist access/refresh tokens.
    account = str(codex_auth.get("account_id") or auth_payload_codex.get("account_id") or "")
    user = str(codex_auth.get("chatgpt_user_id") or auth_payload_codex.get("chatgpt_user_id") or "")
    current_profile = hashlib.sha256(f"account={account}|user={user}".encode("utf-8")).hexdigest() if account or user else None
    ready_values = [codex_auth.get("ready"), auth_payload_codex.get("ready")]
    session_values = [bool(codex_auth.get("ready")) and bool(codex_endpoint.get("reachable")) and bool(codex_endpoint.get("tls_ok"))]
    endpoint_values = [codex_endpoint.get("reachable")]
    ready_values = [item for item in ready_values if isinstance(item, bool)]
    session_values = [item for item in session_values if isinstance(item, bool)]
    endpoint_values = [item for item in endpoint_values if isinstance(item, bool)]
    prep_profile = ((capability_before.get("auth") or {}).get("profile_fingerprint_sha256"))
    provider_text = json.dumps({"doctor": doctor_payload, "auth": auth_payload, "config": config_payload}, ensure_ascii=False).lower()
    no_retry_supported = any(token in provider_text for token in ("no-retry", "max_retries=0", "max-retries=0", "retry=false"))
    value = {
        "stage": "P4D_GR3E_AUTHORIZED_RUNTIME_REPREFLIGHT",
        "continuation_revision": "authorized_20260827_01",
        "parent_freezes": parent,
        "commands": commands,
        "runtime_version": version,
        "provider": "codex",
        "request_model": "gpt-5.4",
        "generation_backend": "image_generation",
        "current_provider_names_observed": provider_names,
        "auth_ready_observed_values": ready_values,
        "session_ready_observed_values": session_values,
        "endpoint_reachable_observed_values": endpoint_values,
        "auth_ready": any(ready_values),
        "session_ready": any(session_values),
        "endpoint_reachable": any(endpoint_values),
        "safe_profile_fingerprint_current": current_profile,
        "safe_profile_fingerprint_preparation": prep_profile,
        "profile_continuity_match": current_profile == prep_profile if current_profile is not None else False,
        "wrapper_path": str(CLI),
        "wrapper_sha256_actual": wrapper_actual,
        "wrapper_sha256_preparation": WRAPPER_SHA,
        "binary_path": str(binary_path),
        "binary_sha256_actual": binary_actual,
        "binary_sha256_preparation": BINARY_SHA,
        "runtime_version_preparation": capability_before.get("runtime_version"),
        "retry_audit_sha256_preparation": sha256_file(PREP_RETRY),
        "retry_audit_sha256_expected": RETRY_SHA,
        "native_retry_policy_preparation": retry_before.get("native_retry_policy_observed"),
        "no_retry_supported_current": no_retry_supported,
        "no_retry_guarantee": no_retry_supported,
        "native_retry_risk_explicitly_accepted": True,
        "outer_retry": False,
        "verified_at": now(),
    }
    value["provider_ready_gate"] = bool(value["auth_ready"] and value["session_ready"] and value["endpoint_reachable"])
    value["identity_gate"] = bool(value["provider"] == "codex" and value["request_model"] == "gpt-5.4" and value["generation_backend"] == "image_generation" and value["profile_continuity_match"])
    version_text = str(value["runtime_version"].get("doctor_version") or "")
    value["runtime_identity_gate"] = bool(value["wrapper_sha256_actual"] == WRAPPER_SHA and value["binary_sha256_actual"] == BINARY_SHA and version_text == "0.7.3")
    value["manifest_path"] = str(MANIFEST)
    value["manifest_sha256"] = sha256_file(MANIFEST)
    value["manifest_sha256_expected"] = MANIFEST_SHA
    write_json(PRE / "authorized_runtime_preflight.json", value)
    if not value["identity_gate"]:
        raise RuntimeError("P4D_GR3E current provider identity/profile differs from preparation")
    if not value["runtime_identity_gate"]:
        raise RuntimeError("P4D_GR3E runtime wrapper/binary/version changed")
    if not value["provider_ready_gate"]:
        raise RuntimeError("P4D_GR3E provider is not ready")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("authorize", "preflight"))
    args = parser.parse_args()
    for directory in (CONT, PRE, AUTH, RUNNER_DIR, LEDGER_DIR, RAW_LOG_DIR, CHECKPOINT_DIR, QA_DIR, REVIEW_DIR, FREEZE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    parent = require_parent_freezes()
    zero_batch_check()
    if args.command == "authorize":
        value = authorization_attestation(parent)
        print(json.dumps({"authorization_present": True, "attestation_path": value["path"], "attestation_sha256": value["sha256"], "previous_terminal_freeze_sha256": PREV_TF_SHA}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not (AUTH / "full_regen_authorization_attestation.json").exists():
        raise RuntimeError("authorization attestation must be created before provider preflight")
    before = dataset_snapshot("before_runtime_preflight")
    result = provider_preflight()
    after = dataset_snapshot("after_runtime_preflight")
    result["dataset_boundary"] = {"before": before["counts"], "after": after["counts"], "delta": {key: after["counts"][key] - before["counts"][key] for key in before["counts"]}, "p4d_reference_hits_total": max(before["p4d_reference_hits_total"], after["p4d_reference_hits_total"])}
    write_json(PRE / "authorized_runtime_preflight.json", result)
    print(json.dumps({"provider_ready_gate": result["provider_ready_gate"], "identity_gate": result["identity_gate"], "runtime_identity_gate": result["runtime_identity_gate"], "auth_ready": result["auth_ready"], "session_ready": result["session_ready"], "endpoint_reachable": result["endpoint_reachable"], "profile_continuity_match": result["profile_continuity_match"], "no_retry_guarantee": result["no_retry_guarantee"], "wrapper_sha256": result["wrapper_sha256_actual"], "binary_sha256": result["binary_sha256_actual"], "dataset_before": before["counts"], "dataset_after": after["counts"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        raise SystemExit(2)
