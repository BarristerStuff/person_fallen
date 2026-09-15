# 41 — P4D_GR3 full-regeneration preflight

```text
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
P4D_STATUS=GENERATION_REQUIRED
FULL_REGEN_REQUIRED=true
FULL_REGEN_AUTHORIZED=false
GR1_IMAGES_REUSED=0
PLANNED_NEW_IMAGES=440
PROMPT_CHANGED=false
GROUP_PLAN_CHANGED=false
TAXONOMY_CHANGED=false
SPLIT_CHANGED=false
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
VAL=0
HOLDOUT=0
```

## 已确认事实

- P4D frozen artifacts: `all_match=true`.
- GR1 freeze verified: `true`; GR2 terminal freeze verified: `true`.
- The new revision is `P4D_FULLREGEN_CODEX_PROFILE2_20260827_01` with new batch `batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m` at `/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m`. Its full-regeneration manifest has 440 rows and SHA-256 `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`.
- Prompt bytes match the frozen source for all 440 rows; role counts are 300 hard-negative / 100 positive / 40 ordinary-negative; split is NEW_DESIGN 265 / NEW_SCREEN 175; groups are 88 with zero cross-split groups.
- The new batch has zero raw images, zero final images, and zero requests. The mechanical lineage audit at `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/00_preflight/lineage_isolation_audit.json` found `192` historical GR1 logical images (`192` raw + `192` final files), zero new-batch image files, zero symlinks, and zero old-image SHA collisions.
- No GR1 or GR2 image bytes were copied, symlinked, renamed, re-encoded, cropped, or resized into the new batch. Current Codex capability is `codex` / `gpt-5.4` / `image_generation (server-side gpt-image-2 capability)`, auth-ready `True`, session-ready `False`, endpoint-reachable `False`.
- The read-only dataset boundary was before counts `{'media_count': 4581, 'label_count': 4521, 'batch_count': 44, 'split_count': 2058}` and after counts `{'media_count': 4583, 'label_count': 4521, 'batch_count': 44, 'split_count': 2058}` with delta `{'media_count': 2, 'label_count': 0, 'batch_count': 0, 'split_count': 0}`; active P4D reference hits remained `0`.

## 实验判断

GR3 is a new lineage preparation, not GR2 continuation. Its current safe profile
is bound only as the proposed new identity; it is deliberately not merged with
GR1's historical profile.

## 风险与限制

The provider can be authenticated, but retry behavior is not safely bounded to
one provider operation per logical slot. Preparation therefore cannot advance
to an executable runner.

## 下一阶段建议

Resolve the retry-policy gate and obtain explicit user authorization before any
generation request. Keep `authorized=false` and all image directories empty.
