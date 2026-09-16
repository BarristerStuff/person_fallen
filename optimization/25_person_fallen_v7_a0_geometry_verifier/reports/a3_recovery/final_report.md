# V7-A3-R1 recovery result

`FINAL_STATUS=V7_A3_PILOT_ALREADY_IRREVERSIBLY_FAILED`

The interrupted artifacts were pushed and verified at commit `f016d613c46291967365a2b01458c90c29f15e40`. Zero-request provenance audit classified the 110 historical records as `REUSE_LEVEL=C`: the simplified ledger does not prove the required request-time source, crop, timestamps, raw-response inventory, model/options, semantic, policy, or runner bindings. Therefore no recovery freeze was created and no historical row was reused as formal Pilot evidence.

Zero-inference replay of the observed A3 output found irreversible failures before any new request:

- floor_sitting ALERT: 7
- pushup_plank ALERT: 1 (`V2_ORIGINAL::IMG_003794`)
- crawling ALERT: 1 (`V2_ORIGINAL::IMG_003804`)

Under the frozen image aggregation, later P2 cannot downgrade an existing image ALERT. Pilot recovery, Regression, and Full DEV were therefore stopped. New Ollama requests: 0. VAL/Holdout requests: 0.
