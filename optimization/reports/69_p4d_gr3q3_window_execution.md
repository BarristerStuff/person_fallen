# P4D GR3Q3 quota-window execution record

```text
P4D_GR3Q3_NAME=P4D_GR3Q3_QUOTA_WINDOW_RECOVERY
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
EXECUTION_NOT_EXECUTED=true
PROVIDER_REQUESTS=0
PHYSICAL_ATTEMPTS=0
WINDOW_CAP=90
WINDOW_CAP_REACHED=false
```

## 已确认事实

本 revision 只完成 preparation，不是 provider execution。新目录 [quota_window_recovery_20260828_02](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02) 中：

- [run_config.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/02_runner/run_config.json) 固定 provider `codex`、request model `gpt-5.4`、backend `image_generation`、runtime `0.7.3`、native size `1536x1024`、quality `medium`、format `png`、受控 crop/Pillow LANCZOS 到 `1920x1080`、`concurrency=1`、`outer_retry=false`、native max retries=3；与父 Q2E 的可观察 generation configuration 全部匹配。
- [quota_window_ledger.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/03_ledger/quota_window_ledger.csv) 有 338 行，全部 `NOT_STARTED`；SHA-256 `108e7ff3888f12316107d7be1705717af2145e7a348ed98cbafaf4ace81e13d0`。
- [quota_window_execution.sqlite3](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/03_ledger/quota_window_execution.sqlite3) 已在 `WAL` + `synchronous=FULL` 下创建并 checkpoint/truncate 后关闭；338 行均为 `NOT_STARTED`，SHA-256 `6397a1726e9762443b2b71ce8917706fff9641925660af1717a068f46f84fbf3`。
- [request_log.jsonl](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/02_runner/request_log.jsonl) 与 [raw_responses.jsonl](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/04_raw_responses/raw_responses.jsonl) 均为 0 bytes、0 lines；两者 SHA-256 均为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [new_image_hash_manifest.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/06_full_qa/new_image_hash_manifest.json) 明确为 `NOT_EXECUTED`，raw/final count 均为 0；新 quota window 没有图像输出。

只读 capability audit 使用了 `config inspect`、`doctor`、`auth inspect` 和 `images generate --help`，没有使用 `images generate`。观察到：`resolved_provider=codex`、`AUTH_READY=true`、endpoint reachable、TLS 可用、runtime `0.7.3`、wrapper SHA `f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe`、binary SHA `1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba`。配置文件的全局 default provider 仍显示 `ebond-gpt-image-2`，但本次所有诊断都显式选择并解析为 `codex`；由于没有生成调用，这没有产生 provider side effect。

当前 audit 计算出的 safe profile fingerprint 是 `ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe`，与历史 GR3E Profile-A 相同，而与 Q2E Profile-B `d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190` 不同。此事实已保留在 [provider_runtime_audit.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/00_preflight/provider_runtime_audit.json)，没有把它伪装成 Q2E Profile-B，也没有因此擅自重生 102 张图。

## 实验判断

`AUTH_READY` 只表示本机诊断发现可用 session，不等于本轮有执行授权。当前 [window_authorization_status.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_window_recovery_20260828_02/01_authorization/window_authorization_status.json) 是 `explicit_window_authorization=false`、`authorization_present=false`。此外当前时间早于 19:00，所以最终状态优先为 `WAITING_FOR_PROVIDER_QUOTA_RESET`；没有跑 smoke slot，也没有跑 full 90-slot window。

## 风险与限制

这是 protocol/config/ledger preparation，不是生成基线；semantic metrics、full 440 QA、human review、formal ingest、C3、VAL、NEW_VAL 和 HOLDOUT 均为 `N/A`/`NOT_REACHED`。将来执行必须在新的顶层授权后重新确认时间、profile provenance 和 runtime identity，并重新绑定新的 request/raw/image hash 日志。

