# person_fallen v4 pose-attribute diagnostic

`revision_id=PERSON_FALLEN_V4_POSE_ATTRIBUTES_20260908_01`

This is a new isolated development revision. It does not modify or reinterpret
the frozen v3.0 definition, GT, prompts, metrics, terminal status, SCREEN, VAL,
or Holdout state.

The pipeline deliberately separates:

1. a frozen generic person detector used only to create a full-body crop;
2. one qwen3.5:4b perception call returning visible pose attributes only;
3. deterministic business-policy mapping;
4. a deterministic short-term recheck state machine.

The first diagnostic is limited to 110 frozen DEV rows selected without model
predictions: all 55 `floor_sitting` rows plus 55 clear lying rows selected by
fixed taxonomy quotas. The GT remains `PROMPT_DERIVED_SYNTHETIC_GT`; therefore
the diagnostic cannot establish real-camera or production accuracy.

No SCREEN, VAL, Final Holdout, image generation, GT rewrite, shared-dataset
write, or production-project write is permitted by this revision.

