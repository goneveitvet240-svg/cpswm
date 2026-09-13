# 窗口二：公平性可执行检查与受控开发诊断（2026-09-12）

本轮状态：**PARTIAL（比较公平性与科学有效性尚未建立）**；本轮列明的代码修复、完整重放和回归已完成。仅操作 `codex/s2-comparison-audit-window2-20260911`，起点 `bbb9c819f464bd2c62af199fb04e4091ade7232b`，工作区起初干净。未合并、未推送，未改生产七算子、窗口一/三实现、数据配置、历史 benchmark、全局 manifest、checkpoint 或科学阈值。

证据目录：`docs/reviews/data/structure_two_comparison_audit_window2_fairness_2026-09-12/`，下文记为 E。新包为 E/bundle_v4。两个原正式验证 CLI 继续承担当前源码完整新鲜重放验证；没有另设能凭文件自报签发通过的公平性验证器。

## 修复与边界

| 问题 | 实际根因与冻结合同 | 本窗口修改 | 证据与范围 |
|---|---|---|---|
| validation 评分提前取真值 | 原 `_evaluate_single_state` 在任何解码前调用 `dataset.truth_for`，循环中把 truth 传入 combined decode/score；冻结 `shared_ciav.evaluator_truth_release_phase=after_typed_actions_committed` | 新独立 `validation_errors` 先调用原适配器、公共 decoder，再由 `SplitAccess.score_committed` 记录具体动作后取本步真值；本窗口 `run_audit` 改用安全选择封装 | E/evidence/pre_fix_truth_order.json；正负测试重跑原消费者拒绝、新消费者接受并比对真实分数。没有证据表明原模型已经使用真值作弊 |
| matched receipt 只能验证三臂彼此相同 | 三臂一起改 cost/packet、重新封装所有 hash，原 `verify_matched_consumption` 仍能接受。A1 要求实际 candidate/action/outcome/cost 一致 | 在实际消费者返回边界新增 `check_receipt`，由本次实际 packet 重建应有 receipt 字段；`check_step` 同时检查三臂、支持集顺序与可见输入 | resealed resources/packet 负例先通过原匹配检查再被新检查拒绝；原真实收据通过。这是验证缺口修复，不是发现原回放成本已被改写 |
| 缺失 owner 共同先验对照也把 SEARCH 后验重置 uniform | 旧归因构造同一个替代 typed posterior，把 current/habit 都设为 uniform，虽然只报告 PUT_BACK | 只换 habit；current 使用原 AMG current，公共解码后逐步要求原 SEARCH order 不变 | 新归因的每个冷启动对照带 `search_order_unchanged`；这不修改正式 AMG 冷启动规则 |
| 公平性字段缺少实际执行证据 | 配置、相同 packet 权限不能证明各方法消费相同特征或使用相同计算 | 按实际 train/validation 调用记录访问，记录拟合的真实数组摘要、各次 model fit；首个固定 test episode 用不改函数的调用返回/属性 opcode 探针记录真实特征、P5 evidence/actor prior、AMG likelihood、支持集获取 | 保留字段级证据并纳入主包全重放比较。探针为有界代码路径证据，不是完整数据流污点证明 |

调参仍使用原 `_fit_learned_model`、原适配器、原 12 个拟合模型/24 个 learned 候选、3 个 AMG 候选、同一 PUT_BACK validation 目标及原字典序决策；只改变真值访问顺序。新模块独立重现选择循环以免修改其他窗口依赖的历史 evaluator。回归既比较小网格真实新旧选择，也会对账全量旧 selection。原 evaluator 仍存在提前 envelope 访问，整合方应将同一修复模式应用到其负责入口；本轮没有声称全仓库已修复。

## 逐臂公平性矩阵

| 维度 | P5 | learned two-stage | AMG | 可执行证据、判断与待决定项 |
|---|---|---|---|---|
| 当步可见输入 | `PrototypeTransition` 接收 actor posterior/reference prior、mechanism、ordered role；CIAV 使用本步检测 | `_feature_row` 实际返回12维：检测、visibility/confidence、owner/non-owner/unknown、三类机制、位置变化、历史频数、归一化时间 | `observe` 将 actor posterior/reference prior 转 likelihood ratio，再与 mechanism/ordered-role 输入原 AMG | 首个固定episode实际返回探针；每步 hash/receipt 检查。信息权限相同不等于特征使用相同；不能仅因 learned 较弱认定不公平。feature 匹配要求待用户决定 |
| 时间边界 | transition context 使用 episode 长度；当前检测先释放，之后预测 | 时间特征使用完整 episode 长度，历史计数跨步保留 | 每步 observe/feedback 更新，同一 episode 保留 owner/last | 所有适配器持有完整 visible episode；没有建立严格在线对象能力隔离。固定 horizon 是否公开及公开地图权限需要明确 |
| 候选位置 | `_locations(episode)` | 同左 | 同左 | D0 `known_location_ids` 为空，实际扫描完整 episode 的 source/attempted/destination。每步支持集相同，但可能含未来才出现的位置；不因三臂一致即称公平。公共地图允许完整预给 / 只允许历史前缀二选一需用户定合同，不擅自填地图或截断支持 |
| 真值权限 | test 动作 barrier 后评分 | fit 仅 train 标签；validation 新封装先动作再评分；test barrier 后评分 | validation 新封装先动作再评分；test barrier 后评分 | 实际调用 SplitAccess，跨划分和提前访问拒绝；未提供操作系统进程隔离或独立历史托管证明 |
| 训练和调参 | 原有人工设计、既有 v0.6 validation-selected 读出；历史总人工预算未知 | train 640 行；cause/event监督和9格条件位置头；12 fit缓存复用到24组 smoothing 候选 | 本轮无监督参数拟合；3个独立 validation 参数候选 | train/validation/test仍20/20/60 episodes、固定原seed；真实 fit 和访问记录。不是等训练量或等调参预算；P5历史投入未测 |
| 冷启动/缺失 owner | 空快/慢读出回到 uniform，由公共 UUID 排序定动作 | smoothing 对称 habit_counts，经同一 decoder | 无 owner estimate 时内部 `_argmax` 取 encounter-order 首位置，包装 point mass | 公共 decoder 自身没有逐臂 tie；上游先验不同。保留原始结果，共同 uniform 只作开发对照；是否统一正式先验待用户决定 |
| SEARCH | `_current` 复制检测，负观测 carry | `current` 同规则；learned joint不用于当前位置头 | `current` 同规则，丢弃 native search rank | 每步 current/order + 原敏感性/AMG rank反例；修改合法后验可改变 decoder，但当前接口未提供方法区分力。正式 readout/search budget 需用户决定 |
| PUT_BACK | fast .7、surviving .2、regime .1 | joint(cause,event) × theta 累加 habit_counts，位置头轴顺序已测试 | native owner estimate/default → point mass | 原本就在不同归纳偏置下工作；保留強基线、普通场景，不能为优势删能力 |
| 负观测与长期状态 | CIAV/OPCEU明确 no-new-transition；正检测走生产 full-P5，长期写受门约束 | 负观测 joint仍计算；habit/current carry；跨步累计 | 负观测不创建事件；owner/last carry | 状态/closure/raw readout逐步记录；未测真实迟到反证或合法解除阻塞后的长期记忆收益 |
| 计算/缓存 | 七算子调用、状态hash和trace验证 | 固定投影、logit头、theta与计数；同一已拟合模型缓存 | 原 AMG组合推理与离散历史状态 | 独立顺序计时范围和实际fit量；参数个数不等于符号状态容量；历史训练/峰值内存/功耗未测 |
| 观测与动作成本 | 同一单候选 MICRO_VERIFY；五项成本0 | 同左 | 同左 | 逐步实际 receipt字段对 packet 检查。0是合同的诊断设定，不能解释真实净效用；动作没有改变后续D0轨迹 |

## 原始结果与受控对照

新鲜生成的 `bundle_v4`：60 episodes、1920步。E/semantic_reconciliation.json 按文件比对新旧数值；其本身只是文件比较，来源与重放证明见正式CLI日志。E/fairness_matrix.json 是可机器读取的描述性矩阵，不是额外认证入口。

| 项目 | 本轮实际结果 | 证据与解释 |
|---|---|---|
| 原始三臂 PUT_BACK 错误 | P5 85；AMG 102；learned 533 | 新包 summary 与旧 v3 的所有 summary 字段相同；180条历史episode×arm动作链匹配 |
| P5/AMG逐步分区 | P5赢17、输0、共同错85、共同对1818 | 三臂每步真实后验→动作→评分；没有把数字编入验证答案 |
| 共同 uniform 缺失 owner 对照 | 触发53步，AMG原错53→36，总错误102→85 | trigger仅为真实重放的 `amg_owner_location is None`，不按P5输赢或真值挑选；53步对照动作等于P5，SEARCH全部不变。17步差额归零 |
| 尚未检测过的子组 | 40步，原AMG错40→24 | 解释16步差额；另1步差额来自后续缺失owner估计；见逐步examples，不等于全部历史缺失能力获测 |
| 长期提交 / full-fast动作差异 | 1920步 committed=0；差异0步 | 不强制非零，不降低门槛；仅说明本分布/路径未建立长期作用证据 |
| SEARCH三臂分布相同 | 1920/1920 | 公共decoder的合法后验反例仍能改变SEARCH；区分力损失发生在adapter读出 |
| 前缀之外支持集 | 1040步 | 同步支持集不证明因果时间边界合规；权限待定 |
| 实际训练/选择 | train truth调用20；validation提交后评分17280次；12次fit、24 learned候选、3 AMG候选 | 选择receipt（含所有候选分数/hash）与旧v3完全相同；选定头64参数、投影宽8、12维raw、9格theta；全网格head-only训练乘加68,812,800，非总计算量 |

原始历史结果不覆盖；共同先验、合法后验干预均为已打开 D0 的开发诊断，不是未见确认或新科学优越性实验。P5改进0.008854低于0.02绝对门槛，原95%CI为 [0.002083, 0.017708]；不重选科学门。

独立计时在本轮并行验证启动之前完成，原始576个样本留在新包 `timing.json`，每臂192次。硬件只读补充查询为Apple M5、24 GiB、10逻辑核心；macOS26.4 arm64、Python3.13.5、NumPy2.5.2。进程CPU均值（含状态hash、P5 trace验证和公共decode）：P5 183.273ms、AMG 2.548ms、learned 2.058ms。墙钟原始数据保留但不用于排序或宣称优势；主机未独占，不能将这些数字当作纯模型内核速度、真实观测成本、等算力或净效用。P5历史开发总成本、峰值内存、GPU/能耗未测。

## 长期提交与窗口三接口交接

生产路径 `StructureTwoProductionSystem` 在 primary 阶段使用 `force_long_term_write_blocked=True`，同位置 CIAV 确认走 `same_location_fast_verification` → `apply_fast_action_verification`。当前 adapter 的 CIAV realized detected location 直接来自同一个 step.after；这解释该数据流为何频繁进入相同位置的快速确认闭包。不能把“七算子 invocation 被记录”当成长程写入或动作收益证明，也不能通过强制提交解除门槛。

E/reproduce_p5_interface.py 为固定第一个已打开 test episode 的最小真实接口复现，输出 transition.after、实际CIAV检测、closure、fast/committed/observed counts、各readout。主包包含完整1920步而不是仅此案例。窗口三应在其责任范围验证合法证据解除阻塞、CORRECT 后 write-eligibility/Hybrid/committed 闭包，不能恢复被复核拒绝的旧未经授权 promotion 规则。本轮不修改该路径，也不将它归因于“P5算法没有长期能力”。

## 来源、数值、公平与科学的四层边界

1. **来源可信（限定威胁模型）**：保留 round3 guard，两个CLI及下游源码仍受实际加载约束。测试范围仍不覆盖任意 Python/stdlib/第三方注入、任意运行时 monkeypatch、所有瞬时文件变化、操作系统/解释器被控制的情况。
2. **数值可重算**：仅两个正式入口以当前来源重新生成数据、训练/调参、逐步动作/评分/状态和归因后比较；文件自洽不是这层通过。
3. **比较公平**：未建立。支持集未来信息、共同 SEARCH、特征/训练/容量/预算差异和缺失 owner 默认规则仍有待用户明确的协议选择。
4. **科学有效**：未建立。0.02门槛不降、不重选seed，已打开数据不变为未见测试。完整七算子、隐藏事件、多人物、开放未知、可逆归因、具身反馈范围全部保留。

## 重跑、来源失效与整合

原生解释器：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`。E/reproduce.sh 记录从新目录生成、两个入口验证及全部回归的命令。并行回归耗时不得用作性能比较。新包生成中的计时独立于本轮回归，固定前2条已打开episode、3次重复、轮换臂顺序、每臂每episode新状态；只计 consume+state hash+trace validation+posterior+decode。设置 BLAS/OMP/VECLIB 线程上限为1；未控制其他窗口和系统后台负载，因此墙钟仅描述、不排名。初始化、训练、IO、真值和评分、实际机器人观测均不计入该在线范围。

所有旧 v1/v2/v3 包保留为历史记录，不能在当前新增源码绑定下直接获得当前源码一致状态；E/evidence/old_v3_rejected.log 保存拒绝，不通过改旧 hash 修绿。最终合入窗口一/三会再次改变来源，应在最终树重生成并验证窗口二主包、归因、全部伪造/来源/公平性矩阵；窗口一需重算其 current-results、P0 manifest、receipts和最终checkpoint，窗口三需重算事务链及本接口案例，不能拼接不同树上的绿色报告。

## 尚需用户决定的协议项（本轮未冻结）

| 当前差异 | 影响 | 可选规则 | 所需决定 |
|---|---|---|---|
| 支持集取自完整可见episode，known map字段为空 | 在线前缀含未来位置；也可能混淆“公开地图”与“未来轨迹” | 明确公开地图并独立提供；或因果前缀加开放未知位置处理 | 地图/地点知识权限、未知地点目标的评分方式；不能只截掉困难目标 |
| 缺失owner时 uniform 与 encounter-first point mass不同 | 本批17步差额完全受先验选择影响 | 三臂共享缺失估计规则；或保留方法原生先验并强制同时报告共同先验对照 | 哪个属于正式结果、如何声明结构先验；本批已打开，不能重新包装确认 |
| SEARCH复制当前检测 | 掩盖模型后验差别，不能验证搜索记忆收益 | 在检测前提交搜索计划；或保留现有观测时序但接入真实方法当前位置头 | 动作时机、额外观测预算、SEARCH目标和方法头实现合同 |
| learned丢弃role/reference-prior细节，P5/AMG消费它们 | 相同访问权限不等于相同信息表征 | 相同允许字段、允许各自编码；或增加信息匹配的learned强对照并独立调参 | 公平性中的“匹配”含义、强对照能力和调参预算；不以当前弱结果自动判不公平 |
| 训练/调参/符号状态/推理成本不同 | 不能把信息匹配当等算力；小参数数不足以比较容量 | 固定总预算；或报告预先规定的预算曲线/质量成本曲线 | 总预算边界、缓存/训练复用/历史开发成本的记账方式 |
| 32步且同检测CIAV快速确认；无独立迟到反证或合法解除阻塞挑战 | 无法区分长期记忆、可逆事务和完整七算子效用 | 保留普通场景并增加对称的长历史/歧义/隐藏事件/未知人物/反馈挑战；不只挑P5有利案例 | 挑战分布、普通场景比例、作用目标、确认集封存与开启授权；由窗口三负责实现闭包，由用户决定新实验 |
| 两臂以validation PUT_BACK选参，SEARCH亦对外报告 | SEARCH未被对应调参目标覆盖 | 保留分任务固定目标；或预先定义联合选择/Pareto规则 | 多目标选择合同与预算。不得在已看测试结果后重选到通过 |

## 证据覆盖限制

- 消费探针覆盖固定首条episode：4次支持集函数返回、32次真实learned特征、32次AMG observe返回、22次P5 transition返回。属性 opcode 计数仅作所观察路径的存在证据，不当作完整调用计数或全程序污点追踪；逐步数据、动作、状态和成本检查覆盖全1920步。
- 1276次正观测均进入 `full_p5:same_location_fast_verification`，644次负观测明确 `no_new_transition`；surviving/regime/pooled非uniform步数均0，fast非uniform1867步。现象由真实生产路径和留存状态支持，不能据此否认结构二完整长期能力，也不能当作其已通过。
- 新增检查在本窗口实际运行路径失败关闭，但不是Python进程能力沙箱；旧历史 evaluator 的提前真值代码仍在，不应宣称全工程真值权限已消除。
- 固定旧种子、同一合成模板、独立episode ID不是外部分布验证；真实人物歧义、迟到反证、独立反馈、多步合法解除阻塞后的记忆收益继续标“未测”。
- 来源保护本轮未重写。科学门、公平性、方法收益与外部有效性均未通过；最终报告标记 PARTIAL 指这些仍未建立的比较/科学能力，不以源码可重放通过替代它们。

learned 的64个active logit参数与12维压缩表征是已观察的实现特征；“容量不足导致差距”仍未通过容量干预建立。本轮排除了状态每步重置、位置头未接入PUT_BACK、joint轴序错误及validation选择改变这些具体假设，不能从较弱对照直接推出不公平。


两个本工作树入口已实际通过，新包 source schema=4，400个绑定文件的字节全部等于代码提交 `9b58d7e93e8646c869bfd856be0dff5c6229d82b`；各入口实际加载162个本地模块，guard策略仍为 `captured_local_source_compilation_v1`，没有使用本地pyc，declared root与执行工作树相同。`main_verify.log` 返回1920步、无历史score mismatch；`attribution_verify.log` 对真实包返回 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`。命令、解释器、工作目录、环境、起止时间和退出码在E/command_receipts.json。两个入口的验证运行时间及并行回归内部 timing 都不参与上文性能测量。

验证 schema从3变4，步骤只新增fairness_step；移除该新增字段后，其余逐步语义与旧v3全部一致。归因共同先验的PUT_BACK examples与旧版一致，新增SEARCH不变检查；脚本摘要相应改变。旧原始归因/读数不通过修改来源字段“续期”。

给窗口一的最小交接：源码改动仅三处（主审计模块、新公平性模块、归因CLI的共同先验读出），原主CLI和guard逐字未变。历史包精确路径/摘要见E/preserved_previous_artifacts.json（122文件）。最终树上重新生成窗口二v4的后续版本，跑主审计和归因强验证、原42项及新增16项；再按窗口一自身的绑定环境重算三臂比较、事后读出、延期重放、因子实验、内部D0留出五类current-results，并重验历史覆盖、P0 manifest、工程回执和完整fresh checkpoint。窗口一环境不应直接照搬窗口二的`PYTHONPATH=src`：复核明确其检查点环境指纹对此敏感。历史失败仍须保留，当前性失效不等于历史结论被证伪。


## 本轮验收与提交

- 修复代码：`9b58d7e93e8646c869bfd856be0dff5c6229d82b`。五个文件：`structure_two_comparison_audit.py`、新增`structure_two_comparison_fairness.py`、归因CLI、原完整伪造构造辅助文件（重算新增fairness字段）、新增`test_structure_two_comparison_fairness.py`。未修改原42项测试入口。
- 全部回归 **58 passed，0失败、0错误、0跳过**，1066.09秒。原20项基础诊断、6项依赖验证（含21类完整伪造）、16项来源验证全部保留；新增16项（15项边界/真实消费正负测试及1项包含6类完整公平性伪造的真实CLI批次）。耗时仅作执行记录。
- 原21类完整伪造和新增6类公平性伪造逐包全部拒绝；每个混合批次的真实新包均获得 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，不能用全批次exit1代替这些逐包结果。新增拒绝定位字段见E/evidence/fairness_tests/fairness_forgery_matrix.json。
- 来源测试14个拒绝场景与2个完整正例均通过，含A/B来源、仅下游异源、声明根不匹配、提前导入、陈旧入口/pyc、受控漂移；两种CLI各有正确源码下投毒pyc仍完整重放成功的正例。明细见E/validation_summary.json和E/evidence/source_tests/。
- 新包主审计与归因在本工作树分别完整验证，均exit0。生成、归因创建、P5最小接口复现亦exit0。Ruff、mypy通过；总记录为E/command_receipts.json、E/evidence/pytest.xml、E/evidence/regressions.log、E/evidence/ruff_final.log和E/evidence/mypy.log。
- 旧122文件字节再次核对未变；源绑定失效与整合重算要求见上文及E/source_version.json。先审查代码提交，再审查本报告/证据提交；最终统一源码后重新生成证据，不复制本分支的通过状态到不同源码树。
