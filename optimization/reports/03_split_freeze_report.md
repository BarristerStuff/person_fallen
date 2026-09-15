# 03 Split freeze report

## Confirmed facts

- `frozen_splits.csv` and `frozen_manifest.csv` each contain 500 formal media rows.
- Group-disjoint split counts: DEV=310, VAL=100, HOLDOUT=90; groups=50; cross-split groups=0.
- All uncertain rows are in DEV qualitative pool; no uncertain row is in HOLDOUT. Determinate rows: DEV=290, VAL=100, HOLDOUT=90.
- `frozen_splits.csv` SHA-256: `16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a`. `frozen_manifest.csv` SHA-256: `771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6`.
- The current production tool set has no safe split-writing subcommand. Therefore `FORMAL_SPLITS_CSV_UPDATED=false`; `LOCAL_FROZEN_SPLIT_MANIFEST=true` is the P0 source of truth. `03_splits/splits.csv`/shared `splits.csv` was not hand-edited.

## Holdout boundary

HOLDOUT is sealed for this P0: model requests=0 and consumed=false.
