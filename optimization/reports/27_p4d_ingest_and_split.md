# 27 — P4D formal ingest and internal split

## Dataset validator

Before P4D work the read-only validator reported
`status=valid`, `error_count=0`,
`full_hash_check=True`, and
`warning_count=387`.  After the failed
generation smoke, the same read-only validator reported
`status=valid`, `error_count=0`,
`full_hash_check=True`, and
`warning_count=387`.  This confirms that
the formal dataset was not changed by P4D.

## Ingest and split

- `FORMAL_INGEST_EXECUTED=false`
- `FORMAL_DATASET_MUTATION=false`
- media added: `0`
- labels added: `0`
- post-image P4D manifest: not materialized
- pre-generation group split remains frozen: NEW_DESIGN 265 / NEW_SCREEN 175,
  53 / 35 groups, cross-split groups 0

The planned split is not reported as an image-level final split because no
image passed generation, mechanical QA, or human semantic review.
