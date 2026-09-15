# P4D GR3Q4 quota strategy analysis

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P4D_GR3Q4_NAME=P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN
P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q4_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q4_EXECUTION_NOT_EXECUTED=true
P4D_STATUS=GENERATION_REQUIRED

CURRENT_VERIFIED_SUCCESS=102
OUTSTANDING=338
PARTIAL_GROUP_COUNT=1

FIRST_WINDOW_MAX_LOGICAL_INVOCATIONS=68
LATER_WINDOW_DEFAULT_MAX_LOGICAL_INVOCATIONS=70
MAX_OBSERVED_PHYSICAL_ATTEMPT_LOWER_BOUND=80
MAX_NATIVE_RETRY_SCHEDULED_EVENTS_THIS_WINDOW=5
NATIVE_MAX_RETRIES=3
OUTER_RETRY=false
CONCURRENCY=1

PROVIDER_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
C3=false
NEW_VAL=0
FULL_440_QA=NOT_REACHED
P4D_VALIDATED_GENERATION_BASELINE=false
```

## 已确认事实

GR3Q4 是一个新的、独立的 quota-window preparation revision，目标是治理生成调度、quota 风险、执行顺序和可恢复性；它不是语义 Prompt 优化，也没有修改 Prompt、taxonomy、group assignment、planned split、C3、GT 或图像生成配置。GR3Q2E 的 `STOPPED_BY_FAILURE_POLICY` 和 GR3Q3 的 `WAITING_FOR_PROVIDER_QUOTA_RESET` 被原样保留，旧 ledger 没有被继续写入。

当前冻结的 440-slot manifest 通过完整审计：SHA-256 为 `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`，440 行、440 个唯一 prompt ID、88 个 group、cross-split group=0，角色为 hard_negative=300、positive=100、ordinary_negative=40，planned split 为 `NEW_DESIGN=265`、`NEW_SCREEN=175`。prompt bytes mismatch=0。

独立重建的当前库存是 102 个完整性验证通过的成功 slot：历史 GR3E Profile-A=99，GR3Q2E Profile-B=3。当前 338 个 outstanding 精确分解为：确认的历史 HTTP 429=1、`NEVER_STARTED=337`、`COMPLETION_UNKNOWN=0`。当前没有 provider 请求、没有新图像、没有 formal ingest、C3、NEW_VAL 或 HOLDOUT。

当前 quota evidence 来自 Q2E 的真实失败 raw：provider 报告 `usage_limit_reached`，reset 为 `2026-08-28T18:49:07+08:00`；设置 653 秒安全 margin 后，`NOT_BEFORE_LOCAL=2026-08-28T19:00:00+08:00`。本次实际捕获的本机时间为 `2026-08-28T16:00:31.393314+08:00`，所以 time gate 未通过。没有 sleep、cron、后台等待或自动恢复。

策略将第一窗口限制为 68 个 logical invocations，后续独立窗口默认最多 70 个；同时记录 observed physical-attempt lower bound guard=80 和 native retry scheduled-event guard=5。理论最大尝试数仅为 `68×(1+3)=272`，不是实际 provider 账单、也不是已发生尝试数；本次三类执行计数均为 0。

## 实验判断

在当前时间 gate 未通过且没有独立 campaign authorization 的双重条件下，`PROVIDER_REQUESTS=0` 是唯一合规结论。即使 runtime auth/session 显示 ready，也不能把它解释成用户授权。当前准备检查本身通过，阻塞原因仅为时间门；达到安全时间后，若仍没有独立授权，状态应转为 `AWAITING_CAMPAIGN_AUTHORIZATION`，仍保持请求数为 0。

68-slot 首窗口不是按旧的 manifest ordinal 连续扫过，而是先完成唯一 partial group，再按 role、taxonomy、planned split 的 normalized deficit 做 deterministic group-level round robin。这样可以尽快打破当前只有 floor-sitting/kneeling hard-negative 成功的执行顺序偏差，同时不改变任何数据标签或 split。选择过程不读取视觉质量、C3 或模型错误。

每个窗口独立 ledger、SQLite 和 terminal freeze，且 provider/transport 错误或无效输出硬停止；physical/retry guard 是主动风险停止，不应被错误标为 provider failure。精确 monetary cost 继续记为 `UNKNOWN`。

## 风险与限制

- reset timestamp 只是 provider 返回的窗口证据，不保证 19:00 后配额一定恢复；安全 margin 也不是 provider SLA。
- 68/70 是本项目的保守窗口上限，不是 provider 官方 quota。native runtime 仍可能产生最多 3 次 native retry，必须分开记 logical、observed physical lower bound、retry events 和 theoretical maximum。
- 当前 profile fingerprint 是历史 Profile-A，而 Q2E 的 3 张成功图像属于 Profile-B。Q2 lineage policy 允许按 provenance stratum 记录这一事实，但不能将当前 fingerprint 错写成 B，也不能无依据创建 Profile-C。
- 当前窗口尚未执行，因而没有 latency、生成质量、semantic sentinel、full mechanical QA 或分类指标；不得用 102 张历史生成图像宣称新的 440-image baseline。
- `images generate --help` 的只读 capability 调用返回 CLI `invalid_command`/returncode=2，但 config inspect、doctor、auth inspect 均成功且没有 image-generation provider request；这应作为 CLI help 证据保留，不得伪造为成功的生成测试。

## 下一阶段建议

不要等待或自动重启本任务。只有在本机时间达到 `2026-08-28T19:00:00+08:00` 后，并且用户在新的独立顶层消息中明确授权 campaign 范围，才可以重新读取时间、provider/runtime、profile 和 102/338 inventory，然后手动启动 `WINDOW_01`。窗口第一 slot 必须是 `PF_P4D_HN_KNEEL_G009_V03`；任一 429/401/403/5xx/timeout/connection error/invalid provider output、physical lower bound 达 80 或 retry events 达 5，都必须停止且独立 freeze。

本报告对应的准备工件位于：

- [quota_window_evidence.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/00_preflight/quota_window_evidence.json)
- [time_gate.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/00_preflight/time_gate.json)
- [run_config.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/05_window_01/run_config.json)
- [terminal freeze](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/freeze/p4d_gr3q4_terminal_freeze.json)

