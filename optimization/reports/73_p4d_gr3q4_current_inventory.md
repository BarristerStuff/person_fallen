# P4D GR3Q4 current inventory and gap audit

```text
P4D_GR3Q4_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
TOTAL_FROZEN=440
PROFILE_A_SUCCESS=99
PROFILE_B_SUCCESS=3
CURRENT_VERIFIED_SUCCESS=102
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0
OUTSTANDING=338
GR1_IMAGES_REUSED=0
PROVIDER_REQUESTS=0
```

## 已确认事实

本 inventory 不是对旧 summary 的转录，而是从 frozen 440 manifest、GR3E ledger、GR3Q2E ledger、历史 raw/final 文件和实际文件状态重新构建。当前成功库存 CSV 为 102 行、102 个唯一 prompt ID，SHA-256：

```text
c77d57e33da99add3744c03c9bfb5344b3b81d5c3b5a59a1481443ea6078831b
```

102 条全部是 hard-negative：`floor_sitting=60`、`kneeling_half_kneeling=42`；planned split 为 `NEW_DESIGN=70`、`NEW_SCREEN=32`。generation provenance 为 GR3E Profile-A=99、GR3Q2E Profile-B=3。对应 raw=102、final=102（共 204 个文件）均通过 SHA 对照、Pillow `verify()`/reopen/load、final dimension `1920x1080`、非 symlink、raw/final 非 samefile 检查。inventory issues 为空。

GR1 独立机械 QA 有 440 行，其中历史通过记录 192 行；当前 102 张与 GR1 的 SHA hit、samefile hit、symlink hit 均为 0，`GR1_IMAGES_REUSED=0`。这证明当前库存没有把 GR1 图像重新作为新 revision 输入。

未完成清单 CSV 为 338 行、338 个唯一 prompt ID，SHA-256：

```text
22334fa342e5cfdf51e6e1dc92b26adbc690f1fff7a6521d1642cd5aed4f6e83
```

它精确包含 1 个 `FAILED_CONFIRMED_HTTP_429`（`PF_P4D_HN_KNEEL_G009_V03`）和 337 个 `NEVER_STARTED`，没有 completion ambiguity。outstanding 角色分布为 hard_negative=198、positive=100、ordinary_negative=40；planned split 为 `NEW_DESIGN=195`、`NEW_SCREEN=143`。taxonomy 分布为：

```text
kneeling_half_kneeling=18
pushup_plank=50
crawling_quadruped_support=40
ground_maintenance=40
squat_crouch_deep_bend=30
mixed_hard_negative=20
supine_ground_lying=20
prone_ground_lying=20
side_lying=20
curled_or_partially_occluded_lying=15
intentional_ground_lying=10
multi_person_one_lying=10
horizontal_corridor_ground_lying=5
standing_walking=20
chair_seated_normal_work=20
```

冻结 manifest 仍为 440/440 rows、440 unique prompt IDs、88 groups、cross-split=0；角色 hard_negative=300、positive=100、ordinary_negative=40；planned split `NEW_DESIGN=265`、`NEW_SCREEN=175`。manifest SHA-256：

```text
5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
```

## 实验判断

`102+338=440` 且集合精确互补，因此当前缺口是可追踪的 generation gap，而不是重新 ingest、重新 GT 或重新 split 的理由。当前成功库存只覆盖两种 hard-negative taxonomy，是执行顺序造成的观测偏斜；GR3Q4 通过新的 group-aware order 处理该偏斜，但不会把历史成功类别当作标签分布修正。

历史 Profile-A/B 差异只作为 provenance stratum：当前只读 profile fingerprint 为 Profile-A，三张 Q2E 成功图像仍标记为 Profile-B。没有任何理由重写这 102 条成功记录或把 338 条 outstanding 标为已尝试。

## 风险与限制

- 102 张是 generation integrity evidence，不是 full 440 QA 通过，也不是 semantic approval 或分类 baseline。
- 338 条 `NEVER_STARTED` 仅表示当前父级 ledger 没有开始事件；它不等于 provider 已拒绝或已尝试。
- 唯一历史 429 来自 Q2E raw evidence，不能在本 revision 中转换为成功、删除或改写。
- 完整 440 QA、exact/near-duplicate QA、human semantic review、formal ingest、C3、NEW_VAL 和 HOLDOUT 都尚未到达；现阶段不能从图像内容推导 GT。

## 下一阶段建议

继续保留本 inventory 及其 SHA，不要改变 frozen manifest 或共享 split CSV。等待时间 gate 和 standalone campaign authorization 后，只允许按照已冻结的 adaptive order 逐窗口执行。每个窗口都应重新进行 profile/runtime/config gate，并在终态重新核对 102/338 或更新后的精确互补关系；只有 verified success 达到 440，才进入一次性的 full mechanical/duplicate/lineage QA 和后续人审门槛。

工件：[current_verified_success_inventory.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/01_inventory/current_verified_success_inventory.csv)、[outstanding_338.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/01_inventory/outstanding_338.csv)、[gr1_exclusion_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/01_inventory/gr1_exclusion_audit.json)。

