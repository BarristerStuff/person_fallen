# P4D GR3Q5 retry telemetry erratum

## 已确认事实

The parent terminal freeze was reverified without changing it.  Its SHA-256 is
`3c219c9d75803cd5427862c0255ab557e92969085a864b116435aea85f8817f2`;
the sidecar matches and all 40 bound artifacts match their recorded hashes.

The immutable Q5 raw response for `PF_P4D_NEG_CHAIR_G003_V03` was parsed one
JSON event line at a time.  The unique-event definition is
`event.type == "retry_scheduled"`; provider physical attempts use only
`event.type == "request.started"`.

```text
Q5_FROZEN_NATIVE_RETRY_EVENTS=6
Q5_RAW_SSE_UNIQUE_NATIVE_RETRY_EVENTS=3
Q5_FROZEN_PHYSICAL_ATTEMPT_LOWER_BOUND=17
Q5_FAILED_LOGICAL_REQUEST_STARTED_EVENTS=4
Q5_RAW_SSE_PHYSICAL_ATTEMPT_LOWER_BOUND=14
  = 10 one-attempt Q5 successes + 4 failed-slot request.started events
```

The historical frozen values are preserved.  This erratum does not rewrite Q5
reports, SQLite, raw responses, generated images, terminal freeze, status, or
stop reason.

## 实验判断

The former textual-substring approach had a double-counting risk because one
retry JSON event can contain `retry_scheduled` in multiple fields.  Q6 now
ships `retry_event_parser_v2.py`, and its self-test against the immutable Q5
raw stream passes with exactly 3 retry events and 4 `request.started` events.

## 风险与边界

The corrected counters are raw-SSE-derived lower bounds, not a provider billing
statement.  They are for future Q6 guard accounting only.  Q5 remains
`STOPPED_PROVIDER_429` because its explicit HTTP 429 already satisfied the
global-stop rule.
