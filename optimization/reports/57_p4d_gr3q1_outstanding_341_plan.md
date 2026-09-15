# 57 — P4D GR3Q1 outstanding 341 plan

```text
DERIVED_OUTSTANDING=341
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=340
COMPLETION_UNKNOWN=0
FIRST_RECOVERY_PROMPT_ID=PF_P4D_HN_KNEEL_G008_V05
POSSIBLE_NEW_LOGICAL_INVOCATIONS=341
POSSIBLE_PROVIDER_ATTEMPT_UPPER_BOUND=1364
EXACT_MONETARY_COST=UNKNOWN
AUTHORIZED=false
```

## 已确认事实

Outstanding was derived as frozen 440 prompt IDs minus 99 verified-success IDs. The first future request is preregistered as a new logical recovery attempt bound to parent request `P4D_GR3E_BULK_0100_PF_P4D_HN_KNEEL_G008_V05`; the parent failed row remains immutable.

## 合理推理

The confirmed 429 slot is ambiguity-free because it returned no image bytes. It may be retried once in a new authorized recovery revision, followed by 5, 10, then sequential micro-batches of 10.

## 风险与限制

The 1,364 figure is only `341 × 4`, a theoretical runtime-attempt upper bound. It is neither a prediction nor a billing estimate.
