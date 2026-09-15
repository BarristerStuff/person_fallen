#!/usr/bin/env python3
"""Render the four required P3 reports from frozen/generated artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P3 = ROOT / "07_p3_structured_hard_negative_refinement"
REPORTS = ROOT / "reports"
REFERENCE_LATENCY = 1.852084


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def f(value, digits: int = 6) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def main() -> None:
    pre = load_json(P3 / "00_preflight/dataset_validator.json")
    identity = load_json(P3 / "00_preflight/model_identity.json")
    inventory = load_json(P3 / "00_preflight/source_hash_inventory.json")
    forensic = load_json(P3 / "02_design_forensics/forensic_summary.json")
    design_summary = load_json(P3 / "01_c3_design_baseline/summary.json")
    canary = load_json(P3 / "04_canary/summary.json")
    decision = load_json(P3 / "05_screen/winner_decision.json")
    runtime = load_json(P3 / "05_screen/runtime_latency_summary.json")
    consistency = load_json(P3 / "05_screen/structured_consistency_audit.json")
    verification = load_json(P3 / "05_screen/result_verification.json")
    freeze = load_json(P3 / "03_candidates/candidate_freeze.json")
    tax = load_csv(P3 / "05_screen/taxonomy_comparison.csv")
    groups = load_csv(P3 / "05_screen/group_metrics.csv")
    variants = {row["candidate"]: row for row in load_csv(P3 / "05_screen/comparison.csv")}
    direct = load_json(P3 / "05_screen/S1_DIRECT/summary.json")
    rule = load_json(P3 / "05_screen/S1_RULE/summary.json")
    c3_screen = load_json(P3 / "05_screen/C3_BASELINE/summary.json")

    model = identity.get("matching_models", [{}])[0]
    c3m = forensic["c3_design_metrics"]
    design_tax = load_csv(P3 / "02_design_forensics/residual_taxonomy.csv")
    patterns = load_csv(P3 / "02_design_forensics/evidence_error_patterns.csv")
    type_a = forensic["evidence_to_label_inconsistency_count"]
    type_b = forensic["visual_attribute_extraction_error_count"]
    support = forensic["explicit_support_clue_count"]
    screenm = variants["S1_DIRECT"]
    paired = decision["paired_summary"]

    # 21: C3 DESIGN forensic
    lines = [
        "# 21 — P3 C3 DESIGN forensic",
        "",
        "## 已确认事实",
        "",
        f"- Dataset gate before inference: status={pre.get('status')}, errors={pre.get('error_count')}, full_hash_check={pre.get('full_hash_check')}, warnings={pre.get('warning_count')}; formal dataset was not re-ingested or edited.",
        f"- C3 was newly requested on the complete P2_DESIGN manifest: 190 unique DEV images, manifest SHA `{inventory['files']['p2_design_manifest']['sha256']}`, VAL/HOLDOUT requests=0.",
        f"- Protocol gate: HTTP={design_summary['protocol']['http_success_rate']}, response_nonempty={design_summary['protocol']['response_nonempty_rate']}, JSON={design_summary['protocol']['json_parse_success_rate']}, schema={design_summary['protocol']['schema_success_rate']}, canonical={design_summary['protocol']['canonical_prediction_success_rate']}; thinking_present={design_summary['protocol']['thinking_present_rate']}.",
        f"- C3 DESIGN binary metrics (GT uncertain excluded): TP={c3m['TP']}, FP={c3m['FP']}, TN={c3m['TN']}, FN={c3m['FN']}; Precision={f(c3m['precision'])}, Recall={f(c3m['recall'])}, F1={f(c3m['f1'])}, Accuracy={f(c3m['accuracy'])}, ordinary-negative FPR={f(c3m['ordinary_negative_fpr'])}, hard-negative FPR={f(c3m['hard_negative_fpr'])}, model-uncertain rate={f(c3m['model_uncertain_rate'])}.",
        f"- C3 residual FP={forensic['c3_design_fp_count']}; residual FN={forensic['c3_design_fn_count']}. GT-uncertain prediction distribution={c3m['gt_uncertain_prediction_distribution']}.",
        "",
        "## Residual taxonomy",
        "",
        "| taxonomy | total | C3 FP | C3 TN | category FPR | groups |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in design_tax:
        lines.append(f"| {row['taxonomy']} | {row['total_samples']} | {row['C3_FP']} | {row['C3_TN']} | {f(float(row['C3_category_FPR']))} | {row['group_count']} |")
    lines += [
        "",
        "## Evidence-to-label versus visual-attribute analysis",
        "",
        f"- Strict Type A evidence-to-label inconsistency={type_a}: no residual evidence explicitly concluded a named non-lying posture while retaining `person_fallen=positive`.",
        f"- Type B visual attribute extraction error={type_b}: the two residuals `{','.join([r['media_id'] for r in load_csv(P3 / '02_design_forensics/c3_false_positives.csv')])}` describe prone/collapsed lying although their source scenarios/images are supported kneeling or push-up/plank postures.",
        f"- An explicit hand/foot support clue appears in {support} residual evidences. It is retained as a separate audit dimension and is not double-counted as strict Type A.",
        "- Type C support-surface error=0; Type D multi-person confusion=0; Type E other=0.",
        "",
        "## 实验判断",
        "",
        "- The complete DESIGN residual points to visual posture-attribute extraction as the observed C3 failure mechanism, with no C3 positive FN. This supports testing explicit structured fields, but the sample is only two residuals and cannot establish generalization.",
        "- Candidate design source is DESIGN-only. P2 SCREEN individual errors, P2 VAL individual errors, and HOLDOUT were not used before candidate freeze.",
        "",
        "## 风险与限制",
        "",
        "- All development evidence is AIGC; taxonomy is prompt/scenario metadata plus qualitative inspection of the two DESIGN residuals, not real-camera evidence.",
        "- C3 DESIGN warm P95 is `" + f(design_summary['protocol']['latency_seconds']['p95']) + "s`; this stage does not solve the historical P2L load anomaly.",
    ]
    write(REPORTS / "21_p3_c3_design_forensics.md", "\n".join(lines) + "\n")

    # 22: screening table
    lines = [
        "# 22 — P3 structured candidate screening",
        "",
        "## 已确认事实",
        "",
        "- SCREEN is adaptive development data reused from P2; `P3_SCREEN_IS_PRISTINE=false`. Candidate freeze and independent verifier passed before the new S1 SCREEN stream.",
        "- C3 SCREEN is a zero-request reuse with independent metric recomputation; S1_DIRECT and S1_RULE are two offline projections of one S1_STRUCTURED response stream.",
        "- Structured canary: 12/12 HTTP, response-nonempty, JSON, schema, enum/canonical success; `thinking_present=0%`; structured conflict=0/12.",
        "",
        "## Candidate metrics",
        "",
        "| candidate | TP | FP | TN | FN | Precision | Recall | F1 | Accuracy | ordinary FPR | hard-negative FPR | uncertain rate | conflict rate | P50 | P95 | protocol | decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for name in ["C3_BASELINE", "S1_DIRECT", "S1_RULE"]:
        row = variants[name]
        lines.append("| " + " | ".join([
            name, row["TP"], row["FP"], row["TN"], row["FN"], f(float(row["precision"])), f(float(row["recall"])), f(float(row["f1"])), f(float(row["accuracy"])), f(float(row["ordinary_negative_fpr"])), f(float(row["hard_negative_fpr"])), f(float(row["model_uncertain_rate"])), f(float(row["structured_conflict_rate"])), f(float(row["p50"])), f(float(row["p95"])), str(row["protocol_gate"]), row["decision"],
        ]) + " |")
    lines += [
        "| OPTIONAL_S2 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | not created | not run |",
        "",
        "## Paired and taxonomy comparison",
        "",
        f"- S1_DIRECT and S1_RULE: `direct_wrong_rule_correct={decision['direct_wrong_rule_correct']}`, `direct_correct_rule_wrong={decision['direct_correct_rule_wrong']}`, direct/rule disagreement={consistency['direct_rule_disagreement_count']}; the frozen rule produced no change on this screen.",
        f"- C3 FP → S1_DIRECT TN={paired['S1_DIRECT'].get('C3_FP_to_candidate_TN', 0)}, C3 FP → uncertain={paired['S1_DIRECT'].get('C3_FP_to_candidate_uncertain', 0)}, C3 TN → S1_DIRECT FP={paired['S1_DIRECT'].get('C3_TN_to_candidate_FP', 0)}, C3 TP → S1_DIRECT FN={paired['S1_DIRECT'].get('C3_TP_to_candidate_FN', 0)}.",
        "",
        "| taxonomy | total hard negatives | groups | C3 errors | S1_DIRECT errors | S1_RULE errors | C3 FPR | S1_DIRECT FPR | S1_RULE FPR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in tax:
        lines.append(f"| {row['taxonomy']} | {row['total_hard_negative']} | {row['group_count']} | {row['C3_error_count']} | {row['S1_DIRECT_error_count']} | {row['S1_RULE_error_count']} | {f(float(row['C3_FPR']))} | {f(float(row['S1_DIRECT_FPR']))} | {f(float(row['S1_RULE_FPR']))} |")
    lines += [
        "",
        f"- Group-level hard-negative error: C3 `{decision['group_summary']['C3_groups_with_FP']}/{decision['group_summary']['hard_negative_group_count']}` groups (`{f(decision['group_summary']['C3_group_level_hard_negative_error_rate'])}`); S1_DIRECT `{decision['group_summary']['S1_DIRECT_groups_with_FP']}/{decision['group_summary']['hard_negative_group_count']}` (`{f(decision['group_summary']['S1_DIRECT_group_level_hard_negative_error_rate'])}`).",
        "",
        "## 实验判断",
        "",
        "- S1 preserved positive recall and ordinary-negative FPR but substantially worsened hard-negative errors. The structured rule did not rescue any C3 error and created no direct/rule separation on this screen.",
        "- `P3_STRUCTURED_EVIDENCE_RELIABILITY` is protocol/consistency-pass (100% schema, 0 contradictions) but semantic screen generalization is inadequate for advancement.",
        "",
        "## 风险与限制",
        "",
        "- SCREEN is not pristine and must not be presented as an independent validation estimate. No VAL rerun was performed.",
        "- The 0% model-uncertain rate means the observed FP increase is not hidden abstention behavior.",
    ]
    write(REPORTS / "22_p3_structured_candidate_screening.md", "\n".join(lines) + "\n")

    # 23: winner report
    lines = [
        "# 23 — P3 winner report",
        "",
        "## 已确认事实",
        "",
        "- Candidate advancement gate: protocol=100%, positive recall≥0.95, ordinary-negative FPR=0, hard-negative FPR≤0.075. Neither S1_DIRECT nor S1_RULE qualifies because hard-negative FPR is 0.50 (20/40).",
        f"- Winner decision is `NONE`; `P3_STATUS=SCREENING_COMPLETE_NO_WINNER`. C3 remains the historical semantic reference but is not a P3 winner and still misses the project reference quality thresholds.",
        f"- Quality gate: P3 reference quality={decision['p3_reference_quality_pass']}; runtime gate={decision['p3_runtime_gate']}; runtime anomaly detected={decision.get('p3_runtime_anomaly_detected')}.",
        "",
        "## Candidate comparison",
        "",
        f"- S1_DIRECT: TP/FP/TN/FN={screenm['TP']}/{screenm['FP']}/{screenm['TN']}/{screenm['FN']}; Precision={f(float(screenm['precision']))}; Recall={f(float(screenm['recall']))}; F1={f(float(screenm['f1']))}; hard-negative FPR={f(float(screenm['hard_negative_fpr']))}; P95={f(float(screenm['p95']))}s.",
        f"- S1_RULE: identical metrics and latency because it is the same response stream and the fixed rule made no changes.",
        f"- Relative to C3, S1_DIRECT rescued FP→TN={paired['S1_DIRECT'].get('C3_FP_to_candidate_TN', 0)}, created C3 TN→FP={paired['S1_DIRECT'].get('C3_TN_to_candidate_FP', 0)}, and created C3 TP→FN={paired['S1_DIRECT'].get('C3_TP_to_candidate_FN', 0)}; FP→uncertain={paired['S1_DIRECT'].get('C3_FP_to_candidate_uncertain', 0)}.",
        "",
        "## 实验判断",
        "",
        "- There is no defensible unique P3 winner. Selecting S1 would turn a protocol-successful structured output into a materially worse classifier; selecting a threshold or rule after seeing SCREEN would violate the freeze.",
        "- The structured fields are internally consistent on the measured rows, but their visual attribute values frequently reproduce a lying interpretation for screen hard negatives; this is a semantic failure, not a parser failure.",
        "",
        "## 风险与限制",
        "",
        "- S1 SCREEN observed P95 is `" + f(direct['latency_seconds']['observed_p95']) + "s` versus the `" + f(REFERENCE_LATENCY) + "s` reference; load-duration >5s occurred " + str(runtime['S1_STRUCTURED']['load_duration_gt_5s_count']) + " times with longest sustained run " + str(runtime['S1_STRUCTURED']['longest_sustained_load_gt_5s']) + ". This is a runtime observation, not proof that Prompt text caused the load anomaly.",
        "- No winner freeze is created because the advancement gate failed; `HOLDOUT` remains sealed.",
    ]
    write(REPORTS / "23_p3_winner_report.md", "\n".join(lines) + "\n")

    # 24: final report
    status_block = """PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P0_STATUS=COMPLETE_PROTOCOL_FAILURE

P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR
P1A_DEV_MEASUREMENT=VALID

P1R_STATUS=COMPLETE
P1R_VALID_RECOVERY_BASELINE=true

P2_STATUS=COMPLETE
P2_WINNER=C3
P2_REFERENCE_THRESHOLDS_PASS=false

P2L_STATUS=COMPLETE
P2L_ROOT_CAUSE=UNRESOLVED_LOAD_DURATION_RUNTIME_CAUSE

P3_NAME=P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT
P3_STATUS=SCREENING_COMPLETE_NO_WINNER
P3_DESIGN_SOURCE=P2_DESIGN
P3_SCREEN_SOURCE=P2_SCREEN
P3_SCREEN_IS_PRISTINE=false
P3_WINNER=NONE
P3_REFERENCE_QUALITY_PASS=false
P3_RUNTIME_GATE=FAIL
P3_HOLDOUT_READY_QUALITY=false
P3_HOLDOUT_READY_RUNTIME=false
P3_HOLDOUT_READY=false
P3_NEW_VAL_REQUESTS=0
P3_HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false"""
    lines = [
        "# 24 — P3 Structured Hard-Negative Refinement final report",
        "",
        "## 顶部状态块",
        "",
        "```text\n" + status_block + "\n```",
        "",
        "## 已确认事实",
        "",
        f"- Formal validator final preflight state: `status={pre.get('status')}`, `error_count={pre.get('error_count')}`, `full_hash_check={pre.get('full_hash_check')}`, `warning_count={pre.get('warning_count')}`, media/labels={pre.get('media_count')}/{pre.get('label_count')}. Warnings are the pre-existing 387 historical warnings; no dataset ingest/GT/split mutation occurred.",
        f"- Ollama version={identity.get('version', {}).get('json', {}).get('version')}; model={model.get('name')}; digest=`{model.get('digest')}`; endpoint=`http://192.168.20.62:11434`.",
        f"- C3 prompt SHA=`{inventory['files']['c3_prompt']['sha256']}`; P2 winner freeze SHA=`{inventory['files']['p2_winner_freeze']['sha256']}`; P3 candidate freeze SHA=`{sha(P3 / '03_candidates/candidate_freeze.json')}`; P3 config SHA=`{sha(P3 / '03_candidates/p3_request_config.json')}`; durable runner SHA=`{sha(ROOT / 'tools/p3_inference_runner.py')}`; S1 shared launcher SHA=`{sha(ROOT / 'tools/p3_s1_shared_runner.py')}`.",
        f"- New DEV requests={decision['new_dev_requests']} (C3 DESIGN 190 + structured canary 12 + S1 SCREEN 120); new VAL requests={decision['new_val_requests']}; HOLDOUT requests={decision['holdout_requests']}; HOLDOUT consumed={decision['holdout_consumed']}.",
        f"- Structured canary 12/12: HTTP={canary['protocol']['http_success_rate']}, response_nonempty={canary['protocol']['response_nonempty_rate']}, JSON={canary['protocol']['json_parse_success_rate']}, schema={canary['protocol']['schema_success_rate']}, canonical={canary['protocol']['canonical_prediction_success_rate']}; thinking_present={canary['protocol']['thinking_present_rate']}.",
        f"- C3 DESIGN: TP/FP/TN/FN={c3m['TP']}/{c3m['FP']}/{c3m['TN']}/{c3m['FN']}; Precision={f(c3m['precision'])}; Recall={f(c3m['recall'])}; hard-negative FPR={f(c3m['hard_negative_fpr'])}; residual FP={forensic['c3_design_fp_count']}; Type-A={type_a}; Type-B={type_b}.",
        f"- P2 C3 SCREEN baseline (reused, no new request): TP/FP/TN/FN={c3_screen['metrics_direct']['TP']}/{c3_screen['metrics_direct']['FP']}/{c3_screen['metrics_direct']['TN']}/{c3_screen['metrics_direct']['FN']}; Precision={f(c3_screen['metrics_direct']['precision'])}; Recall={f(c3_screen['metrics_direct']['recall'])}; hard-negative FPR={f(c3_screen['metrics_direct']['hard_negative_fpr'])}; P50/P95={f(c3_screen['protocol']['latency_seconds']['p50'])}/{f(c3_screen['protocol']['latency_seconds']['p95'])}s.",
        f"- S1_DIRECT and S1_RULE (same 120 response stream): TP/FP/TN/FN={screenm['TP']}/{screenm['FP']}/{screenm['TN']}/{screenm['FN']}; Precision={f(float(screenm['precision']))}; Recall={f(float(screenm['recall']))}; F1={f(float(screenm['f1']))}; Accuracy={f(float(screenm['accuracy']))}; ordinary-negative FPR={f(float(screenm['ordinary_negative_fpr']))}; hard-negative FPR={f(float(screenm['hard_negative_fpr']))}; model-uncertain rate={f(float(screenm['model_uncertain_rate']))}; P50/P95={f(float(screenm['p50']))}/{f(float(screenm['p95']))}s.",
        f"- Structured consistency: conflicts={consistency['structured_conflict_count']}/{consistency['row_count']} ({f(consistency['structured_conflict_count']/consistency['row_count'])}); direct_wrong_rule_correct={decision['direct_wrong_rule_correct']}; direct_correct_rule_wrong={decision['direct_correct_rule_wrong']}.",
        f"- Independent result verifier: `{verification['verification_result']}`, metric_recompute_match={verification['metric_recompute_match']}, candidate freeze unchanged={verification['checks']['candidate_freeze_unchanged_final']}.",
        "",
        "## 实验判断",
        "",
        "- S1 does not meet the P3 advancement gate: protocol is valid and positive recall is preserved, but 20/40 hard negatives are false alerts (FPR 0.50 > 0.075), versus C3 5/40 (0.125). Both S1_DIRECT and S1_RULE therefore fail; no winner is selected.",
        "- The deterministic rule did not improve S1 on this screen because the model commonly emitted `torso_pelvis_state=lying` and `active_nonlying_support=no` for these hard negatives; this is consistent with semantic visual-attribute extraction failure, not a response-protocol failure.",
        "- P3 does not rerun the already-exposed VAL: `VAL_INDIVIDUAL_ERRORS_USED_FOR_P3_DESIGN=false`, `P3_NEW_VAL_REQUESTS=0`. SCREEN is explicitly adaptive/non-pristine and is not a validation claim.",
        "",
        "## 风险与限制",
        "",
        f"- Runtime gate is FAIL: S1 observed client P95={f(direct['latency_seconds']['observed_p95'])}s > reference {f(REFERENCE_LATENCY)}s; load-duration P95={f(runtime['S1_STRUCTURED']['component_p95'].get('load_duration'))}s, >5s count={runtime['S1_STRUCTURED']['load_duration_gt_5s_count']}, longest sustained run={runtime['S1_STRUCTURED']['longest_sustained_load_gt_5s']}. Remote GPU/VRAM/runner telemetry remains unavailable as recorded by P2L; do not attribute causality to Prompt.",
        "- The first S1 canary CLI alias attempt failed before any request because the physical stream name and registry view name differed. It is preserved as a local orchestration note; the subsequent compatibility launcher only aliases `S1_DIRECT` to the frozen S1 shared stream and records its SHA. Main runner/config/payload hashes remain bound and no retry was made for the failed pre-request attempt.",
        "- Data are AIGC development images. Results cannot be called real-camera, robot-production, temporal-video, or deployment accuracy.",
        "",
        "## 下一阶段建议",
        "",
        "1. Do not create a P3 winner freeze and do not consume HOLDOUT. Keep `P3_HOLDOUT_READY=false` and wait for separate authorization.",
        "2. Because structured attributes were protocol-valid but semantically poor on the reused SCREEN, prioritize genuinely new lineage-isolated hard-negative DEV data (especially sitting-on-floor, supported exercise, and crawling/kneeling boundaries) before further Prompt-only iteration.",
        "3. If a future authorized experiment targets visual extraction rather than data coverage, test higher resolution, person ROI/crop, or pose assistance as separate new experiment IDs; do not combine them into this stage.",
        "4. If runtime SLA remains relevant, perform a separately authorized read-only runtime confirmation for the unresolved load-duration anomaly before any production inference claim.",
        "",
        "## 关键绝对路径",
        "",
        f"- P3 workspace: `{P3}`",
        f"- Preflight: `{P3 / '00_preflight'}`",
        f"- C3 DESIGN: `{P3 / '01_c3_design_baseline'}`",
        f"- DESIGN forensic: `{P3 / '02_design_forensics'}`",
        f"- Candidate freeze/attestation: `{P3 / '03_candidates'}`",
        f"- Structured canary: `{P3 / '04_canary'}`",
        f"- SCREEN/analysis/verifier: `{P3 / '05_screen'}`",
        f"- Required reports: `{REPORTS / '21_p3_c3_design_forensics.md'}`, `{REPORTS / '22_p3_structured_candidate_screening.md'}`, `{REPORTS / '23_p3_winner_report.md'}`, `{REPORTS / '24_p3_final_report.md'}`",
    ]
    write(REPORTS / "24_p3_final_report.md", "\n".join(lines) + "\n")
    print(json.dumps({"reports_written": ["21_p3_c3_design_forensics.md", "22_p3_structured_candidate_screening.md", "23_p3_winner_report.md", "24_p3_final_report.md"], "winner": decision["winner"], "status": "SCREENING_COMPLETE_NO_WINNER"}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
