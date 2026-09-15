# P4D GR3Q4 adaptive execution order

```text
P4D_GR3Q4_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
ADAPTIVE_ORDER_ROWS=338
ADAPTIVE_ORDER_UNIQUE_PROMPT_IDS=338
ADAPTIVE_ORDER_EXACT_OUTSTANDING=true
PARTIAL_GROUP_COUNT=1
FIRST_WINDOW_CAP=68
FIRST_WINDOW_PLANNED_ROWS=68
FIRST_WINDOW_PLANNED_GROUP_COUNT=14
PROVIDER_REQUESTS=0
```

## 已确认事实

`adaptive_execution_order.csv` 是基于 frozen 440 manifest、独立重建的 102-success inventory 和 338-outstanding inventory 重新计算的本地计划；原始 manifest 没有被改写。计划 SHA-256 为：

```text
acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033
```

计划包含 `execution_order`、`prompt_id`、`group_id`、`variant_id`、`role`、`taxonomy`、`planned_split`、`original_manifest_ordinal`、`current_group_success_count`、`current_group_outstanding_count`、`parent_state`、`selection_reason` 和 group-level deficit/tie-break 证据。338 行对应 338 个唯一 outstanding prompt ID，集合完全相等。

实际识别到的 partial group 只有 1 个：

| group | 当前成功 | outstanding | 处理顺序 |
|---|---:|---:|---|
| `PF_P4D_HN_KNEEL_G009` | 2 | 3 | 先完成该 group |

其余 67 个仍有缺口的 group 都是完整的 5-slot outstanding group；已完成的 group 不会被重复排入。partial group 内按 variant ordinal 执行，并将历史确认失败的 `PF_P4D_HN_KNEEL_G009_V03` 放在第 1 位；随后为 V04、V05。首窗口计划 CSV 为 68 行，SHA-256 为：

```text
2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd
```

首窗口由 3 个 partial slot 加 13 个完整 group 组成（共 14 个 group），首尾 prompt 为：

```text
FIRST_PROMPT_ID=PF_P4D_HN_KNEEL_G009_V03
LAST_PROMPT_ID=PF_P4D_HN_SQUAT_G005_V05
```

窗口内按当前缺口平衡后的计划分布是：

| 维度 | 计划计数 |
|---|---:|
| hard_negative | 23 |
| positive | 35 |
| ordinary_negative | 10 |
| NEW_DESIGN | 30 |
| NEW_SCREEN | 38 |

taxonomy 计数为：`kneeling_half_kneeling=3`，以及各 5 个 slot 的 `supine_ground_lying`、`standing_walking`、`prone_ground_lying`、`side_lying`、`chair_seated_normal_work`、`curled_or_partially_occluded_lying`、`intentional_ground_lying`、`multi_person_one_lying`、`horizontal_corridor_ground_lying`、`pushup_plank`、`crawling_quadruped_support`、`ground_maintenance`、`squat_crouch_deep_bend`。这将首窗口从现有的 floor-sitting/kneeling 偏斜中拉向 positive、ordinary-negative 和新的 hard-negative taxonomy，但没有移动任何 planned split。

首窗口 group 顺序为：

```text
1  PF_P4D_HN_KNEEL_G009       (partial, 3 slots)
2  PF_P4D_POS_SUPINE_G004
3  PF_P4D_NEG_STAND_G003
4  PF_P4D_POS_PRONE_G004
5  PF_P4D_POS_SIDE_G001
6  PF_P4D_NEG_CHAIR_G001
7  PF_P4D_POS_CURLED_G003
8  PF_P4D_POS_INTENTIONAL_G001
9  PF_P4D_POS_MULTI_G002
10 PF_P4D_POS_CORRIDOR_G001
11 PF_P4D_HN_PLANK_G001
12 PF_P4D_HN_CRAWL_G001
13 PF_P4D_HN_MAINT_G001
14 PF_P4D_HN_SQUAT_G005
```

## 实验判断

调度的 deterministic 规则是：先按原始 group ordinal 完成所有 partial group；之后只选择完整 outstanding group，每次按照 `(role deficit + taxonomy deficit + planned_split deficit)`、最大单项 deficit、各项 deficit 的稳定排序，再以 `original_group_ordinal`、`group_id` 做 tie-break。group 内按 manifest ordinal。`selection_reason` 会将 partial/confirmed-429 或具体 deficit 分数写入每行，便于复算。

该顺序改变的是 provider 请求时间序列，不是数据语义。它没有查看生成图像视觉质量、C3 结果或模型错误，也没有把当前 inventory 的成功类别写回 GT。原始 frozen manifest 的 group、role、taxonomy 和 planned split 仍是唯一语义来源。

## 风险与限制

- 68 行是已注册的首窗口计划，不是已经发生的 68 次请求；当前实际 logical invocations、physical attempts 和 retry events 均为 0。
- deficit-balanced 只解决当前已知的执行顺序偏差；它不能保证 provider quota、生成质量或后续模型性能。
- 第一个 slot 同时是历史 429 的恢复候选和 quota capability probe；若再次 429，必须停止而不能跳到第二个 slot。
- 计划仍受独立窗口上限 68/70、physical guard=80、retry-event guard=5 和 provider error hard-stop 约束；不得在不同窗口之间自动续跑。

## 下一阶段建议

达到时间 gate 且获得 standalone campaign authorization 后，手动启动新 window，并在执行前重新读取本计划 SHA。不得重排、追加 smoke prompt 或按视觉/模型错误选样。执行后必须把实际 ledger 与该计划逐行比对；若计划、manifest 或 profile/config hash 发生变化，应创建新的 revision，而不是覆盖本窗口。

计划工件：[adaptive_execution_order.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/02_order/adaptive_execution_order.csv)、[first_window_68_plan.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/02_order/first_window_68_plan.csv)、[adaptive_order_summary.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/02_order/adaptive_order_summary.json)。

