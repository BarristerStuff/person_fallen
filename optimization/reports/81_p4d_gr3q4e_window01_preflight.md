# P4D GR3Q4E Window 01 preflight

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR3Q4E_NAME=P4D_GR3Q4E_ADAPTIVE_QUOTA_CAMPAIGN_WINDOW_01
P4D_GR3Q4E_REVISION=P4D_GR3Q4E_WINDOW_01_EXECUTION_20260830_01
P4D_GR3Q4E_STATUS=AWAITING_CAMPAIGN_AUTHORIZATION
PROVIDER_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
STARTING_VERIFIED_SUCCESS=102
STARTING_OUTSTANDING=338
FAILED_CONFIRMED_HTTP_429=1
NEVER_STARTED=337
COMPLETION_UNKNOWN=0
PARENT_GR3Q4_FREEZE_SHA256=8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2
PARENT_Q2E_FREEZE_SHA256=9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44
PARENT_GR3Q3_FREEZE_SHA256=7191dc15e3425f980b028863d5712a3161dccfa4e7f23f6770745d9d18cbf697
FROZEN_440_MANIFEST_SHA256=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
ADAPTIVE_ORDER_SHA256=acb4abca77c2c1a4c08d4028b3ce95a0dff503ffb68e5995e9fecae9d8749033
FIRST_WINDOW_68_PLAN_SHA256=2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd
PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
ACTIVE_PROFILE_STRATUM=PROFILE_A_RESTORED
PROFILE_FINGERPRINT_SAFE_HASH=ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe
MATERIAL_CONFIG_MATCH=True
HISTORICAL_TIME_GATE_BLOCKING=False
CURRENT_TIME_GATE_PASS=True
EXPLICIT_CAMPAIGN_AUTHORIZATION=false
EXECUTION_ELIGIBLE=false
```

## 已确认事实

父级 GR3Q4、Q2E、GR3Q3 terminal freeze 的 SHA、sidecar 和 bound artifacts 均通过独立只读核验。冻结 440-slot manifest 通过 hash、440 rows、440 unique prompt IDs、88 groups、cross-split=0、prompt byte mismatch=0；角色与 NEW_DESIGN/NEW_SCREEN 分布保持冻结值。

当前 inventory 从 GR3E/Q2E ledgers、实际 raw/final 文件和 Pillow 校验重建为 102 张：Profile-A=99、Profile-B=3，全部通过 SHA、Pillow、1920x1080、symlink/samefile 检查。GR1 排除检查为 SHA/samefile/symlink=0。

## 实验判断

实时日期已超过历史 quota reset 安全时间，因此历史 time gate 不再阻塞本窗口。当前顶层消息没有本窗口所需的等价 campaign authorization；任务正文明确规定其模板不构成授权，所以执行资格为 false，provider 请求必须为 0。

## 风险与限制

auth/session ready 不是用户授权；不能把先前 Q2E 或 EBOND 的授权沿用到 GR3Q4E。runtime audit 只保存脱敏结果；本轮没有调用 EBOND endpoint，也没有持久化或读取其 credential secret。

## 下一阶段建议

由用户在新的独立顶层消息明确授权本窗口范围后，重新验证本 revision 的 parent/hash/profile/config gate，并人工启动新的 execution revision；不得把本零请求 freeze 改造成可执行或自动恢复的窗口。
