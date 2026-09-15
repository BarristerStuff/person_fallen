# P2L historical latency forensics

## Status

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
STAGE=P2L_REMOTE_LATENCY_FORENSICS
P2L_HISTORICAL_SOURCE=P2_C3_RAW_RESPONSES_AND_REQUEST_LOGS
P2L_NEW_VAL_REQUESTS=0
P2L_HOLDOUT_REQUESTS=0
P2L_HISTORY_REWRITTEN=false
HISTORICAL_PRIMARY_LATENCY_COMPONENT=load_duration
HIGH_LOAD_THRESHOLD_SECONDS=5.0
```

## 已确认事实

本报告的历史数值由 [p2l_historical_forensics.py](/home/yanbo/net_vlm_person_fallen_v2_optimization/tools/p2l_historical_forensics.py) 从 P2 C3 的 `raw_responses.jsonl` 与 `request_log.jsonl` 联结重算；没有从 `summary.md`、分类预测或 evidence 反推时延。每一行保留 Ollama 原始纳秒字段、HTTP 客户端时延、图像 SHA、处理后图像 SHA 和 448×336 几何审计结果。

| 数据集 | 请求数 | `load_duration > 5s` | client P50/P95 | Ollama total P50/P95 | load P50/P95 | prompt-eval P50/P95 | eval P50/P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SCREEN | 120 | 0 | 1.580912 / 1.814611 s | 1.572841 / 1.806169 s | 0.459518 / 0.505485 s | 0.120626 / 0.142331 s | 0.465114 / 0.640630 s |
| VAL | 100 | 63 | 14.682363 / 18.144259 s | 14.673721 / 18.136487 s | 13.324700 / 16.756087 s | 0.140699 / 0.167674 s | 0.493393 / 0.744843 s |

完整的 mean、median、P50、P90、P95、max 以及每个组件的 ratio 在 [duration_summary.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/01_historical_forensics/duration_summary.json)；例如 VAL 的 load mean/median/P90/max 为 `9.030091 / 13.324700 / 14.299246 / 19.819997s`，SCREEN 为 `0.455937 / 0.459518 / 0.488111 / 0.520834s`。VAL 的 load ratio median/P95 为 `0.895388 / 0.923384`，而 prompt-eval 和 eval 的 P95 只有 `0.167674s` 和 `0.744843s`。因此“历史异常的主要计时组件是 `load_duration`”是直接由分解数据支持的事实。

自动阈值-run 分析（阈值 `>5s`，按实际请求顺序计算，没有硬编码 64/65）得到：

```text
VAL runs = 1-20 HIGH, 21 LOW, 22-64 HIGH, 65-100 LOW
longest sustained HIGH = 22-64 (43 requests)
main recovery first LOW = request 65
transient LOW retained = request 21
```

主恢复转折前后的窗口：

| 窗口 | 数量 | load median | load P95 | total median | client median |
|---|---:|---:|---:|---:|---:|
| VAL 22–64 sustained HIGH | 43 | 13.762809 s | 16.633463 s | 15.200541 s | 15.209484 s |
| VAL 65–100 recovered LOW | 36 | 0.470802 s | 0.519604 s | 1.631841 s | 1.640880 s |

转折行、时间戳和相邻 request ID 在 [p2_val_change_points.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/01_historical_forensics/p2_val_change_points.csv)。关键行是 request 21 的 `HIGH_TO_LOW`、request 22 的 `LOW_TO_HIGH` 和 request 65 的 `HIGH_TO_LOW`。

## 配置、token 与相关性核对

SCREEN/VAL 的完整归一化配置指纹均为：

```text
872e7210a216c9d496b7930f0b9cf4cef059012ab7c9c4aea23138f3dc8086fe
```

两者使用相同的 qwen3.5:4b、C3 Prompt、`format=json`、`think=false`、`stream=false`、`temperature=0`、`num_ctx=8192`、`num_predict=256`；C3 Prompt SHA 为 `685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e`。`prompt_eval_count` 在 SCREEN/VAL 全部为 `598`，不是造成 VAL 长尾的变量。`eval_count` 会随输出长度变化，但与 load 的 Spearman 为 SCREEN `-0.038339`、VAL `-0.174355`，且 generation/eval duration 仍为亚秒量级。图像字节数与 load 的 Spearman 为 SCREEN `0.036989`、VAL `0.124548`；这是关联检查，不是因果证明。

## 风险与限制

历史 raw timing 证明了一个真实的、load-dominated 的 VAL 状态转折，但不能单独判定是模型 reload/residency、GPU contention、runner 生命周期、调度器还是其他远端运行时原因。对 `tiga@192.168.20.62` 的只读 SSH 在 preflight 阶段因 `Permission denied (publickey,password)` 失败，因此没有远端 GPU/VRAM 利用率、compute PID、Ollama PID、systemd 或 journal 证据。P2 历史结果没有被改写，VAL 仍是已暴露的 recovery evaluation，而不是 pristine holdout。

## 证据文件与哈希

```text
SCREEN raw SHA = f6e56030612e35c4065fe707054793701e875e9172c195d7783ba113a53bb5db
SCREEN request_log SHA = 4fa22a1a7cfd72145ad5db8e1bf879aeb7e3a2748560352e0414d420b2af33e0
VAL raw SHA = cd04ddd89328d7464856dafc8dd99c95eae1761fc7df19b6996ee3de2ad32b4a
VAL request_log SHA = 9b462e6b6b20a57d076b32b98c9b27700fc1fc14f229c63a66baff97ba4d084e
SCREEN/VAL source manifest SHA = ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5 / f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762
```

下一步是使用同一 exact-C3 配置执行 DEV-only controlled probes；不运行 VAL 或 HOLDOUT，不从历史错误驱动 Prompt 改动。
