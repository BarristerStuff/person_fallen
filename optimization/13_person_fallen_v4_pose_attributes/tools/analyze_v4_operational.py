#!/usr/bin/env python3
"""Create a zero-inference operational analysis from the sealed v4 full-DEV run."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from common import ROOT, atomic_json, atomic_text, load_csv, load_json, sha256


RUN = ROOT / "eval/runs/dev_V4-A0-FULL-CROP-436"
SUMMARY = RUN / "summary.json"
PREDICTIONS = RUN / "predictions.csv"
COMPLETION = RUN / "COMPLETION_LOCK.json"
REPORT_JSON = ROOT / "reports/v4_full_dev_operational_analysis.json"
REPORT_MD = ROOT / "reports/v4_full_dev_operational_analysis.md"

EXPECTED_HASHES = {
    SUMMARY: "ef4e40a45bcb2953a03df01d1ab7d1f0fc35a87f74720c8c678292fb7bdebb01",
    PREDICTIONS: "4a46072c5a4e2c94c9844e16387e059870b43bfbfc0d421282a0f90cd43ce589",
    COMPLETION: "5edfc17e04bbf1835a5310e2a9960810c22953f5a773694ce3df366eba0123dd",
}


def counts(rows: list[dict]) -> dict[str, int]:
    return dict(Counter(row["frame_decision"] for row in rows))


def main() -> int:
    for path, expected in EXPECTED_HASHES.items():
        if sha256(path) != expected:
            raise RuntimeError(f"sealed run SHA mismatch: {path}")
    summary = load_json(SUMMARY)
    completion = load_json(COMPLETION)
    rows = load_csv(PREDICTIONS)
    if summary.get("status") != "COMPLETE" or completion.get("status") != "COMPLETE" or len(rows) != 436:
        raise RuntimeError("sealed full DEV run is incomplete")

    lying = [row for row in rows if row["expected_v4_outcome"] == "ALERT_GROUND_LYING"]
    attention = [row for row in rows if row["expected_v4_outcome"] == "ATTENTION_NEAR_GROUND"]
    negatives = [row for row in rows if row["ground_truth"] == "negative"]
    floor = [row for row in rows if row["taxonomy"] == "floor_sitting"]
    source_uncertain = [row for row in rows if row["ground_truth"] == "uncertain"]
    crawling = [row for row in attention if row["taxonomy"].startswith("crawling")]
    pushup = [row for row in attention if row["taxonomy"] == "pushup_plank"]

    lying_alert = sum(row["frame_decision"] == "ALERT_GROUND_LYING" for row in lying)
    lying_recheck = sum(row["frame_decision"] == "RECHECK_VISUAL_UNCERTAIN" for row in lying)
    lying_clear = sum(row["frame_decision"] == "NO_ALERT_NORMAL_POSE" for row in lying)
    negative_alarm = sum(row["frame_decision"] == "ALERT_GROUND_LYING" for row in negatives)
    floor_alarm = sum(row["frame_decision"] == "ALERT_GROUND_LYING" for row in floor)

    ground_lying_gate_checks = {
        "lying_immediate_alert_recall_ge_0_95": lying_alert / len(lying) >= 0.95,
        "lying_silently_cleared_eq_0": lying_clear == 0,
        "negative_immediate_alarm_fpr_eq_0": negative_alarm == 0,
        "floor_sitting_immediate_alarm_fpr_eq_0": floor_alarm == 0,
        "strict_json_success_eq_1": summary["metrics"]["strict_json_success"] == 1.0,
    }
    report = {
        "status": "COMPLETE_ZERO_INFERENCE_ANALYSIS",
        "source_run": str(RUN),
        "source_summary_sha256": sha256(SUMMARY),
        "source_predictions_sha256": sha256(PREDICTIONS),
        "legacy_v3_binary_gate": "FAIL",
        "legacy_v3_binary_metrics": {
            key: summary["metrics"][key]
            for key in ("tp", "fp", "tn", "fn", "precision", "recall", "f1",
                        "hard_negative_fpr", "ordinary_negative_fpr")
        },
        "ground_lying_high_priority": {
            "expected_count": len(lying),
            "immediate_alert": lying_alert,
            "recheck": lying_recheck,
            "silently_cleared": lying_clear,
            "immediate_alert_recall": lying_alert / len(lying),
            "alert_or_recheck_safety_coverage": (lying_alert + lying_recheck) / len(lying),
            "negative_immediate_alarm_count": negative_alarm,
            "negative_immediate_alarm_fpr": negative_alarm / len(negatives),
            "gate_checks": ground_lying_gate_checks,
            "gate_pass": all(ground_lying_gate_checks.values()),
        },
        "floor_sitting": {
            "count": len(floor),
            "decisions": counts(floor),
            "immediate_alarm_count": floor_alarm,
            "immediate_alarm_fpr": floor_alarm / len(floor),
            "direct_clear_rate": sum(row["frame_decision"] == "NO_ALERT_NORMAL_POSE" for row in floor) / len(floor),
        },
        "attention_postures": {
            "all": {"count": len(attention), "decisions": counts(attention)},
            "pushup_plank": {"count": len(pushup), "decisions": counts(pushup)},
            "crawling": {"count": len(crawling), "decisions": counts(crawling)},
        },
        "source_uncertain": {"count": len(source_uncertain), "decisions": counts(source_uncertain)},
        "temporal_evaluation": {
            "status": "NOT_MEASURABLE_FROM_STILL_IMAGE_DEV",
            "state_machine_implemented": True,
            "unit_tests_passed": True,
            "fabricated_repeated_frames_used": False,
        },
        "interpretation": {
            "confirmed_fact": "The frozen candidate separates floor sitting from ground lying on this synthetic DEV lineage.",
            "remaining_model_limitation": "Crawling is frequently emitted as kneeling despite evidence text describing hands-and-knees support.",
            "semantic_decision_required": "Whether crawling must trigger attention is a business-definition choice and cannot be changed post hoc to make the v3 binary gate pass.",
            "production_claim_allowed": False,
        },
        "screen_requests": 0,
        "val_requests": 0,
        "holdout_requests": 0,
    }
    atomic_json(REPORT_JSON, report)

    binary = report["legacy_v3_binary_metrics"]
    high = report["ground_lying_high_priority"]
    md = f"""# person_fallen v4 full-DEV operational analysis

`ZERO_INFERENCE_ANALYSIS=true`

## Confirmed facts

- Frozen full DEV: 436 rows; no SCREEN, VAL, or Holdout access.
- Legacy v3 binary gate: **FAIL** only on Recall.
- Binary metrics: TP={binary['tp']}, FP={binary['fp']}, TN={binary['tn']}, FN={binary['fn']}, precision={binary['precision']:.4f}, recall={binary['recall']:.4f}, F1={binary['f1']:.4f}.
- Hard-negative FPR={binary['hard_negative_fpr']:.4f}; ordinary-negative FPR={binary['ordinary_negative_fpr']:.4f}.
- Floor sitting: 54/55 direct clear, 1/55 recheck, 0/55 immediate alarm.
- High-priority ground lying: {high['immediate_alert']}/{high['expected_count']} immediate alert, {high['recheck']} recheck, {high['silently_cleared']} silently cleared.
- High-priority immediate-alert recall={high['immediate_alert_recall']:.4f}; alert-or-recheck safety coverage={high['alert_or_recheck_safety_coverage']:.4f}.
- Negative immediate high-priority alarms={high['negative_immediate_alarm_count']}/{len(negatives)}.
- Push-up/plank decisions: {counts(pushup)}.
- Crawling decisions: {counts(crawling)}.

## Inference

The 4B model is sufficiently capable for the narrower robot-inspection question
"is a person clearly lying on the ground versus sitting/kneeling/standing?"
on this synthetic DEV lineage. The v3 binary Recall failure is dominated by
`crawling -> kneeling`, not by sitting-versus-lying confusion.

## Risks and boundary

This is prompt-derived synthetic DEV, not an independent or real-camera claim.
The temporal 2-of-3 policy is implemented and unit-tested, but this still-image
dataset cannot measure temporal performance. Removing crawling from required
attention would be a new business-definition decision; it must not be used to
rewrite v3 GT or retroactively turn this failed v3 binary gate into a pass.
"""
    atomic_text(REPORT_MD, md)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
