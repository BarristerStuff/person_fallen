# 43 — P4D_GR3 full-regeneration plan

```text
REVISION_ID=P4D_FULLREGEN_CODEX_PROFILE2_20260827_01
BATCH_ID=batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m
NEW_IMAGES_REQUIRED=440
GR1_IMAGES_REUSED=0
PROMPT_MANIFEST_SHA=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
GROUP_SPLIT_SHA=b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843
NEW_DESIGN=265
NEW_SCREEN=175
GROUPS=88
CONCURRENCY=1
MICROBATCH=10
```

## 已确认事实

The 440-row plan points to frozen prompt paths and preserves the original
taxonomy, role quotas, group assignment, and NEW_DESIGN/NEW_SCREEN allocation.
It does not copy any old image bytes. Future execution order is preregistered
as smoke 1, sequential ramp 5, sequential ramp 10, then micro-batches of 10.

## 实验判断

This changes only image-generation lineage/account, not prompt semantics or
the experimental split. No execution runner is eligible while retry guarantee
is false and authorization is false.

## 风险与限制

All 440 logical generations are new quota/usage. Exact monetary cost is
`UNKNOWN`; no price was invented.

## 下一阶段建议

After retry and authorization gates pass, execute from zero in the new batch,
then mechanical/duplicate/lineage QA and human review. Do not ingest directly.
