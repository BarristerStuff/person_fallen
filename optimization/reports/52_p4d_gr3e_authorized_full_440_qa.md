# 52 — P4D_GR3E authorized full 440 QA

```text
P4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT
FULL_440_QA_STATUS=NOT_REACHED_INCOMPLETE_GENERATION
PARTIAL_SUBSET_SCOPE=99
PARTIAL_PILLOW_RAW_PASS=99
PARTIAL_PILLOW_FINAL_PASS=99
PARTIAL_DIMENSION_PASS=99
RAW_EXACT_DUPLICATES=0
FINAL_EXACT_DUPLICATES=0
NEAR_DUPLICATE_GROUPS=0
CROSS_SPLIT_NEAR_DUPLICATES=0
MAPPING_ROWS=440
MAPPING_PASS=99
MISSING_MAPPINGS=341
GR1_HASH_HITS=0
SAMEFILE_HITS=0
```

## 已确认事实

A post-stop subset audit verified all `99` generated raw/final pairs with Pillow and final dimensions `1920x1080`; raw and final filenames exactly match the successful ledger IDs. The full 440 gate is explicitly `NOT_REACHED`, because 341 slots are not successful. Partial mapping has `99` PASS and `341` missing rows.

The subset audit found raw exact duplicate count `0`, final exact duplicate count `0`, near-duplicate groups `0`, cross-split near-duplicate pairs `0`, old-GR1 hash hits `0`, and same-file hits `0`.

## 实验判断

These subset results cannot be promoted to the required full-440 QA status and cannot trigger semantic acceptance or replacement decisions for the unfinished revision.

## 风险与限制

No claim is made about missing slots. The `replacement_required` gate is not evaluated before a complete 440 successful inventory.

## 下一阶段建议

Use the independent recovery protocol only after the provider usage-limit condition and the non-resend/lineage policy are separately resolved.
