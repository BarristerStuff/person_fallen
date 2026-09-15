# P4D GR3Q10 mechanical QA

- revision: P4D_GR3Q10_BALANCED_COMPLETE_GROUP_WINDOW_20260901_01
- mechanical candidate rows: 30
- mechanical pass rows: 6
- completion-unknown rows: 0; all are quarantined with NO_RESEND
- safe-outstanding return rows: 24
- exact-duplicate-with-prior count: 0
- GR1 SHA collision count: 0
- foreign-event asset count: 0
- adapter provenance failures: 23
- ledger/raw/final consistency failures: 0
- full accounting: 202 clean + 30 binding-blocked + 1 unknown + 207 safe = 440
- P4D_IMAGES_ACCEPTED: 0
- formal ingest/C3/VAL/Holdout/production: all 0 or false

The native provider dimension is recorded as observed evidence; the run config deliberately keeps native_size_contract_enforced=false because Codex may return a provider-native size different from the request flag. Final outputs are locally normalized to 1920x1080 for mechanical QA only.
