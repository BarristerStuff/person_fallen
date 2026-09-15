# P4D GR3Q7 — partial mechanical QA

The Q7 execution produced 20 native PNGs and 20 final PNGs.  Every success followed native PNG → Pillow `verify/load` → controlled 16:9 center crop → Pillow LANCZOS → final 1920×1080 PNG.

The provider returned raw `1672×941` PNGs even though the request size was `1536×1024`.  All final outputs are exactly `1920×1080`; the frozen QA field `dimension_failures=0` refers to those final deliverables and must not be read as a verified raw-size match.

| Check | Result |
| --- | ---: |
| New raw / final | 20 / 20 |
| Pillow failures | 0 |
| Dimension failures | 0 |
| Exact SHA duplicate hits | 0 |
| GR1 SHA hits | 0 |
| Adapter provenance | PASS |
| Partial mechanical QA | PASS |
| Full-440 QA | NOT_REACHED |
| P4D_IMAGES_ACCEPTED | 0 |

The rebuilt frozen-440 partition is disjoint and exhaustive: `VERIFIED_SUCCESS=171`, `COMPLETION_UNKNOWN_QUARANTINED=1`, and `SAFE_EXECUTABLE_OUTSTANDING=268`.  The sole unknown remains `PF_P4D_HN_MAINT_G006_V02`; no resend occurred.

Current role distribution is hard-negative 116, positive 35, ordinary-negative 20.  Current split distribution is NEW_DESIGN 105 and NEW_SCREEN 66.  These are inventory/provenance counts, not human semantic acceptance results.

Evidence: [mechanical QA JSON](/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_04_gr3q7_authorized_20260831_01/06_partial_qa/partial_qa.json).
