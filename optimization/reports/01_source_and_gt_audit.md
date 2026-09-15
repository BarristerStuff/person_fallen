# 01 Source and GT audit

## Confirmed facts

- Source: `/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m`; images=500, prompts=500; one-to-one mapping status **PASS**.
- All images passed Pillow integrity checks. Exact duplicate files=0; dHash near-duplicate candidate groups=0.
- Prompt-derived GT counts: positive=200, negative=100, hard_negative=180, uncertain=20, across 50 prompt/scenario groups.
- GT basis for every row: `user_confirmed_prompt_image_alignment`. It is not independent human visual review and no VLM created GT.
- Generation manifest identifies provider `ebondai`, model/version `gpt-image-2`, batch `batch_person-fallen-v2-camera1p5m`, generation date 2026-08-26 and simulated camera height about 1.5m. Seed was unavailable for all 500 items (`unknown`); metadata completeness is false if seed is required, otherwise documented source metadata fields are present.

## Reasoned interpretation

Prompt declarations and full scene semantics are sufficient for the user-authorized prompt-derived GT, but not for a claim of independent visual review.

## Unverified

Real camera/robot/production generalization is not measured by this AIGC batch.
