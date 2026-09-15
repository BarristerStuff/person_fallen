# P4D GR3Q7 — authorized network-stability execution

## Confirmed facts

- Execution revision: `quota_campaign_window_04_gr3q7_authorized_20260831_01`.
- The Q7 preparation and supplement freezes verified with their required SHA-256 values, matching sidecars and all bound artifacts.  The Q6 original terminal freeze and Q6 erratum seal bytes/sidecars also matched their required SHA-256 values.
- The historical Q6 erratum's only current bound-artifact drift is the append-only `PERSON_FALLEN_V2.md`; the Q7 preparation supplement independently binds the current overview.  The Q6 raw evidence, original freeze, erratum content, and reports all matched.  This was recorded as an explicit append-only exception, not repaired or overwritten.
- Frozen plan SHA-256: `4b6b44597f6d91a0b754f70a3e460cb8bba45fcf8f03f1cab288e7fec6f7149f`; exactly 20 slots in the prescribed four groups were invoked in order.  `MAINT_G006` requests: 0.
- Provider contract: `codex`, `gpt-5.4`, `image_generation`, runtime `0.7.3`, `CODEX_SAFE_STAGED_CV_V1`, single concurrency, no outer retry.
- `20/20` logical invocations completed as HTTP 200 generation successes.  Structured telemetry recorded 2 unique `retry_scheduled` events and 22 `request.started` lower-bound physical attempts.  No policy refusal, 429, 401, 403, 5xx, timeout, network error, or completion-unknown was observed.
- Stop status is `WINDOW_CAP_REACHED_SUCCESS`; no 21st slot was sent.
- The requested native size was `1536×1024`, while the provider returned `1672×941` raw PNGs for all 20 successes.  This is preserved as provider-output evidence; it was not treated as a semantic rejection or a retry condition.

## Interpretation and limits

Generation success is a mechanical/provider outcome only.  No C3, VLM, Codex visual judgement, human semantic acceptance, GT edit, formal ingest, VAL, or HOLDOUT was performed.

The frozen mechanical dimension gate applies to the final `1920×1080` files, all of which passed.  Consequently `DIMENSION_FAILURES=0` does **not** mean the requested native size was verified; native-size fidelity needs an independently authorized future decision rather than a historical rewrite.

## Evidence

- [Terminal summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_04_gr3q7_authorized_20260831_01/05_checkpoints/terminal_summary.json)
- [Request ledger](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_04_gr3q7_authorized_20260831_01/03_ledger/gr3q7_execution.sqlite3)
- [Raw response log](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_04_gr3q7_authorized_20260831_01/raw_responses.jsonl)
