# 完整提议样本合同与 ProcTHOR 调度：电脑 A 交付

2026-09-13。分支 `codex/pc-a-proposal-scheduler-20260913`，base `6e07ab682a9ec15e959e1a50001e237877bc4773`。开工 fetch 成功，电脑 B `c4eb20b045edb9dc34937f2b9d1038475a02e74a`。不修改 B 的五项生产边界或 W1/W2，不自动合并共享集成分支。

## 结论及未关闭项

已实现可执行的全轴样本合同、分离导出、全因子概率回执合同、多实例/多跳角色日程、真实 ProcTHOR 几何调度及因果图片释放入口。**这不是完整训练数据缺口已关闭，更不是默认联合主干/七算子闭环完成。** 旧 49,428 步训练世界及失败报告保持原样，没有补标签改写历史。

最终真实试运行 `procthor_run_07`：官方训练房屋 0，3 个调度身份、7 个模拟日、2 个同类真实 Kettle 实例、42 个事件；实际几何检查 42/42，36 个 RGB-D 观测候选，7 次迟到释放，源前后相同。静态相机的旧 run_05 中目标可见数为 0，固定观察路线后仅 **2/42** 个事件目标可见。角色实际执行数仍为 **0**。不能把有彩色图片、完整日程标签或非空 JSON 视为有效提议训练数据。

仍未关闭：

1. 日程角色是 evaluator（评测侧）的合成身份，不是 Unity 画面中的可观测真人/化身。交接完整角色链在计划/合同中存在，但执行器只执行对象几何变更，不能冒充拾取—搬运—真人交接的物理执行。
2. `late_correction` 当前有早期同实例事件引用与延迟释放队列；它**尚无感知端的错误报告→有来源的新反证→修订标注生产者**。迟到图片不是已验证纠正证据。
3. 真实像素尚未经已批准的检测、身份/角色不确定性及机会模型转换为合法 typed evidence（类型化证据）。仅 2/42 的目标可见覆盖不具备训练准备资格，未把其余 40 次变成负观测。
4. 六操作的合法/非法路径和全轴样本目前是**组件合同测试**，未从原生联合主干执行历史生成经审核的训练标签。主干原生全轴候选/模型、完整 q、真实三解析块及同一连续历史的 RGRC/CIAV 行动反馈验收不属于这次已完成项。
5. 网络参数、连续状态含义/噪声、训练预算没有代用户确定；没有启动训练、采购或付费计算。正式 D1 100×10/200×5/1000×5 规模未缩减，单屋日程只是开发连通/采集试运行。

## 样本合同及边界

补充最终分母核验：2/42 为所有事件的评测侧目标可见数，其中一次是未选择观测、没有释放给方法。真正释放的 36 个候选中只有 **1 个**目标可见（1/36）；该帧属于迟到释放，也不自动成为有效纠正标签。精确修订汇总见 `final_inventory_04/summary.json`，保留此前未分层的摘要。

`src/cpswm/data_preflight/proposal_samples.py`、机器可读 `final_inventory_03/proposal_sample.schema.json`：

- H 为有 event ID、时刻、实例、位置、动作及交接接收者的完整链；拒绝重复事件、倒序、未结束链、持有者错误与跨实例串线。未决假设使用显式 unresolved，不以缺失补全事实。
- R 从完整 H 检查有序 pickup_actor/carrier/handoff_giver/handoff_receiver/placer；重复角色以 `carrier:2`、`handoff_giver:2` 等保留第二次、第三次出现，支持多跳交接。此为数据合同命名，现有生产消费者尚未整体接入该扩展。
- I 每个候选关联一个具体实例或 unknown_instance；同一训练样本可包含两个相似实例竞争，支持集与候选中都保留未知人物/实例与未决后备。
- C/Z 复用冻结枚举，不把世界的三原因或 baseline/shifted/recurrent 直接当成六原因或阶段决策。r 使用既有游程字段。V 绑定粒子/事件/修订/统计/账本引用，检查祖先 DAG、父粒子与父修订一致、孤立/重复/跨账本等问题。
- branch/revise/retract/reactivate/rejuvenate/preserve_unresolved 分别表达推断提案，不从物理事件类型自动推导操作标签。撤回不能替换为无关状态；恢复需已撤回来源；后缀复苏需连续修订后缀、实际迟到引用和 replay_required，不能声称追加新事实。允许真实空历史的 unresolved 引导，不要求手工注入已解析父粒子。
- 复用此前合法可见前缀导出；原始记录必须同时满足发生/到达时间，标签只能引用已导出记录。未知、未观测、模糊、已验证负观测不互相转换。
- `JointProposalProbability` 要求 operation/parent/H/R/I/C/Z/r/V 九项完整有序条件分解、支持归一化、选中项非零、前缀上下文绑定、联合 log-q 求和一致。`bind_probability` 可进一步绑定具体模型输入与完整候选。它不是现成神经生产者，也不证明自报模型/候选支持真实性。
- `export_sample` 重验证嵌套输入，分开 model_input、training_targets、audit_only。模型输入含先验粒子/修订上下文，但不得含本样本未来真值或标注；这些输入的真实托管仍需来源审查，格式校验不构成权限认证。
- 批量检查以 house ID/内容摘要和 schedule block 防跨分区；禁止确认分区。组件样本没有默认训练授权。外部标注者自报 `reviewed_offline/native_trace` 不自动取得可信身份。

## 调度与真实仿真

`procthor_schedule.py` 按显式 seed/day/actor/instance 参数生成变化日程；开发测试覆盖 5 个种子 × (7天3人/10天4人/14天5人)。每日六类事件顺序不同，角色链允许多跳，两个物理实例分别维护连续位置。habit_drift 使用同一调度身份、明确 baseline→shifted→recurrent 目的地课程；这是开发课程，不是重新冻结科研先验。

`procthor_execution.py` 使用实际传入 controller。每次动作保存 SDK lastActionSuccess、RGB-D、完整评测 metadata；对两个对象做动作前后位置验证，验证只改变所选实例以及 no-move 不移动。失败中止并保留局部记录，不自动重复不确定动作。

必须注意其动作是 `TeleportObject(forceAction=False, forceKinematic=True)`，**评测侧外生几何干预**，不是模型提出的具身操作。`forceAction=False` 保留碰撞检查；kinematic 模式不证明重力/抓取/搬运过程。固定 observer route（观察路线）事先登记，按时钟索引，与当前目标真值/可见性无关；所有候选锚点与观察路线预先分开，未使用逐步追踪真值的相机。

原始请求、对象真值、计划角色、纠正引用只进入 evaluator_only。面向可见候选的目录仅含传感文件及摘要；`capture_prefix.py` 按 received_tick 投影，不向模型交付全历史释放表，拒绝路径穿越、替换传感文件、重复释放和提前到达。磁盘目录是逻辑隔离，**不能向方法进程挂载整个离线目录**。

## 外部来源和完整性

- ProcTHOR-10K 官方仓库 <https://github.com/allenai/procthor-10k>，固定数据版本 `439193522244720b86d8c81cde2e51e3a4d150cf`。
- 仅下载其 train.jsonl.gz，官方 LFS SHA-256 `ee3c4aa14b4d8f0895fecfb5fdaca59395427ca1018b2f9aeeedbc61e5824587`，53,314,510 bytes，完整下载校验相同；未读取 val/test。此前重复下载的部分文件停止、保留并排除，不用于运行。
- 官方 `main.py` 同时加载 train/val/test，故本批不调用该全分区 loader：<https://github.com/allenai/procthor-10k/blob/439193522244720b86d8c81cde2e51e3a4d150cf/main.py>。
- 已有 Python 3.11.16 / AI2-THOR 5.0.0 / Unity `f0825767cd50d69f666c7f282e54abfe58f1e917`，未安装/更新用户环境。驱动、SDK controller、二进制、原房屋、初始化、每步请求/结果均留存并绑定。
- 对象移动接口核对对应 Unity 版本公开源码；标准拾取/放置与 teleport 的区别参考 <https://ai2thor.allenai.org/ithor/documentation/interactive-physics/>。不能根据传送成功声称完整具身行动。

## 失败保留与最终证据

- procthor_run_01/02：返回原始接触姿态时与 CounterTop 碰撞；第 3 步失败，未关闭碰撞检查。
- run_03：显式 2.5cm 初始间隙调整后 42 事件完成，但运行中格式化代码，source_unchanged=false，不能作为冻结交付复验。
- run_04/05：42 事件完成、source_unchanged=true；静止相机目标可见 0，采集覆盖不足。
- run_06：固定观察点与预设对象锚点冲突，SDK 正确拒绝；不记通过。首次针对该不完整历史的摘要脚本拒绝长度不一致，未输出成功摘要。
- run_07：实际执行 42/42、36 个非恒定 RGB 候选、7 个延迟释放，源码前后一致；固定观察路线后目标可见仅 2/42，人物角色执行 0。见 `final_inventory_03/summary.json`。事件 tick 不是秒；7 日为加速离散日程，不是连续跑了 7 个自然日。
- CPU run_01：109 passed，Ruff 1 项行长失败；run_02：119 passed/Ruff/mypy 通过；run_03/04：121 passed/Ruff/mypy 通过。最后回归以 run_05 manifest/log 为准。故意绕过枚举构造的旧负例 warning 原样保留。

每个 run 独立创建、不覆盖。审查绑定具体文件摘要/提交，不能将早期测试套在更新源码上。这里只完成修复方工程检查，不声称全面独立验收或穷尽攻击。

## 复跑与训练准备入口

在本分支工作目录，以含开发依赖的 Python 运行：

```sh
python docs/reviews/pc_a/proposal_scheduler_2026-09-13/run_checks.py my_new_check
python tools/structure_two_prepare_proposals.py --input reviewed_samples.json --output prepared_new
```

第二条要求真实提供符合 schema 的样本；本批没有伪造 reviewed_samples.json。输出分别为 features.jsonl/targets.jsonl/audit.jsonl/readiness.json；拒绝目录覆盖。组件演示需显式 `--allow-component-fixtures`，即使六标签全齐也保持 training_ready=false。

真实仿真使用已有 AI2-THOR Python 和 Unity，命令完整 argv 在 run_07/receipt.json；核心参数为 `tools/structure_two_procthor_pilot.py --train-archive <固定训练压缩包> --unity-binary <已有本地二进制> --output <新目录>`，可显式设置 `--days 7..14 --actors 3..5 --seed ... --house-index ...`。官方训练压缩包不重复放入 Git；使用上文固定来源/hash。本地仅打开 index 0 进行开发。

## 下一道门

先解决有效可见覆盖与人物可见证据来源，再接早期错误身份/角色解释、迟到新反证的实际记录及修订谱系，取得原生状态变更的六操作标签。由 B 对完整合法正路径、伪造但完整输入、时间/谱系/账本权限、标签与模型特征隔离独立审查。然后盘点真实样本覆盖和分区托管，明确模型/连续语义/预算后才启动训练。

数据质量检查技能使本批把“未观测”与“负观测”、几何执行与角色证据、合同样例与原生标签分开，并实际检出了静止相机 0 可见覆盖；这些限制没有被测试总数覆盖。
