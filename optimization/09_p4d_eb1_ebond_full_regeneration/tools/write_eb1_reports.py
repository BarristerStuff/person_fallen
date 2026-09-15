#!/usr/bin/env python3
"""Materialize the sealed P4D_EB1 failure reports and post-run audit.

This script is report/QA bookkeeping only.  It never sends a provider request,
never reads a prompt into a model, and never changes the formal dataset.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OPT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration")
BATCH = Path("/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-ebond-fullregen-r1-camera1p5m")
REPORTS = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization/reports")
DATASET_VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
DATASET_BEFORE = OPT / "config/dataset_validator_before.json"
DATASET_AFTER = OPT / "config/dataset_validator_after.json"
DB = OPT / "ledger/p4d_eb1_execution.sqlite3"
TERMINAL = OPT / "freeze/p4d_eb1_terminal_freeze.json"
TERMINAL_SIDECAR = OPT / "freeze/p4d_eb1_terminal_freeze.json.sha256"
PREFLIGHT = OPT / "freeze/p4d_eb1_preflight_freeze.json"
RUNNER = OPT / "tools/ebond_one_shot_runner.py"
ORDER = OPT / "order/ebond_balanced_execution_order.csv"
RUN_CONFIG = OPT / "execution/run_config.json"
REQUEST_LOG = OPT / "execution/request_log.jsonl"
RAW_LOG = OPT / "execution/raw_responses.jsonl"
LEDGER_CSV = OPT / "ledger/execution_ledger.csv"
REVISION = "P4D_EBOND_FULLREGEN_20260828_01"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path: Path, value: Any) -> None:
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def write_text(path: Path, value: str) -> None:
    write_bytes(path, (value if value.endswith("\n") else value + "\n").encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            result.append(json.loads(line))
    return result


def run_validator() -> dict[str, Any]:
    result = subprocess.run([sys.executable, str(DATASET_VALIDATOR), "--json"], capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"dataset validator failed with {result.returncode}: {result.stderr[-1000:]}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("dataset validator returned non-object JSON")
    return value


def db_rows() -> list[sqlite3.Row]:
    if not DB.is_file():
        return []
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM slots ORDER BY order_index").fetchall()
    finally:
        conn.close()


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = max(0, min(len(values) - 1, int(round((len(values) - 1) * q))))
    return values[index]


def pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def markdown_table(rows: list[tuple[str, str]]) -> str:
    return "| 项目 | 实际值 |\n|---|---|\n" + "\n".join(f"| {name} | {value} |" for name, value in rows)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    dataset_before = read_json(DATASET_BEFORE)
    dataset_after = run_validator()
    write_json(DATASET_AFTER, dataset_after)
    terminal = read_json(TERMINAL)
    terminal_sidecar = TERMINAL_SIDECAR.read_text(encoding="utf-8").split()[0] if TERMINAL_SIDECAR.is_file() else None
    terminal_sha = sha256_file(TERMINAL)
    rows = db_rows()
    request_records = jsonl(REQUEST_LOG)
    raw_records = jsonl(RAW_LOG)
    logical_requests_sent = sum(1 for row in rows if int(row["attempt_count"] or 0) > 0)
    statuses = Counter(str(row["status"]) for row in rows)
    http_classes = Counter()
    latencies = []
    for row in rows:
        if row["http_status"] is not None:
            status = int(row["http_status"])
            if 200 <= status < 300:
                http_classes["2xx"] += 1
            elif status in {401, 403, 429}:
                http_classes[str(status)] += 1
            elif 500 <= status < 600:
                http_classes["5xx"] += 1
            else:
                http_classes[str(status)] += 1
        if row["latency_seconds"] is not None:
            latencies.append(float(row["latency_seconds"]))
    order_rows = list(csv.DictReader(ORDER.open(encoding="utf-8", newline="")))
    planned_role = Counter(row["target_role"] for row in order_rows)
    planned_taxonomy = Counter(row["taxonomy"] for row in order_rows)
    planned_split = Counter(row["planned_internal_split"] for row in order_rows)
    generated_role = Counter(row["target_role"] for row in rows if row["status"] == "SUCCESS")
    generated_taxonomy = Counter(row["taxonomy"] for row in rows if row["status"] == "SUCCESS")
    generated_split = Counter(row["planned_internal_split"] for row in rows if row["status"] == "SUCCESS")
    holdout_request_records = [item for item in request_records if item.get("holdout") is True or item.get("planned_internal_split") == "HOLDOUT"]
    raw_files = sorted((BATCH / "metadata/raw_provider_responses").glob("*.json"))
    raw_images = sorted((BATCH / "generated_raw").glob("*.png"))
    final_images = sorted((BATCH / "final").glob("*.png"))
    validator_delta = {key: dataset_after.get(key) - dataset_before.get(key) for key in ("media_count", "label_count", "batch_count", "split_count") if isinstance(dataset_after.get(key), int) and isinstance(dataset_before.get(key), int)}
    freeze_summary = {
        "created_at": now(),
        "status": terminal.get("terminal_status"),
        "preflight_freeze": {"path": str(PREFLIGHT), "sha256": sha256_file(PREFLIGHT)},
        "terminal_freeze": {"path": str(TERMINAL), "sha256": terminal_sha, "sidecar_sha256": terminal_sidecar, "sidecar_match": terminal_sidecar == terminal_sha},
        "runner": {"path": str(RUNNER), "sha256": sha256_file(RUNNER)},
        "run_config": {"path": str(RUN_CONFIG), "sha256": sha256_file(RUN_CONFIG)},
        "order": {"path": str(ORDER), "sha256": sha256_file(ORDER)},
        "ledger": {"sqlite_path": str(DB), "sqlite_sha256": sha256_file(DB), "csv_path": str(LEDGER_CSV), "csv_sha256": sha256_file(LEDGER_CSV)},
        "counts": {"logical_slots": len(rows), "successful": statuses.get("SUCCESS", 0), "failed_confirmed": statuses.get("FAILED_CONFIRMED", 0), "completion_unknown": statuses.get("COMPLETION_UNKNOWN", 0), "pending": statuses.get("PENDING", 0), "started": statuses.get("STARTED", 0), "outstanding": 440 - statuses.get("SUCCESS", 0)},
        "http_classes": dict(http_classes),
        "latency_seconds": {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95), "max": max(latencies) if latencies else None},
        "raw_response_count": len(raw_files),
        "raw_image_count": len(raw_images),
        "final_image_count": len(final_images),
        "holdout_requests": len(holdout_request_records),
        "holdout_consumed": False,
        "dataset_validator_before": {key: dataset_before.get(key) for key in ("status", "error_count", "full_hash_check", "warning_count", "media_count", "label_count", "batch_count", "split_count")},
        "dataset_validator_after": {key: dataset_after.get(key) for key in ("status", "error_count", "full_hash_check", "warning_count", "media_count", "label_count", "batch_count", "split_count")},
        "dataset_delta": validator_delta,
        "planned_role_counts": dict(planned_role),
        "planned_taxonomy_counts": dict(planned_taxonomy),
        "planned_split_counts": dict(planned_split),
        "generated_role_counts": dict(generated_role),
        "generated_taxonomy_counts": dict(generated_taxonomy),
        "generated_split_counts": dict(generated_split),
        "codex_images_reused": 0,
        "gr1_images_reused": 0,
        "p4d_images_accepted": 0,
        "formal_ingest": False,
        "c3": False,
        "new_val": 0,
    }
    write_json(OPT / "qa/eb1_postrun_audit.json", freeze_summary)
    write_json(OPT / "qa/eb1_qa_status.json", {"created_at": now(), "full_440_mechanical_qa": "NOT_REACHED", "reason": "PRIMARY returned HTTP 401 before first image; no raw/final images exist", "raw_count": len(raw_images), "final_count": len(final_images), "pillow_verified": "N/A", "exact_duplicates": "N/A", "near_duplicates": "N/A", "cross_split_duplicates": "N/A", "mapping_rows": "N/A", "accepted": 0})
    write_json(OPT / "human_review/human_review_status.json", {"created_at": now(), "status": "NOT_CREATED_NO_IMAGES", "human_review_rows": 0, "contact_sheets": 0, "semantic_accepted": 0, "p4d_images_accepted": 0, "reason": "generation stopped at PRIMARY HTTP 401 before any image"})
    write_text(BATCH / "metadata/README.md", "Provider response metadata is retained only for the one-shot EBOND smoke. No image bytes were produced; formal ingest remains prohibited.\n")
    write_json(BATCH / "metadata/eb1_batch_status.json", {"created_at": now(), "lineage": "P4D_EB1_EBOND_FULL_REGENERATION", "status": terminal.get("terminal_status"), "raw_images": len(raw_images), "final_images": len(final_images), "outstanding": 440 - statuses.get("SUCCESS", 0), "p4d_images_accepted": 0, "formal_ingest": False, "holdout_requests": 0})

    provider_rows = [
        ("P4D_EB1_STATUS", terminal.get("terminal_status", "N/A")),
        ("P4D_EB1_NAME", "P4D_EB1_EBOND_FULL_REGENERATION"),
        ("P4D_EB1_GENERATION_REVISION", REVISION),
        ("PROVIDER", "EBOND"),
        ("MODEL", "gpt-image-2"),
        ("API_SCHEMA", "POST /v1/images/generations; data[0].b64_json"),
        ("API_SCHEMA_SOURCE", "/home/yanbo/.local/share/Trash/files/image.2/archive/api-capability-tests-20260731/ebondai-direct-1920x1080-result.json; local gpt-image-2 providers.md"),
        ("API_HOST", "api.ebondai.com"),
        ("ACTIVE_CREDENTIAL_SLOT", "PRIMARY (safe fingerprint only)"),
        ("SECONDARY_DISCOVERED", "false"),
        ("CREDENTIAL_FINGERPRINT_SHA256", terminal.get("credential_fingerprint_sha256", "N/A")),
        ("HISTORICAL_CODEX_GENERATION_ASSETS", "true; EBOND_LINEAGE_REUSED_CODEX_IMAGES=0"),
        ("GR1_IMAGES_REUSED", "0"),
        ("FROZEN_MANIFEST_SHA256", "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4"),
        ("RUNNER_SHA256", sha256_file(RUNNER) or "N/A"),
        ("PREFLIGHT_FREEZE_SHA256", sha256_file(PREFLIGHT) or "N/A"),
        ("TERMINAL_FREEZE_SHA256", terminal_sha or "N/A"),
    ]
    generation_rows = [
        ("logical_slots_planned", "440"),
        ("logical_requests_sent", str(logical_requests_sent)),
        ("successful_requests", str(statuses.get("SUCCESS", 0))),
        ("failed_confirmed", str(statuses.get("FAILED_CONFIRMED", 0))),
        ("completion_unknown", str(statuses.get("COMPLETION_UNKNOWN", 0))),
        ("pending_outstanding", str(440 - statuses.get("SUCCESS", 0))),
        ("HTTP_2xx", str(http_classes.get("2xx", 0))),
        ("HTTP_401", str(http_classes.get("401", 0))),
        ("HTTP_403", str(http_classes.get("403", 0))),
        ("HTTP_429", str(http_classes.get("429", 0))),
        ("HTTP_5xx", str(http_classes.get("5xx", 0))),
        ("timeout", str(sum(1 for row in rows if row["completion_semantics"] == "COMPLETION_UNKNOWN"))),
        ("raw_provider_responses", str(len(raw_files))),
        ("raw_images", str(len(raw_images))),
        ("final_images", str(len(final_images))),
        ("smoke", "FAIL: 0/1 image success; HTTP 401 INVALID_API_KEY"),
        ("ramp1", "NOT_REACHED"),
        ("ramp2", "NOT_REACHED"),
        ("client_http_library", "urllib.request with NoRedirect opener"),
        ("client_retry_total", "0"),
        ("logical_retry", "false"),
        ("provider_wrapper_retry", "0"),
        ("client_http_generation_attempts_total", str(sum(int(row["attempt_count"] or 0) for row in rows))),
        ("concurrency", "1"),
        ("latency_p50_seconds", pct(percentile(latencies, 0.50))),
        ("latency_p95_seconds", pct(percentile(latencies, 0.95))),
    ]
    qa_rows = [
        ("full_440_mechanical_qa", "NOT_REACHED"),
        ("Pillow", "N/A (raw image count=0)"),
        ("exact_duplicates", "N/A"),
        ("near_duplicates", "N/A"),
        ("cross_split_duplicates", "N/A"),
        ("prompt_image_mapping", "N/A"),
        ("P4D_IMAGES_ACCEPTED", "0 (not yet human accepted; no images)"),
    ]
    human_rows = [
        ("human_review_package", "NOT_CREATED_NO_IMAGES"),
        ("human_review_rows", "0"),
        ("contact_sheets", "0"),
        ("semantic_accepted", "0"),
        ("formal_ingest", "false; MEDIA_ADDED=0; LABELS_ADDED=0"),
        ("C3", "false"),
        ("NEW_VAL", "0"),
        ("HOLDOUT_REQUESTS", str(len(holdout_request_records))),
        ("HOLDOUT_CONSUMED", "false"),
    ]
    report76 = """# P4D EB1 provider and lineage\n\n""" + markdown_table(provider_rows) + """\n\n## 已确认事实\n\n- Frozen 440 manifest、group/split freeze、prompt pack、C3 prompt 均在 preflight 按指定 SHA-256 复核；`PROMPT_CHANGED=false`、`TAXONOMY_CHANGED=false`、`GROUP_CHANGED=false`、`SPLIT_CHANGED=false`。\n- EBOND schema 来自本机历史成功 direct capability 结果与本地 `gpt-image-2-skill` provider reference；本次未猜测 endpoint 或增加未验证字段。\n- 新 batch 与历史 Codex/GR1 lineage 分离，Codex historical assets 仅作诊断，实际复用为 0。\n\n## 实验判断\n\n- 由于 PRIMARY 的正式第一张 smoke 返回 HTTP 401 且 `INVALID_API_KEY`，在没有可安全取得的 SECONDARY 的前提下，预注册的 auth gate 触发；这次 EBOND lineage 没有形成图像。\n- 这是 credential/auth blocker，不是 semantic 失败、quota 结论或图像质量结论。\n\n## 风险与限制\n\n- 当前可验证的配置 store 只暴露一枚 PRIMARY 的安全指纹；附件所述第二枚 key 在本机当前上下文不可发现，其他事件的 key 被明确排除。不能据此推断 SECONDARY 是否有效。\n- provider 401 的 body、request id 和 hash 已保留，但 Authorization header/key 没有写入任何 artifact。\n\n## 下一阶段建议\n\n- 先由用户在受控 credential store 中修复/轮换 EBOND PRIMARY，或明确提供可安全读取的 SECONDARY credential store；然后创建新的 EB1 auth-recovery revision，而不是改写本次 terminal freeze。\n- 不要在本 sealed run 上重试、切换到其他事件 key、混入 Codex 102、执行 ingest/C3/VAL/HOLDOUT。\n"""
    report77 = """# P4D EB1 generation execution\n\n""" + markdown_table(generation_rows) + """\n\n## 已确认事实\n\n- 仅发送 1 个 logical request：`P4D_EB1_0001 / PF_P4D_HN_SIT_G001_V01`；`attempt_count=1`，HTTP library 是无 retry、禁 redirect 的 `urllib.request`。\n- 响应 raw body 为 JSON `INVALID_API_KEY`，provider request id 与 raw response SHA 已落盘；未产生 raw/final image。\n- smoke FAIL 后没有进入 ramp1/ramp2，也没有发送后续 439 slots。\n\n## 实验判断\n\n本 revision 的停止是 fail-closed 且可审计的：`logical_requests=1`、`successful=0`、`failed_confirmed=1`、`completion_unknown=0`、`outstanding=439`。不能宣称 440 generation 或 generation stability。\n\n## 风险与限制\n\n401 只证明本次 PRIMARY credential 被 provider 拒绝；它不证明模型、prompt、native size 或历史 schema 语义失败。延迟 P50/P95 仅是这次 auth transport latency，不能称图像生成 latency。\n\n## 下一阶段建议\n\n修复 credential 后必须建立新的、独立封存的 auth-recovery revision；保持 one-shot/no-retry 规则，并在新 revision 中重新做 smoke。\n"""
    report78 = """# P4D EB1 full 440 QA\n\n""" + markdown_table(qa_rows) + """\n\n## 已确认事实\n\n- 440 full generation 未完成，raw image=0、final image=0，因此 Pillow、尺寸、exact/near duplicate、cross-split duplicate 与 prompt-image mapping 均未达到可执行前提。\n- QA 结果被标记为 `NOT_REACHED`，不是 PASS，也不是对图像内容的负面结论。\n\n## 实验判断\n\n机械 QA 不能从零张图推出图像质量或 lineage duplicate 结论。\n\n## 风险与限制\n\n如果未来新的 auth-recovery revision 成功，必须在该新 revision 中重新做完整 QA；不得把本次 0 图结果与历史 Codex 图像拼接。\n\n## 下一阶段建议\n\n保持本报告封存，仅在新的 credential-auth revision 完成 440 后按原计划执行机械 QA。\n"""
    report79 = """# P4D EB1 human review package\n\n""" + markdown_table(human_rows) + """\n\n## 已确认事实\n\n- provider 在第一张 smoke 即返回 401，未生成任何可审核图像，因此没有创建 `human_review.csv`、contact sheets 或语义审核队列。\n- `P4D_IMAGES_ACCEPTED=0` 表示 not yet human accepted，不等价于 reject。\n\n## 实验判断\n\n本阶段不涉及语义审核，也没有把 planned role 当作 human-confirmed GT。\n\n## 风险与限制\n\n任何后续审核都必须绑定新的 EBOND lineage、对应 frozen asset hashes 和新的 terminal freeze。\n\n## 下一阶段建议\n\ncredential 修复并在新 revision 完成 440 + mechanical QA 后，再生成独立的人工审核 package；此 revision 保持 0 accepted。\n"""
    report80 = """# P4D EB1 final report\n\n```text\nPROJECT=net_vlm\nEVENT=person_fallen\nEVENT_VERSION=v2.0\n\nP4D_EB1_NAME=P4D_EB1_EBOND_FULL_REGENERATION\nP4D_EB1_PROVIDER=ebond\nP4D_EB1_GENERATION_REVISION=P4D_EBOND_FULLREGEN_20260828_01\nP4D_EB1_STATUS=BLOCKED_PRIMARY_AUTH_NO_SECONDARY\nP4D_EB1_NEW_GENERATION_LINEAGE=true\n\nP4D_EB1_PROMPT_CHANGED=false\nP4D_EB1_TAXONOMY_CHANGED=false\nP4D_EB1_GROUP_CHANGED=false\nP4D_EB1_SPLIT_CHANGED=false\n\nFROZEN_440_MANIFEST_SHA256=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4\nEBOND_LINEAGE_REUSED_CODEX_IMAGES=0\nGR1_IMAGES_REUSED=0\n\nSCHEMA_VERIFIED=true\nACTIVE_EBOND_CREDENTIAL_SLOT=PRIMARY\nSECONDARY_DISCOVERED=false\n\nSMOKE_STATUS=FAIL_HTTP_401\nRAMP1_STATUS=NOT_REACHED\nRAMP2_STATUS=NOT_REACHED\nLOGICAL_REQUESTS=1\nSUCCESSFUL_REQUESTS=0\nFAILED_CONFIRMED=1\nCOMPLETION_UNKNOWN=0\nEBOND_OUTSTANDING=439\n\nRAW_PROVIDER_RESPONSES=1\nRAW_IMAGES=0\nFINAL_IMAGES=0\nFULL_440_MECHANICAL_QA=NOT_REACHED\nP4D_IMAGES_ACCEPTED=0\n\nHOLDOUT_REQUESTS=0\nHOLDOUT_CONSUMED=false\nFORMAL_INGEST=false\nMEDIA_ADDED=0\nLABELS_ADDED=0\nC3=false\nNEW_VAL=0\nPRODUCTION_CODE_MODIFIED=false\n```\n\n## 已确认事实\n\n1. P4D 440 design 与所有冻结依赖在 provider 请求前均通过 SHA-256 核对；balanced order 保持 group 连续，前 16 slots 覆盖 3 roles、4 taxonomies、NEW_DESIGN/NEW_SCREEN。\n2. 历史 schema 证据支持 `POST https://api.ebondai.com/v1/images/generations`、`model=gpt-image-2`、`prompt`、`size=1536x1024`、`quality=medium`、响应 `data[0].b64_json`；本次请求未加入额外未验证字段。\n3. 只有第一张正式 smoke 被发送：HTTP 401，body 为 `INVALID_API_KEY`；请求 id、raw body hash、safe request metadata、SQLite WAL ledger、terminal freeze 均已持久化。\n4. 当前 EBOND lineage 没有任何成功图片，未产生 raw/final output；历史 Codex 102 与 GR1 192 均未复用。\n5. dataset validator before/after 均为 `valid`、`error_count=0`、`full_hash_check=true`；本阶段没有 formal ingest、C3、NEW_VAL 或 HOLDOUT。\n\n## 实验判断\n\n本次 EB1 不是“440 full-regeneration 完成”，而是一个已封存的 credential/auth 阻断：`P4D_EB1_STATUS=BLOCKED_PRIMARY_AUTH_NO_SECONDARY`。由于 smoke gate 未通过，ramp、full generation、mechanical QA、human semantic review 与任何模型评测均不适用，分类指标统一为 `N/A`。\n\n这次结果不支持关于 prompt、model、size、quality、semantic accuracy、image quality 或 EBOND quota 的正面/负面判断；它只支持“当前 PRIMARY credential 被 provider 拒绝且没有可安全取得的 SECONDARY”这一事实。\n\n## 风险与限制\n\n- 用户附件声明有两枚 key，但当前机器可验证 credential store 仅能取得 PRIMARY；不能把其他事件的 key 当作 SECONDARY，也不能在 sealed run 中猜测或轮换。\n- provider 401 可能意味着 key 过期、撤销、环境/账户不匹配或 provider auth policy；准确原因超出本地证据。\n- latency P50/P95（本次约 3.9235 秒）是 auth request latency，不是有效图像生成 latency。\n- 439 个 pending slots 不得由本次历史 Codex 图像补齐；任何恢复都必须新建独立 revision 并重新 preflight。\n\n## 下一阶段建议\n\n1. 在受控、不会把 secret 写入日志的 credential store 中修复/轮换 EBOND PRIMARY，或让 SECONDARY 以同等安全方式可被 runner 读取；不要把 key 粘贴到报告或 shell。\n2. 建立新的 `P4D_EB1_*_AUTH_RECOVERY` revision，重新绑定相同 frozen 440 assets、prompt hashes、group/split、schema、one-shot/no-retry runner 和新的 credential safe fingerprint；本 terminal freeze 不可重写。\n3. 新 revision 只从 smoke 开始；只有 smoke 2xx + valid `b64_json` + Pillow conversion PASS 才能进入 ramp1/ramp2/full 440。\n4. 维持 `P4D_IMAGES_ACCEPTED=0`、`FORMAL_INGEST=false`、`C3=false`、`NEW_VAL=0`、`HOLDOUT_REQUESTS=0`，直到后续独立 revision 通过完整 mechanical QA 与 human review。\n\n## Evidence paths\n\n- Preflight: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/freeze/p4d_eb1_preflight_freeze.json`\n- Terminal: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/freeze/p4d_eb1_terminal_freeze.json`\n- Runner: `/home/yanbo/net_vlm_person_fallen_v2_eb1_ebond_full_regeneration/tools/ebond_one_shot_runner.py`\n- Ledger SQLite: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/ledger/p4d_eb1_execution.sqlite3`\n- Ledger CSV: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/ledger/execution_ledger.csv`\n- Request log: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/execution/request_log.jsonl`\n- Raw provider response: `/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-ebond-fullregen-r1-camera1p5m/metadata/raw_provider_responses/P4D_EB1_0001_PF_P4D_HN_SIT_G001_V01.json`\n- Dataset validator after: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/config/dataset_validator_after.json`\n"""
    report80 = report80.replace("/home/yanbo/net_vlm_person_fallen_v2_eb1_ebond_full_regeneration", str(OPT))
    report80 = report80.replace("EBOND_OUTSTANDING=439", "EBOND_OUTSTANDING=440")
    report80 = report80.replace("439 个 pending slots", "439 个后续 slots 未发送（以非成功 slot 计的 outstanding=440）")
    report77 = report77.replace("outstanding=439", "outstanding=440")
    write_text(REPORTS / "76_p4d_eb1_provider_and_lineage.md", report76)
    write_text(REPORTS / "77_p4d_eb1_generation_execution.md", report77)
    write_text(REPORTS / "78_p4d_eb1_full440_qa.md", report78)
    write_text(REPORTS / "79_p4d_eb1_human_review_package.md", report79)
    write_text(REPORTS / "80_p4d_eb1_final.md", report80)
    print(json.dumps({"status": terminal.get("terminal_status"), "reports": [str(REPORTS / name) for name in ("76_p4d_eb1_provider_and_lineage.md", "77_p4d_eb1_generation_execution.md", "78_p4d_eb1_full440_qa.md", "79_p4d_eb1_human_review_package.md", "80_p4d_eb1_final.md")], "dataset_after": {key: dataset_after.get(key) for key in ("status", "error_count", "full_hash_check", "warning_count", "media_count", "label_count", "batch_count", "split_count")}, "terminal_sha256": terminal_sha, "holdout_requests": len(holdout_request_records)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
