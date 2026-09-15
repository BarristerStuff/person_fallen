# P4D GR3Q7 — execution final

```text
P4D_GR3Q7_STATUS=WINDOW_CAP_REACHED_SUCCESS
STOP_REASON=WINDOW_CAP_REACHED_SUCCESS
SIMULTANEOUS_GUARD_REACHED=null

LOGICAL_INVOCATIONS=20
SUCCESS=20
CONTENT_POLICY_REFUSALS=0
OTHER_CONFIRMED_FAILURES=0
NEW_COMPLETION_UNKNOWN=0
UNIQUE_NATIVE_RETRY_EVENTS=2
OBSERVED_PHYSICAL_ATTEMPT_LOWER_BOUND=22
HTTP200=20
HTTP429=0
HTTP401=0
HTTP403=0
HTTP5XX=0
NETWORK_ERRORS=0
TIMEOUTS=0

CURRENT_VERIFIED_SUCCESS=171
CURRENT_COMPLETION_UNKNOWN=1
CURRENT_SAFE_EXECUTABLE_OUTSTANDING=268
FORMAL_INGEST=false
MEDIA_ADDED=0
LABELS_ADDED=0
C3=false
VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_IMAGES_ACCEPTED=0
```

The canonical SQLite SHA-256 is `1ea9ad7a823b4f12d2da6211d47a91d9d0255447e6beb4d287d575251904c226`.  The terminal execution freeze SHA-256 is `9adc539e0b55a9207111b025bebdefcc4951760616b83f9680f91df28ef5aaf9`; its sidecar matches and all 78 bound artifacts verified.

Provider-output limitation: each successful raw image was `1672×941`, despite requesting `1536×1024`; the final output contract, not raw-size identity, was the frozen dimension gate and all final files are `1920×1080`.

The formal dataset was only read.  Its final validator status is valid with 0 errors, full hash check true, 387 existing warnings, and zero active P4D formal references.  The next action is **not** automatic continuation: retain the remaining 268 safe executable slots and the single quarantine slot unchanged pending a new explicit authorization and separate revision.
