# 51 — P4D_GR3E authorized generation continuation

```text
P4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT
STOP_REASON=HTTP_429
STOP_PROMPT_ID=PF_P4D_HN_KNEEL_G008_V05
STOP_HTTP_STATUS=429
SMOKE_REQUESTS=1
SMOKE_SUCCESS=1
SMOKE_FAILURE=0
RAMP1_REQUESTS=5
RAMP1_SUCCESS=5
RAMP1_FAILURE=0
RAMP2_REQUESTS=10
RAMP2_SUCCESS=10
RAMP2_FAILURE=0
BULK_REQUESTS=84
BULK_SUCCESS=83
BULK_FAILURE=1
LOGICAL_SLOT_INVOCATIONS=100
LOGICAL_SUCCESSES=99
LOGICAL_FAILURES=1
OUTSTANDING=341
HTTP_429=1
HTTP_401=0
HTTP_403=0
TIMEOUT_OR_5XX=0
GENERATED_RAW=99
GENERATED_FINAL=99
GR1_IMAGES_REUSED=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
```

## 已确认事实

The durable SQLite/WAL ledger records 100 logical invocations: 99 successful image conversions and one `FAILED_CONFIRMED` HTTP 429 at `PF_P4D_HN_KNEEL_G008_V05`. The runner wrote `GLOBAL_STOP` and exited with code 2; no slot after ordinal 99 was invoked. Raw request logs and one per-request JSON preserve the actual provider envelope and retry progress.

## 实验判断

This continuation is incomplete generation, not a 440-image dataset revision. The 99 generated images remain isolated lineage artifacts and are not mixed with the historical GR1 192 images.

## 风险与限制

The provider returned `usage_limit_reached` for plan `plus` with a reported reset interval in the raw error envelope. No exact cost is inferable from this run.

## 下一阶段建议

Keep all 99 successes and the failed-slot evidence immutable. Do not issue automatic recovery requests or formal ingest from this partial run.
