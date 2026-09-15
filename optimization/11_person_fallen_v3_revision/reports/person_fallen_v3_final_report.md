# `person_fallen` v3.0 final reevaluation report

**Decision:** `MODEL_SIDE_LIMIT_REACHED`  
**Revision:** `PERSON_FALLEN_V3_ANOMALOUS_NEAR_GROUND_20260901_01`  
**Decision time:** `2026-09-01T19:21:00+08:00`

## 1. Independent judgment

The requested v3.0 lifecycle was implementable as an isolated, prompt-derived
synthetic-GT evaluation, but it was not safe to treat the two development
candidate runs as acceptance evidence after either failed the preregistered
hard-negative gate. The v3 lifecycle therefore stops at the DEV gate.

The v2.0/P4D history is not rewritten. The v3.0 decision also does not resume
the old 440-slot P4D requirement, Q10, completion-unknown work, or any further
provider generation. That continuation is explicitly superseded for this v3
lifecycle and remains a separate historical state.

## 2. Confirmed facts

### Definition and data boundary

- The event definition is `person_fallen`, version `v3.0`, meaning an
  **anomalous near-ground posture**. Positive covers a person lying on the
  ground, collapsed, or unable to maintain upright posture. Negative covers
  intentional/functional near-ground postures such as sitting, kneeling,
  crouching, crawling, or active push-up/plank. Maintenance/inspection is
  negative only when visible maintenance evidence is present. Ambiguous or
  materially occluded cases are `uncertain`.
- The v3 ground-truth policy is
  `FROZEN_GENERATION_PROMPT_AND_PLANNED_ROLE` and
  `PROMPT_DERIVED_SYNTHETIC_GT`. `model_prediction_used_as_gt=false` and
  `human_semantic_review_required=false` are both bound in the protocol.
- The 500-row v2 synthetic lineage and the 202-row P4D fast-close clean view
  were reused only through a new deterministic v3 remap. The v2 Holdout 90
  rows and every P4D row that was binding-blocked, completion-unknown,
  confirmed-failed, not-started, or otherwise not reusable were excluded from
  v3 formal evaluation.
- The v3 lineage contains 940 rows. The v3 formal evaluation manifests contain
  612 rows: `V3_DEV=436`, `V3_SCREEN=76`, and `V3_VAL=100`; labels are
  `positive=251`, `negative=341`, `uncertain=20`. The DEV manifest has
  `positive=186`, `negative=230`, `uncertain=20` across 57 groups.
- Remap ambiguity is zero and group cross-split leakage is zero. The v3 DEV
  manifest contains zero Holdout rows. Source image SHA, prompt SHA, GT, and
  metric-stratum checks were independently recomputed for both completed runs.

### Runtime and execution

Both candidates used the same model and binding:

- model: `qwen3.5:4b`
- model digest:
  `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`
- Ollama: `0.23.2` at `http://192.168.20.62:11434`
- temperature `0`, `think=false`, strict JSON, one image per request,
  letterbox preprocessing, `CONCURRENCY=1`, no automatic retries, and no
  completion-unknown resends
- all 872 DEV requests completed with HTTP 200, schema success `100%`, strict
  JSON success `100%`, confirmed failures `0`, and transport unknowns `0`.

### DEV gate results

The gate requires precision `>=0.93`, recall `>=0.95`, hard-negative FPR
`<=0.05`, ordinary-negative FPR exactly `0`, and strict JSON success `100%`.

| Candidate | TP/FN/TN/FP | Precision | Recall | Hard-negative FPR | Ordinary-negative FPR | Result |
|---|---:|---:|---:|---:|---:|---|
| `V3-C0-448` (`448x336`) | `185/1/193/37` | `0.8333` | `0.9946` | `0.2387` (`37/155`) | `0.0000` (`0/75`) | `FAIL` |
| `V3-C0-896` (`896x672`) | `185/1/195/35` | `0.8409` | `0.9946` | `0.2258` (`35/155`) | `0.0000` (`0/75`) | `FAIL` |

The 896 candidate reduces false positives slightly, but remains far above the
hard-negative limit and below the precision limit. This is a model-side gate
failure, not a transport or manifest-integrity failure.

## 3. Reasoning and status

Because both preregistered resolutions failed on the same hard-negative
dimension, there is no valid DEV winner to freeze. Running SCREEN or VAL would
be downstream evaluation without a frozen candidate and would create a
misleading acceptance trail. They were not run. No Final Holdout request was
made and no Holdout was consumed.

The status is therefore:

```text
EVENT=person_fallen
EVENT_DEFINITION_VERSION=v3.0
V3_STATUS=MODEL_SIDE_LIMIT_REACHED
V3_DEV_448=COMPLETE_GATE_FAIL
V3_DEV_896=COMPLETE_GATE_FAIL
V3_WINNER=NONE
SCREEN=NOT_RUN_NO_DEV_WINNER
VALIDATION=NOT_RUN_NO_DEV_WINNER
READY_FOR_FINAL_HOLDOUT=false
FINAL_HOLDOUT_REQUESTS=0
FINAL_HOLDOUT_CONSUMED=false
HUMAN_SEMANTIC_REVIEW_REQUIRED=false
MODEL_PREDICTION_USED_AS_GT=false
STOP_FURTHER_P4D_GENERATION=true
FORMAL_DATASET_INGEST=false
PRODUCTION_CODE_OR_DATASET_MODIFIED=false
```

## 4. Risks and limitations

- Prompt-derived synthetic GT is operationally reproducible, but it is not a
  human semantic truth set. The v3 result must not be reported as Human Gold,
  robot-direct, production, or Final Holdout performance.
- The 100-row v3 VAL manifest reuses non-Holdout v2 lineage and was not run
  because no DEV winner existed. Even if it were run, its historical use in
  v2 would need to remain explicit in any future claim.
- The dominant failure is false alerting on hard negatives: 37/155 at 448 and
  35/155 at 896. Increasing resolution alone did not approach the required
  5% ceiling. This evidence does not establish whether the cause is model
  capability, prompt semantics, visual ambiguity, or synthetic-data bias.
- No prompt, model, threshold, or GT tuning was performed after seeing DEV
  results. A future improvement must start a new separately authorized,
  self-consistent revision with its own binding and fresh development policy;
  it must not mutate this failed record.

## 5. Evidence index

- [v3 definition](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/definition/person_fallen_v3_definition.md)
- [v3 prompt](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/prompt/V3-C0_prompt.txt)
- [v3 protocol](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/protocol/person_fallen_v3_protocol.json)
- [v3 evaluation config](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/protocol/v3_eval_config.json)
- [binding audit](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/protocol/v3_binding_audit.json)
- [DEV decision](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/freeze/person_fallen_v3_dev_decision.json)
- [448 summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/eval/runs/dev_V3-C0-448/summary.json)
- [896 summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/eval/runs/dev_V3-C0-896/summary.json)
- [v3 remap audit](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_remap_audit.json)
- [v3 DEV manifest](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_dev_manifest.csv)
- [v2 review supersession notice](/home/yanbo/net_vlm_person_fallen_v2_optimization/10_fast_close/FAST_CLOSE_HUMAN_REVIEW/V3_SUPERSESSION_NOTICE.md)

The reproducible runner is
`/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/tools/run_v3_eval.py`.
The official shared dataset validator was not used as a reason to accept v3;
the v3 decision is based on the isolated manifests and the two bound DEV runs.
