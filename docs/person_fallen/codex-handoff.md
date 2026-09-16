# `person_fallen` Codex 工程交接文档

> 单事件文档。当前事件：园区巡逻人员倒地检测。本文只记录 `person_fallen`，不代表真实摄像头、机器人或生产准确率。
>
> 最后更新：2026-09-16（Asia/Shanghai）

## 1. 当前终态速查

```text
CURRENT_EVENT=person_fallen
CURRENT_WINNER=NONE
CURRENT_WINNER_STAGE=N/A
NEXT_CANDIDATE=V7-B0R1-STRICT-MATCH-FALLBACK
NEXT_CANDIDATE_STATUS=PLANNED_NOT_RUN
CURRENT_STAGE=V7-B0_CLOSED_PROTOCOL_AND_FUSION_DEFECT
FINAL_STATUS=V7_B0_STATUS_CLOSED_PROTOCOL_AND_FUSION_DEFECT
PRODUCTION_INTEGRATION_READY=false
CODE_COMMITTED=false
HOLDOUT_CONSUMED=false
REAL_CAMERA_VALIDATED=false
VIDEO_VALIDATED=false
ROBOT_REOBSERVATION_VALIDATED=false
```

V7-B0 原冻结候选已关闭。58 requests、57 parsed completed 以及 `V7_B0_pilot_0049_P2_scene` 的严格 JSON 失败均属于原 `V7-B0-HARD-VETO-CROSSVIEW`，不是 V7-B0R1。原 B0 partial output 已出现 `floor_sitting` 的 `ATTENTION_NEAR_GROUND > 0`，因此即使修复 JSON，也不能继续作为原冻结候选验收。`V7-B0R1-STRICT-MATCH-FALLBACK` 仅为下一 successor 方案，尚未执行；其 Pilot、Known Regression、Full DEV、VAL、Holdout 和生产集成均未运行。

## 2. 业务定义

这是园区巡逻事件，不是观察“站立到摔倒过程”的动作识别。目标是在巡逻单帧或短时复观察中发现已经明显由道路、地面、车间地坪等非休息地面承托的人。

高优先级倒地应以人物属性和支撑关系共同确定：

```text
supine / side_lying / prone / curled_lying
+ support_surface=floor
+ torso_orientation=horizontal
+ torso_ground_contact=broad
+ body_support_configuration=torso_ground_supported
```

正常或非高优先级包括：

```text
floor_sitting、kneeling、squat、bending、standing、walking
bed/sofa/chair resting
明确由手、前臂、膝、脚主动支撑的 push-up、plank、crawling
```

不得为了通过评测而把 crawling、push-up/plank 或其他主动支撑姿态改成倒地正类。蜷缩只有在躯干确实由地面大面积承托时才是倒地。

## 3. V7-B0 历史终态

基线仓库与提交：

```text
repository=https://github.com/BarristerStuff/person_fallen.git
baseline_branch=v7-b0-hard-veto-crossview
baseline_commit=c0f39998474dd17586481bdacb289d1823af1940
V7_B0_STATUS=CLOSED_PROTOCOL_AND_FUSION_DEFECT
STRICT_JSON_FAILURE=true
PARTIAL_SEMANTIC_GATE_ALREADY_FAILED=true
```

关闭原因：一是 B0 Pilot 的 `V7_B0_pilot_0049_P2_scene` 返回 `done_reason=length`、`eval_count=512`，产生未闭合 JSON；二是已完成 floor-sitting 行出现 `ATTENTION_NEAR_GROUND`，违反 floor gate 的 `ATTENTION=0`。B0 的所有 artifact 只读保留，不得恢复或覆盖。

## 4. V7-B0R1 successor 状态

```text
V7_B0R1_STATUS=PLANNED_NOT_RUN
B0R1_FREEZE=NOT_CREATED
B0R1_OLLAMA_REQUESTS=0
B0R1_PILOT=NOT_RUN
B0R1_REGRESSION=NOT_RUN
B0R1_FULL_DEV=NOT_RUN
```

原 handoff 曾将 B0 的 58 requests、57 parsed completed 和严格 JSON 失败错误归入 V7-B0R1；现已纠正为原 `V7-B0-HARD-VETO-CROSSVIEW`。不得将 B0 的 request、raw response、ledger、partial output 或报告改名、迁移或包装为 B0R1。B0R1 的后续计划仅为：

1. strict schema 删除 evidence；
2. P1/P2 使用严格 enum；
3. 修正 P2↔detector association；
4. P2 不允许产生 ATTENTION；
5. 使用历史 B0 前 48 行做 zero-request replay；
6. `floor-sitting ALERT=0 AND ATTENTION=0` 才允许创建 freeze；
7. 然后才能执行 Clean Pilot 156。

以上计划在本阶段未执行。

## 5. B0 历史实现与缺陷记录

V7-B0 曾实现并冻结以下方向，但未通过正式验收：

- P1/P2 schema 删除 `evidence`，并设置 `additionalProperties=false` 与严格 enum；
- P2 bbox 转换到 0–1000 坐标并进行一对一关联；
- `GEOM_UPRIGHT` hard veto，P2 不得覆盖为 ALERT/RECHECK/ATTENTION；
- P2 作为漏检人员 fallback，不再产生 `ATTENTION_NEAR_GROUND`；
- prone 需要跨视图确认。

这些是 V7-B0 的历史代码/设计事实，不是 B0R1 的执行结果，也不等同于模型效果验收。原 B0 Pilot 在 `V7_B0_pilot_0049_P2_scene` 发生 `done_reason=length`、`eval_count=512`、`num_predict=512` 的严格 JSON 失败；同时已完成的 floor-sitting partial output 出现 `ATTENTION_NEAR_GROUND > 0`，故 B0 状态为 `CLOSED_PROTOCOL_AND_FUSION_DEFECT`。

## 6. 既往候选关键结论

### V6-A0

```text
Pilot=156
strict_json=156/156
source_binding=156/156
ground_lying ALERT=59/60，ALERT+RECHECK=60/60
floor_sitting ALERT=5/55
crawling ALERT=1/15
multi_person_one_lying ALERT=4/5
FINAL_STATUS=V6_A0_PILOT_FAIL
```

V6 的 `body_support_configuration` 没有形成可验收候选。V6 后续恢复阶段均不得被写成成功。

### V5-B0

完整 DEV 436 结果为：

```text
ground_lying ALERT=145/145
normal_negative ALERT=0/230，RECHECK=8/230
floor_sitting ALERT=0/55，RECHECK=5/55
auxiliary ALERT=3/41
```

因 auxiliary ALERT（其中 push-up/plank 和 crawling 有误报）被拒绝。

### V4-A0

唯一 SCREEN 失败 `PFV4_SCREEN_0066` 为多人物场景：一人跪着，另一人躺在地面；旧结构化输出只保留主要跪着人物，最终为 `NO_ALERT_NORMAL_POSE`。这证明多人物枚举、检测关联和场景聚合是系统风险，但不代表当前候选已修复。

## 7. 数据、验证和安全边界

```text
GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT
MODEL_PREDICTION_USED_AS_GT=false
OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED
HOLDOUT_CONSUMED=false
```

历史 VAL=100 已被 P1R recovery 消费，不能称为 pristine independent validation。不得运行旧 VAL 或读取其图像、预测、evidence；不得访问 Holdout；不得修改 GT、taxonomy、生成提示词、历史 freeze、历史 raw response 或共享数据集。

所有模型请求必须直接访问：

```text
http://192.168.20.62:11434
MODEL=qwen3.5:4b
```

正式请求前需 GET `/api/tags` 确认模型存在并记录 `/api/version`、`/api/ps`。禁止 SSH tunnel、`127.0.0.1:11444`、备用模型、代理、固定 GPU、`CUDA_VISIBLE_DEVICES` 或修改服务器。

## 8. 当前判断与下一步

已确认事实：V7-B0 已消费 58 requests，其中 57 parsed completed；`V7_B0_pilot_0049_P2_scene` 发生严格 JSON 协议失败，且 partial floor-sitting output 已出现 `ATTENTION_NEAR_GROUND > 0`，因此 B0 关闭。V7-B0R1 当前仅为 successor 计划，未执行、未创建 freeze、请求数为 0。

合理推理：不能在同一已消费候选上修 runner 后续跑。若继续，必须先由新窗口完成只读取证，确认 `27_*` 中真实请求、freeze、ledger、raw 的归属，再建立新的、明确标记为 protocol-recovery 的候选；不得把它称为 V7-B0R1 已通过。任何 successor 都应先解决：严格 envelope 校验（`done=true` 且 `done_reason != length`）、真实全局一对一匹配、完整 zero-request association replay、完整 fake E2E、阶段白名单、不可绕过的 Pilot→Regression→Full 依赖和精确 request ledger。

风险：继续在 synthetic DEV 上优化可能不能代表真实园区摄像头；VLM 单帧路线对远距离、遮挡、多人和主动支撑姿态仍有结构性误报/漏检风险。提交代码不等于验收通过。若没有新的明确授权，保持 `CURRENT_WINNER=NONE`，不运行 V7 后续阶段，不访问 VAL/Holdout，不做生产集成。

## 9. 关键路径索引

```text
事件 handoff=/home/yanbo/net_vlm_yanboversion/docs/person_fallen/codex-handoff.md
优化根=/home/yanbo/net_vlm_person_fallen_v2_optimization
V7-B0=/home/yanbo/net_vlm_person_fallen_v2_optimization/26_person_fallen_v7_b0_hard_veto_crossview
V7-B0R1=/home/yanbo/net_vlm_person_fallen_v2_optimization/27_person_fallen_v7_b0r1_strict_match_fallback
V6-A0=/home/yanbo/net_vlm_person_fallen_v2_optimization/24_person_fallen_v6_a0_direct_evaluation
生产仓库=/home/yanbo/net_vlm_yanboversion/vlm
```

生产仓库当前可能有其他未提交修改；不得直接在 dirty main 上提交，不得使用 `git add .`、`git add -A`、`git commit -a`、reset、clean、restore 或覆盖既有修改。只有候选通过相应开发门禁并获得明确授权后，才可创建隔离 worktree 做生产集成。当前代码未提交，生产集成未开始。

## 10. V7-B0R1 CLEAN_R1 workspace correction（2026-09-16）

```text
V7_B0R1_CONTAMINATED_WORKSPACE=ABANDONED
V7_B0R1_CONTAMINATED_FORMAL_REQUESTS=0
V7_B0R1_FORMAL_WORKSPACE=/home/yanbo/net_vlm_person_fallen_v2_optimization/28_person_fallen_v7_b0r1_strict_match_fallback_clean
WORKSPACE_GENERATION=CLEAN_R1
V7_B0R1_STATUS=ASSOCIATION_PREFLIGHT_FAIL
B0R1_FREEZE=NOT_CREATED
B0R1_OLLAMA_REQUESTS=0
```

污染的 `27_*` 工作区已原样保留并标记 `CONTAMINATED_DO_NOT_USE.md`，未作为正式 lineage 复用。Clean workspace 的 geometry binding 通过；B0 历史 48 行 floor-sitting zero-request replay 为 NO_ALERT=48、RECHECK=0、ALERT=0、ATTENTION=0。association preflight 因这 48 行仅含 floor-sitting，缺少 multi-person-one-lying 与 PFV4_SCREEN_0066 可验证 diagnostic，无法同时证明要求的匹配/漏检行为，故在 freeze 和首个模型请求前停止。

## 11. V7-B0R1 CLEAN_R1 association evidence completion and test stop（2026-09-16）

```text
V7_B0R1_STATUS=TEST_FAIL_BEFORE_FREEZE
FINAL_STATUS=B0R1_TEST_FAIL
V7_B0R1_FORMAL_WORKSPACE=/home/yanbo/net_vlm_person_fallen_v2_optimization/28_person_fallen_v7_b0r1_strict_match_fallback_clean
WORKSPACE_GENERATION=CLEAN_R1

WORKSPACE_PROVENANCE=PASS
GEOMETRY_BINDING=PASS
MULTI_PERSON_ASSOCIATION_PREFLIGHT=PASS
PFV4_SCREEN_0066_OFFLINE_ASSOCIATION=PASS
B0_OFFLINE_REPLAY=PASS

ASSOCIATION_MULTI_CANDIDATES=5
ASSOCIATION_MULTI_VALID=1
PFV4_SCREEN_0066_MEASURABLE=true
WRONG_LYING_ATTACHMENT_TO_GEOM_UPRIGHT=0

TEST_FAILURE=unmatched floor_sitting expected NO_EFFECT but frozen policy returned RECHECK_VISUAL_UNCERTAIN
POLICY_MODIFIED=false
B0R1_FREEZE=NOT_CREATED
B0R1_OLLAMA_REQUESTS=0
B0R1_PILOT=NOT_RUN
B0R1_REGRESSION=NOT_RUN
B0R1_FULL_DEV=NOT_RUN
CURRENT_WINNER=NONE
READY_FOR_FINAL_HOLDOUT=false
HOLDOUT_CONSUMED=false
```

此终态是 freeze 前 policy contract 测试失败，不是 matcher association 失败，也不是模型指标失败。任务禁止修改 policy，因此未创建 freeze、未发送 Ollama 请求。

## 2026-09-16 V7-B0R1 pre-freeze policy contract correction

- candidate: `V7-B0R1-STRICT-MATCH-FALLBACK`
- branch: `v7-b0r1-clean`
- formal workspace: `/home/yanbo/net_vlm_person_fallen_v2_optimization/28_person_fallen_v7_b0r1_strict_match_fallback_clean`
- policy correction occurred before candidate freeze: `true`
- formal requests before correction: `0`
- correction scope: deterministic P2 `NO_EFFECT` precedence for explicit non-lying poses and limb-supported configurations only
- association matcher/thresholds, geometry, prompts, schemas, manifests, GT, crops, model and options changed: `false`
- pre-freeze rerun: workspace provenance PASS; geometry binding PASS; multi-person association PASS; PFV4_SCREEN_0066 offline association PASS; B0 48-row replay PASS with floor ALERT=0 and ATTENTION=0; strict schema PASS; full tests PASS; fake E2E PASS; crop QA PASS
- candidate freeze created only after all checks and while formal Ollama request count remained `0`
- freeze SHA-256: `b4591557c0ce7b1580fe1f5500ee636318a18d72fec88c2def9df2a4c8ebca44`

## 2026-09-16 V7-B0R1 formal execution blocked before first request

- status: `BLOCKED_B0R1_SOURCE_ASSET_MISSING`
- this is not a model-metric failure
- freeze SHA-256: `b4591557c0ce7b1580fe1f5500ee636318a18d72fec88c2def9df2a4c8ebca44`
- Ollama endpoint/model/digest preflight: `PASS`
- Pilot completed rows: `0`
- B0R1 formal Ollama requests: `0`
- source binding failed before the first request because 380/437 unique manifest `image_path` assets are absent; exact-sha historical candidates were found for 70, while 310 remain unresolved
- frozen runner, manifests, association matcher, prompts, schemas, geometry, GT and crop preprocessing were not modified
- no symlink/copy/reconstruction, resend, retry, Regression, Full DEV, VAL, or Holdout execution occurred
- required next action: restore all missing source assets at their frozen paths with exact manifest SHA-256, then obtain explicit resume authorization because the current clean-execution runner created the Pilot phase directory during the failed pre-request attempt

## 2026-09-16 V7-B0R1 source recovery and frozen Pilot stop

- source asset recovery: `PASS` (`380/380` missing exact-SHA assets restored by byte-identical atomic copy; final source binding `437/437`; restored images were not added to Git)
- Pilot pre-request directory recovery: `REMOVED_EMPTY_PRE_REQUEST_DIRECTORY`
- freeze unchanged: `true`; SHA-256 remains `b4591557c0ce7b1580fe1f5500ee636318a18d72fec88c2def9df2a4c8ebca44`
- Ollama endpoint/model/digest preflight: `PASS`
- formal Pilot execution produced 4 completed P2 requests and 4 completed floor-sitting rows, all strict-JSON/source-bound and all `NO_ALERT_NORMAL_POSE`
- execution then stopped at Pilot row 5 before claiming its next request: frozen crop QA/lookup contains no valid `(item_id, person_idx)` binding for required background person `0` of `P4D_PLAN::PF_P4D_HN_SIT_G001_V05`
- status: `BLOCKED_B0R1_FROZEN_CROP_PLAN_INCOMPLETE`
- this is a frozen execution-input defect, not a model metric failure; no retry/resend, runner/manifest/freeze modification, Regression, Full DEV, VAL, or Holdout occurred
- B0R1 formal request count: `4`
