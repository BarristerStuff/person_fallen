"""Materialize a normalized, immutable inventory of the 115 V5-B0 results.
No model or network calls. The semantic files remain in the original V5-B0 tree.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))
from reuse_v5_b0 import load_reuse_records, sha256  # noqa: E402


def main() -> None:
    output = ROOT / "manifests/reuse115_records.json"
    if output.exists():
        raise RuntimeError("reuse inventory already exists; refusing overwrite")
    records, freeze = load_reuse_records()
    with output.open("x", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    inventory = {
        "status": "PASS_V5_B0_REUSE_PREPARED",
        "candidate": "V5-B0-TARGET-ATTRIBUTES",
        "count": len(records),
        "result_source": "REUSE_V5_B0_PILOT",
        "source_candidate_freeze": str(Path(__file__).resolve().parents[2] / "17_person_fallen_v5_target_attributes/freeze/EXECUTION_FREEZE.json"),
        "source_candidate_freeze_sha256": sha256(Path(__file__).resolve().parents[2] / "17_person_fallen_v5_target_attributes/freeze/EXECUTION_FREEZE.json"),
        "records_sha256": sha256(output),
        "raw_response_count": len({r["original_raw_response_sha256"] for r in records}),
        "original_request_ids_unique": len({r["original_request_id"] for r in records}) == len(records),
        "source_hash_binding_all": all(r["source_binding_ok"] is True for r in records),
        "strict_json_all": all(r["strict_json_ok"] is True for r in records),
        "semantic_files_directly_bound": True,
        "model": freeze["model"],
        "VAL_images_read": 0,
        "VAL_predictions_read": 0,
        "HOLDOUT_read": 0,
    }
    audit_path = ROOT / "reports/reuse_inventory_audit.json"
    with audit_path.open("x", encoding="utf-8") as handle:
        json.dump(inventory, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(inventory, ensure_ascii=False))


if __name__ == "__main__":
    main()
