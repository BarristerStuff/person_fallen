# Q6 failure-classifier erratum

## 已确认事实

The original Q6 terminal freeze remains valid and immutable.  Its later
post-freeze erratum is the authoritative correction for
`PF_P4D_HN_MAINT_G006_V02`: its raw result was `network_error` with no saved
image and no provable completion, therefore it is `COMPLETION_UNKNOWN`, not a
content-policy refusal.

The source bug was a substring match against `safety` in raw SSE text.  It
wrongly treated the metadata key `safety_identifier` as a provider decision.

## Corrected rule

`provider_failure_classifier_v2.py` ignores `safety_identifier`, `safety_id`,
and metadata field names.  A policy refusal now requires all of: failed
image-generation call, completed response, image_count=0, and explicit refusal
decision text.  A final `network_error` without a provable image result is
always `COMPLETION_UNKNOWN`.
