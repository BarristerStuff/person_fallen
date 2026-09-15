# 开发结果与剩余风险摘要

- 115张新属性推理：躺地60/60立即ALERT；坐地0 ALERT、5 RECHECK、50 NO_ALERT、0 ATTENTION。全部115有效JSON、源绑定完整。
- 多人DEV5张全部frame ALERT，但只来自1个group；people记录数依次2、3、3、2、3。没有人工框级GT，不把这些数量视作正确实例匹配证明。
- 单张已知错误回归：2条person_id；人物1 kneeling/upright/none/floor得到NO_ALERT，人物2 prone/horizontal/broad/floor得到ALERT，最终ALERT。该人物pose是模型输出而非新增人物级GT。
- 已知回归旧crop同时包含两人，不以“躺地者未进入crop”解释历史失败。
- Pilot people_count：1人记录101张、2人记录10张、3人记录4张；scene_coverage模型输出complete=115，bbox=null=0。覆盖声明和框合法性不能证明枚举/定位准确。
- 新测pilot时延p50=8.8665s、p95=14.1253s；单张回归=6.9981s。不推算机器人现场端到端延迟。
- 当前坐地RECHECK恰到门禁上限，历史V4同55张为1 RECHECK、54 NO_ALERT，本次增加4条复核。5条RECHECK里4张输出了第二条不可靠人物记录，另一张单人物记录不可靠；此为结构化输出观察，不能在无实例GT时断言模型发现了真实第二人或产生了幻觉。
- V4同60张躺地也为60 ALERT；本次应报告为新的独立属性推理保留该子集表现，并在已知单张错误回归得到ALERT，不能说全面提高了倒地召回。
- 结果均来自已消费合成开发资源，未验证场景泛化、框定位、真实视频、机器人复拍或生产性能。
- 本次116请求用尽，未准备或执行额外完整DEV/其余SCREEN/VAL/Holdout；只有扩展提案，需新授权。
