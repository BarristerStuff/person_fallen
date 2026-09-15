# P4D GR3Q8 — partial mechanical QA

| Check | Result |
| --- | ---: |
| New raw / final PNGs | 25 / 25 |
| Pillow failures | 0 |
| Final-dimension failures | 0 |
| Exact duplicate hits | 0 |
| GR1 SHA hits | 0 |
| Foreign-event assets used | 0 |
| Partial mechanical QA | PASS |
| Full-440 QA | NOT_REACHED |
| P4D_IMAGES_ACCEPTED | 0 |

Requested native size was `1536×1024`; every raw PNG was `1672×941`. `NATIVE_SIZE_CONTRACT_ENFORCED=false`; that provenance observation did not trigger a retry. Every final PNG passed Pillow verify/load and is exactly `1920×1080` after controlled center crop and Pillow LANCZOS.

The rebuilt frozen-440 partition is `VERIFIED_SUCCESS=196`, `COMPLETION_UNKNOWN=1`, `SAFE_EXECUTABLE_OUTSTANDING=243`. Current roles: HN=126, POS=50, ordinary-negative=20. Current splits: NEW_DESIGN=120, NEW_SCREEN=76.

