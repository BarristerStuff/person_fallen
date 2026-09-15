# P4D GR3Q6 authorized execution

## 已确认事实

Q6 was executed in the separate revision
`quota_campaign_window_03_gr3q6_authorized_20260831_01`; neither Q5 nor the
sealed Q6 preparation revision was modified.  The Q5 freeze, Q6 preparation
freeze, and Q6 supplemental preparation freeze all passed sidecar and bound
artifact verification before the first request.

```text
Q6_PLAN_SHA256=11821c0b090706467cac98e84cddcecd76f9d2ac7d7a2b3ae0368e86c3a1f2f8
Q6_PLAN_ROWS=33
FIRST_REQUEST=PF_P4D_NEG_CHAIR_G003_V03
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
ADAPTER_VERSION=CODEX_SAFE_STAGED_CV_V1
CONCURRENCY=1
OUTER_RETRY=false
NATIVE_MAX_RETRIES=3

LOGICAL_INVOCATIONS=10
SUCCESS=9
HTTP200=9
HTTP429=0
HTTP401=0
HTTP403=0
HTTP5XX=0
TIMEOUTS=0
UNIQUE_NATIVE_RETRY_EVENTS=3
OBSERVED_PHYSICAL_ATTEMPT_LOWER_BOUND=13
```

The first three chair-group rows (V03/V04/V05) all completed successfully.
The next six frozen hard-negative rows also completed successfully.  No
eleventh logical invocation was sent.

## 后冻结勘误

The initial execution terminal freeze is preserved exactly as written, but its
classification of logical request 10 was wrong.  The raw outer envelope for
`PF_P4D_HN_MAINT_G006_V02` is `error.code=network_error` with a send-request
failure and no image result.  It is not a content-policy refusal.  The old
classifier matched the SSE metadata field name `safety_identifier`, rather
than an explicit provider refusal, and falsely assigned
`CONTENT_POLICY_REFUSAL_CONFIRMED`.

The corrected state is `COMPLETION_UNKNOWN=1`, not a policy refusal.  The same
logical invocation had 3 parsed `retry_scheduled` events and 4 parsed
`request.started` events, so the retry cap was also reached after it completed.
The safety-preserving primary stop interpretation is
`STOPPED_COMPLETION_UNKNOWN`; no resend is permitted.  A separate immutable
post-freeze erratum records this without altering the original terminal freeze.

## 风险与边界

The network failure proves neither semantic failure nor human rejection.  The
slot remains outstanding and must not be resent in this revision.  No C3,
semantic filter, formal ingest, NEW_VAL, VAL, or HOLDOUT operation was run.
