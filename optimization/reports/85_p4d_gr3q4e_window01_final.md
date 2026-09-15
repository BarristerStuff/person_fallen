# P4D GR3Q4E Window 01 final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR3Q4E_NAME=P4D_GR3Q4E_ADAPTIVE_QUOTA_CAMPAIGN_WINDOW_01
P4D_GR3Q4E_REVISION=P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01
P4D_GR3Q4E_STATUS=AWAITING_CAMPAIGN_AUTHORIZATION
PROVIDER_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
STOP_REASON=EXPLICIT_CAMPAIGN_AUTHORIZATION_MISSING
PARENT_GR3Q4_FREEZE_VERIFIED=true
FROZEN_440_VERIFIED=true
CURRENT_PROFILE_FINGERPRINT=ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe
ACTIVE_PROFILE_STRATUM=PROFILE_A_RESTORED
WINDOW_LOGICAL_CAP=68
PHYSICAL_ATTEMPT_CAP=80
RETRY_EVENT_CAP=5
LOGICAL_INVOCATIONS=0
SUCCESS=0
FAILURE=0
NEW_RAW_COUNT=0
NEW_FINAL_COUNT=0
CURRENT_TOTAL_VERIFIED_SUCCESS=102
CURRENT_OUTSTANDING=338
FULL_440_QA=NOT_REACHED
FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
DATASET_VALIDATOR_STATUS=valid
PRODUCTION_CODE_MODIFIED=false
OLLAMA_MODIFIED=false
```

## 已确认事实

本次是新的独立 Window 01 execution revision，但按硬 authorization rule 在零请求状态封存。parent GR3Q4 freeze SHA `8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2`、Q2E `9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44`、GR3Q3 `7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697`、frozen 440 manifest `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4` 均核验通过。起始 102 张由实际文件重建并通过完整性验证，338 outstanding 精确为 1 confirmed HTTP 429、337 NEVER_STARTED、0 COMPLETION_UNKNOWN。

provider/runtime 为 codex / gpt-5.4 / image_generation / 0.7.3，当前 profile 为 `PROFILE_A_RESTORED`；预注册 native 1536x1024、medium、PNG、controlled 16:9 crop + Pillow LANCZOS 到 1920x1080，material config match=True。

## 实验判断

任务正文自身明确不是授权。本轮顶层用户消息没有另外给出“保留 102、处理 338、Window 01 上限 68、后续手动窗口、并接受 retry/quota/cost 风险且不做 ingest/C3/VAL/HOLDOUT”的等价授权，故 `P4D_GR3Q4E_STATUS=AWAITING_CAMPAIGN_AUTHORIZATION` 是唯一合规状态。没有分类或图像生成 baseline；所有新增 generation/latency/cost/quality 指标为 N/A。

## 风险与限制

本轮没有调用 EBOND endpoint、没有访问 HOLDOUT、没有 formal ingest、没有修改 shared split CSV 或 production code；Codex-only capability audit 的 configured-provider 字段已脱敏，未持久化或读取 EBOND credential secret。空日志和 0 attempts 不代表 provider 配额可用。未来即使获得授权，也必须新建 revision，先重新绑定当前 parent/hash/profile/config，再人工按冻结 68-slot order 执行。

## 下一阶段建议

请在新的独立顶层消息明确授权该窗口；授权前不要启动任何 provider 请求。授权后不得复用本零请求 ledger 作为已执行结果，需新建独立 execution revision。

## 关键本地工件

- starting inventory: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_01_execution_20260830_01/01_inventory/current_verified_success_inventory.csv` (SHA `537416bdc8b6aa355d4dfccf910db4d892631be3e506bac87ad5b1f1f7fd23cb`)
- outstanding: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_01_execution_20260830_01/01_inventory/outstanding_338.csv` (SHA `22334fa342e5cfdf51e6e1dc92b26adbc690f1fff7a6521d1642cd5aed4f6e83`)
- SQLite stable ledger: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_01_execution_20260830_01/03_ledger/window_01_execution.sqlite3` (SHA `8d720f285f0a634146795635ab04e6951881cb3d2a8677d5abd5de5d923b8b25`)
- CSV ledger: `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_01_execution_20260830_01/03_ledger/window_01_ledger.csv` (SHA `404bcad2dd6a7ec359ec9847a6dde531ffdc5d4f9cad33d4d307ab0474ac5b2d`)
- runner SHA: `8572fb9c0750157b2113ae8f258334778fe9aebe395375aac42227e9471c524d`
