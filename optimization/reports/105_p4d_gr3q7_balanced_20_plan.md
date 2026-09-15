# Q7 balanced 20-slot network-stability plan

## 已确认事实

The frozen universe is explicitly partitioned:

```text
VERIFIED_SUCCESS=151
COMPLETION_UNKNOWN_QUARANTINED=1
SAFE_EXECUTABLE_OUTSTANDING=288
TOTAL=440
SETS_PAIRWISE_DISJOINT=true
```

The Q7 plan is frozen at 20 unique slots / four complete 5-slot groups:

```text
PLAN_SHA256=4b6b44597f6d91a0b754f70a3e460cb8bba45fcf8f03f1cab288e7fec6f7149f
POSITIVE=15
HARD_NEGATIVE=5
ORDINARY_NEGATIVE=0
NEW_DESIGN=10
NEW_SCREEN=10
MAINT_G006_HITS=0
```

Selected groups, all `SAFE_NOT_STARTED`, are:

| Group | Role | Taxonomy | Split |
|---|---|---|---|
| `PF_P4D_POS_INTENTIONAL_G001` | positive | intentional_ground_lying | NEW_DESIGN |
| `PF_P4D_POS_MULTI_G001` | positive | multi_person_one_lying | NEW_DESIGN |
| `PF_P4D_POS_CORRIDOR_G001` | positive | horizontal_corridor_ground_lying | NEW_SCREEN |
| `PF_P4D_HN_SQUAT_G006` | hard_negative | squat_crouch_deep_bend | NEW_SCREEN |

Semantic frozen prompts, group/taxonomy/split assignments, and Adapter V1 are
unchanged.  Provider render prompts remain deterministic provenance artifacts.
