# V6-A0 direct evaluation

Pilot 156 completed with 156 valid strict JSON responses and 156/156 source bindings. The pilot gate failed: floor sitting produced 5 immediate ALERTs, crawling produced 1 ALERT, and the five multi-person rows produced only 4 ALERTs. Ground lying was 59 ALERT plus 1 RECHECK, so its coverage was 60/60 and immediate ALERT recall was 59/60, meeting the minimum 57/60.

Per protocol, Known Regression, Full Remaining, Full DEV aggregation, production integration, and Git commit were not run. Total new model requests: 156. VAL/Holdout/V6 requests outside this pilot: zero.

The semantic candidate remains unchanged and rejected for this execution. `CURRENT_WINNER=NONE`, `OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED`, `REAL_CAMERA_VALIDATED=false`, and `PRODUCTION_INTEGRATION_READY=false`.
