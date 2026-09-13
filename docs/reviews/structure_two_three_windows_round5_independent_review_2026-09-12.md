# 结构二三个窗口：第五轮独立复核

日期：2026-09-12。结论：**旧缺陷确有关闭，但三个窗口不能整体签收。窗口一的统一验收编排仍需修复；窗口二可按“局部开发诊断”验收；窗口三旧三项可关闭，新增准备粒子接口仍有缺陷。完整七算子—主干协作及科学门未通过。**

本轮只审核，没有修复、合并、推送，没有修改阈值、科学协议或原窗口代码。以下“通过”只针对明确列出的测试和命题，不是穷尽安全证明。

## 1. 固定的实际交付

| 窗口 | 实际来源 | 独立副本 | 源码/测试/配置/apps/tools 文件校验 |
|---|---|---|---|
| 一 | `/private/tmp/cpswm-s2-evidence-repair-window1`，`f5089d94ba217b377f88067bc36fdb976e12a4cf`，干净 | `/private/tmp/s2-review5-w1.boRzcK` | 772 个文件一致；其中包含原环境生成的 5 个 egg-info 文件 |
| 二 | `/private/tmp/s2-comparison-audit-window2-20260911`，`aa9690146e5261d826b642c7bc4c54d2c43be31b`，干净 | `/private/tmp/s2-review5-w2.OkojBR` | 767 个文件一致 |
| 三 | `/private/tmp/s2-w3-native`，`281e88894fca527df1d54018b5053469e8c422d5` **加实际未提交 R5 交付** | `/private/tmp/s2-review5-w3.o33e1p` | 773 个文件一致；不是只审核 HEAD，也没有使用中间 final_* 失败快照 |

证据根 E：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round5_review_2026-09-12`。

- `snapshot_binding.json` 保存逐文件哈希；`source_after.json` 核查原窗口和独立副本源码仍一致。
- 窗口一 312 个旧证据、窗口二 332 个旧证据均与保全清单及上一轮 Git 来源一致；窗口三 115 个 R4 证据与开工归档内容、文件集合一致。窗口三 R5 未改变已有 `tests/test_*` 断言文件或配置。见 `preservation_check.json`。
- 窗口三新增接口的独立反例重复运行两次，均得到相同的数值结论。

## 2. 新发现：窗口一

### W1-1 / P2：新比较包的生产、测试消费及证据输出没有接成同一依赖链

位置：[build_plan](/private/tmp/cpswm-s2-evidence-repair-window1/tools/structure_two_unified_acceptance.py:503)。

固定计划先执行 `window2_comparison_and_forgery`，之后才执行 `comparison_generate` 和归因生成；编排器没有为测试绑定本次 `comparison` 目录对应的 `S2_AUDIT_BUNDLE`。

真实消费者并不会自行生成必需包：窗口二来源测试默认指向 `not-generated-round3-bundle`，另一组默认指向旧 `bundle_v2`。我在最新窗口二副本取消该环境变量，直接运行实际来源攻击用例，立即得到 `generate the current round3 bundle first`，**1 failed**。这不是窗口二正确配置的 77 项回归失败，而是窗口一编排所缺的依赖输入。

还有同一问题的输出侧：来源测试默认在 checkout 的 `source-evidence/` 写日志；本次实际回归确实生成了该目录。窗口一完整输入快照会纳入它，而固定排除区只有统一 run 区等指定产物，因而即使外部补了 bundle，测试自身输出仍可能触发 `SOURCE_CHANGED`。不应靠关闭源码漂移检测绕过。

修复要求：先生成并核验本次比较包及归因，再让相关矩阵消费该固定包；所有测试证据路径显式放入本次 run 区并留存；补真实生产者—消费者集成测试。整合最新窗口二动态测试、窗口三 R5 新矩阵和经审核的 closure 节点。不能只填空的 `CLOSURE_TESTS` 就认为入口已经可执行。

边界：当前入口仍被空 closure、旧封存输出等条件阻挡，本轮没有运行完整统一验收。这是**准备入口的可执行性缺陷**，没有证据表明已经签发错误的完整验收结果。

证据：`w2_unbound_orchestration_input.command.json` / `.stdout.log`；实际源码中的固定阶段顺序；窗口二副本 `source-evidence/`。

### W1-2 / P2：预检的解释器不一定是 pytest 实际使用的解释器

位置：[execution_environment](/private/tmp/cpswm-s2-evidence-repair-window1/tools/structure_two_unified_acceptance.py:137)、[matrix 启动入口](/private/tmp/cpswm-s2-evidence-repair-window1/tools/structure_two_unified_acceptance.py:475)。

预检检查 `root/.venv/bin/python`，矩阵却启动 `root/.venv/bin/pytest`，后者的 shebang 没有绑定到被检查的解释器。

独立反例没有恶意替换 Python、标准库或 pytest 实现：把既有虚拟环境复制到审核副本，保留自然存在的旧绝对 shebang。真实预检认可 `/private/tmp/s2-review5-w1.boRzcK/.venv`；真实测试中的 `sys.executable` 却是 `/private/tmp/cpswm-s2-evidence-repair-window1/.venv/bin/python`。共用阶段引擎仍记录 **1 passed、STAGES_COMPLETED_NOT_AUTHORIZATION**，前后环境检查未发现差异。

修复要求：通过已核验的 Python 以 `-m pytest` 启动，并验证实际测试进程的解释器和关键模块来源；加入复制/迁移虚拟环境的正反例。不能仅记录旁路解释器的包版本。

边界：这里运行的是实际阶段引擎与真实单项测试，不是完整统一验收；没有据此声称生产源码已被替换，或科学门已被误放行。

证据：`w1_launcher_probe.py`、`w1_launcher_probe.stdout.log`，以及其中指向的完整阶段日志。

## 3. 新发现：窗口三准备粒子接口

以下均通过真实 `core.stage_prepared_particle_candidates` 和 `core.prepared_particle_location_marginal`，从合法普通生产历史构造输入。只改变公开输入及其合法类型化内容摘要，没有把伪造状态写入 core。合法对照同时通过。

### W3-1 / P2：外部后验来源未被实际解析和绑定

位置：[候选来源校验](/private/tmp/s2-w3-native/src/cpswm/system/structure_two_particle_workspace.py:157)、[公共入口](/private/tmp/s2-w3-native/src/cpswm/system/prototype_spine.py:2651)。

把合法 receipt 声明为 `posterior_projection_not_likelihood`，给 `source_posterior_snapshot_id` 一个在本次运行中不存在的随机 UUID，投影项设为 10，其他事件链、proposal snapshot、账本引用仍合法。接口接受该声明并实际消费投影项，使首个候选权重从 **0.631579 增至 0.999974**。

现有检查绑定的是 `proposal.source_snapshot_id`，没有将 receipt 引用的后验来源解析成真实可用状态。“显式调用方输入、未标定”不能替代最基本的引用真实性。修复应核验被引用的实际后验及消费权限；尚不支持的投影模式应明确拒绝，而非接受一个任意 UUID。

### W3-2 / P2：条件统计的位置支持集可以逸出当前世界

位置：[统计引用校验](/private/tmp/s2-w3-native/src/cpswm/system/structure_two_particle_workspace.py:212)。

将已知实例候选的条件统计 locations 换成四个完全不在 `core.locations` 中的 UUID，重算该统计的真实内容引用。接口照常接受，位置边缘分布向这四个外部地点分配合计 **0.631579** 概率；它们没有被登记为地图扩展，也没有进入 unresolved（未解析）质量。

修复应把条件统计支持集与本运行可见/获准的地点支持绑定；若允许开放世界扩展，需真实注册及未知状态语义，不能仅靠字段类型和自洽哈希。

### W3-3 / P2：有限输入的算术溢出会静默改变概率语义

位置：[alpha 有限性校验](/private/tmp/s2-w3-native/src/cpswm/system/structure_two_particle_workspace.py:50)、[位置边缘化](/private/tmp/s2-w3-native/src/cpswm/system/structure_two_particle_workspace.py:259)、[权重归一化](/private/tmp/s2-w3-native/src/cpswm/system/evaluation_operations/structure_two_selected_method.py:455)。

两个独立反例：

1. `alpha=(1e308, 1e308, 1e308, 1e308)` 每项有限，但总和溢出。公共读出成功返回，位置概率总和加 unresolved 仅为 **0.368421**，剩余质量消失。
2. proposal log probability 为 `-1e308`，observation log likelihood 为 `1e308`，字段各自有限，但合成 log weight 为正无穷。现有归一化把非有限值当成零质量，首个合法候选权重变成 **0**，而非稳定计算或明确拒绝。

第二处归一化器是既有实现，不应说成 R5 新引入；R5 新公共接口现在可直接到达它。上述输入是数值鲁棒性反例，不是常规已标定数据的发生率估计。

修复要求：稳定求和/归一化，检查派生数值和总质量；区分“结构拒绝导致的负无穷”与“计算故障导致的非有限值”；不能返回成功的错误后验。若选择拒绝，应验证拒绝后无工作区、账本或动作副作用。

共同影响边界：四个攻击输入目前均**没有改变长期 Hybrid 账本或默认动作**，合法对照总质量为 1。因此本轮证据不能扩大成“已污染正式长期记忆”。但这些问题阻止新增准备粒子接口按其来源与概率语义签收，必须在接入默认主干前关闭。

证据：`w3_independent_prepared_probes.py`；首次与重复运行的 `w3_independent_prepared*.stdout.log`。

## 4. 已确认关闭与本轮独立回归

| 范围 | 本轮结果 | 可以支持的结论 |
|---|---|---|
| 窗口一新增编排测试 | 40 passed；0 skip/xfail | 所测进程管理、源码变化拒绝、工件冻结、等待状态等路径成立，不覆盖上述新缺陷 |
| 窗口二全部测试 | 77 passed；0 skip/xfail；733.75 秒 | 两正式入口及局部比较/动态诊断可以独立重放 |
| 窗口三原252 + R4新增105 + 邻接82 + 自动阶段44 | 483 passed；0 skip/xfail | 原有回归未被 R5 破坏 |
| 窗口三 R5 新矩阵 | 134 passed；0 skip/xfail；保留10条构造恶意模型输入的序列化 warning | 新矩阵覆盖范围成立，但没有包含本轮四个新输入 |
| 窗口三行动读出 | 30 passed；0 skip/xfail | 相邻行动读出回归成立 |
| 窗口三合计 | 647 passed | 不能替代完整协作或科学验收 |

窗口三上一轮独立发现的三项已在本轮固定交付上关闭：

- 公开 CORRECT 不再出现“返回 correct，但旧新记录同时离开提交集合”的原反例。原脚本现在报 ValueError；补充独立检查进一步确认完整执行可观察摘要不变、Hybrid/CCRR/CF/粒子工作区实例不变、原记录仍提交、新记录未遗留。不是把任何异常都算作通过。
- 已纠正历史再次冻结，原独立 oracle 现在接受未变化状态，actual/reference 均为 2。
- 相同冻结输入跨运行纠正，语义状态一致，差异路径为空；仍保留执行身份区别。

`w3_prior_boundary.stdout.log` 与 `w3_independent_prepared.stdout.log` 保存原反例与补充后置条件。各组精确 argv、环境、退出码及完整 stdout/stderr 位于 E 下 `*.command.json`、`*.stdout.log`、`*.stderr.log`。文件标签 `w3_old_513` 是启动时的命名误差，实际该组为 **483**；另有独立 30 项，不能重复计数。

第一次窗口一回归使用了审核通用 PYTHONPATH，触发入口的预期环境拒绝，得到 39 passed / 1 failed；保留在 `w1_40.*`。随后使用该树 Python、清除不允许的环境变量重新跑完整40项，得到上表结果，未改断言。不可把第一次环境错误隐去，也不可把它误报为实现回归。

## 5. 窗口二结论是否可靠

**其自述的局部开发诊断结论可靠；它明确没有取得的结论依然没有取得。**

本轮独立留存三批完整伪造矩阵：21、6、4 类攻击均 REJECTED，每批同时包含真实合法包 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，不是只有负例通过。另有两正式入口的完整正向来源重放，包含陈旧 unchecked pyc 拒绝/绕开测试。见 `w2_retained_index.json` 和 `w2_retained/` 下原始矩阵与日志。

当前固定版本的数据支持：

- 六个动态场景共84输入、83个合法三臂输出步骤；纯 P5 长期提交最大值均为0，full/fast 的 PUT_BACK 差异均为0。ordinary 参考路径虽有12–14条提交，但它不属于 direct P5，也不为其预热。
- 原1920步 P5/AMG/learned 错误数仍为85/102/533；53个缺失owner估计步骤中，共同均匀先验使AMG总错误102→85，原17步差额不能解释成完整结构优势。
- 新窗口二报告中的公开 CORRECT 缺陷指向其**本分支固定旧核心**，并没有声称检查了窗口三R5。窗口三修复后必须在实际整合源码上更新诊断断言、重生成新包；现有“预期已知缺陷存在”的测试不能搬过去充当修复验收。
- 地图权限、缺省先验、具体资源预算仍有待决定或不匹配之处。最终PCT效用和护栏已经冻结，但未执行；不是重新选择指标的理由。
- 三臂真实环境执行、环境状态改变为未测，不把解码地点正确当成机器人任务完成，也不以并行测试耗时比较算法速度。

本轮没有发现需要推翻这些局部数值结论的新反例；不等于所有公平性和依赖攻击已穷尽。W1-1 所述的无 bundle 失败属于编排集成问题，不撤销窗口二正确绑定包时的77项结果。

## 6. 七算子与完整主干的验收判断

| 命题 | 本轮判断 |
|---|---|
| 七算子在已有生产路径中存在真实调用和局部下游影响 | 有工程证据；不只是七个名字出现在trace里 |
| 原公开纠正、参考重放、语义身份三项接线缺陷关闭 | 是，在上述固定版本和覆盖矩阵内 |
| 原子统计包及分析缓存完整日志恢复接入生产 | 有非空正例及故障/数值反例回归 |
| 显式粒子具备跨步父引用、真实事件链引用和 log-q 消费 | 部分实现；本轮发现来源/支持/数值边界缺陷 |
| 默认主干自动生成完整联合粒子，并用于默认 CIAV、动作与唯一账本聚合 | **未建立** |
| 纯 P5 自主、合法、非空长期学习及实际行动收益 | **未建立**，不能由ordinary或调用方显式授权例子替代 |
| 所有纠正→延期→晋升/取消→恢复生命周期闭合 | **未建立**；窗口三已披露取消后恢复父贡献未实现、部分延期终态未覆盖 |
| 公平比较、统一证据门、科学收益 | **未通过/未执行**，不授权正式消融或密封确认 |

代码交叉搜索显示 `stage_prepared_particle_candidates` 和 `prepared_particle_location_marginal` 在 `src/apps` 只有定义，没有默认生产调用点；已有新测试也明确断言准备候选干预不改变默认动作与账本。这是“新增工程接口”与“完整方法已经进入主干”的直接区别，不应混写。

证明完整预期协作仍需在一个经指定、固定的统一版本上形成以下证据链：

1. 真实可见输入，经 OPCEU/ORRER/PCHMP 等产生并约束完整 H/R/I/C/Z/r/V 联合状态及条件统计，来源可追溯；不能只让外部调用方填满字段。
2. 同一后验实际影响 CF-BOCPD/CCRR 的阶段判断、CIAV选择、执行反馈，以及 RGRC 唯一权威账本中的非空长期贡献和后续动作。
3. 对关键边同时有公共输入的应变干预、应不变对照、完整伪造正路径、重复/乱序/撤回/反复纠正/延期终止/中断恢复；验证统计、资格、存活集合和动作后果，而非只验证调用计数。
4. 生产后缀修订与独立从头重放满足冻结容差；身份、权限、离散提交及关键动作按合同精确一致；总质量、未知质量和三类自然统计成立。
5. 在已明确的共同信息、支持集、先验、调参及预算规则下比较，并接入三臂共同实际执行环境，运行冻结的PCT和护栏。随后由窗口一重算当前证据、P0、真实工程回执和fresh检查点。

以上保留完整统一框架，不删隐藏事件、多人物、开放世界、可逆归因或具身反馈；未决科研选择仍由用户决定。本轮没有擅自指定统一工作树或合并方案。

## 7. 分窗口签收与下一步

- **窗口一：等待状态和保全成果认可；准备入口需修复 W1-1、W1-2 后再谈统一执行。** 空 closure 与旧检查点过期不能伪装成通过，也不应抹去旧证据。
- **窗口二：按“当前分支局部动态诊断完成、完整机制/公平性/科学收益未建立”验收。** 无需为追求全绿反复改指标；后续工作是在真实统一源码上更新已知缺陷断言和重算。
- **窗口三：上一轮三项缺陷关闭；R5 新接口因 W3-1/2/3 不能完整签收。** 这些工程问题与已披露的生命周期、默认主干接入缺口分别跟踪，不以科研设计待决为由搁置基础来源和数值正确性。

本轮最终结论是“**有实质修复，也有新边界缺陷；不能宣称完整七算子—主干协作完成**”，不是“647项通过，所以全系统通过”，也不是“还有缺口，所以之前修复没有价值”。
