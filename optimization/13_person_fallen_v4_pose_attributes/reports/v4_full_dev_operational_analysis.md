# person_fallen v4 full-DEV operational analysis

`ZERO_INFERENCE_ANALYSIS=true`

## Confirmed facts

- Frozen full DEV: 436 rows; no SCREEN, VAL, or Holdout access.
- Legacy v3 binary gate: **FAIL** only on Recall.
- Binary metrics: TP=169, FP=2, TN=228, FN=17, precision=0.9883, recall=0.9086, F1=0.9468.
- Hard-negative FPR=0.0129; ordinary-negative FPR=0.0000.
- Floor sitting: 54/55 direct clear, 1/55 recheck, 0/55 immediate alarm.
- High-priority ground lying: 141/145 immediate alert, 4 recheck, 0 silently cleared.
- High-priority immediate-alert recall=0.9724; alert-or-recheck safety coverage=1.0000.
- Negative immediate high-priority alarms=0/230.
- Push-up/plank decisions: {'ATTENTION_NEAR_GROUND': 24, 'ALERT_GROUND_LYING': 2}.
- Crawling decisions: {'NO_ALERT_NORMAL_POSE': 13, 'ATTENTION_NEAR_GROUND': 2}.

## Inference

The 4B model is sufficiently capable for the narrower robot-inspection question
"is a person clearly lying on the ground versus sitting/kneeling/standing?"
on this synthetic DEV lineage. The v3 binary Recall failure is dominated by
`crawling -> kneeling`, not by sitting-versus-lying confusion.

## Risks and boundary

This is prompt-derived synthetic DEV, not an independent or real-camera claim.
The temporal 2-of-3 policy is implemented and unit-tested, but this still-image
dataset cannot measure temporal performance. Removing crawling from required
attention would be a new business-definition decision; it must not be used to
rewrite v3 GT or retroactively turn this failed v3 binary gate into a pass.
