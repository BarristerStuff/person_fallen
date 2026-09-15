# P2 CANARY C1 summary

```json
{
  "candidate": "C1",
  "config_sha256": "8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d",
  "execution_status": "COMPLETE",
  "holdout_consumed": false,
  "holdout_requests": 0,
  "ledger_states": {
    "COMPLETED": 9
  },
  "manifest_sha256": "1efed8e5d46945ae39e6615586c7c1daa853fdcb35bdbe63684b5c1b5fa8adf8",
  "materializer_sha256": "d2485bc89345df7b03bfae42e7cbea206cc1136271381a6cbf3da9d29092482b",
  "metrics": null,
  "phase": "canary",
  "planned_requests": 9,
  "predictions_sha256": "554244cf7f2aa1e4b318503d0079ceb1219c3b0b55cf44016cf188f6dbe553a1",
  "prompt_sha256": "f3291b1f231316f3d424a2d4d4a1ac43fe0010205bef4528d62ca1771cb2d396",
  "protocol": {
    "canonical_prediction_success_rate": 1.0,
    "http_success_rate": 1.0,
    "json_parse_success_rate": 1.0,
    "latency_seconds": {
      "cold": 7.218357,
      "max": 1.784846,
      "p50": 1.662466,
      "p95": 1.78135545,
      "warm_mean": 1.642497625
    },
    "prediction_distribution": {
      "negative": 5,
      "positive": 4
    },
    "request_count": 9,
    "response_nonempty_rate": 1.0,
    "schema_success_rate": 1.0,
    "thinking_present_rate": 0.0
  },
  "protocol_gate_pass": true,
  "raw_responses_sha256": "7f493a22fcaf25ef9d72c1af948fe53477d0f65eb86237a3198231a969031ae5",
  "request_log_sha256": "13d54f9f40355576658aa3790efcc4d8d280c76055bfd93687271df7137793eb",
  "runner_sha256": "72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568",
  "stage": "P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION"
}
```
