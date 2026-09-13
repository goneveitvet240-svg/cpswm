# G1 工程修复与修后两轮对抗审核

2026-09-13。**G1 已实现并通过下述作者工程复核；G2/G3/G4 未完成，不签收完整训练准备或默认联合主干。**

## 冻结版本和范围

- 分支 `codex/pc-a-proposal-g1-fix-20260913`；base `f95086718ad2d7d6f0707bcae1dc6758d3417233`，来自已公开的两轮缺陷审核。
- 实际生产修复/测试冻结 SHA：`2ebd815543a9e51948c0eba237aacff8629b51ed`。最终 CPU `run_03`、真实采集 `procthor_run_01` 绑定这一版内容，源码前后摘要一致。
- 远端 B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`、集成 `bdec3ee21b7db361e390496d97ff2eb30390dc6c` 开工 fetch 核验无变化。不改 `src/cpswm/system`，未自动集成 B 或共享分支。
- 本轮承接用户公开推送授权；本人修复及两轮复核，不冒称电脑 B 独立验收。未训练、未选择网络/连续状态/噪声/预算、未读取 val/test、未选择新的科学后端。

## 修复内容

| 对应缺陷 | 实际修复 | 仍需区分的边界 |
|---|---|---|
| A1 完整提议后果解绑 | 概率回执增加 `proposal_sha256`，绑定完整 target，包括证据、修订后缀和 replay 标志；保留九项条件概率检查 | 旧无绑定回执可用于数学检查，但不可授权绑定；不等于已有神经模型或完整支持枚举 |
| A2 三时钟混淆 | 按 opportunity/detection/actor 实际发生时刻判断迟到；无 detection_time 的负结果按关联观察机会时刻 | 接收时间仍由 ingestion owner 提供；未伪造感知反证或校准噪声 |
| A3 传感真值夹带 | `status`/单位严格标量；NPZ 恰含 RGB/可选深度，校验 dtype/shape/有限非负；拒绝对象数组、额外数组、重复成员与大小不符；分配前检查 NPY 头与实际字节数，64MiB 输入/解压限额 | 文件一致性不能认证摄像头。`read_sensor_snapshot` 返回不可变已验证字节，消费者不得验证后重新打开可变路径；预期摘要必须独立取得 |
| A4 非法释放时钟 | 日程和队列逐层要求非负整数，拒绝 bool/NaN/Infinity/小数；完成时检查剩余帧及数量守恒，完成后禁止再次释放/登记 | tick 是离散逻辑时间，不是自然日秒数；没有把计划延迟包装成真实传输延迟 |
| A5 重复采集身份 | 队列同时去重事件和已选 capture_ref；失败登记不消耗合法身份 | 同一帧如需支持多个事件，应显式复用证据引用，不能复制为独立证据 |
| A6 数值坐标别名 | 使用与执行一致的 2mm 数值容差，拒绝整数/浮点不同表示的同一位置 | 不改变科学收益阈值；此为既有执行几何容差 |
| A7 可变日程 | 构造时复制支持集、事件列表与角色列表为不可变元组；执行入口再分离日程快照 | 摘要、执行、记账使用同一份快照；不声称能够认证任意恶意控制器 |

同时完成：

- **分区隔离**：输出 `train/`、`development/` 独立特征/标签/审核文件，不再把两分区混在根目录同一文件。
- **稳定样本连接**：每行有非模型用 `sample_id`、partition、field、pair digest；读取器按 ID 连接并核验三个文件的完整样本绑定，拒绝缺失/重复/跨分区/换标签和换摘要。入口要求外部留存的 manifest 摘要。模型只能消费返回的 `model_input`，不得将包含 pair digest/标签的外壳直接输入模型。
- **地点来源合同**：显式区分 snapshot、已到达 detection 新发现地点与 unknown；H 地点必须在来源支持内。快照地点再与同一快照的地点目录交叉核验。新发现地点必须绑定实际可见检测的 location entity；未知仍有合法路径，未缩小开放世界。

地点来源目录和标注者目前仍由调用方提供，`source_authentication_verified=false`；伪造目录和声明全部一致不能被内部 schema 当成真实来源认证。独立托管和真实主干快照接入属于后续 G3，不能因本轮通过而忽略。

## 两轮修后审核的实际过程

| 运行 | 原回归 | 第一轮：原反例、合法路径、来源/时间/数组 | 第二轮：完整伪造、状态机、组合后果 |
|---|---|---|---|
| run_01 | 125 passed | 29 passed / 1 failed | 22 passed |
| run_02 | 125 passed | 30 passed | 22 passed |
| 冻结源码 run_03 | **125 passed** | **30 passed** | **22 passed** |

原回归保留一个故意构造坏枚举的既有 Pydantic warning。没有 xfail、没有跳过缺陷。两轮含原 15 个审查用例及新增 37 个用例，共 52 个；加原 125 项为 177 项。范围是这批数据/调度工程合同，不是全仓库 812 或完整科学验收。

第一轮新增测试确实再次抓到了漏洞：只检查 location binding 的 snapshot ID 时，替换实体 ID 仍可通过。已增加快照地点目录交叉绑定并保留 run_01 的失败日志和当时源码快照，没有删断言过门。

原审核文件的攻击和期望行为保持不变；仅将合法概率构造补上完整提议摘要。原组件样本显式加入 @2 地点来源与快照目录，原 CLI 正例调整为分区路径。旧报告、旧源 SHA、旧失败文件与 evidence 目录均未改写。此次不是“原文件字节完全不变复跑”，而是必要合同迁移后复跑相同攻击。

第二轮额外覆盖：外部保留摘要拒绝整套重新签哈希的包；在显式接受新文件哈希的对照中，内部错误 pairing 仍被拒绝；已完成队列不能重开；失败 SDK 动作不能生成成功状态/释放证据；嵌套调用方 actor 列表修改无效；未来地点发现不进入过去前缀；修改合法修订后缀必须重新绑定 q，重新绑定后的合法正例仍通过。

Ruff 与五个生产模块 mypy 已通过，最终命令日志见 `verification/`。本轮尚不覆盖第三方摄像头来源认证、训练器恶意读取整个标签目录、原生长期账本和任务动作后果；没有将它们写成 PASS。

## 真实执行复测

`procthor_run_01` 使用原官方训练包和房屋 0，实际 Unity/SDK 5.0.0，生产源码前后相同：42 个几何事件完成、36 个 RGB-D 候选、7 次计划迟到释放；不是完整 D1，也不代表真实人物行为。保留全部初始化、SDK 请求/metadata、RGB-D 和源码摘要。运行耗时约 4.55 秒，7 天是加速逻辑日程。

新读取器另外检查实际产生的 36 帧，使用原始采集回执的摘要核对不可变传感字节；不把任何一帧自动升级为 detected/verified_absence/actor evidence。

## G2 后端能力：有证据的新阻塞

官方固定版本 `f0825767cd50d69f666c7f282e54abfe58f1e917` 的 `AgentManager.addAgents` 在 Procedural 场景对 `agentCount > 1` 有显式未实现保护：

[对应版本 AgentManager.cs](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/AgentManager.cs)

不能只根据 AI2-THOR 首页写着 multi-agent，就推断当前 ProcTHOR 支持完整多人交接。官方 [Concepts](https://ai2thor.allenai.org/ithor/documentation/concepts/) 还明确普通 agent 为胶囊形实体，不等于具有完整人体/手部交接动作的演员。

本轮做了两个真实探测，均加载同一房屋成功：

1. `multiagent_probe_01`：加载后发送 `Initialize(agentCount=2, makeAgentsVisible=True)`。
2. `multiagent_probe_02`：通过 SDK `reset(scene=house, agentCount=2, makeAgentsVisible=True)` 走场景初始化路径。

两次响应均只包含 **1 个 agent event**，`multiple_agents_verified=false`。接口 `lastActionSuccess=true` 不能算多人通过。**运行没有直接返回上述 NotImplemented 异常，因此不能断言源码 guard 就是这两次响应的直接触发点**；源码限制和两次未建成多 agent 的实测分别记录。进一步构建/初始化机制调查仍属人物后端可行性工作。

因此 G2 不是“再采几十间房”就会补上人物角色证据。下一门是用户确认后，保留 ProcTHOR 正式环境，验证可渲染多演员/动作后端和真实持有关系；若需自定义 Unity 构建，先确认工具链、演员资产许可和范围。不能静默用别的环境、胶囊颜色真值或对象传送替代完整人物角色链。

## G3/G4 与下一步

当前仓库本批模块仍没有真实感知适配器、人物行为生产者和从原生主干历史生成六操作监督的生产者。`annotation_kind=native_trace` 只是声明，不能生成证据。没有创建手填“原生样例”来伪装推进。

- G1：修复方工程检查完成；交电脑 B 按 `2ebd815543a9e51948c0eba237aacff8629b51ed` 独立复核。新的源码不能套用旧审核。
- G2：真实几何/传感采集保留可用；人物后端仍待方案确认及真实可行性门。分别建立像素覆盖、检测、实例关联、角色证据四层检查，不能混成一个可见率。
- G3：在 G2 和真实主干输入具备后，导出同一历史的证据到达、当时解释、迟到反证、实际后缀重算、账本贡献撤回/新增及后验/动作变化。六操作从实际提议与回放结果产生，不按六个物理事件名填写。
- G4：数据与来源门通过，且网络、连续状态/噪声、算力预算明确后再训练；再证明真实候选/完整 q/三个条件解析块/联合后验到 CIAV 行动与反馈。**training_ready=false、training_started=false** 保持不变。

## 复跑和兼容性

样本合同升级为 `full-proposal-sample@2`。旧数据不自动推断地点授权，不进行静默回填；迁移时必须提供真正的快照地点目录或已到达地点发现来源。旧无完整提议摘要的概率回执不得用于 `bind_probability`。

```sh
python tools/structure_two_proposal_g1_checks.py fresh_run_name
python tools/structure_two_prepare_proposals.py --input reviewed_samples.json --output fresh_prepared
```

组件示例仍需显式 `--allow-component-fixtures`，并始终保留非训练状态。新读取入口 `load_prepared_partition` 必须给定分区和外部留存的 `readiness.json` SHA-256；禁止读取根目录旧格式特征或将整个 envelope 当模型输入。
