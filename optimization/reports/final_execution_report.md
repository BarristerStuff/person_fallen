# Final execution report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
SOURCE_MAPPING_STATUS=PASS
GT_BUILD_STATUS=COMPLETE
DATASET_INGEST_STATUS=COMPLETE
DATASET_VALIDATION_STATUS=valid
SPLIT_FREEZE_STATUS=COMPLETE
FORMAL_SPLITS_CSV_UPDATED=false
LOCAL_FROZEN_SPLIT_MANIFEST=true
HOLDOUT_CONSUMED=false
HOLDOUT_REQUESTS=0
P0_NAME=P0_IMAGE_BASELINE_V2
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P0_MODEL=qwen3.5:4b
P0_ENDPOINT=http://192.168.20.62:11434
P0_PRIMARY_SOURCE=ai_generated
P1_EXECUTED=false
PRODUCTION_CODE_MODIFIED=false
ROBOT_CHAIN_STARTED=false
SSH_OLLAMA_TUNNEL_USED=false
```

## Confirmed facts

- Images/prompts: 500/500; mapping PASS; exact duplicates=0; dHash near-duplicate candidate groups=0.
- Roles: positive=200, negative=100, hard_negative=180, uncertain=20.
- Formal additions: media=500, labels=500; media IDs `IMG_003702` through `IMG_004201`; validator valid with 0 errors and full hash check.
- Frozen split: DEV=310, VAL=100, HOLDOUT=90; HOLDOUT is unconsumed.
- P0 executed 410 calls with HTTP 100%, but JSON/schema 0% because all model JSON appeared in `thinking` instead of empty `response`; no valid classification metric exists.

## Reasoned conclusion

The data ingestion and split freeze are complete, but the P0 model-output contract failed. The next technically justified step is a separately versioned DEV-only protocol-control study, not accuracy tuning, higher resolution, crop/ROI, or holdout use.

## Unverified

No conclusion about robot real-camera accuracy, production safety-inspection accuracy, or real-world generalization follows from this AIGC-only dataset or failed protocol run.
