# 30 — P4D_GR1 generation resume

PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P0_STATUS=COMPLETE_PROTOCOL_FAILURE
P1A_STATUS=COMPLETE
P1A_VALID_CLASSIFICATION_BASELINE=true
P1A_PROTOCOL_STATUS=PASS
P2_EXECUTED=false
P3_EXECUTED=false
P4D_NAME=P4D_NEW_HARD_NEGATIVE_DEV_REVISION
P4D_GR1_NAME=P4D_GR1_GENERATION_RESUME
P4D_GR1_CHANGE=provider_revision_only_after_old_ebond_401
P4D_GR1_PROMPT_CHANGED=false
P4D_GR1_GROUP_PLAN_CHANGED=false
P4D_GR1_TAXONOMY_CHANGED=false
P4D_GR1_STATUS=BLOCKED_PROVIDER_AUTH_RECURRENCE
P4D_STATUS=GENERATION_REQUIRED
P4D_NEW_TOTAL=440
P4D_HARD_NEGATIVE=300
P4D_POSITIVE=100
P4D_ORDINARY_NEGATIVE=40
P4D_GROUPS=88
P4D_NEW_DESIGN=265
P4D_NEW_SCREEN=175
P4D_CROSS_SPLIT_GROUPS=0
P4D_IMAGES_GENERATED=192
P4D_IMAGES_ACCEPTED=0
P4D_IMAGES_REJECTED=0
P4D_OUTSTANDING_SLOTS=248
P4D_EXACT_DUPLICATES=0
P4D_NEAR_DUPLICATE_GROUPS=0
P4D_CROSS_SPLIT_NEAR_DUPLICATES=0
P4D_PROMPT_IMAGE_MAPPINGS=N/A
P4D_MISSING_MAPPINGS=N/A
FORMAL_INGEST_EXECUTED=false
MEDIA_ADDED=0
LABELS_ADDED=0
C3_EXECUTED=false
P4D_NEW_VAL_REQUESTS=0
P4D_HOLDOUT_REQUESTS=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
VAL_P0_PROTOCOL_EXPOSED=true
VAL_SEMANTIC_METRICS_USED_FOR_TUNING=false
PRODUCTION_CODE_MODIFIED=false
OLLAMA_SERVICE_MODIFIED=false


## Provider revision and generation resume

- Original provider: `ebond-gpt-image-2` / `gpt-image-2`; its one smoke attempt remains permanently preserved as attempt 1 and returned HTTP 401 `INVALID_API_KEY`.
- Active revision: `P4D_GR1_PR_CODEX_20260827_01`, provider `codex`, model `gpt-5.4` using the authenticated Codex image-generation wrapper (delegated image capability: `gpt-image-2`).
- `provider_changed=true` was recorded because the old provider had 0 successful images and an observed credential failure. Prompt/group/taxonomy/frozen split hashes were unchanged.
- Stage gates: smoke `PASS`, Stage1 `PASS`, Stage2 `PASS`, bulk `FAIL_AUTH`.
- GR1 phase counts (successful rows): `{"BULK": 166, "RAMP1": 5, "RAMP2": 20, "SMOKE": 1}`; native output sizes observed: `{"1672x941": 192}`; controlled final sizes: `{"1920x1080": 192}`.
- No API key is written to the revision, request, raw-response, or provider-result artifacts; credential-like output is sanitized.
- The bulk gate stopped after 200/414 scheduled bulk attempts: 166 successes and 34 failures (32 HTTP 429 usage-limit responses, followed by 2 HTTP 401 `refresh_token_invalidated` responses).  Automatic retry remained `false`; no failed slot was recovered.


Generation summary: `{"attempt_rows": 226, "failed_rows": 34, "final_images": 192, "final_size_counts": {"1920x1080": 192}, "latency": {"count": 192, "max": 113.52491, "mean": 47.47718898958333, "p50": 44.2377945, "p95": 71.171872}, "native_size_counts": {"1672x941": 192}, "old_ebond_401_recorded": true, "old_ebond_attempt_rows": 1, "phase_counts": {"BULK": 166, "RAMP1": 5, "RAMP2": 20, "SMOKE": 1}, "raw_successful_images": 192, "successful_rows": 192}`

Frozen hash audit: `{"actual": {"C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e", "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab", "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843", "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb", "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250", "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b"}, "all_match": true, "checks": {"C3_prompt.txt": true, "group_manifest.csv": true, "group_split_freeze.json": true, "prompt_manifest.csv": true, "prompt_pack.md": true, "prompt_pack_freeze.json": true}, "expected": {"C3_prompt.txt": "685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e", "group_manifest.csv": "11ab903056e0acbdb9ca5a507f33f3237f3b90f059f445f8df76c1dde174fbab", "group_split_freeze.json": "b9d1df02541454b38ab296bd0033b0d327cca0ba720b95c7414ea6ec1bc05843", "prompt_manifest.csv": "e75c48626f2eabade9cdbc48bb77072c5d470ddce60ec9a903f580d4990aeceb", "prompt_pack.md": "8b791d2007b0866f83275082a7394a0d33a5d7bd0aef4ab9f19993fba857a250", "prompt_pack_freeze.json": "385b7b9f0b6b675c3820e97fe1931bd0e19b9b5839f50a3fcae70fd1feec136b"}}`
