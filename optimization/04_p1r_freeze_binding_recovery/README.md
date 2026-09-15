# P1R — Freeze-Binding Recovery and VAL Recovery Evaluation

`P1R_FREEZE_BINDING_RECOVERY` is a separately named recovery stage for the P1A freeze-binding incident. It does not alter, repair, or reinterpret P0 or P1A historical artifacts.

## Scope and invariant

The original P1A DEV freeze declared DEV-manifest SHA-256 `f829285121249ceac924632c485f67ee3d83e9a9cf08a0d3716908bb21878c58`, while the actual P1A DEV manifest hashes to `7f8ff256a8da3cc6451e1ec3f6a842dc9b3eb6f4080e4fb5a1a49dda9bc7d7d8`. The original freeze remains preserved. P1R bound the actual DEV evidence, frozen inputs, model identity, and a newly frozen recovery VAL manifest, then obtained an independent verification before network inference.

P1R kept P1A inference semantics unchanged: `qwen3.5:4b`, `format=json`, top-level `think=false`, response-only parsing, temperature 0, `num_ctx=8192`, `num_predict=256`, stream false, concurrency 1, letterbox 448×336, JPEG quality 70. It made no prompt, definition, GT, split, parser, preprocess, model, endpoint, or threshold change.

## Evaluation status

P1R VAL is a **recovery validation**, not a pristine validation: P1A had already confirmed 10 VAL requests, with one additional request potentially in flight and not durably observable. P1R therefore records `P1R_VAL_IS_PRISTINE=false`, `prior_val_confirmed_exposure=10`, and `prior_val_possible_additional_exposure=1`.

The recovery manifest has 100 unique VAL items and zero HOLDOUT rows. The durable ledger recorded 100 `COMPLETED` requests, with zero failed or unknown terminal states. An independent result verifier confirmed exact manifest/prediction/raw/log entity-set equality, canonical protocol success for all rows, `HOLDOUT_REQUESTS=0`, and exact metric recomputation agreement.

## Evidence

- `preflight/p1a_history_audit.json` — preserved history and actual DEV evidence binding.
- `freeze/p1r_recovery_freeze.json` — current, read-only-verified freeze artifact, SHA-256 `15d7e30d43c39b305ab89ac7a9f2e91567a40b3ff86c6e2a9299f5e3994c27e0`.
- `preflight/recovery_freeze_verification.json` — independent pre-inference verification (`PASS`).
- `val/request_ledger.sqlite3` — WAL/full-synchronous request state ledger.
- `val/responses/` — one durable response object per completed recovery request.
- `val/result_verification.json` — independent post-run verification (`PASS`).

No P2 work, production-code modification, or HOLDOUT inference is part of P1R.

## Post-run verifier correction

The execution-time freeze identifier recorded in the VAL summary is `9aa6b1e9d0f87144633539850d6b30236fe5c50acb5368bd90961cd2ac3674a0`. A post-run invocation of the original verifier rewrote only the verification timestamp and consequently changed the on-disk freeze JSON SHA to `15d7e30d43c39b305ab89ac7a9f2e91567a40b3ff86c6e2a9299f5e3994c27e0`. No model request, response, ledger, prediction, or other bound candidate input changed. The verifier was then corrected to be read-only for an existing freeze; a before/after check confirms its current invocation leaves the artifact unchanged. This is retained as a governance limitation rather than hidden or backfilled.
