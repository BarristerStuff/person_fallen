# V7-A0 Geometry Verifier

- **FINAL_STATUS:** `STAGE2_GEOMETRY_FAIL`
- **VLM requests:** 0 (Pilot/Regression/Full DEV not run)
- Detector weight SHA matched the authorized value.
- Pose weight downloaded from the official Ultralytics release; SHA recorded in `final_report.json`.

## Stage 2 gates

- Ground lying: `GEOM_LYING ∪ GEOM_UNCERTAIN = 97/145` — **FAIL**, required 145/145.
- Ground lying: `GEOM_LYING = 96/145` — **FAIL**, required at least 130/145.
- Floor sitting all-primary upright: `55/55` — PASS.
- Floor sitting geometry lying: `0/55` — PASS.
- Auxiliary geometry lying: `36/41` — **FAIL**, required at most 4/41.

The candidate is stopped before VLM, freeze, Pilot, Regression, Full DEV, production integration, and Git commit. No VAL/Holdout data or requests were used.
