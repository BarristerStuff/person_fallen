# person_fallen

Archival publication of the `person_fallen` event work, including the optimization
workspace, frozen candidate artifacts, evaluation records, scripts, manifests, and
the event handoff.

## Scope

- `optimization/` is a read-only archival copy of
  `/home/yanbo/net_vlm_person_fallen_v2_optimization`.
- `docs/person_fallen/` contains the event handoff from the working repository.
- Historical candidate outcomes are preserved as recorded. In particular,
  `V6-A0-TARGET-SUPPORT-CONFIG` remains rejected after its real Pilot gate failed;
  this repository does not claim a production winner.
- This archive contains synthetic-development artifacts and does not establish
  real-camera, video, robot, localization, or production accuracy.

## Publication boundary

The target GitHub repository is public. Do not treat this archive as a private
workspace or as a sealed validation store. The source records may contain
internal endpoint names/addresses and local-path references because they are
preserved as evidence. Synthetic images and historical evaluation artifacts are
included as event material; consumers must not use them as a fresh independent
validation set.

Generated Python bytecode and volatile SQLite WAL/SHM/journal sidecars are not
source/evidence records and are intentionally excluded. No access token or
private key is included.

## Current status at publication

- Candidate: `V6-A0-TARGET-SUPPORT-CONFIG`
- Current winner: `NONE`
- V6 status: `V6_A0_PILOT_FAIL`
- Production integration: not ready
- Git commit in the production repository: none for this event
- Holdout consumed: `false`
