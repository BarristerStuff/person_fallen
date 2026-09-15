# P4D GR3Q9 final report

```text
PROJECT=net_vlm
EVENT=person_fallen
EVENT_VERSION=v2.0
P4D_GR3Q9_STATUS=COMPLETE_WITH_POSTRUN_CONFIG_BINDING_MISMATCH
P4D_GR3Q9_LOGICAL_INVOCATIONS=30
P4D_GR3Q9_SUCCESS=30
P4D_GR3Q9_PHYSICAL_ATTEMPT_LOWER_BOUND=30
P4D_GR3Q9_NATIVE_RETRY_EVENTS=0
P4D_GR3Q9_CONTENT_POLICY_REFUSALS=0
P4D_IMAGES_ACCEPTED=0
HOLDOUT_REQUESTS=0
HOLDOUT_CONSUMED=false
FORMAL_INGEST=false
C3=false
VAL=0
PRODUCTION_CODE_MODIFIED=false
```

## 已确认事实

Q9 generated 30/30 authorized slots successfully, preserving all raw/final artifacts and the terminal freeze. The resulting partition is 226 verified, 1 quarantined completion-unknown, and 213 safe executable outstanding. Mechanical QA passed. Dataset validator remained valid with zero errors and 387 pre-existing warnings.

Key hashes: plan `0344c97847ea7447fee7246a7dc9b173429efd058aa0f4153eb9d2f6d5bb950c`; run config `a98a3028ebc251ab4dba05dc506f02cf85fb18356f260e2a66b4221df1e18b2e`; Q9 runner `80476d4fa06548bf766cf674c9a912cd324eedd04a29f1dda8da7759ef2ff454`; SQLite ledger `a73940f40ea63588ab5b1d3f78b42735e4825c62b4549d0d76747ff3d548e533`; raw-response log `ea17820cae9ec6b0e09bfd8e8387b5bdff3dd4fe37a8303074486b071268e106`; terminal freeze `f62af81a6ebbdecd807e3db6ab14ed1abc1ac4ceef73d4ffea64cc081e8a3bf6`.

## 实验判断

Generation success is evidence of provider completion and mechanical integrity only; it is not human semantic acceptance or Ground Truth. The six-group balanced composition is suitable for later human review, but this stage did not perform C3 or semantic optimization.

## 风险与限制

The frozen authorization JSON contains Q8 caps (25/30) while the actual Q9 runner enforced 30/36. Because this is a material binding inconsistency, this revision is not a clean formally accepted Q9 freeze despite all calls remaining within the user-authorized actual caps. Native-size identity is also not proven (all raw outputs were 1672x941). `P4D_IMAGES_ACCEPTED` remains 0.

## 下一阶段建议

Do not ingest or use these images for C3 until a new, independently self-consistent revision is explicitly authorized and audited. A future revision should regenerate only its own authorization/config artifacts or, if governance permits, classify this revision as raw evidence with the mismatch permanently attached. Do not resend completion-unknown or start any automatic recovery.

