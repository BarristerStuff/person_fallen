# person_fallen Codex ingest audit

This is a SHA- and frozen-remap-derived inventory. No unified-dataset write, provider request, Holdout access, model inference, or production-project change was performed.

## Formal v3 remap

- V3_DEV=436; V3_SCREEN=76; V3_VAL=100; total=612.
- Existing V2 source images valid on disk: 500.
- Clean Codex P4D images valid on disk: 202.
- person_fallen images on disk (V2 original + clean P4D): 702.

## P4D disposition

- Codex ledger successes: 232 (clean=202, binding-blocked=30).
- completion-unknown=1; failed-confirmed=1; terminal not-started=23; other unexecuted/not-clean=183.
- Clean already in unified dataset by SHA: 0; clean pending as new media: 202; clean pending reuse existing media: 0.

## Current formal-ingest gate

**BLOCKED — no mutation performed.** The requested new labels must be `event_definition_version=v3.0`, but the current official `ingest_media.py add-label` derives `person_fallen` as `v2.0`, and `validate_dataset.py` rejects any other version. Writing via that command would silently create v2.0 labels; hand-writing v3.0 would fail validation. A separately authorized versioned-dataset-tool change is required before the official dry-run and ingest can proceed.

## Evidence

- Detailed row audit: `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/person_fallen_codex_ingest_audit.csv`
- Frozen clean manifest: `/home/yanbo/net_vlm_person_fallen_v2_optimization/10_fast_close/fast_close_clean_manifest.csv`
- Frozen v3 remap: `/home/yanbo/net_vlm_person_fallen_v2_optimization/11_person_fallen_v3_revision/remap/person_fallen_v3_remap_manifest.csv`
