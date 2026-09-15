# P4D EB1 generation execution

| 项目 | 实际值 |
|---|---|
| logical_slots_planned | 440 |
| logical_requests_sent | 1 |
| successful_requests | 0 |
| failed_confirmed | 1 |
| completion_unknown | 0 |
| pending_outstanding | 440 |
| HTTP_2xx | 0 |
| HTTP_401 | 1 |
| HTTP_403 | 0 |
| HTTP_429 | 0 |
| HTTP_5xx | 0 |
| timeout | 0 |
| raw_provider_responses | 1 |
| raw_images | 0 |
| final_images | 0 |
| smoke | FAIL: 0/1 image success; HTTP 401 INVALID_API_KEY |
| ramp1 | NOT_REACHED |
| ramp2 | NOT_REACHED |
| client_http_library | urllib.request with NoRedirect opener |
| client_retry_total | 0 |
| logical_retry | false |
| provider_wrapper_retry | 0 |
| client_http_generation_attempts_total | 1 |
| concurrency | 1 |
| latency_p50_seconds | 3.9235 |
| latency_p95_seconds | 3.9235 |

## 已确认事实

- 仅发送 1 个 logical request：`P4D_EB1_0001 / PF_P4D_HN_SIT_G001_V01`；`attempt_count=1`，HTTP library 是无 retry、禁 redirect 的 `urllib.request`。
- 响应 raw body 为 JSON `INVALID_API_KEY`，provider request id 与 raw response SHA 已落盘；未产生 raw/final image。
- smoke FAIL 后没有进入 ramp1/ramp2，也没有发送后续 439 slots。

## 实验判断

本 revision 的停止是 fail-closed 且可审计的：`logical_requests=1`、`successful=0`、`failed_confirmed=1`、`completion_unknown=0`、`outstanding=440`。不能宣称 440 generation 或 generation stability。

## 风险与限制

401 只证明本次 PRIMARY credential 被 provider 拒绝；它不证明模型、prompt、native size 或历史 schema 语义失败。延迟 P50/P95 仅是这次 auth transport latency，不能称图像生成 latency。

## 下一阶段建议

修复 credential 后必须建立新的、独立封存的 auth-recovery revision；保持 one-shot/no-retry 规则，并在新 revision 中重新做 smoke。
