# P2 DESIGN-only hard-negative forensic report

## Status

```text
P2_FORENSIC_SOURCE=DESIGN_ONLY
DESIGN_ROWS=190
DESIGN_HARD_NEGATIVE=70
DESIGN_BASELINE_FP=7
DESIGN_ORDINARY_NEGATIVE_FP=0
VAL_ERROR_CASES_USED_FOR_PROMPT_DESIGN=false
GT_INTEGRITY_CONCERN=false
```

## Confirmed facts

Only the 190-item P2_DESIGN manifest was used for forensic inspection. It contains 70 hard negatives, 40 ordinary negatives, 70 positives, and 10 GT-uncertain items. P1A baseline produced 7 DESIGN false positives; all 7 were hard negatives. No ordinary-negative FP was found. No P1R VAL individual error, image, evidence, or taxonomy was accessed for Prompt design.

The seven FP records were visually consistent with their frozen hard-negative labels. They were seated on the floor, kneeling/repairing, squatting, or performing push-up/plank exercise. No Prompt/Image/GT integrity concern was found, so GT was not changed.

## Taxonomy statistics

| Taxonomy | Groups | Total hard negative | Baseline FP | Baseline TN | Category FPR |
| --- | ---: | ---: | ---: | ---: | ---: |
| `sitting_on_floor` | 1 | 10 | 2 | 8 | 0.200000 |
| `kneeling_or_half_kneeling` | 2 | 20 | 2 | 18 | 0.100000 |
| `squatting_or_crouching` | 1 | 10 | 1 | 9 | 0.100000 |
| `deep_bending_or_picking` | 2 | 20 | 0 | 20 | 0.000000 |
| `exercise_pushup_or_plank` | 1 | 10 | 2 | 8 | 0.200000 |
| **Total** | **7** | **70** | **7** | **63** | **0.100000** |

The largest observed DESIGN error rates were sitting and push-up/plank (0.20 each), followed by kneeling and squatting (0.10 each). Deep bending/picking had no DESIGN FP in this split, so it was retained as a coverage category rather than treated as an observed error source.

## Evidence-pattern judgment

The baseline repeatedly described a low or horizontal-looking body as “lying,” “prone,” or “collapsed,” while overlooking the decisive support relation:

- floor sitting: buttocks and legs provided a seated base, sometimes with an upright or wall-supported torso;
- kneeling: knees/shins and hands created a stable kneeling/maintenance posture;
- squatting: flexed legs and feet supported the pelvis in a crouch;
- push-up/plank: hands plus feet actively elevated the torso despite a horizontal silhouette.

This supports a visible support-state boundary intervention. It does not support changing V2 to require an accidental fall, loss of consciousness, injury, or a visible transition.

## Candidate design rationale

- **C1 — explicit posture boundary:** strengthens torso/pelvis distinction between lying and low supported postures.
- **C2 — ordered negative-posture veto:** checks clearly stable seated/kneeling/squatting/exercise support before testing genuine lying, while preserving true lying cases.
- **C3 — concise evidence rubric:** requires support surface, torso/pelvis state, and active supporting limbs as visible evidence slots without changing JSON schema.

All three retain the original V2 positive definition, use response-only JSON, and do not request chain-of-thought.

## Evidence

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/02_forensics/forensic_summary.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/02_forensics/taxonomy_statistics.csv`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/02_forensics/design_false_positives.csv`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/02_forensics/taxonomy_definition.md`
