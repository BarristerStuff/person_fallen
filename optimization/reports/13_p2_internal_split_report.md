# P2 internal DESIGN / SCREEN split report

## Status

```text
STAGE=P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION
P2_PREFLIGHT=PASS
P2_INTERNAL_SPLIT_STATUS=PASS
P2_SCREEN_BLIND_BEFORE_CANDIDATE_FREEZE=true
P2_FORENSIC_SOURCE=DESIGN_ONLY
VAL_ERRORS_USED_FOR_PROMPT_DESIGN=false
HOLDOUT_REQUESTS=0
```

## Preflight facts

The formal dataset was revalidated read-only with the current supported CLI (`tools/validate_dataset.py --json`). The prompt-specified `ingest_media.py validate --json-output` form is not an available command in this checkout; this interface difference was recorded rather than treated as a dataset failure.

The actual validator result was `status=valid`, `error_count=0`, `full_hash_check=true`, `warning_count=387`, `media_count=4201`, and `label_count=4201`. The 387 warnings are unchanged historical warnings.

The model identity check returned Ollama `0.23.2` and `qwen3.5:4b` digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.

All required historical hashes matched their recorded values:

```text
P0 prompt                         b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4
frozen_splits.csv                16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a
frozen_manifest.csv              771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6
P1A DEV predictions              5d67e80d753ed71ae33cf9c222a8793b829c60a0bc1ff5ee09085518bf9d359b
P1A DEV manifest                 7f8ff256a8da3cc6451e1ec3f6a842dc9b3eb6f4080e4fb5a1a49dda9bc7d7d8
P1R recovery VAL manifest        f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762
P1R recovery VAL predictions     7f221795f9a21febd47d5861ee58492dbef6eb00a1032ea240bc1c536de1e38b
```

## Deterministic internal split

The original DEV was not re-split. Its 31 groups were assigned once by a deterministic role-stratified hash procedure, without splitting a group:

| Internal role | Groups | Rows | Positive | Ordinary negative | Hard negative | GT uncertain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P2_DESIGN | 19 | 190 | 70 | 40 | 70 | 10 |
| P2_SCREEN | 12 | 120 | 50 | 20 | 40 | 10 |

```text
CROSS_DESIGN_SCREEN_GROUPS=0
P2_DESIGN_MANIFEST_SHA=f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1
P2_SCREEN_MANIFEST_SHA=ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5
P2_INTERNAL_SPLIT_SHA=a9edfb22fc0170ce774dfe5e6229bf776c8c272868b55c303e74ae629b153892
```

Before the candidate freeze, the program recorded `p1a_prediction_rows_read_before_split=0` and `val_individual_rows_read_before_split=0`. Only aggregate role/group counts were used to construct the split. The nine-image protocol canary was also selected from DESIGN only.

## Governance interpretation

The split is intentionally approximate to the requested 60/40 ratio at group level. Group isolation takes priority over exact row percentage. SCREEN remained blind to individual prediction, evidence, image, prompt, FP identity, and taxonomy information until `candidate_freeze.json` existed and its independent verifier passed.

## Evidence

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/00_preflight/source_hash_inventory.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/00_preflight/model_identity.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/01_internal_split/p2_internal_split.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/01_internal_split/p2_internal_split_verification.json`
