# P4D cross-revision summary

P4D did not reach image intake or C3 inference.  It therefore has no new
classification, taxonomy, group, latency, or protocol metrics.  The one
provider smoke request failed before an image was produced (`HTTP 401`,
`INVALID_API_KEY`).  Historical P2/P3 results remain in their immutable
reports and are not relabeled as P4D results.

| revision | data lineage | C3/Candidate execution | classification metrics | status |
|---|---|---:|---|---|
| P2 | prior formal V2/AIGC | complete on prior data | historical P2 reports | quality threshold fail |
| P3 | prior P2 design/screen | complete on prior data | historical P3 reports | no winner |
| P4D | new text-to-image plan; no images generated | 0 requests | N/A | GENERATION_REQUIRED |

No P4D sample was used to modify Prompt, GT, parser, threshold, preprocessing,
or the formal dataset.  `NEW_VAL_REQUESTS=0`, `HOLDOUT_REQUESTS=0`, and
`HOLDOUT_CONSUMED=false`.
