# 窗口三 R4 修复与分项验收记录

工作树 `/private/tmp/s2-w3-native`；已审核起点 `281e88894fca527df1d54018b5053469e8c422d5`。修改未提交、未合并、未推送。未修改科学阈值，未签发消融或新权威授权，未把工程修复解释为方法创新或基线优势。

**三个实证问题在下述有界正负矩阵中已关闭；完整主干和七算子尚未整体验收。** 252 项通过只说明原回归集合通过。G1/G2/G5/G6/G7/G9 仍有明确剩余工作。

## 1. 分项结论

证据在新目录 [w3_repair_2026-09-12_r4](data/w3_repair_2026-09-12_r4/)，下文简记为 `E/`。最终验收使用 `verified_*` 与 `bound_verified/`。较早 `final_*` 文件仍保留，但不是最后一次源码状态的验收依据。

| 项目 | 状态 | 已验证内容 | 边界与剩余工作 |
|---|---|---|---|
| P1 / A | **已修并验证，限所列矩阵** | 四条原独立反例的新 revision 存活、资格完整、Hybrid 有活跃记录；legacy/direct-P5/debt-replay × 同/异位置 × owner 权重；连续纠正、撤回、重复/乱序、失败/中断回滚及重试 | CCRR 可拒绝部分历史重分类；同步纠正明确失败并恢复原状态，不能返回成功后丢失新 revision。正式延期请求有独立状态回执，不强制提交 |
| P2 / B | **已修并验证，限集成参考** | 事前冻结观察输入与资格、独立操作日志校验、自行构造预期存活集合和遍历；八种故障检出，正常纠正通过 | 不证明冻结前历史来源可信性；Dirichlet/RLS/CCRR 使用新实例的共享叶模型，不能排除共同数学错误或宣称完整语义正确 |
| P2 / C | **已修并验证，非空公共混合路径** | 五条稳定前缀 → 第六条 direct-P5 同位置明确阻断 → 第七条公共 legacy CCRR HABIT_CHANGE 授权 → 原阻断记录真实提交 | 原独立 31 天输入仍无授权，结果保留；此正例不等于 adaptive-only 同位置/负观测已可固化 |
| G1 | **部分完成** | 验证现有合同内公共解禁路径；保留同位置/负观测/异位置/延期重放差异 | 纯自适应同位置、负观测没有通用慢写路径；证据独立性与候选寿命规则尚需设计 |
| G2 | **部分完成** | 反馈循环与 core 共享实际 engine/message passer；真实多轴反馈公共入口调用 ingest/infer/engine revision/统计应用；内容绑定、去重、回滚、重试 | 标准路径无该类反馈时不假调用循环；完整粒子后缀修订与全回放回退尚未接入 |
| G4 | **已修并验证，限既有输入接线** | CIAV identity-switch 概率进入真实 CCRR observe/decide，保存到事件并在重建/重放使用；固定其他输入的干预改变授权判定 | 未证明上游概率估计或校准正确；不硬设非零、不改阈值 |
| G5 | **未完成，部分设计待决** | 完整方案、类型接口、开发核、正式装配逐项对照；列出持久粒子/神经模型/log-q/条件统计/后验行动/反馈具体缺口 | 生产完整粒子、神经提议、条件化 RB 块尚未接入。已确定工程仍待完成，不全部归因于用户选择 |
| G6 | **部分完成** | 新增独立语义记忆摘要；legacy/direct/replay 同冻结输入同源码可复现，执行 UUID 仍不同；权重和账本引用改变可检出 | 仅覆盖明确列出的记忆/修订状态，不是任意 Python 对象或全部适应运行状态的完整语义序列化 |
| G7 与非 P0 绑定 | **部分完成** | 核验声明额外实例的实际成员、锚定实例和共享依赖；五公共路径 × 五方法替换与同类外来实例攻击被拒绝；合法覆盖与实际执行分开记载 | 不声称覆盖任意并发篡改或每个算子全部数学分支；七条回执不是七算子全部运行 |
| G9 | **设计待决；默认策略未完成** | 显式 caller-policy 与多轴反馈可修订；默认自主策略缺口、候选接口、风险与最小实验已列出 | 默认仍保守隔离，未自行选择行动损失或操作级证据校准规则 |

## 2. A：资格、事务与实际行为

实现位于 [prototype_spine.py](../../src/cpswm/system/prototype_spine.py)。新 revision 的资格在正式纠正事务内建立，绑定父 revision、父资格摘要、纠正反馈来源和 `EventRevisionOutcome` 内容摘要。完整 outcome 保存在只读暴露的事务序列 `revision_transactions`。纠正授权审计行的 `basis` 为 `{}`，其摘要指向完整 outcome；必须连同该 outcome 验证，不能把空 basis 当作独立证据。

缺失资格拒绝写入；普通被阻断观测仍须有现有 CCRR HABIT_CHANGE 授权。授权人必须仍为有效、未被阻断的存活观测。父资格与 outcome 关联递归验证；资格、操作日志、历史、账本、快行动项、反馈去重状态随事务提交或恢复。旧 revision 的历史资格保留用于谱系，但已移出 active/live 集合，公开 `write_eligible` 为假。

`origin_write_blocked=True, origin_path=formal_correction_transaction` 表示新纠正记录必须有显式事务授权，不表示它就是原始十条行政阻断观测。原始十条在相关纠正/撤回矩阵中始终不因重建被间接提交。

额外目标扫查发现：十二条 legacy 历史中的部分异位置纠正会被 CCRR 重分类隔离。“资格补齐”仍不足以承诺同步 CORRECT 成功。现在 `process_execution_feedback` 明确报 `CORRECT not admitted by CCRR; transaction rolled back`，恢复父记录、资格、统计、动作与反馈状态。八个实测目标分别断言无残留；不通过强制提交或改阈值消除拒绝。原 `ProjectOneStatRequest` 的 DEFERRED/APPLIED 合同保留，并用真实公共授权验证延期后恰好应用一次。

收尾发现中断遗漏：修订事务原来只捕获 `Exception`。三个入口改为回滚 `BaseException` 后重新抛出。caller-policy/多轴反馈 × Hybrid/Dirichlet/RLS 六个中断用例验证全状态恢复并能重试；不吞掉中断。隔离副本仅撤回这三处修复后，六例全部检出状态残留，原结果保存在 `E/before_interruption_fix.txt`。

[revision_acceptance](../../tests/test_structure_two_w3_revision_acceptance.py) 包含 24 个路径/位置/权重组合、三条连续/乱序路径、九个统计阶段失败、资格伪造、提交去重失败及原十条阻断检查。[supplement](../../tests/test_structure_two_w3_supplement.py) 的单观察纠正验证动作分布从旧位置 1/新位置 0 变为旧位置 0/新位置 1，旧位置 Hybrid 质量为 0、旧 revision 无活跃账本记录。这比仅返回 CORRECT 或内部重跑等价更强，但不承诺每次纠正都会改变 top-1 行动。

## 3. B：参考独立性与故障检出

[FrozenRevisionOracle](../../tests/structure_two_revision_oracle.py) 在变更前复制观察输入、资格、配置、嵌入和已有操作序列。它使用独立 projector 准备反馈，先得到 caller-policy 的预期操作；成功后校验新增操作数量、父目标、位置、owner 权重、反馈来源和新 ID，再纳入参考日志。预期事件由冻结父输入及已校验操作构造，**不从最终 `_committed_events` 定义预期集合**；最终集合仅作为被检查对象。没有参考则不以当前系统值兜底。

参考拥有独立重放遍历、成员选择及 Hybrid 标量求和，不调用被测重建函数。Dirichlet、RLS、CCRR 复用叶算法的新实例。该独立程度检出谱系、集成和账务错误，不证明感知真值、冻结前独立托管或共享模型本身的科学正确性。冻结资格不是新的外部签名权威。

每个故障用例先验证真实合法纠正通过，再故意注入：遗漏纠正记录、额外提交阻断记录、错误权重、错误位置、重复统计、漏撤回、回滚残留、遗漏操作日志。八类均要求检查器实际抛出断言失败，不是“永远拒绝”的检查器。

原独立 journal 脚本在起点输出“纠正未存活，但检查通过”，保存在 `E/before_journal.json`。修复后的原脚本输出纠正存活且检查通过。脚本本身未修改，错误检出能力由上述八类故障实验补充证明。

## 4. C：非空公共解禁与拒绝条件

`public_grant_prefix()` 不向私有授权字典写记录。它通过公共入口创建稳定前缀，再调用 direct-P5 得到**确实阻断、无授权、未提交**的目标。下一条真实 legacy 观察触发现有 CCRR HABIT_CHANGE，授予该目标资格并提交；断言目标及每个中间阶段均非空。`verified_public_path_evidence.json` 保存授权前后快照及授权来源、决定、源记录和阶段信息。

拒绝/原子性覆盖：无授权时重建不提升；外来反馈不授予本系统资格；重复授权观察以时序错误拒绝且资格不变；撤回授权人使依赖授权失效；授权事务统计写入失败恢复无授权状态；同一真实观察随后可重试成功；合法解禁后的父记录可纠正，旧父不再有效。

本轮“失效授权”指**授权人撤回后失效**。没有擅自新增按天数到期、独立性评分或新权威。原 `blocked_grants` 的 31 天无授权结果仍保留，不能把另一条正例说成关闭了该 adaptive-only 输入的不可达性。

## 5. 实际连接与因果证据

[production_system](../../src/cpswm/system/structure_two_production_system.py) 锚定 core/engine/passer/feedback/planner/executor 的实际对象，检查额外实例的实际声明成员。debt replay 在恢复历史 checkpoint **之前**检查当前装配，避免恢复步骤把被替换对象覆盖掉而掩盖攻击。合法注册 override 使用既有接口状态描述，不假定私有字段。

| 公共路径 | 本轮捕获的真实调用 | 内容与干预依据 | 统计/动作含义 |
|---|---|---|---|
| P0 | PCHMP/CF-BOCPD/CCRR/RGRC 安全维护、propensity weighting | 实际 profiler 输入/输出与对象；原维护故障与 no-change 断言；替换攻击 | 维护与欠账约束，不等同完整推理/长期提交 |
| direct-P5 | ORRER branch、PCHMP consume/infer、CF observe_online、CCRR observe、RGRC commit、CIAV select/execute、OPCEU weight | 内容绑定回执与 profiler；身份概率干预、原算子因果矩阵、非侵入式接口断言 | 正式观察/主动验证路径；声明数不是执行数 |
| debt-replay | P0 维护后实际重放完整路径 | 固定并重用原 CIAV 输入；恢复前身份核验；权重/资格和复现测试 | 欠账实际重放，不能绕过写入门 |
| legacy | branch、consume/infer、observe_online、observe、commit、weight | 实际对象/输入/输出；纠正矩阵和独立存活集合 | 有长期统计更新；未发生 CIAV 执行时不补造回执 |
| 多轴反馈 | feedback ingest、PCHMP infer、共享 engine revise_actor_responsibility、ProjectOne 统计应用及重建 | 历史正文绑定、同 ID 异正文拒绝、反馈重放校验；权重效果与失败/中断恢复 | 新旧贡献替换，真实 owner 权重变化；未声称其余轴完整科学覆盖 |

`E/verified_public_path_evidence.json` 逐调用保存 actual object ID/type、实际输入 repr/hash、返回值 repr/hash，并保存 trace rows 与前后记忆/动作。**repr 快照用于复查实际运行，不是独立可信执行证明，也不是单独的因果证据**。应变/应不变证据来自对应正负测试和原 `operator_causal_matrix`、`operator_coverage_matrix`、维护故障测试；不是每条边每个参数均已干预。

反馈测试插桩改用 `sys.setprofile` 观察真实函数，保留内容哈希和中断断言，不再把实例 monkeypatch 冒充正式调用。25 个路径/成员替换组合覆盖 legacy/direct/P0/debt/反馈 × branch/consume/select/execute/ingest；另覆盖同类外来额外实例。未穷尽所有时序攻击，G7 保持部分完成。

## 6. G6 与完整研究能力的边界

[semantic_identity](../../src/cpswm/system/structure_two_semantic_identity.py) 增加语义记忆摘要，同时返回原执行摘要和源码绑定摘要。仅对已知内部生成的 ledger/snapshot/correction 等身份做保引用的 α-renaming（同构重命名）；外部对象、位置、来源和授权标识继续绑定。先验证原账本完整哈希链，再计算语义对应链，不删原始完整性字段制造稳定。

相同冻结输入（包括 CIAV action ID）在 legacy/direct/debt 两次执行中语义摘要相同、运行摘要不同；权重和引用变动能检出。范围含观察/提交/隔离、资格/修订日志、事件历史、Hybrid/Dirichlet/RLS、阶段候选与行动读出等；不宣称覆盖全部自适应控制器状态、任意对象或所有多轴反馈历史的跨运行等价。

完整 H/R/I/C/Z/r/V 粒子、六修订操作、三条件统计块、隐藏事件、多 actor、open-world unknown、可逆归因和具身反馈闭环继续保留。[remaining_connections.md](data/w3_repair_2026-09-12_r4/design/remaining_connections.md) 逐项区分已选字段/接口、已有开发核、生产缺失接线、科学候选、风险与最小验证。

G5 还有不依赖新科学选择的工程：跨步完整 typed particle state、父/快照/统计引用的事务管理、真实证据到类型接口转换、生产后验与行动/反馈接线。**这些本轮没有全部完成。** 神经完整输出头、条件统计聚合细则、正式重采样/再生选择不能随意采用开发默认值。G9 默认自主策略也没有借 caller-policy 测试冒充完成。

## 7. 回归、起点和原证据保留

各组配套 JSON 记录命令、返回码、耗时和运行前后全部 src/tests 哈希，XML 保留逐项结果。三组分别解释，不合并成“整体验收通过”的总数。

| 对照 | 结果与用途 |
|---|---|
| 审核点原 16 文件 / 252 项 | `baseline_252`：252 通过，不能检出已知纠正丢失 |
| 第一轮修改后同组 | `current_252_iteration1`：16 失败、236 通过，原样保留 |
| 中间修复轮 | `new_matrix_iteration1`、`regression_repairs_iteration1/2` 保留错接、恢复键错误、插桩和恢复前身份检查问题；不作为最终验收 |
| 最终原回归组 | **`verified_252`：252 通过，160.89 秒** |
| 最终新增正负矩阵 | **`verified_new_105`：105 通过，172.59 秒**；含原新增 98 + 动作效果 1 + 中断 6 |
| 最终邻接组 | **`verified_adjacent_82`：82 通过，10.30 秒**；反馈循环、修订动作、ORRER、CCRR、Hybrid durable log |
| 邻接既有失败 | `baseline_adjacent_deferred` 在审核点失败：私有注入隔离样本未产生 APPLIED；`final_adjacent` 在资格门处拒绝；改为真实公共解禁后通过，保留 exactly-once 断言 |
| 新发现的中断漏洞 | `before_interruption_fix`：6 失败、1 通过，隔离副本仅撤回三个异常捕获修复；`interrupted_transaction_check`：7 通过 |
| 静态检查 | `verified_ruff.txt`：通过；`verified_mypy.txt`：3 个生产源文件通过，不替代行为测试 |

原 252 的适配未使用 skip/xfail 或放宽科学阈值：① 将明确断言“反馈 engine 与 core 不同”的旧缺陷断言改为共享实际对象；② 生产方法替换式插桩改为真实调用观察，内容/中断条件保留；③ 共享反馈引擎变更归于 core 状态守卫；④ vacuous 正例改为非空公共授权；⑤ oracle 修正预期构造。真实注册 override 兼容和 checkpoint 恢复错误在生产代码修复。第一轮失败保留以供审查。

## 8. 复核入口和源码绑定

原独立脚本和 current/previous JSON 位于主工作树既有审核目录，已先读、先运行，保留 `before_additional.json`、`before_journal.json`。`independent_original_sha256.json` 冻结原目录全部文件哈希；最终 `bound_verified/manifest.json` 校验原脚本和旧结果未改，记录完整命令、源码前后哈希、HEAD、解释器、tracked patch 和新增源文件副本。最终原样结果为 `bound_verified/w3_additional_probes.json`、`bound_verified/w3_journal_oracle_probe.json`。

可复跑脚本为 `E/run_suite.py`、`E/finalize_evidence.py`，须使用新 label/新输出目录，拒绝覆盖旧结果。`E/r4_evidence.py` 以工作树为参数捕获真实公共路径。没有用新结果替换原审核证据。

本轮交付三个实证问题的有界修复、算子连接和事务保护增量、失败/成功对照及完整剩余工作。G5 生产接线与 G9 默认策略等欠项继续属于统一框架，后续仍须分项补验。
