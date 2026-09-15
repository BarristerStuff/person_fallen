# P1A final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0

P0_STATUS=COMPLETE_PROTOCOL_FAILURE

P1A_NAME=P1A_THINK_FALSE_PROTOCOL
P1A_CHANGE=think_false_only
P1A_PROMPT_CHANGED=false
P1A_PREPROCESS_CHANGED=false

CANARY_STATUS=PASS
DEV_PROTOCOL_GATE=PASS
VAL_PROTOCOL_GATE=NOT_RUN_TO_COMPLETION

P1A_STATUS=VAL_INCOMPLETE_FREEZE_BINDING_ERROR
P1A_VALID_CLASSIFICATION_BASELINE=false

HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false

VAL_P0_PROTOCOL_EXPOSED=true
VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false

P2_EXECUTED=false
PRODUCTION_CODE_MODIFIED=false
```

## Confirmed facts

- `think=false` fixed the P0 response-channel failure: canary and DEV both have 100% response non-empty, JSON parse, schema, and canonical success, with no thinking fallback.
- DEV classification metrics are valid for the frozen DEV request protocol: TP=120, FP=29, TN=141, FN=0; Precision=0.805369; Recall=1.0; F1=0.892193; Accuracy=0.9; ordinary-negative FPR=0.0; hard-negative FPR=0.263636; model uncertain rate=0.0; P50/P95=1.453798s/1.610508s.
- A DEV freeze binding error was detected before completion of VAL. The original freeze is preserved and not rewritten. P1A VAL is an incomplete, partially exposed one-shot evaluation with 10 confirmed and 1 possible additional request, but no committed results.
- HOLDOUT was not requested or consumed.

## Experiment judgment

The `think=false` change is the confirmed output-protocol repair. DEV now provides a valid development classification measurement, but P1A does not provide a valid DEV-to-VAL baseline because VAL was not completed under a valid freeze binding. The hard-negative FPR also exceeds the project reference; this is only a reported observation, not authorization to optimize in this task.

## Risks and limitations

- This is AIGC-only; it does not establish robot, real-camera, or production accuracy.
- VAL had been P0 protocol-exposed already; P1A additionally introduced partial unlogged exposure. It must not be called pristine or unexposed.
- The preserved original freeze binding mismatch means later work cannot claim that P1A VAL was governed by a correct prior DEV freeze.

## Next recommended stage

Do not execute P2 or consume HOLDOUT. The correct next step is a separately named, explicitly authorized recovery/freeze-governance stage that first decides how to treat the partial VAL exposure and then creates a new immutable protocol/evaluation plan. It is not P1B_SCHEMA_FORMAT: the P1A output protocol itself succeeded.
