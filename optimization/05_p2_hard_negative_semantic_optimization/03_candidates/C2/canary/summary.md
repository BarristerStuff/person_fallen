# P2 CANARY C2 summary

```json
{
  "candidate": "C2",
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
  "predictions_sha256": "f2aa1670a0555094e889ed0b0ef5371d77cf91a9f05c8b470077a3bdf32c2db0",
  "prompt_sha256": "c3827dcbf4eae4e39729f4b42c3f7398da8b835f4e047e79bf0d82edbec8c42d",
  "protocol": {
    "canonical_prediction_success_rate": 1.0,
    "http_success_rate": 1.0,
    "json_parse_success_rate": 1.0,
    "latency_seconds": {
      "cold": 1.414498,
      "max": 1.575441,
      "p50": 1.4926295,
      "p95": 1.5754081,
      "warm_mean": 1.49955275
    },
    "prediction_distribution": {
      "negative": 4,
      "positive": 5
    },
    "request_count": 9,
    "response_nonempty_rate": 1.0,
    "schema_success_rate": 1.0,
    "thinking_present_rate": 0.0
  },
  "protocol_gate_pass": true,
  "raw_responses_sha256": "031244ea519393e9c5eaadff34dd1030fbf8390be10b4f022c98e3e48e42d751",
  "request_log_sha256": "d29adcdb11c70aade13164fb1a50eccfdfecaf70da1e16765df4ffa897bef9cd",
  "runner_sha256": "72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568",
  "stage": "P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION"
}
```
