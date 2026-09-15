# 36 — P4D_GR2 generation continuation

```text
P4D_GR2_STATUS=FULL_REGEN_AUTHORIZATION_REQUIRED
P4D_STATUS=GENERATION_REQUIRED
GR1_PRESERVED_IMAGES=192
GR2_GENERATED_IMAGES=0
CURRENT_TOTAL_IMAGES=192
OUTSTANDING_SLOTS=248
SMOKE_REQUESTS=0
RAMP_REQUESTS=0
GR2_TOTAL_REQUESTS=0
GR2_FAILURES=0
HTTP_429=0
HTTP_401=0
HTTP_403=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## 已确认事实

GR1 remains read-only. Its 192 verified successes were preserved and skipped. The 248 outstanding slots were rebuilt from the frozen prompt manifest minus the verified success IDs; the historical failed slots remain represented in the new inventory without overwriting their GR1 rows. GR2 created an independent empty ledger with zero attempts and did not run smoke, ramp, or micro-batches.

## 实验判断

The provider/account lineage gate failed before the first actual outstanding smoke slot (`PF_P4D_HN_CRAWL_G005_V01`). Therefore `GR2_GENERATED_IMAGES=0` means no new provider-side generation was attempted; it is not a quota or image-quality metric.

## 风险与限制

The current profile may be valid for other work, but using it for continuation would make the frozen generation set mixed-account. The 192 preserved images cannot be silently regenerated or relabeled to hide that distinction.

## 下一阶段建议

Stop this GR2 revision. Continue only under a separately authorized revision that either proves the original profile continuity or authorizes a complete, explicitly new lineage; do not append attempts to GR1.
