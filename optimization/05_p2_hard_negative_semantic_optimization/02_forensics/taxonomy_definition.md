# P2 DESIGN hard-negative taxonomy

This taxonomy was derived only from the 70 hard-negative images and their P1A outcomes in frozen `P2_DESIGN`. No `P2_SCREEN` individual prediction, image, source prompt, evidence, FP identity, or VAL error case was used.

- `sitting_on_floor`: buttocks form the primary base; torso remains recognizably seated, optionally wall-supported; legs may be crossed or extended.
- `kneeling_or_half_kneeling`: one or both knees/shins form a stable base, including forward-bent maintenance posture.
- `squatting_or_crouching`: pelvis is held over flexed legs/feet in a compact but supported crouch.
- `deep_bending_or_picking`: person remains supported by feet/legs while bending toward or handling an object near the floor.
- `exercise_pushup_or_plank`: torso may be horizontal and near the floor but is actively supported/elevated by hands plus feet or knees.
- `other`: reserved for DESIGN hard negatives not represented by the above visible support states.

The taxonomy is descriptive only. It does not modify frozen GT. Manual inspection of all seven DESIGN baseline false positives found no evident Prompt/Image/GT conflict, so `possible_GT_boundary_review_needed=false` for those records.
