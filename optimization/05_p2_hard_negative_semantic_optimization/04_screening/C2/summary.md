# P2 SCREEN C2 summary

```json
{
  "candidate": "C2",
  "config_sha256": "8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d",
  "execution_status": "COMPLETE",
  "holdout_consumed": false,
  "holdout_requests": 0,
  "ledger_states": {
    "COMPLETED": 120
  },
  "manifest_sha256": "ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5",
  "materializer_sha256": "d2485bc89345df7b03bfae42e7cbea206cc1136271381a6cbf3da9d29092482b",
  "metrics": {
    "FN": 0,
    "FP": 29,
    "TN": 31,
    "TP": 50,
    "accuracy": 0.7363636363636363,
    "determinate_count": 110,
    "f1": 0.7751937984496124,
    "fpr": 0.48333333333333334,
    "gt_uncertain_prediction_distribution": {
      "positive": 10
    },
    "hard_negative_fpr": 0.725,
    "model_uncertain_count": 0,
    "model_uncertain_rate": 0.0,
    "ordinary_negative_fpr": 0.0,
    "positive_recall": 1.0,
    "precision": 0.6329113924050633,
    "recall": 1.0,
    "specificity": 0.5166666666666667
  },
  "phase": "screen",
  "planned_requests": 120,
  "predictions_sha256": "ddc09c9e7626fb695f7972ff78eceb132889adad5cbc54b0a19d2225502ac350",
  "prompt_sha256": "c3827dcbf4eae4e39729f4b42c3f7398da8b835f4e047e79bf0d82edbec8c42d",
  "protocol": {
    "canonical_prediction_success_rate": 1.0,
    "http_success_rate": 1.0,
    "json_parse_success_rate": 1.0,
    "latency_seconds": {
      "cold": 1.5642,
      "max": 1.637859,
      "p50": 1.451907,
      "p95": 1.5924791,
      "warm_mean": 1.455814781512605
    },
    "prediction_distribution": {
      "negative": 31,
      "positive": 89
    },
    "request_count": 120,
    "response_nonempty_rate": 1.0,
    "schema_success_rate": 1.0,
    "thinking_present_rate": 0.0
  },
  "protocol_gate_pass": true,
  "raw_responses_sha256": "667c89d03a6bc8b43ea9fe99aaf52edaaf48e35f5bf44b296fdf74da0bbebaf9",
  "request_log_sha256": "b09ec29ffd6c1d0b1bc8fde754af77aa7ec3b7129a484bc7d9f0685b079820c0",
  "runner_sha256": "72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568",
  "stage": "P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION"
}
```
