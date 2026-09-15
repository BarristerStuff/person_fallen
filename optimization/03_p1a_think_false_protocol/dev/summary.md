# DEV P1A summary

```json
{
  "stage": "dev",
  "P1A_NAME": "P1A_THINK_FALSE_PROTOCOL",
  "think_false_only": true,
  "prompt_sha256": "b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4",
  "config_sha256": "db933a7420a4ca0f50785c487c1f0703830af9804e4cac1f0a962f18d4500557",
  "runner_sha256": "6ebc633b3a89ab9aaa4ea5653fd8fec126f283e8c5d70ce657c46b5e8e926f93",
  "frozen_manifest_sha256": "771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6",
  "frozen_splits_sha256": "16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a",
  "selected_count": 310,
  "holdout_requests": 0,
  "reused_canary_results": 12,
  "duplicate_protocol_requests": 0,
  "protocol": {
    "request_count": 310,
    "http_success_rate": 1.0,
    "response_nonempty_rate": 1.0,
    "thinking_present_rate": 0.0,
    "json_parse_success_rate": 1.0,
    "schema_success_rate": 1.0,
    "canonical_prediction_success_rate": 1.0,
    "first_attempt_success_rate": 1.0,
    "latency_seconds": {
      "cold": 6.653924,
      "warm_mean": 1.4567729158576053,
      "p50": 1.453798,
      "p95": 1.6105076,
      "max": 1.746854
    },
    "prediction_distribution": {
      "positive": 163,
      "negative": 147
    }
  },
  "protocol_gate_pass": true,
  "metrics": {
    "determinate_count": 290,
    "TP": 120,
    "FP": 29,
    "TN": 141,
    "FN": 0,
    "precision": 0.8053691275167785,
    "recall": 1.0,
    "f1": 0.8921933085501859,
    "accuracy": 0.9,
    "fpr": 0.17058823529411765,
    "specificity": 0.8294117647058824,
    "ordinary_negative_fpr": 0.0,
    "hard_negative_fpr": 0.2636363636363636,
    "positive_recall": 1.0,
    "model_uncertain_count": 0,
    "model_uncertain_rate": 0.0,
    "gt_uncertain_prediction_distribution": {
      "negative": 6,
      "positive": 14
    }
  },
  "predictions_sha256": "5d67e80d753ed71ae33cf9c222a8793b829c60a0bc1ff5ee09085518bf9d359b",
  "raw_responses_sha256": "87df6303bfa2ea87a1c3be2900c886f643e17692c38d35b1f3bedb166cdce159",
  "request_log_sha256": "9a1bbea6c57c9a418a1f9c43c5bd83471973f792e2f35c5ccde1bcdc00c687bb"
}
```
