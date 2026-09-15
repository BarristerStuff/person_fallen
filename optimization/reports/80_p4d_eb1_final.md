# P4D EB1 final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P4D_EB1_NAME=P4D_EB1_EBOND_FULL_REGENERATION
P4D_EB1_PROVIDER=ebond
P4D_EB1_GENERATION_REVISION=P4D_EBOND_FULLREGEN_20260828_01
P4D_EB1_STATUS=BLOCKED_PRIMARY_AUTH_NO_SECONDARY
P4D_EB1_NEW_GENERATION_LINEAGE=true

P4D_EB1_PROMPT_CHANGED=false
P4D_EB1_TAXONOMY_CHANGED=false
P4D_EB1_GROUP_CHANGED=false
P4D_EB1_SPLIT_CHANGED=false

FROZEN_440_MANIFEST_SHA256=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
EBOND_LINEAGE_REUSED_CODEX_IMAGES=0
GR1_IMAGES_REUSED=0

SCHEMA_VERIFIED=true
ACTIVE_EBOND_CREDENTIAL_SLOT=PRIMARY
SECONDARY_DISCOVERED=false

SMOKE_STATUS=FAIL_HTTP_401
RAMP1_STATUS=NOT_REACHED
RAMP2_STATUS=NOT_REACHED
LOGICAL_REQUESTS=1
SUCCESSFUL_REQUESTS=0
FAILED_CONFIRMED=1
COMPLETION_UNKNOWN=0
EBOND_OUTSTANDING=440

RAW_PROVIDER_RESPONSES=1
RAW_IMAGES=0
FINAL_IMAGES=0
FULL_440_MECHANICAL_QA=NOT_REACHED
P4D_IMAGES_ACCEPTED=0

HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
MEDIA_ADDED=0
LABELS_ADDED=0
C3=false
NEW_VAL=0
PRODUCTION_CODE_MODIFIED=false
```

## 已确认事实

1. P4D 440 design 与所有冻结依赖在 provider 请求前均通过 SHA-256 核对；balanced order 保持 group 连续，前 16 slots 覆盖 3 roles、4 taxonomies、NEW_DESIGN/NEW_SCREEN。
2. 历史 schema 证据支持 `POST https://api.ebondai.com/v1/images/generations`、`model=gpt-image-2`、`prompt`、`size=1536x1024`、`quality=medium`、响应 `data[0].b64_json`；本次请求未加入额外未验证字段。
3. 只有第一张正式 smoke 被发送：HTTP 401，body 为 `INVALID_API_KEY`；请求 id、raw body hash、safe request metadata、SQLite WAL ledger、terminal freeze 均已持久化。
4. 当前 EBOND lineage 没有任何成功图片，未产生 raw/final output；历史 Codex 102 与 GR1 192 均未复用。
5. dataset validator before/after 均为 `valid`、`error_count=0`、`full_hash_check=true`；本阶段没有 formal ingest、C3、NEW_VAL 或 HOLDOUT。

## 实验判断

本次 EB1 不是“440 full-regeneration 完成”，而是一个已封存的 credential/auth 阻断：`P4D_EB1_STATUS=BLOCKED_PRIMARY_AUTH_NO_SECONDARY`。由于 smoke gate 未通过，ramp、full generation、mechanical QA、human semantic review 与任何模型评测均不适用，分类指标统一为 `N/A`。

这次结果不支持关于 prompt、model、size、quality、semantic accuracy、image quality 或 EBOND quota 的正面/负面判断；它只支持“当前 PRIMARY credential 被 provider 拒绝且没有可安全取得的 SECONDARY”这一事实。

## 风险与限制

- 用户附件声明有两枚 key，但当前机器可验证 credential store 仅能取得 PRIMARY；不能把其他事件的 key 当作 SECONDARY，也不能在 sealed run 中猜测或轮换。
- provider 401 可能意味着 key 过期、撤销、环境/账户不匹配或 provider auth policy；准确原因超出本地证据。
- latency P50/P95（本次约 3.9235 秒）是 auth request latency，不是有效图像生成 latency。
- 439 个后续 slots 未发送（以非成功 slot 计的 outstanding=440） 不得由本次历史 Codex 图像补齐；任何恢复都必须新建独立 revision 并重新 preflight。

## 下一阶段建议

1. 在受控、不会把 secret 写入日志的 credential store 中修复/轮换 EBOND PRIMARY，或让 SECONDARY 以同等安全方式可被 runner 读取；不要把 key 粘贴到报告或 shell。
2. 建立新的 `P4D_EB1_*_AUTH_RECOVERY` revision，重新绑定相同 frozen 440 assets、prompt hashes、group/split、schema、one-shot/no-retry runner 和新的 credential safe fingerprint；本 terminal freeze 不可重写。
3. 新 revision 只从 smoke 开始；只有 smoke 2xx + valid `b64_json` + Pillow conversion PASS 才能进入 ramp1/ramp2/full 440。
4. 维持 `P4D_IMAGES_ACCEPTED=0`、`FORMAL_INGEST=false`、`C3=false`、`NEW_VAL=0`、`HOLDOUT_REQUESTS=0`，直到后续独立 revision 通过完整 mechanical QA 与 human review。

## Evidence paths

- Preflight: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/freeze/p4d_eb1_preflight_freeze.json`
- Terminal: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/freeze/p4d_eb1_terminal_freeze.json`
- Runner: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/tools/ebond_one_shot_runner.py`
- Ledger SQLite: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/ledger/p4d_eb1_execution.sqlite3`
- Ledger CSV: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/ledger/execution_ledger.csv`
- Request log: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/execution/request_log.jsonl`
- Raw provider response: `/home/yanbo/下载/batches/batch-person-fallen-v2-p4d-ebond-fullregen-r1-camera1p5m/metadata/raw_provider_responses/P4D_EB1_0001_PF_P4D_HN_SIT_G001_V01.json`
- Dataset validator after: `/home/yanbo/net_vlm_person_fallen_v2_optimization/09_p4d_eb1_ebond_full_regeneration/config/dataset_validator_after.json`
