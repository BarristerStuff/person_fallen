# P4D GR3Q4E Window01 execution

```text
STATUS=STOPPED_BY_FAILURE_POLICY
STOP_REASON=missing_image_result
LOGICAL_INVOCATIONS=31
SUCCESS=30
FAILED=1
COMPLETION_UNKNOWN=0
RETRY_EVENTS=0
PHYSICAL_ATTEMPT_LOWER_BOUND=31
FORMAL_INGEST=false
C3=false
HOLDOUT_REQUESTS=0
```

所有请求按冻结 first-window order 单并发执行。任何非成功或 completion-unknown 已触发全局停止；没有 outer recovery。
