# `person_fallen` V2 P2 final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_PROTOCOL_REPAIR=SUCCESS
P1A_DEV_MEASUREMENT=VALID
P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR
P1A_VALID_CLASSIFICATION_BASELINE=false
P1R_STATUS=COMPLETE
P1R_VALID_RECOVERY_BASELINE=true
P1R_VAL_IS_PRISTINE=false

P2_NAME=P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION
P2_STATUS=COMPLETE
P2_INTERNAL_SPLIT_STATUS=PASS
P2_SCREEN_BLIND_BEFORE_CANDIDATE_FREEZE=true
P2_FORENSIC_SOURCE=DESIGN_ONLY
VAL_ERRORS_USED_FOR_PROMPT_DESIGN=false
P2_WINNER=C3
P2_SCREEN_PROTOCOL_GATE=PASS
P2_WINNER_FREEZE=PASS
P2_VAL_PROTOCOL_GATE=PASS
P2_VALIDATION_COMPLETE=true
P2_VAL_IS_PRISTINE=false
P2_REFERENCE_THRESHOLDS_PASS=false
P2_LATENCY_GATE=FAIL

HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
P3_EXECUTED=false
PRODUCTION_CODE_MODIFIED=false
```

## 已确认事实

P2 changed only Prompt text. Model, model digest, endpoint, output format, top-level `think=false`, response-only parser, temperature, context, token budget, concurrency, letterbox preprocessing, JPEG quality, GT, original DEV/VAL/HOLDOUT split, and event definition remained fixed.

The final read-only formal dataset validation is `status=valid`,
`error_count=0`, `full_hash_check=true`, `warning_count=387` (the same
pre-existing warning set). The requested `ingest_media.py validate
--json-output` interface is not available in this checkout; the available
`tools/validate_dataset.py --json` interface was used and its output was
recorded. No formal re-ingest or shared split CSV edit was performed.

The 31 original DEV groups were frozen once into 19 DESIGN groups (190 images) and 12 SCREEN groups (120 images), with zero cross-group leakage. DESIGN was the only source of individual forensic evidence. The forensic set contained 70 hard negatives and 7 baseline false positives, all hard-negative; ordinary-negative baseline FP count was zero. No VAL individual error was used to design candidates.

Three candidates were tested on the same SCREEN manifest. C1 did not improve over C0; C2 worsened hard-negative FPR; C3 was the only candidate satisfying protocol, recall, ordinary-negative, latency, and minimum hard-negative-improvement gates. C3 fixed 17 C0 false positives with zero new false positives in SCREEN, preserved all 50 positive TPs, and created no FN.

The common protocol canary had 9 DEV images. Each of C1, C2, and C3 completed
9/9 with HTTP, response-nonempty, JSON, schema, and canonical success at 100%
and `thinking_present=0%`; each full 120-image SCREEN run also passed all
protocol checks at 100%.

The winner C3 was frozen before VAL. P2 VAL then ran once, with 100/100 durable completed requests and no HOLDOUT. Protocol and canonical output success were 100%, and the independent verifier reproduced all classification metrics exactly.

## 实验判断

P2 的证据支持一个有限但清晰的判断：C3 的 support-state 语义约束在 DEV SCREEN 上显著减少了把近地面姿态误报为倒地的错误，并在 P1R recovery VAL 的汇总结果上保留全部正例召回、减少 6 个误报且没有新增误报；但当前结果不能被称为达到项目参考门槛的发布基线，因为 Precision、hard-negative FPR 和 P95 延迟门槛均未通过。

### DESIGN forensic

The observed failure mechanism was support-state confusion: the baseline treated seated, kneeling, squatting, and active push-up/plank postures near the floor as lying. C3 was designed to require the evidence slots “support surface,” “torso/pelvis state,” and “active supporting limbs” while preserving intentional abnormal-surface lying as positive. No GT label was modified.

### SCREEN candidate selection

| Candidate | TP/FP/TN/FN | Precision | Recall | Ordinary FPR | Hard-negative FPR | P95 | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| C0 | 50/22/38/0 | 0.694444 | 1.000000 | 0.000000 | 0.550000 | 1.594376s | baseline |
| C1 | 50/22/38/0 | 0.694444 | 1.000000 | 0.000000 | 0.550000 | 1.761156s | rejected: insufficient improvement |
| C2 | 50/29/31/0 | 0.632911 | 1.000000 | 0.000000 | 0.725000 | 1.592479s | rejected: worsened hard-negative FPR |
| C3 | 50/5/55/0 | 0.909091 | 1.000000 | 0.000000 | 0.125000 | 1.815010s | **winner** |

The SCREEN improvement was substantial: hard-negative FPR delta `-0.425000`, Precision delta `+0.214646`, Recall delta `0`, and paired `17` FP rescues with `0` new FP. The auxiliary McNemar exact p-value was `0.000015`; selection still followed the declared metric/gate ordering.

### P2 winner and VAL generalization

P2 C3 VAL:

| Metric | Result |
| --- | ---: |
| TP / FP / TN / FN | **40 / 5 / 55 / 0** |
| Precision | **0.888889** |
| Recall | **1.000000** |
| F1 | **0.941176** |
| Accuracy | **0.950000** |
| Ordinary-negative FPR | **0.000000** |
| Hard-negative FPR | **0.125000** |
| Model uncertain rate | **0.000000** |
| P50 / P95 | **14.684316s / 18.147252s** |

Compared with P1R VAL (`40/11/49/0`, Precision `0.784314`, hard-negative FPR `0.275000`):

```text
baseline_FP_rescued=6
new_FP_created=0
baseline_TP_preserved=40
new_FN_created=0
```

The semantic improvement generalizes on this recovery VAL aggregate, but the reference thresholds are not met (`Precision < 0.93`; `hard-negative FPR > 0.05`). The P2 VAL P95 also fails the predeclared `1.8520842s` development latency limit by a wide margin. `P2_VALIDATION_COMPLETE=true` refers to a complete, protocol-valid, independently verified run; it does not mean the reference quality/latency gates passed.

## 风险与限制

1. **VAL 非 pristine。** P1R had prior VAL protocol exposure and a completed recovery evaluation. P2 therefore remains `P2_VAL_IS_PRISTINE=false`.
2. **延迟回归。** SCREEN P95 was 1.815010s, but P2 VAL P95 was 18.147252s. The source of this remote-run variability was not investigated by changing the frozen experiment; it is a release-blocking operational risk.
3. **门槛未达标。** Precision 0.888889 and hard-negative FPR 0.125000 are improved but not sufficient for the stated 0.93 / 0.05 targets.
4. **AIGC-only.** The dataset is `gpt-image-2` AIGC with prompt-derived GT. No robot, real-camera, temporal-video, or production generalization is established.
5. **HOLDOUT remains sealed.** The 90 HOLDOUT images were never requested or consumed. No follow-up optimization or measurement may use them without a separate authorization and one-time final-run protocol.
6. **Production boundary.** P2 wrote no files under `/home/yanbo/net_vlm_yanboversion/vlm`; no RTC, RTM, MQTT, TTS, or production integration was started. A read-only completion probe did show pre-existing user-owned dirty files in that repository; they were preserved. Thus `PRODUCTION_CODE_MODIFIED=false` describes this P2 run, not a claim that the production worktree was clean beforehand.

## Hashes and identities

```text
Ollama version                 0.23.2
Model / digest                 qwen3.5:4b / 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
P2 winner Prompt SHA           685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e
P2 winner config SHA           8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d
P2 runner SHA                  72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568
P2 materializer SHA            d2485bc89345df7b03bfae42e7cbea206cc1136271381a6cbf3da9d29092482b
P2 internal split SHA           a9edfb22fc0170ce774dfe5e6229bf776c8c272868b55c303e74ae629b153892
P2 candidate freeze SHA        7ab9169a9502c832c8a10b522ab7257eba846a5ff7ecef39f6139b7e5d9beebe
P2 winner freeze SHA            ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0
P2 VAL manifest SHA             f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762
P2 VAL predictions SHA          2f60d6e3e9c0f9589b28cb8812ef9443501b9f971b70e163d4f6f017050bed98
P2 VAL raw responses SHA        cd04ddd89328d7464856dafc8dd99c95eae1761fc7df19b6996ee3de2ad32b4a
P2 VAL request log SHA          9b462e6b6b20a57d076b32b98c9b27700fc1fc14f229c63a66baff97ba4d084e
```

## 下一阶段建议

不要自动启动 P3。P2 已经验证了 Prompt-only semantic boundary 能显著降低 hard-negative FPR，但尚未达到质量或延迟目标。下一步应先由人工确认是否接受一个新的开发实验：回到原 DEV 的新 DESIGN/SCREEN 规划，优先诊断 C3 在 VAL 上的延迟回归及剩余 hard-negative 误报；不能打开 VAL 个体错误来调 Prompt，也不能消费 HOLDOUT。若必须探索更强的证据建模、分辨率、ROI/crop 或姿态特征，应分别创建新的实验 ID 和 freeze，不能把它们混入本 P2 结果。

## Evidence

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/13_p2_internal_split_report.md`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/14_p2_design_forensic_report.md`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/15_p2_candidate_screening_report.md`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/16_p2_val_report.md`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/06_val/result_verification.json`
