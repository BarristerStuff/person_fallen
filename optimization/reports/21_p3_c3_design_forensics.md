# 21 — P3 C3 DESIGN forensic

## 已确认事实

- Dataset gate before inference: status=valid, errors=0, full_hash_check=True, warnings=387; formal dataset was not re-ingested or edited.
- C3 was newly requested on the complete P2_DESIGN manifest: 190 unique DEV images, manifest SHA `f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1`, VAL/HOLDOUT requests=0.
- Protocol gate: HTTP=1.0, response_nonempty=1.0, JSON=1.0, schema=1.0, canonical=1.0; thinking_present=0.0.
- C3 DESIGN binary metrics (GT uncertain excluded): TP=70, FP=2, TN=108, FN=0; Precision=0.972222, Recall=1.000000, F1=0.985915, Accuracy=0.988889, ordinary-negative FPR=0.000000, hard-negative FPR=0.028571, model-uncertain rate=0.000000.
- C3 residual FP=2; residual FN=0. GT-uncertain prediction distribution={'negative': 6, 'positive': 4}.

## Residual taxonomy

| taxonomy | total | C3 FP | C3 TN | category FPR | groups |
|---|---:|---:|---:|---:|---:|
| deep_bending_or_picking | 20 | 0 | 20 | 0.000000 | 2 |
| exercise_pushup_or_plank | 10 | 1 | 9 | 0.100000 | 1 |
| kneeling_or_half_kneeling | 20 | 1 | 19 | 0.050000 | 2 |
| sitting_on_floor | 10 | 0 | 10 | 0.000000 | 1 |
| squatting_or_crouching | 10 | 0 | 10 | 0.000000 | 1 |

## Evidence-to-label versus visual-attribute analysis

- Strict Type A evidence-to-label inconsistency=0: no residual evidence explicitly concluded a named non-lying posture while retaining `person_fallen=positive`.
- Type B visual attribute extraction error=2: the two residuals `IMG_003739,IMG_003786` describe prone/collapsed lying although their source scenarios/images are supported kneeling or push-up/plank postures.
- An explicit hand/foot support clue appears in 2 residual evidences. It is retained as a separate audit dimension and is not double-counted as strict Type A.
- Type C support-surface error=0; Type D multi-person confusion=0; Type E other=0.

## 实验判断

- The complete DESIGN residual points to visual posture-attribute extraction as the observed C3 failure mechanism, with no C3 positive FN. This supports testing explicit structured fields, but the sample is only two residuals and cannot establish generalization.
- Candidate design source is DESIGN-only. P2 SCREEN individual errors, P2 VAL individual errors, and HOLDOUT were not used before candidate freeze.

## 风险与限制

- All development evidence is AIGC; taxonomy is prompt/scenario metadata plus qualitative inspection of the two DESIGN residuals, not real-camera evidence.
- C3 DESIGN warm P95 is `1.868383s`; this stage does not solve the historical P2L load anomaly.
