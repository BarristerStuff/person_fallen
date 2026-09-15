# V5-B0 Full DEV Recovery R1 终态

**FINAL_STATUS=V5_B0_FULL_DEV_EARLY_GATE_FAIL**

Recovery 使用同一冻结 V5-B0：复用115条pilot结果，新请求274条后按预注册条件 `E_AUXILIARY_HIGH_PRIORITY_ALERT` 不可逆早停。未执行47条（auxiliary 27、visual_uncertain 20），因此不能把partial结果写成完整436门禁。

## 观察结果

- Ground lying：观察145/145，ALERT=145，RECHECK/NO_ALERT/ATTENTION=0。
- Normal negative：观察230/230，ALERT=0，RECHECK=8，NO_ALERT=221，ATTENTION=1；RECHECK率=3.4783%。
- Floor sitting：55条，ALERT=0，RECHECK=5，NO_ALERT=50。
- Auxiliary：观察14/41，ATTENTION=13，**ALERT=1**，pending=27。
- Visual uncertain：观察0/20，pending=20。

触发样本：`V5_B0_FULLDEV_EXTENSION_0274` / `V2_ORIGINAL::IMG_003795` / taxonomy=`pushup_plank`。模型结构化属性为 prone、horizontal、broad、floor，冻结人物规则产生ALERT。其 evidence 提到前臂/脚支撑，但 policy 明确不解析 evidence，不能用自由文本后验修改结果。

## 协议

- 新请求 claimed/completed/unknown/not-started = 274/274/0/47。
- raw/strict parser/policy replay、payload和源hash均由独立零推理审计核验；43项检查通过、0分歧。
- 没有 completion lock、协议错误、截断、重试或恢复续跑。
- 新274条时延 p50=3.0174s、p95=18.6092s、p99=19.5839s；历史115时延单独保留，不混合称作同批测量。

## 数据与验证边界

- 原VAL100经metadata复核：media/image SHA 100/100重合，P1R已完成100请求，`P1R_VAL_IS_PRISTINE=false`；不能包装为首次独立验证。P1R manifest实际无item_id，此信息缺口未被补造。
- VAL/Holdout模型请求=0，VAL图像读取=0，HOLDOUT_CONSUMED=false。
- OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED；合成DEV及合法bbox不证明现场、视频或机器人性能。
- 当前候选关闭，不创建B1/V6，不进入fresh final evaluation。

NEXT_ACTION=CLOSE_CURRENT_MODEL_CANDIDATE
