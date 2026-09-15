# P3 C3 DESIGN residual forensic

## 已确认事实

- Scope is P2_DESIGN only: 190 rows, protocol gate=True, VAL/HOLDOUT requests=0.
- C3 DESIGN metrics: TP=70, FP=2, TN=108, FN=0; Precision=0.972222; Recall=1.000000; hard-negative FPR=0.028571; ordinary-negative FPR=0.000000.
- Residual FP count=2; residual FN count=0.
- GT-uncertain rows remain outside the confusion matrix; their prediction distribution is retained in forensic_summary.json.

## Residual taxonomy

| taxonomy | total | C3 FP | C3 TN | category FPR | groups |
|---|---:|---:|---:|---:|---:|
| deep_bending_or_picking | 20 | 0 | 20 | 0.000000 | 2 |
| exercise_pushup_or_plank | 10 | 1 | 9 | 0.100000 | 1 |
| kneeling_or_half_kneeling | 20 | 1 | 19 | 0.050000 | 2 |
| sitting_on_floor | 10 | 0 | 10 | 0.000000 | 1 |
| squatting_or_crouching | 10 | 0 | 10 | 0.000000 | 1 |

## Evidence contradiction analysis

- Strict Type A evidence-to-label inconsistency=0: the C3 evidence did not explicitly name a non-lying posture as its conclusion, so the two support-clue cases are not double-counted as Type A.
- Type B visual attribute extraction errors=2: IMG_003739,IMG_003786; both evidences assert prone/collapsed lying while the source scenario/image is a supported non-lying posture.
- Explicit hand/foot support clues appeared in 2 residual evidences (IMG_003739,IMG_003786); this is an audit dimension, not a second error count.
- Type C support-surface errors=0, Type D multi-person confusion=0, Type E other=0 in the two residuals.

## 实验判断

- The small DESIGN residual is dominated by visual posture attribute extraction: the model saw a floor and support limbs but adjudicated the posture as collapsed lying. This is evidence for testing explicit structured attributes; it is not evidence that a fixed rule already generalizes.
- P3 candidate design uses only this DESIGN forensic. P2_SCREEN individual errors, P2 VAL individual errors, and HOLDOUT were not read for design.

## 风险与限制

- There are only two C3 DESIGN false positives across two hard-negative groups; taxonomy rates are descriptive and have high uncertainty.
- All images are AIGC development data; this is not a real-camera or production generalization claim.
