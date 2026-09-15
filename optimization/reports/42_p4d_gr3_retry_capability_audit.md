# 42 — P4D_GR3 retry capability audit

```text
NO_RETRY_GUARANTEE=false
WRAPPER_MAX_RETRIES=3
EFFECTIVE_POSSIBLE_ATTEMPTS_PER_LOGICAL_SLOT=4
CONCURRENCY_PREREGISTERED=1
FAIL_FAST_429=true
FAIL_FAST_401=true
FAIL_FAST_403=true
P4D_GR3_STATUS=BLOCKED_RETRY_POLICY
PROVIDER_REQUESTS=0
```

## 已确认事实

The installed wrapper is `/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs` (SHA `f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe`), dispatches to the installed binary, and the current runtime reports native retry policy `{'base_delay_seconds': 1, 'max_retries': 3}`. `images generate --help` exposes no supported `--no-retry` or `--max-retries` switch. The shared config inspection exposed no retry control. The third-party runtime was not modified.

## 实验判断

An outer Python loop with no retries would not prove no-retry: the native CLI
could still turn one logical slot into up to four provider attempts. The safe
preparation value is therefore `NO_RETRY_GUARANTEE=false`, not a misleading
`automatic_retry=false` claim.

## 风险与限制

The exact provider-side billing/attempt behavior for every error class is not
asserted; the upper-bound planning multiplier of four is used from the observed
`max_retries=3`. A future runner must make first 429/401/403 a global stop and
must not rely on hidden internal retries.

## 下一阶段建议

Wait for a supported one-attempt mechanism or explicit human acceptance of the
runtime retry risk. Do not create or run a generation runner in this revision.
