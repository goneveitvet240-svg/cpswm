# 批次一：恢复真实开发模型原件

恢复历史提交 `505e723170c29f8707ee19d113a5b8646680c5f6` 中的原始 Git blob，字节 SHA `5be8a0c5c87b2272049ed6e283e63feab12bcaa97b1f7b91ecaec69ad8986478` 与已有 Route C benchmark 的绑定完全一致。模型内容摘要 `a35f06274ac702e7173b1135ffdb784a9dfdb5a1369917240e59af637f08b2bf` 和 960 条训练样本记录一致。没有重新训练、改哈希或改旧基准。

恢复前额外 50 项为 33 passed / 7 failed / 10 errors；恢复后 50 passed。原非零退出、全文日志、fresh cache 域、实际解释器、源码前后哈希与完整命令保存于 `model_before_50.*` / `model_restored_50.*`。

训练/验证种子、冻结配置、manifest 哈希及历史来源见 `model_recovery.json`。原始模型使用训练可见信念，无需开启确认种子或重建数据。恢复只证明历史字节和现有绑定一致；不补签独立训练托管。该 16×8×5 开发模型只覆盖既有 cause/regime 提议，不能宣称完整七轴神经架构或默认联合主干已经完成。
