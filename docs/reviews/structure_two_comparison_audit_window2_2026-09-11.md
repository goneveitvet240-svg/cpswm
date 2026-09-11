# 结构二 P5 三臂比较：评测有效性、公平性与错误归因审计

日期：2026-09-11。共同起点：`09eb4d48e1c11082e90ca18332d04333e6b5b47a`。
独立工作树：`/private/tmp/s2-comparison-audit-window2-20260911`。
分支：`codex/s2-comparison-audit-window2-20260911`。

**证据用途：已经打开的 D0 开发诊断，非新的未见确认。** 使用固定 train 1–20、validation 1001–1020、opened test 12001–12060，每条 32 步。本文不降低 0.02 绝对门槛，不选新种子，不启动 router calibration（路由器校准），不更新历史工件、全局 manifest（清单）、工程 checkpoint（检查点）或生产算子。完整七算子框架及隐藏事件、多人物、开放世界、可逆归因、具身反馈范围保留。功能执行与研究创新、调用次数与任务贡献分别判断。

## 1. 结论与证据边界

**本批 P5 对 AMG 的 0.008854 差额不能归因为长期记忆增益：17 个净胜步全部发生在 P5 的 owner-habit 后验仍均匀、AMG 尚无 owner 估计而选默认位置的冷启动状态。** 独立重放 AMG 并仅在 `amg_owner_location is None` 时将其离散默认位置改为共同均匀先验，固定观测/支持/decoder 后，53 个冷启动步的 AMG 错误从 53 变为 36，与 P5 完全一致；全批 17 步差额归零。此反事实仅为开发诊断。

| 方法 | PUT_BACK 错误/1920 | 错误率 | SEARCH 错误/1920 | 错误率 |
|---|---:|---:|---:|---:|
| P5 | 85 | 0.044271 | 154 | 0.080208 |
| AMG | 102 | 0.053125 | 154 | 0.080208 |
| learned two-stage | 533 | 0.277604 | 154 | 0.080208 |

180 个 episode×arm 的错误计数均与历史工件一致；180 条历史 SEARCH top-1/PUT_BACK 动作链也全部一致。原 P5–AMG 改善 0.008854，95% episode bootstrap CI [0.002083, 0.017708]，低于 0.02；`p5_action_signal_detected=false` 保持。相对改善 16.67% 并不能弥补绝对门槛失败。

- SEARCH 三臂 current 后验 **1920/1920 逐步相等**。1276 个已检测步全部 SEARCH 正确，154 个错误全部在 644 个无检测步。相同 detected-location copy/carry 规则使该任务无法评价方法 SEARCH 推断差异。
- P5 赢/输 AMG/共同错误/共同正确分别 **17/0/85/1818 步**。按 episode 总误差比较：6 胜、0 负、54 平。首次检测前 40 步占 16 个胜步；另 1 胜步是只观察到未知人物、尚无 owner 估计的日步。
- P5 **1920/1920 步长期 `_committed_events` 都是 0**。1276 个正观测闭环全部是 `same_location_fast_verification`；644 个负观测明确无新转移。完整 P5 PUT_BACK 动作与 fast-only 读出 **1920/1920 相同**；当前结果不能证明长期提交或所有算子的边际贡献。
- 1040/1920 步的支持集中存在尚未在前缀出现的位置。原 evaluator 提前取真值、本工具先提交后取真值，仍得到相同历史动作/误差；没有观察到当前三臂显式使用真值。


评测有效性存在已证实的问题，但这不意味着三臂每一项比较都无效，也不意味着 learned 对照较弱本身证明不公平。此次完成的是当前固定数据和执行路径的比较审计；不是对整个生产系统、所有状态机或独立托管的穷尽安全审计。

## 2. 输入、状态、后验、动作、真值和评分链路

现有实现位置：

- `src/cpswm/system/evaluation_operations/structure_two_p5_three_arm_death_test.py`：`_packet_for_step`、`_transition`、三个 `*LocationAdapter`、`_feature_row`、`_validation_selection`、`_decode_and_score`。
- `structure_two_p5_readout_posthoc_diagnostic.py`：修复后的 P5 读出配置、`_evaluate_posthoc_episode`；当前 opened D0 runner 调用此实现。
- `structure_two_p5_three_arm_contract.py`：`TypedLocationPosterior.seal/decode`。
- `structure_two_action_utility_construct_gate.py`：`decode_task_separated_actions`、`_rank`。
- `project_two_action_benchmark.py`：`_AMGOpenWorldMethod`、`_locations`、`_argmax`。
- `project_two_dataset_adapters.py`：`D0SyntheticOracleReplayAdapter._convert`；`structure_two_action_death_test.py`：生成器。

| 环节 | P5 | learned two-stage（学习式两阶段） | AMG |
|---|---|---|---|
| 方法可访问对象 | 整条 visible episode、当前 step、公共 packet；不传 evaluator truth | 同左 | 同左 |
| 正观测更新 | `_transition` 提取人物、机制、有序角色证据；完整 P5 执行及 trace 校验 | 12 维特征→固定哈希投影→p(C) p(E\|C)→9 格条件位置匹配头→累计 habit counts | 人物 posterior/reference prior 转证据比；机制/角色输入 AMG；唯一 owner MAP 才更新 owner location |
| 负观测更新 | CIAV/OPCEU 负闭环；转移算子显式无新转移；当前位置保持 | joint 重算，habit counts 和 current 保持 | `observe` 早退，current/owner location 保持；feedback 继承 no-op |
| SEARCH 后验 | `_current`：检测后 one-hot（点质量），否则 carry forward（沿用）；不读 P5 原生物体位置推断 | `current`：同一检测点质量；cause/event joint 不连接此头 | `current`：同一检测点质量；原生 `prediction.search_order` 被丢弃 |
| PUT_BACK 后验 | `system.action_location_distribution(current_snapshot)`，fast 0.7 / surviving 0.2 / regime 0.1 | `normalize(habit_counts)`，每个正观测增量为 joint 与 theta 的内积 | 原生 `prediction.put_back` 被包装成点质量 |
| 公共解码 | 三臂均传各自 typed posterior；SEARCH 与 PUT_BACK 分别排序；同分按位置 UUID 字符串 | 同左 | 同左；但包装前已执行原生离散选择 |
| 评分 | SEARCH top-1 对 true_location；PUT_BACK 对 true_owner_habit_location；搜索顺序另计 normalized regret | 同左 | 同左 |

**SEARCH 平局的充分条件已满足。** 三臂相同位置支持、相同初始均匀 current、相同检测位置更新、相同负观测沿用，可按 step 归纳证明 current 分布逐步相等。公用解码器只是忠实读取被覆盖后的分布。不能称 P5 和 learned 已各自产生原生 SEARCH 后验而后来被丢弃：当前 adapter 根本没有暴露这类头；AMG 则确有原生排序，在包装层丢弃，连剩余位置排序也被公共 UUID 排序替代。

**可执行反例：** `sensitivity()` 保持真实可见 step、位置支持和 decoder 不变，给每一臂分别构造支持内两个合法点质量 SEARCH 后验。SEARCH 首选改变而 PUT_BACK 不变。`test_amg_native_search_order_is_discarded_by_adapter` 改变原生合法排序，原协议 SEARCH 不变；以同一 decoder 读取从该排序确定性映射出的概率后动作才改变。后者是开发用 rank-to-mass（排序转概率）读出，不是校准后验或替代原协议。

**真值边界：** 原 `_evaluate_posthoc_episode` 在循环前获取完整 truth envelope，循环内在 predict/decode 之前取当前 truth；`_decode_and_score` 接受 truth 后才调用 decode。因此字面上的“动作提交后释放”没有被调用顺序强制实现。没有发现当前三臂函数直接读取 evaluator truth；也不能把 `Literal[False]` 声明当成访问隔离证明。本工具 `CommitBarrier` 拒绝不齐全、重复、错 step、重复 release，并且先解码三臂和替代读出，再调用 `dataset.truth_for`。这只是本进程的顺序约束，没有独立进程/权限隔离或历史真实性证明。

**位置支持的时间问题：** D0 visible case 原本有位置目录，但 `_convert` 没填 `episode.known_location_ids`。因此 `_locations` 从整条未来轨迹的 source/attempted/destination 收集支持。三臂拿到的信息相同，但不是严格的在线前缀信息。该目录同时依赖观察覆盖和出现顺序。全 episode 的长度也被 P5 context 和 learned 相对时间特征使用；固定阶段日期使时间特征能在同一模板内预测阶段，不能据此认定泛化到新时间表。

## 3. PUT_BACK 逐步及逐 episode 归因

机器结果：[`audit.json`](data/structure_two_comparison_audit_window2_2026-09-11/audit.json)、[`attribution.json`](data/structure_two_comparison_audit_window2_2026-09-11/attribution.json)、压缩逐步轨迹 [`steps.jsonl.gz`](data/structure_two_comparison_audit_window2_2026-09-11/steps.jsonl.gz)。

| 分组 | 步数 | episode 数 | P5 赢 | P5 输 | 共同错误 | 共同正确 | learned 错误 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 全部 | 1920 | 60 | 17 | 0 | 85 | 1818 | 533 |
| 正观测 | 1276 | 60 | 1 | 0 | 9 | 1266 | 323 |
| 负观测 | 644 | 60 | 16 | 0 | 76 | 552 | 210 |
| 人物证据清晰 | 1276 | 60 | 1 | 0 | 9 | 1266 | 323 |
| 人物证据缺失 | 644 | 60 | 16 | 0 | 76 | 552 | 210 |
| 真 owner | 1380 | 60 | 11 | 0 | 69 | 1300 | 516 |
| 真其他已知人物 | 480 | 60 | 0 | 0 | 0 | 480 | 0 |
| 真未知人物 | 60 | 60 | 6 | 0 | 16 | 38 | 17 |
| 真交接机制 | 232 | 60 | 0 | 0 | 0 | 232 | 0 |
| 有序角色证据存在 | 133 | 53 | 0 | 0 | 0 | 133 | 0 |
| 初始阶段 | 1020 | 60 | 17 | 0 | 36 | 967 | 37 |
| 改变阶段 | 540 | 60 | 0 | 0 | 20 | 520 | 348 |
| 回归阶段 | 360 | 60 | 0 | 0 | 29 | 331 | 148 |
| 改变当步 | 60 | 60 | 0 | 0 | 16 | 44 | 60 |
| 回归当步 | 60 | 60 | 0 | 0 | 23 | 37 | 45 |
| 历史 0–7 步 | 480 | 60 | 17 | 0 | 36 | 427 | 37 |
| 历史 8–15 步 | 480 | 60 | 0 | 0 | 0 | 480 | 0 |
| 历史 16–23 步 | 480 | 60 | 0 | 0 | 20 | 460 | 325 |
| 历史 24–31 步 | 480 | 60 | 0 | 0 | 29 | 451 | 171 |
| 首次检测前 | 40 | 22 | 16 | 0 | 24 | 0 | 24 |
| 首次检测后负观测 | 604 | 60 | 0 | 0 | 52 | 552 | 186 |
| P5 habit 后验均匀 | 53 | 22 | 17 | 0 | 36 | 0 | 37 |
| P5 habit 后验非均匀 | 1867 | 60 | 0 | 0 | 49 | 1818 | 496 |

人物歧义差值≤0.2：0 步、0 episode，**未测**；真实迟到反证挑战：0，**未测**。按 episode “是否出现任何错误”另分为 P5 全对/AMG 有错 2、反向 0、两者有错 41、两者全对 17；这与按总错误比较的 6/0/54 定义不同。

六条 P5 总误差较少的 episode（完整 60 条见机器结果）：

| episode ID | P5 错误 | AMG 错误 | learned 错误 | P5 胜步数 |
|---|---:|---:|---:|---:|
| `e3626958-aed0-559e-8cf4-82de8b04090b` | 2 | 4 | 7 | 2 |
| `00b03913-8e45-2fc8-4295-5bd75d2d2bf2` | 1 | 3 | 11 | 2 |
| `a47c77d7-12db-eefa-0ce3-5fa12a2df836` | 1 | 3 | 9 | 2 |
| `ef529fd4-44da-d551-c202-831c39243b5d` | 0 | 3 | 10 | 3 |
| `aa84f8a1-8763-9c0d-8a55-8186c740ad2a` | 1 | 7 | 7 | 6 |
| `19ea0b29-0b9b-8c35-d60e-eb5b580ecce8` | 0 | 2 | 7 | 2 |

**错误归因而非能力外推：** 17 胜步全部在初始 0–7 步、P5 均匀 owner-habit 后验的 53 个冷启动步内。AMG counts 初始全空，`_argmax` 选支持首项；D0 `_locations` 首项来自 before/source 的夜间 decoy（干扰位置），而真 owner habit 不在该位置。P5 的均匀后验由公共 decoder 选择 UUID 字符串最小项，部分 episode 恰好对应 owner habit。不是 P5 从负观测恢复了正确长期习惯。`00b03913-8e45-2fc8-4295-5bd75d2d2bf2` 的 step 1 是唯一正观测胜步：未知人物质量 0.8；P5 habit 仍均匀、AMG 仍无 owner 估计。

共同均匀先验干预的触发条件来自**独立 AMG 重放状态**，没有按 P5 是否获胜或真值挑选。53 步选择均与 P5 相同（AMG 错误 53→36）；限定首次检测前的 40 步则是 40→24。后验非均匀的其余 1867 步 P5/AMG 均错 49 步、无任何胜负分歧。P5 与 AMG 共同错误中，冷启动占 36，之后阶段改变/回归相关错误占 49；首次检测后的 604 个负观测步两者完全打平（各错 52）。

**长期提交的具体原因：** `StructureTwoProductionSystem._execute_adaptive_plan` 的主处理调用 `core._process_transition(..., force_long_term_write_blocked=True)`（生产源约 1133–1137 行）。当前 `_ciav_input` 将预期检测位置设为 packet 的已检测位置，realizer 只回传同一 packet 的 outcome，故所有正步都走约 1196 行的 same-location 分支，只调用 `apply_fast_action_verification`；约 1240 行的不同位置完整反馈 `_process_transition` 不发生。`prototype_spine.py` 约 2395、2430 行将 force-blocked 事件保留在观察/快速状态而不 `_commit_event`。这解释了已观测事件增长、长期提交始终为 0 的组合，不能归因成“数据太短所以偶然没学到”。

| 同状态的开发读出 | PUT_BACK 错误 | 与完整 P5 动作关系 |
|---|---:|---|
| fast-only | 85/1920 = 0.044271 | 1920 步完全相同 |
| surviving-only | 1409/1920 = 0.733854 | 无长期提交，不能据此评价该算法有数据时的能力 |
| regime-only | 1409/1920 = 0.733854 | 同上 |
| pooled-only | 1409/1920 = 0.733854 | 同上 |

AMG 原生排序转概率的额外 SEARCH 读出：166/1920 = 0.086458，normalized regret 0.058333；原协议分别为 0.080208、0.055382。原生完整排序与 adapter 排序在 1634 步不同。这是“读出变化可被评测看到”的证据，结果并不刻意只展示有利于 P5 或 AMG 的变化。


`steps.jsonl.gz` 每行保留 episode/step ID、源 step 哈希、packet/schedule 哈希、各臂状态前后哈希、当前位置和 owner-habit 后验、完整搜索排序、放回动作、闭环类别、评分，以及原生 AMG 排序、learned joint/counts、P5 四种纯读出与提交数量。真值和派生标签只用于动作提交后的分组。生成器可按固定配置重建原始轨迹，并通过行内 step 哈希核验；不依赖人为补标签。

分组定义与限制：

- 人物歧义用合法可见 actor posterior 的前两项概率差 `<=0.2` 定义，缺失单列。这是预先声明的描述性分箱，不是因果诊断阈值或调参结果。当前生成器正观测人物证据主要是 0.8/0.15/0.05 或未知人物 0.8/0.1/0.1；不能将 missing 误称强歧义。
- phase（阶段）和 recurrence（回归）依据评分侧 owner-habit 真值的变化/重访定义；since-change（距阶段起点步数，初始阶段从 step 0 起计）分 0–2 和 3+。所有 episode 的阶段变化固定在 step 17 和 26；不同 seed 不代表新时间表。历史长度按已处理步数 0–7、8–15、16–23、24–31 分箱，不能外推长期生命周期。
- hidden-move proxy（隐藏移动代理）仅指无检测的日步：生成器每天都生成一次搬动。机制标签区分 direct/handoff/unknown；这不等于具有可验证中间状态的隐藏事件链。当前 `event_chain_truth` 所有日步写固定 pick_up/carry/place，无法评估真实交接链的重建质量。
- 真未知人物由 evaluator `true_actor == unknown_actor` 分组；与“可见支持含 unknown_actor”严格分开。60 个真未知人物事件全部固定在 step 1，且与 unknown mechanism 同时出现；不能分离未知人物、未知机制与冷启动效应。
- 原轨迹没有针对早期事件迟到、可追溯的反证干预，迟到反证恢复能力标为**未测**。当天的 CIAV 后验确认不能替代迟到反证测试。
- execution_feedback 为脚本化成功概率（按 day%3 取值），没有 post-action destination 检测；当前 P5 `_transition` 不接入这些 replay execution_feedback，AMG feedback 为 no-op，learned 特征也不使用。工具不把这些标签当成真实机器人执行净收益。
- 替代 P5 readout（读出）只从同一状态额外读取 fast、surviving、regime、pooled，不改变写入和后续动作。读出一致不证明删除算子仍等价；读取长期提交薄弱也不授权移除长期机制。

所有子组是相关性归因，没有多重比较筛选“显著”子组；没有独立 subgroup 优越性声明。每组同时给步数及 episode 数，重叠分组不相加，不能把 1920 步视为 1920 个独立样本。

## 4. learned two-stage 与 AMG 核查

1. **状态跨步保留已证实。** 每条 episode 只构建一次 adapter。learned 保留 habit_counts、last_observed、seen_counts、last_joint；AMG 保留 last 和 amg_owner_location；P5 保留完整生产系统。不存在每 step 重建 learned 状态的当前缺陷。
2. **学习位置头接线没有发现轴序错误。** `predict_joint` 的下标是 `cause*3+event`，theta 同形 3×3；更新为 `sum joint[c,e]*theta[c,e]`；counts 正确归一化后送 PUT_BACK。单元测试复算增量并确认 decoder 对 counts 的改变敏感。SEARCH 不读取此头是当前协议的结构问题。
3. **输入权限相同不等于有效特征相同。** learned 仅有观察标记、visibility、confidence、owner/non-owner/unknown 人物质量、三类机制质量、位置变化标记、当前位置历史比例、相对步数。缺少 ordered roles、reference actor prior、人物分别身份和源位置关系、迟到证据 lineage（沿袭关系）、原始负观测机会模型；测试证实去掉角色证据特征逐项不变。P5/AMG 都有使用角色证据的代码。这是表示能力差异，不是模型直接多拿了 evaluator 标签。 另一个编码边界是：人物证据缺失时 `_feature_row` 给 owner/other-known/unknown 的三个质量为 `(0,1,0)`，而 unified evidence 在同情形把 unknown 设为 1；learned 仍有 observed=0 标志可区分缺失，因此这里记录为表示语义差异，不直接判定模型必然受损。
4. **训练与验证的执行隔离：** learned 特征投影均值/方差、logit 权重、theta 的 successes/totals 仅由 train 640 步拟合；选择器对 validation 640 步评分，20/20/60 episode ID 不交。测试拦截 truth_for，确认 `_learned_training_material` 只请求 train。选择器没有访问 test ID。它们仍来自同一个固定合成模板，split 标识隔离不等于外部分布独立或托管独立。
5. **模型容量和目标限制：** learned 是固定哈希投影后的多项 logistic heads（逻辑回归头），不是一个端到端可学习长期记忆网络。条件 theta 只学“检测位置等于 owner habit 的概率”，然后做无遗忘的非负计数累加；不具备 AMG 的最近唯一 owner 直接覆盖行为，阶段改变后旧质量会阻碍切换。可据源代码判定适应机制限制；不能仅凭这批误差声称增加宽度一定能解决、或者分类器优化失败是唯一原因。
6. **调参适用性：** learned 12 次拟合×2 个 smoothing 共 24 个 validation 候选，AMG 3 个参数候选，均最小化 validation PUT_BACK error。各自独立调参已实施；没有给 SEARCH 单独目标，但当前 SEARCH 对这些参数不敏感，重调也不能恢复区分力。P5 既有 v0.6 三个读出候选按 cumulative_action_regret（累计动作遗憾）选择，目标/预算与此处对照不同，历史人工开发投入也未可比。没有依据将“信息匹配”写成“等算力”或“训练预算完全公平”。
7. **AMG 边界：** 这是仓库内 Damen–Hogg 2012 的 matched-evidence adaptation（匹配证据改编），不是对原论文所有输入设置的完整复现。当前 owner MAP 唯一性、reference-prior 修正已在代码中，不应仅因它无神经网络训练就判不公平。其 `observe` 捕获 `ValueError` 后早退是潜在静默路径，本文没对所有异常空间穷举，不能宣布全面排除 AMG 实现缺陷。

本次固定 validation 选择：learned `base_width=8, learning_rate=0.1, l2=0, smoothing=0.25`，AMG `parameter=0.2`。learned validation 最佳 PUT_BACK error 为 0.246875；width 16/32 的各自最佳均为 0.265625，因此不能说本次搜索简单地遗漏了已登记的大宽度。AMG 三个参数 validation error 都是 0.0453125，按既定较小参数打平规则选 0.2。

selected learned 有 64 个 active logit 参数、12 个 raw features、投影 width 8，另有 9 个 theta 条件格及投影归一化统计和跨步计数。单个所选模型申报的 head-only training multiply-add 为 2,457,600、每次 inference 为 64；这不是整个 adapter 的实测算力。

训练正观测 theta 格（cause 行、event 列；顺序见代码 CAUSE_GROUPS/EVENT_GROUPS）：totals `[[37,0,60],[0,29,0],[0,0,281]]`，successes `[[0,0,0],[0,29,0],[0,0,281]]`。5/9 格没有正观测训练样本，只依赖平滑。opened test 的 joint top-1 confusion 中，120 个真 regime-change 类全部预测为 other/other；这提示分类/表示诊断问题，但 soft joint 仍用于更新，不能把硬分类误差直接等同动作错误。learned 的 533 个动作错误中，改变阶段 348、回归阶段 148，合计 496（93.06%）；和不遗忘计数头的阶段适应限制一致，尚不是独立证明的单一因果归因。


## 5. 公平性与成本表

| 维度 | 已核查事实 | 审计判断/缺口 |
|---|---|---|
| 信息访问 | 同 visible episode/step、相同 packet、位置支持和 exogenous schedule；receipt 匹配逐步校验 | 可访问输入匹配；feature 使用不匹配；未来支持暴露是共同问题 |
| 训练数据 | learned：train-only supervised cause/event 与位置 theta；AMG 无本次监督拟合；P5 既有规则与读出 | 数据来源可追踪，训练机制与容量不同；不声称等训练量 |
| 调参预算 | learned 24 候选、AMG 3，P5 既有 3 个 v0.6 读出候选与更广人工开发 | 对照各自独立调参；不存在统一预算，历史投入未完整计量 |
| 模型容量 | learned 小型固定投影+logits+9格 theta+累积计数；AMG 离散逻辑状态；P5 七算子完整状态 | 不同归纳偏置；不能以参数数直接匹配符号状态复杂度 |
| 推理计算 | 独立 wall/process CPU 纳秒计时，3 次重复×固定前 2 条 episode×32 步，各臂 192 次；轮换臂顺序 | 范围含 consume、状态哈希、trace 验证、posterior、公共 decode；不含真值和评分 |
| 观测成本 | 每步同一 MICRO_VERIFY，motion/time/interruption/privacy/safety 均为 0 | 仅信息/动作诊断，绝非真实零成本观测或净效用；没有真实能耗/机器人运动测量 |
| 动作时机 | 先释放当前检测后 SEARCH/PUT_BACK；D0 环境不因这些提交动作推进 | SEARCH 部分近似“已看到后再寻找”；没有 action-contingent（依动作变化）闭环效果 |
| 真值访问 | 当前臂无 truth 参数；原 evaluator 提前读取；本诊断严格先全部 commit 再 release | 排除了当前显式参数注入，未建立进程权限/独立托管隔离 |

[`timing.json`](data/structure_two_comparison_audit_window2_2026-09-11/timing.json) 包含 576 条原始纳秒计时记录。硬件：Apple M5 / 24 GiB / 10 逻辑核心，macOS 26.4 arm64，Python 3.13.5、NumPy 2.5.2。下表单位毫秒/step：

| 方法 | 样本数 | wall 均值 | wall 中位数 | wall P95 | process CPU 均值 |
|---|---:|---:|---:|---:|---:|
| P5 | 192 | 214.929 | 259.115 | 387.158 | 209.056 |
| learned | 192 | 2.411 | 2.404 | 3.100 | 2.355 |
| AMG | 192 | 2.933 | 3.204 | 4.116 | 2.860 |

P5 在该测量范围的平均 wall 时间约为 AMG 的 73.27 倍、learned 的 89.14 倍，明确不等算力。训练材料构建及完整 validation 选择共用 77.694 秒（单次；非每个模型的独立训练耗时）。


计时包含验证/哈希开销，P5 还实际验证七算子 trace，不能把结果包装成纯推理内核 benchmark（基准测试）。训练+验证墙钟只测一次，明确与重复的在线成本分开。硬件默认沙箱无法读取 CPU 型号时会写 unavailable；同机只读升级查询得到 Apple M5、24 GiB、10 个逻辑核心，详见 `hardware_supplement.json`。没有测 GPU、功耗、峰值内存或观测物理成本；也没有隔离其他系统进程负载。延迟数字只支持此机此测量范围的开发比较，不支持统一效用结论。

## 6. 分类处置与精确补丁建议

### 已证实缺陷/测量问题

- SEARCH adapter 的公共 copy/carry 规则使方法区分力消失，AMG 原生排序被丢弃。公共 decoder 本身的敏感性已通过可执行反例验证。
- 原 evaluator 在 typed action decode 前取 truth，协议声明未由顺序边界兑现。未发现当前方法因此使用真值的证据，不能将边界缺陷夸大成已发生标签作弊。
- `_convert` 遗漏已知位置目录，`_locations` 读未来 episode，支持集不满足在线前缀约束。
- 初始无观测时不同 adapter 对“无知识”的编码不同；定量影响见上文开发反事实，不回写原分数。
- 历史 post-hoc 来源哈希断裂：原测试 `test_posthoc_config_discloses_opened_test_and_forbids_positive_receipt` 报 `retained v0.1 result file hash drifted`。共同起点配置要求 `1a617567a224d11eca20f589a9aa84ddc2195494263bc58f2c4fb21030643c04`，其指向 `benchmarks/structure_two/structure_two_p5_three_arm_death_test_v0_1.json` 的实际 SHA-256 是 `a25b8619fd0270b863bfd0aa8e91767a0cd6274d164f3529424175fe7218bfcf`。`git show 09eb4d4:<path>` 与工作树两文件分别逐字节相等，因此是起点问题。

### 已排除的具体假设

- “公共 decoder 忽略不同的合法位置后验”：反例排除。
- “PUT_BACK 三臂也被一个公共 detected-location 规则全部覆盖”：代码及逐步独立 posterior 排除。
- “learned 每一步被重置”“cause/event 轴接错”“counts 没送进 PUT_BACK”：状态、复算更新及动作敏感性测试排除当前路径。
- “本次 learned theta/投影用 test truth 拟合”：train-only 访问拦截与选择器调用链排除；不外推历史手工开发完全没看过数据。
- “本窗口新增源文件造成历史哈希测试失败”：共同起点文件字节对比排除。

### 尚未建立的能力证据

长期持久记忆（超过 32 步及跨 session）、有歧义的人物/角色挑战、真实迟到反证、未知人物多样性泛化、真实可变长度隐藏事件链、负观测的地点排除推断、机器人行动改变未来状态、真实物理成本与净效用、每一个完整算子的边际贡献、外部分布泛化：均未建立。不能从“trace 调用了七算子”推断已测完这些能力。

### 修复建议（未应用）

1. `data/.../truth_barrier_suggestion.patch` 是可 `git apply --check` 的建议 diff：将 `_decode_and_score` 的后半评分提取为 `_score_committed_readout`，在 `_evaluate_posthoc_episode` 中先解码所有三臂，再取 truth 和评分。保留原 helper 包装以免无意改动其他历史 runner。下一版还应让 validation/其他 runner 同样切分，并由 evaluator process（评测进程）托管 truth，验证后才迁移；不要重写旧工件的时间声明。
2. 下一版 D0 adapter 在构造 `ProjectTwoReplayEpisode` 时显式增加 `known_location_ids=visible.locations`，并让新版本在线 evaluator 在目录缺失时拒绝 `_locations` 的全轨迹回退。该改动会改变 visible hash、支持顺序、初始动作和可能的分数，必须用新 dataset/protocol 版本；不得把本批历史重算结果改名为原协议确认。若用户选择逐步发现的位置目录，则应采用前缀扩展且明确 unknown-location（未知位置）质量的处理，这与预知地图是两个需用户选择的任务假设。
3. **同位置确认后的长期提交路径：** 不能简单将 `force_long_term_write_blocked=True` 改为 False，这会跳过先验证再提交的安全意图。建议增加同位置验证后的显式 consolidation（巩固）阶段：对已验证 revision 在同一个事务内重新检查 PCHMP/CCRR/RGRC、授权与证据绑定，允许则恰好一次写入长期状态，否则保留带原因的 quarantine（隔离）。分别测试可提交正例、证据不足拒绝、重复确认不重复写入、迟到反证撤销、跨 episode 状态和不同位置反馈一致性。当前报告仅提出精确调用点及必要语义；不代替用户冻结门控策略、不修改生产源。
4. 下一版 SEARCH 先明确预测时刻，再接各方法真正的 current-location head。AMG 排序转概率只作为开发可执行示例，不能擅自定为生产概率模型。P5 的事件/位置推断与 learned 的位置头需要各自有可学习/可推理的 SEARCH 接口，均接受相同证据和支持；保留“不改变后验就不改变动作”的控制与有效反例。
5. 对历史哈希断裂，先以 Git 历史追溯配置所指原工件的确切字节。找到则新增不可变归档路径和版本化更正说明；找不到则标记 unavailable。不能直接把配置期望哈希换成当前值并声称原绑定通过。

## 7. 下一版评测协议草案：用户决策项，不冻结

最小必要修改应同时恢复测量作用和保留普通场景/强基线，不只挑对 P5 有利的病例：

| 需要检验的目标 | 最小修改草案 | 保留的对照/负控制 | 用户需决定的项目 |
|---|---|---|---|
| SEARCH 方法区分力 | 在揭示用于评分的位置观测前提交当前位置 posterior 和 search plan；事先声明地图目录或前缀支持；正、负、缺失观测采用共同调度 | 保留已检测的简单场景、last-seen、原生 AMG 排序、learned 与 P5；理想检测只作为天花板 | 搜索目标时刻、top-1/预算内成功/搜索代价的主次、观测预算和目标分布 |
| 公平冷启动 | 为无历史状态声明共同知识、支持与 ignorance（无知识）表达；同时报告 burn-in（预热）前后，但不删除困难初始步 | 普通冷启动作为正式组成部分；共同 uniform 控制、方法原生先验另列 | 是否预先知道 owner habit、位置先验从何而来、tie 的对称策略 |
| 长期记忆 | 在普通稳定场景外加入更长轨迹、短暂扰动/持续变化/回归，以及离线保存和跨 session 恢复 | 独立调参的 AMG、recent-owner、带验证选定遗忘率的 learned；保留无需复杂记忆的场景 | 时长、阶段占比、迁移次数、数据总量与每臂预算 |
| 完整算子作用 | 在统一七算子系统上安排可追溯隐藏链、多人物角色歧义、未知人物/机制、地点条件负观测、迟到可撤销反证；对应 operator ablation（算子消融）只作实验臂 | 普通直接搬动、清晰证据、无反证的零效应控制；信息/行动机会相同 | 事件分布、干预频率、合法证据来源和评分目标 |
| 真实闭环与成本 | 每臂先提交动作；环境随后执行并产生可见反馈和评分侧真值；观测/计算/动作分别计量 | 固定公共 schedule 和等预算自适应 schedule 分开比较，保留强固定策略 | 采用何种模拟器/外部轨迹、cost weights（成本权重）、预算上限、是否汇总效用 |
| 学习对照可靠性 | 让 learned 接受有序角色、reference prior、必要的时间/历史表示，并分别选择当前位置与 owner-habit 目标；验证集报告拟合诊断和容量前沿 | 保留当前小模型作为可解释基线，并增加独立调参的强状态学习对照 | 新训练目标、模型族、训练量、调参和推理预算；不由本窗口替用户选定 |

沿用当前 0.02 门槛用于当前登记的信号门，不因为上述诊断而降低。新版本目标/分布/预算与主指标需要用户决定并在新数据打开前登记；本文不创建或打开新测试集，不启动路由器校准。若新协议改变单位、任务或效用，须独立讨论其阈值，不能反向用于当前数据“转通过”。

## 8. 复现、验证与整合

从自己的工作树执行，使用现有环境但强制 `PYTHONPATH=src`，因此导入本工作树源代码，不写原工作区：

```sh
cd /private/tmp/s2-comparison-audit-window2-20260911
export PYTHONPATH=src
export AUDIT_PY=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python
export AUDIT_BUNDLE=docs/reviews/data/structure_two_comparison_audit_window2_2026-09-11
# 本分支已经附带结果；新运行须选择新的输出目录，否则入口拒绝覆盖。
"$AUDIT_PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output /private/tmp/s2-comparison-audit-new-run
"$AUDIT_PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$AUDIT_BUNDLE" --verify --timing-repeats 1 --timing-episodes 1
"$AUDIT_PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle "$AUDIT_BUNDLE" --verify
"$AUDIT_PY" -m pytest tests/test_structure_two_comparison_audit.py
```

主入口完整重做既有训练/验证选择及固定 60 条 opened D0 轨迹；默认为 3 次×2 条固定 episode 的成本复测。归因入口只重建同一公开配置、读取已打开的逐步结果并执行开发反事实；不重选模型。默认对文件采用拒绝覆盖；主入口 `--verify` 复算来源、选择、逐步语义哈希、汇总和历史分数对齐，归因 `--verify` 逐字 JSON 语义比较。

`audit.json` 绑定所有 `src/**/*.py` 及当前数据/方法配置和历史对照文件。整合其他源修改后 verify 会有意报 source binding 不同，需要新输出目录重跑，不能改旧哈希。运行局部 provenance 中的随机状态/动作身份与计时不是可重复性的判断依据：逐步 semantic hash 明确排除每臂 `provenance` 字段，但保留后验、动作、错误、内部可读状态和分组。它证明可重复计算，不证明历史发生时间或独立托管。

验证完成：

- 主诊断：60 episode / 1920 step，历史分数差异 0；归因核对 180/180 条历史动作链一致。
- 第二次完整 `--verify`：重做 train/validation 选择及全部 60 条轨迹，全部报告字段与逐步语义相等。为了只核验语义，第二次计时使用 1 次×1 条 episode，不与首个正式诊断的 3 次×2 条计时混合。
- 逐步语义 SHA-256：`d32b9d7bd2ff4963d8a71939fe752b260806e8775b692d602ac4588205f70c76`。
- 归因 `--verify`：重新生成同一 D0、独立重放 AMG 冷启动状态、复算开发读出并全量比较，输出 `attribution verified`。
- 新增测试：**20 passed in 28.79s**。覆盖合法后验动作敏感性、原生 AMG 搜索头丢弃、learned 状态和条件头、角色特征缺失、未来支持、train-only truth、提交屏障正例/负例/重复/错 step、无长期提交复现、硬件不可用降级、工件篡改与伪造 positive gate（通过声明）拒绝。
- 原有相邻回归：**15 passed / 1 failed**，失败为本报告第 6 节的既有 post-hoc 文件哈希断裂；未修改历史工件消除该失败。机器证据在 `baseline_binding_issue.json`，包含两个文件与共同起点字节相等的检查。
- 新增四个 Python 文件 `ruff check`、`ruff format --check` 通过；新增源模块 `mypy --follow-imports=silent` 通过；`git diff --check` 通过；建议 truth barrier patch 的 `git apply --check` 通过，未应用。
- 初次完整计算在采样结束后的硬件 sysctl 查询因沙箱权限失败而未保存。修复的是诊断容错；之后固定同一配置完成一轮保存和一轮完整验证，没有改变种子或选择规则。
- 原工作区 `git status --short` 为空；本分支仅新增诊断、测试、报告及其数据，未修改原有跟踪文件。

代码/测试提交：`6f9ca3669cef8476c356fda0d2d07f74079671c7`。
报告和机器结果为紧随其后的独立提交，其哈希可由 `git log -1 --format=%H -- docs/reviews/structure_two_comparison_audit_window2_2026-09-11.md` 取得，并在交付消息列出。

建议整合顺序：先诊断模块、入口和测试；再将本次数据及报告作为只读评审记录整合；用户审阅协议选择后，另开版本实施生产/evaluator 修复。建议 patch 仅供审阅，不在本分支应用。不要先 cherry-pick 建议补丁再用本报告声称原版本通过，也不要把本次开发结果写进全局科学信号或工程完成状态。
