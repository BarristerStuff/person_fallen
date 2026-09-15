# P4D GR3Q2 lineage-policy amendment v1

```text
POLICY_CHANGE=true
POLICY_CHANGE_RETROACTIVE_TO_GR3Q1_DECISION=false
ACCOUNT_PROFILE_CLASS=OPERATIONAL_PROVENANCE
MATERIAL_GENERATION_CONFIG_CHANGE=false
```

## 已确认事实

GR3Q1 remains a correct historical `BLOCKED_PROFILE_LINEAGE_CHANGE` result under its then-frozen policy. GR3Q2 does not edit that decision or any parent freeze.

## 新规则

Hard continuation variables are provider/model/backend/capability, prompt bytes, generation command and configuration, requested quality, image-generation mode, output conversion, taxonomy, group allocation, and DESIGN/SCREEN allocation. Account/profile/session/quota/timestamp fields are operational provenance unless an observable material generation variable differs.

## 风险与限制

Equal observable client/runtime configuration does not prove that an opaque provider service has no account-specific behavior. Consequently, Profile-A and Profile-B must remain explicit provenance strata, cannot be model inputs or GT, and require future distribution/style diagnostics after all 440 assets exist.
