# 54 — P4D_GR3E authorized continuation final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION
P4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT
P4D_STATUS=GENERATION_REQUIRED
FULL_REGEN_AUTHORIZED=true
AUTHORIZATION_ATTESTATION_PRESENT=true
GR1_IMAGES_REUSED=0
HISTORICAL_GR1_IMAGES=192
PLANNED_NEW_IMAGES=440
LOGICAL_SLOT_INVOCATIONS=100
LOGICAL_SUCCESSES=99
LOGICAL_FAILURES=1
GENERATED_RAW=99
GENERATED_FINAL=99
OUTSTANDING=341
HTTP_429=1
HTTP_401=0
HTTP_403=0
TIMEOUT_OR_5XX=0
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT=0
HOLDOUT_CONSUMED=false
P4D_IMAGES_ACCEPTED=0
HUMAN_SEMANTIC_REVIEW_STATUS=NOT_STARTED
VAL_P0_PROTOCOL_EXPOSED=true
VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false
P4D_ACTIVE_DATASET_HITS=0
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
```

## 已确认事实

The authorized continuation passed the frozen-surface and provider/runtime gates, then executed smoke 1/1, ramp1 5/5, ramp2 10/10, and 83 successful bulk slots before the first terminal provider usage-limit response at logical invocation 100. The runner durably recorded the 429, performed no outer retry, and globally stopped.

The shared dataset remained unmodified by GR3E. The final read-only validator snapshot is `valid`, errors `0`, full hash `True`, warnings `387`. CSV-row boundary counts changed by `{'media_count': 0, 'label_count': 262, 'batch_count': 0, 'split_count': 560}` during the long run and are retained as an observed shared-workspace boundary, not attributed to GR3E; active P4D references remain `0`.

## 实验判断

This is a provider-quota-blocked partial generation revision, not a valid 440-image P4D dataset and not a human-reviewed or ingestible revision. No semantic classifier baseline, C3 result, or NEW_VAL/HOLDOUT result may be derived from it.

## 风险与限制

Native retry telemetry observed `7` retry-scheduled events and an observed attempt lower-bound sum of `107` across `100` logical records. The conservative possible upper bound remains `440 × 4 = 1760` provider attempts; exact monetary cost is `UNKNOWN`.

The prior no-auth terminal freeze remains byte-for-byte preserved at `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/freeze/p4d_gr3e_terminal_freeze.json`. This authorized continuation has its own terminal freeze under `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/authorized_20260827_01/freeze` and must not be resumed or rewritten.

## 下一阶段建议

Stop at this sealed failure. A later recovery requires a new explicit provider/quota authorization and a separately frozen recovery revision; it must not silently resend the failed logical slot or continue this sealed ledger.
