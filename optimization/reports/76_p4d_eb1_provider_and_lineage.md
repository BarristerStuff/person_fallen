# P4D EB1 provider and lineage

| 项目 | 实际值 |
|---|---|
| P4D_EB1_STATUS | BLOCKED_PRIMARY_AUTH_NO_SECONDARY |
| P4D_EB1_NAME | P4D_EB1_EBOND_FULL_REGENERATION |
| P4D_EB1_GENERATION_REVISION | P4D_EBOND_FULLREGEN_20260828_01 |
| PROVIDER | EBOND |
| MODEL | gpt-image-2 |
| API_SCHEMA | POST /v1/images/generations; data[0].b64_json |
| API_SCHEMA_SOURCE | /home/yanbo/.local/share/Trash/files/image.2/archive/api-capability-tests-20260731/ebondai-direct-1920x1080-result.json; local gpt-image-2 providers.md |
| API_HOST | api.ebondai.com |
| ACTIVE_CREDENTIAL_SLOT | PRIMARY (safe fingerprint only) |
| SECONDARY_DISCOVERED | false |
| CREDENTIAL_FINGERPRINT_SHA256 | 43d31d860533665709eb74ab30e6643ae2addd79d71156940e517c75db44873f |
| HISTORICAL_CODEX_GENERATION_ASSETS | true; EBOND_LINEAGE_REUSED_CODEX_IMAGES=0 |
| GR1_IMAGES_REUSED | 0 |
| FROZEN_MANIFEST_SHA256 | 5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4 |
| RUNNER_SHA256 | 1131bc96261751670b816faa2d5e20a03b1b33357751a2f18e2849671fa145db |
| PREFLIGHT_FREEZE_SHA256 | b9efdb90c9cf2b326e24a7565de5b109501908e904122f41c330e01b2848b1b5 |
| TERMINAL_FREEZE_SHA256 | ecb7bc9498f5c2184dab0fc1f1ed112dff13f7dfac9b316322af53e3dd233bb0 |

## 已确认事实

- Frozen 440 manifest、group/split freeze、prompt pack、C3 prompt 均在 preflight 按指定 SHA-256 复核；`PROMPT_CHANGED=false`、`TAXONOMY_CHANGED=false`、`GROUP_CHANGED=false`、`SPLIT_CHANGED=false`。
- EBOND schema 来自本机历史成功 direct capability 结果与本地 `gpt-image-2-skill` provider reference；本次未猜测 endpoint 或增加未验证字段。
- 新 batch 与历史 Codex/GR1 lineage 分离，Codex historical assets 仅作诊断，实际复用为 0。

## 实验判断

- 由于 PRIMARY 的正式第一张 smoke 返回 HTTP 401 且 `INVALID_API_KEY`，在没有可安全取得的 SECONDARY 的前提下，预注册的 auth gate 触发；这次 EBOND lineage 没有形成图像。
- 这是 credential/auth blocker，不是 semantic 失败、quota 结论或图像质量结论。

## 风险与限制

- 当前可验证的配置 store 只暴露一枚 PRIMARY 的安全指纹；附件所述第二枚 key 在本机当前上下文不可发现，其他事件的 key 被明确排除。不能据此推断 SECONDARY 是否有效。
- provider 401 的 body、request id 和 hash 已保留，但 Authorization header/key 没有写入任何 artifact。

## 下一阶段建议

- 先由用户在受控 credential store 中修复/轮换 EBOND PRIMARY，或明确提供可安全读取的 SECONDARY credential store；然后创建新的 EB1 auth-recovery revision，而不是改写本次 terminal freeze。
- 不要在本 sealed run 上重试、切换到其他事件 key、混入 Codex 102、执行 ingest/C3/VAL/HOLDOUT。
