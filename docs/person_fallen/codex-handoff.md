# `person_fallen` Codex 工程交接文档

> 单事件文档。当前事件：园区巡逻人员倒地检测。本文只记录 `person_fallen`，不代表真实摄像头、机器人或生产准确率。
>
> 最后更新：2026-09-15（Asia/Shanghai）

## 1. 当前终态速查

```text
CURRENT_EVENT=person_fallen
CURRENT_WINNER=NONE
CURRENT_WINNER_STAGE=N/A
CURRENT_STAGE=V6-A0_PILOT_FAIL
FINAL_STATUS=V6_A0_PILOT_FAIL
PRODUCTION_INTEGRATION_READY=false
CODE_COMMITTED=false
HOLDOUT_CONSUMED=false
REAL_CAMERA_VALIDATED=false
VIDEO_VALIDATED=false
ROBOT_REOBSERVATION_VALIDATED=false
```

V6-A0 已经真实执行了 Pilot 156 条请求，但 Pilot 门禁失败。按协议没有运行已知错误回归、Full DEV、VAL、Holdout、生产集成或 Git 提交。当前不能把 V5-B0 或 V6-A0 称为 Winner，也不能据此提交为生产可用检测器。

## 2. 业务定义

这是园区巡逻事件，不是“观察站立到摔倒过程”的动作识别。目标是在巡逻单帧或短时复观察中识别已经明显由道路、地面、车间地坪等非休息地面承托的人。

高优先级倒地：

```text
supine / side_lying / prone / curled_lying / other_near_ground
+ support_surface=floor
+ torso_orientation=horizontal
+ torso_ground_contact=broad
+ body_support_configuration=torso_ground_supported
```

正常或非高优先级：

```text
floor_sitting、kneeling、squat、bending、standing、walking
bed/sofa/chair resting
明确由手、前臂、膝、脚主动支撑的 push-up、plank、crawling
```

`push-up/plank/crawling` 不应为了通过评测而改成倒地正样本；它们可以是 `ATTENTION_NEAR_GROUND`，但不能直接成为 `ALERT_GROUND_LYING`。蜷缩只有在躯干确实由地面大面积承托时才是倒地。

## 3. 当前最新 V6-A0 结果

候选：

```text
CANDIDATE=V6-A0-TARGET-SUPPORT-CONFIG
EXECUTION_DIR=/home/yanbo/net_vlm_person_fallen_v2_optimization/24_person_fallen_v6_a0_direct_evaluation
FREEZE_SHA256=aef2926c3b0b9232ab91bb1d9b2375a594fec991e7dd8216649cc14435ecac89
```

语义变化是增加人物级 `body_support_configuration`，用于区分躯干贴地和手、前臂、膝、脚支撑。V6 语义文件来自并保持不变：

```text
/home/yanbo/net_vlm_person_fallen_v2_optimization/20_person_fallen_v6_target_support_config/prompt/target_support_attributes.txt
/home/yanbo/net_vlm_person_fallen_v2_optimization/20_person_fallen_v6_target_support_config/schema/target_attributes.json
/home/yanbo/net_vlm_person_fallen_v2_optimization/20_person_fallen_v6_target_support_config/policy/target_policy.py
/home/yanbo/net_vlm_person_fallen_v2_optimization/20_person_fallen_v6_target_support_config/definition/person_fallen_v4_operational_definition.md
```

执行前：4 项离线测试、fake 437 请求控制流、freeze 只读校验和 Ollama preflight 均通过。Ollama 使用固定直连：

```text
OLLAMA_BASE_URL=http://192.168.20.62:11434
MODEL=qwen3.5:4b
MODEL_DIGEST=2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
OLLAMA_VERSION=0.23.2
concurrency=1
think=false
stream=false
temperature=0
num_ctx=8192
num_predict=768
automatic_retry=false
```

实际 Pilot：

```text
rows=156
requests_claimed=156
requests_completed=156
requests_unknown=0
failure=0
strict_json=156/156
source_binding=156/156
```

业务结果：

```text
ground_lying:       ALERT=59/60，ALERT+RECHECK=60/60
floor_sitting:      ALERT=5/55，RECHECK=5/55，NO_ALERT=45/55
pushup_plank:       ALERT=0/26
crawling:           ALERT=1/15
multi_person_one_lying: ALERT=4/5
```

门禁失败项：

```text
floor_sitting ALERT=5，要求=0
crawling ALERT=1，要求=0
multi_person_one_lying ALERT=4/5，要求=5/5
```

这是模型/语义表现失败，不是网络、JSON、请求账本或执行器失败。报告：

```text
/home/yanbo/net_vlm_person_fallen_v2_optimization/24_person_fallen_v6_a0_direct_evaluation/reports/final_report.json
/home/yanbo/net_vlm_person_fallen_v2_optimization/24_person_fallen_v6_a0_direct_evaluation/reports/independent_audit.json
```

## 4. 历史候选与关键结论

### V5-B0-TARGET-ATTRIBUTES

完整 DEV 436 已形成，结果：

```text
ground_lying ALERT=145/145
normal_negative ALERT=0/230，RECHECK=8/230
floor_sitting ALERT=0/55，RECHECK=5/55
auxiliary_attention ALERT=3/41
  pushup/plank ALERT=2
  crawling ALERT=1
visual_uncertain ALERT=5/20（单独报告）
```

因此 V5-B0 因 auxiliary ALERT=3/41 被拒绝。报告：

```text
/home/yanbo/net_vlm_person_fallen_v2_optimization/23_person_fallen_v5_b0_remaining47_diagnostic/reports/final_report.json
/home/yanbo/net_vlm_person_fallen_v2_optimization/23_person_fallen_v5_b0_remaining47_diagnostic/reports/independent_audit.json
```

### V5-A0 与 REV15

V5-A0 的 scene-review 旁路造成正常负例过多 RECHECK，不能作为当前方案。REV15 虽然试图增加场景级 `any_person_ground_lying_on_nonrest_surface`，但完整 DEV 出现明显 ground recall 下降和负例误报，已关闭。不要复用旧报告中错误的分层或召回结论。

### V4-A0

V4 的唯一 SCREEN 失败是 `PFV4_SCREEN_0066`：场景中有跪着的人和另一名躺地的人，旧结构化输出只保留跪着人物，最终 NO_ALERT。V4 的问题说明多人物枚举/聚合是重要风险，但它不是当前 Winner。

Regression item：

```text
operational_id=PFV4_SCREEN_0066
item_id=P4D_PLAN::PF_P4D_POS_CURLED_G003_V05
```

V6-A0 Pilot 失败后，本次没有运行这个回归。

### V6 执行恢复历史

`20_*` 首次 freeze 因预算接口不一致而在请求前阻塞；`21_*` R1 因 fake 覆盖不足、Pilot 与 Full Remaining 聚合缺失、early-stop 未执行、阶段依赖可绕过等问题阻塞；`22_*` R2 又发现 freeze 没有直接绑定真实消费的 manifest，且 completion lock 未覆盖完整证据链。上述阶段真实模型请求均为 0，不得当作 V6 模型失败；真正的模型失败是 `24_*` 的 Pilot。

## 5. 数据、验证和安全边界

```text
GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT
HUMAN_SEMANTIC_REVIEW_REQUIRED_FOR_SYNTHETIC_DEVELOPMENT=false
MODEL_PREDICTION_USED_AS_GT=false
OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED
```

历史 VAL=100 已被 P1R recovery 消费，存在 media/image SHA 重合，不能称为 pristine independent validation。当前不得运行旧 VAL 或读取其图像、预测、evidence。Holdout 状态仍为：

```text
HOLDOUT_CONSUMED=false
HOLDOUT_REQUESTS=0
```

不得访问 Holdout，不得修改 GT、taxonomy、生成提示词、历史 freeze、历史 raw response 或共享数据集。

所有模型请求必须直接访问 `http://192.168.20.62:11434`，禁止 SSH tunnel、`127.0.0.1:11444`、备用模型、CUDA 固定 GPU 或服务器配置修改。

## 6. 当前判断与后续路线

已确认 V6 的 `body_support_configuration` 对 push-up/plank 有局部收益（0/26 ALERT），但没有形成可验收候选：坐地新增 5 个误报，爬行仍有误报，多人物倒地仍漏 1/5。继续仅靠扩充单帧 Prompt/schema 字段的收益存疑。

最合理的下一方向不是把辅助动作改成倒地正样本，而是架构路线：

```text
YOLO person localization
→ pose/keypoint 或人体几何/支撑特征
→ VLM 只复核遮挡、多人物、属性冲突样本
→ 巡逻短时复观察确认
```

建议生产决策逻辑：

```text
明确躯干贴地且非主动支撑 → ALERT
明确坐地/跪地/俯卧撑/爬行 → NO_ALERT 或 ATTENTION
遮挡、多人物或属性冲突 → RECHECK
短时连续观察仍满足倒地 → 升级 ALERT
```

如果只是为了尽快提交代码，可以提交默认关闭的事件框架，但不能宣称检测通过：

```text
PERSON_FALLEN_ENABLED=false
CURRENT_WINNER=NONE
PRODUCTION_INTEGRATION_READY=false
```

如果要继续研发，只允许在明确授权后建立新的、架构有实质变化的 V7 方案；不得自动创建 V6-A1、V7 Prompt 微调候选、放宽门禁、把 crawling/push-up/plank 改成倒地正类，或继续运行 V6 Full DEV。

## 7. 生产 Git 边界

生产仓库：

```text
/home/yanbo/net_vlm_yanboversion/vlm
```

当前 worktree 有用户/其他任务的未提交修改。禁止直接在该 worktree 提交，禁止 `git add .`、`git add -A`、`git commit -a`、reset、clean、restore 或覆盖既有修改。只有在获得明确授权且候选通过相应开发门禁后，才可从实际 HEAD 创建隔离 worktree，例如：

```text
/home/yanbo/net_vlm_person_fallen_v6_integration
feature/person-fallen-v6
```

提交不等于真实验收；提交后仍需保持 `REAL_CAMERA_VALIDATED=false`、`ROBOT_REOBSERVATION_VALIDATED=false`，直到有独立现场证据。

## 8. 当前禁止重复的工作

```text
不重跑 V6-A0 Pilot
不运行 V6 Known Regression、Full Remaining、Full DEV、VAL、Holdout
不修改 V6-A0 语义文件
不把 V5/V6 失败改写为成功
不把 synthetic DEV 当真实相机准确率
不创建 V6-A1 或纯 Prompt 搜索候选
不修改其他事件 handoff
```

## 9. 关键路径索引

```text
事件 handoff:
/home/yanbo/net_vlm_yanboversion/docs/person_fallen/codex-handoff.md

优化根目录:
/home/yanbo/net_vlm_person_fallen_v2_optimization

V5-B0 完整诊断:
/home/yanbo/net_vlm_person_fallen_v2_optimization/23_person_fallen_v5_b0_remaining47_diagnostic

V6-A0 Pilot:
/home/yanbo/net_vlm_person_fallen_v2_optimization/24_person_fallen_v6_a0_direct_evaluation

V6-A0 语义候选:
/home/yanbo/net_vlm_person_fallen_v2_optimization/20_person_fallen_v6_target_support_config

生产仓库:
/home/yanbo/net_vlm_yanboversion/vlm
```

## V7-A1 Stage 2 重标定结果（2026-09-15）
- FINAL_STATUS: `STAGE2_A1_GEOMETRY_FAIL`
- A1 diagnosis found 48 missed ground-lying images, 36/41 auxiliary GEOM_LYING images, and no feasible tested threshold tuple satisfying revised G1 and G3 simultaneously.
- VLM requests: `0`; thresholds not frozen; no Stage 3+ execution.
- Next action: close V7-A1 candidate.
