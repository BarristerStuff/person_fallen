# 35 — P4D_GR2 lineage and provider preflight

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR2_NAME=P4D_GR2_GENERATION_CONTINUATION
P4D_GR2_STATUS=FULL_REGEN_AUTHORIZATION_REQUIRED
P4D_STATUS=GENERATION_REQUIRED
FROZEN_HASHES_ALL_MATCH=true
GR1_BLOCKED_FREEZE_VERIFIED=true
GR1_LEDGER_SHA_MATCH=true
GR1_PRESERVED_VERIFIED=192
GR2_OUTSTANDING_DERIVED=248
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation (server-side gpt-image-2 capability)
PROFILE_CONTINUITY=false
ACCOUNT_CHANGED=true
CONTINUATION_COMPATIBLE=false
AUTH_CHANGE=account_or_profile_change
GR2_PROVIDER_REQUESTS=0
FORMAL_INGEST_EXECUTED=false
C3_EXECUTED=false
NEW_VAL_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

## 已确认事实

- The six authoritative P4D frozen artifacts still match their recorded SHA-256 values. The GR1 blocked terminal freeze sidecar and the GR1 append-only ledger SHA also match their recorded values.
- Independent inventory verification found 192 GR1 success slots with existing raw/final files, matching ledger SHA-256 values, Pillow verification/load success, raw native dimensions 1672×941, and final dimensions 1920×1080. No preserved file was rewritten.
- The frozen 440-slot set derives 248 outstanding slots: 32 historical GR1 `FAILED_429`, 2 historical GR1 `FAILED_401`, and 214 `NEVER_STARTED`. The union is 440, intersection is 0, and missing/unexpected IDs are 0.
- Current explicit Codex capability is ready and resolves to provider `codex` with request model `gpt-5.4`; no image request was sent.
- The safe profile fingerprint comparison differs between the historical GR1 Codex profile and the current profile. Raw account IDs, user IDs, tokens, cookies, and API keys were not written to GR2 artifacts.

## 实验判断

`FULL_REGEN_AUTHORIZATION_REQUIRED` is the fail-closed lineage decision. A same-provider/model/backend match does not make a different account/profile safe for a mixed set of 192 preserved images plus new images. A session refresh is allowed only when profile continuity is proven; that condition is false here. This is an authorization/lineage stop, not an image-quality or semantic result.

## 风险与限制

- The installed GPT Image 2 wrapper reports a native `max_retries=3` policy and exposes no no-retry flag in its current command help. Since GR2 issued zero requests, no retry or quota spend occurred. Any future authorized continuation needs an explicit no-automatic-retry path before scheduling.
- The dataset validator's current `ingest_media.py` interface has no `validate` subcommand; the requested probe was recorded as unavailable and the repository's read-only `tools/validate_dataset.py --json` validator was used instead.
- The shared dataset can change outside P4D; boundary snapshots therefore bind counts, CSV hashes, and P4D-reference hits rather than assuming global counts remain constant.

## 下一阶段建议

Obtain explicit authorization for a full new generation lineage, or restore/prove the exact historical GR1 Codex profile without exposing credentials. Do not generate 440 images under the current profile, do not mix accounts, and do not proceed to ingest, C3, NEW_VAL, or HOLDOUT.
