# P2L_REMOTE_LATENCY_FORENSICS

This stage audits the P2 C3 SCREEN/VAL latency split and runs controlled
DEV-only runtime probes. It does not tune semantics, rewrite P2 history, run
new VAL requests, or consume HOLDOUT.

```text
P2L_STATUS=COMPLETE
P2L_PRIMARY_COMPONENT=load_duration
P2L_ANOMALY_REPRODUCED=false
P2L_FORMAL_PROBE_REQUESTS=64
P2L_PRESERVED_INITIAL_ATTEMPT_REQUESTS=1
P2L_NEW_DEV_REQUESTS=65
P2L_NEW_VAL_REQUESTS=0
P2L_HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P2L_WINNER=NONE
CURRENT_BEST_SEMANTIC_CANDIDATE=C3
OLLAMA_SERVICE_MODIFIED=false
PRODUCTION_CODE_MODIFIED=false
```

Historical analysis is in `01_historical_forensics/`; diagnostic manifests are
in `02_diagnostic_manifest/`; direct API and best-effort read-only remote
telemetry are in `03_runtime_telemetry/`; formal probes are A/B/C; and
independent aggregation plus the final boundary audit are in `07_analysis/`.

The initial one-request runner defect is preserved at
`04_probe_A_exact_c3_attempt_001/` and is explicitly excluded from the formal
24-request Probe A statistics.
