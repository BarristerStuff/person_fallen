# P4D GR3Q6 partial mechanical QA

## 已确认事实

All nine successfully generated Q6 images were retained and mechanically
processed exactly once:

```text
NATIVE_RAW_PNG=9
FINAL_1920x1080_PNG=9
PILLOW_FAILURES=0
DIMENSION_FAILURES=0
EXACT_DUPLICATE_HITS=0
GR1_SHA_HITS=0
PARTIAL_MECHANICAL_QA=PASS
FULL_440_QA=NOT_REACHED
P4D_IMAGES_ACCEPTED=0
```

The final conversion used Pillow verify/load, controlled centre 16:9 crop, and
Pillow LANCZOS; no stretch, semantic image filtering, deletion, or regeneration
occurred.  The one network-ambiguous slot has no raw/final image and is not
included in the nine-success QA count.

The rebuilt effective inventory is:

```text
CURRENT_VERIFIED_SUCCESS=151
CURRENT_OUTSTANDING=289

ROLE=hard_negative:111, positive:20, ordinary_negative:20
SPLIT=NEW_DESIGN:95, NEW_SCREEN:56
```

Current taxonomy counts are chair_seated_normal_work=15,
crawling_quadruped_support=5, curled_or_partially_occluded_lying=5,
floor_sitting=60, ground_maintenance=1, kneeling_half_kneeling=45,
prone_ground_lying=5, side_lying=5, standing_walking=5, and
supine_ground_lying=5.

## 风险与边界

Mechanical success is not human semantic acceptance or ground truth.  The
remaining 289 slots include the tenth Q6 slot as `COMPLETION_UNKNOWN`; it is
not silently converted to a refusal or a success.
