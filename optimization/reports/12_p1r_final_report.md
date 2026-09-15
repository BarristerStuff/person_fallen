# person_fallen V2 — P1R final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR
P1R_NAME=P1R_FREEZE_BINDING_RECOVERY
P1R_STATUS=COMPLETE
P1R_PROTOCOL_STATUS=PASS
P1R_VALID_RECOVERY_BASELINE=true
P1R_VAL_IS_PRISTINE=false

HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P2_EXECUTED=false
PRODUCTION_CODE_MODIFIED=false
```

## Confirmed facts

P0 remains a permanent output-protocol failure: its 410 responses were HTTP-successful but the formal `response` field was empty and model text appeared in `thinking`; no P0 result was reconstructed from `thinking`.

P1A changed only the request top-level `think=false` and restored response-channel protocol on a 12-image DEV canary and 310-image DEV run. Its historical DEV freeze binding later proved wrong: declared DEV-manifest SHA-256 `f829285121249ceac924632c485f67ee3d83e9a9cf08a0d3716908bb21878c58` differs from actual `7f8ff256a8da3cc6451e1ec3f6a842dc9b3eb6f4080e4fb5a1a49dda9bc7d7d8`. P1A history was retained as `VAL_INCOMPLETE_FREEZE_BINDING_ERROR`; it was not changed into a completed baseline.

P1R independently bound and verified the actual P1A DEV evidence, all frozen source inputs, model identity, and its own 100-item recovery VAL manifest. Its pre-inference freeze verifier passed with all hashes matching. The execution-time recovery-freeze identifier recorded in the durable VAL summary is `9aa6b1e9d0f87144633539850d6b30236fe5c50acb5368bd90961cd2ac3674a0`.

P1R executed exactly 100 planned VAL requests under the P1A request semantics. The durable ledger has 100 `COMPLETED`, 0 confirmed failed, and 0 unknown terminal requests. It recorded no HOLDOUT item. All 100 requests passed HTTP, non-empty response, JSON, schema, and canonical prediction checks; `thinking_present=0/100`. The independent result verifier passed and reproduced all metrics exactly.

The final read-only dataset validator reports `status=valid`, `error_count=0`, `full_hash_check=true`, and `warning_count=387`. Dataset media and label counts are both 4201. Existing warnings were neither modified nor attributed to P1R.

## Experiment judgment

P1R establishes the first valid **recovery** classification baseline for this frozen `person_fallen` V2 AIGC dataset. It is valid with respect to its frozen input binding, durable one-run execution, response-only output contract, complete audit trail, and independent recomputation. It is not a pristine VAL evaluation: before P1R, P1A had 10 confirmed VAL requests and one possible additional in-flight request without a durable result, so `P1R_VAL_IS_PRISTINE=false`.

### P1R VAL outcome

| Metric | Value |
| --- | ---: |
| TP / FP / TN / FN | 40 / 11 / 49 / 0 |
| Precision | 0.784314 |
| Recall | 1.000000 |
| F1 | 0.879121 |
| Accuracy | 0.890000 |
| Ordinary-negative FPR | 0.000000 |
| Hard-negative FPR | 0.275000 |
| Model uncertain rate | 0.000000 |
| P50 / P95 latency | 1.478509s / 1.650989s |

The project reference thresholds are not met: precision is below 0.93 and hard-negative FPR is above 0.05. The main observed error mode is therefore hard-negative false alerts (11 total FP, all consistent with zero ordinary-negative FPR and hard-negative FPR 0.275). This is an observation from the frozen evaluation, not a post-hoc change to its semantics.

## Risks and limitations

- **Prior VAL exposure:** This P1R result cannot be represented as never-model-exposed validation. It has confirmed prior exposure 10 and possible additional exposure 1.
- **Data provenance:** All 500 images are AIGC (`gpt-image-2`) and GT is prompt-derived from user-confirmed prompt/image alignment. The outcome does not establish real-camera, robot, temporal-video, or production performance.
- **Error control:** Hard-negative FPR 0.275 creates an unacceptable false-alert risk under the stated 0.05 reference. Recall was 1.0 on this AIGC VAL, but this should not be generalized beyond the frozen dataset.
- **HOLDOUT:** The 90-item HOLDOUT remains unrequested and unconsumed. It must not be used for prompt/config decisions or for follow-up measurement without a separate one-time authorization and frozen final-run protocol.
- **Freeze-verifier mutation:** A post-run invocation of the original verifier rewrote only its verification timestamp, so the current on-disk freeze JSON SHA is `15d7e30d43c39b305ab89ac7a9f2e91567a40b3ff86c6e2a9299f5e3994c27e0`, distinct from the execution-time identifier above. Candidate fields still match exactly and no model/response/ledger/prediction/log artifact changed. The verifier was corrected to be read-only for an existing freeze and passed a before/after SHA equality check. This retention caveat prevents describing the current freeze file as byte-immutable across the post-run audit.

## Next-stage recommendation

Do not execute P2 automatically. If a new, separately authorized stage is approved, the evidence supports designing `P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION` on DEV only, with a new experiment ID and a newly frozen configuration. It should target the false-alert mechanism while preserving the P1R recovery record, keeping VAL fixed (already non-pristine), and leaving HOLDOUT untouched. Any real-camera or robot claim needs separately collected, independently adjudicated data; it cannot be inferred from this AIGC baseline.

## Key identities and evidence

```text
Ollama version:       0.23.2
Model/digest:         qwen3.5:4b / 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
Prompt SHA-256:       b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4
P1R config SHA-256:   f15d4083ae7c52ccf668b75982aee98e35f24d28bf96fe1303e0d9885c94de8c
P1R runner SHA-256:   18e45f2693334baac80105ccbb9a094cd6781022e5243955e0b9ed8e61260eb5
Recovery VAL manifest: f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762
Execution freeze ID:  9aa6b1e9d0f87144633539850d6b30236fe5c50acb5368bd90961cd2ac3674a0
Current freeze SHA:   15d7e30d43c39b305ab89ac7a9f2e91567a40b3ff86c6e2a9299f5e3994c27e0
P1R prediction SHA:   7f221795f9a21febd47d5861ee58492dbef6eb00a1032ea240bc1c536de1e38b
P1R raw SHA:          d9be1890277f2e4798f1b4ab7ee63817667d1cae0c79aa86ecaccb82de878f97
P1R request-log SHA:  e553985465791fd57d9e0ca8cc6960ff7481e7b66a4cc669b7fb9d190a994b34
P1R ledger SHA:       05fdba91477da465aee3e305edc4437f43279556ca2dccac9e6034586a1c54c0
```
