# 23 — P3 winner report

## 已确认事实

- Candidate advancement gate: protocol=100%, positive recall≥0.95, ordinary-negative FPR=0, hard-negative FPR≤0.075. Neither S1_DIRECT nor S1_RULE qualifies because hard-negative FPR is 0.50 (20/40).
- Winner decision is `NONE`; `P3_STATUS=SCREENING_COMPLETE_NO_WINNER`. C3 remains the historical semantic reference but is not a P3 winner and still misses the project reference quality thresholds.
- Quality gate: P3 reference quality=False; runtime gate=FAIL; runtime anomaly detected=True.

## Candidate comparison

- S1_DIRECT: TP/FP/TN/FN=50/20/40/0; Precision=0.714286; Recall=1.000000; F1=0.833333; hard-negative FPR=0.500000; P95=9.601210s.
- S1_RULE: identical metrics and latency because it is the same response stream and the fixed rule made no changes.
- Relative to C3, S1_DIRECT rescued FP→TN=0, created C3 TN→FP=15, and created C3 TP→FN=0; FP→uncertain=0.

## 实验判断

- There is no defensible unique P3 winner. Selecting S1 would turn a protocol-successful structured output into a materially worse classifier; selecting a threshold or rule after seeing SCREEN would violate the freeze.
- The structured fields are internally consistent on the measured rows, but their visual attribute values frequently reproduce a lying interpretation for screen hard negatives; this is a semantic failure, not a parser failure.

## 风险与限制

- S1 SCREEN observed P95 is `9.601210s` versus the `1.852084s` reference; load-duration >5s occurred 7 times with longest sustained run 3. This is a runtime observation, not proof that Prompt text caused the load anomaly.
- No winner freeze is created because the advancement gate failed; `HOLDOUT` remains sealed.
