# 完整 DEV 扩展提案（未执行）

本次 115+1 请求预算已经全部用完，本文件不构成后续执行授权。

1. 保持 V5-B0 的 Prompt、schema、人物/场景策略、模型及768 token参数、图像字节不变，不创建B1。
2. 若取得新明确授权，先单独冻结完整DEV执行协议与来源/暴露审计。只有严格绑定一致时，复用本候选已经新推理得到的115条结果；不得用V4历史主路替换。
3. 完整436中其余321条最多各新请求一次；对应分层算术为85倒地、175正常负例、41辅助、20视觉不确定。此处未准备扩展manifest、未读取额外图像、未执行额外推理。
4. 建议完整DEV继续区分立即ALERT召回与ALERT+RECHECK coverage，并冻结正常负例ALERT=0、总RECHECK≤10%、坐地RECHECK≤5及NO_ALERT≥50等门禁；具体协议须新授权评审后冻结。
5. 当前坐地5/55 RECHECK恰到上限，且比历史V4同子集增加4条；必须报告复核成本，不依据这些结果修改本候选。
6. 多人样本本次仅1个group；输出人物数与bbox机械合法不证明目标枚举或定位准确。OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED。
7. 全部数据仍是已消费合成DEV，不是独立验证，也不证明机器人复拍、视频或现场效果。VAL/Holdout与生产集成不在该扩展提案内。

NEXT_ACTION=PROPOSE_FULL_DEV_EXTENSION_PLAN_ONLY
