#!/usr/bin/env python3
"""Create immutable P2L DEV-only diagnostic manifests.

Selection is based only on the frozen P2 DESIGN manifest, never on P2 VAL
predictions or individual P2 errors.  The selection is deterministic so the
result can be independently recreated from the source manifest.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from PIL import Image


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
OUT = ROOT / "06_p2l_remote_latency_forensics/02_diagnostic_manifest"
DESIGN = P2 / "01_internal_split/p2_design_manifest.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "media_id",
        "image_path",
        "image_sha256",
        "event_label",
        "sample_role",
        "scenario_id",
        "group_id",
        "original_split",
        "p2_internal_role",
        "source_type",
        "selection_reason",
    ]
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        f.flush()
    tmp.replace(path)


def select_round_robin(rows: list[dict[str, str]], role: str, count: int) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in sorted((r for r in rows if r["sample_role"] == role), key=lambda r: (r["group_id"], r["media_id"])):
        grouped.setdefault(row["group_id"], []).append(row)
    selected: list[dict[str, str]] = []
    groups = sorted(grouped)
    for offset in range(max((len(v) for v in grouped.values()), default=0)):
        for group in groups:
            if offset < len(grouped[group]) and len(selected) < count:
                selected.append(grouped[group][offset])
        if len(selected) >= count:
            break
    if len(selected) != count:
        raise RuntimeError(f"cannot select {count} rows for role={role}; got {len(selected)}")
    return selected


def verify_image(row: dict[str, str]) -> int:
    path = Path(row["image_path"])
    if not path.is_file():
        raise RuntimeError(f"missing image: {path}")
    actual = sha256(path)
    if actual != row["image_sha256"]:
        raise RuntimeError(f"image hash mismatch: {path}")
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        im.load()
        width, height = im.size
    return path.stat().st_size


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load(DESIGN)
    if len(rows) != 190 or any(r.get("p2_internal_role") != "P2_DESIGN" for r in rows):
        raise RuntimeError("P2 DESIGN manifest is not the expected 190-row DESIGN source")
    if any((r.get("original_split") or "") != "DEV" for r in rows):
        raise RuntimeError("P2L diagnostic source is not DEV-only")
    if any((r.get("split") or "") == "HOLDOUT" for r in rows):
        raise RuntimeError("P2L source contains HOLDOUT")

    # Select the smallest deterministic binary-GT image for the repeated
    # request probe.  Size is a practical corruption/oversize guard and has no
    # semantic role.
    binary = [r for r in rows if r.get("event_label") in {"0", "1"}]
    fixed = sorted(binary, key=lambda r: (verify_image(r), r["media_id"]))[0]
    fixed = dict(fixed, selection_reason="smallest_verified_binary_p2_design_image_for_repeated_probe")

    diverse: list[dict[str, str]] = []
    for role, count in (("positive", 4), ("negative", 4), ("hard_negative", 8)):
        diverse.extend(
            dict(r, selection_reason=f"deterministic_round_robin_{role}_from_p2_design")
            for r in select_round_robin(rows, role, count)
        )
    if len({r["media_id"] for r in diverse}) != 16:
        raise RuntimeError("diverse manifest is not unique")
    if len({r["group_id"] for r in diverse}) < 4:
        raise RuntimeError("diverse manifest does not span enough groups")
    for row in diverse:
        verify_image(row)

    fixed_path = OUT / "p2l_fixed_image_manifest.csv"
    diverse_path = OUT / "p2l_diverse_manifest.csv"
    write(fixed_path, [fixed])
    write(diverse_path, diverse)
    sidecar = OUT / "manifests.sha256"
    sidecar.write_text(
        f"{sha256(fixed_path)}  {fixed_path.name}\n{sha256(diverse_path)}  {diverse_path.name}\n"
    )
    report = {
        "source_manifest": str(DESIGN),
        "source_manifest_sha256": sha256(DESIGN),
        "source_role": "P2_DESIGN",
        "fixed_count": 1,
        "fixed_media_ids": [fixed["media_id"]],
        "diverse_count": 16,
        "diverse_role_counts": {role: sum(r["sample_role"] == role for r in diverse) for role in ("positive", "negative", "hard_negative")},
        "diverse_group_count": len({r["group_id"] for r in diverse}),
        "holdout_rows": 0,
        "fixed_manifest_sha256": sha256(fixed_path),
        "diverse_manifest_sha256": sha256(diverse_path),
        "selection_uses_p2_val_individual_errors": False,
        "selection_uses_p2_val_predictions": False,
    }
    (OUT / "manifest_report.md").write_text(
        "# P2L diagnostic manifest report\n\n"
        "The fixed and diverse manifests were selected only from the frozen P2 DESIGN manifest before new P2L requests.\n\n"
        "```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
