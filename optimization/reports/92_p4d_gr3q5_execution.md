# Q5 execution

```text
{
  "stage": "P4D_GR3Q5_POLICY_AWARE_RENDER_ADAPTER_RECOVERY",
  "status": "STOPPED_PROVIDER_429",
  "stop_reason": "HTTP429_USAGE_LIMIT_REACHED",
  "q5_logical_invocations": 11,
  "q5_success": 10,
  "q5_policy_refusals": 0,
  "q5_other_failure": 0,
  "q5_completion_unknown": 0,
  "q5_native_retry_events": 6,
  "q5_physical_attempt_lower_bound": 17,
  "current_verified_success": 142,
  "current_outstanding": 298,
  "formal_ingest": false,
  "c3": false,
  "new_val": 0,
  "holdout_requests": 0,
  "holdout_consumed": false,
  "dataset_validator": {
    "status": "valid",
    "error_count": 0,
    "warning_count": 387,
    "full_hash_check": true
  }
}
```

HTTP429 is provider quota/usage-limit evidence, not a policy refusal.
