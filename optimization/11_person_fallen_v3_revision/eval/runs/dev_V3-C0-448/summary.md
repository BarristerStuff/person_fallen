# person_fallen v3.0 DEV V3-C0-448

- Resolution: `448x336` letterbox JPEG70
- Requests: `436`; Holdout requests: `0`; Holdout consumed: `false`
- GT: `PROMPT_DERIVED_SYNTHETIC_GT` from `FROZEN_GENERATION_PROMPT_AND_PLANNED_ROLE`; human semantic review required: `false`

## Metrics
- TP: `185`
- FP: `37`
- TN: `193`
- FN: `1`
- precision: `0.8333333333333334`
- recall: `0.9946236559139785`
- f1: `0.9068627450980392`
- accuracy: `0.9086538461538461`
- hard_negative_fpr: `0.23870967741935484`
- ordinary_negative_fpr: `0.0`
- model_uncertain_rate: `0.0`

## Protocol and latency
- strict JSON success: `1.0`
- P50 seconds: `4.443172000000001`
- P95 seconds: `5.47514725`
- gate pass: `False`

Taxonomy-level TP/FP/TN/FN and protocol errors are in `taxonomy_metrics.csv`; individual error rows are in the false-positive/false-negative/uncertain files.
