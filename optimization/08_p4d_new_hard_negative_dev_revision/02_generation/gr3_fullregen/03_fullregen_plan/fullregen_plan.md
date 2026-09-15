# P4D_GR3 full-regeneration plan

```text
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
REVISION_ID=P4D_FULLREGEN_CODEX_PROFILE2_20260827_01
BATCH_ID=batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m
TOTAL_SLOTS=440
GROUPS=88
HARD_NEGATIVE=300
POSITIVE=100
ORDINARY_NEGATIVE=40
NEW_DESIGN=265
NEW_SCREEN=175
CROSS_SPLIT_GROUPS=0
GR1_IMAGES_REUSED=0
PROMPT_CHANGED=false
GROUP_PLAN_CHANGED=false
TAXONOMY_CHANGED=false
SPLIT_CHANGED=false
```

The manifest points to the already frozen prompt bytes and contains no copied
prompt/image bytes from GR1 or GR2. The new batch has empty `generated_raw/`
and `final/` directories. Any future generation must be separately authorized,
use concurrency 1, stop globally on the first 429/401/403, and remain at the
logical 440-slot scope.
