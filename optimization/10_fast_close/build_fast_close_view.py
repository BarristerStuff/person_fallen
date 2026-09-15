#!/usr/bin/env python3
"""Build a read-only person_fallen v2 fast-close audit and human-review view.

This script deliberately does not call a provider, mutate the formal dataset,
or manufacture semantic ground truth. It resolves the current terminal
partition to authoritative historical asset records, performs mechanical
checks, and creates a review package whose labels remain blank.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps


EVENT = "person_fallen"
VERSION = "v2.0"
ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
GR3 = ROOT / "08_p4d_new_hard_negative_dev_revision"
EXEC = GR3 / "02_generation/gr3_fullregen/06_execution"
Q10 = EXEC / "quota_campaign_window_07_gr3q10_authorized_20260901_01"
Q9 = EXEC / "quota_campaign_window_06_gr3q9_authorized_20260831_01"
Q8 = EXEC / "quota_campaign_window_05_gr3q8_authorized_20260831_01"
Q7 = EXEC / "quota_campaign_window_04_gr3q7_authorized_20260831_01"
Q6 = EXEC / "quota_campaign_window_03_gr3q6_authorized_20260831_01"
Q5 = EXEC / "quota_campaign_window_02_policy_adapter_20260830_01"
Q2_INVENTORY = Q5 / "00_preflight/current_verified_success_132.csv"
Q5_LEDGER = Q5 / "03_ledger/gr3q5.sqlite3"
Q6_PARTITION = Q6 / "06_partial_qa/current_verified_success.csv"
Q10_PARTITION = Q10 / "06_partial_qa/verified_success.csv"
Q10_UNKNOWN = Q10 / "06_partial_qa/completion_unknown_quarantine.csv"
Q10_SAFE = Q10 / "06_partial_qa/safe_executable_outstanding.csv"
FULL_MANIFEST = GR3 / "02_generation/gr3_fullregen/03_fullregen_plan/full_regen_prompt_manifest.csv"
P4D_FREEZE = GR3 / "freeze/p4d_generation_required_freeze.json"
P4D_OVERVIEW = GR3 / "02_generation/gr3_fullregen/freeze/overview.md"
P4D_FINAL_REPORT = ROOT / "reports/29_p4d_final_report.md"
Q10_FREEZE = Q10 / "freeze/p4d_gr3q10_execution_terminal_freeze.json"
Q10_FINAL_REPORT = ROOT / "reports/124_p4d_gr3q10_final.md"
ACTIVE_DATASET_VALIDATOR = Q10 / "00_preflight/dataset_after.json"
DOWNLOAD_BATCHES = Path("/home/yanbo/下载/batches")
OUT = ROOT / "10_fast_close"
REVIEW = OUT / "FAST_CLOSE_HUMAN_REVIEW"
OUTPUT_MANIFEST = OUT / "fast_close_clean_manifest.csv"
OUTPUT_AUDIT = OUT / "fast_close_data_audit.json"
OUTPUT_REPORT = OUT / "fast_close_report.md"
REVIEW_MANIFEST = REVIEW / "review_manifest.csv"
REVIEW_PAGE = REVIEW / "index.html"
REVIEW_INSTRUCTIONS = REVIEW / "review_instructions.md"
REVIEW_STATUS = REVIEW / "package_status.json"
RESAMPLING = getattr(Image, "Resampling", Image)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_once(path: Path, content: str) -> None:
    """Refuse to overwrite a changed generated or human-review artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if old != content:
            raise RuntimeError(f"refusing to overwrite existing changed file: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def asset_path_is_allowed(path: Path, prompt_id: str) -> bool:
    if path.name != f"{prompt_id}.png" or path.parent.name not in {
        "final",
        "08_final",
        "generated_raw",
        "07_generated_raw",
    }:
        return False
    if is_under(path, ROOT):
        return True
    if is_under(path, DOWNLOAD_BATCHES):
        cursor = path
        while cursor != DOWNLOAD_BATCHES and cursor.parent != cursor:
            if cursor.name.startswith("batch-person-fallen-v2-p4d-hardneg"):
                return True
            cursor = cursor.parent
    return False


def inspect_image(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_symlink": path.is_symlink(),
        "verify": False,
        "load": False,
        "format": "",
        "mode": "",
        "width": None,
        "height": None,
        "error": "",
    }
    if not result["exists"] or not result["is_file"]:
        result["error"] = "missing_or_not_file"
        return result
    try:
        with Image.open(path) as image:
            result["format"] = image.format or ""
            image.verify()
        result["verify"] = True
        with Image.open(path) as image:
            result["mode"] = image.mode
            result["width"], result["height"] = image.size
            image.load()
        result["load"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def dhash(path: Path) -> int:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("L")
        image = image.resize((17, 16), resample=RESAMPLING.LANCZOS)
        pixels = list(image.getdata())
    value = 0
    for y in range(16):
        row = y * 17
        for x in range(16):
            value = (value << 1) | int(pixels[row + x] > pixels[row + x + 1])
    return value


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def union_find_groups(pairs: Iterable[tuple[int, int]], size: int) -> list[list[int]]:
    parent = list(range(size))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in pairs:
        union(left, right)
    grouped: dict[int, list[int]] = defaultdict(list)
    for node in range(size):
        grouped[find(node)].append(node)
    return [members for members in grouped.values() if len(members) > 1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def source_stage_for_row(row: dict[str, str]) -> tuple[str, Path, str, str]:
    source = row.get("source", "")
    if source == "Q7_EXECUTION":
        return "Q7_EXECUTION", Q7 / "02_runner/run_config.json", "codex", "CODEX_SAFE_STAGED_CV_V1"
    if source == "Q8_EXECUTION":
        return "Q8_EXECUTION", Q8 / "02_plan/run_config.json", "codex", "CODEX_SAFE_STAGED_CV_V1"
    if source.startswith("P4D_GR3Q10_"):
        return "Q10_EXECUTION", Q10 / "02_runner/run_config.json", "codex", "CODEX_SAFE_STAGED_CV_V1"
    raise RuntimeError(f"unrecognized clean-success source: {source!r}")


def make_html(review_rows: list[dict[str, str]]) -> str:
    payload = json.dumps(review_rows, ensure_ascii=False, separators=(",", ":"))
    title = "person_fallen v2.0 fast-close human review"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,-apple-system,"Noto Sans CJK SC",sans-serif;margin:0;background:#111;color:#eee}}
header{{position:sticky;top:0;background:#20252b;padding:12px 18px;z-index:2}}
main{{max-width:1500px;margin:0 auto;padding:18px}}
.grid{{display:grid;grid-template-columns:minmax(520px,2fr) minmax(320px,1fr);gap:18px}}
.card{{background:#20252b;border-radius:8px;padding:14px}}
img{{max-width:100%;max-height:76vh;display:block;margin:auto;background:#000}}
label{{display:block;margin:10px 0 4px;color:#b9c6d3}}
select,input,textarea,button{{font:inherit;width:100%;box-sizing:border-box;padding:8px;border-radius:4px;border:1px solid #52606d;background:#111;color:#eee}}
textarea{{min-height:100px;resize:vertical}}
button{{cursor:pointer;background:#2d6cdf;border:0;margin-top:8px}}
button.secondary{{background:#495057}}
.nav{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px}}
.meta{{font-size:.92rem;line-height:1.45;overflow-wrap:anywhere}}
.warning{{color:#ffd166}}
.counter{{font-variant-numeric:tabular-nums}}
@media (max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header>
  <div><strong>{html.escape(title)}</strong> — <span id="position"></span></div>
  <div class="counter">已填复核: <span id="reviewed-count">0</span> / <span id="total-count"></span></div>
</header>
<main>
  <p class="warning">这是人工候选复核入口，不是正式 P4D 440 条审核的替代品；不得把 planned role、prompt 或模型输出当作 GT。</p>
  <div class="grid">
    <section class="card">
      <img id="sample-image" alt="candidate image">
      <div class="nav">
        <button class="secondary" id="prev">上一条</button>
        <button class="secondary" id="next">下一条</button>
        <button id="download">下载当前 CSV</button>
      </div>
      <p class="meta" id="path"></p>
    </section>
    <section class="card">
      <div class="meta" id="metadata"></div>
      <label for="decision">人工结论（必填）</label>
      <select id="decision">
        <option value="">未复核</option>
        <option value="accept">accept</option>
        <option value="reject">reject</option>
        <option value="uncertain">uncertain</option>
      </select>
      <label for="event">人工事件标签</label>
      <select id="event">
        <option value="">未填写</option>
        <option value="person_fallen">person_fallen</option>
        <option value="not_person_fallen">not_person_fallen</option>
        <option value="uncertain">uncertain</option>
      </select>
      <label for="role">人工样本角色</label>
      <select id="role">
        <option value="">未填写</option>
        <option value="positive">positive</option>
        <option value="hard_negative">hard_negative</option>
        <option value="ordinary_negative">ordinary_negative</option>
        <option value="uncertain">uncertain</option>
      </select>
      <label for="alignment">语义对齐</label>
      <select id="alignment">
        <option value="">未填写</option>
        <option value="aligned">aligned</option>
        <option value="misaligned">misaligned</option>
        <option value="uncertain">uncertain</option>
      </select>
      <label for="artifact">图像工件状态</label>
      <select id="artifact">
        <option value="">未填写</option>
        <option value="pass">pass</option>
        <option value="reject">reject</option>
        <option value="uncertain">uncertain</option>
      </select>
      <label for="reviewer">审核人</label>
      <input id="reviewer" autocomplete="off">
      <label for="notes">备注</label>
      <textarea id="notes"></textarea>
      <button id="save">保存当前行到浏览器状态</button>
    </section>
  </div>
</main>
<script>
const rows = {payload};
let index = 0;
const fields = {{
  decision: "accept_reject_uncertain",
  event: "reviewed_event_label",
  role: "reviewed_sample_role",
  alignment: "semantic_alignment",
  artifact: "image_artifact_status",
  reviewer: "reviewer",
  notes: "notes"
}};
const stateKey = "person_fallen_v2_fast_close_review_v1";
let state = {{}};
try {{ state = JSON.parse(localStorage.getItem(stateKey) || "{{}}"); }} catch (e) {{ state = {{}}; }}
document.getElementById("total-count").textContent = rows.length;
function current() {{ return rows[index]; }}
function loadRow() {{
  const row = current();
  document.getElementById("position").textContent = (index + 1) + " / " + rows.length + " — " + row.prompt_id;
  document.getElementById("sample-image").src = row.image_path_uri;
  document.getElementById("path").textContent = row.image_path;
  document.getElementById("metadata").innerHTML =
    "<b>prompt_id</b>: " + row.prompt_id + "<br>" +
    "<b>group</b>: " + row.group_id + "<br>" +
    "<b>planned split</b>: " + row.planned_split + "<br>" +
    "<b>planned role</b>: " + row.planned_role + "<br>" +
    "<b>taxonomy</b>: " + row.taxonomy + "<br>" +
    "<b>provider</b>: " + row.provider + "<br>" +
    "<b>historical adapter</b>: " + row.historical_adapter_version;
  const saved = state[row.prompt_id] || {{}};
  for (const [id, key] of Object.entries(fields)) document.getElementById(id).value = saved[key] || "";
  document.getElementById("reviewed-count").textContent =
    Object.values(state).filter(x => x.accept_reject_uncertain).length;
}}
function saveRow() {{
  const row = current();
  state[row.prompt_id] = {{}};
  for (const [id, key] of Object.entries(fields)) state[row.prompt_id][key] = document.getElementById(id).value;
  state[row.prompt_id].review_status = state[row.prompt_id].accept_reject_uncertain ? "reviewed" : "unreviewed";
  state[row.prompt_id].review_timestamp = new Date().toISOString();
  localStorage.setItem(stateKey, JSON.stringify(state));
  loadRow();
}}
function move(delta) {{ saveRow(); index = Math.max(0, Math.min(rows.length - 1, index + delta)); loadRow(); }}
document.getElementById("save").onclick = saveRow;
document.getElementById("prev").onclick = () => move(-1);
document.getElementById("next").onclick = () => move(1);
document.getElementById("download").onclick = () => {{
  saveRow();
  const columns = Object.keys(rows[0]).filter(k => k !== "image_path_uri");
  const quote = v => '"' + String(v ?? "").replaceAll('"', '""') + '"';
  const lines = [columns.map(quote).join(",")];
  for (const row of rows) {{
    const merged = Object.assign({{}}, row, state[row.prompt_id] || {{}});
    lines.push(columns.map(k => quote(merged[k])).join(","));
  }}
  const blob = new Blob(["\ufeff" + lines.join("\\n") + "\\n"], {{type:"text/csv;charset=utf-8"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "review_manifest.completed.csv"; a.click(); URL.revokeObjectURL(a.href);
}};
loadRow();
</script>
</body>
</html>
"""


def count_existing_human_rows() -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".csv" or "review" not in path.name.lower():
            continue
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if not rows or "review_status" not in rows[0] or "reviewer" not in rows[0]:
            continue
        legal = [
            row
            for row in rows
            if row.get("review_status", "").strip().lower() in {"pass", "accepted", "reject", "rejected", "uncertain"}
            and row.get("reviewer", "").strip()
        ]
        records.append({"path": str(path), "rows": len(rows), "legal_rows": len(legal)})
    return {
        "files_inspected": len(records),
        "files": records,
        "legal_human_review_rows": sum(item["legal_rows"] for item in records),
    }


def resolve_historical_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    q2_map: dict[str, dict[str, Any]] = {}
    for row in read_csv(Q2_INVENTORY):
        pid = row["prompt_id"]
        if pid in q2_map:
            raise RuntimeError(f"duplicate q2 inventory prompt_id: {pid}")
        q2_map[pid] = {
            "raw_path": row["raw_path"],
            "final_path": row["final_path"],
            "raw_sha256": row["raw_sha256"],
            "final_sha256": row["final_sha256"],
            "historical_stage": "Q2_PRE_Q6_LEGACY_INVENTORY",
            "historical_adapter_version": row.get("source", "LEGACY_NO_ADAPTER"),
            "provider": "codex",
            "provenance_evidence": str(Q2_INVENTORY),
            "sha_evidence": "preexisting_inventory_sha256",
        }

    q5_map: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(Q5_LEDGER) as connection:
        cursor = connection.execute(
            "SELECT prompt_id, raw_path, final_path FROM slots WHERE state = 'SUCCESS'"
        )
        for pid, raw_path, final_path in cursor.fetchall():
            if pid in q5_map:
                raise RuntimeError(f"duplicate q5 ledger prompt_id: {pid}")
            q5_map[pid] = {
                "raw_path": raw_path,
                "final_path": final_path,
                "raw_sha256": "",
                "final_sha256": "",
                "historical_stage": "Q5_EXECUTION",
                "historical_adapter_version": "CODEX_SAFE_STAGED_CV_V1",
                "provider": "codex",
                "provenance_evidence": str(Q5_LEDGER),
                "sha_evidence": "no_preexisting_sha_in_q5_slots_table",
            }

    q6_map: dict[str, dict[str, Any]] = {}
    for row in read_csv(Q6_PARTITION):
        if row.get("source") != "Q6_EXECUTION":
            continue
        pid = row["prompt_id"]
        q6_map[pid] = {
            "raw_path": row["raw_path"],
            "final_path": row["final_path"],
            "raw_sha256": row["raw_sha256"],
            "final_sha256": row["final_sha256"],
            "historical_stage": "Q6_EXECUTION",
            "historical_adapter_version": row.get("adapter_version", ""),
            "provider": "codex",
            "provenance_evidence": str(Q6_PARTITION),
            "sha_evidence": "preexisting_partition_sha256",
        }
    return q2_map, q5_map, q6_map


def find_known_final_paths() -> list[Path]:
    paths: set[Path] = set()
    for search_root in (ROOT, DOWNLOAD_BATCHES):
        if not search_root.exists():
            continue
        for path in search_root.rglob("*.png"):
            if (
                path.name.startswith("PF_P4D_")
                and path.parent.name in {"final", "08_final"}
                and path.is_file()
            ):
                paths.add(path)
    return sorted(paths)


def main() -> int:
    if not Q10_PARTITION.exists() or not Q10_FREEZE.exists():
        raise RuntimeError("Q10 terminal artifacts are missing")
    current_rows = read_csv(Q10_PARTITION)
    q9_ids = {row["prompt_id"] for row in read_csv(Q9 / "02_plan/q9_hard_negative_balanced_30_plan.csv")}
    unknown_rows = read_csv(Q10_UNKNOWN)
    safe_rows = read_csv(Q10_SAFE)
    q10_freeze = load_json(Q10_FREEZE)
    q10_partition_sha = sha256_file(Q10_PARTITION)
    q9_plan_path = Q9 / "02_plan/q9_hard_negative_balanced_30_plan.csv"
    q9_plan_sha = sha256_file(q9_plan_path)

    current_ids = {row["prompt_id"] for row in current_rows}
    if len(current_rows) != 232 or len(current_ids) != 232:
        raise RuntimeError(f"FAST_CLOSE_PREFLIGHT_BLOCKED: current verified partition is {len(current_rows)} rows")
    if len(q9_ids) != 30 or not q9_ids.issubset(current_ids):
        raise RuntimeError("FAST_CLOSE_PREFLIGHT_BLOCKED: Q9 binding-blocked set does not match current verified partition")
    if len(unknown_rows) != 1 or len(safe_rows) != 207:
        raise RuntimeError("FAST_CLOSE_PREFLIGHT_BLOCKED: Q10 unknown/outstanding partition counts changed")
    if q10_freeze.get("accounting_after") != {
        "binding_blocked_success": 30,
        "clean_success": 202,
        "completion_unknown": 1,
        "safe_executable_outstanding": 207,
        "sum": 440,
        "target_total": 440,
    }:
        raise RuntimeError("FAST_CLOSE_PREFLIGHT_BLOCKED: Q10 terminal accounting does not match frozen accounting")

    q2_map, q5_map, q6_map = resolve_historical_maps()
    manifest_rows = read_csv(FULL_MANIFEST)
    manifest_by_id: dict[str, dict[str, str]] = {}
    manifest_order: dict[str, int] = {}
    for ordinal, row in enumerate(manifest_rows):
        pid = row["prompt_id"]
        if pid in manifest_by_id:
            raise RuntimeError(f"duplicate full manifest prompt_id: {pid}")
        manifest_by_id[pid] = row
        manifest_order[pid] = ordinal
    if len(manifest_rows) != 440:
        raise RuntimeError(f"FAST_CLOSE_PREFLIGHT_BLOCKED: full manifest rows={len(manifest_rows)}")

    clean_rows = [row for row in current_rows if row["prompt_id"] not in q9_ids]
    if len(clean_rows) != 202:
        raise RuntimeError(f"FAST_CLOSE_PREFLIGHT_BLOCKED: clean_success rows={len(clean_rows)}")
    clean_rows.sort(key=lambda row: manifest_order.get(row["prompt_id"], 10**9))

    resolved: list[dict[str, Any]] = []
    resolution_counts = Counter()
    for row in clean_rows:
        pid = row["prompt_id"]
        if pid not in manifest_by_id:
            raise RuntimeError(f"prompt not found in frozen full manifest: {pid}")
        if row["source"] == "PRE_Q7_VERIFIED":
            if pid in q2_map:
                source_record = q2_map[pid]
            elif pid in q5_map:
                source_record = q5_map[pid]
            elif pid in q6_map:
                source_record = q6_map[pid]
            else:
                raise RuntimeError(f"cannot resolve inherited PRE_Q7 asset: {pid}")
            resolution_counts[source_record["historical_stage"]] += 1
        else:
            stage, evidence, provider, adapter = source_stage_for_row(row)
            source_record = {
                "raw_path": row.get("raw_path", ""),
                "final_path": row.get("final_path", ""),
                "raw_sha256": row.get("raw_sha256", ""),
                "final_sha256": row.get("final_sha256", ""),
                "historical_stage": stage,
                "historical_adapter_version": adapter,
                "provider": provider,
                "provenance_evidence": str(evidence),
                "sha_evidence": "preexisting_partition_sha256",
            }
            resolution_counts[stage] += 1
        full = manifest_by_id[pid]
        resolved.append(
            {
                "prompt_id": pid,
                "group_id": full["group_id"],
                "variant_id": full["variant_id"],
                "role": row["role"],
                "taxonomy": row["taxonomy"],
                "planned_split": row["planned_split"],
                "prompt_path": full.get("original_prompt_path", ""),
                "prompt_sha256_expected": full.get("prompt_sha256", ""),
                "current_partition_source": row["source"],
                "current_partition_adapter_version": row.get("adapter_version", ""),
                "raw_path": source_record["raw_path"],
                "final_path": source_record["final_path"],
                "raw_sha256_expected": source_record.get("raw_sha256", ""),
                "final_sha256_expected": source_record.get("final_sha256", ""),
                "historical_stage": source_record["historical_stage"],
                "historical_adapter_version": source_record["historical_adapter_version"],
                "provider": source_record["provider"],
                "provenance_evidence": source_record["provenance_evidence"],
                "sha_evidence": source_record["sha_evidence"],
                "target_event_label_from_prompt_plan": full.get("target_event_label", ""),
                "planned_role_from_prompt_plan": full.get("target_role", ""),
                "planned_split_from_prompt_plan": full.get("planned_internal_split", ""),
            }
        )

    prompt_sha_mismatches: list[str] = []
    raw_sha_mismatches: list[str] = []
    final_sha_mismatches: list[str] = []
    raw_final_samefile: list[str] = []
    disallowed_paths: list[str] = []
    metadata_mismatches: list[str] = []
    image_failure_ids: list[str] = []
    q5_missing_sha_ids: list[str] = []
    final_hash_by_id: dict[str, str] = {}
    dhash_by_id: dict[str, int] = {}

    for item in resolved:
        pid = item["prompt_id"]
        prompt_path = Path(item["prompt_path"])
        raw_path = Path(item["raw_path"])
        final_path = Path(item["final_path"])
        prompt_actual = sha256_file(prompt_path) if prompt_path.is_file() else ""
        raw_actual = sha256_file(raw_path) if raw_path.is_file() else ""
        final_actual = sha256_file(final_path) if final_path.is_file() else ""
        raw_info = inspect_image(raw_path)
        final_info = inspect_image(final_path)
        item.update(
            {
                "prompt_sha256_actual": prompt_actual,
                "raw_sha256_actual": raw_actual,
                "final_sha256_actual": final_actual,
                "raw_width": raw_info["width"],
                "raw_height": raw_info["height"],
                "raw_format": raw_info["format"],
                "raw_pillow_verify": raw_info["verify"],
                "raw_pillow_load": raw_info["load"],
                "final_width": final_info["width"],
                "final_height": final_info["height"],
                "final_format": final_info["format"],
                "final_pillow_verify": final_info["verify"],
                "final_pillow_load": final_info["load"],
            }
        )
        if item["prompt_sha256_expected"] != prompt_actual:
            prompt_sha_mismatches.append(pid)
        if item["raw_sha256_expected"] and item["raw_sha256_expected"] != raw_actual:
            raw_sha_mismatches.append(pid)
        if item["final_sha256_expected"] and item["final_sha256_expected"] != final_actual:
            final_sha_mismatches.append(pid)
        if not item["raw_sha256_expected"] or not item["final_sha256_expected"]:
            q5_missing_sha_ids.append(pid)
        if raw_path.exists() and final_path.exists():
            try:
                if os.path.samefile(raw_path, final_path):
                    raw_final_samefile.append(pid)
            except OSError:
                pass
        if not asset_path_is_allowed(raw_path, pid) or not asset_path_is_allowed(final_path, pid):
            disallowed_paths.append(pid)
        full = manifest_by_id[pid]
        if any(
            item[key] != full_value
            for key, full_value in (
                ("role", full.get("target_role", "")),
                ("taxonomy", full.get("taxonomy", "")),
                ("planned_split", full.get("planned_internal_split", "")),
            )
        ):
            metadata_mismatches.append(pid)
        if not (
            raw_info["verify"]
            and raw_info["load"]
            and final_info["verify"]
            and final_info["load"]
            and (final_info["width"], final_info["height"]) == (1920, 1080)
        ):
            image_failure_ids.append(pid)
        final_hash_by_id[pid] = final_actual
        if final_actual:
            dhash_by_id[pid] = dhash(final_path)

    for item in resolved:
        item["mechanical_status"] = "PASS" if item["prompt_id"] not in image_failure_ids else "FAIL"

    sha_to_ids: dict[str, list[str]] = defaultdict(list)
    for pid, digest in final_hash_by_id.items():
        sha_to_ids[digest].append(pid)
    exact_internal_groups = [sorted(ids) for digest, ids in sha_to_ids.items() if digest and len(ids) > 1]
    near_pairs: list[dict[str, Any]] = []
    ordered_ids = [item["prompt_id"] for item in resolved]
    for left_index, left_id in enumerate(ordered_ids):
        if left_id not in dhash_by_id:
            continue
        for right_id in ordered_ids[left_index + 1 :]:
            if right_id not in dhash_by_id:
                continue
            distance = hamming(dhash_by_id[left_id], dhash_by_id[right_id])
            if distance <= 4:
                near_pairs.append({"prompt_id_a": left_id, "prompt_id_b": right_id, "dhash_hamming": distance})
    near_groups = union_find_groups(
        [
            (ordered_ids.index(pair["prompt_id_a"]), ordered_ids.index(pair["prompt_id_b"]))
            for pair in near_pairs
        ],
        len(ordered_ids),
    )

    selected_final_paths = {Path(item["final_path"]).resolve() for item in resolved}
    known_sha_to_paths: dict[str, list[str]] = defaultdict(list)
    for path in find_known_final_paths():
        if path.resolve() in selected_final_paths:
            continue
        try:
            digest = sha256_file(path)
        except OSError:
            continue
        known_sha_to_paths[digest].append(str(path))
    historical_exact_collisions: dict[str, list[str]] = {}
    for item in resolved:
        digest = item["final_sha256_actual"]
        if digest in known_sha_to_paths:
            historical_exact_collisions[item["prompt_id"]] = known_sha_to_paths[digest]

    all_group_splits: dict[str, set[str]] = defaultdict(set)
    for row in manifest_rows:
        all_group_splits[row["group_id"]].add(row["planned_internal_split"])
    clean_group_splits: dict[str, set[str]] = defaultdict(set)
    for item in resolved:
        clean_group_splits[item["group_id"]].add(item["planned_split"])
    full_group_split_leakage = {
        group: sorted(splits) for group, splits in all_group_splits.items() if len(splits) > 1
    }
    clean_group_split_leakage = {
        group: sorted(splits) for group, splits in clean_group_splits.items() if len(splits) > 1
    }
    duplicate_prompt_ids = [
        pid for pid, count in Counter(item["prompt_id"] for item in resolved).items() if count > 1
    ]

    dataset_validator = load_json(ACTIVE_DATASET_VALIDATOR)
    validator_result = dataset_validator.get("validator", dataset_validator)
    if not isinstance(validator_result, dict):
        raise RuntimeError("dataset validator evidence has no validator object")
    dataset_fingerprint = {
        key: validator_result.get(key)
        for key in (
            "status",
            "error_count",
            "full_hash_check",
            "media_count",
            "label_count",
            "batch_count",
            "split_count",
            "warning_count",
        )
        if key in validator_result
    }

    existing_human = count_existing_human_rows()
    provider_counts = Counter(item["provider"] for item in resolved)
    adapter_counts = Counter(item["historical_adapter_version"] for item in resolved)
    partition_adapter_counts = Counter(item["current_partition_adapter_version"] for item in resolved)
    stage_counts = Counter(item["historical_stage"] for item in resolved)
    provenance_evidence_missing = [
        item["prompt_id"] for item in resolved if not Path(item["provenance_evidence"]).is_file()
    ]
    current_adapter_is_historical = [
        item["prompt_id"]
        for item in resolved
        if item["current_partition_adapter_version"] != item["historical_adapter_version"]
    ]

    for item in resolved:
        item["known_historical_final_exact_collision_count"] = len(
            historical_exact_collisions.get(item["prompt_id"], [])
        )
        item["near_duplicate_candidate_count"] = sum(
            item["prompt_id"] in {pair["prompt_id_a"], pair["prompt_id_b"]} for pair in near_pairs
        )
        item["provenance_status"] = (
            "PASS" if item["provider"] == "codex" and Path(item["provenance_evidence"]).is_file() else "GAP"
        )
        item["prompt_lineage_status"] = (
            "PASS" if item["prompt_sha256_expected"] == item["prompt_sha256_actual"] else "FAIL"
        )
        item["sha_integrity_status"] = (
            "PASS"
            if (
                item["raw_sha256_actual"]
                and item["final_sha256_actual"]
                and item["prompt_lineage_status"] == "PASS"
                and item["prompt_id"] not in raw_sha_mismatches
                and item["prompt_id"] not in final_sha_mismatches
            )
            else "PASS_WITHOUT_PREEXISTING_EXPECTED_SHA"
            if item["prompt_id"] in q5_missing_sha_ids
            else "FAIL"
        )

    manifest_fields = [
        "prompt_id",
        "group_id",
        "variant_id",
        "role",
        "taxonomy",
        "planned_split",
        "prompt_path",
        "prompt_sha256_expected",
        "prompt_sha256_actual",
        "current_partition_source",
        "current_partition_adapter_version",
        "historical_stage",
        "historical_adapter_version",
        "provider",
        "provenance_evidence",
        "provenance_status",
        "sha_evidence",
        "raw_path",
        "raw_sha256_expected",
        "raw_sha256_actual",
        "raw_width",
        "raw_height",
        "raw_format",
        "raw_pillow_verify",
        "raw_pillow_load",
        "final_path",
        "final_sha256_expected",
        "final_sha256_actual",
        "final_width",
        "final_height",
        "final_format",
        "final_pillow_verify",
        "final_pillow_load",
        "prompt_lineage_status",
        "sha_integrity_status",
        "mechanical_status",
        "known_historical_final_exact_collision_count",
        "near_duplicate_candidate_count",
    ]
    manifest_buffer = StringIO()
    writer = csv.DictWriter(manifest_buffer, fieldnames=manifest_fields, lineterminator="\n")
    writer.writeheader()
    for item in resolved:
        writer.writerow({field: item.get(field, "") for field in manifest_fields})
    manifest_text = manifest_buffer.getvalue()
    write_once(OUTPUT_MANIFEST, manifest_text)
    manifest_digest = sha256_bytes(manifest_text.encode("utf-8"))

    review_fields = [
        "review_row_id",
        "prompt_id",
        "image_path",
        "image_path_uri",
        "raw_path",
        "group_id",
        "planned_split",
        "planned_role",
        "taxonomy",
        "provider",
        "historical_adapter_version",
        "accept_reject_uncertain",
        "reviewed_event_label",
        "reviewed_sample_role",
        "semantic_alignment",
        "image_artifact_status",
        "review_status",
        "reviewer",
        "review_timestamp",
        "notes",
    ]
    review_rows: list[dict[str, str]] = []
    for index, item in enumerate(resolved, start=1):
        final_path = Path(item["final_path"])
        review_rows.append(
            {
                "review_row_id": f"PFV2-FC-{index:04d}",
                "prompt_id": item["prompt_id"],
                "image_path": item["final_path"],
                "image_path_uri": final_path.as_uri(),
                "raw_path": item["raw_path"],
                "group_id": item["group_id"],
                "planned_split": item["planned_split"],
                "planned_role": item["role"],
                "taxonomy": item["taxonomy"],
                "provider": item["provider"],
                "historical_adapter_version": item["historical_adapter_version"],
                "accept_reject_uncertain": "",
                "reviewed_event_label": "",
                "reviewed_sample_role": "",
                "semantic_alignment": "",
                "image_artifact_status": "",
                "review_status": "unreviewed",
                "reviewer": "",
                "review_timestamp": "",
                "notes": "",
            }
        )
    review_buffer = StringIO()
    review_writer = csv.DictWriter(review_buffer, fieldnames=review_fields, lineterminator="\n")
    review_writer.writeheader()
    for row in review_rows:
        review_writer.writerow({field: row.get(field, "") for field in review_fields})
    write_once(REVIEW_MANIFEST, review_buffer.getvalue())
    write_once(REVIEW_PAGE, make_html(review_rows))

    review_instruction_text = """# person_fallen v2.0 fast-close 人工候选复核

状态：FAST_CLOSE_HUMAN_REVIEW_REQUIRED

这不是 P4D 冻结的 440 条正式人工审核的替代品，也不会解除 GENERATION_REQUIRED / FULL_REGEN_REQUIRED 硬门槛。此包只把当前已机械确认的 clean_success=202 条列成候选，供人检查图像是否与事件和规划角色一致。

## 人工填写原则

1. 必须实际查看图像后填写 accept_reject_uncertain；看不清或语义不确定时填 uncertain，不要猜。
2. planned_role、taxonomy、prompt 文本和 provider 结果只是上下文，不能直接复制为 GT。
3. reviewed_event_label、reviewed_sample_role、semantic_alignment 和 image_artifact_status 必须来自人工观察。
4. 不要把模型预测、Codex/VLM 输出、提示词或文件夹名称转换为 ground truth。
5. 页面里的“下载当前 CSV”会导出 review_manifest.completed.csv。导出后应保留原始 review_manifest.csv，由授权人员审阅导出文件并按正式流程登记；不要覆盖历史冻结文件。
6. 本包没有 NEW_VAL、C3、Holdout 或生产写入授权；在完整 P4D 440 门槛和合法人工 GT 均满足前，不得运行算法评测。

## 页面入口

直接打开同目录下的 index.html。图像使用绝对 file:// 路径引用，不复制或改写源图像。
"""
    write_once(REVIEW_INSTRUCTIONS, review_instruction_text)
    review_status = {
        "event": EVENT,
        "version": VERSION,
        "status": "FAST_CLOSE_HUMAN_REVIEW_REQUIRED",
        "review_rows": len(review_rows),
        "all_rows_unreviewed_at_creation": True,
        "formal_p4d_440_review_replaced": False,
        "ground_truth_created": False,
        "model_or_prompt_used_as_ground_truth": False,
        "image_bytes_copied": False,
        "source_manifest": str(OUTPUT_MANIFEST),
        "review_manifest": str(REVIEW_MANIFEST),
        "review_page": str(REVIEW_PAGE),
    }
    write_once(REVIEW_STATUS, json_text(review_status))

    qa_pass = not (
        prompt_sha_mismatches
        or raw_sha_mismatches
        or final_sha_mismatches
        or raw_final_samefile
        or disallowed_paths
        or metadata_mismatches
        or image_failure_ids
        or duplicate_prompt_ids
        or full_group_split_leakage
        or clean_group_split_leakage
        or provenance_evidence_missing
    )
    audit: dict[str, Any] = {
        "event": EVENT,
        "version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FAST_CLOSE_HUMAN_REVIEW_REQUIRED",
        "is_440_full_generation_a_hard_protocol_requirement": True,
        "hard_requirement_scope": "P4D semantic acceptance and C3/downstream P4D evaluation",
        "stop_further_p4d_generation": True,
        "provider_operation_performed": False,
        "formal_dataset_mutation_performed": False,
        "holdout_operation_performed": False,
        "source_accounting": {
            "current_verified_success": len(current_rows),
            "q9_binding_blocked_excluded": len(q9_ids),
            "clean_success_selected": len(resolved),
            "completion_unknown_excluded": len(unknown_rows),
            "safe_executable_outstanding_excluded": len(safe_rows),
            "total_slots": len(q9_ids) + len(resolved) + len(unknown_rows) + len(safe_rows),
            "partition_sha256": q10_partition_sha,
            "q9_plan_sha256": q9_plan_sha,
        },
        "resolution": {
            "stage_counts": dict(sorted(stage_counts.items())),
            "resolution_counts": dict(sorted(resolution_counts.items())),
            "expected": {
                "Q2_PRE_Q6_LEGACY_INVENTORY": 132,
                "Q5_EXECUTION": 10,
                "Q6_EXECUTION": 9,
                "Q7_EXECUTION": 20,
                "Q8_EXECUTION": 25,
                "Q10_EXECUTION": 6,
            },
        },
        "qa": {
            "status": "PASS" if qa_pass else "FAIL",
            "row_count": len(resolved),
            "unique_prompt_ids": len(set(item["prompt_id"] for item in resolved)),
            "prompt_sha256_mismatch_count": len(prompt_sha_mismatches),
            "raw_sha256_mismatch_count": len(raw_sha_mismatches),
            "final_sha256_mismatch_count": len(final_sha_mismatches),
            "rows_without_preexisting_raw_or_final_sha": len(q5_missing_sha_ids),
            "rows_without_preexisting_raw_or_final_sha_ids": sorted(q5_missing_sha_ids),
            "raw_final_samefile_count": len(raw_final_samefile),
            "disallowed_or_foreign_path_count": len(disallowed_paths),
            "metadata_mismatch_count": len(metadata_mismatches),
            "pillow_or_dimension_failure_count": len(image_failure_ids),
            "final_dimension_distribution": {
                str(key): value
                for key, value in sorted(
                    Counter((item["final_width"], item["final_height"]) for item in resolved).items(),
                    key=str,
                )
            },
            "raw_dimension_distribution": {
                str(key): value
                for key, value in sorted(
                    Counter((item["raw_width"], item["raw_height"]) for item in resolved).items(),
                    key=str,
                )
            },
            "exact_duplicate_internal_final_groups": exact_internal_groups,
            "exact_duplicate_internal_final_group_count": len(exact_internal_groups),
            "exact_duplicate_with_known_historical_final_count": len(historical_exact_collisions),
            "exact_duplicate_with_known_historical_final": historical_exact_collisions,
            "near_duplicate_method": "64-bit dHash on EXIF-transposed grayscale 17x16 resize",
            "near_duplicate_threshold_hamming_le_4": True,
            "near_duplicate_pair_count": len(near_pairs),
            "near_duplicate_pairs": near_pairs,
            "near_duplicate_group_count": len(near_groups),
            "full_frozen_group_split_leakage": full_group_split_leakage,
            "clean_view_group_split_leakage": clean_group_split_leakage,
            "duplicate_prompt_id_count": len(duplicate_prompt_ids),
            "role_counts": dict(sorted(Counter(item["role"] for item in resolved).items())),
            "taxonomy_counts": dict(sorted(Counter(item["taxonomy"] for item in resolved).items())),
            "planned_split_counts": dict(sorted(Counter(item["planned_split"] for item in resolved).items())),
        },
        "provenance": {
            "provider_counts": dict(sorted(provider_counts.items())),
            "historical_adapter_counts": dict(sorted(adapter_counts.items())),
            "current_partition_adapter_counts": dict(sorted(partition_adapter_counts.items())),
            "current_partition_vs_historical_adapter_difference_count": len(current_adapter_is_historical),
            "current_partition_vs_historical_adapter_difference_ids": sorted(current_adapter_is_historical),
            "provenance_evidence_missing_count": len(provenance_evidence_missing),
            "provenance_evidence_missing_ids": sorted(provenance_evidence_missing),
            "note": "Inherited PRE_Q7 rows retain the partition field separately; authoritative historical records say LEGACY_NO_ADAPTER for 132 rows.",
        },
        "human_gt_gate": {
            "existing_review_scan": existing_human,
            "legal_existing_human_review_rows": existing_human["legal_human_review_rows"],
            "legal_gt_sufficient_for_algorithm_eval": False,
            "status": "FAST_CLOSE_HUMAN_REVIEW_REQUIRED",
            "review_package": str(REVIEW),
            "planned_role_is_not_ground_truth": True,
            "prompt_is_not_ground_truth": True,
            "model_output_is_not_ground_truth": True,
        },
        "algorithm_evaluation": {
            "b0_c3": "NOT_RUN_HUMAN_GT_GATE",
            "r1_c3": "NOT_RUN_HUMAN_GT_GATE",
            "new_screen": "NOT_RUN_HUMAN_GT_GATE",
            "new_val": "NOT_RUN",
            "holdout": "NOT_RUN",
            "ready_for_final_holdout": False,
        },
        "active_dataset": {
            "validator_evidence_path": str(ACTIVE_DATASET_VALIDATOR),
            "validator": dataset_fingerprint,
            "production_root_touched": False,
        },
        "evidence": {
            "p4d_generation_required_freeze": str(P4D_FREEZE),
            "p4d_overview": str(P4D_OVERVIEW),
            "p4d_final_report": str(P4D_FINAL_REPORT),
            "q10_terminal_freeze": str(Q10_FREEZE),
            "q10_final_report": str(Q10_FINAL_REPORT),
            "full_manifest": str(FULL_MANIFEST),
            "output_manifest": str(OUTPUT_MANIFEST),
            "output_manifest_sha256": manifest_digest,
            "builder_sha256": sha256_file(Path(__file__)),
        },
        "stop_reasons": [
            "P4D frozen protocol explicitly requires complete 440-slot generation before semantic acceptance/C3.",
            "Provider terminal state is usage_limit_reached; no retry/resend/unknown replay is authorized.",
            "No legal explicit human semantic GT rows exist; prompt/planned role/model output cannot fill that gap.",
            "Further generation would not directly change the current C3 bottleneck and is stopped by this handoff.",
        ],
    }
    # These are derived audit summaries, not human-edited review state. They
    # may be regenerated after correcting a check implementation; the review
    # manifest/page themselves remain write-once to protect human edits.
    OUTPUT_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_AUDIT.write_text(json_text(audit), encoding="utf-8", newline="\n")
    audit_digest = sha256_file(OUTPUT_AUDIT)
    (OUT / "fast_close_clean_manifest.sha256").write_text(
        manifest_digest + "  fast_close_clean_manifest.csv\n", encoding="utf-8", newline="\n"
    )
    (OUT / "fast_close_data_audit.sha256").write_text(
        audit_digest + "  fast_close_data_audit.json\n", encoding="utf-8", newline="\n"
    )

    role_counts = dict(sorted(Counter(item["role"] for item in resolved).items()))
    split_counts = dict(sorted(Counter(item["planned_split"] for item in resolved).items()))
    report = f"""# person_fallen v2.0 fast-close handoff

STATUS=FAST_CLOSE_HUMAN_REVIEW_REQUIRED

## 独立判断

- IS_440_FULL_GENERATION_A_HARD_PROTOCOL_REQUIREMENT=true：冻结的 P4D 设计和后续报告明确把完整 440 槽位作为语义接受/C3 的前置条件。本次 fast-close 视图不绕过该门槛。
- STOP_FURTHER_P4D_GENERATION=true：Q10 已在 provider usage_limit_reached 后终止；本次没有 provider 请求、Q10 重试、unknown 重发、207 条 outstanding 生成、formal ingest 或 Holdout 操作。
- clean_success=202 已按当前 terminal partition 精确重建；Q9 的 30 条 binding-blocked、1 条 completion_unknown 和 207 条 safe outstanding 均未进入视图。

## 可核实事实

| 项目 | 结果 |
|---|---:|
| 当前 verified partition | {len(current_rows)} |
| 排除 Q9 binding-blocked | {len(q9_ids)} |
| fast-close clean manifest | {len(resolved)} |
| completion_unknown | {len(unknown_rows)} |
| safe_executable_outstanding | {len(safe_rows)} |
| accounting sum | {len(q9_ids) + len(resolved) + len(unknown_rows) + len(safe_rows)} / 440 |
| full frozen group/split leakage | {len(full_group_split_leakage)} |
| clean-view group/split leakage | {len(clean_group_split_leakage)} |
| internal exact-final duplicate groups | {len(exact_internal_groups)} |
| known historical exact-final collisions | {len(historical_exact_collisions)} |
| near-duplicate pairs, dHash distance <=4 | {len(near_pairs)} |
| Pillow/dimension failures | {len(image_failure_ids)} |
| prompt SHA mismatches | {len(prompt_sha_mismatches)} |
| raw/final SHA mismatches | {len(raw_sha_mismatches) + len(final_sha_mismatches)} |
| legal human GT rows found | {existing_human["legal_human_review_rows"]} |

Resolved stages: {json.dumps(dict(sorted(stage_counts.items())), ensure_ascii=False)}.

Role counts: {json.dumps(role_counts, ensure_ascii=False)}.

Split counts: {json.dumps(split_counts, ensure_ascii=False)}.

## provenance 风险

历史权威记录显示 132 条 inherited rows 是 LEGACY_NO_ADAPTER；当前后续 partition 的通用字段却写成了 CODEX_SAFE_STAGED_CV_V1。本审计把 current_partition_adapter_version 与 historical_adapter_version 分开保留，不把后者缺失或前者通用值升级成虚假的逐图 adapter 证据。Q5 的 10 条成功记录在 SQLite slots 表中有状态和路径，但没有预存 raw/final SHA，因此审计仅能报告“本次重新计算”，不能伪称已有独立 SHA 证据。

## GT 与算法评测

当前没有合法的显式人工 semantic GT。已生成最小 review 包，202 条全部保持 unreviewed。因此：

- B0/C3=NOT_RUN_HUMAN_GT_GATE
- R1/C3=NOT_RUN_HUMAN_GT_GATE
- NEW_SCREEN=NOT_RUN_HUMAN_GT_GATE
- READY_FOR_FINAL_HOLDOUT=false

不得用 prompt、planned role、Codex/VLM 输出或目录名补 GT。完成人工复核也不能自动解除 P4D 的完整 440 硬门槛；需要按冻结协议重新完成完整生成和正式 QA/review 后才可能进入 P4D C3/后续阶段。

## 证据入口

- clean manifest: {OUTPUT_MANIFEST}
- data audit: {OUTPUT_AUDIT}
- human review page: {REVIEW_PAGE}
- human review instructions: {REVIEW_INSTRUCTIONS}
- Q10 terminal freeze: {Q10_FREEZE} (sha256={sha256_file(Q10_FREEZE)})
- Q10 final report: {Q10_FINAL_REPORT}
- P4D generation-required freeze: {P4D_FREEZE}
- frozen full prompt manifest: {FULL_MANIFEST}
- active dataset validator evidence: {ACTIVE_DATASET_VALIDATOR}

本次只新增 fast-close 审计/人工入口文件，没有写入 /home/yanbo/net_vlm_yanboversion/vlm，没有改写共享数据集，也没有改变历史冻结文件。
"""
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(report, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "status": audit["status"],
                "clean_success": len(resolved),
                "stage_counts": dict(sorted(stage_counts.items())),
                "qa_status": audit["qa"]["status"],
                "human_gt_rows": existing_human["legal_human_review_rows"],
                "output_manifest": str(OUTPUT_MANIFEST),
                "review_page": str(REVIEW_PAGE),
                "audit": str(OUTPUT_AUDIT),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
