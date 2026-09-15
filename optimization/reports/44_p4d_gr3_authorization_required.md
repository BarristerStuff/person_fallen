# 44 — P4D_GR3 authorization required

```text
P4D_GR3_NAME=P4D_GR3_FULL_REGEN_PREPARATION
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
FULL_REGEN_REQUIRED=true
FULL_REGEN_AUTHORIZED=false
NEW_GENERATION_LINEAGE=true
GR1_CONTINUATION=false
GR1_IMAGES_REUSED=0
PLANNED_NEW_IMAGES=440
PROVIDER_REQUESTS=0
FORMAL_INGEST=false
C3=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## 已确认事实

The authorization packet is `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/01_authorization/full_regen_authorization.json` and
explicitly contains `authorized=false`. It records current provider/model/
backend, safe profile fingerprint, 440 logical slots, zero old-image reuse,
concurrency 1, fail-fast 429/401/403, the retry limitation, and
`EXACT_MONETARY_COST=UNKNOWN`.

## 实验判断

User continuation messages do not constitute full-regeneration authorization.
The current preparation is correctly blocked before any provider request both
because authorization is false and because no-retry cannot be guaranteed.

## 风险与限制

Changing `authorized` by editing JSON would not be valid authorization. A new
user instruction must attest to the current Codex profile and accept that GR1's
192 historical images remain outside this revision.

## 下一阶段建议

The required user attestation is:

> 我明确授权 P4D_GR3 使用当前 Codex profile，对冻结的 440 个 prompt slots 全量重新生成，接受旧 GR1 192 张不进入新 revision。

Even after that attestation, resolve or explicitly review the retry-policy gate
before generating. Keep formal ingest, C3, NEW_VAL, and HOLDOUT disabled.
