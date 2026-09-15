# P2L diagnostic manifest report

The fixed and diverse manifests were selected only from the frozen P2 DESIGN manifest before new P2L requests.

```json
{
  "source_manifest": "/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/01_internal_split/p2_design_manifest.csv",
  "source_manifest_sha256": "f221e760bd1e6a86c648a60750db7d6f06119c7b872da894cf121e17ed6a79d1",
  "source_role": "P2_DESIGN",
  "fixed_count": 1,
  "fixed_media_ids": [
    "IMG_003745"
  ],
  "diverse_count": 16,
  "diverse_role_counts": {
    "positive": 4,
    "negative": 4,
    "hard_negative": 8
  },
  "diverse_group_count": 15,
  "holdout_rows": 0,
  "fixed_manifest_sha256": "102bb4aeb9db7c8861789499d96c71f52b1af57d37bfa4eb48748ce37978acc1",
  "diverse_manifest_sha256": "e9f2d8b9cc9df254ebd4d6692a40c8e8caaf652be794cb40cf56fd53d66970e2",
  "selection_uses_p2_val_individual_errors": false,
  "selection_uses_p2_val_predictions": false
}
```
