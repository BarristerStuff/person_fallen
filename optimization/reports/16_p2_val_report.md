# P2 winner VAL evaluation report

## Status

```text
P2_WINNER=C3
P2_WINNER_FREEZE=PASS
P2_VAL_PROTOCOL_GATE=PASS
P2_VALIDATION_COMPLETE=true
P2_VAL_IS_PRISTINE=false
P2_VAL_LATENCY_GATE=FAIL
P2_REFERENCE_THRESHOLDS_PASS=false
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

C3 was frozen before any P2 VAL request. The winner freeze SHA-256 is `ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0`; its independent read-only attestation passed without changing the freeze. P2 VAL used exactly the original 100-item recovery VAL manifest, not DEV or HOLDOUT. No P1R VAL individual error, image, evidence, or taxonomy was used to design the Prompt.

## Protocol and durable execution

| Check | Result |
| --- | ---: |
| Planned / completed requests | 100 / 100 |
| SQLite ledger states | `COMPLETED=100` |
| Unknown or failed terminal states | 0 / 0 |
| HTTP success | 100/100 |
| Response nonempty | 100/100 |
| JSON parse | 100/100 |
| Schema | 100/100 |
| Canonical prediction | 100/100 |
| Thinking present | 0/100 |
| Protocol gate | **PASS** |

The request ledger is WAL/full-synchronous, with `STARTED` committed before HTTP and an atomic response file before `COMPLETED`. Automatic retries were false. The final run contains 100 response objects, raw records, request-log records, and prediction rows, with zero HOLDOUT requests.

## P2 VAL metrics

| Metric | P2 C3 VAL |
| --- | ---: |
| TP / FP / TN / FN | **40 / 5 / 55 / 0** |
| Precision | **0.888889** |
| Recall / positive recall | **1.000000 / 1.000000** |
| F1 | **0.941176** |
| Accuracy | **0.950000** |
| FPR / Specificity | **0.083333 / 0.916667** |
| Ordinary-negative FPR | **0.000000** |
| Hard-negative FPR | **0.125000** |
| Model uncertain count / rate | **0 / 0.000000** |

The VAL set is deterministic binary GT, so there are no GT-uncertain rows in this evaluation.

## Latency

| Measure | P2 C3 VAL |
| --- | ---: |
| Cold first request | 10.848432s |
| Warm mean | 10.381262s |
| P50 | 14.684316s |
| P95 | **18.147252s** |
| Maximum | 21.157412s |

The predeclared development latency limit was `1.8520842s` (`P1A DEV P95 1.610508 × 1.15`). P2 VAL P95 exceeds it by `16.295167s` (approximately 9.80× the limit) and exceeds P1R VAL P95 `1.650989s` by `16.496263s` (approximately 10.99×). This is a real post-freeze measurement and is not hidden by the good classification result.

## Independent verification and P1R paired comparison

The independent verifier returned:

```text
verification_result=PASS
metric_recompute_match=true
P2_VALIDATION_COMPLETE=true
```

It confirmed exact 100-row manifest/prediction/raw/log/ledger alignment, canonical success for all rows, zero unknown states, and exact metric recomputation.

Against P1R recovery VAL, which had TP/FP/TN/FN `40/11/49/0`:

```text
baseline_FP_rescued=6
new_FP_created=0
baseline_TP_preserved=40
new_FN_created=0
baseline_FN_to_TP=0
```

Thus the semantic improvement transfers to this already-exposed VAL aggregate, but the project reference thresholds remain unmet: Precision `0.888889 < 0.93`, hard-negative FPR `0.125000 > 0.05`, and latency gate fails.

## Non-pristine and AIGC qualification

```text
P2_VAL_IS_PRISTINE=false
P1R_PRIOR_VAL_PROTOCOL_EXPOSURE=true
```

P1R had previously evaluated this VAL set as a recovery validation, so P2 VAL cannot be called fresh, pristine, or never-exposed. All DEV/SCREEN/VAL images remain AIGC (`gpt-image-2`) with prompt-derived GT under user-confirmed prompt/image alignment. This result does not establish real-camera, robot, or production accuracy.

## Evidence

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/06_val/summary.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/06_val/result_verification.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/06_val/request_ledger.sqlite3`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/05_winner_freeze/p2_winner_freeze_attestation.json`
