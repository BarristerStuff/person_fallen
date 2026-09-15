# `person_fallen` V4 operational definition

Revision: `PERSON_FALLEN_V4_OPERATIONAL_FREEZE_20260909_01`

Candidate: `V4-A0-FULL-CROP`

Event definition version: `v4.0-operational-high-priority`

This is a new operational business freeze. It does not overwrite the frozen
v3.0 definition, v3 metrics, v4 development prototype, GT, remap, or any
historical status.

## High-priority `person_fallen`

`ALERT_GROUND_LYING` means visible evidence supports one of the following:

- clear supine lying on the floor;
- clear side-lying on the floor;
- clear prone lying on the floor;
- clear curled, sprawled, or otherwise horizontal ground-lying posture;
- torso approximately horizontal with a broad torso area supported by the floor;
- an obviously collapsed posture that cannot maintain a normal upright,
  seated, kneeling, crouching, bending, or walking posture.

The model must not infer that a fall happened, that a person is injured,
unconscious, or in danger. The operational event is a visible posture/support
condition for robot safety inspection.

## Required `NO_ALERT_NORMAL_POSE`

The following are not high-priority `person_fallen`:

- normal floor sitting;
- chair sitting;
- standing or ordinary walking;
- kneeling or half-kneeling;
- squatting or crouching;
- bending or picking something up;
- explicit maintenance, repair, construction, installation, or cleaning;
- normal lying or resting on a bed, sofa, recliner, or other rest support.

Maintenance requires visible work evidence such as tools, a toolbox,
materials, a dismantled or operated object, a visible work action, or a clear
person-to-work-object relationship. Proximity to equipment alone is not enough.

## Auxiliary low-priority result

`crawling`, `push-up`, and `plank` are not part of the high-priority binary
`person_fallen` gate. When visible and unambiguous, they map to
`ATTENTION_NEAR_GROUND`, an auxiliary low-priority result. They are neither
counted as high-priority `person_fallen` TP nor high-priority FN.

The auxiliary result is retained for downstream robot behavior and monitoring,
but it cannot change the high-priority gate.

## `RECHECK_VISUAL_UNCERTAIN`

Use `RECHECK_VISUAL_UNCERTAIN` whenever the evidence is insufficient or
conflicting, including a person that is too small, heavily occluded, severely
blurred, only partly visible, or not reliably detectable. A recheck is not
silently counted as `NO_ALERT`; for a ground-lying sample it contributes to
the required `ALERT+RECHECK` safety coverage.

## Frozen implementation contract

The V4-A0 implementation is frozen as a perception/policy cascade:

1. fixed YOLO11n COCO person crop preparation;
2. fixed full-scene plus largest-person crop views;
3. fixed qwen3.5:4b attribute-only JSON Prompt;
4. fixed deterministic attribute-to-decision policy;
5. fixed short-term recheck state machine for deployment integration.

The VLM output is never used to create or alter ground truth. Existing split
manifests retain their original prompt-derived synthetic GT and provenance.

## Operational gates

For each legal split, report separately:

- ground-lying immediate `ALERT` recall: at least `0.95`;
- ground-lying `ALERT+RECHECK` coverage: exactly `1.0`;
- floor-sitting immediate `ALERT` FPR: exactly `0` when the split contains
  floor-sitting rows;
- all determinate-negative immediate `ALERT` FPR: exactly `0`;
- strict JSON success: exactly `1.0`.

`ATTENTION_NEAR_GROUND` does not enter the high-priority binary numerator or
denominator. It is reported separately.

This freeze is synthetic-data development/validation evidence only. It does
not by itself establish real-camera or production accuracy.
