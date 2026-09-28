# 当前功能源码的最终两轮交叉复核

实际代码 `b1969f30b85434452f6b23ec53c93d84799ff62f`。第一轮145通过，第二轮69通过，**共214通过、0失败、0错误、0跳过**；这是两轮顺序A自审，不是B验收或完备安全证明。每条命令执行前后全部Python与依赖文件与受测Git一致。第一轮保留10条Pydantic序列化警告，完整日志未清洗。运行于同一台Mac、实际CPU神经推理和SSDLite权重。

第一轮覆盖原生粒子/批次、修订验收、后验投影、联合生产、连续相机和反馈。第二轮覆盖完整伪造/修订来源链、生产者绑定、非空来源撤回后完整重放、实际神经生产及恢复、像素反馈恢复和连续状态恢复。具体15个测试文件、完整命令、源码文件摘要与JUnit见[evidence/final-integration-attempt02](evidence/final-integration-attempt02)。这些检查验证当前修改相邻的主干，不覆盖整个研究框架的全部失败方式或所有仓库测试。

前次`b0a2abaeb945ab60f8fd6697ec10595db92a8596`的尝试为145通过，加64通过/5跳过；缺少`CPSWM_SSDLITE_WEIGHTS`参数，不能声称214通过。该记录完整保留在[evidence/final-integration-attempt01](evidence/final-integration-attempt01)。发现后显式传入已有官方权重，并在当前源码完整重跑两轮，未把新5项补拼到旧结果。

两版外部执行器以`.py.txt`保存于evidence。它们在A主仓output运行，固定路径写明于源码；复制到别的机器必须明确调整执行目录、结果目录与权重路径，不能称原样SQLite迁移。后续交付提交只改Markdown/证据，不改变受测Python；新Python改动应使本审查过期。
