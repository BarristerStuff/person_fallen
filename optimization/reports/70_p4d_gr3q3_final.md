# P4D GR3Q3 final preparation report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_STATUS=GENERATION_REQUIRED
FULL_341_RECOVERY_COMPLETE=false
P4D_VALIDATED_GENERATION_BASELINE=false

P4D_GR3Q3_NAME=P4D_GR3Q3_QUOTA_WINDOW_RECOVERY
P4D_GR3Q3_REVISION=P4D_GR3Q3_QUOTA_WINDOW_RECOVERY_20260828_02
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q3_EXECUTION_NOT_EXECUTED=true

CURRENT_SUCCESS=102
PROFILE_A_SUCCESS=99
PROFILE_B_SUCCESS=3
OUTSTANDING=338
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0

CURRENT_LOCAL_TIME=2026-08-28T15:15:27.177+08:00
RESET_LOCAL=2026-08-28T18:49:07+08:00
NOT_BEFORE_LOCAL=2026-08-28T19:00:00+08:00
TIME_GATE_PASS=false
EXPLICIT_WINDOW_AUTHORIZATION=false

PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
NATIVE_MAX_RETRIES=3
OUTER_RETRY=false
WINDOW_CAP=90

PROVIDER_REQUESTS=0
PHYSICAL_ATTEMPTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
C3=false
NEW_VAL=0
P4D_ACTIVE_DATASET_REFS=0
PRODUCTION_CODE_MODIFIED=false

SEMANTIC_METRICS=N/A
FULL_440_QA=NOT_REACHED
```

## 已确认事实

本轮严格停在 quota-window preparation gate。父 Q2E canonical freeze 为 `9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44`，sidecar 和 17/17 artifact bindings 通过；Q2E 的 429 raw evidence SHA 为 `a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99`。冻结 440 manifest SHA 为 `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`，440/440 prompt byte、440 unique IDs、88 groups、cross-split=0 均通过。

重新验证后的当前 success inventory 是 99 个历史 GR3E Profile-A 加 3 个 Q2E Profile-B，共 102；全部文件 hash/Pillow/final dimension 通过，GR1 hash/samefile/symlink reuse 均为 0。338 outstanding 的状态精确为 1 个已确认 HTTP 429、337 个 NEVER_STARTED、0 个 COMPLETION_UNKNOWN，第一顺序为 `PF_P4D_HN_KNEEL_G009_V03`。

父共享数据集只读 validator 的 before/after 均为：`status=valid`、`error_count=0`、`full_hash_check=true`、`warning_count=387`，counts `media=5081, labels=4881, batches=45, splits=2618`；四个 annotation CSV hash 未改变，active P4D references=0。未执行正式 ingest、C3、VAL、NEW_VAL、HOLDOUT，也没有修改生产代码、Ollama 或共享 split CSV。

最终 terminal freeze：[p4d_gr3q3_terminal_freeze.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/freeze/p4d_gr3q3_terminal_freeze.json)，SHA-256：

```text
7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697
```

sidecar 同 hash；[terminal_freeze_verification.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/05_checkpoints/terminal_freeze_verification.json) 为 `all_pass=true`、`all_bound_artifacts_match=true`、`provider_requests_added=0`。

Preparation artifact hashes:

```text
RUN_CONFIG_SHA256=f938046ec7ea10a7f851151de4c3b771686e58cccc9adc67af7a560a9451da84
CURRENT_102_INVENTORY_SHA256=c77d57e33da99add3744c03c9bfb5344b3b81d5c3b5a59a1481443ea6078831b
OUTSTANDING_338_SHA256=0b98dce9ca21054548806af97074317f6648bfe89e70549c2799e27cecf4602f
QUOTA_WINDOW_LEDGER_SHA256=108e7ff3888f12316107d7be1705717af2145e7a348ed98cbafaf4ace81e13d0
QUOTA_WINDOW_SQLITE_SHA256=6397a1726e9762443b2b71ce8917706fff9641925660af1717a068f46f84fbf3
REQUEST_LOG_SHA256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
RAW_RESPONSE_LOG_SHA256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
NEW_RUNNER_SHA256=N/A_NO_EXECUTION_RUNNER_CREATED
```

An initial local preparation attempt stopped before any provider call because
the SQLite insert statement had 23 placeholders for a 25-column table. That
failed attempt was moved, without deletion, to
`/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02_failed_preparation_attempt_20260828_01/`;
the corrected preparation then created the sealed revision above. It contains
no provider request or generated image and does not alter the parent Q2E
revision or shared dataset.

## 实验判断

当前结果是一个可审计的 zero-request recovery preparation，不是 90-slot generation result，也不是完整 P4D baseline。时间 gate 在 19:00 前失败，且当前顶层消息没有新的 GR3Q3 standalone authorization；因此没有任何 provider 请求是唯一合规结论。Q2E 的已消费授权不会自动延伸到 GR3Q3。

当前 runtime 的安全 profile fingerprint 新审计结果与 Profile-A 相同、不是 Q2E Profile-B；Q2 lineage policy 允许把 profile 作为 provenance stratum 记录，而不单独触发 semantic-lineage reset，但未来执行必须明确记录该 profile 事实，不能将它写成 B 或忽略它。

## 风险与限制

- reset timestamp 是 provider 返回的窗口信息，不是配额恢复保证；19:00 仅是安全 margin 后的最早时刻。
- 当前 auth/session readiness 不是 authorization。没有 standalone GR3Q3 authorization，不得发 smoke 请求。
- 90 logical-slot cap 不是 provider 官方 quota；任一未来 429/401/403/timeout/5xx/connection error 或 invalid provider output 都必须全局停止，不能 outer retry。
- semantic metrics 全部 `N/A`；不得从 102 张生成文件推断分类 accuracy，也不得把 GR1/Q2E 历史结果混成新 baseline。

## 下一阶段建议

不要 sleep、后台等待、cron 自动运行或自动恢复。待本机时间达到 `2026-08-28T19:00:00+08:00` 后，由用户在新的独立顶层消息中明确授权当前 quota window 最多 90 个 logical invocations；之后创建/确认新的执行 revision，重新读取时间 gate、provider/runtime、当前 profile provenance 和 102/338 inventory，先以 `PF_P4D_HN_KNEEL_G009_V03` 做第一 slot，并在任一规定错误后立即停止。若没有该独立授权，继续保持 `AWAITING_QUOTA_WINDOW_AUTHORIZATION`（在时间 gate 已通过之后）且 provider requests=0。

本报告之前的 P4D 报告 65 及更早文件未覆盖；Q2E 失败历史保持不变。
