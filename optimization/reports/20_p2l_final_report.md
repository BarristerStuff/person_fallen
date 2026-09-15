# person_fallen V2 — P2L remote latency forensics final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR
P1R_STATUS=COMPLETE
P2_STATUS=COMPLETE
P2_WINNER=C3

P2L_NAME=P2L_REMOTE_LATENCY_FORENSICS
P2L_STATUS=COMPLETE
P2L_ANOMALY_REPRODUCED=false
HISTORICAL_ANOMALY_REPRODUCED=false
P2L_ROOT_CAUSE=UNRESOLVED_LOAD_DURATION_RUNTIME_CAUSE
P2L_PRIMARY_COMPONENT=load_duration
P2L_WINNER=NONE
CURRENT_BEST_SEMANTIC_CANDIDATE=C3
CURRENT_SEMANTIC_CANDIDATE=C3_UNCHANGED
CURRENT_C3_WARM_RUNTIME_HEALTHY=true

P2L_FORMAL_PROBE_REQUESTS=64
P2L_PRESERVED_INITIAL_ATTEMPT_REQUESTS=1
P2L_NEW_DEV_REQUESTS=65
P2L_NEW_VAL_REQUESTS=0
P2L_HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false

OLLAMA_SERVICE_MODIFIED=false
PRODUCTION_CODE_MODIFIED=false
P3_EXECUTED=false
```

## 已确认事实

### 1. 数据、模型与冻结边界

- 任务使用已完成并冻结的 `person_fallen` V2 数据；没有重新 ingest、改 GT、改 split 或修改 shared split CSV。
- 结束时正式 validator 仍为 `status=valid`、`error_count=0`、`full_hash_check=true`、`warning_count=387`、`media_count=4201`、`label_count=4201`。387 是既有 warning，不是 P2L 新增错误。证据：[dataset_validator_final.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/00_preflight/dataset_validator_final.json)。
- `/api/version` 为 Ollama `0.23.2`；`/api/tags` 中 `qwen3.5:4b` 存在，digest 为 `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`，details 为 qwen35、4.7B、Q4_K_M。最终 `/api/ps` 同一 digest 已加载，`size_vram=6088300544`、`context_length=8192`、HTTP 200。
- Prompt SHA 为 `685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e`；P2L request config SHA 为 `8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d`；P2L runner SHA 为 `5061817f87882f8137229d2a5d7011c3da5cfe5fabde7fb6161a5ddbeaefde00`。Prompt、preprocess、format、think、temperature、context 和 generation limit 没有被 P2L 改动。
- P2 frozen winner、P2 C3 SCREEN/VAL predictions、P2 VAL raw/log 的结束哈希均与 P2L 开始前记录一致；`p2_frozen_artifacts_unchanged=true`。P2 历史没有重写。

### 2. 历史 P2 C3 时延事实

历史分析仅从 P2 C3 的 raw response JSONL + request log JSONL 重算，见 [18_p2l_historical_latency_forensics.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/18_p2l_historical_latency_forensics.md)：

| 数据集 | n | high-load (>5s) | client P50/P95 | total P50/P95 | load P50/P95 | prompt-eval P50/P95 | eval P50/P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SCREEN | 120 | 0 | 1.580912 / 1.814611 s | 1.572841 / 1.806169 s | 0.459518 / 0.505485 s | 0.120626 / 0.142331 s | 0.465114 / 0.640630 s |
| VAL | 100 | 63 | 14.682363 / 18.144259 s | 14.673721 / 18.136487 s | 13.324700 / 16.756087 s | 0.140699 / 0.167674 s | 0.493393 / 0.744843 s |

VAL 的自动阈值变化点不是手工假设：`1–20 HIGH → 21 LOW → 22–64 HIGH → 65–100 LOW`。最长 sustained high 为 22–64（43 条）；第 65 条恢复为 low。22–64 的 load median/P95 为 `13.762809 / 16.633463s`，65–100 为 `0.470802 / 0.519604s`。因此历史主要异常组件是 `load_duration`，不是 prompt-eval 或 eval。

`prompt_eval_count` 在历史 SCREEN/VAL 都恒为 `[598]`；`eval_count` 虽可变，但与 load 的 Spearman 为 SCREEN `-0.038339`、VAL `-0.174355`，不能解释十秒级 load tail。图像字节数与 load 的 Spearman 为 SCREEN `0.036989`、VAL `0.124548`。

### 3. P2L 正式 DEV 探针数字

三组均使用 `response`-only parser；A/C 不带显式 keep-alive，B 只增加顶层 `keep_alive="30m"`。协议结果全部为 100%：

| Probe | n | HTTP | response non-empty | thinking present | JSON/schema/canonical | load>5s | client P50/P95/max | load P50/P95/max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A exact C3 | 24 | 24/24 | 24/24 | 0/24 | 24/24/24 | 1 | 1.418261 / 1.518300 / 8.285873 s | 0.473133 / 0.503247 / 6.985410 s |
| B fixed + `keep_alive=30m` | 24 | 24/24 | 24/24 | 0/24 | 24/24/24 | 0 | 1.396662 / 1.440333 / 1.447384 s | 0.466865 / 0.498783 / 0.508403 s |
| C diverse DEV | 16 | 16/16 | 16/16 | 0/16 | 16/16/16 | 0 | 1.717896 / 1.826522 / 1.910301 s | 0.453339 / 0.530351 / 0.554933 s |

Probe A 第 1 条是一个 cold-load 行（client `8.285873s`、load `6.985410339s`），A 的第 2–24 条以及 B/C 全部没有 >5s load。A 的当前单个 cold spike 不等于历史 VAL 的 43 条 sustained anomaly，因此 `P2L_ANOMALY_REPRODUCED=false`；本结论并不否认已观察到一次冷加载。

当前 exact-C3 warm 集合定义为 A 的 23 个 low-load 行 + C 的 16 个行，共 39 条：client P50 `1.450764s`、P95 `1.796366s`、max `1.910301s`，相对 `1.852084s` 的开发时延门槛，P95 通过。B 的 keep-alive 序列 P95 `1.440333s`，但 B 紧跟 A，未作随机交叉/冷启动配对，不能做强因果声明。

所有 A/B/C `prompt_eval_count` 都是 `[598]`；A/B 固定图 image-byte 相关性无定义（字节数不变）；C 的 eval_count-load Spearman `0.075111`、image-bytes-load Spearman `0.232353`，样本小且无 high-load 行，只作辅助检查。完整逐请求结果见 [07_analysis](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis)。

### 4. 运行时遥测和请求边界

- `/api/ps` A 开始前为 `models=[]`，A 中点/结束已加载 qwen3.5:4b；B/C 开始与结束保持已加载；最终快照仍为 loaded。该状态证据不能替代完整 daemon 日志。
- 只读 SSH 到 `tiga@192.168.20.62` 在 preflight 和探针快照均因 `Permission denied (publickey,password)` 失败。因此 GPU utilization、VRAM 时间序列、compute PID、Ollama PID/runner PID、systemd 和 journal 都是 unavailable；没有虚构这些值，也没有修改远程服务。外部 1 秒 telemetry 未能建立。
- 正式探针请求为 A=24、B=24、C=16，共 64 条 DEV/P2_DESIGN 新请求。首次 runner manifest-expansion 缺陷产生的 1 条请求被原样保留在 [04_probe_A_exact_c3_attempt_001](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/04_probe_A_exact_c3_attempt_001)，没有删除、合并或伪装成正式 A；所以审计总计为 65 条新 DEV 请求。P2L logs 中非 DEV=0、HOLDOUT=0、protocol failures=0，`P2L_NEW_VAL_REQUESTS=0`。

## 实验判断

### 合理推断

历史 VAL 的高时延几乎由 `load_duration` 占据；client latency 与 Ollama total 的差值只有约 8–10ms 量级。prompt-eval、eval、prompt token 数和图像字节数没有对应的十秒级变化。结合 `/api/ps` 从空到 loaded、A 的首请求 load spike、后续相同图像低 load 以及 B 的低 load，最合理的运行时解释是模型驻留/加载状态切换；但 A→B 是顺序实验，不能证明 `keep_alive` 的独立因果效果。

### 未验证假设

具体是 Ollama reload/residency churn、GPU/VRAM contention、runner 生命周期、调度器还是其他远端 daemon 条件中的哪一个，因缺少远端遥测仍无法确定。以下 H1–H7 矩阵保留每个假设的证据等级，不把推断升级成事实。

### H1–H7 状态

| 假设 | 状态 | 依据摘要 |
|---|---|---|
| H1 model residency/reload churn | PARTIALLY_SUPPORTED | 历史 high run、`/api/ps` 空→loaded、A 首条 cold spike 支持；但当前未复现 sustained anomaly，且无远端服务日志 |
| H2 GPU contention/VRAM pressure | UNRESOLVED | load tail 相容，但 nvidia-smi/VRAM/PID 不可得 |
| H3 runner lifecycle/scheduler | UNRESOLVED | 可能解释状态转折，但 runner PID、systemd/journal 不可得 |
| H4 request/image-dependent cost | NOT_SUPPORTED | A 固定图除首条外稳定，C 16 张不同图都无 high-load |
| H5 prompt/generation cost | NOT_SUPPORTED | prompt_eval_count 恒为 598，prompt/eval P95 亚秒 |
| H6 client/network transport | NOT_SUPPORTED | client≈total，overhead 仅毫秒量级 |
| H7 other remote runtime anomaly | UNRESOLVED | 历史异常真实存在，但缺 daemon/GPU/process 证据无法定位 |

逐项证据在 [hypothesis_matrix.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/hypothesis_matrix.csv)。

## 风险与限制

- P2L 是运行时取证，不是语义质量实验；不能把 A/B/C 的 canonical 输出当作新的 DEV accuracy baseline，也不能据此修改 C3 Prompt、GT、阈值或 P2 结果。
- P2 的质量门槛仍未通过：P2 C3 VAL precision `0.888889 < 0.93`、hard-negative FPR `0.125 > 0.05`；P2 latency gate 也曾因 VAL P95 约 `18.147252s` 失败。P2L 不改写这些事实，也没有产生新的 `P2L_WINNER`。
- B 使用固定顺序且紧跟 A，可能受驻留状态、时间或缓存影响；A/C 样本规模只适合诊断，不足以证明远端状态的分布性规律。
- SSH 不可用使 GPU/VRAM/runner/service 根因保持未决；若没有授权只读访问，不应声称已经确认具体 daemon 或硬件根因。
- 生产 VLM 代码目录的既有 dirty worktree 被保留，P2L 未写入；审计时已读取但未执行清理、reset、restore、git add 或服务控制。

## 下一阶段建议

按“历史异常当前未复现且 exact-C3 warm P95 通过参考线”的决策规则，建议 `NEXT_STAGE=P3_HARD_NEGATIVE_REFINEMENT`，但要把“历史 latency anomaly unresolved”作为部署风险持续记录；本次不执行 P3。若运行时 SLA 是当前阻塞项，则先获取只读远端 telemetry 或另行注册随机化的 DEV runtime revision，再把语义迭代与运行时验证分开。无论哪条路径，都不能把当前 B 的顺序差异当作因果证据，也不应重跑 VAL/HOLDOUT。

1. 若要完成根因闭环，先提供 `tiga@192.168.20.62` 的只读 SSH 权限，或由服务器管理员导出与请求时间对齐的 GPU/VRAM、Ollama PID、systemd/journal 和 runner 调度日志；保持不写服务、不重启、不 unload。
2. 若继续做 runtime 验证，单独注册新的、非 VAL/HOLDOUT 的 DEV revision，预先随机化 cold/warm 顺序并固定探针、重复数和 1 秒采样策略。
3. 只有在另一个明确批准的阶段，才讨论 Prompt、分辨率、crop/ROI、pose、视频、temporal、阈值或 parser 变化；本 P2L 不执行这些修改。

## 交付物

- [18_p2l_historical_latency_forensics.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/18_p2l_historical_latency_forensics.md)
- [19_p2l_controlled_dev_probes.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/19_p2l_controlled_dev_probes.md)
- [07_analysis/forensic_summary.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/forensic_summary.json)
- [07_analysis/final_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/final_audit.json)
- [07_analysis/all_requests.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/all_requests.csv)
- [07_analysis/latency_components.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/latency_components.csv)
- [07_analysis/hypothesis_matrix.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/hypothesis_matrix.csv)
- [07_analysis/anomaly_requests.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/anomaly_requests.csv)
- [07_analysis/change_point_analysis.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/change_point_analysis.csv)
- [07_analysis/final_forensic_summary.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/final_forensic_summary.json)
- [03_runtime_telemetry/telemetry_report.md](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/03_runtime_telemetry/telemetry_report.md)

`all_requests.csv` contains 285 globally timestamp-sorted rows: 120 historical SCREEN, 100 historical VAL, 64 formal P2L DEV probe requests, and the one preserved initial DEV attempt. GPU memory/utilization and runner-PID columns are explicit `unavailable` where remote telemetry could not be authenticated.
