# Frozen full-DEV consolidation protocol

Candidate: `V4-A0-FULL-CROP-FULLDEV-436`

The 110-row floor-sitting/lying diagnostic passed every preregistered gate.
The prompt, deterministic policy, detector, preprocessing, model digest, and
runtime settings are now byte-frozen for one complete 436-row DEV
consolidation. No result-dependent prompt or policy edit is allowed.

The full run uses all rows of the frozen v3 DEV manifest. It does not read
SCREEN, VAL, or Final Holdout. The 110 prior model outputs are reused only when
the source image SHA, full-view SHA, crop-view SHA, person-detection flag,
prompt SHA, policy SHA, completed-run lock, and pinned prediction file all
match. Every other row receives exactly one new request. Transport-unknown
requests are never resent.

For binary metrics, `ALERT_GROUND_LYING` and `ATTENTION_NEAR_GROUND` count as
event-positive, while `NO_ALERT_NORMAL_POSE` counts as negative. A frame-level
`RECHECK_VISUAL_UNCERTAIN` on determinate GT is conservatively counted as an
error: FN for positive GT and FP for negative GT. Source-GT `uncertain` rows
are reported separately and excluded from binary denominators.

The temporal 2-of-3 state machine is implemented and unit-tested but cannot be
measured from this still-image DEV set. No synthetic repeated frames are used
to claim temporal accuracy.
