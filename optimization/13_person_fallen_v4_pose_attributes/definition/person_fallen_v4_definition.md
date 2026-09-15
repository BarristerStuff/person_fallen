# `person_fallen` v4.0 development definition

## Identity and scope

- `event_name=person_fallen`
- `event_definition_version=v4.0-development-only`
- semantic name: `ground-person safety attention`
- modality: image-first attributes with optional short temporal confirmation

This revision detects visible posture and support relationships. It does not
infer whether a fall happened, injury, consciousness, intent, or cause.

## Operational outcomes

### `ALERT_GROUND_LYING`

Use only for a clear ground-lying posture on a non-rest support surface:

- supine, side-lying, prone, or curled lying; or
- the torso is approximately horizontal and a broad torso area is supported
  by the floor.

Pelvis contact with the floor alone is never sufficient evidence.

### `ATTENTION_NEAR_GROUND`

Use for clear crawling, push-up, plank, or another unusual near-ground posture
that is not a clear lying alarm. This is a lower-priority attention state, not
the high-priority ground-lying alarm.

### `NO_ALERT_NORMAL_POSE`

Use for a clearly visible normal pose, including:

- standing, walking, chair sitting, floor sitting, kneeling, squatting,
  crouching, bending, or picking up an object;
- normal lying on a bed, sofa, recliner, or other clear rest support;
- explicit maintenance, repair, construction, installation, or cleaning with
  visible tools, materials, work objects, or an unambiguous work relationship.

Normal floor sitting includes legs extended, bent, or crossed; leaning back;
one or both hands supporting the body; or the back touching a wall. It remains
floor sitting when the pelvis is the primary lower support, the head/shoulders
are visibly above the hips, and the torso is not broadly flat on the floor.

The following are not alarm evidence by themselves:

- hands touching the floor;
- legs extended;
- leaning backward;
- sitting in a corridor, workshop, warehouse, or parking area;
- the pelvis touching the floor.

### `RECHECK_VISUAL_UNCERTAIN`

Use when image quality is insufficient, no reliable person crop exists, or
the attributes conflict (for example, `floor_sitting` together with a
horizontal, broadly floor-supported torso). This result requests another
frame/view; it is never silently mapped to `NO_ALERT_NORMAL_POSE`.

## Ground-truth boundary

The v4 diagnostic inherits frozen v3 DEV taxonomy and
`GT_TYPE=PROMPT_DERIVED_SYNTHETIC_GT`. Model output never creates or changes
GT. A separate human-observed pixel-level benchmark is required before any
real-camera or production claim.

