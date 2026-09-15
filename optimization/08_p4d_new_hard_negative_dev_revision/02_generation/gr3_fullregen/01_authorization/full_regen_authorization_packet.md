# P4D_GR3 full-regeneration authorization packet

```text
REVISION_ID=P4D_FULLREGEN_CODEX_PROFILE2_20260827_01
BATCH_ID=batch-person-fallen-v2-p4d-hardneg-fullregen-r2-camera1p5m
AUTHORIZED=false
WHY_FULL_REGEN_REQUIRED=account/profile changed
OLD_IMAGES_REUSED=0
NEW_LOGICAL_IMAGE_SLOTS=440
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation (server-side gpt-image-2 capability)
NO_RETRY_GUARANTEE=false
WRAPPER_MAX_RETRIES=3
EFFECTIVE_POSSIBLE_ATTEMPTS_PER_LOGICAL_SLOT=4
CONCURRENCY=1
FAIL_FAST_429=true
FAIL_FAST_401=true
FAIL_FAST_403=true
EXACT_MONETARY_COST=UNKNOWN
PROVIDER_REQUESTS=0
```

`authorized=false` is intentional and may not be changed by editing this file.
Generation requires a new user instruction explicitly authorizing the current
Codex profile and accepting that GR1's 192 historical images do not enter this
new revision. The current runtime cannot guarantee one provider attempt per
logical slot, so the preparation is also blocked on retry policy until that is
resolved or explicitly accepted in a separately authorized revision.
