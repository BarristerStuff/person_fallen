#!/usr/bin/env python3
"""Independent P3 candidate-freeze verifier; attestation is separate."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
FREEZE = P3 / "03_candidates/candidate_freeze.json"
ATTEST = P3 / "03_candidates/candidate_freeze_attestation.json"
REGISTRY = P3 / "03_candidates/candidate_registry.csv"
CFG = P3 / "03_candidates/p3_request_config.json"
RUNNER = ROOT / "tools/p3_inference_runner.py"


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def main() -> None:
    before = sha(FREEZE)
    if before is None:
        raise SystemExit("P3_CANDIDATE_FREEZE_MISSING")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected = {
        "c3_prompt": (P3 / "03_candidates/C3_BASELINE/C3_prompt.txt", "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"),
        "p2_winner_freeze": (P2 / "05_winner_freeze/p2_winner_freeze.json", "ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0"),
        "config": (CFG, freeze.get("config_sha256")),
        "runner": (RUNNER, freeze.get("runner_sha256")),
        "design_manifest": (P2 / "01_internal_split/p2_design_manifest.csv", freeze.get("design_manifest_sha256")),
        "screen_manifest": (P2 / "01_internal_split/p2_screen_manifest.csv", freeze.get("screen_manifest_sha256")),
        "canary_manifest": (P3 / "04_canary/canary_manifest.csv", freeze.get("canary_manifest_sha256")),
        "candidate_registry": (REGISTRY, freeze.get("candidate_registry_sha256")),
        "p2_c3_screen_predictions": (P2 / "04_screening/C3/predictions.csv", freeze.get("p2_c3_screen_predictions_sha256")),
    }
    checks = {}
    for name, (path, expected_sha) in expected.items():
        actual = sha(path)
        checks[name] = {"path": str(path), "expected_sha256": expected_sha, "actual_sha256": actual, "match": bool(actual and expected_sha and actual == expected_sha)}
        if not checks[name]["match"]:
            errors.append(name + "_hash_mismatch")

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if cfg.get("think") is not False or cfg.get("format") != "json" or "keep_alive" in cfg or cfg.get("options") != {"temperature": 0, "num_ctx": 8192, "num_predict": 256}:
        errors.append("request_config_semantics_invalid")
    if freeze.get("model_digest") != "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd":
        errors.append("model_digest_invalid")
    if freeze.get("screen_blind_before_candidate_freeze") is not True or freeze.get("p2_screen_individual_errors_used_for_p3_design") is not False or freeze.get("val_individual_errors_used_for_p3_design") is not False:
        errors.append("blindness_governance_invalid")
    if freeze.get("new_val_requests") != 0 or freeze.get("holdout_requests") != 0 or freeze.get("optional_s2_created") is not False:
        errors.append("scope_governance_invalid")

    design = load_csv(P2 / "01_internal_split/p2_design_manifest.csv")
    screen = load_csv(P2 / "01_internal_split/p2_screen_manifest.csv")
    canary = load_csv(P3 / "04_canary/canary_manifest.csv")
    canary_counts = {role: sum(row.get("sample_role") == role for row in canary) for role in ["positive", "negative", "hard_negative", "uncertain"]}
    split_check = {
        "design_count": len(design), "screen_count": len(screen), "canary_count": len(canary),
        "design_screen_media_overlap": len({r["media_id"] for r in design} & {r["media_id"] for r in screen}),
        "design_screen_group_overlap": len({r["group_id"] for r in design} & {r["group_id"] for r in screen}),
        "canary_holdout": sum((r.get("original_split") or r.get("split")) == "HOLDOUT" for r in canary),
        "canary_val": sum((r.get("original_split") or r.get("split")) == "VAL" for r in canary),
        "canary_role_counts": canary_counts,
    }
    if split_check["design_count"] != 190 or split_check["screen_count"] != 120 or split_check["canary_count"] != 12 or split_check["design_screen_media_overlap"] or split_check["design_screen_group_overlap"] or split_check["canary_holdout"] or split_check["canary_val"] or canary_counts != {"positive": 3, "negative": 2, "hard_negative": 5, "uncertain": 2}:
        errors.append("split_or_canary_invalid")

    registry = load_csv(REGISTRY)
    ids = [row["candidate_id"] for row in registry]
    if ids != ["C3_BASELINE", "S1_DIRECT", "S1_RULE", "OPTIONAL_S2"]:
        errors.append("candidate_registry_order_or_ids_invalid")
    if freeze.get("candidates", {}).get("S1_DIRECT", {}).get("prompt_sha256") != freeze.get("candidates", {}).get("S1_RULE", {}).get("prompt_sha256"):
        errors.append("s1_stream_prompt_not_shared")
    if freeze.get("candidates", {}).get("S1_DIRECT", {}).get("schema_sha256") != freeze.get("candidates", {}).get("S1_RULE", {}).get("schema_sha256") or freeze.get("candidates", {}).get("S1_DIRECT", {}).get("rule_sha256") != freeze.get("candidates", {}).get("S1_RULE", {}).get("rule_sha256"):
        errors.append("s1_stream_assets_not_shared")
    if freeze.get("candidates", {}).get("S1_DIRECT", {}).get("candidate_eligible_for_screen") is not True or freeze.get("candidates", {}).get("S1_RULE", {}).get("candidate_eligible_for_screen") is not True:
        errors.append("s1_candidates_not_eligible")
    if freeze.get("candidates", {}).get("OPTIONAL_S2", {}).get("candidate_eligible_for_screen") is not False:
        errors.append("optional_s2_should_not_exist")

    after = sha(FREEZE)
    if before != after:
        errors.append("freeze_changed_during_verification")
    attestation = {
        "verification_result": "PASS" if not errors else "FAIL",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "freeze_sha256": before,
        "freeze_unchanged_during_verification": before == after,
        "checks": checks,
        "split_check": split_check,
        "errors": errors,
    }
    atomic_json(ATTEST, attestation)
    print(json.dumps(attestation, ensure_ascii=False, sort_keys=True))
    if errors:
        raise SystemExit("P3_CANDIDATE_FREEZE_VERIFICATION=FAIL")


if __name__ == "__main__":
    main()
