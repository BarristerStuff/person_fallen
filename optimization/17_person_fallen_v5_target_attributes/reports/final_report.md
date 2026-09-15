# V5-B0-TARGET-ATTRIBUTES 开发实验终态

V5_B0_PILOT_AND_KNOWN_REGRESSION_PASS

新推理只用于固定 pilot115 与条件式 known-regression1；未使用主路缓存决定结果。

新增模型请求总数：116。

## PILOT_DEV_115
```json
{
  "status": "COMPLETE",
  "phase": "pilot",
  "rows": 115,
  "expected_rows": 115,
  "output_rows": 115,
  "new_model_requests": 115,
  "completed_requests": 115,
  "valid_responses": 115,
  "ground_lying_count": 60,
  "ground_lying_ALERT_count": 60,
  "ground_lying_ALERT_recall": 1.0,
  "ground_lying_ALERT_RECHECK_count": 60,
  "ground_lying_ALERT_RECHECK_coverage": 1.0,
  "ground_lying_decision_counts": {
    "ALERT_GROUND_LYING": 60,
    "RECHECK_VISUAL_UNCERTAIN": 0,
    "NO_ALERT_NORMAL_POSE": 0,
    "ATTENTION_NEAR_GROUND": 0
  },
  "floor_sitting_count": 55,
  "floor_sitting_decision_counts": {
    "ALERT_GROUND_LYING": 0,
    "RECHECK_VISUAL_UNCERTAIN": 5,
    "NO_ALERT_NORMAL_POSE": 50,
    "ATTENTION_NEAR_GROUND": 0
  },
  "multi_person_rows": 5,
  "multi_person_group_count": 1,
  "multi_person_ALERT_count": 5,
  "multi_person_details": [
    {
      "request_id": "V5_B0_PILOT_0111",
      "item_id": "P4D_PLAN::PF_P4D_POS_MULTI_G001_V01",
      "group_id": "PF_P4D_POS_MULTI_G001",
      "people_count": 2,
      "image_decision": "ALERT_GROUND_LYING"
    },
    {
      "request_id": "V5_B0_PILOT_0112",
      "item_id": "P4D_PLAN::PF_P4D_POS_MULTI_G001_V02",
      "group_id": "PF_P4D_POS_MULTI_G001",
      "people_count": 3,
      "image_decision": "ALERT_GROUND_LYING"
    },
    {
      "request_id": "V5_B0_PILOT_0113",
      "item_id": "P4D_PLAN::PF_P4D_POS_MULTI_G001_V03",
      "group_id": "PF_P4D_POS_MULTI_G001",
      "people_count": 3,
      "image_decision": "ALERT_GROUND_LYING"
    },
    {
      "request_id": "V5_B0_PILOT_0114",
      "item_id": "P4D_PLAN::PF_P4D_POS_MULTI_G001_V04",
      "group_id": "PF_P4D_POS_MULTI_G001",
      "people_count": 2,
      "image_decision": "ALERT_GROUND_LYING"
    },
    {
      "request_id": "V5_B0_PILOT_0115",
      "item_id": "P4D_PLAN::PF_P4D_POS_MULTI_G001_V05",
      "group_id": "PF_P4D_POS_MULTI_G001",
      "people_count": 3,
      "image_decision": "ALERT_GROUND_LYING"
    }
  ],
  "people_count_distribution": {
    "1": 101,
    "2": 10,
    "3": 4
  },
  "scene_coverage_distribution": {
    "complete": 115
  },
  "bbox_null_count": 0,
  "person_attribute_distributions": {
    "pose": {
      "chair_sitting": 3,
      "floor_sitting": 56,
      "prone": 28,
      "side_lying": 11,
      "standing": 6,
      "supine": 21,
      "walking": 8
    },
    "support_surface": {
      "chair": 3,
      "floor": 129,
      "unknown": 1
    },
    "torso_ground_contact": {
      "broad": 60,
      "none": 40,
      "partial": 33
    },
    "torso_orientation": {
      "horizontal": 60,
      "inclined": 9,
      "upright": 64
    }
  },
  "strict_JSON_success": 1.0,
  "strict_JSON_success_count": 115,
  "strict_JSON_denominator": 115,
  "source_hash_binding_success": 1.0,
  "source_hash_binding_success_count": 115,
  "source_hash_binding_denominator": 115,
  "latency_p50": 8.866479397998773,
  "latency_p95": 14.125282256302308,
  "latency_count": 115,
  "latency_units": "seconds",
  "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED",
  "verification_scope": "offline supplied rows only; strict raw JSON parsing and image hash binding are upstream attestations corroborated against completed records; raw bytes, image content, and request freshness are not independently verified",
  "validation_errors": [],
  "floor_sitting_ALERT_count": 0,
  "floor_sitting_RECHECK_count": 5,
  "floor_sitting_NO_ALERT_count": 50,
  "floor_sitting_ATTENTION_count": 0,
  "gate_checks": {
    "manifest_rows_exact": true,
    "output_rows_exact": true,
    "new_model_requests_exact": true,
    "completed_requests_exact": true,
    "row_integrity_and_protocol": true,
    "valid_responses_exact": true,
    "strict_JSON_all": true,
    "source_hash_binding_all": true,
    "ground_lying_60": true,
    "floor_sitting_55": true,
    "ground_ALERT_at_least_57": true,
    "ground_ALERT_RECHECK_60": true,
    "floor_ALERT_0": true,
    "floor_RECHECK_at_most_5": true,
    "floor_NO_ALERT_at_least_50": true,
    "multi_person_rows_5": true,
    "multi_person_single_group": true,
    "multi_person_ALERT_5": true
  },
  "gate": "PASS"
}
```

## KNOWN_FAILURE_REGRESSION_1
```json
{
  "status": "COMPLETE",
  "phase": "regression",
  "rows": 1,
  "expected_rows": 1,
  "output_rows": 1,
  "new_model_requests": 1,
  "completed_requests": 1,
  "valid_responses": 1,
  "ground_lying_count": 1,
  "ground_lying_ALERT_count": 1,
  "ground_lying_ALERT_recall": 1.0,
  "ground_lying_ALERT_RECHECK_count": 1,
  "ground_lying_ALERT_RECHECK_coverage": 1.0,
  "ground_lying_decision_counts": {
    "ALERT_GROUND_LYING": 1,
    "RECHECK_VISUAL_UNCERTAIN": 0,
    "NO_ALERT_NORMAL_POSE": 0,
    "ATTENTION_NEAR_GROUND": 0
  },
  "floor_sitting_count": 0,
  "floor_sitting_decision_counts": {
    "ALERT_GROUND_LYING": 0,
    "RECHECK_VISUAL_UNCERTAIN": 0,
    "NO_ALERT_NORMAL_POSE": 0,
    "ATTENTION_NEAR_GROUND": 0
  },
  "multi_person_rows": 0,
  "multi_person_group_count": 0,
  "multi_person_ALERT_count": 0,
  "multi_person_details": [],
  "people_count_distribution": {
    "2": 1
  },
  "scene_coverage_distribution": {
    "complete": 1
  },
  "bbox_null_count": 0,
  "person_attribute_distributions": {
    "pose": {
      "kneeling": 1,
      "prone": 1
    },
    "support_surface": {
      "floor": 2
    },
    "torso_ground_contact": {
      "broad": 1,
      "none": 1
    },
    "torso_orientation": {
      "horizontal": 1,
      "upright": 1
    }
  },
  "strict_JSON_success": 1.0,
  "strict_JSON_success_count": 1,
  "strict_JSON_denominator": 1,
  "source_hash_binding_success": 1.0,
  "source_hash_binding_success_count": 1,
  "source_hash_binding_denominator": 1,
  "latency_p50": 6.998123899000348,
  "latency_p95": 6.998123899000348,
  "latency_count": 1,
  "latency_units": "seconds",
  "OBJECT_LOCALIZATION_ACCURACY": "UNVERIFIED",
  "verification_scope": "offline supplied rows only; strict raw JSON parsing and image hash binding are upstream attestations corroborated against completed records; raw bytes, image content, and request freshness are not independently verified",
  "validation_errors": [],
  "floor_sitting_ALERT_count": 0,
  "floor_sitting_RECHECK_count": 0,
  "floor_sitting_NO_ALERT_count": 0,
  "floor_sitting_ATTENTION_count": 0,
  "target_item_id": "P4D_PLAN::PF_P4D_POS_CURLED_G003_V05",
  "target_operational_id": "PFV4_SCREEN_0066",
  "target_people_count": 2,
  "target_unique_person_id_count": 2,
  "target_person_decision_counts": {
    "ALERT_GROUND_LYING": 1,
    "RECHECK_VISUAL_UNCERTAIN": 0,
    "NO_ALERT_NORMAL_POSE": 1,
    "ATTENTION_NEAR_GROUND": 0
  },
  "target_person_decisions": [
    {
      "person_id": 1,
      "decision": "NO_ALERT_NORMAL_POSE",
      "reason": "CONSISTENT_NORMAL_GROUND_POSE:kneeling"
    },
    {
      "person_id": 2,
      "decision": "ALERT_GROUND_LYING",
      "reason": "HORIZONTAL_GROUND_SUPPORTED_TARGET:prone"
    }
  ],
  "target_final": "ALERT_GROUND_LYING",
  "target_image_decision": "ALERT_GROUND_LYING",
  "target_image_reason": "AT_LEAST_ONE_RELIABLE_GROUND_LYING_PERSON",
  "gate_checks": {
    "manifest_rows_exact": true,
    "output_rows_exact": true,
    "new_model_requests_exact": true,
    "completed_requests_exact": true,
    "row_integrity_and_protocol": true,
    "valid_responses_exact": true,
    "strict_JSON_all": true,
    "source_hash_binding_all": true,
    "regression_target_identity": true,
    "regression_ground_lying": true,
    "regression_at_least_2_unique_people": true,
    "regression_person_ALERT": true,
    "regression_image_ALERT": true
  },
  "gate": "PASS",
  "request_count": 1,
  "PFV4_SCREEN_0066_people_count": 2,
  "PFV4_SCREEN_0066_person_attribute_decisions": [
    {
      "person_id": 1,
      "decision": "NO_ALERT_NORMAL_POSE",
      "reason": "CONSISTENT_NORMAL_GROUND_POSE:kneeling"
    },
    {
      "person_id": 2,
      "decision": "ALERT_GROUND_LYING",
      "reason": "HORIZONTAL_GROUND_SUPPORTED_TARGET:prone"
    }
  ],
  "PFV4_SCREEN_0066_final_decision": "ALERT_GROUND_LYING"
}
```

## 边界与历史
- 115张与单张已知错误均为已消费开发资源，不是独立验证。
- 5张多人DEV仅1个scenario group；不宣称多场景泛化。
- bbox仅作机械合法性/关联，不是人工框GT。OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED。
- hash核验不等于全量像素语义核验；人工逐图审核不是本次合成开发前置条件。
- 已知回归旧crop同时包含跪地者与躺地者，不采用“躺地者完全未进入crop”解释。
- V4-A0 SCREEN_FAIL；REV15仍因15/55坐地误报失败，正确ground ALERT为145/145，不能使用81.18%错误分层；V5-A0为90/230正常负例RECHECK超标失败，未请求该回归图。
- RECHECK不是已确认倒地；coverage不是立即告警召回。
- 未运行完整DEV、其余SCREEN、VAL/Holdout、机器人控制或生产集成。

NEXT_ACTION=PROPOSE_FULL_DEV_EXTENSION_PLAN_ONLY
