# P4D GR3Q3 current 102-success inventory

```text
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
CURRENT_SUCCESS=102
PROFILE_A_SUCCESS=99
PROFILE_B_SUCCESS=3
INVENTORY_ISSUES=0
GR1_IMAGES_REUSED=0
GR1_SHA_HITS=0
GR1_SAMEFILE_HITS=0
GR1_SYMLINK_HITS=0
```

## 已确认事实

库存不是从 Q2E summary 直接复制，而是按 frozen 440 manifest 重新关联 GR3E inventory/ledger、Q2E ledger/raw evidence 和 batch 中实际 raw/final 文件后建立。全部 102 个 prompt ID 唯一，所有 raw/final 文件的 SHA 与 ledger 一致，Pillow `verify()` 后重新打开并 `load()` 通过，final 尺寸均为 `1920x1080`，无 current raw/final same-file、无 symlink。

来源分层：

| 来源 | provenance stratum | 已验证成功 |
|---|---:|---:|
| GR3E authorized revision | `GR3E_PROFILE_A` | 99 |
| GR3Q2E recovery revision | `GR3Q2_PROFILE_B` | 3 |
| 合计 | — | 102 |

102 张全部属于本 hard-negative revision；当前已验证库存的 role 计数为 `hard_negative=102`，计划 split 为 `NEW_DESIGN=70`、`NEW_SCREEN=32`，taxonomy 为 `floor_sitting=60`、`kneeling_half_kneeling=42`。

当前库存 CSV SHA-256：

```text
c77d57e33da99add3744c03c9bfb5344b3b81d5c3b5a59a1481443ea6078831b
```

文件：[current_success_inventory_gr3q3.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/02_inventory/current_success_inventory_gr3q3.csv)

GR1 排除审计读取了 [gr1_independent_mechanical_qa.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/03_intake_audit/gr1_independent_mechanical_qa.csv)：该 QA 表有 440 个 slot 行，其中 192 个历史文件对为 PASS、248 个为未生成/FAIL。当前 102 对新 revision raw/final 与历史 GR1 hash、samefile 和 symlink 均无命中；没有复制任何 GR1 文件。审计结果：[gr1_exclusion_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/02_inventory/gr1_exclusion_audit.json)。

冻结 440 prompt manifest 重新核验结果：SHA-256 `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`，440 rows、440 unique prompt IDs、88 groups、prompt byte mismatch=0、cross-split group=0；role 为 hard_negative 300、positive 100、ordinary_negative 40，NEW_DESIGN 265、NEW_SCREEN 175。[full_manifest_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/00_preflight/full_manifest_audit.json)

## 实验判断

102 是当前可被完整性证据支持的 success inventory，不是 440 张已完成的生成结果，也不是 semantic acceptance。由于尚未达到全量 440 QA、人审、正式 ingest 或 C3，`P4D_VALIDATED_GENERATION_BASELINE=false` 保持不变。

## 风险与限制

历史 Profile-A 与 Q2E Profile-B 的成功文件只证明客户端可见的文件和配置条件；它们不证明 opaque provider 内部没有账户路由差异。新 quota window 的当前只读 Codex profile 指纹与 Profile-A 相同，这一 provenance 变化/回切必须在未来真实执行日志中重新绑定，不能事后用 profile 名称替代证据。

