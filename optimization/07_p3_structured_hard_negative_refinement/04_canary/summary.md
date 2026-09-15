# P3 CANARY S1_STRUCTURED summary

```json
{
  "candidate": "S1_STRUCTURED",
  "config_sha256": "102c1e82706a78aacbb8e6e07f41d6b1d0233e4c72954a7d3ab46d07529a5779",
  "execution_status": "COMPLETE",
  "holdout_requests": 0,
  "ledger_states": {
    "COMPLETED": 12
  },
  "manifest_sha256": "749a436404f78cfc7d2a205e28b3942cd6010c89a7fd298dfcd08072b01c0567",
  "metrics_direct": null,
  "metrics_rule": null,
  "phase": "canary",
  "planned_requests": 12,
  "predictions_sha256": "c843e0239e5d3dab6687ebdffea388e62fab71a07f3156d3d60b6ac39a2255fb",
  "prompt_sha256": "a4b0f9b6410d814384c9e43ee2caede4dbedf557a8e02b290cc5865dce60a4ae",
  "protocol": {
    "canonical_prediction_success_rate": 1.0,
    "http_success_rate": 1.0,
    "json_parse_success_rate": 1.0,
    "latency_seconds": {
      "cold": 12.268687,
      "max": 2.530045,
      "observed_max": 12.268687,
      "observed_p50": 2.4457430000000002,
      "observed_p95": 6.912433899999993,
      "p50": 2.419033,
      "p95": 2.5138084999999997,
      "warm_mean": 2.4064354545454547
    },
    "prediction_distribution_direct": {
      "negative": 7,
      "positive": 5
    },
    "prediction_distribution_rule": {
      "negative": 7,
      "positive": 5
    },
    "request_count": 12,
    "response_nonempty_rate": 1.0,
    "schema_success_rate": 1.0,
    "thinking_present_rate": 0.0
  },
  "protocol_gate_pass": true,
  "raw_responses_sha256": "ab158e835ff1a5dbc47d50df862fd97e48df7ebb9610bb9ba8796ffe75ff5719",
  "request_log_sha256": "69e615da376451b259747d3c789bfcf5d9abb529640278716cfceb95fe8ad776",
  "runner_sha256": "4e103b1e6b42418315f6b572b3b53618eb66ba952f32f02157907e3b4122d22b",
  "stage": "P3_STRUCTURED_HARD_NEGATIVE_REFINEMENT",
  "structured_conflict_count": 0,
  "structured_conflict_rate": 0.0,
  "val_requests": 0
}
```
