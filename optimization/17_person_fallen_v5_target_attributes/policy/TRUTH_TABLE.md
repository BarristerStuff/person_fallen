# V5-B0 deterministic target and scene truth table

Contract validation must succeed before these rules. Invalid JSON/keys/enum/bbox/IDs is a terminal protocol error, NOT a valid RECHECK model response. No history, GT, bbox aspect ratio or evidence text is read by decision logic. New person records are model-enumerated targets; no per-person YOLO detection coverage is claimed.

## Per-person: first matching row wins

| Priority | Exact condition | Decision / reason family |
|---|---|---|
| 1 | person_visible != yes OR visual_quality != clear OR bbox_1000 is null | RECHECK: TARGET_EVIDENCE_UNRELIABLE |
| 2a | support_surface != floor AND torso_ground_contact = broad | RECHECK: nonfloor vs ground-contact conflict |
| 2b | pose=chair_sitting AND support_surface=floor | RECHECK: chair/floor conflict |
| 2c | support_surface=chair AND pose in {supine,side_lying,prone,curled_lying,crawling,pushup_plank,floor_sitting,kneeling,squat_crouch,other_near_ground} | RECHECK: ground-pose/chair conflict |
| 2d | pose in {standing,walking,kneeling,squat_crouch,bending,floor_sitting,chair_sitting} AND contact=broad | RECHECK: normal pose/broad torso contact conflict |
| 2e | pose=floor_sitting AND (head_shoulders_above_hips=no OR orientation=horizontal) | RECHECK: floor-sitting head/axis conflict |
| 2f | pose in {standing,walking,kneeling,squat_crouch,chair_sitting} AND orientation=horizontal | RECHECK: normal-pose axis conflict |
| 2g | pose in {supine,side_lying,prone,curled_lying} AND orientation=upright | RECHECK: lying/upright conflict |
| 2h | pose in {supine,side_lying,prone,curled_lying} AND surface=floor AND contact=none | RECHECK: lying without torso ground contact |
| 2i | pose in {crawling,pushup_plank} AND contact=broad | RECHECK: auxiliary/broad-contact conflict |
| 3 | support_surface=unknown | RECHECK: unresolved support |
| 4 | support_surface=bed_sofa, after preceding gates | NO_ALERT: this target's normal rest support |
| 5 | explicit_work_evidence=yes, after preceding gates | NO_ALERT: this target's visible work context only |
| 6 | pose=floor_sitting AND surface=floor AND head=yes AND orientation in {upright,inclined} AND contact in {none,partial} | NO_ALERT: consistent seated pelvis support |
| 6b | pose=floor_sitting but row 6 not satisfied | RECHECK |
| 7 | pose=chair_sitting AND surface=chair AND orientation in {upright,inclined} AND contact in {none,partial} | NO_ALERT |
| 7b | pose=chair_sitting but row 7 not satisfied | RECHECK |
| 8 | pose in {standing,walking,kneeling,squat_crouch} AND surface=floor AND orientation in {upright,inclined} AND contact in {none,partial} | NO_ALERT |
| 8b | pose=bending AND surface=floor AND orientation in {upright,inclined,horizontal} AND contact in {none,partial} | NO_ALERT |
| 8c | one of row 8/8b poses but its conjunction not satisfied | RECHECK |
| 9 | pose in {crawling,pushup_plank} AND surface=floor AND orientation in {inclined,horizontal} AND contact in {none,partial} | ATTENTION |
| 9b | row 9 pose but its conjunction not satisfied | RECHECK |
| 10 | pose in {supine,side_lying,prone,curled_lying,other_near_ground} AND surface=floor AND orientation=horizontal AND contact=broad | ALERT: specific horizontal ground-supported torso |
| 11 | all other combinations, including pose=unknown without earlier explicit rest/work context | RECHECK |

`head_shoulders_above_hips=yes` is not a universal veto on lying: an elevated head does not itself contradict an otherwise horizontal broadly ground-supported torso. For sitting, however, head=yes is required. `explicit_work_evidence=unknown` does not imply confirmed work and does not veto otherwise consistent posture; `no` and `unknown` both proceed to posture rules. All bbox coordinate values are ignored for posture classification after mechanical legality; only null vs non-null enters the target evidence gate.

## Scene aggregation: first matching row wins

1. Any target ALERT -> image ALERT, regardless of other normal/uncertain targets or coverage.
2. Otherwise people empty OR any target RECHECK OR scene_coverage != complete -> image RECHECK.
3. Otherwise any ATTENTION -> image ATTENTION.
4. Otherwise all targets normal -> image NO_ALERT.

Thus one worker/resting person cannot veto another lying person's ALERT. Incomplete coverage cannot clear a reliable ALERT. Complete coverage does not mean all target poses are known. Empty output is not a shortcut to NO_ALERT.
