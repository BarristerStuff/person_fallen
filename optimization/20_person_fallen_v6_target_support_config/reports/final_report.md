# V6-A0 Freeze 前请求阻塞

`FINAL_STATUS=V6_FREEZE_BLOCKED_BEFORE_REQUEST`

候选 freeze 已建立，但首次请求前只读核验发现已冻结 runner 与 freeze 的预算字典接口不一致：freeze 显式包含 full_dev/val/holdout=0，runner 只接受三个 key。未创建任何 claimed、raw response 或 completed 记录，模型请求为0。按规则不修改 runner、不重封 freeze、不创建 V6-A1。

NEXT_ACTION=WAIT_FOR_EXPLICIT_FREEZE_RECOVERY_AUTHORIZATION
