# 07 P1A DEV report

## Confirmed facts

- DEV aggregate covers 310 unique media: 290 determinate binary GT plus 20 GT-uncertain qualitative items.
- Canary results reused=12 under identical frozen prompt/config/runner/model/endpoint/preprocess bindings; duplicate protocol requests=0.
- DEV protocol gate: **PASS**. HTTP/response-nonempty/JSON/schema/canonical success are each 310/310 (100%); thinking_present=0/310.
- Determinate alert-behavior results: TP=120, FP=29, TN=141, FN=0; Precision=0.805369, Recall=1.0, F1=0.892193, Accuracy=0.9, FPR=0.170588, Specificity=0.829412.
- Ordinary-negative FPR=0.0; hard-negative FPR=0.263636; positive recall=1.0; model uncertain count/rate=0/0.0.
- GT-uncertain qualitative predictions: positive=14, negative=6, uncertain=0; they are excluded from binary metrics.
- Valid classification latency: cold=6.653924s, warm mean=1.456773s, P50=1.453798s, P95=1.610508s, max=1.746854s.

## Gate assessment

The output protocol is valid. The project reference Precision >=0.93 and hard-negative FPR <=0.05 are not met on DEV. No prompt, resolution, ROI, threshold, GT, or label change was made.

## Freeze incident

The original DEV freeze JSON declared a manifest hash that did not match the actual DEV manifest. It remains preserved. See `p1a_dev_freeze_binding_audit.json`; this prevents treating P1A as a fully frozen DEV-to-VAL evaluation lineage.
