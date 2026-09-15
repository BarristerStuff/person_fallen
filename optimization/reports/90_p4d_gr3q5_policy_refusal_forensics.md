# P4D GR3Q5 policy-refusal and provider-failure forensics

Window01 slot `PF_P4D_POS_CURLED_G003_V03` had a completed response with a failed `image_generation_call`, zero images, no image bytes, no native retry, and refusal/safety evidence. It is correctly classified as `CONTENT_POLICY_REFUSAL_CONFIRMED`.

Its adapted Q5 smoke request succeeded. Q5 later stopped on a different slot, `PF_P4D_NEG_CHAIR_G003_V03`, whose raw response contains `HTTP 429` and `usage_limit_reached`; this is `STOPPED_PROVIDER_429`, not a policy refusal.
