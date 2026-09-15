# V5-B0 remaining47 diagnostic

The 47 mechanically missing DEV rows were completed once using the frozen V5-B0 prompt, schema, policy, views, and model parameters. The 389 existing results were reused only after raw-response parser/policy replay.

Result: 436/436 unique DEV rows, 47/47 new requests completed, 0 unknown, no retries. Ground-lying was 145/145 ALERT and normal-negative immediate ALERT was 0/230. Floor sitting was 0 ALERT, 5 RECHECK, 50 NO_ALERT.

The candidate remains rejected. Auxiliary attention produced 3 high-priority ALERTs (push-up/plank 2, crawling 1), violating the 0/41 gate. Visual-uncertain also produced 5 ALERTs and is reported separately, not folded into normal-negative FPR. The original V5-B0 early-stop failure remains unchanged.

New-request latency p50/p95/p99: 17.941/22.086/27.506 seconds. New eval_count min/max/mean: 11/470/166.979. People-count distribution: 0=7, 1=358, 2=44, 3=27; scene coverage complete=429, incomplete=7; bbox-null=0. `OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED`.

No VAL, Holdout, V6, production, or Git activity occurred. `CURRENT_WINNER=NONE`; production integration is not ready. Recommended direction is B: treat the broad auxiliary/uncertain error pattern as evidence that the current method does not meet the target, rather than stacking unsupported fields or relaxing gates.
