# person_fallen V5：园区巡逻人员倒地发现与复拍路线

状态：`PREPARATION_COMPLETE_NO_INFERENCE`。本目录是新 V5 的零推理准备，不是已通过的候选，不是生产集成。

## 1. 业务与数据边界

- 事件仍是 `person_fallen`，沿用 V4 operational 的视觉业务定义，不修改历史 GT。
- 巡逻相机看到已经地面躺倒、蜷缩或塌落的人员即可产生高优先级候选；**不要求拍到从站立到倒地的动作过程**。
- 静态图不用于证明摔倒原因、受伤、昏迷；正常坐地、跪、蹲、弯腰、明确作业、床/沙发休息仍按旧定义处理。
- 不再以人工逐图语义审核作为合成数据开发的前置条件。继续使用 `PROMPT_DERIVED_SYNTHETIC_GT`。
- 用户声明生成提示词与图像相符；本次已核验 DEV 436 条提示词路径及 hash，但不宣称完成全量像素语义验证，也不把模型预测作为 GT。
- 不读取 VAL 图像/预测或 Holdout。任何合成开发通过都不是现场准确率证明。

## 2. 为什么不继续 REV15

按原 V4 口径复核：REV15 高优先级倒地为 145/145 ALERT，但坐地误报为 15/55，确定负例误报为 15/230。原报告的 186 倒地、195 正常负例口径错误。

V5 不恢复 REV15，不把其错误清单当开发标签。历史原件保持不变；本目录报告记录按原 V4 分层的历史对照。

## 3. 唯一建议候选方向：主路不变，场景检查独立，只触发复拍

1. 主路完整保留原 V4 的 9 字段 Prompt、人物属性及确定性规则，不删除坐地细则、不追加场景字段到主路。
2. 主路 ALERT 保留；对所有非 ALERT 结果，独立场景检查寻找可能遗漏的倒地人员，不能只按 detector 框数大于 1 触发。
3. 新检查只允许把结果升级为 `RECHECK_VISUAL_UNCERTAIN`，**不能凭一个场景 yes 直接创建高优先级 ALERT**。
4. 场景不确定、无有效结果、或主路已 RECHECK 时，不得静默放行为 NO_ALERT。
5. 机器人收到 RECHECK 后的建议行为是获取新观测或安全的另一视角，再由主路识别。这里仅是设计，不会操控机器人，不会把静态图重复请求当真实复拍测试。
6. 到达预先配置的帧数/时间预算仍不明确，保留未确认状态并报告；不得伪造倒地确认，也不得静默清除。

`policy/routing_contract.py` 只实现首帧调度契约，不包含模型、场景检查 Prompt、网络请求或机器人行为。

**限制**：这条路线能在结构上阻止旁路新增立即报警，但不能保证旁路发现所有漏检、也不能证明复拍后一定确认；这些必须单独评测。原 V4 在 auxiliary/uncertain 的既有问题仍需单列报告，不能通过分母调整掩盖。

## 4. 已完成的零推理工作

- 读取原 V4 DEV 436 行，保存原 GT、taxonomy、group、source_split、图像/提示词/视图 SHA。
- 生成 V5 专用只读衍生 manifest，不修改任何来源文件。
- 固定分层：ground_lying=145；normal_negative=230；auxiliary_attention=41；visual_uncertain=20；floor_sitting=55 是 normal_negative 子集。
- 核验 436 张源图、436 份生成提示词、436 个全图与 436 个 crop 的 hash。
- 基于保存预测核对 V4 与 REV15 历史指标；不是 V5 推理结果。
- 编写并通过 13 项离线单元测试，覆盖指标分层及旁路不直接报警/unknown 不静默清除。

产物：

- `protocol/v5_preparation_plan.json`：路线、运行边界和拟议请求上限。
- `manifests/v5_dev_manifest.csv`：V5 DEV 衍生 manifest。
- `reports/preparation_audit.json`：来源 hash、分层和历史对照。
- `tools/prepare_v5_dev.py`：无网络依赖的准备/历史统计程序；输出存在时拒绝覆盖。
- `tests/test_v5_contract.py`：纯离线测试。

## 5. 后续顺序与成本

### V5-P0：下一项实际工作

实现并冻结**一个**独立场景检查 Prompt/schema/runner。主路不变，detector 不变，resolution 不变，模型不变。冻结完整 Prompt/schema/policy/model/detector/preprocess/source/runner 的 hash 以及停止条件，再允许推理。

### V5-P1：开发评测

- 优先复用具有相同输入/Prompt/policy/model/preprocess 绑定的 V4 主路历史输出，标记 `cached primary`，不得假称新推理或新端到端时延。
- DEV 436 的主路非 ALERT 为 288 行，拟议新增旁路请求上限 288。
- 完整 DEV 通过后，再使用已消费 SCREEN 76 作为开发回归；其主路非 ALERT 为 52 行，拟议新增旁路请求上限 52。
- 合计最多 340 条新的旁路请求；若采用 canary，计入同一配额并复用严格相同的成功响应，不另行重跑。
- 每幅图在线初次观察最多主路 1 次 + 旁路 1 次请求。机器人新观测会增加实际耗时/调用量，当前尚未测量。
- 测量主路继承错误、旁路触发率、确定负例 RECHECK 率、严格 JSON、请求耗时。不得用把所有正常样本都送 RECHECK 的方式过 coverage gate。
- 新增工程护栏草案：确定正常负例的总 RECHECK 率不超过 10%；须在首次新推理前冻结。这不是已确认的现场 SLA。

### V5-P2：独立验证及巡逻行为验证

只有开发和已消费 SCREEN 的回归门禁通过，才进行候选冻结及独立验证集暴露/分组审计。不得默认历史 VAL 从未在其它 revision 使用。当前不授权读取 VAL 图像/预测，也不授权 Holdout。

静态开发报告只证明首帧判断与调度。机器人复拍闭环、告警延迟、最终未确认率需真实序列独立验证；这不要求开发前先完成人工逐图审核，但也不能被合成静态指标替代。

## 6. Ollama 与执行边界

所有巡检事件共用 `http://192.168.20.62:11434`，模型 `qwen3.5:4b`，客户端并发固定 1。任何模型请求前先直接 GET `/api/tags` 并严格核验模型 name/digest；不可达立即停止。

禁止 tunnel/SSH 转发、localhost 替代、ControlMaster/ControlSocket、修改远端文件/服务/模型、设置 CUDA_VISIBLE_DEVICES 或固定 GPU。不得自动重试已知失败或 completion-unknown。

本次：模型请求=0；detector 请求=0；VAL/Holdout 图像访问=0；候选 freeze=无；CURRENT_WINNER=NONE；生产可集成=false。
