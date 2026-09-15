# P4D GR3Q6 balanced 33-slot plan

## 已确认事实

The authoritative inventory was rebuilt from the frozen 440-slot manifest,
Q5 ledger, and verified-success lineage.  It contains 142 verified successes
and 298 outstanding slots, with `COMPLETION_UNKNOWN=0`.

```text
STARTING_SUCCESS_ROLE=hard_negative:105, positive:20, ordinary_negative:17
STARTING_SUCCESS_SPLIT=NEW_DESIGN:87, NEW_SCREEN:55
OUTSTANDING_ROLE=hard_negative:195, positive:80, ordinary_negative:23
OUTSTANDING_SPLIT=NEW_DESIGN:178, NEW_SCREEN:120

Q6_PLAN_ROWS=33
Q6_UNIQUE_PROMPT_IDS=33
Q6_INTERSECTION_WITH_VERIFIED_SUCCESS=0
Q6_ROLE=hard_negative:10, positive:20, ordinary_negative:3
Q6_SPLIT=NEW_DESIGN:18, NEW_SCREEN:15
ADAPTER_VERSION=CODEX_SAFE_STAGED_CV_V1
SEMANTIC_FROZEN_PROMPT_CHANGED=false
PROVIDER_RENDER_PROMPT_CHANGED=true
```

The first three immutable plan rows are:

1. `PF_P4D_NEG_CHAIR_G003_V03` — Q5 HTTP429 recovery probe, NEW_DESIGN.
2. `PF_P4D_NEG_CHAIR_G003_V04` — same partial chair group, NEW_DESIGN.
3. `PF_P4D_NEG_CHAIR_G003_V05` — same partial chair group, NEW_DESIGN.

The remaining six complete five-slot groups balance normalized taxonomy
deficit and frozen split constraints.  Their taxonomies are
`crawling_quadruped_support`, `ground_maintenance`,
`intentional_ground_lying`, `multi_person_one_lying`,
`horizontal_corridor_ground_lying`, and `side_lying`: two distinct
hard-negative groups, four distinct positive groups, three groups per split.

## 实验判断

The plan is materially more balanced than continuing an old sequential order:
if all 33 later succeed, the computed inventory would be 175 successes / 265
outstanding, with hard-negative=115, positive=40, ordinary-negative=20 and
NEW_DESIGN=105 / NEW_SCREEN=70.  These are projections only, not results.

## 风险与边界

The plan has been frozen for reproducibility; it is not authorization to run.
No generated image is semantically accepted, and `P4D_IMAGES_ACCEPTED=0`
remains an absence of human review, not a rejection.
