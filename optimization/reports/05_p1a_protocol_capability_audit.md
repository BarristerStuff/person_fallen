# 05 P1A protocol capability audit

## Confirmed facts

- All required starting hashes matched: P0 prompt `b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4`; frozen splits `16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a`; frozen formal manifest `771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6`.
- Dataset read-only validator: `valid`, `error_count=0`, `warning_count=387`, full hash check=true.
- Ollama `/api/version`: `0.23.2`.
- `qwen3.5:4b` exists. Digest: `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`; family `qwen35`, GGUF, Q4_K_M, parameter size 4.7B.
- P1A config differs from frozen P0 request conditions only by top-level `"think": false`; it retains `format="json"`, model, endpoint, temperature=0, num_ctx=8192, num_predict=256, concurrency=1, and letterbox 448x336 JPEG q70.

## Experiment judgment

Top-level `think=false` is a server capability candidate worth testing through a DEV-only canary. No Prompt/GT/split/preprocess change is authorized here.

## Risk boundary

This audit does not establish production behavior or real-camera performance.
