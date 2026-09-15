# person_fallen V2.0 — formal intake, P0/P1A/P1R history, P2 semantic optimization, and P2L runtime forensics

## Definition

Visible-state image event: real person clearly lying/prone/supine/side-lying/horizontally collapsed on ground or other clearly abnormal non-rest support is positive. Intentional ground lying is positive. Transition/cause/injury/consciousness is not required.

## Data and provenance

AIGC source batch: `batch_person-fallen-v2-camera1p5m`; 500 gpt-image-2 images with user-confirmed prompt/image alignment. GT is prompt-derived, never VLM-generated and not independent visual review. Counts: positive 200; negative 100; hard-negative 180; uncertain 20. Metadata has no provider seed (500 unknown).

## Formal dataset and freeze

Formal media IDs: `IMG_003702`–`IMG_004201` (500 media/500 labels, V2.0). Split counts: DEV 310 / VAL 100 / HOLDOUT 90; group-disjoint across 50 groups. `frozen_splits.csv` SHA-256 `16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a`; P0 prompt SHA-256 `b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4`. `FORMAL_SPLITS_CSV_UPDATED=false`; local frozen manifest is P0 source of truth.

## P0 outcome

P0 used `qwen3.5:4b`, direct LAN `192.168.20.62:11434`, full image letterbox to 448×336 JPEG q70 and concurrency 1. DEV+VAL requests=410; HOLDOUT=0 and unconsumed. HTTP=100%, but JSON/schema=0% because the server placed output in `thinking` while required `response` was empty. This is `COMPLETE_PROTOCOL_FAILURE`, so TP/FP/TN/FN and classification metrics are unavailable.

## P1A think=false-only protocol audit

P1A reused the P0 prompt byte-for-byte and all P0 request/preprocess conditions, adding only top-level `think=false`. Capability audit confirmed Ollama `0.23.2` and `qwen3.5:4b` digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.

The immutable 12-image DEV-only canary passed: HTTP/response-nonempty/JSON/schema/canonical success=100%, with `thinking_present=0%`; it therefore confirms that P1A restores the formal answer to `response` without any thinking fallback. DEV also passed its protocol gate on 310 unique images, reusing the 12 canary results with no duplicate requests. Its determinate results are TP=120, FP=29, TN=141, FN=0; Precision=0.805369; Recall=1.0; F1=0.892193; Accuracy=0.9; ordinary-negative FPR=0.0; hard-negative FPR=0.263636; P50/P95=1.453798s/1.610508s.

P1A is **not** a complete DEV-to-VAL classification baseline. Immediately before the one-shot VAL completion, the original DEV freeze artifact was found to declare a wrong DEV manifest SHA. The artifact is preserved, not overwritten. VAL was stopped after 10 confirmed completed requests; an eleventh was in flight and its completion cannot be established from a persisted log. Thus `P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR`, `P1A_VALID_CLASSIFICATION_BASELINE=false`, `HOLDOUT_REQUESTS=0`, and `HOLDOUT_CONSUMED=false`.

## P1R freeze-binding recovery and VAL recovery evaluation

`P1R_FREEZE_BINDING_RECOVERY` was created as a separate stage after preserving the P1A binding error. It did not modify any P0 or P1A record. P1R recorded the P1A declared/actual DEV-manifest mismatch, independently checked the actual P1A DEV entity sets (310 manifest/prediction/log entries, all equal, zero HOLDOUT), and froze a 100-item recovery VAL manifest with SHA-256 `f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762`. The independent pre-inference freeze verifier passed with all file hashes matching; execution-time freeze ID is `9aa6b1e9d0f87144633539850d6b30236fe5c50acb5368bd90961cd2ac3674a0`.

P1R retained P1A semantics exactly: the unchanged P0 prompt (`b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4`), `qwen3.5:4b`, `format=json`, top-level `think=false`, response-only parser, temperature 0, `num_ctx=8192`, `num_predict=256`, stream false, concurrency 1, and 448×336 letterbox/JPEG q70 preprocessing. Its config SHA-256 is `f15d4083ae7c52ccf668b75982aee98e35f24d28bf96fe1303e0d9885c94de8c`; frozen runner SHA-256 is `18e45f2693334baac80105ccbb9a094cd6781022e5243955e0b9ed8e61260eb5`.

P1R VAL ran 100 planned requests with a WAL/full-synchronous durable ledger: 100 `COMPLETED`, zero failed, zero unknown, zero HOLDOUT. HTTP/response-nonempty/JSON/schema/canonical success were all 100%; `thinking_present=0%`. The independent post-run result verifier passed with exact metric recomputation and marked `P1R_VALID_RECOVERY_BASELINE=true`.

P1R VAL results are TP=40, FP=11, TN=49, FN=0; Precision=0.784314; Recall=1.0; F1=0.879121; Accuracy=0.89; ordinary-negative FPR=0.0; hard-negative FPR=0.275; model-uncertain rate=0.0; P50/P95=1.478509s/1.650989s. Result hashes: predictions `7f221795f9a21febd47d5861ee58492dbef6eb00a1032ea240bc1c536de1e38b`, raw responses `d9be1890277f2e4798f1b4ab7ee63817667d1cae0c79aa86ecaccb82de878f97`, request log `e553985465791fd57d9e0ca8cc6960ff7481e7b66a4cc669b7fb9d190a994b34`, ledger `05fdba91477da465aee3e305edc4437f43279556ca2dccac9e6034586a1c54c0`.

P1R is a valid **recovery** baseline, not pristine validation: prior P1A VAL exposure is 10 confirmed requests plus one possible additional in-flight request. Therefore `P1R_VAL_IS_PRISTINE=false`. The P1R run did not use prior semantic error information to change prompt, parser, preprocessing, config, or threshold. A post-run verifier invocation rewrote only its timestamp, changing the current on-disk freeze JSON SHA to `15d7e30d43c39b305ab89ac7a9f2e91567a40b3ff86c6e2a9299f5e3994c27e0`; candidate fields and all inference/result artifacts remain unchanged. The verifier is now read-only for an existing freeze, and this artifact-history limitation is retained rather than backfilled.

## P2 hard-negative semantic optimization

`P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION` changed only Prompt text. Model identity (`qwen3.5:4b`, Ollama `0.23.2`, digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`), endpoint, `format=json`, top-level `think=false`, response-only parser, all generation options, 448×336 letterbox/JPEG q70 preprocessing, GT, event definition, and original split remained fixed.

The 31 DEV groups were internally frozen into 19 DESIGN groups / 190 images and 12 SCREEN groups / 120 images, with `CROSS_DESIGN_SCREEN_GROUPS=0`. DESIGN was the only source of individual forensic evidence. It contained 70 hard negatives and 7 P1A baseline false positives, all hard-negative; ordinary-negative FP remained 0. P2_SCREEN stayed blind until candidate freeze. The deterministic split hashes are DESIGN `f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1`, SCREEN `ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5`, internal split `a9edfb22fc0170ce774dfe5e6229bf776c8c272868b55c303e74ae629b153892`.

Three Prompt candidates were screened on the same 120 images. C1 did not improve over C0; C2 worsened hard-negative FPR; C3 was the only candidate satisfying protocol, positive recall, ordinary-negative FPR, latency, and minimum hard-negative-improvement gates. C3 SCREEN metrics were TP/FP/TN/FN `50/5/55/0`, Precision `0.909091`, Recall `1.0`, F1 `0.952381`, ordinary-negative FPR `0`, hard-negative FPR `0.125`, P95 `1.815010s`. It rescued 17 C0 false positives, created no new FP, preserved all 50 positive TPs, and created no FN.

C3 was frozen before P2 VAL. P2 ran the original 100-item recovery VAL once, with durable ledger `COMPLETED=100`, no failures/unknown states, and zero HOLDOUT. HTTP, response-nonempty, JSON, schema, and canonical success were all 100%; `thinking_present=0%`. Independent result verification passed with exact metric recomputation.

P2 VAL metrics were TP/FP/TN/FN `40/5/55/0`, Precision `0.888889`, Recall `1.0`, F1 `0.941176`, Accuracy `0.95`, ordinary-negative FPR `0`, hard-negative FPR `0.125`, model-uncertain rate `0`, P50/P95 `14.684316s/18.147252s`. Compared with P1R VAL (`40/11/49/0`), P2 rescued 6 baseline FP, created 0 new FP, preserved 40 TP, and created 0 FN.

P2 therefore completed a valid, protocol-complete winner evaluation but did not pass the reference quality thresholds (`Precision >=0.93`, `hard-negative FPR <=0.05`) or the `1.8520842s` latency gate. `P2_STATUS=COMPLETE`, `P2_VALIDATION_COMPLETE=true`, `P2_REFERENCE_THRESHOLDS_PASS=false`, and `P2_LATENCY_GATE=FAIL`. P2 VAL remains non-pristine because P1R had prior VAL exposure: `P2_VAL_IS_PRISTINE=false`.

`HOLDOUT_REQUESTS=0` and `HOLDOUT_CONSUMED=false` remain true. `P3_EXECUTED=false` and `PRODUCTION_CODE_MODIFIED=false` mean this P2 run did not write the production tree. A read-only completion probe found pre-existing user-owned dirty files under `/home/yanbo/net_vlm_yanboversion/vlm`; they were preserved. Do not automatically start P3; any new experiment must use a new ID and freeze, return to DEV design, and keep HOLDOUT sealed. This remains an AIGC-only evaluation and does not establish robot, real-camera, temporal-video, or production accuracy.

## P2L remote latency forensics

`P2L_REMOTE_LATENCY_FORENSICS` was a runtime-forensics stage, not a semantic P3. It preserved every P0/P1A/P1R/P2 artifact and did not re-ingest the formal dataset, modify GT/splits/Prompt/preprocess, run VAL again, or consume HOLDOUT. The final formal dataset validator remained `status=valid`, `error_count=0`, `full_hash_check=true`, `warning_count=387`, `media_count=4201`, and `label_count=4201`.

Capability audit and final direct endpoint checks observed Ollama `0.23.2`; `qwen3.5:4b` was present in `/api/tags` with digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`. Final `/api/ps` returned HTTP 200 with that digest loaded, `size_vram=6088300544`, and `context_length=8192`. P2L used the unchanged C3 Prompt SHA `685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e` and request config SHA `8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d`.

Historical raw forensics confirmed that P2 C3 SCREEN had 120/120 low-load requests with client P50/P95 `1.580912/1.814611s`, while P2 C3 VAL had 63/100 `load_duration>5s` requests with client P50/P95 `14.682363/18.144259s` and load P50/P95 `13.324700/16.756087s`. Automatic threshold-run analysis found `1–20 HIGH → 21 LOW → 22–64 HIGH → 65–100 LOW`; the longest sustained high window was 22–64 and recovery began at 65. Prompt-eval count was exactly 598 throughout; load duration was the primary historical component.

DEV-only controlled probes were A=24 fixed-image exact-C3 requests, B=24 fixed-image requests with only top-level `keep_alive="30m"`, and C=16 diverse DEV/P2_DESIGN images. All 64 formal requests had HTTP/response/JSON/schema/canonical success 100%, `thinking_present=0%`, and zero protocol failures. A had one first-request cold load (`load=6.985410339s`, client `8.285873s`); the remaining A requests and all B/C requests were below the 5-second load threshold. The current C3 warm aggregate (A low-load rows + C, 39 rows) had client P50/P95 `1.450764/1.796366s`, below the reference development limit `1.852084s`. Because the historical 43-request sustained anomaly did not recur, `P2L_ANOMALY_REPRODUCED=false`; the single cold-load observation is retained as evidence, not treated as a sustained reproduction.

The most supported runtime interpretation is `load_duration` dominated by a model residency/load-state transition (`H1_PARTIALLY_SUPPORTED`), not a confirmed daemon or hardware root cause. H2 GPU/VRAM contention and H3 runner lifecycle/scheduler remain unresolved because read-only SSH to `tiga@192.168.20.62` failed with `Permission denied (publickey,password)`; GPU utilization, VRAM time series, compute PID, Ollama PID/runner PID, systemd and journal evidence are unavailable. H4 request/image-dependent cost, H5 prompt/generation cost, and H6 client/network transport are not supported by the probe and raw component data; H7 other remote runtime anomaly remains unresolved. P2L therefore has `P2L_STATUS=COMPLETE`, but deliberately has no `P2L_WINNER` and does not change the semantic candidate `C3` or the P2 quality/latency gate failures.

The first runner invocation exposed a fixed-manifest expansion defect and completed one DEV request before correction. That evidence is preserved, not deleted or folded into formal Probe A, under `06_p2l_remote_latency_forensics/04_probe_A_exact_c3_attempt_001`; formal A/B/C remain 24/24/16. Including the preserved attempt, P2L made 65 new DEV requests, zero new VAL requests, and zero HOLDOUT requests. `HOLDOUT_CONSUMED=false`, `OLLAMA_SERVICE_MODIFIED=false`, `PRODUCTION_CODE_MODIFIED=false`, and `P3_EXECUTED=false` remain true. See [18_p2l_historical_latency_forensics.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/18_p2l_historical_latency_forensics.md), [19_p2l_controlled_dev_probes.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/19_p2l_controlled_dev_probes.md), and [20_p2l_final_report.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/20_p2l_final_report.md).
Because the sustained historical anomaly did not recur and the current exact-C3 warm P95 is below `1.852084s`, the next authorized stage may be `P3_HARD_NEGATIVE_REFINEMENT` (not executed here), while retaining the unresolved historical latency anomaly as a deployment risk. If runtime SLA is the immediate blocker, obtain read-only remote telemetry or register a separate DEV runtime validation before drawing stronger causal conclusions.

## P3 structured hard-negative refinement

`P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT` was executed as a new DEV-only stage and did not modify any P0/P1A/P1R/P2/P2L history, formal dataset, GT, frozen split, production tree, or Ollama service. The final read-only dataset validator remained `status=valid`, `error_count=0`, `full_hash_check=true`, `warning_count=387`, `media_count=4201`, and `label_count=4201`. Ollama remained `0.23.2`; `qwen3.5:4b` remained digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd` at `http://192.168.20.62:11434`.

The P2 C3 prompt was re-bound byte-for-byte (`685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e`) and the P2 winner freeze remained unchanged (`ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0`). P3 used `format=json`, top-level `think=false`, response-only parsing, temperature 0, `num_ctx=8192`, `num_predict=256`, concurrency 1, and 448×336 letterbox/JPEG q70. The P3 request config SHA is `102c1e82706a78aacbb8e6e07f41d6b1d0233e4c72954a7d3ab46d07529a5779`; the durable runner SHA is `4e103b1e6b42418315f6b572b3b53618eb66ba952f32f02157907e3b4122d22b`.

P3 first requested C3 on the complete `P2_DESIGN` manifest (190 unique DEV images, no VAL/HOLDOUT). C3 DESIGN protocol was 100% and metrics were TP/FP/TN/FN `70/2/108/0`, Precision `0.972222`, Recall `1.0`, ordinary-negative FPR `0`, hard-negative FPR `0.028571`, model-uncertain rate `0`. The two residual hard-negative FP were one kneeling and one push-up/plank case; strict evidence-to-label inconsistency was `0`, visual attribute extraction error was `2`, and explicit support clues were present in both residual evidences. This DESIGN-only forensic led to S1 structured fields: `real_person`, `support_surface`, `torso_pelvis_state`, `active_nonlying_support`, `nonlying_posture_type`, `person_fallen`, and `evidence`, plus the frozen deterministic S1_RULE described in the P3 reports. `OPTIONAL_S2` was not created.

Before new SCREEN requests, P3 froze candidate assets and passed independent verification. The P3 candidate freeze SHA is `b67d3016eade8f33a8b167ff03aaacc0061f96b3d78b7a13518a27f8276542df`; its fixed canary is 3 positive / 2 ordinary-negative / 5 hard-negative / 2 GT-uncertain DESIGN images. The canary passed 12/12 HTTP, response-nonempty, JSON, structured-schema, enum, and canonical checks; `thinking_present=0%`, structured conflicts `0/12`. P2 C3 SCREEN was then independently reused without new requests: TP/FP/TN/FN `50/5/55/0`, Precision `0.909091`, Recall `1.0`, hard-negative FPR `0.125`, P50/P95 `1.580759/1.815010s`.

The S1 structured stream ran once on the reused 120-image P2_SCREEN (`P3_SCREEN_IS_PRISTINE=false`). Both S1_DIRECT and S1_RULE were generated offline from that same response stream, so no second VLM verifier was used. Both had 100% protocol success and structured conflict `0/120`, but both produced TP/FP/TN/FN `50/20/40/0`, Precision `0.714286`, Recall `1.0`, F1 `0.833333`, Accuracy `0.818182`, ordinary-negative FPR `0`, hard-negative FPR `0.5`, model-uncertain rate `0`, and observed P50/P95 `2.134881/9.601210s`. `direct_wrong_rule_correct=0` and `direct_correct_rule_wrong=0`; the fixed rule changed no screen decision. Compared with C3, S1 rescued `0` C3 FP, created `15` new FP from C3 TN, and created `0` positive FN. Hard-negative group error rose from `2/4` groups for C3 to `3/4` for S1.

P3 therefore ended as `P3_STATUS=SCREENING_COMPLETE_NO_WINNER`: neither structured candidate met the advancement gate (`hard-negative FPR<=0.075`), and neither met the project reference quality gate (`Precision>=0.93`, `hard-negative FPR<=0.05`). Runtime was also a fail: S1 observed P95 `9.601210s` exceeded the `1.852084s` reference; load-duration P95 was `7.049979s`, with 7 requests over 5s and a longest sustained run of 3. This is a runtime observation, not proof that the Prompt caused the load anomaly; P2L’s unresolved remote GPU/VRAM/runner evidence limitation remains.

P3 made 322 new DEV requests (C3 DESIGN 190 + structured canary 12 + S1 SCREEN 120), `P3_NEW_VAL_REQUESTS=0`, `P3_HOLDOUT_REQUESTS=0`, and `HOLDOUT_CONSUMED=false`. `VAL_INDIVIDUAL_ERRORS_USED_FOR_P3_DESIGN=false`, `P3_REFERENCE_QUALITY_PASS=false`, `P3_RUNTIME_GATE=FAIL`, `P3_HOLDOUT_READY_QUALITY=false`, `P3_HOLDOUT_READY_RUNTIME=false`, and `P3_HOLDOUT_READY=false`. The independent result verifier passed with exact metric recomputation and unchanged candidate freeze. Because the structured attributes were protocol-valid but semantically poor on the reused SCREEN, the next recommendation is new lineage-isolated hard-negative DEV data before another Prompt-only attempt; higher resolution, ROI/crop, or pose assistance would require separate future experiment IDs. No P4 sealed Holdout run is authorized by this stage. See [21_p3_c3_design_forensics.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/21_p3_c3_design_forensics.md), [22_p3_structured_candidate_screening.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/22_p3_structured_candidate_screening.md), [23_p3_winner_report.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/23_p3_winner_report.md), and [24_p3_final_report.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/24_p3_final_report.md).

## P4D new hard-negative DEV revision

`P4D_NEW_HARD_NEGATIVE_DEV_REVISION` was started as a new text-to-image lineage to address the P3 hard-negative failure. The old `batch_person-fallen-v2-camera1p5m` batch was preserved and not used as a prompt/image/reference source. Before any image request or model view, P4D froze 88 five-image groups (440 prompt slots): hard-negative 300/60 groups, positive 100/20 groups, and ordinary-negative 40/8 groups. The pre-generation split is NEW_DESIGN 265 images/53 groups and NEW_SCREEN 175 images/35 groups, with `CROSS_SPLIT_GROUPS=0`. The exact taxonomy plan is floor_sitting 60, kneeling_half_kneeling 60, pushup_plank 50, crawling_quadruped_support 40, ground_maintenance 40, squat_crouch_deep_bend 30, mixed_hard_negative 20, supine_ground_lying 20, prone_ground_lying 20, side_lying 20, curled_or_partially_occluded_lying 15, intentional_ground_lying 10, multi_person_one_lying 10, horizontal_corridor_ground_lying 5, standing_walking 20, and chair_seated_normal_work 20. All 440 prompt files are complete English prompts and carry new text-to-image lineage.

The prompt pack and split artifacts are frozen: group manifest SHA-256 `11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab`, group split freeze SHA-256 `b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843`, prompt pack SHA-256 `8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250`, prompt manifest SHA-256 `e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb`, and prompt-pack-freeze SHA-256 `385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b`. The dedicated batch is `/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m` and the optimization workspace is `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision`.

Capability audit found Ollama `0.23.2` and `qwen3.5:4b` digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`; these were recorded for the later C3 gate but no C3 request was sent. The configured, previously used image provider `ebond-gpt-image-2` was smoke-tested exactly once for `PF_P4D_HN_SIT_G001_V01` and returned HTTP 401 `INVALID_API_KEY` / `Invalid API key`. No successful image bytes exist (`P4D_IMAGES_GENERATED=0`), no automatic retry or provider switch was made, no mechanical QA or human semantic review could start, and no media/labels were formally ingested. The failed attempt and complete outer/provider evidence remain in the new batch and P4D generation logs.

Therefore `P4D_STATUS=GENERATION_REQUIRED`, `P4D_PROMPT_PACK_READY=true`, `P4D_C3_BASELINE_COMPLETE=false`, `P4D_NEW_VAL_REQUESTS=0`, `P4D_HOLDOUT_REQUESTS=0`, and `HOLDOUT_CONSUMED=false`. The formal dataset was only validated read-only before and after (`status=valid`, `error_count=0`, `full_hash_check=true`, `warning_count=387`); it remains unchanged. P4D has no classification, taxonomy, group, or latency metrics, so all such metrics are `N/A`, not zero and not inferred from the plan. This is an infrastructure/credential gate, not a semantic model result. The Codex image provider was not substituted automatically because its local auth had no prior image-generation history in this run and switching provider/account would change the frozen generation lineage.

The next authorized step is to repair or explicitly authorize an image provider, record the provider decision and retry policy, and continue the frozen 440-slot generation with durable logs. Only after mechanical QA and reliable human semantic review should NEW_DESIGN/NEW_SCREEN image manifests be materialized and C3 be run (DESIGN first, SCREEN once). Do not run NEW_VAL or the formal HOLDOUT from this stopped state. See [25_p4d_data_plan.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/25_p4d_data_plan.md), [26_p4d_generation_and_intake.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/26_p4d_generation_and_intake.md), [27_p4d_ingest_and_split.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/27_p4d_ingest_and_split.md), [28_p4d_c3_new_lineage_baseline.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/28_p4d_c3_new_lineage_baseline.md), and [29_p4d_final_report.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/29_p4d_final_report.md).


## P4D_GR1 generation resume

This append-only section records the P4D_GR1 recovery revision after the original EBOND `INVALID_API_KEY` smoke failure.

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=COMPLETE
P1A_VALID_CLASSIFICATION_BASELINE=true
P1A_PROTOCOL_STATUS=PASS
P2_EXECUTED=false
P3_EXECUTED=false
P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION
P4D_GR1_NAME=P4D_GR1_GENERATION_RESUME
P4D_GR1_CHANGE=provider_revision_only_after_old_ebond_401
P4D_GR1_PROMPT_CHANGED=false
P4D_GR1_GROUP_PLAN_CHANGED=false
P4D_GR1_TAXONOMY_CHANGED=false
P4D_GR1_STATUS=BLOCKED_PROVIDER_AUTH_RECURRENCE
P4D_STATUS=GENERATION_REQUIRED
P4D_NEW_TOTAL=440
P4D_HARD_NEGATIVE=300
P4D_POSITIVE=100
P4D_ORDINARY_NEGATIVE=40
P4D_GROUPS=88
P4D_NEW_DESIGN=265
P4D_NEW_SCREEN=175
P4D_CROSS_SPLIT_GROUPS=0
P4D_IMAGES_GENERATED=192
P4D_IMAGES_ACCEPTED=0
P4D_IMAGES_REJECTED=0
P4D_OUTSTANDING_SLOTS=248
P4D_EXACT_DUPLICATES=0
P4D_NEAR_DUPLICATE_GROUPS=0
P4D_CROSS_SPLIT_NEAR_DUPLICATES=0
P4D_PROMPT_IMAGE_MAPPINGS=N/A
P4D_MISSING_MAPPINGS=N/A
FORMAL_INGEST_EXECUTED=false
MEDIA_ADDED=0
LABELS_ADDED=0
C3_EXECUTED=false
P4D_NEW_VAL_REQUESTS=0
P4D_HOLDOUT_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
VAL_P0_PROTOCOL_EXPOSED=true
VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false

ACTIVE_PROVIDER=codex
ACTIVE_MODEL=gpt-5.4
PROVIDER_CHANGED=true
ORIGINAL_EBOND_ATTEMPT_PRESERVED=true
GENERATION_ATTEMPTS_GR1=226
GENERATION_SUCCESSFUL_GR1=192
GENERATION_FAILED_GR1=34
EXACT_DUPLICATES=0
NEAR_DUPLICATE_GROUPS=0
CROSS_SPLIT_NEAR_DUPLICATES=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
P4D_C3_BASELINE_COMPLETE=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

The generation batch and independent partial-audit artifacts are in `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/`.  Bulk generation stopped on provider usage-limit/authentication recurrence; formal ingest, human semantic review, and C3 were not reached.  The GR1 validator boundary snapshot was `before media=4201/labels=4201/batches=41/splits=2058`, `after media=4521/labels=4521/batches=43/splits=2058`, still `valid/errors=0/full_hash=true/warnings=387`; the +320 media/labels and +2 batches were recorded as external `P5_DEV_20260827` (200) plus `P5_VALIDATION_20260827` (120), with zero P4D references in active CSVs.  No model output was used as ground truth.  See reports [30](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/30_p4d_generation_resume.md) through [34](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/34_p4d_generation_resume_final.md).

## P4D_GR2 generation continuation

`P4D_GR2_GENERATION_CONTINUATION` was opened as a strictly new continuation revision. GR1 remains permanently read-only. Before considering any new image request, GR2 recomputed the six authoritative frozen P4D hashes, verified the GR1 blocked terminal freeze SHA `7bb9bf547ab07ad9f0f64193aae2ee69d15f17d0eb8cfd05722ae3d79afe2fd9`, verified the append-only GR1 ledger SHA `20e00361c532f8386d3f160363cc76d12f104618b6c9fd270d2ec5c78a1a2fd4`, and independently checked all 192 GR1 success files (raw Pillow/hash/native 1672×941 and final Pillow/hash/1920×1080). All checks passed without changing GR1.

The frozen 440-slot manifest was rebuilt as 192 preserved successes plus 248 outstanding slots: 34 historical GR1 failures (32 HTTP 429 and 2 HTTP 401) and 214 never-started slots. Union/intersection/missing/unexpected IDs were 440/0/0/0. GR2 wrote independent inventories, an empty append-only generation ledger, and a run configuration with concurrency 1 and fail-fast gates; it did not schedule the first smoke slot.

The explicit current Codex capability audit was ready and resolved to `codex` / `gpt-5.4` / `image_generation (server-side gpt-image-2 capability)`, but the safe current profile fingerprint differed from the historical GR1 profile fingerprint. Provider, request model, and backend labels alone do not prove account continuity. Therefore the fail-closed decision is:

```text
P4D_GR2_STATUS=FULL_REGEN_AUTHORIZATION_REQUIRED
P4D_STATUS=GENERATION_REQUIRED
P4D_GR2_CONTINUATION_COMPATIBLE=false
GR1_PRESERVED_IMAGES=192
GR2_GENERATED_IMAGES=0
CURRENT_TOTAL_IMAGES=192
OUTSTANDING_SLOTS=248
GR2_REQUESTS=0
GR2_RETRIES=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_IMAGES_ACCEPTED=0
```

This is an account/profile-lineage authorization stop, not a semantic or image-quality result. Full 440 mechanical QA, duplicate/mapping/lineage QA, and the human semantic review package were not reached; the 192 preserved images remain mechanically verified but not accepted. The shared dataset was audited read-only at both boundaries: `valid`, `error_count=0`, `full_hash_check=true`, `warning_count=387`, media/labels `4521/4521`, batches `43`, splits `2058`, and zero P4D-specific references. The current `ingest_media.py` interface has no `validate` subcommand, so that attempted probe was recorded as unavailable and the repository's read-only `tools/validate_dataset.py --json` validator was used.

Do not run GR2 generation under the current profile. Obtain explicit authorization for a full new generation lineage or restore/prove the exact historical GR1 profile, then create another revision before any provider request. Preserve the 192 GR1 files and history; do not ingest, run C3, run NEW_VAL, or consume HOLDOUT. See reports [35](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/35_p4d_gr2_lineage_and_provider_preflight.md) through [39](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/39_p4d_gr2_final.md).

## P4D_GR3 full-regeneration preparation

This append-only section records the GR3 preparation boundary. It creates a
new 0/440 generation lineage but deliberately does not call the image provider.
The prior GR1 192 images remain historical, mechanically verified provenance;
`GR1_IMAGES_REUSED=0` and no old image bytes are copied into the new batch.

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P4D_GR1_STATUS=BLOCKED_PROVIDER_AUTH_RECURRENCE
P4D_GR2_STATUS=FULL_REGEN_AUTHORIZATION_REQUIRED
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
P4D_CURRENT_ACTION=FULL_REGEN_PREPARATION
P4D_STATUS=GENERATION_REQUIRED
FULL_REGEN_REQUIRED=true
FULL_REGEN_AUTHORIZED=false
NEW_GENERATION_LINEAGE=true
GR1_CONTINUATION=false
GR1_IMAGES_REUSED=0
HISTORICAL_GR1_IMAGES=192
PLANNED_NEW_IMAGES=440
P4D_PROMPT_CHANGED=false
P4D_GROUP_PLAN_CHANGED=false
P4D_TAXONOMY_CHANGED=false
P4D_SPLIT_CHANGED=false
P4D_GROUPS=88
P4D_NEW_DESIGN=265
P4D_NEW_SCREEN=175
P4D_CROSS_SPLIT_GROUPS=0
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

The GR2 history erratum is additive at
`/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/40_p4d_gr2_history_status_erratum.md`
and
`/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr2/history_status_erratum.json`.
It corrects the drifted later-summary fields (`P1A_STATUS`, `P2_EXECUTED`,
`P2_STATUS`, `P3_EXECUTED`, and `P3_STATUS`) from authoritative reports while
leaving report39 and the GR2 terminal freeze byte-for-byte unchanged.

The new lineage is revision
`P4D_FULLREGEN_CODEX_PROFILE2_20260827_01` and batch
`/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m`.
Its 440-row prompt manifest binds frozen prompt bytes (300 hard-negative, 100
positive, 40 ordinary-negative; NEW_DESIGN 265 / NEW_SCREEN 175; 88 groups;
zero cross-split groups) and has SHA-256
`5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`.
The batch is preparation-only: `generated_raw/` and `final/` are empty,
the ledger is header-only, and the durable state has 440 `NOT_STARTED` slots.

The current read-only capability audit resolves to provider `codex`, request
model `gpt-5.4`, and backend `image_generation (server-side gpt-image-2
capability)`, runtime `0.7.3`, plan type `plus`, and safe profile fingerprint
`ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe`.
The installed runtime reports native `max_retries=3`; no supported
`--no-retry` or `--max-retries` control was found, so
`NO_RETRY_GUARANTEE=false` and the conservative possible-attempt multiplier is
4 per logical slot. A future runner is only preregistered as smoke 1 → ramp 5
→ ramp 10 → micro-batches 10, concurrency 1, with global first-429/401/403
stop. No executable runner exists in this revision. The authorization packet
remains `authorized=false`; see reports [40](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/40_p4d_gr2_history_status_erratum.md) through [44](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/44_p4d_gr3_authorization_required.md).

The GR3 dataset boundary validator itself did not write the shared dataset and
found zero active P4D references. During the final preparation audit, an
unrelated user-owned `fire_passage_blocked` formal-ingest process was active;
the recorded boundary therefore reflects a real external delta (two media rows
within the audit window) and is not attributed to GR3. The preparation freeze
binds that observed boundary and its `formal_dataset_mutation=false` result.
A post-quiescence validator is a separate read-only follow-up: it must not
rewrite this freeze, the P4D manifests, or the GR3 batch. The requested
`ingest_media.py validate` subcommand is unavailable in the current interface;
the repository's direct `tools/validate_dataset.py --json` validator is the
authoritative fallback.

## P4D_GR3E full-regeneration execution

This append-only section records the GR3E execution gate and its zero-request
terminal state. The preparation freeze remains byte-for-byte unchanged; this
section is bound by the separate GR3E terminal freeze after this append.

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION
P4D_GR3E_STATUS=AWAITING_EXPLICIT_USER_AUTHORIZATION
P4D_STATUS=GENERATION_REQUIRED
EXPLICIT_AUTHORIZATION_VERIFIED=false
AUTHORIZATION_ATTESTATION_PRESENT=false
FULL_REGEN_AUTHORIZED=false
PROVIDER_REQUESTS=0
GENERATED_IMAGES=0
OUTSTANDING=440
OUTER_RETRY=false
NATIVE_RUNTIME_MAX_RETRIES=3 (preparation-time)
NO_RETRY_GUARANTEE=false
POSSIBLE_PROVIDER_ATTEMPTS_UPPER_BOUND=4
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
HOLDOUT_CONSUMED=false
P4D_IMAGES_ACCEPTED=0
P4D_GR3E_RUNTIME_REPREFLIGHT=NOT_RUN_AUTH_GATE
P4D_GR3E_RUNNER_CREATED=false
HUMAN_SEMANTIC_REVIEW_STATUS=NOT_STARTED
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

The current task supplied the required wording only as an embedded execution
specification, not as a standalone user attestation. Under the fail-closed
authorization gate, no provider/runtime re-preflight was run, no runner was
created, and no image or provider request exists. The 440 slots remain
outstanding; no mechanical QA, duplicate/lineage QA, mapping QA, human-review
package, formal ingest, C3, NEW_VAL, or HOLDOUT action was reached. `accepted=0`
means that no image reached human review, not that any image was semantically
rejected or relabeled.

The read-only dataset snapshots for this execution were recorded before and
after the gate. The external `fire_passage_blocked` ingest process changed the
shared media count during that window; GR3E did not mutate the dataset. Both
snapshots had zero active P4D references. The validator remained `valid` with
zero errors, full hash checking enabled, and the existing warning set recorded
as-is. The terminal freeze records the preparation-time provider capability and
retry audit as last-known evidence, explicitly marks current runtime
re-preflight as not run, and binds the current overview hash separately from
the preparation-time overview hash.

See reports [45](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/45_p4d_gr3e_authorization_and_runtime.md),
[46](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/46_p4d_gr3e_generation.md),
[47](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/47_p4d_gr3e_full_440_qa.md),
[48](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/48_p4d_gr3e_human_review_package.md),
and [49](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/49_p4d_gr3e_final.md).
The zero-request execution surface and terminal freeze are under
`08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/`.

The exact next authorization action, if desired, is a new standalone user
instruction containing:

> 我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，接受旧 GR1 192 张不进入新 revision；我同时明确接受当前 GPT Image 2 runtime max_retries=3、单个逻辑 slot 最多约 4 次 provider attempt、精确费用未知以及由此产生的 quota/成本风险。

## P4D_GR3E authorized continuation — provider usage-limit stop

This append-only section records the separately authorized continuation
`authorized_20260827_01`. The previous no-authorization GR3E terminal freeze and
reports 45–49 remain byte-for-byte historical evidence; this continuation does
not rewrite them or the GR3 preparation freeze. GR1's 192 images remain
historical provenance and were not copied, symlinked, renamed, re-encoded,
resized, or otherwise reused.

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION
P4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT
P4D_STATUS=GENERATION_REQUIRED
EXPLICIT_AUTHORIZATION_VERIFIED=true
AUTHORIZATION_ATTESTATION_PRESENT=true
AUTHORIZATION_SCOPE=440_full_regeneration
GR1_IMAGES_REUSED=0
HISTORICAL_GR1_IMAGES=192
PLANNED_NEW_IMAGES=440
LOGICAL_SLOT_INVOCATIONS=100
LOGICAL_SUCCESSES=99
LOGICAL_FAILURES=1
GENERATED_RAW=99
GENERATED_FINAL=99
OUTSTANDING=341
SMOKE_REQUESTS=1
SMOKE_SUCCESS=1
RAMP1_REQUESTS=5
RAMP1_SUCCESS=5
RAMP2_REQUESTS=10
RAMP2_SUCCESS=10
BULK_REQUESTS=84
BULK_SUCCESS=83
BULK_FAILURE=1
FIRST_TERMINAL_ERROR=HTTP_429
HTTP_429=1
HTTP_401=0
HTTP_403=0
TIMEOUT_OR_5XX=0
STOP_NEW_LOGICAL_SLOTS=true
GLOBAL_STOP=true
NATIVE_RUNTIME_MAX_RETRIES=3
NO_RETRY_GUARANTEE=false
OUTER_RETRY=false
OBSERVED_NATIVE_RETRY_SCHEDULED_EVENTS=7
OBSERVED_ATTEMPT_LOWER_BOUND_SUM=107
POSSIBLE_PROVIDER_ATTEMPTS_UPPER_BOUND=1760
EXACT_MONETARY_COST=UNKNOWN
FULL_440_QA=NOT_REACHED_INCOMPLETE_GENERATION
HUMAN_REVIEW_PACKAGE=NOT_CREATED
HUMAN_SEMANTIC_REVIEW_STATUS=NOT_STARTED
P4D_IMAGES_ACCEPTED=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
HOLDOUT_CONSUMED=false
VAL_P0_PROTOCOL_EXPOSED=true
VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false
P4D_ACTIVE_DATASET_HITS=0
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

The immutable preparation and execution identity gates passed: provider
`codex`, model `gpt-5.4`, backend `image_generation`, safe profile continuity
matched preparation, auth/session/endpoint were ready, wrapper SHA was
`f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe`, and
installed binary SHA was
`1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba`. The
frozen 440-slot prompt manifest remained SHA
`5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`.

The first 99 logical slots produced 99 raw/final image pairs. The independent
post-stop subset audit passed Pillow verification, final `1920x1080`
dimensions, exact filename mapping, zero raw/final exact duplicates, zero
near-duplicate groups, zero cross-split near-duplicate pairs, zero old-GR1
hash hits, and zero same-file hits. This is only a 99-image subset result;
the required 440-image QA gate and semantic review were not reached.

At logical invocation 100, prompt
`PF_P4D_HN_KNEEL_G008_V05` returned a provider envelope with `HTTP 429` and
`usage_limit_reached`. The runtime stderr records retry numbers 1–3 after the
initial request. The runner marked the slot `FAILED_CONFIRMED`, wrote a global
stop marker, and invoked no later slot. No automatic recovery or resend is
authorized by this sealed continuation.

The final read-only shared-dataset validator remained `valid`, with zero
errors, full-hash checking enabled, and the pre-existing 387 warnings. The
observed CSV-row boundary changed from media/labels/batches/splits
`5081/4619/45/2058` at the continuation start to `5081/4881/45/2618` at the
post-stop audit; the +262 labels and +560 splits are retained as an observed
shared-workspace delta and are not attributed to GR3E. Active P4D references
remained zero. Formal ingest, C3, NEW_VAL, HOLDOUT, and production integration
were not run.

The continuation artifacts are under
`/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/authorized_20260827_01/`.
Reports 50–54 are the authorized continuation reports; the separate terminal
freeze in that directory binds their hashes, the partial inventory, the raw
request logs, the dataset boundary, and both prior immutable freezes.


## P4D_GR3Q1 provider-quota recovery preparation

```text
P4D_GR3Q1_NAME=P4D_GR3Q1_PROVIDER_QUOTA_RECOVERY_PREPARATION
P4D_GR3Q1_STATUS=BLOCKED_PROFILE_LINEAGE_CHANGE
P4D_STATUS=GENERATION_REQUIRED
PRESERVED_GR3E_SUCCESS=99
FAILED_CONFIRMED_429=1
NEVER_STARTED=340
COMPLETION_UNKNOWN=0
OUTSTANDING=341
CONTINUATION_COMPATIBLE=false
QUOTA_RECOVERY_AUTHORIZED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
```

The sealed GR3E authorized execution remains unchanged. GR3Q1 verified its 99 successes against the durable ledger and image bytes, derived 341 outstanding slots, and confirmed current provider `codex`, model `gpt-5.4`, backend `image_generation`, safe profile fingerprint, runtime, wrapper, binary, and retry-policy continuity. No provider request was sent. The preparation freeze is `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_recovery_20260827_01/freeze/p4d_gr3q1_preparation_freeze.json` with SHA-256 `841e0d77ad85d325b55ea1e0c83534ef8090e6603b77f289d4644a7b54d6141f`; execution still requires the exact standalone authorization in report 59.

### P4D_GR3Q1 profile-lineage gate correction

The preceding GR3Q1 paragraph is preserved as the initial preparation record, but its continuity sentence and authorization conclusion are superseded by the actual gate result. Provider/model/backend/runtime continuity passed; safe profile fingerprint continuity did not. Current fingerprint `d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190` differs from sealed GR3E fingerprint `ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe`. Therefore `CONTINUATION_COMPATIBLE=false`, the 99+341 quota-recovery plan is not authorizable, and the 99 verified images remain historical GR3E-lineage artifacts only. The correctly resealed preparation freeze SHA-256 is `e64a41f735c8837b273b9100a40f7437e70721df4f1f5be8230a9e634890a847`. The next valid lifecycle, if separately authorized, is a new 440-slot full regeneration under the current profile. Provider requests remained zero.


## P4D_GR3Q2 lineage-policy amendment and recovery preparation

```text
P4D_GR3Q2_NAME=P4D_GR3Q2_LINEAGE_POLICY_AMENDMENT_AND_RECOVERY_PREP
P4D_GR3Q2_STATUS=READY_AWAITING_PROFILE_STRATIFIED_RECOVERY_AUTHORIZATION
P4D_STATUS=GENERATION_REQUIRED
POLICY_AMENDMENT_ACCEPTED=true
POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION=false
MATERIAL_GENERATION_CONFIG_CHANGE=false
PROFILE_CHANGE_ONLY=true
PRESERVE_GR3E_99=true
OUTSTANDING=341
PROFILE_STRATIFICATION_REQUIRED=true
RECOVERY_AUTHORIZED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
```

GR3Q1 remains a correct historical profile-lineage block under its former policy. GR3Q2 is a new governance revision: it reclassified account/profile fingerprint as operational provenance when observable provider/model/backend/runtime/prompt/configuration variables remain unchanged. It reverified 99 preserved successes and 341 outstanding slots, created explicit Profile-A/Profile-B strata, and recorded severe profile×role/taxonomy confounding plus split imbalance for future audit. No image-generation request was sent. The GR3Q2 preparation freeze is `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/lineage_policy_amendment_20260828_01/freeze/p4d_gr3q2_preparation_freeze.json` with SHA-256 `bd788e5b2d72bb1681846909e4cb2a2bf314897523c8011285f78deae5889801`. A separate future user authorization is still required before any recovery execution.

### P4D_GR3Q2 preparation-freeze binding correction

The initial GR3Q2 freeze (`e638b52484b60ae072ad791d06a3dfd980ec39294a0780729f65f12de39f1925`) is preserved as an audit artifact, but is not the valid terminal freeze: a duplicate, zero-provider-request local preparation invocation rewrote 13 timestamp-bearing local audit artifacts after its creation. No parent freeze, image payload, provider configuration, dataset annotation, C3, VAL, or HOLDOUT artifact changed. The initial bytes and original sidecar are retained under `lineage_policy_amendment_20260828_01/freeze/`, and the mismatch audit is retained in `05_checkpoints/initial_freeze_binding_error_audit.json`. The current canonical resealed preparation freeze is `bd788e5b2d72bb1681846909e4cb2a2bf314897523c8011285f78deae5889801`, with all 44 current artifact bindings verified. This correction does not authorize recovery execution.

## P4D_GR3Q2E profile-stratified recovery execution (2026-08-28)

```text
P4D_GR3Q2E_NAME=P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY
P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_GR3Q2E_CHANGE=PROFILE_STRATIFICATION_ONLY
P4D_GR3Q2E_PROMPT_CHANGED=false
P4D_GR3Q2E_GENERATION_CONFIG_CHANGED=false
PRESERVED_PROFILE_A=99
PROFILE_B_LOGICAL_INVOCATIONS=4
PROFILE_B_SUCCESS=3
PROFILE_B_FAILED_CONFIRMED=1
PROFILE_B_NOT_STARTED=337
COMPLETION_UNKNOWN=0
FULL_341_RECOVERY_COMPLETE=false
P4D_VALIDATED_GENERATION_BASELINE=false
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
NATIVE_MAX_RETRIES=3
OUTER_RETRY=false
PHYSICAL_PROVIDER_ATTEMPTS_OBSERVED=7
STOP_REASON=HTTP_429
STOP_PROMPT_ID=PF_P4D_HN_KNEEL_G009_V03
STOP_RECOVERY_ORDER=4
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_ACTIVE_DATASET_HITS=0
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
AUTOMATIC_RECOVERY_AFTER_FAILURE=false
EXACT_MONETARY_COST=UNKNOWN
```

The exact standalone recovery authorization was attested and all seven
preflight gates passed before any provider request. Q2E preserved the 99
integrity-verified GR3E images as historical Profile-A and used the current
Codex profile as Profile-B under the accepted lineage-policy amendment. The
frozen 440-slot manifest remained hash matched
(`5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`).

The runner issued four logical Profile-B invocations. The previous 429 slot
`PF_P4D_HN_KNEEL_G008_V05` succeeded on recovery, followed by successful
`G009_V01` and `G009_V02`. `PF_P4D_HN_KNEEL_G009_V03` then returned HTTP 429
(`usage_limit_reached`) after the permitted three native retries. The global
stop marker was written and no later slot was started. Final slot counts were
`99 PRESERVED_PROFILE_A + 3 SUCCESS_PROFILE_B + 1 FAILED_CONFIRMED_PROFILE_B
+ 337 NOT_STARTED_PROFILE_B`, with zero completion-unknown slots. The observed
physical provider-attempt count was 7, while exact cost remains unknown.

Post-stop inventory contained 102 raw and 102 final files (99 preserved pairs
plus three new pairs); all 204 files passed Pillow verification, with raw
`1672x941` and final `1920x1080`. This is mechanical evidence only. The full
440-image QA, deduplication gate, human semantic review, formal ingest, and C3
were not reached, so `P4D_VALIDATED_GENERATION_BASELINE=false` and
`P4D_IMAGES_ACCEPTED=0`. Q2E did not run classifier inference; semantic
metrics are therefore `N/A`, not zero.

The first terminal freeze is retained as an initial SQLite-close binding error
(`f68257b67d0c4685f394fc1a77a5dff74a3c100b6c2f442a91075f8e850355e5`). A
read-only reseal after the SQLite connection closed produced the canonical
terminal freeze SHA
`9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44`; its 17/17
artifact bindings and self-hash pass, and the reseal added zero provider
requests. The detailed execution report is
`/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/65_p4d_gr3q2e_profile_stratified_recovery_final.md`.

The final read-only shared-dataset validator remained `valid` with zero errors,
full-hash checking enabled, 387 pre-existing warnings, and counts
`media=5081, labels=4881, batches=45, splits=2618`; before/after annotation
hashes were unchanged and active P4D references remained zero. No formal
ingest, C3, NEW_VAL, HOLDOUT, or production modification occurred. This Q2E
revision is sealed and stopped; any further provider recovery needs a new
standalone authorization and a separately identified revision. Do not resume
this revision or infer permission for P2/P3/P4 optimization from this entry.

## P4D GR3Q3 quota-window recovery preparation (2026-08-28)

```text
P4D_GR3Q3_NAME=P4D_GR3Q3_QUOTA_WINDOW_RECOVERY
P4D_GR3Q3_REVISION=P4D_GR3Q3_QUOTA_WINDOW_RECOVERY_20260828_02
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q3_EXECUTION_NOT_EXECUTED=true
P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_STATUS=GENERATION_REQUIRED
FULL_341_RECOVERY_COMPLETE=false
P4D_VALIDATED_GENERATION_BASELINE=false
CURRENT_SUCCESS=102
PROFILE_A_SUCCESS=99
PROFILE_B_SUCCESS=3
OUTSTANDING=338
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0
PROVIDER_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
C3=false
NEW_VAL=0
P4D_ACTIVE_DATASET_REFS=0
PRODUCTION_CODE_MODIFIED=false
```

GR3Q3 did not execute generation. The parent Q2E canonical terminal freeze
`9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44` and its
17/17 artifact bindings were verified. The frozen 440 prompt manifest remained
`5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`; prompt
bytes, IDs, groups, and split isolation matched. A rebuilt inventory verified
99 GR3E Profile-A pairs plus 3 Q2E Profile-B pairs (102 total), and the
outstanding inventory verified one prior Q2E HTTP 429 slot followed by 337
never-started slots with no completion ambiguity. GR1 hash/samefile/symlink
reuse was zero.

The Q2E failure raw evidence reported `usage_limit_reached`,
`resets_at=1787914147` (`2026-08-28T18:49:07+08:00`). With a 653-second safety
margin, `NOT_BEFORE_LOCAL=2026-08-28T19:00:00+08:00`; the local time captured
for this preparation was `2026-08-28T15:15:27.177+08:00`, so the time gate
failed. The current top-level user message contained no standalone GR3Q3
window authorization, so no smoke request was permissible even after the time
gate. The new SQLite ledger is WAL/synchronous=FULL with all 338 slots
`NOT_STARTED`; request and raw-response logs are empty.

The read-only GPT Image 2 capability audit resolved explicitly to
`provider=codex`, `request_model=gpt-5.4`, `generation_backend=image_generation`,
runtime `0.7.3`, native max retries 3, and outer retry false. Its current safe
profile fingerprint matched historical Profile-A rather than Q2E Profile-B;
this is recorded as provenance evidence and is not a reason to rewrite the
102-image inventory. Shared dataset validation stayed `valid`, zero errors,
full-hash enabled, 387 existing warnings, counts `media=5081, labels=4881,
batches=45, splits=2618`, with unchanged annotation hashes and zero active P4D
references. Semantic metrics, full 440 QA, human review, formal ingest, C3,
VAL, NEW_VAL, and HOLDOUT remain `N/A`/`NOT_REACHED`.

The detailed final report is
`/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/70_p4d_gr3q3_final.md`.
The new terminal freeze is
`/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/freeze/p4d_gr3q3_terminal_freeze.json`
with SHA-256
`7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697` and a
matching sidecar. Do not sleep, background-run, or automatically resume this
preparation; after the time gate, a new standalone authorization and a fresh
runtime/provenance gate are required before any new execution revision.

## P4D GR3Q4 adaptive quota-window campaign preparation (2026-08-28)

```text
P4D_GR3Q4_NAME=P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN
P4D_GR3Q4_REVISION=P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN_20260828_03
P4D_GR3Q4_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q4_EXECUTION_NOT_EXECUTED=true
P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_STATUS=GENERATION_REQUIRED
CURRENT_VERIFIED_SUCCESS=102
PROFILE_A_SUCCESS=99
PROFILE_B_SUCCESS=3
OUTSTANDING=338
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0
PARTIAL_GROUP_COUNT=1
ADAPTIVE_ORDER_ROWS=338
FIRST_WINDOW_MAX_LOGICAL_INVOCATIONS=68
LATER_WINDOW_DEFAULT_MAX_LOGICAL_INVOCATIONS=70
MAX_OBSERVED_PHYSICAL_ATTEMPT_LOWER_BOUND=80
MAX_NATIVE_RETRY_SCHEDULED_EVENTS_THIS_WINDOW=5
PROVIDER_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
C3=false
NEW_VAL=0
FULL_440_QA=NOT_REACHED
P4D_VALIDATED_GENERATION_BASELINE=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_MODIFIED=false
```

GR3Q4 是一个新的调度/配额风险治理 revision，不是语义优化。GR3Q2E 的 `STOPPED_BY_FAILURE_POLICY`、GR3Q3 的 `WAITING_FOR_PROVIDER_QUOTA_RESET`、Q2E canonical freeze `9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44` 和 GR3Q3 terminal freeze `7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697` 均被只读核对并保持不变。冻结 440-slot manifest SHA-256 仍为 `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`，440/440 prompt bytes、440 unique IDs、88 groups、cross-split=0 通过；角色为 hard_negative=300、positive=100、ordinary_negative=40，planned split 为 NEW_DESIGN=265、NEW_SCREEN=175。

本 revision 从实际父级 ledger、raw/final 文件和 manifest 重新建立了 102-success inventory：GR3E Profile-A=99、GR3Q2E Profile-B=3；102 对 raw/final 各自通过 SHA/Pillow/1920x1080/symlink/samefile 审计，GR1 hash/samefile/symlink reuse=0。338 outstanding 精确为确认的 HTTP 429=1、NEVER_STARTED=337、COMPLETION_UNKNOWN=0。当前唯一 partial group 是 `PF_P4D_HN_KNEEL_G009`（2 success + 3 outstanding），`PF_P4D_HN_KNEEL_G009_V03` 排在新计划首位。

新 `adaptive_execution_order.csv` 有 338 行、338 个唯一 outstanding prompt ID，SHA-256 为 `acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033`。算法先完成 partial group，再按 role/taxonomy/planned split normalized deficit 选择完整 5-slot group，并以 original manifest ordinal、group_id 稳定 tie-break；不使用视觉质量、C3 或模型错误。首窗口计划为 68 行、14 groups（partial 3 slots + 13 个完整 groups），角色 hard_negative=23、positive=35、ordinary_negative=10，planned split NEW_DESIGN=30、NEW_SCREEN=38；其 CSV SHA-256 为 `2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd`。

本次 read-only GPT Image 2 audit 为 provider=`codex`、model=`gpt-5.4`、backend=`image_generation`、runtime=`0.7.3`、auth ready、endpoint reachable、TLS=true、native max retries=3、outer_retry=false；wrapper SHA 为 `f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe`，binary SHA 为 `1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba`。当前安全 fingerprint 与历史 Profile-A 相同，记录为 `PROFILE_A_RESTORED`，不是 Profile-B，也没有创建 Profile-C。预注册图像配置仍为 native 1536x1024/medium/png，controlled 16:9 crop + Pillow LANCZOS 到 1920x1080。

Q2E quota evidence 的 reset 为 `2026-08-28T18:49:07+08:00`，加入 653 秒安全 margin 后 `NOT_BEFORE_LOCAL=2026-08-28T19:00:00+08:00`；本轮捕获本机时间 `2026-08-28T16:00:31.393314+08:00`，所以 time gate 未通过。当前顶层消息没有独立 campaign authorization；packet 的 `authorized=false`、`explicit_campaign_authorization=false`、`template_is_authorization=false`，没有 attestation 和 provider request。即使时间 gate 通过，仍需新的独立授权才能从 `AWAITING_CAMPAIGN_AUTHORIZATION` 进入执行。

首窗口 durable 工件已建立但未执行：68 行 ledger 全部 `NOT_STARTED`；SQLite stable close 后为 WAL/synchronous=FULL，68 rows、1 初始化 event，WAL/SHM 已清理；request/raw logs 均为空。终态 freeze 为 [p4d_gr3q4_terminal_freeze.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/freeze/p4d_gr3q4_terminal_freeze.json)，SHA-256 `8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2`，sidecar 匹配，37/37 bound artifacts 通过，provider_requests=0。共享数据集 validator 最终为 `valid`、error=0、full-hash=true、387 个历史 warning，counts `media=5081, labels=4881, batches=45, splits=2618`；annotation hashes unchanged、active P4D references=0。

GR3Q4 没有执行 full 440 QA、semantic sentinel、formal ingest、C3、NEW_VAL 或 HOLDOUT，也没有修改 shared split CSV、production code 或 Ollama，因此不能称为新的 generation/semantic baseline。详见 [71 strategy](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/71_p4d_gr3q4_quota_strategy_analysis.md)、[72 adaptive order](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/72_p4d_gr3q4_adaptive_execution_order.md)、[73 inventory](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/73_p4d_gr3q4_current_inventory.md)、[74 authorization](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/74_p4d_gr3q4_campaign_authorization.md) 和 [75 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/75_p4d_gr3q4_final.md)。本次没有创建 report 76；只有真实窗口执行后才允许新增该报告。下一步不得 sleep、后台等待或自动恢复，需在安全时间后由用户新顶层消息明确授权，再人工启动独立 window revision。

## P4D EB1 EBOND independent full-regeneration lineage (2026-08-28)

```text
P4D_EB1_NAME=P4D_EB1_EBOND_FULL_REGENERATION
P4D_EB1_PROVIDER=ebond
P4D_EB1_GENERATION_REVISION=P4D_EBOND_FULLREGEN_20260828_01
P4D_EB1_STATUS=BLOCKED_PRIMARY_AUTH_NO_SECONDARY
P4D_EB1_NEW_GENERATION_LINEAGE=true
P4D_EB1_PROMPT_CHANGED=false
P4D_EB1_TAXONOMY_CHANGED=false
P4D_EB1_GROUP_CHANGED=false
P4D_EB1_SPLIT_CHANGED=false
FROZEN_440_MANIFEST_SHA256=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
EBOND_LINEAGE_REUSED_CODEX_IMAGES=0
GR1_IMAGES_REUSED=0
SCHEMA_VERIFIED=true
ACTIVE_EBOND_CREDENTIAL_SLOT=PRIMARY
SECONDARY_DISCOVERED=false
SMOKE_STATUS=FAIL_HTTP_401_INVALID_API_KEY
RAMP1_STATUS=NOT_REACHED
RAMP2_STATUS=NOT_REACHED
LOGICAL_REQUESTS=1
SUCCESSFUL_REQUESTS=0
FAILED_CONFIRMED=1
COMPLETION_UNKNOWN=0
EBOND_OUTSTANDING=440
RAW_PROVIDER_RESPONSES=1
RAW_IMAGES=0
FINAL_IMAGES=0
FULL_440_MECHANICAL_QA=NOT_REACHED
P4D_IMAGES_ACCEPTED=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
C3=false
NEW_VAL=0
PRODUCTION_CODE_MODIFIED=false
```

EB1 是与 Codex GR3Q4 完全独立的 EBOND generation lineage。冻结的 440-slot design、prompt bytes、group/split 与 taxonomy 均通过 preflight SHA-256 核验；新 balanced order 的前 16 个 slot 覆盖三种 role、四个 taxonomy 和两种 planned split。历史 Codex 102 张及 GR1 192 张全部只作诊断，EBOND revision 实际复用为 0，未复制任何历史图像 bytes。

本机历史成功 capability evidence 与 gpt-image-2 skill provider reference 共同确认 EBOND schema 为 `POST https://api.ebondai.com/v1/images/generations`，请求 `model=gpt-image-2`、冻结 prompt、`size=1536x1024`、`quality=medium`，响应要求 `data[0].b64_json`。本次使用 direct `urllib.request`、禁 redirect、client/library/provider/outer retry 均为 0，`CONCURRENCY=1`。

第一张正式 smoke `P4D_EB1_0001 / PF_P4D_HN_SIT_G001_V01` 只发出一次，provider 返回 HTTP 401，raw body 为 `INVALID_API_KEY`。当前可验证 credential store 只有 PRIMARY 的安全指纹，未发现可安全读取的 SECONDARY；因此按 auth gate 停止，没有试用其他事件的 key，也没有继续后续 439 个 slot。按“非成功 slot”计的 `EBOND_OUTSTANDING=440`（1 个已确认失败 + 439 个未启动）。最终 sealed terminal freeze SHA-256 为 `ecb7bc9498f5c2184dab0fc1f1ed112dff13f7dfac9b316322af53e3dd233bb0`，SQLite ledger 为 1 failed + 439 pending，raw/final=0，full QA 和 human semantic review 均未到达，分类/图像质量指标均为 `N/A`。

EB1 前后 shared dataset validator 均为 `valid`、`error_count=0`、`full_hash_check=true`、387 个既有 warning，counts 保持 `media=5081, labels=4881, batches=45, splits=2618`；`MEDIA_ADDED=0`、`LABELS_ADDED=0`、`FORMAL_INGEST=false`、`C3=false`、`NEW_VAL=0`、`HOLDOUT_REQUESTS=0`。本次 terminal freeze 已封存，不能重试、重写或用历史 Codex 图像补齐；credential 修复后的任何恢复都必须新建独立 revision 并重新 smoke/preflight。详情见 [76 provider/lineage](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/76_p4d_eb1_provider_and_lineage.md)、[77 execution](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/77_p4d_eb1_generation_execution.md)、[78 QA](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/78_p4d_eb1_full440_qa.md)、[79 review package](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/79_p4d_eb1_human_review_package.md) 和 [80 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/80_p4d_eb1_final.md)。

## P4D GR3Q4E Adaptive Quota Campaign Window 01 (2026-08-30)

本阶段仍以 `P2-C3` 为当前语义候选，`P3_WINNER=NONE`；GR3Q4E 只负责受控的图像生成窗口，不执行语义 Prompt/C3 优化。

```text
P4D_GR3Q4E_NAME=P4D_GR3Q4E_ADAPTIVE_QUOTA_CAMPAIGN_WINDOW_01
P4D_GR3Q4E_REVISION=P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01
P4D_GR3Q4E_STATUS=AWAITING_CAMPAIGN_AUTHORIZATION
STOP_REASON=EXPLICIT_CAMPAIGN_AUTHORIZATION_MISSING
PARENT_GR3Q4_FREEZE_VERIFIED=true
PARENT_GR3Q4_FREEZE_SHA256=8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2
Q2E_CANONICAL_FREEZE_SHA256=9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44
GR3Q3_TERMINAL_FREEZE_SHA256=7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697
FROZEN_440_MANIFEST_SHA256=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
CURRENT_VERIFIED_SUCCESS=102
PROFILE_A_SUCCESS=99
PROFILE_B_SUCCESS=3
CURRENT_OUTSTANDING=338
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0
ADAPTIVE_ORDER_ROWS=338
FIRST_WINDOW_ROWS=68
FIRST_WINDOW_GROUPS=14
FIRST_WINDOW_ROLE_COUNTS=hard_negative:23,positive:35,ordinary_negative:10
FIRST_WINDOW_SPLIT_COUNTS=NEW_DESIGN:30,NEW_SCREEN:38
FIRST_WINDOW_FIRST_PROMPT=PF_P4D_HN_KNEEL_G009_V03
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
ACTIVE_PROFILE_STRATUM=PROFILE_A_RESTORED
PROFILE_FINGERPRINT_SAFE_HASH=ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe
AUTHORIZATION_PRESENT=false
WINDOW_LOGICAL_CAP=68
PHYSICAL_ATTEMPT_LOWER_BOUND_CAP=80
NATIVE_RETRY_EVENT_CAP=5
LOGICAL_INVOCATIONS=0
WINDOW_SUCCESS=0
WINDOW_FAILURE=0
NATIVE_RETRY_SCHEDULED_EVENTS=0
PHYSICAL_ATTEMPT_LOWER_BOUND=0
PROVIDER_REQUESTS=0
NEW_RAW_COUNT=0
NEW_FINAL_COUNT=0
FULL_440_QA=NOT_REACHED
SEMANTIC_SENTINEL=NOT_EXECUTED
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_ACTIVE_DATASET_REFS=0
DATASET_VALIDATOR_STATUS=valid
DATASET_VALIDATOR_ERRORS=0
DATASET_WARNING_COUNT=387
PRODUCTION_CODE_MODIFIED=false
OLLAMA_MODIFIED=false
```

本轮新建了独立的 Window 01 execution revision，但没有把任务正文中的授权模板误当作用户授权。实时 Codex capability audit 为 `provider=codex`、`model=gpt-5.4`、`backend=image_generation`、runtime `0.7.3`、auth/session ready、endpoint reachable、TLS=true；material generation config 仍是 native `1536x1024`、medium、PNG、controlled 16:9 crop + Pillow LANCZOS 到 `1920x1080`，wrapper SHA=`f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe`，binary SHA=`1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba`。当前 profile 与历史 Profile-A 一致，记录为 provenance stratum A；没有创建 Profile-C。

当前 102 张由 GR3E/Q2E ledgers、实际 raw/final 文件和 Pillow/SHA/dimension/symlink/samefile 检查重建并通过；GR1 hash/samefile/symlink reuse=0。冻结 adaptive order 与 first-window plan 未重排，SHA 分别为 `acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033` 和 `2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd`。历史 reset 时间门槛已过，但没有独立 campaign authorization，因此首 slot 没有发送；68 行 durable SQLite ledger 全部 `NOT_STARTED`，request/raw logs 均为空，provider requests=0。

共享数据集只读 validator before/after 均为 `valid`、0 errors、full-hash=true、387 个历史 warning，counts 保持 `media=5081, labels=4881, batches=45, splits=2618`，annotation hashes unchanged、active P4D refs=0；没有 ingest、C3、VAL、HOLDOUT 或 production/Ollama 修改。canonical terminal freeze 位于 [p4d_gr3q4e_window01_terminal_freeze.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_01_execution_20260830_01/freeze/p4d_gr3q4e_window01_terminal_freeze.json)，SHA-256=`dbb443af788cf2d20a26e812f5f86471aee14e0860e8872d21cb825603912527`，42/42 bound artifacts 和 sidecar 通过；更早的未含报告修订的初始 seal 已保留在同 revision 的 `freeze/initial_seal_before_report_erratum_20260830_01/`，没有覆盖或删除。

详见 [81 preflight](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/81_p4d_gr3q4e_window01_preflight.md)、[82 execution](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/82_p4d_gr3q4e_window01_execution.md)、[83 partial QA](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/83_p4d_gr3q4e_window01_partial_qa.md)、[84 quota metrics](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/84_p4d_gr3q4e_window01_quota_metrics.md) 和 [85 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/85_p4d_gr3q4e_window01_final.md)。下一步必须由用户在新的独立顶层消息明确授权该窗口，再新建 execution revision；不得把本零请求 ledger 改成可执行结果、后台等待或自动恢复。

## P4D GR3Q5 — policy-aware render adapter recovery

`reports/81~85` 继续保留为合法的 zero-request authorization-gate 历史；`reports/86~88` 才是 authorized Window01 的实际执行历史。Window01 实际为 30 success、1 `CONTENT_POLICY_REFUSAL_CONFIRMED`，因此 Q5 以 132 verified successes / 308 outstanding 开始。

Q5 adapter smoke `PF_P4D_POS_CURLED_G003_V03` 使用 `CODEX_SAFE_STAGED_CV_V1` 成功。Q5 总共发出 11 logical invocations：10 success、0 policy refusal、0 completion unknown；第 11 条 `PF_P4D_NEG_CHAIR_G003_V03` 返回明确的 `HTTP429 usage_limit_reached`，native retry events=6，因此按全局停止规则终止。Q5 的当前真实 inventory 为 `CURRENT_VERIFIED_SUCCESS=142`、`CURRENT_OUTSTANDING=298`；`P4D_IMAGES_ACCEPTED=0`，不表示人工拒绝。

Q5 terminal status=`STOPPED_PROVIDER_429`，terminal freeze SHA-256=`3c219c9d75803cd5427862c0255ab557e92969085a864b116435aea85f8817f2`。本阶段没有 formal ingest、C3、VAL、HOLDOUT 或 production/Ollama 修改；数据集 validator 仍为 valid、0 errors、full hash true、387 historical warnings。后续只能在 provider reset 后取得新的独立授权 window；不得自动等待、重试或继续当前 terminal revision。

## P4D GR3Q6 — balanced quota-reset recovery preparation

Q5 remains `STOPPED_PROVIDER_429`; its terminal freeze was reverified with
sidecar match and all 40 bound artifacts matching SHA-256
`3c219c9d75803cd5427862c0255ab557e92969085a864b116435aea85f8817f2`.
Its frozen counters (`native_retry_events=6`, `physical_attempt_lower_bound=17`)
are historical records and were not changed.  A separate raw-SSE erratum parses
the immutable failed-slot JSON event stream instead of counting substrings and
obtains 3 unique `retry_scheduled` events and 14 physical attempts lower bound
(10 successful one-attempt slots plus 4 `request.started` events for the
HTTP429 slot).  This changes neither Q5 status nor its stop reason.

`P4D_GR3Q6_BALANCED_QUOTA_RESET_RECOVERY` rebuilt the authoritative inventory
as 142 verified successes / 298 outstanding, no completion ambiguity, with
role `hard_negative=105, positive=20, ordinary_negative=17` and split
`NEW_DESIGN=87, NEW_SCREEN=55`.  The actual reset time (`2026-08-31
00:14:53+08:00`) has passed, but that time gate is not an authorization.

The frozen Q6 preparation plan contains 33 unique outstanding slots: three
NEW_DESIGN chair rows first (`PF_P4D_NEG_CHAIR_G003_V03/V04/V05`), then two
hard-negative and four positive complete groups.  Its role mix is HN=10,
POS=20, ordinary-negative=3 and split mix is DESIGN=18, SCREEN=15.  It retains
`CODEX_SAFE_STAGED_CV_V1`; semantic frozen prompts remain unchanged and
provider render prompts are deterministic provenance artifacts.  The Q6
preparation freeze SHA-256 is
`0895c36bb13ce7fbd7c8eebb24deeea6ba650ef6247c294cc9656722b19dd900`.

```text
P4D_GR3Q6_STATUS=AWAITING_Q6_GENERATION_AUTHORIZATION
STOP_REASON=EXPLICIT_Q6_GENERATION_AUTHORIZATION_MISSING
PROVIDER_REQUESTS=0
LOGICAL_INVOCATIONS=0
Q6_SUCCESS=0
P4D_IMAGES_ACCEPTED=0
FORMAL_INGEST=false
C3=false
VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

The pre-authorisation runner includes a JSON-event retry parser and a 33-slot
WAL/full-synchronous `NOT_STARTED` ledger, but its execute gate refuses until a
new top-level Q6 authorization is independently bound to a new execution
freeze.  The shared dataset validator remained valid with 0 errors, full-hash
true, and the same 387 historical warnings; active P4D references remain 0.
No provider request, formal ingest, C3, VAL, HOLDOUT, production write, or
Ollama change occurred.  See [95 telemetry erratum](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/95_p4d_gr3q5_retry_telemetry_erratum.md), [96 preflight](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/96_p4d_gr3q6_preflight_and_reset.md), [97 plan](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/97_p4d_gr3q6_balanced_33_plan.md), and [100 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/100_p4d_gr3q6_final.md).

## P4D GR3Q6 — authorized execution and post-freeze correction

The prior Q6 pre-authorisation preparation remains preserved as
`AWAITING_Q6_GENERATION_AUTHORIZATION`; the later execution used a new,
separate revision after explicit top-level paid-generation authorization.  It
reverified the Q5, Q6 preparation, and Q6 supplemental freezes before the
first request, then ran the frozen 33-slot plan with `provider=codex`,
`request_model=gpt-5.4`, `generation_backend=image_generation`,
`CODEX_SAFE_STAGED_CV_V1`, concurrency 1, and outer retry false.

The first chair recovery rows V03/V04/V05 all generated successfully.  In all,
9 of 10 new logical invocations returned HTTP 200 and passed native/raw plus
Pillow/crop/LANCZOS/final-1920x1080 mechanical QA.  Q6 added 9 verified
generation artifacts, rebuilding the lineage to 151 verified successes and
289 outstanding slots; exact duplicate and GR1 SHA hits were zero.  No formal
ingest, C3, NEW_VAL, VAL, HOLDOUT, production, or Ollama operation occurred;
the final read-only validator was valid/0-errors/full-hash/387-warnings and
active P4D formal references remained zero.

The initial Q6 execution terminal freeze
(`95df937db097e23f2e3939fbd132f3e9a24a20bff3d0d91eb174285a082d8d52`) is
intact and verifies.  A post-freeze audit found its classifier made a material
mistake: the tenth slot `PF_P4D_HN_MAINT_G006_V02` ended with `network_error`,
no image, and unknown completion after 3 native retries / 4 physical attempts;
it was incorrectly marked policy refusal because the parser matched the SSE
metadata name `safety_identifier`.  The preserved raw evidence supports
`COMPLETION_UNKNOWN=1`, `POLICY_REFUSALS=0`, and
`P4D_GR3Q6_STATUS=STOPPED_COMPLETION_UNKNOWN`; the native retry guard was also
reached.  No eleventh request and no resend occurred.  The correction is
sealed separately and does not rewrite the original terminal freeze.  See
[98 execution](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/98_p4d_gr3q6_execution.md), [99 partial QA](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/99_p4d_gr3q6_partial_qa.md), and [101 corrected final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/101_p4d_gr3q6_execution_final.md).

## P4D GR3Q7 — completion-unknown quarantine and network-stability preparation

Q6's original terminal freeze and its post-freeze erratum seal were both
reverified, while remaining immutable.  The erratum is authoritative:
`PF_P4D_HN_MAINT_G006_V02` is `COMPLETION_UNKNOWN`, not policy refusal.  A
zero-provider-request local search found no late image bytes or request-bound
completion artifact, so it remains `COMPLETION_UNKNOWN_QUARANTINED` with
`NO_RESEND=true`.  G006 is partial (V01 success, V02 unknown) and Q7 excludes
the entire group.

Q7 rebuilt the frozen 440 universe into 151 verified successes, one quarantined
unknown, and 288 safe executable outstanding IDs, with all three sets pairwise
disjoint and exhaustive.  It created a structured failure classifier V2
(SHA-256 `fbd773b5d5d131f06abd334e041377fc5e0c7b9c0e5e6179164979c2abb624c0`)
that ignores metadata field names such as `safety_identifier`; immutable raw
regression cases for a real refusal, Q5 quota failure, and Q6 network ambiguity
all pass (3/3).

The frozen Q7 network-stability plan has 20 rows / four complete safe groups:
15 positive and 5 hard-negative, with NEW_DESIGN=10 and NEW_SCREEN=10.  It
uses intentional_ground_lying, multi_person_one_lying,
horizontal_corridor_ground_lying, and squat_crouch_deep_bend; it has zero G006
hits.  Semantic prompts, taxonomy, groups, splits, and Adapter V1 are unchanged.

```text
P4D_GR3Q7_STATUS=AWAITING_Q7_GENERATION_AUTHORIZATION
STOP_REASON=EXPLICIT_Q7_GENERATION_AUTHORIZATION_MISSING
PROVIDER_REQUESTS=0
LOGICAL_INVOCATIONS=0
FORMAL_INGEST=false
C3=false
VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

Q7's task text is not a paid-generation authorization.  Its read-only provider
audit resolved `codex/gpt-5.4/image_generation`, runtime 0.7.3, and no image
request was sent.  The shared dataset remains valid/0-errors/full-hash/387
historical warnings with active P4D references=0.  See [102 classifier erratum](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/102_p4d_gr3q6_failure_classifier_erratum.md), [103 forensics](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/103_p4d_gr3q7_completion_unknown_forensics.md), [104 classifier V2](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/104_p4d_gr3q7_failure_classifier_v2.md), [105 plan](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/105_p4d_gr3q7_balanced_20_plan.md), and [108 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/108_p4d_gr3q7_final.md).

## P4D GR3Q7 — authorized network-stability execution

The prior Q7 preparation remains preserved as `AWAITING_Q7_GENERATION_AUTHORIZATION`.
After a separate explicit paid-generation authorization, a new independent
`quota_campaign_window_04_gr3q7_authorized_20260831_01` execution revision
verified the Q7 preparation freeze `9ac34d6335c48883845e1bcb8d254596623a13f9625d93a406570d80461cc8c5`,
the supplement freeze `5df11b38536a05afb0fec14b89cb6f61a31bafb5dc6f8fef1cc686b371f6d859`,
the Q6 original freeze, the Q6 erratum seal, the frozen 20-slot plan, and
Failure Classifier V2.  The historical Q6 erratum has one expected current
bound-artifact drift: this append-only overview was extended by later stages;
the Q7 supplement freeze binds its pre-execution state.  No historical freeze
was overwritten.

The frozen 20-slot plan completed at its logical cap: `HTTP200=20`, success=20,
policy refusals=0, other confirmed failures=0, new completion unknown=0,
unique native retry events=2, physical-attempt lower bound=22, and no 429,
401, 403, 5xx, timeout, or network error.  The final status is
`WINDOW_CAP_REACHED_SUCCESS`; no 21st request was sent.  `MAINT_G006` requests
were zero and `PF_P4D_HN_MAINT_G006_V02` remains completion-unknown quarantined
with no resend.

Mechanical QA passed for 20 raw / 20 final images with zero Pillow failures,
dimension failures, exact duplicate hits, and GR1 SHA hits.  The exhaustive
frozen-440 partition is now 171 verified successes, 1 completion-unknown
quarantine, and 268 safe executable outstanding slots.  `P4D_IMAGES_ACCEPTED=0`
remains a statement that human semantic review has not started, not a rejection
count.  There was no formal ingest, C3, VAL, HOLDOUT, production, or Ollama
operation.  The shared dataset validator remained valid with 0 errors,
full-hash=true, 387 historical warnings, and active P4D references=0.

One provider-output limitation is preserved for subsequent governance: every
raw image returned at `1672×941` although the request used `1536×1024`.
The frozen Q7 mechanical dimension check applies to final `1920×1080` files,
which all passed; `dimension failures=0` is therefore not a claim that the
provider honored raw-size identity.  This does not authorize a retry or a
historical rewrite.

The terminal freeze SHA-256 is `9adc539e0b55a9207111b025bebdefcc4951760616b83f9680f91df28ef5aaf9`,
with matching sidecar and 78/78 bound artifacts.  See [106 execution](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/106_p4d_gr3q7_execution.md), [107 partial QA](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/107_p4d_gr3q7_partial_qa.md), and [109 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/109_p4d_gr3q7_execution_final.md).  Any later continuation requires a new explicit authorization and a new isolated revision.

## P4D GR3Q8 — balanced stable authorized window

Q8 independently reverified Q7’s intact terminal freeze and rebuilt the frozen-440 state as 171 verified successes, one quarantined completion-unknown, and 268 safe outstanding slots. The Q8 25-slot plan SHA-256 was `d8fd7ffbd0259d66a4707c01746b6b23c7195808557c7f0eb675ce7abb0c6e22`: positive=15, hard-negative=10, ordinary-negative=0, DESIGN=15, SCREEN=10, with zero MAINT_G006 requests.

The new execution revision ran all 25 authorized requests using `codex/gpt-5.4/image_generation`, runtime 0.7.3 and Adapter V1: `HTTP200=25`, 429/401/403/5xx/network/timeouts=0, policy refusals=0, new completion-unknown=0, retry events=0 and physical lower bound=25. It stopped at the logical cap without a 26th request. Q8 produced 25 raw and 25 final images; mechanical QA passed with zero Pillow failures, final-dimension failures, duplicate hits, GR1 SHA hits, or foreign-event assets. The raw provider size was again 1672×941 despite requested 1536×1024; raw-size fidelity remains unproven and no retry was made. Finals are all 1920×1080.

The resulting frozen-440 partition is 196 verified success, one completion-unknown quarantine and 243 safe outstanding. `P4D_IMAGES_ACCEPTED=0` continues to mean that human semantic review has not begun. Q8’s terminal freeze SHA-256 is `2235fff83e62b2daf05f736446ccc5819e599fd2c7112fdb788871ecc20d8477`, with sidecar and 95/95 artifacts matching. Unlike prior live-overview bindings, Q8 binds a revision-local immutable overview snapshot and does not bind this append-only file. There was no formal ingest, C3, VAL, HOLDOUT, production, or Ollama operation. See [110 preflight](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/110_p4d_gr3q8_preflight.md), [111 plan](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/111_p4d_gr3q8_balanced_25_plan.md), [112 execution](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/112_p4d_gr3q8_execution.md), [113 QA](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/113_p4d_gr3q8_partial_qa.md), and [114 final](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/114_p4d_gr3q8_final.md).
