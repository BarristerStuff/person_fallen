# P3 SCREEN S1_RULE

```json
{
  "candidate": "S1_RULE",
  "holdout_requests": 0,
  "latency_seconds": {
    "cold": 9.210637,
    "max": 22.183683,
    "observed_max": 22.183683,
    "observed_p50": 2.1348805,
    "observed_p95": 9.601209649999978,
    "p50": 2.134373,
    "p95": 4.071322199999917,
    "warm_mean": 2.9954679915966387
  },
  "metrics": {
    "FN": 0,
    "FP": 20,
    "TN": 40,
    "TP": 50,
    "accuracy": 0.8181818181818182,
    "determinate_count": 110,
    "f1": 0.8333333333333334,
    "fpr": 0.3333333333333333,
    "gt_uncertain_prediction_distribution": {
      "negative": 1,
      "positive": 9
    },
    "hard_negative_fpr": 0.5,
    "model_uncertain_count": 0,
    "model_uncertain_rate": 0.0,
    "ordinary_negative_fpr": 0.0,
    "positive_recall": 1.0,
    "precision": 0.7142857142857143,
    "recall": 1.0,
    "specificity": 0.6666666666666666
  },
  "new_requests": 120,
  "p2_screen_individual_errors_used_for_p3_design": false,
  "phase": "screen",
  "predictions_sha256": "49cfe8bfaa924d20ee5203f16b06a5cf88141d922fd9d3b741f1421269edd7ad",
  "protocol": {
    "canonical_prediction_success_rate": 1.0,
    "http_success_rate": 1.0,
    "json_parse_success_rate": 1.0,
    "latency_seconds": {
      "cold": 9.210637,
      "max": 22.183683,
      "observed_max": 22.183683,
      "observed_p50": 2.1348805,
      "observed_p95": 9.601209649999978,
      "p50": 2.134373,
      "p95": 4.071322199999917,
      "warm_mean": 2.9954679915966387
    },
    "prediction_distribution_direct": {
      "negative": 41,
      "positive": 79
    },
    "prediction_distribution_rule": {
      "negative": 41,
      "positive": 79
    },
    "request_count": 120,
    "response_nonempty_rate": 1.0,
    "schema_success_rate": 1.0,
    "thinking_present_rate": 0.0
  },
  "protocol_gate_pass": true,
  "screen_is_pristine": false,
  "source_stream": "S1_STRUCTURED",
  "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
  "stream_request_count": 120,
  "structured_conflict_count": 0,
  "structured_conflict_rate": 0.0,
  "val_requests": 0
}
```
