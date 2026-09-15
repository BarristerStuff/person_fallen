# 60 — P4D GR3Q2 lineage-policy amendment

```text
P4D_GR3Q2_STATUS=READY_AWAITING_PROFILE_STRATIFIED_RECOVERY_AUTHORIZATION
POLICY_CHANGE=true
POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION=false
PROFILE_FINGERPRINT_CHANGED=true
MATERIAL_GENERATION_CONFIG_CHANGE=false
PROVIDER_REQUESTS=0
```

## 已确认事实

GR3Q1 remains an immutable historical `BLOCKED_PROFILE_LINEAGE_CHANGE` decision. GR3Q2 created a separate policy amendment without rewriting GR3Q1 or GR3E.

## 合理推理

Profile change is treated as provenance-only under the newly amended policy because no observable material configuration changed.

## 风险与限制

The provider may have opaque account-specific behavior that cannot be proven absent from local metadata. Profile stratification is therefore mandatory, and it never becomes a GT feature or C3 model input.
