# V7-A1 Stage 2 diagnosis

- Ground images with all primary people classified UPRIGHT: 48.
- Auxiliary images with GEOM_LYING: 36.
- Ground images with GEOM_UNCERTAIN: 1.
- The 48 missed-lying records and per-person features/rule labels are in `missed_lying.json`.
- Skeleton grids: `missed_lying_grid.jpg`, `floor_sitting_grid.jpg`.
- No threshold tuple in the tested grid satisfied G1 and G3 simultaneously; therefore no A1 thresholds were frozen.
- No VLM request was made.
