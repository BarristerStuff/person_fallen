# person_fallen v2.0 fast-close 人工候选复核

状态：FAST_CLOSE_HUMAN_REVIEW_REQUIRED

这不是 P4D 冻结的 440 条正式人工审核的替代品，也不会解除 GENERATION_REQUIRED / FULL_REGEN_REQUIRED 硬门槛。此包只把当前已机械确认的 clean_success=202 条列成候选，供人检查图像是否与事件和规划角色一致。

## 人工填写原则

1. 必须实际查看图像后填写 accept_reject_uncertain；看不清或语义不确定时填 uncertain，不要猜。
2. planned_role、taxonomy、prompt 文本和 provider 结果只是上下文，不能直接复制为 GT。
3. reviewed_event_label、reviewed_sample_role、semantic_alignment 和 image_artifact_status 必须来自人工观察。
4. 不要把模型预测、Codex/VLM 输出、提示词或文件夹名称转换为 ground truth。
5. 页面里的“下载当前 CSV”会导出 review_manifest.completed.csv。导出后应保留原始 review_manifest.csv，由授权人员审阅导出文件并按正式流程登记；不要覆盖历史冻结文件。
6. 本包没有 NEW_VAL、C3、Holdout 或生产写入授权；在完整 P4D 440 门槛和合法人工 GT 均满足前，不得运行算法评测。

## 页面入口

直接打开同目录下的 index.html。图像使用绝对 file:// 路径引用，不复制或改写源图像。
