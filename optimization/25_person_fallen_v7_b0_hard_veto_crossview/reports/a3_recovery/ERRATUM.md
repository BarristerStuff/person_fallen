# A3 erratum

`A3_EXECUTION_STATUS=INVALID_FOR_FORMAL_METRICS`

`A3_OUTPUT_SOURCE_CONTAMINATION=true`

`A3_MODEL_FAILURE_CONCLUSION_WITHDRAWN=true`

`A3_HISTORICAL_ARTIFACTS_PRESERVED=true`

The prior A3 `partial_semantic_audit` read `eval/a3_pilot/output.jsonl`. Its request IDs are `V6_TARGET_SUPPORT_PILOT_*`, which identify historical V6 image outputs, not A3 final outputs. The actual A3 request records are in `eval/a3_pilot/requests.jsonl` with `A3_pilot_*_P1_primary_*` and `A3_pilot_*_P1_background_*` IDs.

The old reports and artifacts are preserved unchanged. The prior A3 model-failure conclusion is withdrawn and is not used as a V7-B0 metric.
