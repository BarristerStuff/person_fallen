# P2L historical latency forensics

## Status

```text
STAGE=P2L_REMOTE_LATENCY_FORENSICS
P2L_HISTORICAL_SOURCE=P2_C3_RAW_RESPONSES_AND_REQUEST_LOGS
P2L_NEW_VAL_REQUESTS=0
P2L_HOLDOUT_REQUESTS=0
HISTORICAL_PRIMARY_LATENCY_COMPONENT=load_duration
HISTORICAL_HIGH_LOAD_THRESHOLD_SECONDS=5.0
```

This report was recomputed from the P2 C3 raw response JSONL and request-log JSONL, not from `summary.md` and not from predictions/evidence. P2 history was not rewritten. Duration fields from Ollama nanoseconds are retained in the per-request CSV and converted to seconds for statistics. `client_latency_seconds` is the runner's HTTP timing; `wall_span_seconds` is also retained because the runner records its start marker before local preprocessing.

## Historical counts and component statistics

| Dataset | Requests | High-load (>5s) | Client P50/P95 | Ollama total P50/P95 | Load P50/P95 | Prompt-eval P50/P95 | Eval P50/P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SCREEN | 120 | 0 | 1.580912s / 1.814611s | 1.572841s / 1.806169s | 0.459518s / 0.505485s | 0.120626s / 0.142331s | 0.465114s / 0.640630s |
| VAL | 100 | 63 | 14.682363s / 18.144259s | 14.673721s / 18.136487s | 13.324700s / 16.756087s | 0.140699s / 0.167674s | 0.493393s / 0.744843s |

The full component summaries (mean, median, P50, P90, P95, max) are in `duration_summary.json`; each raw row is in `p2_screen_duration_breakdown.csv` and `p2_val_duration_breakdown.csv`. In VAL, load duration contributes a median ratio of 0.895388 and P95 ratio of 0.923384; prompt evaluation and generation remain sub-second at P95 (0.167674s and 0.744843s). This is why the primary historical anomaly component is `load_duration`, subject to the runtime evidence limitations below.

## Automatically detected change points

The method is an explicit threshold-run analysis: mark each ordered VAL request as HIGH when `load_duration > 5s`, form contiguous runs, and select the longest sustained HIGH run followed by a LOW run. No request index was hard-coded.

VAL runs:

```text
[{"start_index": 1, "end_index": 20, "state": "HIGH", "count": 20}, {"start_index": 21, "end_index": 21, "state": "LOW", "count": 1}, {"start_index": 22, "end_index": 64, "state": "HIGH", "count": 43}, {"start_index": 65, "end_index": 100, "state": "LOW", "count": 36}]
```

The longest sustained HIGH run is requests 22–64; the first recovered LOW request after that run is index 65. Single-request LOW runs detected between HIGH runs start at index 21; they are retained rather than hidden. All transitions, timestamps, and request IDs are in `p2_val_change_points.csv`.

For the main recovery transition, the pre-change sustained HIGH window is requests 22–64 and the post-change LOW window begins at 65:

| Window | Count | Load median | Load P95 | Total median | Client median |
|---|---:|---:|---:|---:|---:|
| Sustained HIGH before recovery | 43 | 13.762809s | 16.633463s | 15.200541s | 15.209484s |
| Recovered LOW after transition | 36 | 0.470802s | 0.519604s | 1.631841s | 1.640880s |

## Config and token checks

```json
{
  "screen_config_fingerprints": [
    "872e7210a216c9d496b7930f0b9cf4cef059012ab7c9c4aea23138f3dc8086fe"
  ],
  "val_config_fingerprints": [
    "872e7210a216c9d496b7930f0b9cf4cef059012ab7c9c4aea23138f3dc8086fe"
  ],
  "screen_val_config_equal": true,
  "prompt_sha_values": [
    "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e"
  ],
  "prompt_matches_expected_c3": true,
  "model_values": [
    "qwen3.5:4b"
  ],
  "format_values": [
    "json"
  ],
  "think_values": [
    "False"
  ],
  "stream_values": [
    "False"
  ],
  "generation_options_values": [
    "{\"num_ctx\":8192,\"num_predict\":256,\"temperature\":0}"
  ],
  "reduced_scalar_config_equal": true
}
```

SCREEN and VAL request payloads are byte-equivalent after JSON normalization for model, Prompt, `format`, `think`, `stream`, and generation options. Both use Prompt SHA `685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e`, model `qwen3.5:4b`, `format=json`, `think=false`, `stream=false`, `temperature=0`, `num_ctx=8192`, and `num_predict=256`. The actual payload/config evidence is retained in the source request logs.

`prompt_eval_count` is stable at `[598]` in VAL and `[598]` in SCREEN. `eval_count` varies, but the generation/eval-duration P95 remains only `0.744843s`; it does not track the ten-second-scale load spike as the dominant component. The load-duration versus eval-count Spearman correlations are VAL `-0.17435523203238062` and SCREEN `-0.038338765339134856`. Image geometry is uniformly 448×336; the load-duration/image-byte Spearman correlations are VAL `0.12454845484548455` and SCREEN `0.036988679769428434`. These correlations are auxiliary association checks, not causal claims.

## Evidence boundary

The raw timing evidence confirms a load-duration-dominated historical anomaly: VAL has 63 requests over 5 seconds, while SCREEN has 0; prompt evaluation and generation do not expand comparably. It does not by itself identify whether the load time came from model reload/residency churn, runner lifecycle, scheduler behavior, GPU contention, or another server runtime condition. SSH read-only authentication to `tiga@192.168.20.62` failed during preflight, so remote GPU memory, compute-process, runner-PID, systemd, and journal evidence remain unavailable.

## Source hashes

```text
{
  "screen_raw": "f6e56030612e35c4065fe707054793701e875e9172c195d7783ba113a53bb5db",
  "screen_request_log": "4fa22a1a7cfd72145ad5db8e1bf879aeb7e3a2748560352e0414d420b2af33e0",
  "screen_manifest": "ccb8c9df51371dbfd2a8e34201ccd42b0a825eea4444ba45a3aaa6945094aab5",
  "val_raw": "cd04ddd89328d7464856dafc8dd99c95eae1761fc7df19b6996ee3de2ad32b4a",
  "val_request_log": "9b462e6b6b20a57d076b32b98c9b27700fc1fc14f229c63a66baff97ba4d084e",
  "val_manifest": "f3feb12b364ffbf045857d6b4ba77ed28932ccf0d9c1d644db7a10de7dfd7762"
}
```
