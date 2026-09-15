# 40 — P4D_GR2 historical status erratum

```text
GR2_PROVIDER_LINEAGE_DECISION_REMAINS_VALID=true
GR2_GENERATION_REQUESTS=0
GR2_TERMINAL_FREEZE_REMAINS_VALID=true
REPORT39_MODIFIED=false
```

## 已确认事实

`reports/39_p4d_gr2_final.md` contains a later-summary status drift in its
top block. The drift does not alter the GR2 provider-lineage decision, its zero
request count, or the GR2 terminal freeze. The file and its SHA are preserved;
this erratum is additive.

| incorrect_field | incorrect_value | correct_value | evidence_source |
|---|---|---|---|
| `P1A_STATUS` | `COMPLETE` | `VAL_INCOMPLETE_FREEZE_BINDING_ERROR` | `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/09_p1a_final_report.md` |
| `P2_EXECUTED` | `false` | `true` (`P2_STATUS=COMPLETE`) | `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/17_p2_final_report.md` |
| `P2_STATUS` | omitted from report39 | `COMPLETE` | `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/17_p2_final_report.md` |
| `P3_EXECUTED` | `false` | `true` (`P3_STATUS=SCREENING_COMPLETE_NO_WINNER`) | `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/24_p3_final_report.md` |
| `P3_STATUS` | omitted from report39 | `SCREENING_COMPLETE_NO_WINNER` | `/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/24_p3_final_report.md` |

The authoritative history is P0 protocol failure; P1A incomplete freeze-bound
VAL with valid DEV measurement and successful protocol repair; P1R complete
recovery baseline; P2 complete with C3 winner; P2L complete with no winner and
C3 unchanged; and P3 complete screening with no winner. No historical report
was rewritten.

## 实验判断

This is documentation drift only. It must not be interpreted as a request to
rewrite GR2's immutable freeze or to recalculate any old stage.

## 风险与限制

The later report39 remains intentionally inconsistent and should always be
read together with this erratum and the earlier evidence reports.

## 下一阶段建议

Use the corrected history in GR3 planning and keep reports 25--39 immutable.
