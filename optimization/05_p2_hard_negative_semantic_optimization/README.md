# `person_fallen` V2 — P2 hard-negative semantic optimization

This directory is the complete, isolated record of stage
`P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION` for `event_version=v2.0`. It is an
evaluation workspace only; it is not the production project and it does not
authorize a new stage.

## Final status

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P2_NAME=P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION
P2_STATUS=COMPLETE
P2_WINNER=C3
P2_INTERNAL_SPLIT_STATUS=PASS
P2_SCREEN_BLIND_BEFORE_CANDIDATE_FREEZE=true
P2_FORENSIC_SOURCE=DESIGN_ONLY
VAL_ERRORS_USED_FOR_PROMPT_DESIGN=false
P2_SCREEN_PROTOCOL_GATE=PASS
P2_WINNER_FREEZE=PASS
P2_VAL_PROTOCOL_GATE=PASS
P2_VALIDATION_COMPLETE=true
P2_VAL_IS_PRISTINE=false
P2_REFERENCE_THRESHOLDS_PASS=false
P2_LATENCY_GATE=FAIL
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P3_EXECUTED=false
PRODUCTION_CODE_MODIFIED=false
```

`P2_VAL_IS_PRISTINE=false` is intentional: the original VAL had prior P1A
protocol exposure and the P1R recovery evaluation. P2 used VAL only after the
C3 winner was frozen, ran it once, and did not use individual VAL errors to
design or tune the Prompt.

## Scope and fixed conditions

The only experimental change was semantic Prompt text. C3 retained
`format=json`, top-level `think=false`, the response-only parser, model
`qwen3.5:4b`, endpoint `http://192.168.20.62:11434`, temperature `0`,
`num_ctx=8192`, `num_predict=256`, `stream=false`, concurrency `1`, and
448x336 letterbox/JPEG quality 70 preprocessing. GT, event definition, the
formal split, scenario/group IDs, and the 90-image HOLDOUT were not changed.

The read-only formal dataset validator finished `valid` with `error_count=0`,
`full_hash_check=true`, and 387 pre-existing warnings. The user-specified
`ingest_media.py validate --json-output` interface is not present in this
checkout; the available `tools/validate_dataset.py --json` interface was used
and recorded instead. No dataset re-ingest and no shared split CSV edit were
performed.

## Controlled pipeline

1. `00_preflight/` records dataset, model, and source-hash checks.
2. `01_internal_split/` freezes the original DEV by group into DESIGN (19
   groups, 190 images) and SCREEN (12 groups, 120 images); cross-split groups
   are zero. The split was made before reading any P1A individual predictions.
3. `02_forensics/` contains DESIGN-only hard-negative inventory, false
   positives, and the posture taxonomy. It was not populated from VAL errors.
4. `03_candidates/` contains the common protocol canary, C0 baseline, C1/C2/C3
   candidate Prompts, candidate registry, and candidate freeze.
5. `04_screening/` contains the common SCREEN results and declared winner
   decision. C3 was selected before any P2 VAL request.
6. `05_winner_freeze/` binds the C3 Prompt/config, runner/materializer,
   manifests, model identity, and screen evidence.
7. `06_val/` contains the single, post-freeze C3 VAL run, durable request
   ledger, raw responses, predictions, summaries, and independent verification.

The frozen internal manifests are DESIGN SHA-256
`f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1`, SCREEN
`ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5`, and
internal split `a9edfb22fc0170ce774dfe5e6229bf776c8c272868b55c303e74ae629b153892`.

## Results

C3 SCREEN (the declared selection set) was protocol-valid for all 120 rows and
returned TP/FP/TN/FN `50/5/55/0`, Precision `0.909091`, Recall `1.000000`,
F1 `0.952381`, ordinary-negative FPR `0`, hard-negative FPR `0.125000`, and
P95 `1.815010s`. Relative to C0 it rescued 17 false positives, created no new
false positives, preserved all 50 positive TPs, and created no FN.

C3 VAL (the recovery evaluation, not pristine validation) completed 100/100
durable requests with all HTTP, response-nonempty, JSON, schema, and canonical
checks at 100% and `thinking_present=0%`. Metrics were TP/FP/TN/FN
`40/5/55/0`, Precision `0.888889`, Recall `1.000000`, F1 `0.941176`, Accuracy
`0.950000`, ordinary-negative FPR `0`, hard-negative FPR `0.125000`, and model
uncertain rate `0`. Latency was P50 `14.684316s` and P95 `18.147252s`; the
predeclared development limit was `1.8520842s`, so the latency gate failed.
The reference quality thresholds also failed: Precision `<0.93` and
hard-negative FPR `>0.05`.

## Identities and key hashes

```text
Ollama version                 0.23.2
Model / digest                 qwen3.5:4b / 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
P2 winner Prompt SHA           685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e
P2 winner config SHA           8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d
P2 runner SHA                  72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568
P2 materializer SHA            d2485bc89345df7b03bfae42e7cbea206cc1136271381a6cbf3da9d29092482b
Candidate freeze SHA           7ab9169a9502c832c8a10b522ab7257eba846a5ff7ecef39f6139b7e5d9beebe
Winner freeze SHA              ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0
P2 VAL manifest SHA            f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762
P2 VAL predictions SHA         2f60d6e3e9c0f9589b28cb8812ef9443501b9f971b70e163d4f6f017050bed98
P2 VAL raw responses SHA       cd04ddd89328d7464856dafc8dd99c95eae1761fc7df19b6996ee3de2ad32b4a
P2 VAL request log SHA         9b462e6b6b20a57d076b32b98c9b27700fc1fc14f229c63a66baff97ba4d084e
```

## Safety boundary and next step

All P2 request ledgers are terminal `COMPLETED` with no HOLDOUT requests; the
90 HOLDOUT images remain sealed and unconsumed. No SSH tunnel, RTC/RTM/MQTT/TTS,
robot integration, or production edit was used. A read-only completion probe
found pre-existing user-owned dirty files in
`/home/yanbo/net_vlm_yanboversion/vlm`; they were left untouched. Therefore
`PRODUCTION_CODE_MODIFIED=false` is scoped to this P2 run and does not mean the
production worktree was clean before the run. Do not start P3 automatically.
Any follow-up must be a separately named and frozen development experiment,
starting with the latency regression and remaining hard-negative errors while
keeping VAL individual errors and HOLDOUT outside Prompt design.

The consolidated result is in
`/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/17_p2_final_report.md`.
