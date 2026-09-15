# 61 — P4D GR3Q2 generation configuration comparison

```text
PROVIDER_SAME=true
MODEL_SAME=true
BACKEND_SAME=true
RUNTIME_SAME=true
WRAPPER_SAME=true
BINARY_SAME=true
PROMPT_AND_CONFIG_SAME=true
MATERIAL_GENERATION_CONFIG_CHANGE=false
```

## 已确认事实

Parent and proposed recovery use `codex` / `gpt-5.4` / `image_generation`, native request `1536x1024`, `medium` quality, PNG output, no references, concurrency 1, outer retry false, native max retries 3, then RGB center-crop to 16:9 and Pillow LANCZOS resize to 1920×1080. Frozen prompt bytes and manifest SHA also match.

## 合理推理

No observable material generation-config difference was found. The model's more granular server-side capability version is not exposed; this conclusion is explicitly limited to the observable evidence recorded here.

## 风险与限制

Identical client-side settings do not prove identical opaque server-side behavior. Future profile-stratified QA must look for dimension, latency, file-size, perceptual-hash, scene-distribution, and visual-style differences.
