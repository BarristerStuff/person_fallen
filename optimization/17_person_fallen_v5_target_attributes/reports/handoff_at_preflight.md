# net_vlm `person_fallen` Codex 完整交接文档

## 最新授权开发终态：V5-A0-INDEPENDENT-RECHECK（2026-09-09）

> **当前状态以本节为准。** 下方原第 0–21 节为 V4-A0 operational SCREEN
> 停止时的历史交接基线，保留证据，但其中“当前阶段/后续授权”不覆盖本次已执行的
> V5 授权。所有历史候选均未发布，CURRENT_WINNER 仍为 NONE。

### 业务与数据政策

- 目标是园区巡逻中发现已经地面躺倒或异常塌落的人员，不要求拍到站立到倒下的过程。
- 沿用 V4 operational 定义；不推断摔倒原因、伤情、意识或危险程度。
- RECHECK 是待复核，不是已确认倒地；ALERT+RECHECK coverage 不是最终告警召回率。
- GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT；MODEL_PREDICTION_USED_AS_GT=false。
- HUMAN_SEMANTIC_REVIEW_REQUIRED_FOR_SYNTHETIC_DEVELOPMENT=false：人工逐图审核不是当前合成开发前置条件。
- 用户声明生成提示词与图像相符；机器核验 hash、行绑定与协议完整性，不宣称全量像素语义验证。

### V4-A0 与 REV15 历史纠正（未改写历史原件）

- V4-A0 SCREEN_FAIL 保留：25 条 ground_lying 中 24 ALERT、1 NO_ALERT；
  PFV4_SCREEN_0066 是已知多人漏检，VAL 当时未运行。
- 原 V4 DEV 主路正确 operational 分层：ground_lying=145、normal_negative=230、
  auxiliary_attention=41、visual_uncertain=20；坐地 55 条属于 normal_negative。
  倒地 141 ALERT + 4 RECHECK；坐地 0/55 ALERT；确定负例 0/230 ALERT。
- REV15 正确口径：ground_lying=145/145 ALERT；floor_sitting=15/55 ALERT（27.27%）；
  determinate_negative=15/230 ALERT（6.52%）。REV15 仍失败，主要是坐地误报，
  不是旧错误分层所声称的高优先级倒地召回降至 81.18%。
- REV15 旧报告的 ground_lying=186、normal_negative=195、recall=81.18% 不可继续使用。
  41 条 crawling/pushup/plank 等辅助近地姿态不能混入高优先级倒地分母；uncertain 不算确定负例。
- V5 不恢复 REV15，不使用其 scene 字段构建旁路；13/14/15 历史文件未回写。

### V5-A0 实际执行与结果

候选目录：`/home/yanbo/net_vlm_person_fallen_v2_optimization/16_person_fallen_v5_patrol_recheck/candidates/V5-A0-INDEPENDENT-RECHECK`。
唯一候选：`V5-A0-INDEPENDENT-RECHECK`，执行冻结 SHA256：
`40ebbde11f0f87c5722f14cc2b4e7357987d27cdfb0c90225073c8f84a3a83db`。

- PRIMARY_SOURCE=FROZEN_V4_CACHE；EVALUATION_MODE=CACHED_PRIMARY_PLUS_NEW_SECONDARY。
- 主路 9 字段 Prompt、policy、模型参数、detector、视图保持历史绑定，主路新增请求为 0。
- 旁路只接收已有 full-scene 448×336 JPEG70 原字节；返回 scene_review/evidence 两字段。
- 主路 ALERT 不请求旁路；主路 RECHECK 不能被清除；旁路仅可升级到 RECHECK，不能新增 ALERT。
- preparation inventory、逐行缓存/原响应/策略重放、源图/提示词/full/crop SHA 核验通过；
  13 项准备测试 + 18 项候选离线测试通过。冻结绑定 2,627 个文件/输入。
- 直连 qwen3.5:4b，digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`，
  Ollama 0.23.2；concurrency=1、think=false、stream=false、temperature=0、num_ctx=8192、num_predict=384。
- 无 warm-up/canary 额外请求，无 retry/resume；新增推理实际为 DEV 288 次，全部有效 JSON。

| DEV 指标 | 实际结果 |
|---|---|
| 总输出 / 缓存主路 | 436 / 436 |
| 旁路请求 / 有效响应 | 288 / 288 |
| ground_lying 立即 ALERT | 141/145 = 97.24%（继承主路） |
| ground_lying ALERT+RECHECK coverage | 145/145 = 100%（不是确认告警召回） |
| 坐地 ALERT FPR | 0/55 |
| 坐地总 RECHECK | 51/55 = 92.73% |
| 确定负例 ALERT FPR | 0/230 |
| 确定负例总 RECHECK | **90/230 = 39.13%，超过上限 23/230 = 10%** |
| 旁路 strict JSON / 主路 cache binding | 1.0 / 1.0 |
| ALERT 集合 | final = primary = 148 条 |
| scene_review | candidate_present=140，candidate_absent=148，uncertain=0 |
| 新测旁路 latency p50 / p95 | 1.4793s / 1.6735s |

auxiliary 41 条：2 ALERT（主路继承）、35 RECHECK、4 ATTENTION。
visual_uncertain 20 条：5 ALERT（主路继承）、15 RECHECK。
确定负例原主路 RECHECK 为 2，旁路新增 88，总计 90；不能只用增量作门禁分子。

这是干净完成后的 **DEV metric gate failure**，不是 infra/protocol failure。
旁路产生了过多正常负例复核，不能仅凭 ALERT 误报为零或 coverage 为 100% 宣告通过。
冻结后没有改 Prompt/schema/policy/runner/阈值或配额，没有创建 A1/A2/V6。

### 未执行范围与停止要求

- CONSUMED_SCREEN_DEVELOPMENT_REGRESSION=NOT_RUN：DEV 失败后禁止进入下一阶段。
- PFV4_SCREEN_0066 的 V5 secondary/final=NOT_RUN，不能声称已修复；历史缓存 NO_ALERT 保留。
- PRIMARY_NEW_MODEL_REQUESTS=0；DETECTOR_NEW_REQUESTS=0；VAL_REQUESTS=0；HOLDOUT_REQUESTS=0。
- 不读取 VAL/Holdout 图像、提示词、预测或样本内容；HOLDOUT_CONSUMED=false。
- 没有机器人复拍、移动/转向/变焦控制、现场/视频验证或生产集成。
- 已消费 SCREEN 即便日后获授权使用，也只能记为开发回归，不是独立 SCREEN。

```text
FINAL_STATUS=V5_A0_DEV_GATE_FAIL
DEVELOPMENT_CANDIDATE=V5-A0-INDEPENDENT-RECHECK
CURRENT_WINNER=NONE
TOTAL_NEW_MODEL_REQUESTS=288
READY_FOR_INDEPENDENT_VALIDATION_PROTOCOL_REVIEW=false
READY_FOR_FINAL_HOLDOUT=false
HOLDOUT_CONSUMED=false
ROBOT_REOBSERVATION_VALIDATED=false
PRODUCTION_INTEGRATION_READY=false
NEXT_ACTION=STOP_CURRENT_CANDIDATE
```

机器报告：`/home/yanbo/net_vlm_person_fallen_v2_optimization/16_person_fallen_v5_patrol_recheck/candidates/V5-A0-INDEPENDENT-RECHECK/reports/final_report.json`。
简明报告：`/home/yanbo/net_vlm_person_fallen_v2_optimization/16_person_fallen_v5_patrol_recheck/candidates/V5-A0-INDEPENDENT-RECHECK/reports/final_report.md`。
零推理独立输出复算：`/home/yanbo/net_vlm_person_fallen_v2_optimization/16_person_fallen_v5_patrol_recheck/candidates/V5-A0-INDEPENDENT-RECHECK/reports/independent_output_audit.json`。
DEV 原始请求/响应与完成锁：`/home/yanbo/net_vlm_person_fallen_v2_optimization/16_person_fallen_v5_patrol_recheck/candidates/V5-A0-INDEPENDENT-RECHECK/eval/dev/`。
本次到此停止；不能自动用“修评测”名义重新推理、修改候选或进入独立验证。

---

## 以下为保留的 V4-A0 历史交接正文


> 本文只对应 `event_name=person_fallen`。它是本旧 Codex 窗口截至
> `2026-09-09` 的单事件接手基线，不覆盖任何其它检测事件。
>
> 最新已验证状态优先。旧的 v2.0、v3.0、V4 prototype、P4D freeze 和
> 评测结果均保留为历史证据；不得用旧状态覆盖后续的 operational freeze
> 和 SCREEN_FAIL。本文是 UPDATE，不是聊天记录追加。

## 0. 文档用途与接手规则

- 新 Codex 窗口应先读取本文，再读取本文列出的 `person_fallen` 证据。
- 只允许围绕本事件核验；不得借此修改其它事件 handoff、共享数据集、生产
  项目或本事件历史 freeze。
- 文中区分：
  - **已确认事实**：有实际文件、summary、manifest、ledger 或命令结果支持；
  - **合理推断**：由事实推得但没有独立实验确认；
  - **UNVERIFIED**：当前没有足够证据。
- 本次所在工作目录 `/home/yanbo/net_vlm_yanboversion` 不是 Git 仓库：
  `git rev-parse --show-toplevel` 和 `git status --short` 均返回“不是 git 仓库”。
  因此 Git diff/status 审计为 `UNVERIFIED`；本次只对本文件执行写入，不能把
  Git 状态说成已验证。

## 1. 当前事件身份

```text
中文事件名=人员倒地
event_name=person_fallen
当前业务定义版本=v4.0-operational-high-priority
历史业务版本=v2.0, v3.0（均保留）
主要模态=静态单图 AIGC 开发/评测；生产目标为机器人安全巡检图像链路
当前阶段=V4-A0-FULL-CROP operational SCREEN
当前状态=SCREEN_FAIL
DEVELOPMENT_WINNER=NONE
CURRENT_WINNER=NONE
历史最佳语义开发参考=P2 C3（不是当前 winner、不是 release winner）
是否允许继续模型优化=false（当前任务边界下；如重新授权必须新 revision）
VAL=NOT_RUN
FINAL_HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
PRODUCTION_INTEGRATION_READY=false
```

`V4-A0-FULL-CROP` 是已经绑定并执行过 SCREEN 的 candidate，不是通过了
SCREEN 的 winner。V4 operational definition 已冻结；candidate 因 SCREEN
coverage 失败而没有晋级 VAL。

## 2. 当前事件业务定义

### 2.1 v4.0 operational-high-priority（当前定义）

高优先级 `person_fallen` 只表示可见的异常近地人体姿态，不要求推断“是否真的
摔倒”、是否受伤、昏迷、危险或动作原因。

`ALERT_GROUND_LYING`：

- 明确仰卧、侧卧或俯卧在地面；
- 明确蜷缩、横卧、摊倒；
- 躯干近似水平且大面积由地面承托；
- 明显塌落，无法维持正常站立、坐、跪、蹲、弯腰或行走姿态。

必须 `NO_ALERT_NORMAL_POSE`：

- 正常坐地、坐椅子；
- 正常站立、行走；
- 跪/半跪、蹲/半蹲；
- 弯腰、捡东西；
- 明确维修、清洁、施工、安装，且有工具、材料、拆装对象、操作动作或明确
  人-设备作业关系等可见证据；仅靠近设备不算维修；
- 床、沙发、躺椅等休息支撑上的正常躺卧。

视觉证据不足、人物过小、严重遮挡/模糊、只见局部、检测不到可靠人物或属性
冲突时使用 `RECHECK_VISUAL_UNCERTAIN`，不能静默变成 NO_ALERT。

`crawling`、`push-up`、`plank` 不再进入高优先级 binary gate。可见且明确时
映射为辅助低优先级 `ATTENTION_NEAR_GROUND`，不计为高优先级 `person_fallen`
的 TP/FN；该辅助结果供后续机器人行为使用。

Ground Truth 继续是 `PROMPT_DERIVED_SYNTHETIC_GT`，
`model_prediction_used_as_gt=false`，当前 v4 operational freeze 仍为
`HUMAN_SEMANTIC_REVIEW_REQUIRED=false`。定义文件没有覆盖 v3 历史。

### 2.2 历史定义变化

- v2.0 曾把较宽的倒地/近地姿态与 hard-negative 语义放在同一分类问题中；P2
  C3 是该时期的最佳语义参考。
- v3.0 将 crawling、push-up、plank 等功能性近地姿态放入 binary negative，
  但 C0-448/896 的 hard-negative 误报门禁失败。
- v4.0 operational 将高优先级目标收窄为“明确地面躺倒/塌落”，把上述动作
  移到辅助 attention；这是新的业务 freeze，不是对 v3 指标或 GT 的后验修改。

## 3. 项目目标

### 3.1 net_vlm 整体目标

为园区/机器人安全巡检提供可解释、低误报、可审计的视觉事件链路。AIGC
结果只能作为开发/评测证据；真实相机、机器人现场、视频时序和生产性能需要
独立验证。

### 3.2 person_fallen 当前目标

高优先级只在“明确躺倒或塌落且由地面承托”时提醒机器人，优先避免把正常坐地、
跪、蹲、弯腰、维修和床/沙发休息误报成倒地。当前 operational gate 为：

```text
ground_lying immediate ALERT recall >= 0.95
ground_lying ALERT+RECHECK coverage == 1.0
floor_sitting immediate ALERT FPR == 0
all determinate-negative immediate ALERT FPR == 0
strict JSON success == 1.0
```

静态图不能证明 temporal 性能；V4 已实现短时复核状态机，但尚未用真实视频
或独立视频集验证。

## 4. 当前最终状态

```text
EVENT=person_fallen
CURRENT_STAGE=V4-A0-FULL-CROP operational SCREEN
CURRENT_STATUS=SCREEN_FAIL

UNIQUE_P_LEVELS=7 (P0,P1A,P1R,P2,P2L,P3,P4D)
EXECUTED_CLASSIFIER_CANDIDATES=12
P4D_GENERATION_REVISIONS=documented separately; not classifier candidates

DEVELOPMENT_WINNER=NONE
CURRENT_WINNER=NONE
CURRENT_WINNER_STAGE=N/A
HISTORICAL_SEMANTIC_REFERENCE=P2 C3
CURRENT_PIPELINE=V4-A0 frozen full-scene+largest-person-crop attribute cascade; not accepted

DEV_STATUS=PASS_ZERO_INFERENCE_OPERATIONAL_GATE
SCREEN_STATUS=FAIL (24/25 ALERT+RECHECK coverage)
VALIDATION_STATUS=NOT_RUN_AFTER_SCREEN_FAIL
HOLDOUT_STATUS=NOT_RUN
HOLDOUT_CONSUMED=false

OPERATIONAL_DEFINITION_FROZEN=true
PRODUCTION_INTEGRATION_READY=false
FURTHER_MODEL_OPTIMIZATION_ALLOWED=false_under_current_freeze
NEXT_ACTION=STOP_AFTER_SCREEN_FAIL; future work requires a new authorized revision
```

### 4.1 最新 V4 DEV

使用已完成的 `V4-A0-FULL-CROP-436` predictions 做 zero-inference policy
重算，没有重复请求模型：

```text
ground_lying: 145 total, ALERT=141, RECHECK=4, NO_ALERT=0
ALERT recall=141/145=0.9724137931034482
ALERT+RECHECK coverage=145/145=1.0
floor_sitting: 55 total, immediate ALERT=0, FPR=0
determinate negatives: 230 total, immediate ALERT=0, FPR=0
RECHECK count=19, rate=0.04357798165137615
strict JSON success=1.0
DEV gate=PASS
```

### 4.2 最新 V4 SCREEN

使用冻结的 `V4-A0-FULL-CROP`，SCREEN 76 行，未访问 Holdout：

```text
ground_lying: 25 total, ALERT=24, RECHECK=0, NO_ALERT=1
ALERT recall=24/25=0.96
ALERT+RECHECK coverage=24/25=0.96  (required 1.0; FAIL)
floor_sitting: 25 total, immediate ALERT=0, FPR=0
determinate negatives: 51 total, immediate ALERT=0, FPR=0
RECHECK count=2, rate=0.02631578947368421
strict JSON success=1.0
detector coverage=74/76=0.9736842105263158
P50=2.437323097496119s
P95=2.7155437137407716s
SCREEN gate=FAIL
```

唯一导致 coverage 失败的样本是 `PFV4_SCREEN_0066`，taxonomy 为
`curled_or_partially_occluded_lying`，模型输出 `NO_ALERT_NORMAL_POSE`，
reason=`CLEAR_NORMAL_POSE:kneeling`。按协议没有运行 VAL，也没有创建
Final Holdout preflight。

## 5. P 阶段完整路线

只有以下 7 个主 P level 实际存在。`P0R1`、`P1B`、`P2D`、`P3-ALT` 等没有
在本事件证据中作为实际阶段执行，不补造。

下表所有计数均按 `TP/FP/TN/FN` 顺序；没有分类预测的 provider/generation
revision 的分类指标统一为 `N/A`，不是零。

| 阶段/候选 | 目的与变化 | 数据/结果摘要 | 结论 |
|---|---|---|---|
| P0 baseline | 原始单图 VLM；response-only parser；448×336 letterbox；无 crop/detector | DEV+VAL 410 请求 HTTP 全成功，但 `response` 为空、结构化内容在 thinking；JSON/schema=0/410，分类指标 N/A | 永久 protocol failure |
| P1A think=false | 只增加顶层 `think=false`，其余冻结 | DEV 310：TP/FP/TN/FN=120/29/141/0；P=.805369，R=1，F1=.892193，HN FPR=.263636，ordinary FPR=0，P50/P95=1.453798/1.610508s，JSON=1 | 协议修复；VAL 因 freeze manifest SHA mismatch 未成为完整 baseline |
| P1R recovery | 新 freeze-bound recovery VAL；不改 P0 prompt/config | VAL 100：40/11/49/0；P=.784314，R=1，F1=.879121，HN FPR=.275，ordinary FPR=0，P50/P95=1.478509/1.650989s | protocol-complete recovery；质量门禁失败、非 pristine |
| P2 C0 | P1A 离线 baseline 重算 | SCREEN 110 deterministic：50/22/38/0；P=.694444，R=1，F1=.819672，HN FPR=.55，P50/P95=1.456534/1.594376s | baseline |
| P2 C1 | explicit posture boundary Prompt | 50/22/38/0；HN FPR=.55，P50/P95=1.539897/1.761156s | 淘汰，无 HN 改善 |
| P2 C2 | ordered negative-posture veto | 50/29/31/0；P=.632911，R=1，F1=.775194，HN FPR=.725，P50/P95=1.451907/1.592479s | 淘汰，HN 恶化 |
| P2 C3 | support surface、torso/pelvis、active limbs evidence rubric | SCREEN 50/5/55/0；P=.909091，R=1，F1=.952381，HN FPR=.125，P50/P95=1.580759/1.815010s；recovery VAL 40/5/55/0，P=.888889，F1=.941176，P95=18.147252s | P2 最佳语义开发参考；不是 release winner |
| P2L A/B/C | 对 P2 C3 做远端 load/residency 时延取证，不改分类 | 受控 probe 协议=100%；keep_alive/diverse warm probe 改善长尾，但缺远端系统证据证明唯一根因 | forensic，无新候选/winner |
| P3 C3 forensic | 190 张 DESIGN 重跑 | 70/2/108/0；P=.972222，R=1，F1=.985915，HN FPR=.028571，ordinary FPR=0 | DESIGN-only，不代表泛化 |
| P3 S1_DIRECT | 一次 structured response 直接取 canonical decision | SCREEN 50/20/40/0；P=.714286，R=1，F1=.833333，HN FPR=.50，P95=9.601210s | 淘汰 |
| P3 S1_RULE | 同一 response 应用 deterministic rule | 与 S1_DIRECT 相同：50/20/40/0，HN FPR=.50，P95=9.601210s | 淘汰；P3 无 winner |
| V3-C0-448 | v3.0 binary，448×336 | DEV 185/37/193/1；P=.833333，R=.994624，F1=.906863，Accuracy=.908654，HN FPR=.238710，ordinary FPR=0，P50/P95=4.443172/5.475147s | gate fail |
| V3-C0-896 | v3.0 binary，896×672 | DEV 185/35/195/1；P=.840909，R=.994624，F1=.911330，Accuracy=.913462，HN FPR=.225806，ordinary FPR=0，P50/P95=9.445309/28.625082s | gate fail；停止 resolution search |
| V4-A0 prototype | pose attributes + full/crop cascade，原始 v4 binary | DEV 436：TP=169、FP=2、TN=228、FN=17；P=.988304，R=.908602，F1=.946779，HN FPR=.012903，ordinary FPR=0，P50/P95=2.399737/2.719135s；recall 失败主要来自 crawling | 原始 binary gate fail；不覆盖历史 |
| V4-A0 operational | 新 v4 operational definition；zero-inference DEV 后冻结并运行 SCREEN | DEV gate pass；SCREEN coverage=24/25=.96，其他 gate pass | 最新 candidate SCREEN_FAIL；无 winner |

P2 C0/C1/C2/C3 的 ordinary-negative FPR 均为 `0`、strict JSON/schema 均为
`1.0`、FN 均为 `0`；P2 C0/C1/C2 的 Accuracy 分别为 `.8、.8、.736364`。
P3 S1_DIRECT/S1_RULE 的 ordinary-negative FPR=0、strict JSON=1.0；P3 C3
DESIGN 也不是独立 validation。P0 没有 valid classification，因此其
Precision/Recall/F1/Accuracy/FPR/JSON success 的分类口径分别为 `N/A`、
协议 JSON/schema=0/410；P4D 所有 revision 的分类指标均为 `N/A`。

### 5.1 P4D generation lineage（不是分类候选）

P4D 只解决 AIGC hard-negative/lineage 供未来开发使用，provider 成功不是
GT，也没有自动进入 C3、VAL 或生产。实际存在的 revision 记录如下：

| revision | 实际执行 | 终态 |
|---|---|---|
| EBOND smoke | 1 次 HTTP401，0 图 | auth blocked |
| GR1 | 192 success、34 failure（429/401） | provider auth recurrence；未接受 |
| GR2 | 0 请求 | profile continuity gate blocked |
| GR3E | 99 success、1 429 | usage-limit blocked |
| GR3Q1 | 0 请求 | preparation blocked |
| GR3Q2E | 3 success、1 429 | failure policy stop |
| GR3Q3/GR3Q4 | 0 请求 | quota/preparation only |
| EB1 | 1 HTTP401，0 图 | primary auth blocked |
| GR3Q4E | 30 success、1 content-policy refusal | failure policy stop |
| GR3Q5 | 10 success、1 HTTP429 | provider 429 stop |
| GR3Q6 | 9 success、1 completion-unknown | unknown quarantine |
| GR3Q7 | 20/20 success | window cap |
| GR3Q8 | 25/25 success | window cap |
| GR3Q9 `_01` | 0 请求 | preflight config mismatch |
| GR3Q9 `_02` | 30/30 success，机械 QA pass | post-run authorization/runner cap mismatch，不能作为 clean formal freeze |
| GR3Q10 | 7 provider logical requests；6 success、1 confirmed HTTP429、23 not started | terminal partial mechanical QA；不得 resume |

最新 accounting 已确认：

```text
clean_success=202
binding_blocked_success=30
completion_unknown=1
safe_outstanding=207
sum=440
P4D_IMAGES_ACCEPTED=0
FORMAL_INGEST=false
GROUND_TRUTH_ASSIGNMENT=false
C3_ON_P4D=false
```

GR3Q10 terminal freeze 状态是 `COMPLETE_P4D_GR3Q10_PARTIAL_MECHANICAL_QA_NO_INGEST`，
6 张成功图不是人工语义 GT；Q9 mismatch 和 Q10 429 均保留，不能恢复旧 revision。

## 6. 所有候选技术对比

| 方案 | Prompt | Resolution/resize | ROI/crop | Detector | Temporal | Fusion | VLM calls |
|---|---|---|---|---|---|---|---:|
| P0/P1R/P2/P3 | 单图分类/语义 Prompt；P2 C3 加 support-state rubric | letterbox 448×336；P3 同 | 无 person crop | 无 | 无 | 直接二分类或 structured projection | 1 |
| V3-C0-448 | v3 C0 | letterbox 448×336 | 无 | 无 | 无 | binary remap | 1 |
| V3-C0-896 | v3 C0 | letterbox 896×672 | 无 | 无 | 无 | binary remap | 1 |
| V4-A0 | pose attribute Prompt | letterbox 448×336，JPEG70 | full scene + largest-person full-body crop | YOLO11n COCO person class | 2-of-3 recheck policy 已实现 | deterministic attribute policy | 1 请求、2 视图 |

固定 V4 runtime：`qwen3.5:4b`、Ollama `0.23.2`、直连
`http://192.168.20.62:11434`、digest
`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`、
`think=false`、temperature=0、strict JSON、`num_ctx=8192`、
`num_predict=384`、并发 1、无自动重试/unknown 重发。YOLO11n 权重 SHA 为
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`。

```text
Baseline=P1/P2 C0 semantic binary
Historical semantic reference=P2 C3
Current frozen candidate=V4-A0-FULL-CROP
Current accepted Winner=NONE
```

## 7. 当前为什么没有 Winner

P2 C3 仍是旧 v2/P2 线上最好的 semantic development reference：它在 SCREEN
上把 HN FPR 从 .55 降到 .125，保留 recall=1；但 recovery VAL 的 Precision=.888889、
HN FPR=.125、P95=18.147252s，不满足参考门槛。

v3 C0-448/896 都没有通过 Precision 和 HN FPR，且 896 只改善 2 个 FP；不能
把 v3 的 `MODEL_SIDE_LIMIT_REACHED` 继续当成当前 v4 业务定义的最终结论。

V4 operational 解决了当前目标中最重要的坐地/正常姿态问题：DEV 和 SCREEN
的 floor-sitting immediate FPR 均为 0，determinate-negative immediate FPR 也为 0。
但是 SCREEN 的一个明确 curled/partially-occluded lying 被清成 kneeling，
使 `ALERT+RECHECK coverage` 只有 .96，严格 gate 失败。因此不能选择 V4-A0
为 current winner，也不能进入 VAL 或 Final Holdout。

## 8. 当前最终 Pipeline

```text
输入单图
  ↓
YOLO11n person detection
  ↓
保留 full scene + largest-person full-body crop
  ↓
每次请求 letterbox 448×336、JPEG70
  ↓
qwen3.5:4b pose-attribute strict JSON
  ↓
严格 key/enum/evidence 校验
  ↓
deterministic_policy.py
  ├─ ALERT_GROUND_LYING
  ├─ NO_ALERT_NORMAL_POSE
  ├─ ATTENTION_NEAR_GROUND
  └─ RECHECK_VISUAL_UNCERTAIN
  ↓
部署侧 temporal_recheck.py：最多 3 帧，2-of-3 确认或升级歧义
  ↓
机器人安全巡检告警/辅助 attention
```

这是冻结 candidate 的工程形状，不是生产已集成 pipeline。`YOLOE=false`、
`segmentation=false`、`multi-crop=true`、`letterbox=true`、
`temporal=true（已实现但静态图未验证）`。

## 9. 数据集与评测状态

### 9.1 事件 workspace 与 split

v3-derived formal lineage 共 940 行，v3 formal manifests 为：

```text
DEV=436 (57 groups)
SCREEN=76
VAL=100
formal total=612
cross-split group leakage=0
DEV Holdout rows=0
GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT
HUMAN_SEMANTIC_REVIEW_REQUIRED=false for v3/v4 operational
```

v3 formal labels 为 `positive=251, negative=341, uncertain=20`；v3 DEV 为
`positive=186, negative=230, uncertain=20`。V4 operational 在 DEV 的工作 strata
为 `ground_lying=145、floor_sitting=55、determinate negative=230`；SCREEN
为 `ground_lying=25、floor_sitting=25、determinate negative=51`。

当前共享统一数据集只读核验结果：

```text
validator status=valid
error_count=0
full_hash_check=true
media_count=8536
label_count=8336
batch_count=51
split_count=3315
warning_count=687 (全局历史 warnings，未由本事件修复)
person_fallen labels/media=702
person_fallen v2.0=500
person_fallen v3.0=202
person_fallen source_type=ai_generated 702/702
person_fallen labels: event_label=1:261, 0:421, uncertain:20
```

共享 `splits.csv` 当前没有这 702 个 `person_fallen` media_id 的行；本事件评测
以隔离的 v3 manifests/local split 为准，不能把缺少共享 split 行误写成跨 split
泄漏。`v2.0` 旧 500 行未迁移；新增 202 行是 `v3.0`，两版本共存。

### 9.2 数据来源边界

本事件 formal 评测 lineage 是 `ai_generated`。当前可确认的
`public_dataset=0、phone_camera=0、robot_direct=0`；不能将 AIGC 结果单独等同
机器人真实生产准确率。v3/v4 均没有读取 Final Holdout，v4 SCREEN 的
`holdout_rows_read=0`。

## 10. 当前目录结构与关键证据

### 统一数据集

`/home/yanbo/net_vlm_xunjian_dataset`

### 当前事件独立优化 workspace

`/home/yanbo/net_vlm_person_fallen_v2_optimization`

### 生产项目（只读）

`/home/yanbo/net_vlm_yanboversion/vlm`

本次没有修改生产项目；其既有 dirty 状态因当前目录非 Git 仓库而无法用 Git
核验。

### 当前事件 docs

`/home/yanbo/net_vlm_yanboversion/docs/person_fallen/`

### 关键 revision

```text
11_person_fallen_v3_revision/
13_person_fallen_v4_pose_attributes/
14_person_fallen_v4_operational_freeze/
```

## 11. 已完成的功能

- v2/v3 AIGC provenance、prompt/image mapping、duplicate/group split audit；
- v3 deterministic remap、DEV/SCREEN/VAL manifests，cross-split group audit；
- P0 strict response-only protocol failure 记录与 P1 `think=false` 修复；
- P2 hard-negative semantic Prompt screening、C3 reference freeze、P2L latency
  forensic、P3 structured candidate screening；
- P4D generation ledger、provider failure/unknown quarantine、mechanical QA；
- 202 张 clean Codex generation 正式录入统一数据集为 v3.0，旧 500 张 v2.0
  保留；dataset validator 当前通过；
- V4 pose-attribute Prompt、YOLO11n crop、strict JSON、deterministic policy、
  temporal recheck implementation；
- V4 operational definition independent freeze；既有 DEV predictions 的
  zero-inference gate 重算；冻结 candidate 的 SCREEN 执行与失败报告。

## 12. 正在开发或尚未完成

### 正在开发

无。当前没有后台模型、provider、VAL 或 Holdout 任务。

### 尚未完成但不应自动启动

- V4 candidate 没有通过 SCREEN，因此 VAL 未执行；
- Final Holdout preflight 未创建，Holdout 仍未消费；
- 真实相机/机器人/视频 temporal validation 未完成；
- V4 SCREEN 的 curled/partially-occluded lying coverage 问题没有在旧 candidate
  上修复；若要处理必须新建授权 revision；
- P4D 440-slot full semantic acceptance 仍未完成，且本窗口最新指令要求停止
  继续 P4D generation；P4D 图像不进入当前 V4 winner 选择。

## 13. 关键技术

- `qwen3.5:4b` + Ollama：直接访问公司局域网 endpoint；不能把历史 thinking
  内容当作 response 或预测。
- Prompt engineering：V4 只抽取可见姿态属性，不让模型直接决定告警。
- letterbox 448×336、JPEG70：保持 V4 freeze 的输入 contract。
- YOLO11n person detector：为最大可见人物准备 full-body crop；detector 不是
  GT，也没有引入 YOLOE/segmentation。
- deterministic policy：根据 pose、torso orientation、torso-ground contact、
  head/shoulders-above-hips、support surface 和 work evidence 做确定性映射。
- strict JSON：exact keys/enums/evidence，解析失败进入 RECHECK。
- temporal recheck：2-of-3 frame state machine 已实现；静态图只证明代码/单帧
  policy，不证明视频性能。
- group-aware split：v3 DEV/SCREEN/VAL cross-group leakage=0；Holdout 保持
  不访问。

## 14. 重要文件说明

| 路径 | 用途 | 当前状态 | 是否允许修改 |
|---|---|---|---|
| [`docs/person_fallen/codex-handoff.md`](/home/yanbo/net_vlm_yanboversion/docs/person_fallen/codex-handoff.md) | 本事件交接 | 本次 UPDATE 后为最新状态 | 仅后续本事件状态变化时更新 |
| [`person_fallen_v4_operational_definition.md`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/definition/person_fallen_v4_operational_definition.md) | v4 operational definition | SHA=`e0a3b104...06d7e`，已冻结 | 不覆盖 |
| [`V4-A0_pose_attributes_prompt.txt`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/prompt/V4-A0_pose_attributes_prompt.txt) | 冻结 Prompt | SHA=`a8136720...8fad7` | 不改；新实验新 revision |
| [`deterministic_policy.py`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/policy/deterministic_policy.py) | 属性到决策 | SHA=`3a3e16f1...a9ccaf` | 不改 |
| [`temporal_recheck.py`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/policy/temporal_recheck.py) | temporal policy | 已冻结并单元测试 | 不改 |
| [`final_operational_plan.json`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/protocol/final_operational_plan.json) | model/detector/preprocess/split binding | plan SHA=`88ffaf7c...f9d37` | 不覆盖 |
| [`CANDIDATE_FREEZE.json`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/freeze/CANDIDATE_FREEZE.json) | V4 candidate immutable binding | `FROZEN_PENDING_SCREEN` artifact；SCREEN 结果另由 summary 记录 | 不回写 |
| [`run_operational_eval.py`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/tools/run_operational_eval.py) | frozen SCREEN/VAL runner | SHA=`78858e39...e60f94` | 不改旧 candidate |
| [`dev_V4-A0-FULL-CROP-436/summary.json`](/home/yanbo/net_vlm_person_fallen_v2_optimization/13_person_fallen_v4_pose_attributes/eval/runs/dev_V4-A0-FULL-CROP-436/summary.json) | V4 原型 DEV raw summary | sealed；zero-inference source | 不覆盖 |
| [`screen_V4-A0-FULL-CROP/summary.json`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/eval/runs/screen_V4-A0-FULL-CROP/summary.json) | 最新 SCREEN 实际结果 | COMPLETE、gate=false、summary SHA=`df59dc3e...c72840` | 不重跑覆盖 |
| [`final_operational_report.md`](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/reports/final_operational_report.md) | V4 最终状态报告 | SCREEN_FAIL | 保留 |
| [`person_fallen_v3_screen_manifest.csv`](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_screen_manifest.csv) | SCREEN source manifest | SHA=`8e9b4048...e8923c` | 不改 |
| [`person_fallen_v3_val_manifest.csv`](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_val_manifest.csv) | VAL source manifest | SHA=`ffe093f9...184302`；未用于 V4 VAL | 不改 |
| [`124_p4d_gr3q10_final.md`](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/124_p4d_gr3q10_final.md) | P4D latest terminal report | 6 success/1 HTTP429/23 not started；no ingest | 不改 |
| `/home/yanbo/net_vlm_xunjian_dataset/01_annotations/{media,labels,batches,splits}.csv` | 统一数据集 metadata | validator valid；person_fallen 500 v2 + 202 v3 | 只读 |

## 15. 已知问题

1. **SCREEN coverage 失败（阻塞）**：一个 curled/partially-occluded lying 被
   判为 kneeling，导致 coverage=.96 而不是 1.0。影响是当前 candidate 不能进入
   VAL/Holdout；不能修改旧 Prompt 或重新挑样本掩盖。
2. **V4 detector coverage 不是 100%**：SCREEN 为 74/76；当前 ground-lying
   rows 检测覆盖为 100%，但一般样本的缺失会增加 RECHECK 风险。
3. **V3 hard-negative 误报**：448/896 的 HN FPR=.2387/.2258，证明旧 v3
   binary 语义不适合当前高优先级业务；不应再用它否定新的 v4 operational
   定义，也不应把失败改写为通过。
4. **P4D lineage 未被人工接受**：clean 202、binding-blocked 30、unknown 1、
   safe 207 的 accounting 只是生成/机械证据；不能当 GT、不能自动进 C3。
5. **AIGC domain gap**：所有当前 formal 评测为 ai_generated；没有 robot_direct
   或真实相机独立 gate，production accuracy 为 UNVERIFIED。
6. **共享数据集 warning 增长**：validator 当前 687 warnings、0 errors；这些是
   全局历史 metadata warnings，本次没有归因、修复或覆盖其它事件。
7. **Git 取证缺口**：当前 shell 路径不是 Git 仓库；生产代码是否存在其它窗口
   的 dirty diff 不能由本次 handoff 证明。

## 16. 后续优化方向

### Priority 1

当前不继续模型优化。若业务方明确要处理 SCREEN 失败，必须新建独立、
self-consistent revision，针对“部分遮挡/蜷缩躺地被判 kneeling”定义新的 DEV
gate；不能改写 V4 freeze、SCREEN summary、GT 或 v3 历史，也不能直接使用
SCREEN 个体错误反调旧 Prompt。

### Priority 2

获得真实机器人/相机视频后，单独验证 detector coverage、人物尺度、遮挡、
2-of-3 temporal recheck、告警延迟和人工 adjudication；AIGC 指标不能代替它。

### Priority 3

只有新的 candidate 通过合法 DEV、SCREEN、VAL 后，才可生成 immutable Final
Holdout preflight 并等待用户授权；不得读取当前 Holdout 做开发。

### 不建议继续

- 不建议恢复 P4D/Q10、重发 provider 失败或 completion-unknown slot；
- 不建议继续 448/896 全图 search；v3 896 只减少 2 个 FP；
- 不建议用 pose/segmentation/新 verifier 继续扩大实验范围；
- 不建议把 crawling/push-up/plank 强行放回高优先级 gate；它们当前是辅助
  `ATTENTION_NEAR_GROUND`。

## 17. 下一步具体行动

当前只有一个安全动作：

```text
STOP_AFTER_SCREEN_FAIL
```

如果用户未来重新授权开发：

1. 新建新的 `person_fallen` revision，先绑定新的 definition、Prompt、GT policy、
   split、runner、model digest 和 stop rule；
2. 只在新的 DEV 上验证 coverage、FPR、strict JSON 和 detector boundary；
3. 新 DEV 通过后，才可从新的 candidate 再走 SCREEN→VAL；
4. SCREEN 或 VAL 任一失败，立即停止，不读取 Holdout；
5. 只有 DEV/SCREEN/VAL 全通过，才生成 Holdout preflight，等待单独授权。

没有新授权时，不执行上述第 1 步，也不执行任何模型/provider 请求。

## 18. 不允许改动的约束

### 生产项目与共享数据

- 不修改 `/home/yanbo/net_vlm_yanboversion/vlm`；
- 不修改共享 dataset CSV、media、labels、review links 或其它事件 metadata；
- 不修改 v2/v3 GT、taxonomy、manifest、remap、历史 metrics、ledger、freeze；
- 本事件的 202 张 v3 clean ingest 与旧 500 张 v2.0 共存，不批量迁移版本。

### Ollama

```text
ENDPOINT=http://192.168.20.62:11434
MODEL=qwen3.5:4b
```

后续推理只允许评测程序直接访问该公司局域网地址，不采用任何端口转发承载
推理的方案。模型、服务、权重和服务器配置均不得修改。当前冻结 candidate 的
并发为 1、无自动重试。

### Ground Truth 与 Holdout

- 禁止模型预测覆盖 GT；禁止为提高指标改标签；
- 禁止读取 Holdout 做 prompt、threshold、candidate 或 GT 选择；
- 当前 `HOLDOUT_CONSUMED=false`、requests=0；不得 resume、rerun 或复用；
- v4 当前 `HUMAN_SEMANTIC_REVIEW_REQUIRED=false` 是 synthetic policy，不得
  推导为 Human Gold。

### Git 与范围

- 不执行 `git add/commit/push/reset/clean/restore` 等越界或破坏性操作；
- 本窗口只允许更新本文件；不得批量生成其它事件 handoff；
- 若未来需要本事件实验，必须在独立 workspace、新 revision 中进行。

## 19. 新 Codex 窗口接手时禁止重复的工作

- 不重跑 P0 的 410 个 protocol-failure 请求；
- 不伪造或补跑 P1A VAL，不重跑 P1R/P2 VAL；
- 不重复 P2 C0/C1/C2/C3、P2L A/B/C 或 P3 S1 screening；
- 不重跑 V3-C0-448/896，也不把 v3 `MODEL_SIDE_LIMIT_REACHED` 当作 v4
  operational 最终结论；
- 不重复 V4 DEV zero-inference 或已完成的 SCREEN；
- 不修改 V4 freeze、Prompt、policy、GT 或 SCREEN summary 来让 gate 通过；
- 不恢复 GR1/GR3/Q windows/Q9/Q10，不重发 completion-unknown 或 confirmed
  failure，不继续 P4D generation；
- 不运行 VAL 或 Final Holdout；不消费 Holdout；
- 不把 P2 C3 的历史 reference 写成当前 winner；当前 winner 是 NONE。

## 20. 最终状态速查

```text
EVENT=person_fallen
BUSINESS_DEFINITION=v4.0-operational-high-priority
CURRENT_STAGE=V4-A0-FULL-CROP operational SCREEN
CURRENT_STATUS=SCREEN_FAIL

UNIQUE_P_LEVELS=7
EXECUTED_CANDIDATES=12 classifier candidates (P4D revisions separate)

CURRENT_WINNER=NONE
CURRENT_WINNER_STAGE=N/A
CURRENT_PIPELINE=YOLO11n crop + full/crop V4 attribute JSON + deterministic policy + temporal recheck

BEST_CONFIRMED_PRECISION=0.988304 (historical V4-A0 original binary DEV; not current winner)
BEST_CONFIRMED_RECALL=1.000000 (historical P1R/P2 C3 scopes; not current operational gate)
BEST_CONFIRMED_F1=0.985915 (historical P3 C3 DESIGN-only; not generalization)
BEST_CONFIRMED_HARD_NEG_FPR=0.012903 (historical V4-A0 original binary DEV; current operational strata are reported separately)
WINNER_P95=N/A (no current winner)

YOLOE_IN_FINAL_PIPELINE=false
SEGMENTATION_IN_FINAL_PIPELINE=false
TEMPORAL_IN_FINAL_PIPELINE=true_implemented_static_validation_not_done
MULTI_CROP_IN_FINAL_PIPELINE=true
LETTERBOX_IN_FINAL_PIPELINE=true

DEV_STATUS=PASS_ZERO_INFERENCE_OPERATIONAL_GATE
SCREEN_STATUS=FAIL
VAL_STATUS=NOT_RUN
HOLDOUT_STATUS=NOT_RUN
HOLDOUT_CONSUMED=false

PRODUCTION_INTEGRATION_READY=false
FURTHER_MODEL_OPTIMIZATION_ALLOWED=false_under_current_freeze
NEXT_ACTION=STOP_AFTER_SCREEN_FAIL; new authorization and new revision required for any future work
```

## 21. 关键证据索引

- [v3.0 final report](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/reports/person_fallen_v3_final_report.md)
- [v3 448 DEV summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/eval/runs/dev_V3-C0-448/summary.json)
- [v3 896 DEV summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/eval/runs/dev_V3-C0-896/summary.json)
- [V4 prototype operational analysis](/home/yanbo/net_vlm_person_fallen_v2_optimization/13_person_fallen_v4_pose_attributes/reports/v4_full_dev_operational_analysis.md)
- [V4 operational definition](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/definition/person_fallen_v4_operational_definition.md)
- [V4 final operational plan](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/protocol/final_operational_plan.json)
- [V4 candidate freeze](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/freeze/CANDIDATE_FREEZE.json)
- [V4 DEV source summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/13_person_fallen_v4_pose_attributes/eval/runs/dev_V4-A0-FULL-CROP-436/summary.json)
- [V4 SCREEN summary](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/eval/runs/screen_V4-A0-FULL-CROP/summary.json)
- [V4 final operational report](/home/yanbo/net_vlm_person_fallen_v2_optimization/14_person_fallen_v4_operational_freeze/reports/final_operational_report.md)
- [P4D GR3Q10 final report](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/124_p4d_gr3q10_final.md)

本文件不包含旧的端口转发说明；Ollama 后续只按上述局域网地址直接访问。
