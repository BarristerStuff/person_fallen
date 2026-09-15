# P3 preflight report

checked_at_utc: 2026-08-27T03:19:10.816344+00:00

## 已确认事实

- dataset validator returncode=0; status=valid; errors=0; warnings=387; full_hash_check=True
- model identity pass=True; Ollama version=0.23.2; qwen3.5:4b digest=2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
- P2 DESIGN rows=190, SCREEN rows=120, media overlap=0, group overlap=0
- P2 C3 prompt SHA=685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e
- P2 winner freeze SHA=ffbf7cf4cb914b54226ef974f0a51674fcd42b3ad98be98cc210474f434131c0

## 独立判断

- P3 只使用 P2_DESIGN 进行 C3 residual forensic 和 candidate design；P2_SCREEN 仅在 candidate freeze 后用于 adaptive screening。
- 本阶段不运行 VAL，不读取 P2 SCREEN/VAL 个体错误，不请求 HOLDOUT。

## 风险与停止条件

- 若 source_hash_inventory.errors 非空，或 model_identity_pass=false，P3 必须 BLOCKED，不得发起正式图片请求。
- 当前 validator 的 387 条 warning 记录为既有数据集 warning；本阶段不修改正式数据集。
