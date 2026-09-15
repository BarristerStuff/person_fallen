# V5-A0 独立场景复核开发终态

**V5_A0_DEV_GATE_FAIL**

主路来源：FROZEN_V4_CACHE；评测方式：CACHED_PRIMARY_PLUS_NEW_SECONDARY。

新旁路模型请求：288；新主路/Detector/VAL/Holdout 请求均为 0。

## 分阶段结果

### dev
```json
{
  "status": "COMPLETE",
  "phase": "dev",
  "EVALUATION_MODE": "CACHED_PRIMARY_PLUS_NEW_SECONDARY",
  "PRIMARY_SOURCE": "FROZEN_V4_CACHE",
  "SECONDARY_CANDIDATE": "V5-A0-INDEPENDENT-RECHECK",
  "rows": 436,
  "primary_cached_rows": 436,
  "secondary_requests": 288,
  "secondary_valid_responses": 288,
  "ground_lying_count": 145,
  "immediate_ALERT_count": 141,
  "immediate_ALERT_recall": 0.9724137931034482,
  "ALERT_RECHECK_coverage": 1.0,
  "floor_sitting_count": 55,
  "floor_sitting_ALERT_FPR": 0.0,
  "floor_sitting_RECHECK_rate": 0.9272727272727272,
  "determinate_negative_count": 230,
  "determinate_negative_ALERT_FPR": 0.0,
  "determinate_negative_total_RECHECK_count": 90,
  "determinate_negative_total_RECHECK_rate": 0.391304347826087,
  "secondary_strict_JSON_success": 1.0,
  "primary_cache_binding_success": 1.0,
  "final_ALERT_set_equals_primary_ALERT_set": true,
  "scene_review_distribution": {
    "candidate_present": 140,
    "candidate_absent": 148
  },
  "auxiliary_decision_distribution": {
    "RECHECK_VISUAL_UNCERTAIN": 35,
    "ATTENTION_NEAR_GROUND": 4,
    "ALERT_GROUND_LYING": 2
  },
  "uncertain_decision_distribution": {
    "RECHECK_VISUAL_UNCERTAIN": 15,
    "ALERT_GROUND_LYING": 5
  },
  "secondary_latency_p50": 1.4792579714994645,
  "secondary_latency_p95": 1.673537250557274,
  "strata": {
    "ground_lying": {
      "count": 145,
      "decision_distribution": {
        "ALERT_GROUND_LYING": 141,
        "RECHECK_VISUAL_UNCERTAIN": 4
      },
      "alert_count": 141,
      "recheck_count": 4,
      "alert_rate": 0.9724137931034482,
      "recheck_rate": 0.027586206896551724,
      "alert_recheck_coverage": 1.0
    },
    "normal_negative": {
      "count": 230,
      "decision_distribution": {
        "NO_ALERT_NORMAL_POSE": 140,
        "RECHECK_VISUAL_UNCERTAIN": 90
      },
      "alert_count": 0,
      "recheck_count": 90,
      "alert_rate": 0.0,
      "recheck_rate": 0.391304347826087,
      "alert_recheck_coverage": 0.391304347826087
    },
    "auxiliary_attention": {
      "count": 41,
      "decision_distribution": {
        "RECHECK_VISUAL_UNCERTAIN": 35,
        "ATTENTION_NEAR_GROUND": 4,
        "ALERT_GROUND_LYING": 2
      },
      "alert_count": 2,
      "recheck_count": 35,
      "alert_rate": 0.04878048780487805,
      "recheck_rate": 0.8536585365853658,
      "alert_recheck_coverage": 0.9024390243902439
    },
    "visual_uncertain": {
      "count": 20,
      "decision_distribution": {
        "RECHECK_VISUAL_UNCERTAIN": 15,
        "ALERT_GROUND_LYING": 5
      },
      "alert_count": 5,
      "recheck_count": 15,
      "alert_rate": 0.25,
      "recheck_rate": 0.75,
      "alert_recheck_coverage": 1.0
    },
    "floor_sitting": {
      "count": 55,
      "decision_distribution": {
        "RECHECK_VISUAL_UNCERTAIN": 51,
        "NO_ALERT_NORMAL_POSE": 4
      },
      "alert_count": 0,
      "recheck_count": 51,
      "alert_rate": 0.0,
      "recheck_rate": 0.9272727272727272,
      "alert_recheck_coverage": 0.9272727272727272
    }
  },
  "PFV4_SCREEN_0066": null,
  "gate_checks": {
    "ground_lying_immediate_alert_recall": true,
    "ground_lying_alert_recheck_coverage": true,
    "floor_sitting_alert_fpr": true,
    "determinate_negative_alert_fpr": true,
    "determinate_negative_total_recheck_rate": false,
    "secondary_strict_json_success": true,
    "primary_cache_binding_success": true,
    "alert_set_unchanged": true
  },
  "gate": "FAIL",
  "screen_role": "DEVELOPMENT",
  "ROBOT_REOBSERVATION_VALIDATED": false
}
```

### regression
```json
"NOT_RUN"
```

## 解释与暴露边界
- ALERT 集合是历史主路继承；不可写成旁路新增的直接告警能力。
- RECHECK 是待确认状态，不是确认倒地；coverage 不等于立即报警召回。
- DEV 与旧 SCREEN 都是已暴露的开发资源；SCREEN 本次仅为 CONSUMED_SCREEN_DEVELOPMENT_REGRESSION。
- 用户声明提示词与图像相符；机器核验仅证明 hash/行绑定，不声称全量像素语义验证。当前合成开发不要求人工逐图审核。
- auxiliary 和 visual_uncertain 保留独立决策分布，不能隐藏主路继承 ALERT。
- 未验证机器人复拍、新视角、现场相机、视频或端到端性能；报告时延仅为旁路新测量。

## 独立验证待办（未执行）
- 审计 DEV、历史 SCREEN、REV15/V5 和其它历史试验的样本/组/媒体暴露；证明拟议独立验证资源未被用于选择候选。
- 在新授权下评审独立验证协议、同一门禁、失败停止规则与缓存/新推理边界；本次不读取或选择 VAL/Holdout 样本。

NEXT_ACTION=STOP_CURRENT_CANDIDATE
