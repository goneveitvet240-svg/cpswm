# Structure Two 自适应运行时两轮对抗审核与独立终审补充

日期：2026-09-10
对象：Architecture A（架构 A）下的 P0–P5 本地生产控制流
证据等级：D0 local engineering evidence（D0 本地工程证据）

## 审核结论

两轮原定攻击测试均在发现问题、修改实现后重新运行通过；但 2026-09-10 的独立终审又构造出这些
测试没有覆盖的 positive-path attacks（正路径攻击），因此“两轮测试通过”不能解释成审核完备。
当前已绑定的是 transitively read-only P0–P5 plan/consumption registries（传递只读 P0–P5 计划/依赖
注册表）、部分真实控制流、
different-location detected full CIAV closure（异位置检测的完整主动验证闭包）、same-location fast
verification（同位置快速验证）与债务发行/隔离重放入口；
negative-observation full closure（未检测到观测的完整闭包）尚缺。它不是六条已经完整区分的生产计算
策略，更不是已证明优于最佳固定路径的科学方法。

- 第一轮最终结果：`8 passed`。
- 第二轮新增终审反例后：`12 passed`。
- 基础自适应路径测试：`10 passed`。
- readiness（就绪度）仍为 `PROTOCOL_IMPLEMENTED_EXECUTION_BLOCKED`；独立终审把四个过强 gate
  降回 `false`，当前共有 12 个 blocker。

## 第一轮：执行、回滚与状态机

攻击面包括：

- 待偿债务后继续执行新 transition（状态转移）并堆叠债务；
- 分支状态已经演化后重放旧债务；
- 同一债务重复结算、step index（步骤编号）倒退；
- CIAV realizer（主动验证观测实现器）中途失败；
- CIAV 合法 no-action（不行动）却发生长期写入；
- CIAV 确认同一位置时被误当成新位置迁移；
- 路由、策略、CIAV 输入和逐算子耗时未进入轨迹身份链。

发现并修复：

1. **同位置 CIAV 错接 CHEH。** CHEH 首切片只接受位置发生变化的端点；原实现会把“仍在原位置”的
   检测强制送入迁移入口并回滚。修复后使用
   `same_location_fast_verification`：只调用可逆 fast-action verification（快速动作验证），明确
   `long_term_write=false`，不伪造移动事件。
2. **债务可能继续堆叠。** 普通自适应入口现在在存在 pending debt（未偿债务）时 fail closed；只能
   使用绑定原 transition/checkpoint（转移/检查点）的 `replay_adaptive_debt`，P5 也不能从低层入口
   绕过 replay authorization（重放授权）。
3. **验证前写入屏障不足。** P3/P5 的 primary pass（首轮执行）现在与延迟 CIAV 路径一样强制阻断
   长期写入；no-action 或失败不会把未验证结果写进长期人物习惯。
4. **逐算子耗时回执不完整。** CF-BOCPD 与 CCRR 的实际阶段耗时被分开测量，已执行回执携带
   `elapsed_ns`，结果按算子聚合。这只关闭 operator wall-clock receipt（算子墙钟耗时回执），不等于
   feature extraction、router、energy、memory、storage、replay 和 sensing 的完整资源核算。

## 第二轮：伪造、依赖、资源、债务与授权

攻击面包括：

- 对错误路径选择重新计算自洽哈希，再与另一 execution plan（执行计划）拼接；
- 把运行时拒绝策略的三个授权标志由调用方改成允许；
- 替换 authorization policy hash（授权策略哈希）；
- 有未偿债务时直接拼接 P5；
- 使用同一源码位置但不同闭包捕获值的 CIAV callback（回调）；
- 回调执行中修改其绑定闭包或重绑授权策略；
- trace sink（轨迹接收器）修改债务账本、重放 guard（护栏）或耗时回执；
- 对整条回执链重新哈希但篡改 output-consumption DAG（输出消费有向无环图）。

发现并修复：

1. **CIAV 回调身份只绑定源码文件。** 两个相同源码、不同 closure（闭包）值的回调原本可获得相同
   身份。现在绑定 callback symbol（回调符号）、源码 SHA、loaded code object SHA（已加载代码对象
   哈希）、默认参数和 closure content SHA（闭包内容哈希），并在真实回调前后复算；执行中变化会使
   整笔事务回滚。
2. **选择回执可由调用方自洽重哈希。** 生产执行入口现在使用冻结特征重新运行 deterministic router
   （确定性路由器），要求结果与提交的选择回执完全相同。仅 plan id 和 feature hash 相符不再足够。
3. **授权标志属于调用方。** 新增默认全拒绝、运行时自有的
   `AdaptiveAuthorizationPolicy`；特征必须绑定当前 policy SHA，三个标志必须逐项等于运行时策略。
   这建立本地策略绑定，但不冒充独立权限保管。
4. **自适应 DAG 只检查“引用先前输出”。** 轨迹验证器现在按 P0–P5 和两种反馈闭环核对精确依赖边、
   phase（阶段）、binding kind（绑定类型）与债务 origin（来源）；整链重新哈希也不能把错误边变合法。
5. **重放 guard 对象身份未保留。** rollback（回滚）现在原位恢复债务 ledger（账本）和 replay
   authorization set（重放授权集合），避免外部持有的旧引用与运行时内部对象分叉。

## 独立终审：两轮攻击矩阵漏掉的正路径

终审不是只检查命名攻击，而是从每个正向 readiness claim（就绪主张）反推完整信任链。它发现：

1. **生产状态没有生成路由特征。** 普通 `process_adaptive_transition` 接收 caller-constructed
   `AdaptiveRouterFeatures`（调用方构造的自适应路由特征），只核对状态/策略哈希、授权标志和债务
   计数；冲突、歧义、未知质量、行动 margin（余量）和 regime hazard（阶段风险）没有生产 extractor
   （提取器）。同一生产状态可由调用方改变这些分数而选择 P0/P1/P2/P3/P4。因此
   `path_eligibility_policy_bound_to_production_state=false`。
2. **六个计划不等于六种计算内核。** P0 有单独的安全维护/债务逻辑，P3/P5 有 CIAV 形态；但
   P1/P2/P4 的主要六算子仍调用同一个完整 core pass（核心通路），差异主要存在于 mode receipt
   （模式回执），没有实现名称所承诺的 event/actor-local、regime-local 和 combined kernel
   （局部事件人物、局部阶段恢复和组合内核）。协议规定的 P0–P4 failure/timeout → P5、P5 failure →
   receipted safe abstain（带回执安全弃权）也尚未实现。因此
   `legal_path_executor_bound_to_production_runtime=false`。
3. **完整后果身份链尚未成立。** 路由特征来源不真实、路径内核不完整且 fallback 缺失时，已有哈希链
   只能证明“给定调用方特征后执行了这段部分控制流”，不能证明从 production state（生产状态）到
   path、action 和 next state（路径、行动和下一状态）的后果身份。因此
   `p0_p5_consequential_runtime_identity_established=false`。
4. **资源核算把调用方数字当成了成本。** `feature_extraction_cost_units` 由调用方提供且没有进入结果
   聚合；feature extraction 和 router selection（特征提取与路由选择）没有真实计时，其余资源轴也
   未绑定。因此 `resource_accountant_bound_to_production_execution=false`，只保留
   `executed_operator_wallclock_receipts_bound=true` 的窄结论。
5. **债务状态机曾可被旧入口永久卡死。** 产生 pending debt 后，legacy wrapper 或公开
   `system.core.process_transition` 曾可继续演化 core，导致旧债务拒绝重放、新自适应步骤又被债务阻断。
   现已在 production-owned core mutation guard（生产拥有的核心写入护栏）中统一阻断，并增加组合
   回归测试；被拒绝的旧/直连调用不再破坏随后合法重放。
6. **不可信 realizer 曾可改写步骤状态。** frozen dataclass（冻结数据类）可被
   `object.__setattr__` 绕过；回调可在 trace 已记录 step 之后修改 caller context，使 trace step 与
   `_adaptive_last_step` 分叉。生产入口现在先复制并验证 runtime-owned context snapshot（运行时自有
   上下文快照），回调后的提交只读取该快照，并检查 trace step 与最终 runtime step 一致。独立复核
   随后发现低层 public adaptive overload（公开自适应重载）最初漏掉同一复制步骤；该入口也已补齐，
   并增加专门回归。
7. **多个局部正向诊断仍曾过强。** pending-debt guard 真实覆盖的是 legacy/traced-legacy、direct-core
   transition 与装饰过的 public core mutator，不覆盖 policy/evidence-trace wrapper rebinding；CIAV
   对异位置 detected observation 才有完整下游 closure，同位置 detected 只有 fast OPCEU，negative
   observation 没有完整下游 core closure。debt replay 也只证明隔离入口存在，不绑定 origin
   policy/trace。因此 readiness 现把这些事实拆为窄 source-bound diagnostics，并令 all-wrapper barrier、
   full-outcome/negative-observation closure 保持 false，不再用宽泛 true 掩盖范围差异。
8. **工程清单曾漏掉 benchmark JSON fixtures（基准 JSON 测试夹具）。** 测试会读取这些夹具，但旧
   v0.3 草案只绑定 code/config/data/split/test/toolchain。当前清单新增独立
   `test_fixture_contract` scope（测试夹具合同范围），并对 symlink/非普通文件失败关闭；历史 v0.2
   manifest 保持原始日期快照，不用当前源码重哈希伪装成历史证据。
9. **计划注册表曾不是不可变。** `REGISTERED_ADAPTIVE_PATH_MODES` 与 consumption graphs 原为可变
   `dict`，factory 与 validator 同时读取同一对象；修改注册表后，两者会共同接受被篡改的 plan。当前
   mode registry、legacy graph、所有 path graph 及 feedback graph 均使用深层 `MappingProxyType`
   只读包装，并新增 registry mutation regression（注册表变异回归）。

这次终审没有选择或发明上述路由特征的科学定义，也没有用占位公式冒充实现。特征定义、局部内核
语义、路径预算和失败策略仍需项目所有者冻结；完整七算子范围保持不变。

## 两轮审核后的全仓回归修复

两轮自适应审核通过后，完整 engineering audit（工程审计）还暴露了两个环境指纹的假漂移问题；均已
修复并重新运行正式审计：

1. `.venv/bin/python` 与 `.venv/bin/python3` 可能是同一解释器的不同 symlink（符号链接）。环境
   指纹改为绑定 canonical resolved interpreter path（规范解析解释器路径）及二进制 SHA-256，不再
   把入口别名误判为解释器变化。
2. 未激活 shell 与 `uv run` 可能只在是否显式提供 `VIRTUAL_ENV` 上不同。指纹现在绑定 effective
   virtual environment path（实际虚拟环境路径）的哈希；缺失变量与显式指向同一环境等价，指向其他
   环境仍会改变指纹并被拒绝。

该段工程审计是当时工作树上的 current-local recorded audit（当前本地记录审计），不建立 recorded
execution authenticity（记录执行真实性）、hermetic build（密闭构建）或 independent custody
（独立保管）。独立终审改动后的最终工程工件与数值须以末尾重新生成的 manifest、receipt 和
checkpoint 为准，不能沿用此前哈希。

## 仍然明确未建立

以下 12 项是独立终审后的 readiness blocker：

1. durable cross-system trace/state atomicity（跨系统轨迹/状态持久原子性）；
2. path-specific operator budgets（路径级算子预算）；
3. frozen exhaustive branch-point manifest（冻结穷举分支点清单）；
4. production-owned router feature extractor（生产自有路由特征提取器）；
5. debt replay versus eager-reference recovery equivalence（债务重放相对即时完整参照的恢复等价）；
6. empirical power/ICC binding（经验功效与组内相关绑定）；
7. independent confirmatory custody（独立确认集保管）；
8. exogenous production RNG binding（生产外生随机数绑定）；
9. distinct path-specific kernels and registered fallback（不同路径内核与登记失败回退）；
10. end-to-end P0–P5 consequential runtime identity（端到端 P0–P5 后果运行时身份）；
11. full adaptive resource accounting（完整自适应资源核算）；
12. long-horizon action consequences（长期动作后果）。

因此 `shadow_execution_authorized=false`、`scientific_superiority_established=false`。本轮没有删除七个
算子、隐藏事件、多人物责任、开放世界未知、可逆归因、主动验证或具身反馈中的任何一项。

## 最终工程冻结

- adaptive runtime 基础/第一轮/第二轮/readiness：10/8/12/54 passed；结构二定向合并回归：229
  passed；checkpoint 独立回归：13 passed；
- 全仓 core audit：3,789 passed、1 skipped、1 xfailed；P0 adversarial matrix：118 passed；其余
  mypy、Ruff lint/format、compileall、frozen/offline dependency check、`git diff --check` 全部通过；
- 7-scope manifest SHA：
  `ebf05dad4785182c139a552658344acd9a3b812e3437f32aabfa5dcbe84ac9ff`；
- readiness content SHA：
  `f1356ad5aa2ac427c4d9168acd79dc43084e8246be264eb423f9521ff077a54b`；
- engineering audit receipt content SHA：
  `1dc800c0a2271beda1cd0e6d69bf12a5dd48937ce8aca1b5c47ac72137b3d0f7`；
- engineering checkpoint content SHA：
  `c0da629d5f6da45890409afee3808cd8b7ca11370e784ef8fedc42192f7408d6`；生成与 no-fresh verify 均通过；
  生成过程本身完成 fresh task recomputation。

这些哈希与通过数只证明 current-local recorded audit（当前本地记录审计）内部一致；
`recorded_execution_authenticity_established=false`、`hermetic_toolchain_established=false`、
`independent_custody_established=false`。

## 复现命令

```bash
uv run --frozen pytest -q tests/test_structure_two_adaptive_runtime_adversarial_round1.py
uv run --frozen pytest -q tests/test_structure_two_adaptive_runtime_adversarial_round2.py
uv run --frozen pytest -q tests/test_structure_two_adaptive_runtime.py
uv run --frozen python apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py
uv run --frozen python apps/evaluation_runner/run_structure_two_adaptive_compute_predeath.py \
  --verify benchmarks/structure_two/structure_two_adaptive_compute_predeath_readiness_v0_1.json
```
