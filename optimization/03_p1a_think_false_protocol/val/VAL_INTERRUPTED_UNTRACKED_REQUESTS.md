# P1A VAL interruption record

P1A VAL was stopped immediately after discovery that the preceding DEV freeze artifact declared an incorrect DEV manifest hash. This is a permanent P1A audit record; it is not a resumable checkpoint.

- The runner emitted `VAL_P1A_PROGRESS=10/100`, so ten requests completed successfully before interruption.
- `IMG_004112` has a preprocessing artifact, showing that an eleventh request was prepared and was in-flight when interruption occurred. Its server-side completion cannot be established from a persisted client response log.
- No `predictions.csv`, `raw_responses.jsonl`, `request_log.jsonl`, or `summary.json` was committed for this incomplete VAL attempt. Therefore the exact number of server-accepted VAL requests is **at least 10 and at most 11**, and no semantic metric may be calculated from this attempt.
- Do not rerun the 100 VAL samples as P1A. Any future use requires a separately named, explicitly frozen recovery/revision protocol with this exposure recorded.
- HOLDOUT was not selected, processed, or requested.
