# person_fallen V4 operational closure report

```text
OPERATIONAL_DEFINITION_FROZEN=true
```

DEV passed by zero-inference recomputation from the sealed `V4-A0-FULL-CROP-436` predictions:

```text
ground_lying ALERT recall=141/145=0.9724137931034482
ground_lying ALERT+RECHECK coverage=145/145=1.0
floor_sitting ALERT FPR=0/55=0
determinate-negative ALERT FPR=0/230=0
RECHECK count=19
strict JSON success=1.0
gate=PASS
```

SCREEN used the frozen candidate without changing definition, Prompt, policy, GT, or threshold:

```text
ground_lying ALERT recall=24/25=0.96
ground_lying ALERT+RECHECK coverage=24/25=0.96
floor_sitting ALERT FPR=0/25=0
determinate-negative ALERT FPR=0/51=0
RECHECK count=2
strict JSON success=1.0
gate=FAIL
```

The single failed coverage sample was `PFV4_SCREEN_0066`, taxonomy `curled_or_partially_occluded_lying`, returned as `NO_ALERT_NORMAL_POSE` with `CLEAR_NORMAL_POSE:kneeling`. The failed gate is the required `ground_lying ALERT+RECHECK coverage == 1.0`; therefore the candidate is not advanced to VAL.

```text
SCREEN=FAIL
VAL=NOT_RUN
FINAL_CANDIDATE=V4-A0-FULL-CROP
READY_FOR_FINAL_HOLDOUT=false
HOLDOUT_CONSUMED=false
NEXT_ACTION=STOP_AFTER_SCREEN_FAIL; no VAL, no Holdout preflight, and no further model-side experiment
```

The auxiliary `near_ground_attention` path remains outside the high-priority `person_fallen` gate. No Holdout rows were read or consumed.
