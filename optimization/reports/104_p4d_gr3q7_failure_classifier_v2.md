# Q7 structured provider-failure classifier V2

## 已确认事实

```text
CLASSIFIER_SHA256=fbd773b5d5d131f06abd334e041377fc5e0c7b9c0e5e6179164979c2abb624c0
REGRESSION_PASS=3/3
```

The offline regression suite uses immutable historical raw evidence only:

| Case | Expected classification | Result |
|---|---|---|
| Window01 `PF_P4D_POS_CURLED_G003_V03` | `CONTENT_POLICY_REFUSAL_CONFIRMED` | PASS |
| Q5 `PF_P4D_NEG_CHAIR_G003_V03` | `HTTP429_USAGE_LIMIT_REACHED` | PASS |
| Q6 `PF_P4D_HN_MAINT_G006_V02` | `COMPLETION_UNKNOWN / NETWORK_ERROR_COMPLETION_AMBIGUITY` | PASS |

No provider call was made for this regression.  The new classifier must be
bound into any future Q7 execution revision; the Q6 runner remains historical
evidence and must not be reused for generation.
