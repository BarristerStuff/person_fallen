# P4D GR3Q5 render adapter V1

```text
ADAPTER_VERSION=CODEX_SAFE_STAGED_CV_V1
SEMANTIC_PROMPT_CHANGED=false
PROVIDER_RENDER_PROMPT_CHANGED=true
```

The adapter supplies explicit fictional staged occupational-safety and computer-vision training context for the provider-facing render prompt. It neither changes frozen semantics, taxonomy, groups, split, GT, nor human acceptance. Existing successes retain `LEGACY_NO_ADAPTER`; Q5 requests use `CODEX_SAFE_STAGED_CV_V1` as generation provenance.
