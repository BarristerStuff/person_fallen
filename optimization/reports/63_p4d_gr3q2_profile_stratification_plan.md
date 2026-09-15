# 63 — P4D GR3Q2 profile stratification plan

```text
PROFILE_A=GR3E_PROFILE_A
PROFILE_A_COUNT=99
PROFILE_B=GR3Q2_PROFILE_B
PROFILE_B_COUNT=341
PROFILE_STRATIFICATION_REQUIRED=true
PROFILE_ROLE_CONFOUNDING=true
PROFILE_TAXONOMY_CONFOUNDING=true
PROFILE_SPLIT_CONFOUNDING=true
PROFILE_IS_GT_FEATURE=false
PROFILE_IS_C3_INPUT=false
```

## 已确认事实

Profile-A contains 99 hard negatives only: floor-sitting 60 and kneeling/half-kneeling 39; its split allocation is NEW_DESIGN 70 and NEW_SCREEN 29. Profile-B contains 201 hard negatives, all 100 positives, and all 40 ordinary negatives; its split allocation is NEW_DESIGN 195 and NEW_SCREEN 146.

## 合理推理

This is severe profile×role/taxonomy confounding. Split confounding is not deterministic because both strata appear in both splits, but the NEW_DESIGN proportions differ: A 70/99 versus B 195/341.

## 风险与限制

After all 440 images are generated, mechanically valid, deduplicated, and human-reviewed, profile-stratified diagnostics must compare native dimensions, latency, file size, perceptual-hash distributions, scene/taxonomy allocation, and obvious visual style. Do not use the profile field for truth or prediction.
