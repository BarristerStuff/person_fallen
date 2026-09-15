# 34 — P4D_GR1 generation resume final report

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
ORIGINAL_PROVIDER=ebond-gpt-image-2
PROVIDER_CHANGED=true
ORIGINAL_EBOND_SUCCESSFUL_IMAGES=0
ORIGINAL_EBOND_FAILED_ATTEMPTS=1
GENERATION_ATTEMPTS_GR1=226
GENERATION_SUCCESSFUL_GR1=192
GENERATION_FAILED_GR1=34
GENERATION_LATENCY_MEAN=47.47718898958333
GENERATION_LATENCY_P50=44.2377945
GENERATION_LATENCY_P95=71.171872
GENERATION_LATENCY_MAX=113.52491
RAW_SUCCESSFUL_IMAGES=192
FINAL_IMAGES=192
C3_EXECUTED=false
DESIGN_PROTOCOL_GATE=N/A
SCREEN_PROTOCOL_GATE=N/A
DESIGN_TP/FP/TN/FN=N/A
SCREEN_TP/FP/TN/FN=N/A
DESIGN_PRECISION/RECALL/F1/ACCURACY=N/A
SCREEN_PRECISION/RECALL/F1/ACCURACY=N/A
DESIGN_ORDINARY_NEGATIVE_FPR=N/A
DESIGN_HARD_NEGATIVE_FPR=N/A
DESIGN_POSITIVE_RECALL=N/A
SCREEN_ORDINARY_NEGATIVE_FPR=N/A
SCREEN_HARD_NEGATIVE_FPR=N/A
SCREEN_POSITIVE_RECALL=N/A
DESIGN_MODEL_UNCERTAIN_RATE=N/A
SCREEN_MODEL_UNCERTAIN_RATE=N/A
TAXONOMY_AGGREGATE=N/A
GROUP_AGGREGATE=N/A
DESIGN_LATENCY=N/A
SCREEN_LATENCY=N/A
SUSTAINED_HIGH_LOAD_C3=N/A
METRIC_RECOMPUTE_MATCH=N/A_C3_NOT_RUN
""`

## 已确认事实

## Provider revision and generation resume

- Original provider: `ebond-gpt-image-2` / `gpt-image-2`; its one smoke attempt remains permanently preserved as attempt 1 and returned HTTP 401 `INVALID_API_KEY`.
- Active revision: `P4D_GR1_PR_CODEX_20260827_01`, provider `codex`, model `gpt-5.4` using the authenticated Codex image-generation wrapper (delegated image capability: `gpt-image-2`).
- `provider_changed=true` was recorded because the old provider had 0 successful images and an observed credential failure. Prompt/group/taxonomy/frozen split hashes were unchanged.
- Stage gates: smoke `PASS`, Stage1 `PASS`, Stage2 `PASS`, bulk `FAIL_AUTH`.
- GR1 phase counts (successful rows): `{"BULK": 166, "RAMP1": 5, "RAMP2": 20, "SMOKE": 1}`; native output sizes observed: `{"1672x941": 192}`; controlled final sizes: `{"1920x1080": 192}`.
- No API key is written to the revision, request, raw-response, or provider-result artifacts; credential-like output is sanitized.
- The bulk gate stopped after 200/414 scheduled bulk attempts: 166 successes and 34 failures (32 HTTP 429 usage-limit responses, followed by 2 HTTP 401 `refresh_token_invalidated` responses).  Automatic retry remained `false`; no failed slot was recovered.


## Mechanical QA and lineage audit

- Independent partial audit: `192/440` prompt slots have successful ledger rows and existing images; `192` rows pass the mechanical checks and `248` are missing because generation stopped.  The full mechanical-QA gate was **not reached**.
- Exact final-image duplicate count: `0`; connected-component near-duplicate groups: `0`; cross-split near-duplicate pairs: `0`.
- Prompt-image mapping summary: `NOT_REACHED` (the complete 440-row mapping gate was not reached).
- Metadata-only shortcut audit was retained as a diagnostic; no model predictions were used, and no image was deleted or relabeled from it.
- Native provider output was actually observed as `{"1672x941": 192}` and normalized by controlled center crop + Pillow LANCZOS to exact `1920x1080`; the request's nominal `1536x1024` was not silently treated as actual native size.
- Validator before: `valid`, errors `0`, full hash `true`, warnings `387`, counts `media=4201/labels=4201/batches=41/splits=2058`; validator after: `valid`, errors `0`, full hash `True`, warnings `387`, counts `media=4521/labels=4521/batches=43/splits=2058`.
- Shared-dataset boundary audit: `{"active_annotation_sha256": {"/home/yanbo/net_vlm_xunjian_dataset/01_annotations/batches.csv": "e166de60b418f42dceb0ccc77ba01e549cb1930f2ab08f4a62d5792329200a45", "/home/yanbo/net_vlm_xunjian_dataset/01_annotations/labels.csv": "a12c08e587196350557749e1d24c138f089d8d96db27bcd458ff4c693de5ca54", "/home/yanbo/net_vlm_xunjian_dataset/01_annotations/media.csv": "6fd2e03b38012df827a756dd299e1e99444f71bc1afd5181ac0f241096fdc518", "/home/yanbo/net_vlm_xunjian_dataset/01_annotations/splits.csv": "967018452f8fe5334b438a6be554d3333533cd947fd52c0ccf66f594c8439c18"}, "after_counts": {"batch_count": 43, "label_count": 4521, "media_count": 4521, "split_count": 2058}, "before_counts": {"batch_count": 41, "label_count": 4201, "media_count": 4201, "split_count": 2058}, "before_validator_artifact": "/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/00_preflight/dataset_validator_gr1_before.json", "captured_at": "2026-08-27T08:02:25.214+00:00", "count_delta": {"batch_count": 2, "label_count": 320, "media_count": 320, "split_count": 0}, "interpretation": "The shared dataset changed outside P4D_GR1 while generation was running; no P4D token/reference was found in active annotation CSVs, so the observed delta is not attributed to P4D formal ingest.", "p4d_formal_ingest_detected": false, "p4d_reference_hits_by_active_csv": {"/home/yanbo/net_vlm_xunjian_dataset/01_annotations/batches.csv": 0, "/home/yanbo/net_vlm_xunjian_dataset/01_annotations/labels.csv": 0, "/home/yanbo/net_vlm_xunjian_dataset/01_annotations/media.csv": 0, "/home/yanbo/net_vlm_xunjian_dataset/01_annotations/splits.csv": 0}, "p4d_reference_hits_total": 0, "post_baseline_label_rows": 320, "post_baseline_media_capture_batches": {"P5_DEV_20260827": 200, "P5_VALIDATION_20260827": 120}, "post_baseline_media_rows": 320}`.  The observed post-baseline rows are attributed to their recorded external capture batches only when the active CSV evidence supports that attribution; P4D references were not used or ingested.


## Semantic review and formal ingest gate

Generation/mechanical QA did not complete because the provider-auth recurrence gate stopped the 440-slot run.  Human semantic review was therefore **not reached** and no review package was promoted or used as ground truth.  If a future authorized continuation completes generation, it must create the review package and obtain explicit human approval before ingest.

`FORMAL_INGEST_EXECUTED=false`, `MEDIA_ADDED=0`, and `LABELS_ADDED=0`.  No shared CSV was hand-edited, no NEW_DESIGN/NEW_SCREEN materialization occurred, and no C3 request was made.  Explicit human semantic approval is required before any later ingest transaction.


## C3 new-lineage execution

`C3_EXECUTED=false` because provider-auth recurrence stopped generation before human semantic review.  NEW_DESIGN (265) and NEW_SCREEN (175) remain the pre-frozen intended groups, but no image was promoted into formal dataset rows and no C3 classification queue was built.

All C3 protocol, deterministic classification, taxonomy, group, latency, sustained-load, and recomputation metrics are `N/A` (not zero).  No NEW_VAL or formal HOLDOUT request occurred; `C3_EXECUTED=false
DESIGN_PROTOCOL_GATE=N/A
SCREEN_PROTOCOL_GATE=N/A
DESIGN_TP/FP/TN/FN=N/A
SCREEN_TP/FP/TN/FN=N/A
DESIGN_PRECISION/RECALL/F1/ACCURACY=N/A
SCREEN_PRECISION/RECALL/F1/ACCURACY=N/A
DESIGN_ORDINARY_NEGATIVE_FPR=N/A
DESIGN_HARD_NEGATIVE_FPR=N/A
DESIGN_POSITIVE_RECALL=N/A
SCREEN_ORDINARY_NEGATIVE_FPR=N/A
SCREEN_HARD_NEGATIVE_FPR=N/A
SCREEN_POSITIVE_RECALL=N/A
DESIGN_MODEL_UNCERTAIN_RATE=N/A
SCREEN_MODEL_UNCERTAIN_RATE=N/A
TAXONOMY_AGGREGATE=N/A
GROUP_AGGREGATE=N/A
DESIGN_LATENCY=N/A
SCREEN_LATENCY=N/A
SUSTAINED_HIGH_LOAD_C3=N/A
METRIC_RECOMPUTE_MATCH=N/A_C3_NOT_RUN`


## 实验判断

    The Codex revision passed smoke and both ramp gates but the bulk provider hit a usage-limit/authentication recurrence; the frozen generation is incomplete and the correct terminal state is provider-auth blocked, with no recovery or downstream evaluation.

    The provider revision kept the frozen P4D prompt/group/taxonomy design unchanged.  No semantic-quality claim and no formal C3 baseline exist.

## 风险与限制

- The active provider is a different authenticated provider/account lineage from the failed EBOND attempt; this is recorded as a new generation revision and should not be compared to EBOND as if it were the same provider run.
- The image service normalized requested `1536x1024` output to the observed native `{"1672x941": 192}`; final files are controlled `1920x1080` derivatives. Native-vs-final dimensions must remain explicit in later C3 reports.
- Metadata shortcut checks cannot establish semantic correctness. Human review must inspect every image without C3 predictions and retain `accepted`, `rejected`, and `uncertain` outcomes.
- No C3 metrics, taxonomy metrics, group metrics, latency metrics, or hard-negative FPR exist yet; they must remain `N/A` until formal ingest and the one-pass C3 gates are authorized.

## 下一阶段建议

    1. Do not retry the 401/429 failed slots in this closed revision.  First obtain a fresh, explicitly authorized provider/session and register a separate continuation/revision with a new preflight decision.
2. Only after a complete 440-slot generation and mechanical/lineage gates pass, perform human semantic review; model outputs must not generate or override labels.
3. If and only if explicit human approval is complete, run transactional ingest/materialization and then C3 DESIGN followed by SCREEN once.  Do not run NEW_VAL or the formal HOLDOUT.

## Artifact hashes

```json
{
  "08_p4d_new_hard_negative_dev_revision/00_preflight/dataset_validator_gr1_boundary_audit.json": "e953e4f6f93c43f9eda9c9fc99b922d0e2bf2c521f99d9cc1a4effcd20753151",
  "08_p4d_new_hard_negative_dev_revision/02_generation/gr1/generation_attempts.csv": "20e00361c532f8386d3f160363cc76d12f104618b6c9fd270d2ec5c78a1a2fd4",
  "08_p4d_new_hard_negative_dev_revision/02_generation/gr1/raw_responses.jsonl": "cd7ad49cafac28b179983e4958ec73222cf70102c4a9555ee7e6e7dafde2bbf0",
  "08_p4d_new_hard_negative_dev_revision/02_generation/gr1/request_log.jsonl": "961b06a9e22cad84a4f3762f1cb9b989b29bf7c68b598271de7a2a044d676e6b",
  "08_p4d_new_hard_negative_dev_revision/03_intake_audit/gr1_independent_qa_summary.json": "376375e6485cce3cbbeabf8f1aec2e3bda2f88379b43a062a172ad0e08c3195c",
  "08_p4d_new_hard_negative_dev_revision/03_intake_audit/gr1_near_duplicate_groups.csv": "352e607e555bce97f0b061b8f8850fd770e653034af95152a688cd8744ff9969"
}
```
