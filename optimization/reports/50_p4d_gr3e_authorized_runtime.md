# 50 — P4D_GR3E authorized runtime continuation

```text
P4D_GR3E_NAME=P4D_GR3E_FULL_REGEN_EXECUTION
P4D_GR3E_STATUS=BLOCKED_PROVIDER_USAGE_LIMIT
EXPLICIT_AUTHORIZATION_VERIFIED=true
AUTHORIZATION_ATTESTATION_SHA256=c5605ea785f04ba93b7017e9ccb0d586826a6c1094d0545538f2b5da67a5f7e9
PREPARATION_FREEZE_VERIFIED=true
FROZEN_ASSET_HASHES_VERIFIED=true
PROVIDER=codex
MODEL=gpt-5.4
BACKEND=image_generation
PROFILE_CONTINUITY_WITH_PREPARATION=True
AUTH_READY=True
SESSION_READY=True
ENDPOINT_REACHABLE=True
WRAPPER_SHA256=f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe
BINARY_SHA256=1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba
NO_RETRY_GUARANTEE=False
NATIVE_RUNTIME_MAX_RETRIES=3
OUTER_RETRY=false
POSSIBLE_PROVIDER_ATTEMPTS_UPPER_BOUND_PER_SLOT=4
```

## 已确认事实

- The current user authorization was attested in the separate continuation file; the preparation authorization packet and the previous no-auth terminal freeze were not edited.
- Runtime re-preflight passed for provider `codex`, model `gpt-5.4`, backend `image_generation`. The safe profile fingerprint continuity gate passed.
- The installed runtime remains wrapper `f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe` and binary `1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba`, with native `max_retries=3` and no supported no-retry guarantee.

## 实验判断

The 429 is a provider usage-limit stop, not a semantic or image-integrity result. The failed logical slot's stderr exposes four native provider attempts (initial request plus retry numbers 1–3); exact monetary cost remains unknown.

## 风险与限制

Successful requests without retry events are counted only as an observed lower bound. The upper bound remains 4 attempts per logical slot, or 1,760 for all 440 slots; it is not a billing statement.

## 下一阶段建议

Do not resume this sealed continuation. A separately authorized recovery/new revision must address the provider quota window and must not reuse this failed slot without a new, explicitly frozen recovery protocol.
