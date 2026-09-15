# `person_fallen` v3.0 floor-pose verifier revision

This is an isolated, additive two-stage optimization revision. It preserves
the v3.0 definition, V3-C0 prompt, deterministic GT remap, DEV results, and
all v3.0 freeze/history files unchanged.

The pipeline is fixed as follows:

1. Stage 1 is the existing `V3-C0-448` classifier. On DEV it is reused from
   the frozen `dev_V3-C0-448/predictions.csv`; it is never re-run or tuned.
2. Stage 2 is called only when Stage 1 returns `positive`. It determines
   whether the visible person has explicit evidence of a safely suppressible
   normal floor pose: floor sitting, kneeling, or maintenance/work.
3. A Stage-2 `SUPPRESS_NORMAL_POSE` maps the final cascade output to
   `negative`; `KEEP_ALERT` maps to `positive`; `UNCERTAIN` maps to
   `uncertain`.

Ground truth remains `PROMPT_DERIVED_SYNTHETIC_GT` from frozen generation
prompt and planned role. Model output never creates or changes GT. Per-image
human semantic review is not a gate.

This revision does not generate P4D data, resume Q10/Q11, access a Holdout,
modify the production project, modify a shared dataset, or write Git state.

The sole DEV candidate is `V3-CASCADE-448` (Stage-2 `448x336`). Only if it
fails solely because residual final false positives are `floor_sitting`, while
recall, ordinary-negative FPR, and strict JSON gates pass, may the runner
evaluate `V3-CASCADE-896` (Stage-2 `896x672`) with every other variable fixed.
