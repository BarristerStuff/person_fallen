# 06 P1A canary report

## Confirmed facts

- Canary is immutable: 12 DEV-only media across 12 distinct groups: positive=4, negative=2, hard_negative=4, uncertain=2.
- Canary manifest SHA-256: `9db0cda0066e50e9b2f36caaf01fd728e37deaa1b04ea093fb38b3741c4b548b`.
- All 12 formal predictions came strictly from the Ollama `response` field. No `thinking` fallback exists in the runner.
- HTTP=12/12, response_nonempty=12/12, JSON parse=12/12, schema=12/12, canonical prediction=12/12, first-attempt=12/12; thinking_present=0/12.
- `P1A_CANARY_STATUS=PASS`; HOLDOUT requests=0.

## Boundary

The canary validates only the output contract. Its apparent classification outcome is not used to announce accuracy.
