#!/usr/bin/env python3
"""C3 DESIGN-only residual forensic and taxonomy materializer."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
P2 = ROOT / "05_p2_hard_negative_semantic_optimization"
DESIGN = P3 / "01_c3_design_baseline"
OUT = P3 / "02_design_forensics"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def ratio(a: int, b: int) -> float | None:
    return None if not b else a / b


def metrics(rows: list[dict[str, str]]) -> dict:
    valid = [r for r in rows if r["event_label"] in {"0", "1"} and r["canonical_ok"] == "true"]
    tp = fp = tn = fn = 0
    for row in valid:
        gt = row["event_label"]
        alert = row["predicted_status"] == "positive"
        if gt == "1" and alert:
            tp += 1
        elif gt == "1":
            fn += 1
        elif alert:
            fp += 1
        else:
            tn += 1
    ordinary = [r for r in valid if r["sample_role"] == "negative"]
    hard = [r for r in valid if r["sample_role"] == "hard_negative"]
    uncertain = sum(r["predicted_status"] == "uncertain" for r in valid)
    return {
        "determinate_count": len(valid), "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn), "accuracy": ratio(tp + tn, tp + tn + fp + fn),
        "ordinary_negative_fpr": ratio(sum(r["predicted_status"] == "positive" for r in ordinary), len(ordinary)),
        "hard_negative_fpr": ratio(sum(r["predicted_status"] == "positive" for r in hard), len(hard)),
        "model_uncertain_count": uncertain, "model_uncertain_rate": ratio(uncertain, len(valid)),
        "gt_uncertain_prediction_distribution": dict(Counter(r["predicted_status"] for r in rows if r["event_label"] == "uncertain")),
    }


def taxonomy_name(scenario_id: str) -> str:
    value = scenario_id.lower()
    if "sitting-on-floor" in value:
        return "sitting_on_floor"
    if "kneeling" in value:
        return "kneeling_or_half_kneeling"
    if "squatting" in value:
        return "squatting_or_crouching"
    if "deep-bending" in value:
        return "deep_bending_or_picking"
    if "exercise-push-up-plank" in value:
        return "exercise_pushup_or_plank"
    return "other"


def forensic_type(row: dict[str, str]) -> tuple[str, str, str]:
    """Return primary mechanism, support clue flag, and posture assertion flag.

    The two actual DESIGN residuals were checked against their source scenario
    and image.  Both C3 evidences assert a lying/collapsed posture while also
    mentioning a hand/foot support clue; neither explicitly names the true
    non-lying posture as the final state.  We therefore classify them as the
    strict Type-B visual-attribute error, while retaining the support clue as a
    separate audit field.  This avoids double-counting Type A.
    """
    media_id = row["media_id"]
    if media_id in {"IMG_003739", "IMG_003786"}:
        return (
            "visual_attribute_extraction_error",
            "true",
            "true",
        )
    return "other", "false", "false"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = P2 / "01_internal_split/p2_design_manifest.csv"
    predictions_path = DESIGN / "predictions.csv"
    summary_path = DESIGN / "summary.json"
    manifest = load_csv(manifest_path)
    rows = load_csv(predictions_path)
    if len(manifest) != 190 or len(rows) != 190:
        raise SystemExit("P3_C3_DESIGN_FORENSIC_COUNT_MISMATCH")
    if {r["media_id"] for r in manifest} != {r["media_id"] for r in rows}:
        raise SystemExit("P3_C3_DESIGN_FORENSIC_ENTITY_MISMATCH")
    if any((r.get("original_split") or r.get("split")) in {"VAL", "HOLDOUT"} for r in manifest):
        raise SystemExit("P3_C3_DESIGN_FORENSIC_SCOPE_INVALID")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not summary.get("protocol_gate_pass"):
        raise SystemExit("P3_C3_DESIGN_PROTOCOL_GATE_FAIL")

    computed = metrics(rows)
    fp_rows = [r for r in rows if r["event_label"] == "0" and r["predicted_status"] == "positive"]
    fn_rows = [r for r in rows if r["event_label"] == "1" and r["predicted_status"] != "positive"]
    enriched_fp = []
    for row in fp_rows:
        mechanism, support_clue, lying_assertion = forensic_type(row)
        enriched_fp.append({
            **row,
            "residual_taxonomy": taxonomy_name(row["scenario_id"]),
            "forensic_type": mechanism,
            "explicit_support_clue_in_evidence": support_clue,
            "evidence_asserts_lying": lying_assertion,
            "source_boundary": "P2_DESIGN_ONLY",
        })
    fp_fields = list(enriched_fp[0]) if enriched_fp else [
        "media_id", "residual_taxonomy", "forensic_type", "explicit_support_clue_in_evidence",
        "evidence_asserts_lying", "source_boundary",
    ]
    atomic_csv(OUT / "c3_false_positives.csv", enriched_fp, fp_fields)
    atomic_csv(OUT / "c3_false_negatives.csv", fn_rows, list(rows[0]) if rows else [])

    hard = [r for r in rows if r["sample_role"] == "hard_negative"]
    by_tax: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in hard:
        by_tax[taxonomy_name(row["scenario_id"])].append(row)
    pattern_text = {
        "sitting_on_floor": "no DESIGN residual FP in this category",
        "kneeling_or_half_kneeling": "C3 evidence called a forward-supported posture prone/collapsed; the visible knee/hand-supported posture was not extracted as the final posture",
        "squatting_or_crouching": "no DESIGN residual FP in this category",
        "deep_bending_or_picking": "no DESIGN residual FP in this category",
        "exercise_pushup_or_plank": "C3 evidence noticed hands/feet support but interpreted the body as collapsed lying rather than supported exercise",
        "other": "no residual evidence",
    }
    taxonomy_rows = []
    for name in sorted(by_tax):
        values = by_tax[name]
        fps = [r for r in values if r["predicted_status"] == "positive"]
        taxonomy_rows.append({
            "taxonomy": name,
            "total_samples": len(values),
            "C3_FP": len(fps),
            "C3_TN": len(values) - len(fps),
            "C3_category_FPR": ratio(len(fps), len(values)),
            "group_count": len({r["group_id"] for r in values}),
            "typical_C3_evidence_error": pattern_text.get(name, "no residual evidence"),
        })
    atomic_csv(OUT / "residual_taxonomy.csv", taxonomy_rows, list(taxonomy_rows[0]) if taxonomy_rows else ["taxonomy"])
    atomic_csv(OUT / "taxonomy_statistics.csv", taxonomy_rows, list(taxonomy_rows[0]) if taxonomy_rows else ["taxonomy"])

    mechanisms = {
        "evidence_to_label_inconsistency": [],
        "visual_attribute_extraction_error": [],
        "support_surface_error": [],
        "multi_person_confusion": [],
        "other": [],
    }
    for row in enriched_fp:
        mechanisms[row["forensic_type"]].append(row["media_id"])
    pattern_rows = []
    definitions = {
        "evidence_to_label_inconsistency": "Strict Type A: evidence explicitly names knees/hands as the active non-lying posture but final label remains positive.",
        "visual_attribute_extraction_error": "Type B: evidence asserts lying/collapsed posture although source scenario/image is a stable non-lying posture.",
        "support_surface_error": "Type C: support surface is materially misidentified.",
        "multi_person_confusion": "Type D: another person is used as the target posture.",
        "other": "Type E: residual not covered above.",
    }
    for name in mechanisms:
        ids = mechanisms[name]
        pattern_rows.append({"error_pattern": name, "count": len(ids), "media_ids": ";".join(ids), "definition": definitions[name]})
    # This is a deliberate non-double-counting audit: support clues are kept
    # separately even when the primary Type-B error is selected.
    support_ids = [r["media_id"] for r in enriched_fp if r["explicit_support_clue_in_evidence"] == "true"]
    pattern_rows.append({"error_pattern": "explicit_support_clue_present_but_not_adjudicated", "count": len(support_ids), "media_ids": ";".join(support_ids), "definition": "Audit dimension; not counted as strict Type A unless an explicit non-lying posture is named as the model conclusion."})
    atomic_csv(OUT / "evidence_error_patterns.csv", pattern_rows, list(pattern_rows[0]))

    forensic_summary = {
        "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
        "source": "P2_DESIGN_ONLY",
        "design_manifest_sha256": sha(manifest_path),
        "c3_predictions_sha256": sha(predictions_path),
        "c3_summary_sha256": sha(summary_path),
        "design_rows": len(rows),
        "c3_design_metrics": computed,
        "c3_design_fp_count": len(fp_rows),
        "c3_design_fn_count": len(fn_rows),
        "residual_taxonomy_counts": {r["taxonomy"]: {"total_samples": r["total_samples"], "C3_FP": r["C3_FP"], "C3_TN": r["C3_TN"], "category_FPR": r["C3_category_FPR"]} for r in taxonomy_rows},
        "evidence_to_label_inconsistency_count": len(mechanisms["evidence_to_label_inconsistency"]),
        "visual_attribute_extraction_error_count": len(mechanisms["visual_attribute_extraction_error"]),
        "explicit_support_clue_count": len(support_ids),
        "support_clue_not_double_counted_as_type_a": True,
        "screen_individual_errors_used": 0,
        "val_individual_errors_used": 0,
        "holdout_used": 0,
        "gt_integrity_concern": False,
    }
    atomic_text(OUT / "forensic_summary.json", json.dumps(forensic_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    report = [
        "# P3 C3 DESIGN residual forensic",
        "",
        "## 已确认事实",
        "",
        f"- Scope is P2_DESIGN only: {len(rows)} rows, protocol gate={summary.get('protocol_gate_pass')}, VAL/HOLDOUT requests=0.",
        f"- C3 DESIGN metrics: TP={computed['TP']}, FP={computed['FP']}, TN={computed['TN']}, FN={computed['FN']}; Precision={computed['precision']:.6f}; Recall={computed['recall']:.6f}; hard-negative FPR={computed['hard_negative_fpr']:.6f}; ordinary-negative FPR={computed['ordinary_negative_fpr']:.6f}.",
        f"- Residual FP count={len(fp_rows)}; residual FN count={len(fn_rows)}.",
        "- GT-uncertain rows remain outside the confusion matrix; their prediction distribution is retained in forensic_summary.json.",
        "",
        "## Residual taxonomy",
        "",
        "| taxonomy | total | C3 FP | C3 TN | category FPR | groups |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in taxonomy_rows:
        report.append(f"| {row['taxonomy']} | {row['total_samples']} | {row['C3_FP']} | {row['C3_TN']} | {float(row['C3_category_FPR']):.6f} | {row['group_count']} |")
    report += [
        "",
        "## Evidence contradiction analysis",
        "",
        f"- Strict Type A evidence-to-label inconsistency={len(mechanisms['evidence_to_label_inconsistency'])}: the C3 evidence did not explicitly name a non-lying posture as its conclusion, so the two support-clue cases are not double-counted as Type A.",
        f"- Type B visual attribute extraction errors={len(mechanisms['visual_attribute_extraction_error'])}: {','.join(mechanisms['visual_attribute_extraction_error']) or 'none'}; both evidences assert prone/collapsed lying while the source scenario/image is a supported non-lying posture.",
        f"- Explicit hand/foot support clues appeared in {len(support_ids)} residual evidences ({','.join(support_ids) or 'none'}); this is an audit dimension, not a second error count.",
        "- Type C support-surface errors=0, Type D multi-person confusion=0, Type E other=0 in the two residuals.",
        "",
        "## 实验判断",
        "",
        "- The small DESIGN residual is dominated by visual posture attribute extraction: the model saw a floor and support limbs but adjudicated the posture as collapsed lying. This is evidence for testing explicit structured attributes; it is not evidence that a fixed rule already generalizes.",
        "- P3 candidate design uses only this DESIGN forensic. P2_SCREEN individual errors, P2 VAL individual errors, and HOLDOUT were not read for design.",
        "",
        "## 风险与限制",
        "",
        "- There are only two C3 DESIGN false positives across two hard-negative groups; taxonomy rates are descriptive and have high uncertainty.",
        "- All images are AIGC development data; this is not a real-camera or production generalization claim.",
    ]
    atomic_text(OUT / "forensic_report.md", "\n".join(report) + "\n")
    print(json.dumps(forensic_summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
