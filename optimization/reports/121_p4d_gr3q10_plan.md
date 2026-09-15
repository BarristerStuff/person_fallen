# P4D GR3Q10 deterministic plan

- revision: P4D_GR3Q10_BALANCED_COMPLETE_GROUP_WINDOW_20260901_01
- planned logical invocations: 30
- planned physical-attempt lower-bound cap: 36
- concurrency: 1; outer retry: false; native max retries: 3
- role balance: HN20 / positive5 / ordinary-negative5
- split balance: NEW_DESIGN20 / NEW_SCREEN10
- selected complete groups: PF_P4D_HN_MAINT_G002, PF_P4D_HN_PLANK_G002, PF_P4D_HN_CRAWL_G002, PF_P4D_HN_SQUAT_G005, PF_P4D_POS_INTENTIONAL_G002, PF_P4D_NEG_STAND_G001
- plan SHA-256: 66d79a5d0453b8c7b223f9cd8997b284ff936791421477629316bfc15ae55590
- authorization SHA-256: 56a6642448db4143bda77fc66d708097078dd730fa15720c7827608d3cc07bf5
- run-config SHA-256: fac1469c132476ca04d900e5b1991b721f98ad0e0a166f0103483b11eb916b64
- runner SHA-256: a20d561a227ba6666bdb1c8a1907b9080b358577b2c3735f6feef68d2f59ad11

Selection rationale: deterministic_complete_group_balance_v1; four hard-negative taxonomy groups plus one positive and one ordinary negative group; target HN20/POS5/ORD5 and NEW_DESIGN20/NEW_SCREEN10

No Q9 slot, no completion-unknown slot, and no cross-group or cross-split slot is selected. The render prompt bytes come from the frozen adapter manifest and each row's UTF-8 byte hash is checked before execution.
