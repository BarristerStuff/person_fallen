# P2L controlled DEV probes

## Status

```text
STAGE=P2L_REMOTE_LATENCY_FORENSICS
PROTOCOL_SOURCE=response_only
PROMPT_CHANGED=false
PREPROCESS_CHANGED=false
FORMAT=json
THINK=false
CONCURRENCY=1
AUTOMATIC_RETRY=false
P2L_NEW_VAL_REQUESTS=0
P2L_HOLDOUT_REQUESTS=0
```

### Probe design

- Probe A: one fixed, verified DEV/P2_DESIGN image (`IMG_003745`) repeated 24 times; exact P2 C3 request configuration; no explicit `keep_alive`.
- Probe B: the same image and 24-request sequence; the only request-level difference is the top-level `keep_alive: "30m"`, whose placement was supported by read-only local/project source evidence. `keep_alive=0` was not used.
- Probe C: 16 unique DEV/P2_DESIGN images (4 positive, 4 negative, 8 hard-negative, 15 groups), exact P2 C3 configuration, no explicit keep-alive.

All requests were direct to `http://192.168.20.62:11434/api/generate`; no SSH tunnel, `127.0.0.1:11444`, service restart, unload, or remote write was used. Every request has a durable ledger row, raw response wrapper, request log, image SHA and protocol prediction row.

## 协议结果

| Probe | Requests | HTTP 200 | response non-empty | thinking present | JSON | schema | canonical |
|---|---:|---:|---:|---:|---:|---:|---:|
| A exact C3 | 24 | 24/24 (1.0) | 24/24 (1.0) | 0/24 (0.0) | 24/24 (1.0) | 24/24 (1.0) | 24/24 (1.0) |
| B `keep_alive=30m` | 24 | 24/24 (1.0) | 24/24 (1.0) | 0/24 (0.0) | 24/24 (1.0) | 24/24 (1.0) | 24/24 (1.0) |
| C diverse | 16 | 16/16 (1.0) | 16/16 (1.0) | 0/16 (0.0) | 16/16 (1.0) | 16/16 (1.0) | 16/16 (1.0) |

正式分类答案全部来自 `response`；任何 `thinking` 字段都没有被用作 fallback。A/B/C 都没有 protocol failure。

## 组件与客户端时延

单位均为秒；P50/P95 使用逐请求 Ollama 原始 duration 纳秒换算，client 是本地 HTTP 计时。完整 mean、median、P90、max 以及 ratio 在 [latency_components.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/latency_components.csv)。

| Probe | client P50/P95/max | total P50/P95/max | load P50/P95/max | prompt-eval P50/P95/max | eval P50/P95/max | load>5s |
|---|---:|---:|---:|---:|---:|---:|
| A (24) | 1.418261 / 1.518300 / 8.285873 | 1.411415 / 1.511117 / 8.280188 | 0.473133 / 0.503247 / 6.985410 | 0.036960 / 0.056823 / 0.135522 | 0.440649 / 0.450214 / 0.454359 | 1 |
| B (24) | 1.396662 / 1.440333 / 1.447384 | 1.390041 / 1.433131 / 1.439994 | 0.466865 / 0.498783 / 0.508403 | 0.036895 / 0.053363 / 0.055483 | 0.437948 / 0.447719 / 0.450200 | 0 |
| C (16) | 1.717896 / 1.826522 / 1.910301 | 1.710288 / 1.818961 / 1.902707 | 0.453339 / 0.530351 / 0.554933 | 0.131057 / 0.144843 / 0.154303 | 0.529636 / 0.659936 / 0.719613 | 0 |

Probe A 的第 1 条（固定图 `IMG_003745`）是唯一正式 A 的 high-load 行：client `8.285873s`、total `8.280188171s`、load `6.985410339s`；第 2–24 条全部低于 5s。固定图随后稳定、C 的多图序列也稳定，说明本次没有复现历史 VAL 的 43 条 sustained high-load 状态。Probe B 的 `keep_alive=30m` 序列没有 high-load 行，但由于 B 紧接 A 执行，不能把 A→B 差异当成随机化因果证明。

当前 exact-C3 warm 集合定义为 A 的低 load 行（第 2–24 条）加 C 的 16 条，共 39 条：client P50 `1.450764s`、P95 `1.796366s`、max `1.910301s`，低于历史开发门槛 `1.852084s`（这是运行时观测 gate，不改变 P2 已冻结的质量结论）。

`prompt_eval_count` 在 A/B/C 均稳定为 `[598]`。A/B 固定图片的 image-byte 相关性无定义（字节数恒定）；C 的 eval_count-load Spearman `0.075111`、image-bytes-load Spearman `0.232353`，样本很小且没有 high-load 行，只能作为非因果辅助检查。

## `/api/ps` 与远端遥测

只读 `/api/ps` 快照观察到：正式 A 开始前 `models=[]`，A 中点/结束加载 `qwen3.5:4b`；B、C 开始前和结束时均保持已加载。快照中的模型 digest 为 `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`，`size_vram=6088300544`，`context_length=8192`。最终 `/api/ps` 仍显示该模型已加载。快照只是状态采样，不等价于完整服务日志。

SSH 只读认证在 preflight 和每次快照均失败：`tiga@192.168.20.62: Permission denied (publickey,password)`。因此 GPU utilization/VRAM 时间序列、compute-process PID、Ollama PID/runner PID、systemd 状态和 journal 均为 unavailable；没有伪造这些字段。外部 1 秒遥测未能建立，保留为明确限制。

## 证据路径与哈希

```text
P2L runner SHA = 5061817f87882f8137229d2a5d7011c3da5cfe5fabde7fb6161a5ddbeaefde00
P2L analysis SHA = dd8d50a81bdc82df40b28a7f026fa38f7c8f96e940c69e8c47ead8a20d6fb7a5
Prompt SHA = 685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e
request config SHA = 8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d
fixed manifest SHA = 102bb4aeb9db7c8861789499d96c71f52b1af57d37bfa4eb48748ce37978acc1
diverse manifest SHA = e9f2d8b9cc9df254ebd4d6692a40c8e8caaf652be794cb40cf56fd53d66970e2
Probe A raw/log/predictions = 654c84b75ade5801e8eeb7d3980f799f23d5f1a2b34cb41ce5bdcf26f107d788 / df48820d2bd53341a1ebbcb1ba3c4e758840f1a9349f8a919b7f5636f925be51 / 33eb9e10fae21eae0142c51b1f129ffee6f07dc28d646601380c265f2fec53ce
Probe B raw/log/predictions = a382571bf01ef12eff84569d6d194e6d1517abaee204090b87f3d228387fe0c5 / b1331101bfbf6a7afb7531dfc0df3e63f92c30234b3a03b93c769fbe59c72a7c / aa5be83ef9835f2d5ddad27355e9eda9ae2834397cae8c33764e0b7ef382e302
Probe C raw/log/predictions = e75201f241e0f357de0bf19b84ef5c106a751e1fe6dabab8fc93570c39995e7c / a646a096d73fa192ce8d862a276e548245eaf8c0b08fbbd086cce66060f6b612 / 49bc08e3f0f10be7218f9cffc6bbe0ae1441f992a0862d887082fda2713ce0be
```

一次实现缺陷导致的首个 1-request 尝试没有被删除，保存在 [04_probe_A_exact_c3_attempt_001](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/04_probe_A_exact_c3_attempt_001)；它不是正式 Probe A，不进入上表统计。正式 A/B/C 共 64 次 DEV 请求；连同该保留尝试，P2L 阶段实际新 DEV 请求总数为 65。
