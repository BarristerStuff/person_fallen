# P1R preflight and freeze-binding recovery

## Status

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
STAGE=P1R_FREEZE_BINDING_RECOVERY
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR
P1R_PREFLIGHT=PASS
P1R_FREEZE_VERIFICATION=PASS
ALL_FILE_HASHES_MATCH=true
HOLDOUT_ROWS_IN_RECOVERY_MANIFEST=0
HOLDOUT_REQUESTS_BEFORE_P1R=0
```

## Confirmed facts

The historical P1A DEV freeze is preserved unchanged. Its declared DEV manifest SHA-256 was:

```text
f829285121249ceac924632c485f67ee3d83e9a9cf08a0d3716908bb21878c58
```

The actual P1A DEV manifest SHA-256 is:

```text
7f8ff256a8da3cc6451e1ec3f6a842dc9b3eb6f4080e4fb5a1a49dda9bc7d7d8
```

They do not match. The P1A history audit separately established that the actual DEV manifest, predictions, and request log each contain 310 unique media IDs; their entity sets are identical; there are zero HOLDOUT rows; and all 310 rows are HTTP/JSON/schema/canonical successes with no `thinking` field used for prediction. P1R used that actual evidence only after recording the mismatch; it did not overwrite the original freeze or P1A report.

The frozen recovery VAL manifest contains 100 unique deterministic binary-GT VAL images, zero non-VAL rows, zero HOLDOUT rows, and SHA-256:

```text
f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762
```

The independent verifier checked every frozen input file hash and returned `PASS`. The execution-time recovery-freeze identifier recorded by the VAL run is SHA-256 `9aa6b1e9d0f87144633539850d6b30236fe5c50acb5368bd90961cd2ac3674a0`.

### Post-run verifier mutation, retained and corrected

During final verification, the original verifier implementation rewrote `freeze_verified_at_utc`; this changed the on-disk freeze JSON byte SHA to `15d7e30d43c39b305ab89ac7a9f2e91567a40b3ff86c6e2a9299f5e3994c27e0`. This was a verifier design defect, not an inference/config/data change. A field-by-field comparison confirms every recovery-candidate field still matches; the only additional freeze fields are the candidate SHA, `freeze_verification=PASS`, and the verifier timestamp. No network inference was made during that refresh and no VAL result artifact changed.

The verifier was corrected before task close so that an existing freeze is checked read-only. The final before/after SHA check is `15d7…27e0` both before and after the verifier call. The pre-run execution identifier remains in the durable VAL summary for traceability; the current on-disk artifact SHA is reported separately rather than silently substituting one for the other.

## Frozen request semantics

```text
model=qwen3.5:4b
endpoint=http://192.168.20.62:11434
ollama_version=0.23.2
model_digest=2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
format=json
think=false (top-level)
parser=response_only
temperature=0
num_ctx=8192
num_predict=256
stream=false
concurrency=1
preprocess=letterbox
target_size=448x336
jpeg_quality=70
```

The P0 prompt remained byte-identical: SHA-256 `b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4`. P1R configuration SHA-256 is `f15d4083ae7c52ccf668b75982aee98e35f24d28bf96fe1303e0d9885c94de8c`; the frozen inference-runner SHA-256 is `18e45f2693334baac80105ccbb9a094cd6781022e5243955e0b9ed8e61260eb5`.

## Recovery-validation exposure

P1R cannot describe VAL as model-pristine. The prior P1A attempt has 10 confirmed completed VAL requests and one possible additional in-flight request without a durable result record. P1R records:

```text
P1R_VAL_IS_PRISTINE=false
PRIOR_VAL_CONFIRMED_EXPOSURE=10
PRIOR_VAL_POSSIBLE_ADDITIONAL_EXPOSURE=1
```

## Reasoning and risk boundary

The mismatch was a binding/provenance problem, not evidence that P1A DEV response parsing was wrong: the actual P1A DEV artifacts are internally consistent and were re-bound under P1R. That supports a separate recovery run; it does not retroactively make P1A a complete pristine DEV-to-VAL baseline.

The dataset is AIGC-only and GT is prompt-derived under confirmed prompt/image alignment, not independently visually adjudicated. This constrains any accuracy claim to this formal AIGC dataset.

## Evidence locations

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/04_p1r_freeze_binding_recovery/preflight/p1a_history_audit.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/04_p1r_freeze_binding_recovery/preflight/recovery_freeze_verification.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/04_p1r_freeze_binding_recovery/freeze/p1r_recovery_freeze.json`
