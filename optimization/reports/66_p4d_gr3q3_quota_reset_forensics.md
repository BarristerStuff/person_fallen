# P4D GR3Q3 quota-reset forensics

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR3Q3_NAME=P4D_GR3Q3_QUOTA_WINDOW_RECOVERY
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
PROVIDER_REQUESTS=0
EXPLICIT_WINDOW_AUTHORIZATION=false
TIME_GATE_PASS=false
```

## 已确认事实

本报告是新的 `quota_window_recovery_20260828_02` 准备 revision 的配额取证，未调用图像生成。父 Q2E 的 canonical terminal freeze 在只读复核中通过：

- freeze SHA-256：`9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44`；sidecar 相同。
- 父 freeze 状态：`P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY`；17/17 已绑定 artifact 一致。
- 父失败 raw evidence：`P4D_GR3Q2E_RECOVERY_0004_PF_P4D_HN_KNEEL_G009_V03.json`，SHA-256 `a21d6034962800409ef117e7f01435b11d1dd328671ccfba2282be5b66963e99`。
- 父失败 HTTP 状态为 429，`error_code=http_error`，provider detail 的 `type=usage_limit_reached`，message 为 “The usage limit has been reached”。
- provider 报告的 `resets_at=1787914147`，即 `2026-08-28T10:49:07+00:00` / `2026-08-28T18:49:07+08:00`；`resets_in_seconds=15278`。

按预注册的 653 秒安全 margin，新的最早执行时刻为：

```text
NOT_BEFORE_UTC=2026-08-28T11:00:00+00:00
NOT_BEFORE_LOCAL=2026-08-28T19:00:00+08:00
```

本轮在 `2026-08-28T15:15:27.177+08:00`（`2026-08-28T07:15:27.177+00:00`）捕获本机时间，`TIME_GATE_PASS=false`。因此按规则状态为 `WAITING_FOR_PROVIDER_QUOTA_RESET`，不是等待中后台任务；没有 sleep、cron、后台 runner 或自动恢复。

配额证据原件、解析结果和时间 gate 位于：

- [quota_reset_evidence.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/00_preflight/quota_reset_evidence.json)
- [time_gate.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/00_preflight/time_gate.json)
- [q2e_parent_freeze_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/00_preflight/q2e_parent_freeze_audit.json)

## 实验判断

`usage_limit_reached` 的 reset timestamp 是父 Q2E raw response 中的直接 provider evidence；它不是对未来配额可用性的永久保证。加 margin 后的 19:00 gate 只是本 revision 允许发请求的最早时间，不能替代新的 standalone GR3Q3 authorization，也不能保证第一 slot 不再收到 429。

当前仍只有准备资格：冻结面、库存、outstanding 状态和运行时配置可以被复核，但没有 execution eligibility。时间门槛通过后仍必须重新走 authorization gate 和 provider/runtime gate。

## 风险与限制

- 该错误证据只证明父 Q2E 当时触发了 usage limit；provider 可能在 reset 后继续返回 429，或出现 401/403/timeout/5xx/connection error。
- 只读 runtime audit 的当前账户/profile 安全指纹与历史 GR3E Profile-A 一致，而非 Q2E Profile-B；这属于 provenance 观察，不能据此假设 provider 侧分布完全相同，也不能把它当作已执行授权。
- 精确费用未知。即使未来获得授权，一个 window 也最多执行 90 个 logical slots，且单 logical invocation 允许 runtime 内部最多约 4 次 provider attempts。

