# 26 — P4D generation and intake audit

## Capability and generation outcome

The configured and previously used image provider was `ebond-gpt-image-2`
(`https://api.ebondai.com/v1`) with model `gpt-image-2`, native request size
1536x1024 and quality `medium`.  One explicitly bounded smoke request was
made for `PF_P4D_HN_SIT_G001_V01`.  The provider returned HTTP 401 with
`INVALID_API_KEY` / `Invalid API key`; the CLI return code was
`1` and no output image file was
accepted.  Automatic retry and provider switching were disabled.

| measure | result |
|---|---:|
| planned prompt slots | 440 |
| generation attempt rows | 1 |
| successful generation attempts | 0 |
| failed generation attempts | 1 |
| raw successful images | 0 |
| accepted images | 0 |
| rejected images | 0 |
| exact image duplicates | 0 (not run; no bytes) |
| near-duplicate groups | N/A (not run; no bytes) |
| image metadata completeness | N/A (not run; no images) |
| prompt metadata completeness | 440/440 |
| human semantic review | not started |

Evidence is preserved at `/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m/generation_attempts.csv`, `/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/cli_logs/PF_P4D_HN_SIT_G001_V01.stdout.json`, and
`/home/yanbo/net_vlm_person_fallen_v2_optimization/08_p4d_new_hard_negative_dev_revision/02_generation/provider_results/PF_P4D_HN_SIT_G001_V01.json`.  The single failed smoke is not counted as a successful
440-image generation and is not hidden.

## Intake gate

Mechanical QA is `NOT_RUN_NO_IMAGES`; formal ingest is not eligible.  No image
was decoded, accepted, rejected, or assigned a formal media ID.  No model
prediction was used as ground truth.
