# P2 CANARY C3 summary

```json
{
  "candidate": "C3",
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
  "predictions_sha256": "cbf0870ba5ab33fda5961cf30c0dd403923741319e14454af289df46a758dd75",
  "prompt_sha256": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e",
  "protocol": {
    "canonical_prediction_success_rate": 1.0,
    "http_success_rate": 1.0,
    "json_parse_success_rate": 1.0,
    "latency_seconds": {
      "cold": 1.590897,
      "max": 1.865634,
      "p50": 1.687397,
      "p95": 1.8592997,
      "warm_mean": 1.70021025
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
  "raw_responses_sha256": "1175e5df421d1d297035cb163fe7d18c52660c1125e86bd1efc495f6b1d76a41",
  "request_log_sha256": "1cb19c185a4fbdc4c3ff43eb60fc43dae09589f2d96d5491ee7bc9cf2a4e849b",
  "runner_sha256": "72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568",
  "stage": "P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION"
}
```
