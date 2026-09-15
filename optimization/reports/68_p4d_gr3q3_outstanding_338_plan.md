# P4D GR3Q3 outstanding 338 recovery plan

```text
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
OUTSTANDING=338
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0
PROVIDER_REQUESTS=0
```

## 已确认事实

用 frozen manifest 中未出现在 102-success inventory 的 prompt IDs 计算 outstanding，得到精确 `440 - 102 = 338`。唯一已确认 provider failure 是：

```text
recovery_order=1
prompt_id=PF_P4D_HN_KNEEL_G009_V03
parent_request_id=P4D_GR3Q2E_RECOVERY_0004_PF_P4D_HN_KNEEL_G009_V03
parent_http_status=429
parent_state=FAILED_CONFIRMED_HTTP_429
```

其余 337 个 slot 在父 GR3E/Q2E 证据中仍是 `NEVER_STARTED`。没有 `COMPLETION_UNKNOWN`。恢复顺序是先处理这个唯一 429 slot，然后按 frozen manifest ordinal 顺序；[outstanding_338.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/02_inventory/outstanding_338.csv) SHA-256 为 `0b98dce9ca21054548806af97074317f6648bfe89e70549c2799e27cecf4602f`。

待恢复清单的角色和 split 分布为：

| 字段 | 计数 |
|---|---:|
| hard_negative | 198 |
| positive | 100 |
| ordinary_negative | 40 |
| NEW_DESIGN | 195 |
| NEW_SCREEN | 143 |

每个新 slot 的预注册窗口约束：`MAX_LOGICAL_INVOCATIONS_THIS_WINDOW=90`、`concurrency=1`、`outer_retry=false`、native `max_retries=3`。90 是本 revision 的保守停止上限，不是 provider 官方 quota，也不保证 90 个都能成功。

## 实验判断

当前清单可以作为未来新 execution revision 的输入，但本次不创建可运行队列：`eligible_after_authorization=false`。即使 19:00 后，必须先收到新的、独立顶层用户授权，明确当前 quota window、最多 90 个 logical invocations、失败即停止和成本风险。

## 风险与限制

- 不应把 `NEVER_STARTED` 解读为 provider 已经尝试过；它只表示当前已核实 ledger 中没有开始事件。
- G009_V03 的 429 evidence 来自 Q2E，不能把它转换成成功，也不能重写 Q2E ledger。
- 若未来第一个 slot 仍是 429，必须在一个 logical invocation 后全局停止；不得 outer retry、自动切换 schema、改变 prompt、改变 batch 或跨到 VAL/HOLDOUT。

