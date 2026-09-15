# V7-A2 two-state veto + scene fallback

`FINAL_STATUS=STAGE2_A2_GEOMETRY_FAIL`

Selected diagnostic thresholds: `tau_ang=45`, `tau_dy=0.30`, `tau_kp=0.50`.

- G1: ground detected 141; all-primary-UPRIGHT 4; required <=2 — **FAIL**. Pilot ground all-primary-UPRIGHT was 0/60.
- G2: floor all-primary-UPRIGHT 53/55; required >=50 — count **PASS**, specified V6 false-positive IoU verification not completed.
- G3: auxiliary NOT_UPRIGHT 41/41; normal-negative non-floor all-vetoed 91; vetoed ground list in `vetoed_ground.json`.
- G4: not run because G1 failed.

No VLM request, freeze, Pilot, Regression, Full DEV, production integration, or production commit was executed.
