# 65 — P4D GR3Q2E profile-stratified recovery final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P4D_GR3Q2E_NAME=P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY
P4D_GR3Q2E_STATUS=STOPPED_BY_FAILURE_POLICY
P4D_GR3Q2E_CHANGE=PROFILE_STRATIFICATION_ONLY
P4D_GR3Q2E_PROMPT_CHANGED=false
P4D_GR3Q2E_GENERATION_CONFIG_CHANGED=false

PRESERVED_PROFILE_A=99
PROFILE_B_LOGICAL_INVOCATIONS=4
PROFILE_B_SUCCESS=3
PROFILE_B_FAILED_CONFIRMED=1
PROFILE_B_NOT_STARTED=337
COMPLETION_UNKNOWN=0
FULL_341_RECOVERY_COMPLETE=false
P4D_VALIDATED_GENERATION_BASELINE=false

PROVIDER=codex
REQUEST_MODEL=gpt-5.4
GENERATION_BACKEND=image_generation
RUNTIME_VERSION=0.7.3
NATIVE_MAX_RETRIES=3
OUTER_RETRY=false
PHYSICAL_PROVIDER_ATTEMPTS_OBSERVED=7

GLOBAL_STOP=true
STOP_REASON=HTTP_429
STOP_PROMPT_ID=PF_P4D_HN_KNEEL_G009_V03
STOP_RECOVERY_ORDER=4

FORMAL_INGEST=false
C3=false
NEW_VAL=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P4D_ACTIVE_DATASET_HITS=0
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false
AUTOMATIC_RECOVERY_AFTER_FAILURE=false
EXACT_MONETARY_COST=UNKNOWN
```

## 已确认事实

### 1. Scope and authorization

The execution was a new `P4D_GR3Q2E_PROFILE_STRATIFIED_RECOVERY_20260828_01`
revision under the exact standalone authorization recorded in
`01_authorization/recovery_authorization_attestation.json`. The authorization
permitted preservation of the 99 integrity-verified GR3E images as historical
Profile-A, use of the current Codex profile as Profile-B, at most 341 new
logical slot invocations, native runtime retries up to 3, and immediate global
stop when any logical invocation returned 429/401/403/timeout/5xx. No outer
automatic retry was enabled.

The preflight gate passed all seven checks (parent freezes, authorization,
manifest, batch/inventory, runtime, dataset validity, and no active-dataset
P4D references) before the first provider request. The frozen 440-slot prompt
manifest remained byte/hash matched (`5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4`),
and the immutable parent freezes were rechecked. The Q2 policy amendment was
used as a provenance stratification rule: Profile-A and Profile-B have
different safe profile fingerprints, while provider/model/backend/runtime and
the frozen prompt/configuration remained matched.

### 2. Actual logical execution and fail-closed stop

The runner issued exactly four Profile-B logical invocations in frozen recovery
order. All four were `hard_negative`, taxonomy `kneeling_half_kneeling`, and
planned split `NEW_SCREEN`.

| Recovery order | Prompt ID | Parent state | Result | HTTP | Native retries | Latency (s) | Image pair |
|---:|---|---|---|---:|---:|---:|---|
| 1 | `PF_P4D_HN_KNEEL_G008_V05` | `FAILED_CONFIRMED` (historical 429) | `SUCCESS_PROFILE_B` | 200 | 0 | 37.7138902510 | raw + final |
| 2 | `PF_P4D_HN_KNEEL_G009_V01` | `NEVER_STARTED` | `SUCCESS_PROFILE_B` | 200 | 0 | 40.9335045140 | raw + final |
| 3 | `PF_P4D_HN_KNEEL_G009_V02` | `NEVER_STARTED` | `SUCCESS_PROFILE_B` | 200 | 0 | 37.2069907620 | raw + final |
| 4 | `PF_P4D_HN_KNEEL_G009_V03` | `NEVER_STARTED` | `FAILED_CONFIRMED_PROFILE_B` | 429 | 3 | 12.7270571940 | none |

The fourth logical invocation returned an outer error with HTTP 429 and a
redacted provider detail of `usage_limit_reached`. The runtime performed its
pre-authorized three native retries; after the terminal 429 the runner wrote
`05_checkpoints/global_stop.json` and did not start order 5 or any later slot.
The observed physical attempt count is 7: one attempt for each of the three
successful invocations and four attempts (initial plus three retries) for the
failed invocation. The three successful calls wrote new raw/final PNG pairs;
the failed slot wrote no image. The output directory contained no stale `.tmp`
files after the stop.

Terminal ledger counts are:

```text
PRESERVED_PROFILE_A=99
SUCCESS_PROFILE_B=3
FAILED_CONFIRMED_PROFILE_B=1
NOT_STARTED_PROFILE_B=337
PROFILE_B_STARTED=0
COMPLETION_UNKNOWN=0
TOTAL_FROZEN_SLOTS=440
LOGICAL_PROVIDER_REQUESTS=4
```

### 3. Mechanical output and lineage evidence

The post-stop batch inventory found 102 raw and 102 final files: the original
99 preserved pairs plus three new Profile-B pairs. All 204 files passed Pillow
verification; raw files are `1672x941` and final files are `1920x1080`, with no
inventory errors or symlinks. The three new pairs have these hashes:

```text
PF_P4D_HN_KNEEL_G008_V05
  raw   9c570d8bcebef89080e8ca87951b5e1c3bc10207148ec35b7ec8b10e3e135c66
  final 1c66e4146019746cfc21b3de759aae6b7eee9550e5e23634b656eadaba8a0140
PF_P4D_HN_KNEEL_G009_V01
  raw   eedb08a999233dfb0f6f9b7894ed30238278be445208a971d148215f452ab896
  final b024c2e324504db9c3e0ee27a2677a5647be0e3ea895279b490de49904bda5df
PF_P4D_HN_KNEEL_G009_V02
  raw   112604412fd71da0d4112c646f05eef127f905006fa5bd13c82b2a3a32608edb
  final 3e4cd1c8194c514353ea7dc63756f4fa1b0300093436b7e1d8c530977c9b27e6
```

This is mechanical integrity evidence only. The 440-image mechanical QA,
deduplication gate, human semantic review, formal ingest, and C3 were not
reached. Therefore `P4D_VALIDATED_GENERATION_BASELINE=false` and
`P4D_IMAGES_ACCEPTED=0`; no image is being promoted to the formal dataset by
this report.

### 4. Freeze binding correction and canonical terminal seal

The first terminal-freeze attempt is retained unchanged as
`freeze/p4d_gr3q2e_terminal_freeze_initial_binding_error.json` with SHA
`f68257b67d0c4685f394fc1a77a5dff74a3c100b6c2f442a91075f8e850355e5`. Its audit
found exactly one local binding mismatch: the SQLite main file was hashed while
the runner connection was open, then changed bytes during normal close/checkpoint
(expected `565914925fa556b53096c7267188eeb9ae0cc1b8667f54716c5def08980c2612`,
stable actual `f41f0a0c70afc48957df60e60759d65c075f266a9b082cf639be53e965819ce7`).
The original bytes, sidecar, and mismatch audit were preserved. A read-only
reseal after SQLite close produced the canonical terminal freeze
`freeze/p4d_gr3q2e_terminal_freeze.json`, SHA
`9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44`.
The resealed verification reports `17/17` bound artifacts matched,
`freeze_self_match=true`, and `provider_requests_added_by_reseal=0`.

### 5. Dataset and isolation boundary

The formal dataset validator was rerun read-only at task end and remained:

```text
status=valid
error_count=0
full_hash_check=true
warning_count=387
media_count=5081
label_count=4881
batch_count=45
split_count=2618
```

The durable before/after dataset-boundary records have identical annotation
hashes and counts, zero active CSV references to P4D, and `formal_ingest=false`.
The shared split CSV was not edited. No C3, NEW_VAL, or HOLDOUT request was
performed; `HOLDOUT_REQUESTS=0` and `HOLDOUT_CONSUMED=false`. The 387 warnings
remain the pre-existing validator warning set and are not attributed to Q2E.
The parent batch metadata remained unchanged; Q2E slot metadata and request
evidence are isolated under the new Q2E execution root.

## 实验判断

1. The recovery policy worked as specified: it preserved the 99 historical
   Profile-A pairs, successfully recovered three Profile-B slots, retried the
   prior 429 slot once as a new logical invocation, and stopped immediately
   after the next terminal 429. The stop is a policy-compliant terminal state,
   not a transport-success baseline.
2. The successful recovery of `G008_V05` shows that the historical failed slot
   was retryable under this profile at that moment; it does not establish that
   the quota condition is resolved for subsequent slots. The new failure at
   `G009_V03` is the controlling terminal evidence for this revision.
3. Because 337 frozen Profile-B slots remain not started and no full-image QA or
   semantic review occurred, this revision cannot be called a completed 341-slot
   recovery, a validated full-regeneration revision, a C3 candidate, or a
   production-ready dataset.
4. No classifier inference was run in Q2E. Consequently TP/FP/TN/FN,
   precision/recall/F1/accuracy, hard-negative FPR, and any semantic baseline
   metric are `N/A`, not zero.

## 风险与限制

- The provider returned a usage-limit 429 after seven observed physical
  attempts. Exact monetary cost is unknown; the theoretical maximum of
  `341 x 4 = 1,364` provider attempts was not reached and must not be reported
  as actual usage or billing.
- Profile stratification reduces the earlier profile-lineage ambiguity but does
  not remove possible account-dependent distribution or server-side behavior.
  The 99 Profile-A images and three Profile-B images are not a balanced sample;
  all four attempted slots in this stop segment are the same hard-negative
  taxonomy and split. No semantic conclusion should be generalized from them.
- The three new image pairs are retained as execution artifacts only. They are
  not formally ingested, not ground truth, and not evidence that the generated
  content satisfies the target semantic taxonomy.
- The initial freeze-binding error is preserved rather than overwritten. The
  canonical reseal is valid only after the SQLite-close correction; future
  audits must use the canonical SHA and retain the initial error artifact.
- Existing validator warnings are historical/shared-workspace warnings. They
  remain visible and were not repaired or suppressed by Q2E.

## 下一阶段建议

Do not resume this sealed revision, resend `G009_V03`, or start another slot
under the same Q2E authorization. Any further provider recovery requires a new
standalone authorization and a separately identified revision that explicitly
addresses quota/reset timing, preserves this stopped history, repeats the
freeze and runtime gates, and declares its own maximum logical scope. A future
revision must also complete the full 440-slot mechanical/duplicate audit and
human semantic review before any formal ingest or C3/VAL work. No P2/P3/P4
semantic optimization, prompt change, crop/ROI change, or HOLDOUT access is
authorized by this report.

## 交付物与关键哈希

Execution root:

`/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/profile_stratified_recovery_20260828_01/`

```text
PREFLIGHT_FREEZE_SHA256=5ed7db5f0b0a623e380b1daf3201518c920cdcd1aca0d2d796d5dcccabcf0f67
TERMINAL_FREEZE_SHA256=9ccc13936d0b62a5d352a0c2a402603e99712bc2064beca67b4ee7fd56fb7a44
INITIAL_TERMINAL_FREEZE_BINDING_ERROR_SHA256=f68257b67d0c4685f394fc1a77a5dff74a3c100b6c2f442a91075f8e850355e5
AUTHORIZATION_ATTESTATION_SHA256=7633373e4f601e9b93bd9378cbe5290b4c3836a84284e6c94fe42db1df2b75b6
AUTHORIZATION_TEXT_SHA256=ae484cf957c0e88f6a7329c3359e2ebbc7a3e4794fd3dc35f22dbc9f606e9cbd
RUN_CONFIG_SHA256=5a08f9a935f43614ef66b654c008e5c9b52f32a1728366f9cd9dcb6de25d086a
FROZEN_440_MANIFEST_SHA256=5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4
SLOT_PLAN_SHA256=07f4f4c35c93c072dd5dfd5b0db576b8a7451726c4b878929f380da641e0fa14
EXECUTION_LEDGER_SHA256=40a170cc48526e04bc344b55f4060c8bc0ab8c729c7c9f8ee126ede1da8c2fd0
EXECUTION_SQLITE_SHA256=f41f0a0c70afc48957df60e60759d65c075f266a9b082cf639be53e965819ce7
REQUEST_LOG_SHA256=f2083b8379d01893efe932d599c8f58f20cb8a071101fbc5fe646d0275e00637
RAW_RESPONSES_JSONL_SHA256=fc16d104248a157e3c3ab67f98fbebd37a54639be0dc602b1d37320eef08236d
BATCH_OUTPUT_INVENTORY_SHA256=c7f60a5f39c117b5cf96bd1e579345d97da1cee1b54668351ea4cbefe215cf36
RAW_RESPONSE_MANIFEST_SHA256=12b0abfa30b0e8cec0a9f25d5fc456625b73592587f2ad0dcaeb390680506e06
TERMINAL_SUMMARY_SHA256=1459c61dc626d29660a46514b3e52ca6ab192e8915f3ac80c3d299cafe64ccc0
RUNNER_SHA256=707033a48a8189e774682a8ef734797b41f925a19d03b5408da43ec7fd47be3c
RESEALER_SHA256=4d349916e171b272788258a11dea578f6d3bfc97825886689a9b29747f4d4037
PROFILE_A_SAFE_FINGERPRINT=ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe
PROFILE_B_SAFE_FINGERPRINT=d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190
WRAPPER_SHA256=f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe
INSTALLED_BINARY_SHA256=1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba
```

The detailed per-request evidence is in `request_log.jsonl`,
`raw_responses.jsonl`, `04_raw_responses/`, and
`03_ledger/slot_metadata/`. Account/session identifiers in provider output are
redacted; the raw response, retry, HTTP, and image-hash evidence is retained.
