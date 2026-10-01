# 自然检测候选进入 owner RGB-D 后验更新事务

本轮功能源码 `63b053fa30a508a0c73dcff44d47a645f5a1362f`；分支 `codex/pc-a-natural-candidate-update-20261001`；base `0061bf82c5db70367f8afa513478e3e86c4ca470`（PR88）。已 fetch 并核验共享集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`，未改集成分支、原用户树或 STATUS_B。

本轮处理真实检测候选与旧观测事务之间的接线缺口。新 `natural-candidate-single-position-raw@1` 在每次原件消费/核验时，从 owner 原始 RGB 重新运行固定官方权重 SSDLite，再用原始 depth/self-pose、既有 affinity 和位置模型重建公开候选及表面读出。配置不接受 caller 提供的框、seed、检测分数或三维点；原 fixed-box profile 保留。

## 功能与保留的科学边界

- 候选来自自然像素检测；用公开固定规则 `candidate-method-id-then-valid-grid-uv@1` 选择首个可用读出，保留其他候选与全部有效/无效 seed。规则延续前序公开规范顺序的开发选择，未使用类别、私有 mask/对象 ID、目标位置或验证误差选框/像素，未改变既有 0.5 开发过滤值。
- 该排序是工程诊断规则，不是目标身份算法。帧 candidate UUID 只标识本次检测。相同像素不同 observation UUID 可能改变候选 UUID 排序，不能将跨 capture 选择变化解释为跟踪。
- 检测分数不写入 likelihood 或 identity mass；现有同帧 affinity 也不充当跨时身份概率。自然候选的最终目标关联仍是原显式受控假设，保留 unknown/aggregate。新外观/三维关联基线已询问用户，未答复前未实施；不能报告自然世界身份已闭合。
- 原单测量原子事务、逻辑去重、回滚、SQLite 恢复和按原 cutoff 的撤回重放被复用；新候选 profile 列入精确类型注册和消费端完整 raw 重算。未知 subclass 或 proof 自报 profile 不授权。
- 空检测或候选深度全无效明确拒绝此次更新，数据库/后验不变、物理交付保留；它们不授权负观察或假测量。随后可发起新的有效 capture；成功消费后第二个 measurement 仍明确不支持。
- 自然读出源、选择函数与常量、官方权重内容、torch/torchvision 版本纳入 binding。完整伪造 target/读出即使神经 q 有效，也须通过原始 RGB-D 独立重算。

## 验证与失败记录

目录 `/private/tmp/cpswm-pc-a-natural-candidate-update-20261001`；原证据 `/private/tmp/cpswm-natural-candidate-evidence-20261001`。核心测试环境借用上一轮完整 `.venv`，不是重新独立安装。SSDLite 官方权重使用全摘要核验的本地副本；测试通过 `CPSWM_SSDLITE_WEIGHTS` 显式提供，缺少它时感知集成测试会 skip，不能称通过。

开发初轮 12 passed / 3 failed：三个 fresh 子进程恢复测试把 JSON 里的 checkpoint 路径字符串直接交模型加载器，触发 TypeError；修正测试装配为 Path，原失败保留。后续三个 fresh 阶段及两种新增攻击共 5 passed。此开发修复未绕开恢复/依赖核验。

严格 `mypy`：392 个源文件无问题。新增真实模型测试使用上一轮已提交归档的 RGB 像素，但 depth、语义、身份关联、残差、先验、效用明确为夹具；该测试不是新物理采集，SDK 私有标签未进入方法。真实新 Unity 实验另列。

冻结源码后顺序 R1 **35 passed / 426.19s**、R2 **73 passed / 142.63s**，均无失败或跳过。1022 个所列源码/测试/工具/配置文件摘要未变；两轮有交叉覆盖，不合计为独立样本。[第一轮](ADVERSARIAL_REVIEW_1.md)、[第二轮](ADVERSARIAL_REVIEW_2.md)及 evidence 日志/JUnit 可复核。本轮为实现者 A 自审，不是独立 B；全仓验收和自然任务收益仍开放。

## 下一主项

自然候选接线完成后，依据用户对未校准关联开发基线的选择，加入外观/三维候选比较、多候选与未知分支；不能直接将本次首候选当成世界对象。多帧相关性、正式身份概率/接受门槛、长期记忆和任务收益仍需后续模型与实验。完整统一框架与原分类/主动澄清对照保持。

## 双审后的实时 Unity 验证

使用上一轮建立的独立本地 SDK `/private/tmp/cpswm-ai2thor-owned-20261001`，同一固定 south-320 scene 与实际冻结源码运行新 runtime。`live_probe.py` 由默认 collector 选择并执行一次 RotateRight 30°，实际 owner action `3ac24e38-a147-4268-bd55-05cbb02641e6`。新 RGB-D 进入自然候选 profile；此前测试所用归档图像未进入此次传感器输入。

固定官方 SSDLite 检测出 **1 个 bottle 候选**，score 0.557375729（未校准、未作为 density）。自然框为 `[70.9697876,88.8618622,99.0055695,164.0621185]`；64 个公开网格点均深度有效，规则选择 `[72,93]`，软表面点约 `[0.1841711,1.0715165,2.0983413]` 米。这个表面代表点不是对象中心，类别预测不构成身份真值；未检查其是否等于语义夹具中的任务对象。

实际语义状态不变、后验发生变化、原交付重复消费无效；后续 problem 绑定新后验，planner 选择停止（受控效用下无进一步增益），不能把停止解释为找物成功。该次物理 SDK 记录保持初始/三次准备动作/一次模型动作分离。完整原件、模型、DB、SDK 私有验证轨迹归档在 evidence/live-transaction.tar.gz，模型输入不使用私有实例标签。

`live_fresh.py` 以新解释器直接恢复实际 live DB 副本，重建自然候选并核验全链；后验摘要与实时结果相同，未创建传感器 executor，未重跑语义 producer，原数据库完整字节摘要不变。见 evidence/live-fresh-verification.json。核心环境、官方 detector digest、脚本和完整结果均保留；14 MB 官方 SSDLite 权重不重复提交，需按 environment.json 的完整 pin 提供本地文件。权重路径是 profile 配置绑定的一部分，本轮没有验证旧 DB 跨机/异目录迁移。

结果范围：自然检测候选已经实际进入一次 owner 观测→真实后验→下一决策的工程链；语义/身份/残差/先验/相机效用仍是明示开发条件，不是自然身份闭合或行为收益证据。
