# P4D GR3Q9 preflight

## 已确认事实

- Parent Q8 terminal freeze SHA: `2235fff83e62b2daf05f736446ccc5819e599fd2c7112fdb788871ecc20d8477`; parent partition verified as 196 success / 1 completion-unknown / 243 safe outstanding.
- Dataset read-only validator before execution: valid, 0 errors, full-hash=true, 387 warnings; active P4D references=0.
- Provider: Codex image_generation, runtime 0.7.3, model `gpt-5.4` delegated to GPT Image 2, Adapter `CODEX_SAFE_STAGED_CV_V1`, native max retries=3.
- Frozen plan contains 30 rows, 25 hard-negative + 5 positive, NEW_DESIGN=15 and NEW_SCREEN=15, six complete groups, zero MAINT_G006.

## 实验判断

The plan is balanced under the requested split feasibility: positive curled plus distinct ground-maintenance, squat, crawling, pushup/plank and mixed hard-negative groups. Semantic prompts and taxonomy are unchanged; only the provider render adapter is recorded.

## 风险与限制

The first Q9 preparation revision (`..._01`) was invalidated before any provider request because its frozen runner identity was inherited from Q8. It is preserved with a zero-request audit marker. Execution proceeded only in independent revision `..._02`.

