#!/usr/bin/env python3
"""Build an auditable, prompt-derived V2 image manifest without touching production."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Pillow is required for image audit: {exc}")

SRC = Path("/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m")
OUT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
FINAL = SRC / "final"
PROMPTS = SRC / "prompts"
MANIFEST = SRC / "manifest.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CSV_DIALECT = dict(lineterminator="\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dhash(path: Path) -> str:
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        gray = im.convert("L").resize((9, 8))
        px = list(gray.getdata())
    bits = ["1" if px[y * 9 + x] > px[y * 9 + x + 1] else "0" for y in range(8) for x in range(8)]
    return f"{int(''.join(bits), 2):016x}"


def prompt_group(stem: str) -> str:
    m = re.match(r"\d+_([a-z]\d+-.+)-\d+$", stem)
    if not m:
        raise ValueError(f"cannot derive prompt group from {stem}")
    return m.group(1)


def classify(prompt_text: str, group: str) -> tuple[str, str, str]:
    lines = [x.strip() for x in prompt_text.splitlines() if x.strip()]
    declared = lines[0].lower() if lines else ""
    body = " ".join(lines[1:]).lower()
    if declared == "positive":
        label, role = "1", "positive"
        reason = f"Prompt group {group} explicitly requires a real person in a lying/fallen state on ground or abnormal support; V2 accepts voluntary lying and does not require a transition."
    elif declared == "hard_negative":
        label, role = "0", "hard_negative"
        reason = f"Prompt group {group} explicitly designs a V2 visual confound (not a clear ground-lying event), so event_label remains 0 and role is hard_negative."
    elif declared == "negative":
        label, role = "0", "negative"
        reason = f"Prompt group {group} explicitly describes ordinary non-event activity or an empty ordinary environment under the V2 definition."
    elif declared == "uncertain":
        label, role = "uncertain", "uncertain"
        reason = f"Prompt group {group} explicitly requires ambiguity (occlusion, tiny/blurry/partial body, or unclear support surface); retained as uncertain rather than guessed."
    else:
        raise ValueError(f"unsupported prompt declaration {declared!r} for {group}")
    # Guard against a malformed declaration silently passing as a label.
    if not body:
        raise ValueError(f"empty prompt body for {group}")
    return label, role, reason


def write_csv(path: Path, rows: Iterable[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", **CSV_DIALECT)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    if not FINAL.is_dir() or not PROMPTS.is_dir():
        raise SystemExit("source final/ or prompts/ is missing")
    images = sorted(p for p in FINAL.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    prompts = sorted(p for p in PROMPTS.rglob("*") if p.is_file() and p.suffix.lower() == ".txt")
    if len(images) != len(prompts):
        raise SystemExit(f"MAPPING_STATUS=BLOCKED count mismatch images={len(images)} prompts={len(prompts)}")
    prompt_by_stem = {p.stem: p for p in prompts}
    if len(prompt_by_stem) != len(prompts):
        raise SystemExit("MAPPING_STATUS=BLOCKED duplicate prompt stems")
    meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scene_meta = {s.get("file_stem"): s for s in meta.get("scenes", [])}
    mapping, classifications, dup_rows, scenarios = [], [], [], []
    exact = defaultdict(list)
    dh = defaultdict(list)
    for image in images:
        prompt = prompt_by_stem.get(image.stem)
        if prompt is None:
            raise SystemExit(f"MAPPING_STATUS=BLOCKED missing prompt for {image.name}")
        try:
            with Image.open(image) as im:
                im.verify()
            with Image.open(image) as im:
                width, height = im.size
            image_hash, prompt_hash, dhash_value = sha256(image), sha256(prompt), dhash(image)
        except Exception as exc:
            raise SystemExit(f"MAPPING_STATUS=BLOCKED corrupt file {image}: {exc}")
        group = prompt_group(image.stem)
        label, role, reason = classify(prompt.read_text(encoding="utf-8"), group)
        scenario_id = f"pf_v2_aigc_{group}"
        exact[image_hash].append(image.name)
        dh[dhash_value].append(image.name)
        scene = scene_meta.get(image.stem, {})
        mapping.append({
            "image_filename": image.name, "image_path": str(image), "image_sha256": image_hash,
            "image_width": str(width), "image_height": str(height), "prompt_filename": prompt.name,
            "prompt_path": str(prompt), "prompt_sha256": prompt_hash, "mapping_status": "PASS",
        })
        classifications.append({
            "image_filename": image.name, "prompt_filename": prompt.name, "prompt_group": group,
            "event_label": label, "sample_role": role, "label_decision_reason": reason,
            "gt_basis": "user_confirmed_prompt_image_alignment", "review_status": "unreviewed",
        })
        scenarios.append({
            "image_filename": image.name, "scenario_id": scenario_id, "group_id": scenario_id,
            "prompt_group": group, "event_label": label, "sample_role": role,
            "split": "", "split_reason": "group-disjoint role-stratified assignment pending",
        })
    for image_hash, names in exact.items():
        for name in names:
            dup_rows.append({"image_filename": name, "sha256": image_hash, "dhash": next(v for v, ns in dh.items() if name in ns), "exact_duplicate": "yes" if len(names) > 1 else "no", "duplicate_of": sorted(names)[0] if len(names) > 1 and name != sorted(names)[0] else "", "near_duplicate_group": ""})
    # dHash collisions are a conservative near-duplicate candidate set; no source is deleted.
    for dvalue, names in dh.items():
        for name in names:
            for row in dup_rows:
                if row["image_filename"] == name:
                    row["near_duplicate_group"] = f"dhash:{dvalue}" if len(names) > 1 else ""
                    break
    by_group = {row["group_id"]: row["group_id"] for row in scenarios}
    groups = sorted(by_group)
    # Deterministic group-level split: 60/20/20 by group, while keeping every role isolated.
    role_groups = defaultdict(list)
    for row in scenarios:
        role_groups[row["sample_role"]].append(row["group_id"])
    for role in role_groups:
        role_groups[role] = sorted(set(role_groups[role]))
    assignments = {}
    for role, gs in sorted(role_groups.items()):
        n = len(gs)
        if role == "uncertain":
            for g in gs:
                assignments[g] = ("DEV", "uncertain qualitative pool; excluded from formal metrics and holdout")
            continue
        n_dev = max(1, round(n * 0.6)) if n else 0
        n_val = max(0, round(n * 0.2))
        if n_dev + n_val > n:
            n_val = max(0, n - n_dev)
        for g in gs[:n_dev]: assignments[g] = ("DEV", "first deterministic role-group tranche")
        for g in gs[n_dev:n_dev+n_val]: assignments[g] = ("VAL", "second deterministic role-group tranche")
        for g in gs[n_dev+n_val:]: assignments[g] = ("HOLDOUT", "sealed remaining role-group tranche")
    for row in scenarios:
        split, why = assignments[row["group_id"]]
        row["split"], row["split_reason"] = split, why
    frozen = [{
        "media_candidate_id": "", "image_filename": row["image_filename"], "image_sha256": next(x["image_sha256"] for x in mapping if x["image_filename"] == row["image_filename"]),
        "scenario_id": row["scenario_id"], "group_id": row["group_id"], "event_label": row["event_label"], "sample_role": row["sample_role"], "split": row["split"], "split_reason": row["split_reason"], "source_type": "ai_generated", "event_definition_version": "v2.0",
    } for row in scenarios]
    aigc = []
    for row in mapping:
        scene = scene_meta.get(Path(row["image_filename"]).stem, {})
        aigc.append({"image_filename": row["image_filename"], "source_type": "ai_generated", "generation_model": scene.get("generation_model", meta.get("model", "unknown")), "generation_model_version": scene.get("model_version", meta.get("model_version", "unknown")), "prompt_group": scene.get("prompt_group_id", meta.get("prompt_group_id", "unknown")), "seed": str(scene.get("seed", meta.get("seed", "unknown")) if scene.get("seed", meta.get("seed", "unknown")) is not None else "unknown"), "generation_date": scene.get("generation_date", meta.get("generation_date", "unknown")), "generation_batch": scene.get("generation_batch", meta.get("generation_batch", "unknown")), "prompt_path": row["prompt_path"], "prompt_sha256": row["prompt_sha256"], "camera_height_approx_m": "1.5", "source_manifest": str(MANIFEST)})
    write_csv(OUT/"01_data/prompt_image_mapping.csv", mapping, list(mapping[0]))
    write_csv(OUT/"01_data/prompt_classification.csv", classifications, list(classifications[0]))
    write_csv(OUT/"01_data/duplicate_audit.csv", dup_rows, list(dup_rows[0]))
    write_csv(OUT/"01_data/scenario_group_manifest.csv", scenarios, list(scenarios[0]))
    write_csv(OUT/"01_data/frozen_splits.csv", frozen, list(frozen[0]))
    write_csv(OUT/"01_data/aigc_generation_metadata.csv", aigc, list(aigc[0]))
    inv = [{"image_filename": m["image_filename"], "image_path": m["image_path"], "image_sha256": m["image_sha256"], "prompt_filename": m["prompt_filename"], "prompt_sha256": m["prompt_sha256"], "prompt_group": next(c["prompt_group"] for c in classifications if c["image_filename"] == m["image_filename"]), "event_label": next(c["event_label"] for c in classifications if c["image_filename"] == m["image_filename"]), "sample_role": next(c["sample_role"] for c in classifications if c["image_filename"] == m["image_filename"]), "scenario_id": next(s["scenario_id"] for s in scenarios if s["image_filename"] == m["image_filename"]), "group_id": next(s["group_id"] for s in scenarios if s["image_filename"] == m["image_filename"]), "source_type": "ai_generated", "event_definition_version": "v2.0"} for m in mapping]
    write_csv(OUT/"01_data/source_inventory.csv", inv, list(inv[0]))
    snapshot_paths = [OUT/"01_data/"/n for n in ["source_inventory.csv", "prompt_image_mapping.csv", "prompt_classification.csv", "duplicate_audit.csv", "scenario_group_manifest.csv", "frozen_splits.csv", "aigc_generation_metadata.csv"]]
    with (OUT/"01_data/dataset_snapshot.sha256").open("w", encoding="utf-8") as f:
        for p in snapshot_paths:
            f.write(f"{sha256(p)}  {p.name}\n")
    counts = Counter((c["event_label"], c["sample_role"]) for c in classifications)
    splits = Counter((x["split"], x["sample_role"]) for x in scenarios)
    summary = {"image_count": len(images), "prompt_count": len(prompts), "mapping_status": "PASS", "exact_duplicate_files": sum(len(v)-1 for v in exact.values() if len(v)>1), "exact_duplicate_sha_groups": sum(len(v)>1 for v in exact.values()), "near_duplicate_dhash_groups": sum(len(v)>1 for v in dh.values()), "role_counts": dict(Counter(c["sample_role"] for c in classifications)), "label_counts": dict(Counter(c["event_label"] for c in classifications)), "group_count": len(groups), "split_counts": dict(Counter(s["split"] for s in scenarios)), "split_role_counts": {f"{k[0]}:{k[1]}": v for k,v in splits.items()}, "aigc_metadata_completeness": all(x["generation_model"] != "unknown" and x["generation_model_version"] != "unknown" and x["generation_batch"] != "unknown" for x in aigc), "unknown_seed_count": sum(x["seed"] == "unknown" for x in aigc), "source_manifest": str(MANIFEST)}
    (OUT/"01_data/build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
