"""Metadata-only audit of historical VAL exposure.

This intentionally reads only manifest identity metadata and the historical P1R
summary. It never opens VAL image bytes, generation prompts, predictions, or
per-sample evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
V3_VAL = BASE / "11_person_fallen_v3_revision/remap/person_fallen_v3_val_manifest.csv"
P1R_MANIFEST = BASE / "04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv"
P1R_SUMMARY = BASE / "04_p1r_freeze_binding_recovery/val/summary.json"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metadata_rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"missing header: {path}")
        # P1R's actual manifest has no item_id; preserve that information gap rather than inventing it.
        available = [field for field in fields if field in reader.fieldnames]
        missing = [field for field in fields if field not in reader.fieldnames]
        if not all(field in reader.fieldnames for field in ('media_id','group_id','image_sha256')):
            raise ValueError(f"missing required overlap metadata in {path}: {missing}")
        # Project only allowed metadata columns; absent item_id is explicitly null.
        return [{field: row.get(field) if field in available else None for field in fields} for row in reader]


def main() -> None:
    output = ROOT / "reports/legacy_val_exposure_audit.json"
    if output.exists():
        raise RuntimeError("legacy VAL audit already exists; refusing overwrite")
    fields = ("item_id", "media_id", "group_id", "image_sha256")
    v3 = metadata_rows(V3_VAL, fields)
    p1r = metadata_rows(P1R_MANIFEST, fields)
    if len(v3) != 100 or len(p1r) != 100:
        raise ValueError("legacy VAL metadata row count is not 100/100")
    v3_by_media = {row["media_id"]: row for row in v3}
    p1r_by_media = {row["media_id"]: row for row in p1r}
    v3_by_sha = {row["image_sha256"]: row for row in v3}
    p1r_by_sha = {row["image_sha256"]: row for row in p1r}
    if len(v3_by_media) != 100 or len(p1r_by_media) != 100 or len(v3_by_sha) != 100 or len(p1r_by_sha) != 100:
        raise ValueError("duplicate legacy VAL metadata identity")
    summary = json.loads(P1R_SUMMARY.read_text(encoding="utf-8"))
    result = {
        "status": "PASS_HISTORIC_VAL_EXPOSURE_CONFIRMED_METADATA_ONLY",
        "v3_val_manifest": {"path": str(V3_VAL), "sha256": sha(V3_VAL), "rows": len(v3)},
        "p1r_recovery_val_manifest": {"path": str(P1R_MANIFEST), "sha256": sha(P1R_MANIFEST), "rows": len(p1r)},
        "p1r_summary": {"path": str(P1R_SUMMARY), "sha256": sha(P1R_SUMMARY), "execution_status": summary.get("execution_status"), "planned_val_requests": summary.get("planned_val_requests"), "confirmed_completed_requests": summary.get("confirmed_completed_requests"), "p1r_val_is_pristine": summary.get("P1R_VAL_IS_PRISTINE"), "holdout_consumed": summary.get("holdout_consumed")},
        "overlap": {
            "media_id_overlap": len(set(v3_by_media) & set(p1r_by_media)),
            "image_sha256_overlap": len(set(v3_by_sha) & set(p1r_by_sha)),
            "group_id_overlap": len({row["group_id"] for row in v3} & {row["group_id"] for row in p1r}),
            "item_id_overlap": len({row["item_id"] for row in v3 if row["item_id"] is not None} & {row["item_id"] for row in p1r if row["item_id"] is not None}),
        },
        "conclusion": "V5 has not run this VAL in the current candidate, but the 100-row collection is historically exposed and is not pristine independent validation.",
        "metadata_gap": "P1R recovery manifest has no item_id column; item_id overlap is unavailable (not inferred). Media and image SHA overlap remain directly verified.",
        "allowed_reads": ["item_id", "media_id", "group_id", "image_sha256", "manifest hash", "historical execution status and request counts"],
        "forbidden_reads_performed": {"val_images": 0, "val_generation_prompts": 0, "val_predictions": 0, "val_evidence": 0, "holdout": 0},
        "not_used_for_candidate_design": True,
        "p1r_item_id_column_present": False,
    }
    if result["overlap"]["media_id_overlap"] != 100 or result["overlap"]["image_sha256_overlap"] != 100:
        raise ValueError("expected 100/100 historical VAL overlap not confirmed")
    if summary.get("execution_status") != "COMPLETE" or summary.get("planned_val_requests") != 100 or summary.get("confirmed_completed_requests") != 100 or summary.get("P1R_VAL_IS_PRISTINE") is not False:
        raise ValueError("historical P1R execution metadata mismatch")
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"media_overlap": 100, "image_sha_overlap": 100, "p1r_status": summary.get("execution_status"), "pristine": summary.get("P1R_VAL_IS_PRISTINE"), "val_images_read": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
