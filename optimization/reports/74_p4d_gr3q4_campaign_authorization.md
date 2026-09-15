# P4D GR3Q4 campaign authorization and runtime gate

```text
P4D_GR3Q4_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
AUTHORIZATION_PRESENT=false
AUTHORIZED=false
EXPLICIT_CAMPAIGN_AUTHORIZATION=false
TEMPLATE_IS_AUTHORIZATION=false
EXECUTION_ELIGIBLE=false
PROVIDER_REQUESTS=0
```

## 已确认事实

本 revision 建立了可复用的 campaign authorization packet，但当前顶层用户消息只包含任务模板，没有独立的、等价的 campaign authorization。因此没有创建 `campaign_authorization_attestation.json`，没有启动首窗口，也没有 provider request。packet JSON SHA-256 为：

```text
a02fc2a3b691eb493328d21dd56f748027c8e41211dca2e133b8617c700cfe98
```

packet markdown SHA-256 为：

```text
a3fb9d13009f17be0519074a8a23bccebadf8b994d0753bc52ca8653f2476a78
```

模板固定记录以下范围和停止条件：

```text
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
SCOPE=image_generation_only
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
```

只读 gpt-image-2 capability audit 得到：

```text
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
AUTH_READY=true
ENDPOINT_REACHABLE=true
TLS_OK=true
NATIVE_MAX_RETRIES=3
OUTER_RETRY=false
ACTIVE_PROFILE_STRATUM=PROFILE_A_RESTORED
PROFILE_FINGERPRINT_SAFE_HASH=ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe
```

wrapper SHA-256 是 `f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe`，binary SHA-256 是 `1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba`。预注册生成参数保持 `native_size=1536x1024`、`quality=medium`、`format=png`，controlled 16:9 crop 后由 Pillow LANCZOS 转成 `1920x1080`。没有修改生产代码、Ollama 或任何 provider 配置。

provider/runtime 命令全部是只读审计：`config inspect`、`doctor`、`auth inspect`；`images generate --help` 返回了 CLI `invalid_command`（returncode=2）及 usage 文本，但它没有调用图像生成 endpoint。该 help 异常已原样保存在 capability audit，不被当作生成成功。

## 实验判断

auth/session ready 只说明当前工具可以尝试连接 provider，不等同于用户对有成本的图像生成授权。任务正文内的推荐授权原文只是 packet 模板；在新的独立顶层消息收到明确授权前，`authorization_present=false`、`execution_eligible=false` 和 `PROVIDER_REQUESTS=0` 必须保持。

当前时间门也未通过：`RESET_LOCAL=2026-08-28T18:49:07+08:00`，`NOT_BEFORE_LOCAL=2026-08-28T19:00:00+08:00`，捕获时间 `CURRENT_LOCAL=2026-08-28T16:00:31.393314+08:00`。因此当前最终状态优先写为 `WAITING_FOR_PROVIDER_QUOTA_RESET`；即便时间先通过，没有授权也只能转成 `AWAITING_CAMPAIGN_AUTHORIZATION`。

## 风险与限制

- 用户未来授权必须在新的独立顶层消息中明确覆盖当前 338 slots、最多 5 个手动窗口、68/70 caps、native retries、失败硬停止、成本未知和不包含 ingest/C3/NEW_VAL/HOLDOUT/生产集成；不能引用模板本身作为已授权证据。
- Profile-A restored 是当前只读观察值，不是用户选定的 account；若执行时 profile 既不匹配历史 A 也不匹配历史 B，应暂停为 `PAUSED_NEW_PROFILE_STRATUM_DECISION_REQUIRED`，不得自动创建 C/D/E。
- capability audit 的 endpoint reachable/TLS/auth ready 不保证 quota reset、生成成功或费用可控。
- 未执行任何窗口，因此没有实际 request payload、raw response、retry、latency 或图片输出可供报告；不应虚构这些字段。

## 下一阶段建议

时间 gate 通过后，仍等待新的 standalone authorization。收到后必须先把授权原文/消息 ID（或等价证据）写入新的 attestation，再重新运行只读 runtime/profile gate；任何 material config、wrapper、binary 或 profile mismatch 都停止。窗口运行必须人工启动、concurrency=1、outer retry=false，并单独生成 ledger、raw/request logs、SQLite stable-close freeze 和 independent verification。

工件：[campaign_authorization.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/04_authorization/campaign_authorization.json)、[campaign_authorization_packet.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/04_authorization/campaign_authorization_packet.md)、[provider_runtime_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/00_preflight/provider_runtime_audit.json)。

