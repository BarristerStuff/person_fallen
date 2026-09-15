# P4D GR3Q4 final preparation report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_GR3Q3_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q4_NAME=P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN
P4D_GR3Q4_REVISION=P4D_GR3Q4_ADAPTIVE_QUOTA_WINDOW_CAMPAIGN_20260828_03
P4D_GR3Q4_STATUS=WAITING_FOR_PROVIDER_QUOTA_RESET
P4D_GR3Q4_EXECUTION_NOT_EXECUTED=true
P4D_STATUS=GENERATION_REQUIRED

STARTING_VERIFIED_SUCCESS=102
STARTING_OUTSTANDING=338
PARTIAL_GROUP_COUNT=1
ADAPTIVE_ORDER_SHA256=acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033

WINDOW_LOGICAL_CAP=68
LATER_WINDOW_DEFAULT_CAP=70
PHYSICAL_ATTEMPT_LOWER_BOUND_CAP=80
NATIVE_RETRY_EVENT_CAP=5

PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
ACTIVE_PROFILE_STRATUM=PROFILE_A_RESTORED
PROFILE_FINGERPRINT_SAFE_HASH=ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe

AUTHORIZATION_PRESENT=false
TIME_GATE_PASS=false
EXECUTION_ELIGIBLE=false

LOGICAL_INVOCATIONS=0
LOGICAL_SUCCESSES=0
LOGICAL_FAILURES=0
NATIVE_RETRY_SCHEDULED_EVENTS=0
OBSERVED_PHYSICAL_ATTEMPT_LOWER_BOUND=0
HTTP_429=0
HTTP_401=0
HTTP_403=0
TIMEOUTS=0
HTTP_5XX=0

CURRENT_TOTAL_SUCCESS=102
CURRENT_OUTSTANDING=338
PROVIDER_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false

FULL_440_QA=NOT_REACHED
SEMANTIC_SENTINEL=NOT_EXECUTED
SEMANTIC_REVIEW=NOT_REACHED
FORMAL_INGEST=false
C3=false
NEW_VAL=0
P4D_VALIDATED_GENERATION_BASELINE=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_MODIFIED=false
```

## 已确认事实

本次完成的是零请求的 GR3Q4 preparation，不是生成窗口执行。父级 Q2E canonical freeze SHA-256 为 `9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44`，GR3Q3 terminal freeze SHA-256 为 `7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697`；两者及其 bound artifacts 均只读核对通过。冻结 440 manifest SHA-256 为 `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`，440/440 prompt bytes、440 IDs、88 groups、cross-split=0 通过。

当前 inventory 由实际文件和父级 ledgers 重新建立：GR3E Profile-A=99、GR3Q2E Profile-B=3，共 102 个 verified success；raw/final 各 102 个，Pillow、SHA、1920x1080、symlink/samefile 检查均通过。GR1 hash/samefile/symlink reuse=0。338 outstanding 为 confirmed HTTP 429=1、never started=337、completion unknown=0；角色为 hard_negative=198、positive=100、ordinary_negative=40，planned split 为 NEW_DESIGN=195、NEW_SCREEN=143。

唯一 partial group 是 `PF_P4D_HN_KNEEL_G009`（2 success + 3 outstanding），confirmed-429 的 `PF_P4D_HN_KNEEL_G009_V03` 已排在首位。完整 adaptive order 为 338 行/338 unique IDs，首窗口计划为 68 行、14 groups（partial 3 slots + 13 个完整 groups），首窗口角色 hard_negative=23、positive=35、ordinary_negative=10，planned split NEW_DESIGN=30、NEW_SCREEN=38。首窗口计划不是已发出的请求。

本次只读 runtime audit 得到 provider=`codex`、model=`gpt-5.4`、backend=`image_generation`、runtime=`0.7.3`、auth ready、endpoint reachable、TLS true，native max retries=3、outer retry=false；wrapper/binary hash 与预注册值一致。当前安全 profile fingerprint 是历史 Profile-A (`ab7f...caffe`)，不是 Q2E Profile-B (`d80e...c190`)；记录为 `PROFILE_A_RESTORED`，没有错误改标。

时间 gate 证据为 reset `2026-08-28T18:49:07+08:00`、安全门 `2026-08-28T19:00:00+08:00`；捕获时本地时间 `2026-08-28T16:00:31.393314+08:00`，因此 `TIME_GATE_PASS=false`。当前 campaign packet 的 `authorized=false`、`explicit_campaign_authorization=false`、`template_is_authorization=false`；没有 attestation、图片、raw response 或请求日志。

首窗口 durable 工件已经建立：68 行 ledger 全部 `NOT_STARTED`；SQLite 在 stable close 后为 WAL、synchronous=FULL，68 rows、1 个初始化 event，WAL/SHM 已清理；request/raw logs 都是空文件（SHA-256=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`）。terminal freeze `all_bound_artifacts_match=true`、sidecar 匹配、37 个 bound artifacts、provider_requests=0。

共享数据集 validator 最终只读结果为 `status=valid`、`error_count=0`、`full_hash_check=true`、`warning_count=387`；counts `media=5081, labels=4881, batches=45, splits=2618`，before/after annotation hashes 一致、active P4D references=0。没有正式 ingest、C3、NEW_VAL、HOLDOUT，也没有写 shared split CSV、production code 或 Ollama。

## 实验判断

GR3Q4 已达到“固定 campaign policy + adaptive balanced order + bounded quota window + independent freeze”的准备目标，但尚未产生任何 provider 输出，不能称为 generation result 或新的 semantic baseline。当前最终阻塞是 time gate；即使安全时间已到，没有 standalone authorization 仍不能执行。

`CURRENT_TOTAL_SUCCESS=102`、`CURRENT_OUTSTANDING=338` 是当前 generation 状态，不是本窗口结果。逻辑调用、物理尝试、retry events、429/401/403/timeout/5xx 均为本 revision 的 0；历史 Q2E 的 1 个 confirmed 429 被保留在 outstanding 证据中，未被伪装为本次请求。

没有执行 full 440 QA、semantic sentinel 或分类评估，因此 `P4D_VALIDATED_GENERATION_BASELINE=false`。只有 440 张都实际完整性验证通过，才允许进入完整 mechanical/duplicate/lineage QA 和人审门槛；不会自动进入 C3、VAL 或 HOLDOUT。

## 风险与限制

- provider quota reset 不是配额保证，19:00 是加入安全 margin 的最早可执行时间；不得 sleep、后台等待或 cron 自动恢复。
- campaign authorization packet 是模板和治理记录，不是授权。真正授权需要新的独立顶层消息，且每个窗口仍必须人工启动、独立 freeze。
- 68/70 logical caps、physical lower-bound=80、retry-event=5 是风险控制，不是账单；理论最多尝试与实际 provider attempts 必须分开。
- 当前 Profile-A restored 与历史 Profile-B 的 provenance 分层会继续存在；若未来运行时出现既非 A 也非 B 的 fingerprint，必须暂停等待 profile-stratum 决策。
- `images generate --help` 的只读调用返回 CLI invalid_command/returncode=2，虽然 config/doctor/auth 成功，但不应把 help 输出当作生成能力的实测证明。
- 由于本轮没有请求，latency、成本、图片质量、semantic review、分类 TP/FP/TN/FN 和任何 accuracy 指标均为 N/A，不得填写 0 以外的虚构数值。
- 本次准备脚本的一次性 stdout 摘要把 `first_window` 字典的键数打印成了 `first_window_plan_rows=9`；这只是显示层 bug，没有写入任何持久化工件。落盘的 `first_window_68_plan.csv`、`adaptive_order_summary.json`、terminal summary 及独立审计均验证 `planned_rows=68`。当前封存脚本不在本 revision 内原地修改，未来修正该 helper 必须建立新 revision。

## 下一阶段建议

等待用户在新独立顶层消息中明确接受 packet 范围后，手动启动一个全新的 window execution revision：先重读当前本机时间并确认 `>=19:00 +08:00`，再重跑 config/doctor/auth/help、profile、manifest、102/338 inventory 和 dataset boundary gate。只在所有 hash 和配置保持一致时使用已经冻结的 68-slot order；首 slot 是 `PF_P4D_HN_KNEEL_G009_V03`。任一规定 provider/transport/invalid-output 错误，或 physical/retry guard 触发，都应完成该 window 的 stable-close terminal freeze 并停止，禁止自动进入下一窗口。

本次没有生成 `reports/76_p4d_gr3q4_window_execution.md`，因为没有执行 window；后续只有真实窗口运行后才增加该报告。当前终态 freeze：[p4d_gr3q4_terminal_freeze.json](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_20260828_03/freeze/p4d_gr3q4_terminal_freeze.json)，SHA-256：

```text
8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2
```

### 关键工件哈希

| 工件 | SHA-256 |
|---|---|
| parent Q2E canonical freeze | `9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44` |
| parent GR3Q3 terminal freeze | `7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697` |
| frozen 440 manifest | `5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4` |
| current 102 inventory CSV | `c77d57e33da99add3744c03c9bfb5344b3b81d5c3b5a59a1481443ea6078831b` |
| outstanding 338 CSV | `22334fa342e5cfdf51e6e1dc92b26adbc690f1fff7a6521d1642cd5aed4f6e83` |
| adaptive order CSV | `acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033` |
| first-window 68 plan | `2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd` |
| provider runtime audit | `ee712f4a185b2c36b3c04a64470ca7eaece65147a1a6a8ec8d6119832bbb7236` |
| campaign authorization JSON | `a02fc2a3b691eb493328d21dd56f748027c8e41211dca2e133b8617c700cfe98` |
| window run config | `39909db6969a6cb4f2ad979faca70490f7be7b620f693173daa0970154f7fb68` |
| window ledger CSV | `404bcad2dd6a7ec359ec9847a6dde531ffdc5d4f9cad33d4d307ab0474ac5b2d` |
| window SQLite after stable close | `7688dc23ff4ba909a7bdd3049d9fa5cfd55d4e168a6576f8d8b6585f3a528557` |
| request log (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| raw-response log (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| terminal freeze | `8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2` |
| terminal freeze sidecar file | `dd44d8744d9ed1a5fa023633967bb9c52df7be477c070112cf2ba90bf6f1c6ca` |
| terminal freeze verification | `db33b7839f0b351b307048652a90ebb6a7184ea4bd1f7052fe1164dc642ed9f7` |
| preparation script (new runner not created) | `92f168fa66db54b63c8b251cc1f5759da3e7fd7f71b408833e23e49b9dd5d8ca` |
| GPT Image 2 wrapper | `f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe` |
| GPT Image 2 binary | `1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba` |

`NEW_RUNNER_SHA=N/A_NO_EXECUTION_RUNNER_CREATED`；上表的 preparation script SHA 只用于记录本地零请求准备脚本，不应被解释成已执行的 provider runner。
