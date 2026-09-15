# person_fallen v3 floor-pose verifier — terminal status

Revision: `PERSON_FALLEN_V3_FLOOR_POSE_VERIFIER_20260902_01`  
Terminal status: `MODEL_SIDE_LIMIT_REACHED_AFTER_TARGETED_VERIFIER`

## Boundaries preserved

- v3.0 definition, GT, remap, V3-C0 prompt, existing DEV results, and freeze history are unchanged.
- DEV Stage 1 reuses the frozen `V3-C0-448` predictions; it made zero new Stage-1 model calls.
- No P4D generation, human review, shared-dataset or production-project write, SCREEN, VAL, or Holdout access occurred.
- `HOLDOUT_CONSUMED=false`; `holdout_requests=0`; no model prediction was used to create or alter GT.

## V3-CASCADE-448 DEV (436 items)

| Item | Result |
| --- | ---: |
| Stage-2 calls | 233 |
| Baseline TP / FP / TN / FN | 185 / 37 / 193 / 1 |
| Cascade TP / FP / TN / FN | 184 / 33 / 197 / 2 |
| Precision / Recall / F1 | 0.8479 / 0.9892 / 0.9132 |
| Hard-negative FPR | 0.2129 (33 / 155) |
| Ordinary-negative FPR | 0.0000 |
| Strict JSON success | 1.0000 |
| DEV gate | FAIL |

Floor-sitting baseline FP = 33; suppressed = 4; remaining FP = 29.

The cascade also left `ground_maintenance=2` and `kneeling_half_kneeling=2` false positives. One true positive (`crawling_without_explicit_maintenance`) was incorrectly suppressed by Stage 2; the other final false negative was the pre-existing Stage-1 negative and had no Stage-2 call.

## Deterministic stop decision

The only permitted 896 fallback required a DEV failure solely from residual floor-sitting verifier error, while recall, ordinary FPR, and strict JSON passed. This 448 run has non-floor-sitting residual FPs and one Stage-2 positive suppression, so the prerequisite is false. Therefore `V3-CASCADE-896`, SCREEN, and VAL are `NOT_RUN`; no additional prompt, resolution, or model experiment is authorized in this revision.

Next action: **stop this event without consuming Final Holdout.**
