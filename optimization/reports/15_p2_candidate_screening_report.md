# P2 candidate SCREEN report

## Status

```text
P2_SCREEN_PROTOCOL_GATE=PASS
P2_SCREEN_BLIND_BEFORE_CANDIDATE_FREEZE=true
CANDIDATE_FREEZE_VERIFICATION=PASS
P2_WINNER=C3
P2_WINNER_SELECTION=UNIQUE
HOLDOUT_REQUESTS=0
```

Candidate freeze was created before any SCREEN request. Its immutable SHA-256 is `7ab9169a9502c832c8a10b522ab7257eba846a5ff7ecef39f6139b7e5d9beebe`; independent verification left the freeze byte-identical. The common protocol canary used nine DESIGN images per candidate and passed 9/9 for C1, C2, and C3; every canary had HTTP, response-nonempty, JSON, schema, and canonical success, with no `thinking` output.

## Same-manifest SCREEN results

All C1–C3 runs used the identical 120-item, 12-group SCREEN manifest and the same model/config/preprocessing. C0 was recomputed offline from P1A DEV predictions, with zero new model requests.

| Candidate | Protocol | TP | FP | TN | FN | Precision | Recall | F1 | Ordinary FPR | Hard-negative FPR | Uncertain rate | P50 | P95 | Eligible |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| C0 baseline | PASS | 50 | 22 | 38 | 0 | 0.694444 | 1.000000 | 0.819672 | 0.000000 | 0.550000 | 0.000000 | 1.456534 | 1.594376 | — |
| C1 | PASS | 50 | 22 | 38 | 0 | 0.694444 | 1.000000 | 0.819672 | 0.000000 | 0.550000 | 0.000000 | 1.539897 | 1.761156 | No |
| C2 | PASS | 50 | 29 | 31 | 0 | 0.632911 | 1.000000 | 0.775194 | 0.000000 | 0.725000 | 0.000000 | 1.451907 | 1.592479 | No |
| C3 | PASS | 50 | 5 | 55 | 0 | 0.909091 | 1.000000 | 0.952381 | 0.000000 | 0.125000 | 0.000000 | 1.580759 | 1.815010 | **Yes** |

Every candidate had 120/120 HTTP, response-nonempty, JSON, schema, and canonical success. SCREEN GT-uncertain prediction distributions were C0 `negative=1, positive=9`, C1 `negative=2, positive=8`, C2 `positive=10`, and C3 `negative=2, positive=8`; these items were excluded from binary metrics.

## Gates and selection

The development latency limit was `1.610508 × 1.15 = 1.8520842s`. C1, C2, and C3 all passed protocol, positive recall `>=0.95`, ordinary-negative FPR `=0`, and SCREEN P95 latency. C1 failed the minimum hard-negative improvement rule because its hard-negative FPR reduction was 0. C2 failed because its hard-negative FPR worsened by 0.175. C3 reduced hard-negative FPR by 0.425, from 0.55 to 0.125, satisfying the required absolute reduction `>=0.05`; it was the only eligible candidate.

Paired comparison against C0:

| Candidate | Baseline FP → candidate TN | Baseline TN → candidate FP | Baseline TP → candidate FN | Baseline FN → candidate TP | McNemar exact p (auxiliary) |
| --- | ---: | ---: | ---: | ---: | ---: |
| C1 | 2 | 2 | 0 | 0 | 1.000000 |
| C2 | 0 | 7 | 0 | 0 | 0.015625 |
| C3 | **17** | **0** | 0 | 0 | 0.000015 |

The p-values are auxiliary evidence only; the winner was selected by the predeclared gate and ranking rule, not statistical significance alone.

## Hashes

```text
C0 prompt SHA                         b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4
C1 prompt SHA                         f3291b1f231316f3d424a2d4d4a1ac43fe0010205bef4528d62ca1771cb2d396
C2 prompt SHA                         c3827dcbf4eae4e39729f4b42c3f7398da8b835f4e047e79bf0d82edbec8c42d
C3 prompt SHA                         685bb9724b1faa96298c1e6cf8139774d82afbc9d2f30cdd154fbe5cb776951e
P2 request config SHA                 8f3e64f30beeadb0a31e2ac909fd0c57562a1a06291d0a93360ce788a4b1f10d
P2 runner SHA                         72a3ffdd044cbea46025e0fe90f9c7e62350af194e0ccaa89f267d1cf0f0a568
P2 materializer SHA                   d2485bc89345df7b03bfae42e7cbea206cc1136271381a6cbf3da9d29092482b
C3 SCREEN predictions SHA             5d21d873dc327c8e59d25c59fad79522f65d6d0e19a817c5d893f662aaa1a848
C3 SCREEN summary SHA                 4c6c0233a92e9a918d176d866286849a1fd59865d2dff85d7ae0e2a77bce78be
```

## Evidence

- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/04_screening/screening_comparison.csv`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/04_screening/paired_error_analysis.csv`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/04_screening/winner_decision.json`
- `/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/03_candidates/candidate_freeze_attestation.json`
