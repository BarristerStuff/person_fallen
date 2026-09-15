# P4D GR3Q8 — preflight and authority binding

Q8 verified the Q7 terminal freeze SHA-256 `9adc539e0b55a9207111b025bebdefcc4951760616b83f9680f91df28ef5aaf9`, with matching sidecar and 78/78 bound artifacts. It rebuilt the frozen-440 partition as 171 verified successes, one completion-unknown quarantine, and 268 safe outstanding slots; the sets were pairwise disjoint and exhaustive.

`PF_P4D_HN_MAINT_G006_V02` remained quarantined with no resend and Q8 made zero MAINT_G006 requests. The provider gate resolved `codex/gpt-5.4/image_generation`, runtime 0.7.3, `CODEX_SAFE_STAGED_CV_V1`, concurrency 1 and outer retry false. The shared dataset validator was read-only, valid, zero-error and full-hash true. Classifier V2 SHA-256 `fbd773b5d5d131f06abd334e041377fc5e0c7b9c0e5e6179164979c2abb624c0` regression is 3/3 PASS.

