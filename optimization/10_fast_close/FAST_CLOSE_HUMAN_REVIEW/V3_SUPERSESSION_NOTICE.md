# v3.0 supersession notice

status=SUPERSEDED_FOR_V3_BY_PROMPT_DERIVED_GT_POLICY
event_name=person_fallen
event_definition_version=v3.0

This notice is additive only. The existing `review_manifest.csv`, `index.html`,
`review_instructions.md`, and `package_status.json` are preserved unchanged as
v2.0 fast-close evidence. They are not v3.0 formal ground truth.

For the isolated v3.0 lifecycle, the formal synthetic development/screening
ground truth is derived from the frozen generation prompt and planned role
mapping. Per-image human semantic review is not a required gate for v3.0.
`model_prediction_used_as_gt=false` remains mandatory. Human review, if later
performed on this package, is supplementary audit evidence only and cannot
rewrite v2.0 history or become v3.0 ground truth without a separately
authorized, self-consistent lifecycle.

The v3.0 lifecycle also supersedes the v2.0 fast-close requirement to continue
the 440-slot P4D generation. No Q10/Q11 continuation, completion-unknown
resend, failed-slot resend, or further P4D generation is authorized by this
notice.
