# 02 Ingest report

## Confirmed facts

- Pre-ingest validator: `valid`, errors=0, full hash check=true, warnings=387; pre counts media=3701, labels=3701, batches=40, splits=2058.
- All 50 group-level media dry-runs passed (500 planned new media; no duplicate reuse). Official `ingest_media.py add` completed 50 transactions, adding 500 media; official `add-label` completed 500 prompt-derived V2 labels (all review status `unreviewed`).
- Post-ingest: media=4201, labels=4201, batches=41, splits=2058. New person_fallen media=500 and labels=500; roles={'positive': 200, 'negative': 100, 'hard_negative': 180, 'uncertain': 20}; version set={v2.0}. Other event label counts remained: dangerous_weapon_present=199, evacuation_indicator_light_noncompliant=187, fire_equipment_noncompliant=1288, garbage_present=184, open_flame_present=1186, person_smoking=164, water_accumulation=493.
- Formal validator after ingest: status=valid, error_count=0, warning_count=387, full_hash_check=True.
- `rebuild_review_links.py` completed with conflict_count=0 and error_count=0; it created 1386 missing review links (including historical links that the tool found missing).

## Boundary

No shared annotation CSV was manually edited or wholesale-overwritten.
