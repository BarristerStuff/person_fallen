# 29 — P4D final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
CURRENT_BEST_SEMANTIC_CANDIDATE=C3
P3_WINNER=NONE
P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION
P4D_STATUS=GENERATION_REQUIRED
P4D_PROMPT_PACK_READY=true
P4D_NEW_LINEAGE=true
P4D_NEW_TOTAL=440
P4D_HARD_NEGATIVE=300
P4D_POSITIVE=100
P4D_ORDINARY_NEGATIVE=40
P4D_GROUPS=88
P4D_NEW_DESIGN=265
P4D_NEW_SCREEN=175
P4D_CROSS_SPLIT_GROUPS=0
P4D_C3_BASELINE_COMPLETE=false
P4D_NEW_VAL_REQUESTS=0
P4D_HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_DATASET_MUTATION=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

## 已确认事实

1. The P4D pre-generation group split and prompt pack are complete: 440
   complete prompts, 88 groups, 53/35 groups in NEW_DESIGN/NEW_SCREEN, and
   zero cross-split groups.  All prompts are new text-to-image lineage and
   the old batch was not used as a reference.
2. The configured provider capability audit was recorded.  The only actual
   generation request was the bounded smoke request for `PF_P4D_HN_SIT_G001_V01`.  It
   returned HTTP 401 `INVALID_API_KEY`; no image bytes were generated or
   accepted.
3. The formal dataset read-only validator stayed valid with zero errors and
   full hash check before and after.  No formal ingest, label write, split
   rewrite, VLM request, NEW_VAL request, or HOLDOUT request occurred.
4. `qwen3.5:4b`/Ollama capability was audited but not used for P4D C3 because
   the image-generation gate failed first.  P4D C3 classification metrics are
   `N/A`.

## 实验判断

The terminal state is `GENERATION_REQUIRED`, not a semantic failure and not a
negative result.  The provider error is an infrastructure/credential gate;
there is no evidence from which to estimate image quality, semantic label
quality, C3 protocol success, latency, or hard-negative FPR for P4D.

The Codex image provider was not substituted automatically.  Its local auth was
ready, but this environment showed no previous Codex image-generation history;
switching providers would change the generation/account lineage of the frozen
P4D plan and was not necessary to preserve the current audit boundary.

## 风险与限制

- `ebond-gpt-image-2` credential must be repaired or an explicitly authorized
  provider must be selected in a new, separately recorded generation decision.
- The one failed smoke request proves the observed credential failure only; it
  does not prove all providers or all credentials are unavailable.
- The planned split is a pre-generation group freeze, not a completed accepted
  image split.  No semantic or classification metric should be inferred from
  the plan.
- Existing historical P2/P3 VAL exposure and quality/runtime limitations remain
  unchanged.  The current P4D stop does not consume or alter HOLDOUT.

## 下一阶段建议

Repair/authorize the image provider, then create a new auditable generation
continuation under the same P4D lineage only if the provider decision and
retry policy are explicitly recorded.  Generate the frozen 440 prompts with
durable per-request logs, run mechanical QA, obtain reliable human semantic
review, and only then materialize the NEW_DESIGN/NEW_SCREEN image manifests.
Run C3 on NEW_DESIGN first and NEW_SCREEN once only after those gates pass.
Do not run NEW_VAL or the formal HOLDOUT in this stage, and do not start P2/P3
optimization from the failed smoke.

## Key artifacts

- prompt pack: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/01_prompt_plan/prompt_pack.md`
- prompt manifest: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/01_prompt_plan/prompt_manifest.csv`
- generation attempts: `/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m/generation_attempts.csv`
- capability decision: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/00_preflight/generation_capability_decision.json`
- final terminal freeze: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/freeze/p4d_generation_required_freeze.json`
- final report: `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/29_p4d_final_report.md`
