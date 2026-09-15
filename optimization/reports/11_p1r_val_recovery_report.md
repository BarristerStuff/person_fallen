# P1R VAL recovery evaluation

## Status

```text
STAGE=P1R_FREEZE_BINDING_RECOVERY
RUN_ID=P1R_VAL_20260826_221040
PLANNED_VAL_REQUESTS=100
CONFIRMED_COMPLETED_REQUESTS=100
COMPLETION_UNKNOWN_COUNT=0
FAILED_CONFIRMED_COUNT=0
LEDGER_STATES={COMPLETED:100}
P1R_VAL_IS_PRISTINE=false
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## Protocol result

All classifications were parsed only from the outer Ollama `response`; `thinking` was never a parser fallback.

| Check | Result |
| --- | ---: |
| HTTP success | 100/100 (100%) |
| Response nonempty | 100/100 (100%) |
| Thinking present | 0/100 (0%) |
| JSON parse success | 100/100 (100%) |
| Schema success | 100/100 (100%) |
| Canonical prediction success | 100/100 (100%) |
| Protocol gate | PASS |

The durable SQLite ledger uses WAL mode and full synchronous commits. A request enters `STARTED` before its HTTP request, its response is atomically persisted before the `COMPLETED` transition, and no automatic retries were performed. There are 100 durable response objects, 100 raw response records, and 100 request-log records.

## Classification result

The deterministic binary VAL set has 40 positive and 60 negative/hard-negative images. Under frozen alert behavior (`positive=alert`; `negative`/`uncertain`=no alert):

| Metric | P1R VAL |
| --- | ---: |
| TP / FP / TN / FN | 40 / 11 / 49 / 0 |
| Precision | 0.784314 |
| Recall / positive recall | 1.000000 / 1.000000 |
| F1 | 0.879121 |
| Accuracy | 0.890000 |
| FPR | 0.183333 |
| Specificity | 0.816667 |
| Ordinary-negative FPR | 0.000000 |
| Hard-negative FPR | 0.275000 |
| Model uncertain count / rate | 0 / 0.000000 |

The model emitted 51 `positive` and 49 `negative` predictions, with no model `uncertain` outputs.

## Latency

The protocol gate is 100% valid, so these are valid-classification transport-and-inference latencies for this P1R run:

| Measure | Seconds |
| --- | ---: |
| First request (cold) | 6.320095 |
| Warm mean | 1.482832 |
| P50 | 1.478509 |
| P95 | 1.650989 |
| Maximum | 1.732129 |

## Independent post-run verification

The independently implemented result verifier returned:

```text
P1R_RESULT_VERIFICATION=PASS
P1R_VALID_RECOVERY_BASELINE=true
METRIC_RECOMPUTE_MATCH=true
```

It confirmed exactly 100 manifest, prediction, raw, request-log, and `COMPLETED` ledger entities; exact cross-artifact entity-set equality; canonical success for every row; no HOLDOUT rows; and recomputed all reported metrics with an exact match.

Result hashes:

```text
predictions.csv     7f221795f9a21febd47d5861ee58492dbef6eb00a1032ea240bc1c536de1e38b
raw_responses.jsonl d9be1890277f2e4798f1b4ab7ee63817667d1cae0c79aa86ecaccb82de878f97
request_log.jsonl   e553985465791fd57d9e0ca8cc6960ff7481e7b66a4cc669b7fb9d190a994b34
request_ledger      05fdba91477da465aee3e305edc4437f43279556ca2dccac9e6034586a1c54c0
```

## Post-run derived-metadata correction

After result materialization, a derived summary field initially labeled the materializer script as `runner_sha256`. The original derived summary is preserved at `summary_pre_runner_metadata_correction.json`; the materialized summary was regenerated without any new model request or any alteration to ledger, response, raw, prediction, or request-log evidence. It now correctly records the frozen inference runner (`18e45…60eb5`) and separately records `materializer_sha256=2998cec63c1fde25950cbd4d90951490554eccb6e6094a70be85e7d6583a1f85`. Independent verification was rerun and passed.

Separately, a post-run freeze-verifier invocation rewrote only its verification timestamp, changing the current on-disk freeze artifact SHA from the execution-time summary identifier `9aa6…4a0` to `15d7…7e0`. Its bound candidate fields, model request behavior, and every VAL evidence artifact remained unchanged. The verifier is now read-only when a freeze exists; a before/after SHA test confirms `15d7…7e0` remains unchanged on verification. This is a retained governance caveat and does not alter the request/result counts above.

## Evaluation limitation

This is a valid **recovery** baseline, not a pristine VAL evaluation, because P1A had prior protocol-only exposure of at least 10 and at most 11 VAL requests. It remains AIGC-only. No semantic metric was used to change Prompt, parser, config, threshold, or preprocessing before this run.

## Evidence locations

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/04_p1r_freeze_binding_recovery/val/summary.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/04_p1r_freeze_binding_recovery/val/result_verification.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/04_p1r_freeze_binding_recovery/val/request_ledger.sqlite3`
