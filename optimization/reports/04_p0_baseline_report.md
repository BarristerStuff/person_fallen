# 04 P0 baseline report

## Execution status

`P0_IMAGE_BASELINE_V2` executed all planned DEV/VAL requests (DEV=310, VAL=100, HOLDOUT=0) against `http://192.168.20.62:11434`, model `qwen3.5:4b`, single concurrency, letterbox 448x336, JPEG quality 70. P0 prompt SHA-256 is `b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4`.

## Confirmed protocol outcome

- HTTP success=100% (410/410); first-attempt success=100%.
- JSON parse success=0% (0/410); schema success=0% (0/410); canonical prediction success=0% (0/410).
- Every failure has the same evidence: the Ollama outer JSON placed the requested object in `thinking`, while `response` was an empty string. The strict P0 parser accepts only the required JSON object in `response`; it did not extract or backfill reasoning text.
- Thus every request is a protocol failure, not a negative prediction. Classification metrics TP/FP/TN/FN and Precision/Recall/F1/Accuracy/FPR are **not available**. `hard_negative_fpr` and model uncertain rate are likewise not available.
- Measured transport response latency across all HTTP-successful requests: cold=6.675069s, post-cold mean=1.582012s, P50=1.546396s, P95=1.793916s, max=3.517867s. These are protocol-failed transport observations, not a valid P0 classification-latency baseline.
- `HOLDOUT_REQUESTS=0`; `HOLDOUT_CONSUMED=false`.

## Quality gate

The required JSON/schema rate of 1.0 was not met. P0 is recorded as `COMPLETE_PROTOCOL_FAILURE`; no prompt/config change or rerun occurred in this P0.

## Recommended next stage

A separately versioned P1 protocol investigation may test a documented reasoning-disable/response-channel control (for example an Ollama-compatible `think=false` request only after verifying server support) and must use DEV only for development before any new frozen evaluation.
