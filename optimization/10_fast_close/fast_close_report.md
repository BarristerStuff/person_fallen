# person_fallen v2.0 fast-close handoff

STATUS=FAST_CLOSE_HUMAN_REVIEW_REQUIRED

## 独立判断

- IS_440_FULL_GENERATION_A_HARD_PROTOCOL_REQUIREMENT=true：冻结的 P4D 设计和后续报告明确把完整 440 槽位作为语义接受/C3 的前置条件。本次 fast-close 视图不绕过该门槛。
- STOP_FURTHER_P4D_GENERATION=true：Q10 已在 provider usage_limit_reached 后终止；本次没有 provider 请求、Q10 重试、unknown 重发、207 条 outstanding 生成、formal ingest 或 Holdout 操作。
- clean_success=202 已按当前 terminal partition 精确重建；Q9 的 30 条 binding-blocked、1 条 completion_unknown 和 207 条 safe outstanding 均未进入视图。

## 可核实事实

| 项目 | 结果 |
|---|---:|
| 当前 verified partition | 232 |
| 排除 Q9 binding-blocked | 30 |
| fast-close clean manifest | 202 |
| completion_unknown | 1 |
| safe_executable_outstanding | 207 |
| accounting sum | 440 / 440 |
| full frozen group/split leakage | 0 |
| clean-view group/split leakage | 0 |
| internal exact-final duplicate groups | 0 |
| known historical exact-final collisions | 0 |
| near-duplicate pairs, dHash distance <=4 | 0 |
| Pillow/dimension failures | 0 |
| prompt SHA mismatches | 0 |
| raw/final SHA mismatches | 0 |
| legal human GT rows found | 0 |

Resolved stages: {"Q10_EXECUTION": 6, "Q2_PRE_Q6_LEGACY_INVENTORY": 132, "Q5_EXECUTION": 10, "Q6_EXECUTION": 9, "Q7_EXECUTION": 20, "Q8_EXECUTION": 25}.

Role counts: {"hard_negative": 132, "ordinary_negative": 20, "positive": 50}.

Split counts: {"NEW_DESIGN": 126, "NEW_SCREEN": 76}.

## provenance 风险

历史权威记录显示 132 条 inherited rows 是 LEGACY_NO_ADAPTER；当前后续 partition 的通用字段却写成了 CODEX_SAFE_STAGED_CV_V1。本审计把 current_partition_adapter_version 与 historical_adapter_version 分开保留，不把后者缺失或前者通用值升级成虚假的逐图 adapter 证据。Q5 的 10 条成功记录在 SQLite slots 表中有状态和路径，但没有预存 raw/final SHA，因此审计仅能报告“本次重新计算”，不能伪称已有独立 SHA 证据。

## GT 与算法评测

当前没有合法的显式人工 semantic GT。已生成最小 review 包，202 条全部保持 unreviewed。因此：

- B0/C3=NOT_RUN_HUMAN_GT_GATE
- R1/C3=NOT_RUN_HUMAN_GT_GATE
- NEW_SCREEN=NOT_RUN_HUMAN_GT_GATE
- READY_FOR_FINAL_HOLDOUT=false

不得用 prompt、planned role、Codex/VLM 输出或目录名补 GT。完成人工复核也不能自动解除 P4D 的完整 440 硬门槛；需要按冻结协议重新完成完整生成和正式 QA/review 后才可能进入 P4D C3/后续阶段。

## 证据入口

- clean manifest: /home/yanbo/net_vlm_person_fallen_v2_optimization/10_fast_close/fast_close_clean_manifest.csv
- data audit: /home/yanbo/net_vlm_person_fallen_v2_optimization/10_fast_close/fast_close_data_audit.json
- human review page: /home/yanbo/net_vlm_person_fallen_v2_optimization/10_fast_close/FAST_CLOSE_HUMAN_REVIEW/index.html
- human review instructions: /home/yanbo/net_vlm_person_fallen_v2_optimization/10_fast_close/FAST_CLOSE_HUMAN_REVIEW/review_instructions.md
- Q10 terminal freeze: /home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_07_gr3q10_authorized_20260901_01/freeze/p4d_gr3q10_execution_terminal_freeze.json (sha256=2c05bb62e8b4041fb5b62e9b0cc49265068fdb6a3c1975ad5b922da5656b80e8)
- Q10 final report: /home/yanbo/net_vlm_person_fallen_v2_optimization/reports/124_p4d_gr3q10_final.md
- P4D generation-required freeze: /home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/freeze/p4d_generation_required_freeze.json
- frozen full prompt manifest: /home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/03_fullregen_plan/full_regen_prompt_manifest.csv
- active dataset validator evidence: /home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_07_gr3q10_authorized_20260901_01/00_preflight/dataset_after.json

本次只新增 fast-close 审计/人工入口文件，没有写入 /home/yanbo/net_vlm_yanboversion/vlm，没有改写共享数据集，也没有改变历史冻结文件。
