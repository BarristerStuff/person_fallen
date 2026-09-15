# 22 — P3 structured candidate screening

## 已确认事实

- SCREEN is adaptive development data reused from P2; `P3_SCREEN_IS_PRISTINE=false`. Candidate freeze and independent verifier passed before the new S1 SCREEN stream.
- C3 SCREEN is a zero-request reuse with independent metric recomputation; S1_DIRECT and S1_RULE are two offline projections of one S1_STRUCTURED response stream.
- Structured canary: 12/12 HTTP, response-nonempty, JSON, schema, enum/canonical success; `thinking_present=0%`; structured conflict=0/12.

## Candidate metrics

| candidate | TP | FP | TN | FN | Precision | Recall | F1 | Accuracy | ordinary FPR | hard-negative FPR | uncertain rate | conflict rate | P50 | P95 | protocol | decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| C3_BASELINE | 50 | 5 | 55 | 0 | 0.909091 | 1.000000 | 0.952381 | 0.954545 | 0.000000 | 0.125000 | 0.000000 | 0.000000 | 1.580759 | 1.815010 | True | historical_baseline |
| S1_DIRECT | 50 | 20 | 40 | 0 | 0.714286 | 1.000000 | 0.833333 | 0.818182 | 0.000000 | 0.500000 | 0.000000 | 0.000000 | 2.134880 | 9.601210 | True | not_eligible |
| S1_RULE | 50 | 20 | 40 | 0 | 0.714286 | 1.000000 | 0.833333 | 0.818182 | 0.000000 | 0.500000 | 0.000000 | 0.000000 | 2.134880 | 9.601210 | True | not_eligible |
| OPTIONAL_S2 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | not created | not run |

## Paired and taxonomy comparison

- S1_DIRECT and S1_RULE: `direct_wrong_rule_correct=0`, `direct_correct_rule_wrong=0`, direct/rule disagreement=0; the frozen rule produced no change on this screen.
- C3 FP → S1_DIRECT TN=0, C3 FP → uncertain=0, C3 TN → S1_DIRECT FP=15, C3 TP → S1_DIRECT FN=0.

| taxonomy | total hard negatives | groups | C3 errors | S1_DIRECT errors | S1_RULE errors | C3 FPR | S1_DIRECT FPR | S1_RULE FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| crawling_or_kneeling_support | 10 | 1 | 2 | 6 | 6 | 0.200000 | 0.600000 | 0.600000 |
| exercise_pushup_or_plank | 10 | 1 | 3 | 9 | 9 | 0.300000 | 0.900000 | 0.900000 |
| sitting_on_floor | 10 | 1 | 0 | 5 | 5 | 0.000000 | 0.500000 | 0.500000 |
| squatting_or_crouching | 10 | 1 | 0 | 0 | 0 | 0.000000 | 0.000000 | 0.000000 |

- Group-level hard-negative error: C3 `2/4` groups (`0.500000`); S1_DIRECT `3/4` (`0.750000`).

## 实验判断

- S1 preserved positive recall and ordinary-negative FPR but substantially worsened hard-negative errors. The structured rule did not rescue any C3 error and created no direct/rule separation on this screen.
- `P3_STRUCTURED_EVIDENCE_RELIABILITY` is protocol/consistency-pass (100% schema, 0 contradictions) but semantic screen generalization is inadequate for advancement.

## 风险与限制

- SCREEN is not pristine and must not be presented as an independent validation estimate. No VAL rerun was performed.
- The 0% model-uncertain rate means the observed FP increase is not hidden abstention behavior.
