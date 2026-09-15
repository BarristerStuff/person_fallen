# 08 P1A VAL report

## Status: incomplete and non-evaluable

P1A VAL must not be reported as a valid one-shot validation result.

## Confirmed facts

- `VAL_P0_PROTOCOL_EXPOSED=true`.
- `VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false`.
- After DEV, an incorrect declared DEV-manifest binding was detected in the original freeze artifact. VAL was stopped immediately.
- Ten VAL requests are confirmed completed from the runner progress output. An eleventh was prepared/in-flight at interruption; its completion is indeterminate. No persisted P1A VAL raw responses/predictions/request log exist for this partial attempt.
- Therefore P1A VAL request exposure is >=10 and <=11, not the required one-shot 100, and all VAL classification/protocol metrics are N/A.
- HOLDOUT requests=0; HOLDOUT consumed=false.

## Consequence

Do not resume or rerun VAL as P1A. Any future evaluation needs a separately named and newly authorized protocol/recovery revision that records this prior VAL exposure.
