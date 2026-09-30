# 第二轮软表面位置因子：第一轮对抗审查

结论：冻结源码 `493e05720f066c5db7173502d03b245bf74b6d43` 在下述受控组成、完整输出伪造、Native 原始观测似然及撤回恢复范围内未发现阻断缺陷，可以进入同 SHA 的 R2。该结论不代表全仓验收、电脑 B 独立验收、自然身份关联或真实仿真任务收益；真实 96 帧新实验尚未在本轮审查中运行。

审查者为电脑 A 辅助代理，参与编写 `soft_surface_position.py`、`soft_position_dataset.py` 及其测试，以及 driver 组成测试。因此这是明确披露作者参与的 A 辅助审核，不称独立 B。

## 源码与覆盖范围

工作树 `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`；base `8623e7890594fce2b3c872bd2484b30138a9f408`。最终逐项比较当前 891 份 Python 文件与 `frozen-source.json`，全部相同，HEAD 匹配且 `git status --porcelain` 为空。文件清单的规范序列化 SHA256 为 `650dae7fdd571ad3e22945e91762a584ae460465662057bb0b7f18f2a9a7a2ac`，完整清单及检查结果见 `R1/source-binding-check.json`。

本轮阅读了 6 个生产文件及对应 6 个测试文件的完整新链路：公开 RGB-D 软/均匀表面读出、私有 seed 标签连接、双参考三维残差模型、固定实验 driver、数值消费诊断、受控 Native producer。未改动这些源码或测试。复用根代理冻结前的 29 套定向回归证据：`pre-freeze-regression-01.log/json`，728 passed / 581.84 s；本次未再次运行全部 728，也不称全仓 CI。

审查确认的关键边界：公开阶段不接收 mask、SDK 对象身份、房屋划分或参考目标；模型分数从真实公开输入重新计算。相同完整网格（含无效点）和 seed 合并并保留候选来源，不同邻域保留。每个 seed 的两种估计器都保留，无效深度给明确不可用结果。私有阶段重新核验原件和公开读出，逐点查所有 masks；仅唯一且合格的归属提供 transform position / AABB center 两个独立命名参考。训练固定使用 1–8 屋；全部公开输入先完成，训练/公开修正/受控诊断均先于 validation 标签读取。

## 实际受控 CLI 正路径

`R1/prepare_controlled_cli.py` 从冻结前组成测试的受控原件复制一个 12 屋 × 8 帧数据包，并重新生成依赖。这里的 SDK、mask、候选框及三维参考是人工自洽 fixture，不是官方 archive，也没有启动 Unity。SDK/audit 的三维变化是为全秩残差组成正路径明确构造，不能解释为传感器物理真值或定位收益。

前端使用真实诊断函数和受控 decoder；前一轮 affinity 使用真实 `build` 两次并作字节复验；controls 使用真实 `build` 两次。历史 CLI 是审查目录中的显式受控 wrapper，它在新进程实际调用冻结的 `controls.build` 重新训练三种特征模型，核对输入清单及外 pin，并比较全部 controls 输出。它没有执行原官方 SDK/Unity 历史入口。其源码 token 明示为 wrapper 内容 SHA1，前端 token 明示为 synthetic fixture token，均未伪称官方 Git commit；借用算法源码另绑定当前完整 891 文件清单。

当前 `tools/run_soft_position_development.py` 则未经替换，使用实际 `subprocess.run` 和显式 argv 执行：

| 执行 | 退出码 | 耗时 | 结果 |
|---|---:|---:|---|
| actual current CLI run | 0 | 44.343 s | 96 帧、4 个模型、302 份输出 |
| actual current CLI fresh `--verify` | 0 | 44.902 s | 新进程完整重建，与 run 的 302 文件逐字节相同 |

精确 argv、环境和边界见 `R1/controlled-cli-argv.json`、`R1/run_controlled_cli.py`；执行记录为 `R1/actual-cli-cases.json` 和两份 `legal-*.log`。两份成功日志 SHA256 均为 `964bdc8511d0cd06d143fa14aafb7ea3d8e2541ff1939905d0abc741853a720c`。受控输入完整摘要及来源见 `R1/controlled-inputs-provenance.json`；最终再次核对原件未变。

该正路径保留全部 96 帧，包括 8 个零候选帧；528 个候选来源合并成 264 个邻域、16,896 个 seed。全部公开深度有效，私有连接中 12,672 个 seed 合格，4,224 个 seed 因 unmapped_pixel 为 VOID。这里的计数仅描述受控 fixture；无效深度、全部 VOID、拟合缺类/秩不足及空记录分支的证据来自冻结基线中对应测试，不能把本次正路径当成它们都出现过。

## 完整伪造与恢复后果

`R1/forge_and_verify.py` 复制合法 302 份结果，修改全部 4 个位置模型的 bias，重新生成每个模型的有效内容 pin；重新写入全部 96 个 corrected 文件（8 个空帧仍为空）、模型引用、全部逐屋/分区报告和完整 `controlled-position-consumption.json`，最后重建 report 的成员摘要及攻击者自签 ledger。公开输入、原训练残差和调用方外 pin 保持不变。因此这是可通过局部模型 restore 的成套重签替换，不能通过自签获得训练来源授权。

实际冻结 CLI 新进程 `--verify` 运行到最后完整重建比较，以 `ValueError: fresh trained outputs differ` 拒绝，退出码 1，44.993 s。攻击目录所有文件在拒绝后保持不变。随后原合法目录再次执行 actual fresh verify，退出码 0，44.467 s，合法输出亦保持原字节。证据见 `R1/complete-forgery-cases.json`、`complete-forgery-rejected.log`、`legal-recovery-verify.log` 和保留的 `forged-experiment`。

另一个实际 CLI 攻击清空缓存某帧的三个公开候选及其 geometry/frame 表示，重写公开预测 hash、两阶段文件摘要和缓存 ledger，却保留调用方原 frontend 外 pin。它在受控历史子进程的原 ledger pin 核验处拒绝，当前 driver 不进入标签读取或拟合，合法结果与攻击缓存均未被改写。见 `R1/attack_original_pin.py`、`candidate-deletion-original-pin.json/log`。该攻击证明外部 pin 拒绝被重写的缓存；它不是声称任意语义自洽、已获新外 pin 的前端实现都无法改变候选。

## Native、训练分区与标签错绑

本轮额外运行 5 个新参数化/组成用例及 2 个已有后果用例，共 **7 passed / 23.48 s**，日志 `R1/extra-attacks-01.log`，完整 argv 保存在 `source-binding-check.json`。新攻击脚本为 `R1/test_extra_adversarial.py`。

- 分别替换位置 bias、位置参考类型和 affinity 模型；每次重算相关 pin，建立新的完整 `ControlledPositionProducer` / `NeuralNativeProducer`，实际运行网络，生成包含非零 `raw_observation_likelihood` 的完整 receipts。原 owner 下 stage 均拒绝，workspace、语义账本及原 producer 的调用/消费状态保持不变；随后原合法 producer 仍可正常发布并只消费一次。
- 调换公开 seed 像素坐标后，即便外层内容摘要可重算，私有 join 仍因原件重建不一致拒绝。随后合法 join 成功。再调换标签顺序，driver 因 measurement/estimator 配对不一致拒绝，恢复原标签可生成训练行。
- 将验证 house 9 的成员文字改成 train，位置拟合仍因固定训练房屋范围拒绝，不能通过分区命名绕过。
- 重跑实际 Native 数值正路径：预更新 prior 的预测协方差使用 `HΣHᵀ+R`，完整三维 normalizer 的 raw likelihood 改变真实 posterior 权重；Gaussian 信息矩阵与信息向量符合解析结果。q 与 integration 修正相抵，观测项仍实际改变目标权重。重复发布及下一语义步仍可见的同帧来源不会再次增加信息。
- 重跑撤回后果：撤回目标 semantic event 后旧读出先失效；完整重放不另写语义账本，消费集合清空，最终权重/统计与禁用因子的匹配对照一致；新的 producer 经 SQLite 恢复得到相同 view 与状态。

这些 Native 测试使用显式 oracle 语义关联、固定框/seed、受控 affinity/残差与已声明 prior/未知分支。它们证明实际 Native receipts、统计、权重及重放的工程接线，不证明自然世界身份已学到。CLI 的 `controlled-position-consumption.json` 是数值消费者诊断，其 `native_receipts_produced=False` / `owner_pipeline_executed=False` 标志保持；实际 Native 后果来自上述单独测试，不把两者混写。

## 保留问题、边界与交接

未发现本轮受测范围内的生产缺陷，未修改任何生产源码或冻结测试。一次只读摘要打印脚本误用 ledger 的 `case`/`name` 字段导致 `KeyError`，完整错误及更正原因保留在 `R1/inspect-summary-01.log`；它没有影响任何 CLI 执行或数据。最终核验脚本通过，第二份日志避免把仍在写入的自身日志 hash 当最终摘要。

本轮并未覆盖全部可能伪造、平台、数值极端及真实场景；也未重跑官方 SDK 来源验收。固定网格 seed 之间强相关，mask 归属不保证深度点来自物体物理表面，双参考开发残差不等于正式校准。自然 I→Z 关联、未知/杂波模型、跨帧相关性、正式位置参考、朝向和真实动作收益仍未完成。未据 validation 选择新模型、阈值或位置定义；未缩小完整结构二的其余范围。

R1 交接只授权进入**同一冻结 SHA** 的 R2；任何生产修改都需要重新冻结与顺序审查。R2 通过之后再由根任务运行实际固定 96 帧实验与独立新进程 fresh 验证。本审查结束后停止写入本轮 OUT，等待根任务封存。
