# 39 — P4D_GR2 final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=COMPLETE
P2_EXECUTED=false
P3_EXECUTED=false
P4D_GR2_NAME=P4D_GR2_GENERATION_CONTINUATION
P4D_GR2_STATUS=FULL_REGEN_AUTHORIZATION_REQUIRED
P4D_STATUS=GENERATION_REQUIRED
FROZEN_HASHES_ALL_MATCH=true
GR1_BLOCKED_FREEZE_VERIFIED=true
GR1_LEDGER_SHA_MATCH=true
GR1_PRESERVED_IMAGES=192
GR1_FAILED_ATTEMPTED=34
GR1_NEVER_STARTED=214
GR2_GENERATED_IMAGES=0
CURRENT_TOTAL_IMAGES=192
OUTSTANDING_SLOTS=248
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation (server-side gpt-image-2 capability)
PROFILE_CONTINUITY=false
SESSION_REFRESHED=false
ACCOUNT_CHANGED=true
PROVIDER_CHANGED=false
MODEL_CHANGED=false
BACKEND_CHANGED=false
CONTINUATION_COMPATIBLE=false
SMOKE_REQUESTS=0
SMOKE_SUCCESS=0
SMOKE_FAILURE=0
RAMP_REQUESTS=0
RAMP_SUCCESS=0
RAMP_FAILURE=0
GR2_TOTAL_REQUESTS=0
GR2_SUCCESS=0
GR2_FAILURES=0
HTTP_429=0
HTTP_401=0
HTTP_403=0
P4D_440_MECHANICAL_QA=NOT_REACHED
P4D_440_MAPPING_GATE=NOT_REACHED
P4D_440_LINEAGE_GATE=BLOCKED_ACCOUNT_PROFILE_MISMATCH
HUMAN_REVIEW_PACKAGE_GENERATED=false
SEMANTIC_REVIEW_STATUS=NOT_REACHED
P4D_IMAGES_ACCEPTED=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_ACTIVE_DATASET_REFERENCES=0
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
TERMINAL_FREEZE_PATH=/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr2/freeze/p4d_gr2_terminal_freeze.json
TERMINAL_FREEZE_SHA=SEE_SIDECAR
```

## 已确认事实

1. All authoritative P4D frozen hashes match. The GR1 blocked freeze (`7bb9bf547ab07ad9f0f64193aae2ee69d15f17d0eb8cfd05722ae3d79afe2fd9`) and append-only GR1 ledger (`20e00361c532f8386d3f160363cc76d12f104618b6c9fd270d2ec5c78a1a2fd4`) were independently verified.
2. GR1 preservation is 192; GR1 attempted failures are 34 (32 historical 429 plus 2 historical 401), and never-started is 214. Derived outstanding is 248; union/intersection/missing/unexpected are 440/0/0/0.
3. Current Codex doctor/auth is ready, but the safe historical/current profile fingerprints differ. Provider/model/backend labels otherwise match (`codex`/`gpt-5.4`/`image_generation (server-side gpt-image-2 capability)`).
4. GR2 made zero provider requests, zero retries, zero formal dataset mutations, zero C3 requests, zero NEW_VAL requests, and zero HOLDOUT requests. Dataset before/after snapshots are `{'media_count': 4521, 'label_count': 4521, 'batch_count': 43, 'split_count': 2058}` and `{'media_count': 4521, 'label_count': 4521, 'batch_count': 43, 'split_count': 2058}` with P4D active-reference hits `0`.

## 实验判断

`FULL_REGEN_AUTHORIZATION_REQUIRED` is the correct fail-closed result. This is not a provider usage-limit observation and not a semantic model result. It means the current account/profile cannot safely extend the frozen GR1 set. The current revision stops before smoke exactly as required.

## 风险与限制

- The shared dataset has external mutable state; counts and hashes are bound in the boundary snapshots. The current read-only validator is `valid`, `error_count=0`, `full_hash_check=true`, with historical warnings retained.
- Full 440 QA and human semantic review are not reached. The preserved 192 are mechanically verified but not semantically accepted.
- The image wrapper's observed retry policy is `max_retries=3`; no request was made, so no retry occurred. A future authorized continuation must make no-retry behavior explicit before spending quota.

## 下一阶段建议

Do not run GR2 generation under the current profile. Obtain explicit authorization for a full new generation lineage, or restore/prove the exact historical GR1 profile. Preserve GR1 forever, create a new revision for any materially changed account/provider/model, then perform full QA and human semantic review before ingest/C3. NEW_VAL and HOLDOUT remain forbidden.
