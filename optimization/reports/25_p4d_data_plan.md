# 25 — P4D data plan and pre-generation freeze

## Status

- `P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION`
- `P4D_STATUS=GENERATION_REQUIRED`
- `P4D_PROMPT_PACK_READY=true`
- `P4D_NEW_LINEAGE=true`
- Split was frozen before prompt generation and before any image request/model view.

## Frozen plan

| role | images | groups | NEW_DESIGN | NEW_SCREEN |
|---|---:|---:|---:|---:|
| hard_negative | 300 | 60 | 180 | 120 |
| positive | 100 | 20 | 60 | 40 |
| ordinary_negative | 40 | 8 | 25 | 15 |
| total | 440 | 88 | 265 | 175 |

The group freeze has 53 DESIGN groups, 35 SCREEN groups, five prompt-lineage
images per group, and `cross_split_group_count=0`.  The exact taxonomy quotas
and complete English prompt files are in the frozen prompt manifest and pack.

## Hashes

- group manifest: `11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab`
- group split freeze: `b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843`
- prompt manifest: `e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb`
- prompt pack: `8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250`
- prompt pack freeze: `385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b`

The old batch `/home/yanbo/下载/batches/batch_person-fallen-v2-camera1p5m` was
not used as a source or reference.  The new batch path is
`/home/yanbo/下载/batches/batch_person-fallen-v2-p4d-hardneg-rev1-camera1p5m` and is development-only.
