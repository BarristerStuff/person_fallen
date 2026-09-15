# 24 — P3 Structured Hard-Negative Refinement final report

## 顶部状态块

```text
PROJECT=net_vlm
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
OLLAMA_SERVICE_MODIFIED=false
```

## 已确认事实

- Formal validator final preflight state: `status=valid`, `error_count=0`, `full_hash_check=True`, `warning_count=387`, media/labels=4201/4201. Warnings are the pre-existing 387 historical warnings; no dataset ingest/GT/split mutation occurred.
- Ollama version=0.23.2; model=qwen3.5:4b; digest=`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`; endpoint=`http://192.168.20.62:11434`.
- C3 prompt SHA=`685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e`; P2 winner freeze SHA=`ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0`; P3 candidate freeze SHA=`b67d3016eade8f33a8b167ff03aaacc0061f96b3d78b7a13518a27f8276542df`; P3 config SHA=`102c1e82706a78aacbb8e6e07f41d6b1d0233e4c72954a7d3ab46d07529a5779`; durable runner SHA=`4e103b1e6b42418315f6b572b3b53618eb66ba952f32f02157907e3b4122d22b`; S1 shared launcher SHA=`6489f2828cf1bc1bdfb497e07f230836c4b5dba11a434edea2e49a66f9df0399`.
- New DEV requests=322 (C3 DESIGN 190 + structured canary 12 + S1 SCREEN 120); new VAL requests=0; HOLDOUT requests=0; HOLDOUT consumed=False.
- Structured canary 12/12: HTTP=1.0, response_nonempty=1.0, JSON=1.0, schema=1.0, canonical=1.0; thinking_present=0.0.
- C3 DESIGN: TP/FP/TN/FN=70/2/108/0; Precision=0.972222; Recall=1.000000; hard-negative FPR=0.028571; residual FP=2; Type-A=0; Type-B=2.
- P2 C3 SCREEN baseline (reused, no new request): TP/FP/TN/FN=50/5/55/0; Precision=0.909091; Recall=1.000000; hard-negative FPR=0.125000; P50/P95=1.580759/1.815010s.
- S1_DIRECT and S1_RULE (same 120 response stream): TP/FP/TN/FN=50/20/40/0; Precision=0.714286; Recall=1.000000; F1=0.833333; Accuracy=0.818182; ordinary-negative FPR=0.000000; hard-negative FPR=0.500000; model-uncertain rate=0.000000; P50/P95=2.134880/9.601210s.
- Structured consistency: conflicts=0/120 (0.000000); direct_wrong_rule_correct=0; direct_correct_rule_wrong=0.
- Independent result verifier: `PASS`, metric_recompute_match=True, candidate freeze unchanged=True.

## 实验判断

- S1 does not meet the P3 advancement gate: protocol is valid and positive recall is preserved, but 20/40 hard negatives are false alerts (FPR 0.50 > 0.075), versus C3 5/40 (0.125). Both S1_DIRECT and S1_RULE therefore fail; no winner is selected.
- The deterministic rule did not improve S1 on this screen because the model commonly emitted `torso_pelvis_state=lying` and `active_nonlying_support=no` for these hard negatives; this is consistent with semantic visual-attribute extraction failure, not a response-protocol failure.
- P3 does not rerun the already-exposed VAL: `VAL_INDIVIDUAL_ERRORS_USED_FOR_P3_DESIGN=false`, `P3_NEW_VAL_REQUESTS=0`. SCREEN is explicitly adaptive/non-pristine and is not a validation claim.

## 风险与限制

- Runtime gate is FAIL: S1 observed client P95=9.601210s > reference 1.852084s; load-duration P95=7.049979s, >5s count=7, longest sustained run=3. Remote GPU/VRAM/runner telemetry remains unavailable as recorded by P2L; do not attribute causality to Prompt.
- The first S1 canary CLI alias attempt failed before any request because the physical stream name and registry view name differed. It is preserved as a local orchestration note; the subsequent compatibility launcher only aliases `S1_DIRECT` to the frozen S1 shared stream and records its SHA. Main runner/config/payload hashes remain bound and no retry was made for the failed pre-request attempt.
- Data are AIGC development images. Results cannot be called real-camera, robot-production, temporal-video, or deployment accuracy.

## 下一阶段建议

1. Do not create a P3 winner freeze and do not consume HOLDOUT. Keep `P3_HOLDOUT_READY=false` and wait for separate authorization.
2. Because structured attributes were protocol-valid but semantically poor on the reused SCREEN, prioritize genuinely new lineage-isolated hard-negative DEV data (especially sitting-on-floor, supported exercise, and crawling/kneeling boundaries) before further Prompt-only iteration.
3. If a future authorized experiment targets visual extraction rather than data coverage, test higher resolution, person ROI/crop, or pose assistance as separate new experiment IDs; do not combine them into this stage.
4. If runtime SLA remains relevant, perform a separately authorized read-only runtime confirmation for the unresolved load-duration anomaly before any production inference claim.

## 关键绝对路径

- P3 workspace: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement`
- Preflight: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement/00_preflight`
- C3 DESIGN: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement/01_c3_design_baseline`
- DESIGN forensic: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement/02_design_forensics`
- Candidate freeze/attestation: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement/03_candidates`
- Structured canary: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement/04_canary`
- SCREEN/analysis/verifier: `/home/yanbo/net_vlm_person_fallen_v2_optimization/07_p3_structured_hard_negative_refinement/05_screen`
- Required reports: `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/21_p3_c3_design_forensics.md`, `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/22_p3_structured_candidate_screening.md`, `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/23_p3_winner_report.md`, `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/24_p3_final_report.md`
