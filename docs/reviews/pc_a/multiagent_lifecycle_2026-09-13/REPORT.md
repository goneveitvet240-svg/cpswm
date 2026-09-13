# ProcTHOR 多 agent：因果定位、入口修复及两轮作者审核

2026-09-13。**PARTIAL：诊断与拒绝错误接纳的入口修复已完成；ProcTHOR 真正多人生成尚未实现/验收。** 没有更换正式 D1 环境，没有把胶囊 agent 当人物，没有训练或修改 Unity 二进制。

## 版本与范围

- 分支 `codex/pc-a-multiagent-lifecycle-20260913`，base `6a008aedd9c588a7716206eba60b3a57f9fc94d4`。
- 入口/会话/测试冻结：`0b46b7de077c6b25e675648deb8b5026c901c9eb`。
- 原始 Unity 包记录器冻结：`14708f93aa006b465ddfb7a9e8823e0fb2311dee`；该提交只增强诊断记录器，不改入口算法。最终 `*_wire_frozen_03` 绑定此 SHA 和运行前后逐文件摘要。
- fetch 核验 B `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`，集成 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`。不写 `src/cpswm/system`、B 文件、科学配置或共享集成分支。
- SDK 5.0.0 / Python 3.11.16；单元与相邻回归使用项目 Python 3.13.5。两种环境分别记录，不称为 Windows 复现。

## 实际发现

同一 Unity 程序，同一固定训练房屋，完整原始传输对照：

| 条件 | Initialize 原始完整包中的 agent 数 | 原来无 guard 的行为 | 修后行为 |
|---|---:|---|---|
| FloorPlan1，请求 1 | 1 | 成功 | 成功；独立转向/复位通过 |
| FloorPlan1，请求 2 | 2 | 第二个 agent 的 Pass 可达 | 两个 agent 分别右转/左转；其他 agent 不动 |
| ProcTHOR，请求 1 | 1 | 建房成功 | 建房成功；转向/复位通过 |
| ProcTHOR，请求 2 | 1 | Initialize 成功回执；随后 CreateHouse 成功；向 agentId=1 发 Pass 超时 | **Initialize 后立即 AgentRosterError，未发送 CreateHouse/Pass/转向** |

另外，建房后再次 Initialize(2) 的未修复对照仍返回 1，向 agentId=1 发 Pass 超时，见 `procedural_post_2_r2`。这不是仅把初始化放到建房后就能解决的现成能力。

最终 4 个真实案例在 `*_wire_frozen_03/`；请求 2 的 ProcTHOR 案例退出码 1 是正确报告未满足能力，**不是多人 PASS**。三个合法控制退出码 0。每条记录包含实际发送参数、Unity 包类型、完整 metadata/patch、SDK 解码结果、帧摘要、序号和动作状态。图像字节未归档，不宣称人物像素覆盖/检测/角色证据通过。

`Initialize` 的原始返回在四组都是 FieldType.METADATA（类型 1 的完整包），不是 SDK 用旧缓存重建的快速 patch。因此可排除“SDK 只是把两个 agent 错数成一个”这一解释。普通场景的请求 2 确实生效，也排除了所有场景都忽略 agentCount 的解释。

## 根因证据与仍有的边界

1. SDK reset 的实际顺序是 Reset Procedural → Initialize → CreateHouse。过去第二次探测保存的是 CreateHouse 的成功回执，不能作为 Initialize 的独立验收。
2. 真正承载 AgentManager 的程序集是 **AI2-THOR-Base.dll**，不是 Assembly-CSharp.dll。前者 SHA-256 为 `431c291648600927a524b48173a343e43dd3bf55bc383dd8d16f77a19c5eb984`。本轮用 dnfile 0.18.0 / dncil 1.0.2 只读解析实际 IL，记录在 `il_frozen_02.json`；没有修改程序集。
3. 该实际 IL 确认：addAgents 在 Procedural 且 agentCount>1 时抛 NotImplementedException；普通场景则进入可达位置/追加 agent 分支。这与固定源码及真实场景差异一致。
4. 实际 IL 同时确认一个错误回执的机制：AgentManager 将 Initialize 分发给当前旧 controller；Initialize 中 SetUpPhysicsController 清空列表并通过 createAgentType 新建 primary controller；新 controller 执行自身 Initialize 后才调用 addAgents。若后者抛异常，外层 BaseFPSAgentController.ProcessControlCommand 的 catch 在**旧接收者**上调用 actionFinished(false)，而后续 metadata 来自已注册的**新接收者**。这解释了限制失败仍可能呈现新 controller 的成功回执。

证据等级：**实际传输 + 实际程序集静态控制流共同支持的高置信根因定位**。未做 Unity 内部动态打点或修后 Unity 构建对照，不能写成“已直接观测到两次旧运行的内部 throw/catch”，更不能宣称完整后端已修复。旧两次运行没有原始包和程序集绑定，因此本轮新复现实验不能倒写其历史记录。

早期检查 Assembly-CSharp.dll 没找到限制文本，进一步类型枚举后确认该 DLL 仅有 6 个其他类型，已纠正；**没有得出源码/运行程序版本不匹配的结论**。仅检查启动程序或一个错误程序集不足以认证业务源码。

主来源：

- [固定版本 AgentManager](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/AgentManager.cs)
- [固定版本 BaseFPSAgentController](https://github.com/allenai/ai2thor/blob/f0825767cd50d69f666c7f282e54abfe58f1e917/unity/Assets/Scripts/BaseFPSAgentController.cs)

## 已实施修复，不冒充新增后端能力

- `agent_roster.py`：人数精确相等，ID 完整唯一，初始化逐 agent 成功，场景一致，位姿有限且非完全重合，活动回执与目标 agent 对齐。位姿不完全重合检查**不是碰撞体不相交证明**。
- `VerifiedAgentSession`：绑定原始传输 metadata、SDK 解码、活动 ID、序号和前一状态；拒绝重放、跳号、外部重置、原始/解码错配、非法寻址和会话内重新建房。任何不确定动作后会话不可继续；动作前非法参数不消耗合法会话。
- 原几何 pilot 增加其真实单 agent 合同检查；旧多人探测加入精确人数与回执检查。新诊断入口在每次 Initialize 返回时立即验证，阻止“人数不符仍继续”。
- 记录器修复：SDK `_build_server` 用类对象身份比较，不接受直接传入子类；本批专属 Controller 显式创建记录服务器，未改安装的 SDK。保留 `ordinary_1` 首次记录器失败，其不是仿真器实验；`ordinary_1_r2` 等才是实景结果。
- 初始化中途异常也能清理本批 Unity controller；新的诊断 CLI 失败退出码为 1。未自动重试不确定动作。

任意调用者伪造整套 controller、传输与 metadata 仍不能由本模块认证；controller 来源由真实运行 owner 负责。本模块不是攻击者同进程完整控制下的安全边界。自主导航、物理交接、人物外观、感知跟踪与七算子后果不在这次测试的 PASS 范围。

## 两轮对抗审核

这是作者自我对抗复核，不冒称电脑 B 独立审核。测试控制器全部显式标为组件 fixture；真实 Unity 对照独立归档。

| 归档 | 第一轮 | 第二轮 | 意义 |
|---|---:|---:|---|
| audit_01 | 29 passed | 11 passed / 4 failed | 抓到 stale / raw active ID / raw roster / 外部状态变化漏检 |
| audit_02 | 29 passed | 15 passed | 修复四项后原样复跑 |
| audit_03（扩展矩阵） | 29 passed / 2 failed | 22 passed | 抓到第二个 agent 初始化失败漏检；极大整数位姿异常类型不统一 |
| audit_04 | 31 passed | 22 passed | 扩展问题修复 |
| audit_frozen_05、audit_wire_frozen_06 | **31 passed** | **22 passed** | 最终冻结源码重复复核 |

旧失败日志与对应源码快照保留，未删除断言。相邻 G1 回归另有 125+30+22=177 项通过，保留一个既有故意坏枚举 warning；在 `../proposal_g1_fix_2026-09-13/multiagent_regression_01/`。合计 **230 个不同测试项通过**，不是全仓库验收或七算子闭环通过。新增源模块 mypy、所有本批工具/测试 Ruff 通过。

## 下一项真正的能力修复

见 [NEXT_BUILD.md](NEXT_BUILD.md)。这台 Mac 的常规安装位置未找到 Unity Editor/Hub。已向用户询问是否允许安装编辑器及构建组件，尚未收到选择；不能自动接受许可或用未编译补丁宣称功能完成。

保持 ProcTHOR 为正式环境：先在旧控制器被替换前准确拒绝/报告不支持的初始化，再实现建房就绪后的额外角色生成及事务性失败处理。必须先在真实构建中验证角色注册、合法位置、独立行动、重置/重复请求与帧/相机一致性，再验证人物拿取/交接、角色证据和原生监督。

**当前：错误接纳入口已修；ProcTHOR 多人能力 BLOCKED；真实人物事件、完整连续监督、训练和默认联合主干均 NOT_ESTABLISHED。**

## 复跑

```sh
python tools/structure_two_multiagent_checks.py <新的审核输出目录>
python tools/structure_two_multiagent_diagnose.py \
  --binary <已有AI2-THOR程序路径> \
  --house docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json \
  --output <新的真实运行目录> --scene procedural --count 2 --guarded
```

真实运行使用含 ai2thor 5.0.0 的 Python 3.11。输出目录必须不存在；不覆盖历史。`--scene ordinary --count 2 --guarded` 为多人合法控制；ProcTHOR 双 agent 在当前未修后端上应明确失败，不能将退出码改成 0 来过门。
