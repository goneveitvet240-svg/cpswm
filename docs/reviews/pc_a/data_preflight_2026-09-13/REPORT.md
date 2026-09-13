# 本机三项建议复核与实现交付 2026-09-13

## 结论

建议有条件可靠，已经推进。必须修正两点：不能把允许 method-free 检查的旧训练世界直接授权给新提议器训练；不能从主项目解释器未安装 SDK 推断整台电脑不能仿真。本批未训练模型、未改科研路线/阈值、未替用户选择连续状态含义或噪声、未动 B 的三个生产文件或 W1/W2 专属代码。

本批 base `2a7a547fba30412d9349605aff3a7df7c60d6b3a`，分支 `codex/pc-a-data-preflight-20260913`；fetch 已核验 B `c4eb20b045edb9dc34937f2b9d1038475a02e74a`。代码逐文件绑定见 `run_03/manifest.json`。这些成果未整合入共享集成分支，也不是独立验收。

## 数据质量盘点

本轮动态盘点对象仅为 `structure_two_world_rolling_train_gate_v0_4.json` 明确指定、已用于调优的训练世界。先验证继承的 v0.2 manifest 字节摘要，只使用训练 seeds 和训练轨迹/观测 seeds；没有生成验证/确认世界，没有运行方法臂。最小粒度为 world/trajectory/observation/day，不把重复观测轨迹当独立世界。

| 项目 | 实际数量 | 解释 |
|---|---:|---|
| 训练世界 / 轨迹 / 步 | 24 / 144 / 49,428 | 整个指定训练抽样，不是全项目数据全集 |
| 观测到 / 未观测到 | 26,512 / 22,916 | 未观测不等于 verified absence |
| 未知人物真值 | 4,176 | 审计侧统计，不导出给方法 |
| handoff 机制标签 | 2,218 | 不代表存在完整有序角色链 |
| 不同事件链模板 | 1 | 所有步均 pick_up → carry → place |
| 感知位置与真位置不一致 | 3,505 | 观测侧错误，并非已构建多物理实例任务 |
| false true_identity_match | 0 | 此物理身份真值字段恒真，不能证明 I 轴覆盖 |
| 六种 proposal operation 标签 | 每类 0 | 尚无完整提议训练目标 |

高置信、高影响缺口：H 只有固定三事件模板；R 无完整角色赋值链；I 无竞争物理实例/unknown_instance；C 的三个生成原因不等于冻结六原因支持；Z 的 baseline/shifted/recurrent 不等于阶段决策标签；r、V 无显式粒子游程和修订谱系。负观测、未知地点、实际到达时间、执行反馈、连续测量与噪声模型也未在这个数据结构中表达。

同时静态检查现有 `structure_two_neural_amortized.py`：`TrainingExample` 只有 features/cause_target/regime_target，目标为当前可见信念的原因/阶段自蒸馏；不能冒充全轴监督。该旧收集器把训练 seeds 放在名为 VALIDATION 的容器里，不能仅按枚举名推断分区泄漏或合法性。本批未调用该训练/评测入口或读取其封存 seeds。

数据质量技能使本轮明确区分粒度、缺失与负观测、生成真值与可见信息、发生与到达时间，以及开发数据与确认数据。后续需要新增覆盖和使用授权，而不是直接开始训练。可复跑入口为 `tools/structure_two_data_preflight.py coverage --output <新文件>`（需本工作树 src 在 PYTHONPATH）。附 `coverage_companion.ipynb` 便于检查代码，notebook 本身未另行执行。

## 已实现的可见前缀导出

`src/cpswm/data_preflight/visible_prefix.py` 接受既有 observation opportunity、detection、actor responsibility 合同和独立 received_at 表。发生时间和到达时间都在 cutoff 内，且父观测/结果已经可见时，记录才入前缀。未返回保持 result=null；not_observed、ambiguous、verified_absence 不互相改写。

- 保留选择概率、可见结果、人物后验及其 reference prior，避免遗漏导致再次使用错误先验。
- 不导出全轨迹/世界摘要、种子、全局阶段变化点、真值、metadata、trace_id 或证据 URI；来源摘要仅在 audit_only，不能将整个 CLI 输出喂给模型。
- 重验证嵌套可变输入；拒绝重复 ID、孤立结果、混合 household/session、不合法早到时间、未选择却出现检测或负证据、oracle 人物证据。
- CLI 只接受明确 train/development envelope，拒绝额外顶层真值、确认分区和输出覆盖。

`development_example_01` 是从既有 D0 合同生成器产生并通过真实 CLI 导出的开发示例；cutoff 处导出四个 observation rows。received_at 使用该符号生成器的 recorded_time，明确不是实时到达日志。它不等于完整训练集，更不是传感器采集证据。

限制：到达时间、partition、字符串模型 ID 和原始可见字段来源依赖可信采集所有者。自报 train 或匹配摘要不构成独立托管/权限认证。未知地点地图合同、完整类型化主干状态、纠正/修订记录和全部动作特征尚未接入这个初版导出器；不能把字段格式校验称为完整来源真实性证明。

## 仿真采集接口及真实运行

`src/cpswm/data_preflight/simulator_capture.py` 直接调用传入 controller.step，保存 RGB/可选 depth 与实际 lastActionSuccess。objects、actionReturn、errorMessage、全局姿态等只放 evaluator_only；观测候选不得直接充当已经授权的方法输入。动作须在运行所有者明确提供的采集动作集合中。未知执行结果/中断使会话停止接收动作，不自动重复可能已经执行的动作。

初检事实：主项目 Python 3.13 环境没有 ai2thor，`run_03/simulator.json` 真实返回 exit 2。进一步环境清查发现 `.venv-ai2thor` Python 3.11.16、SDK 5.0.0，以及本地 Unity `f0825767cd50d69f666c7f282e54abfe58f1e917`，可执行文件同时含 x86_64/arm64。

随后已运行两次独立的真实 iTHOR 单场景连通性验证；最终取证 `real_simulator_02/result.json` 包含完整 argv、解释器/SDK路径、SDK源码摘要、Unity二进制摘要、驱动/采集代码摘要及前后源码一致性。没有修改主项目环境、安装软件或下载房屋集。日志写入本批独立目录；运行后停止本批 controller。

每次运行均为同一 controller 的 FloorPlan1、64×64 RGB-D，按 Pass → RotateRight → MoveAhead 执行；首次三次成功均为 true，RGB 有非零像素变化，深度为非负有限实数。最终运行的实际结果以 `real_simulator_02/result.json` 为准。保留 `real_simulator_01` 初次原始采集，不覆盖为新证据。

严格边界：这是 **真实 iTHOR 采集传输链**，不是 ProcTHOR 房屋采集、D1 长期多人日程、机器人真实世界实验、默认联合主干或七算子闭环。动作由连通性脚本提出，不是模型决策。评测目录与候选目录只是逻辑隔离，不是 OS 权限隔离；部署时不能向方法进程挂载 evaluator_only。

参考：
- AI2-THOR SDK 与采集：https://ai2thor.allenai.org/ithor/documentation/ 、https://ai2thor.allenai.org/ithor/documentation/environment-state/
- ProcTHOR-10K：https://github.com/allenai/procthor-10k
- 项目 D1 冻结协议仍要求 3–5 人、7–14 天、六类事件与 house/schedule block 划分；本批没有用三步连通性缩减这些要求。

## 检查与下一步

- `run_03`：43 passed（新增 29 + 既有 D0 14）；Ruff、4 个新源文件 mypy 通过。一个故意绕过枚举构造的负例产生序列化 warning，已保留。
- `run_01`：22 passed / 15 fixture errors、Ruff/type errors 保留；原因是初始 fixture 假定第一条检测存在人物证据，已改为沿真实人物证据反查检测与观测。`run_02`：37 passed。没有覆盖非绿色旧输出。
- profile、CLI、SDK smoke 是不同范围；主解释器 preflight exit 2 未被算进测试通过率，也没有掩盖后来独立解释器的真实成功。
- 下一步：为完整 H/R/I/C/Z/r/V 与六操作建立具备明确使用权限的新训练样本合同；接 ProcTHOR house/schedule 数据来源与事件调度；校准测量和实际可见输入；网络参数和算力预算明确后才训练。没有训练工件、完整 D1 或完整生产闭环签收。
