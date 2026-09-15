# P4D GR3 quota-window generation campaign authorization packet

```text
authorized=false
explicit_campaign_authorization=false
authorization_present=false
template_is_authorization=false
MAX_MANUAL_WINDOWS=5
FIRST_WINDOW_MAX_LOGICAL_INVOCATIONS=68
LATER_WINDOW_DEFAULT_MAX_LOGICAL_INVOCATIONS=70
CONCURRENCY=1
OUTER_RETRY=false
NATIVE_MAX_RETRIES=3
PHYSICAL_ATTEMPT_LOWER_BOUND_GUARD=80
NATIVE_RETRY_SCHEDULED_EVENT_GUARD=5
NO_BACKGROUND_EXECUTION=true
NO_CRON=true
NO_SLEEP_TO_NEXT_WINDOW=true
PROVIDER_REQUESTS=0
```

本 packet 是授权模板和治理记录，不是授权。当前顶层消息没有独立的等价 campaign authorization，因此不得创建 attestation、不得启动第一窗口，也不得把本段模板视为用户已同意。模板 SHA-256 为 `d6f205d49d4b59c8bb977a0d096f34c6cbe098d84f3f2b5b5bc37623ab7eb0c5`。

用户未来必须在新的独立顶层消息中明确授权以下范围：

> 我明确授权 person_fallen P4D_GR3 quota-window generation campaign：保留当前已经完整性验证通过的102张当前GR3 generation-lineage图像，继续处理冻结的338个 outstanding slots。授权最多5个由我手动启动的独立 quota-window execution revisions；第一个 window 最多68个 logical invocations，后续每个 window 最多70个；每个 window concurrency=1、outer_retry=false，同时接受 GPT Image 2 native max_retries=3、精确费用未知以及 quota/成本风险。任何 window 中 returned 429/401/403/5xx/timeout/connection error 立即停止；observed physical-attempt lower bound 达80或 native retry events 达5也主动停止。每个 window 必须独立 freeze，禁止后台等待、cron 或自动跨 window 执行。该授权只覆盖图像生成，不授权 formal ingest、C3、NEW_VAL、HOLDOUT 或生产集成。

该模板只覆盖图像生成；每个 window 必须手动启动并独立 freeze。它不授权 formal ingest、C3、NEW_VAL、HOLDOUT、生产集成、后台等待、cron 或自动跨 window 执行。
