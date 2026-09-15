# person_fallen v3.0 DEV V3-C0-896

- Resolution: `896x672` letterbox JPEG70
- Requests: `436`; Holdout requests: `0`; Holdout consumed: `false`
- GT: `PROMPT_DERIVED_SYNTHETIC_GT` from `FROZEN_GENERATION_PROMPT_AND_PLANNED_ROLE`; human semantic review required: `false`

## Metrics
- TP: `185`
- FP: `35`
- TN: `195`
- FN: `1`
- precision: `0.8409090909090909`
- recall: `0.9946236559139785`
- f1: `0.9113300492610837`
- accuracy: `0.9134615384615384`
- hard_negative_fpr: `0.22580645161290322`
- ordinary_negative_fpr: `0.0`
- model_uncertain_rate: `0.0`

## Protocol and latency
- strict JSON success: `1.0`
- P50 seconds: `9.445309`
- P95 seconds: `28.62508175`
- gate pass: `False`

Taxonomy-level TP/FP/TN/FN and protocol errors are in `taxonomy_metrics.csv`; individual error rows are in the false-positive/false-negative/uncertain files.
