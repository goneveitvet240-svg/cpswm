# B9：W2 公平性与新统一验收准备独立审核

日期：2026-09-13。结论：**PARTIAL / ACCEPTANCE PREPARED / UNIFIED ACCEPTANCE BLOCKED**。

本轮没有修改科学指标、阈值、先验、预算、模型选择规则、生产实现或 `STATUS_B`。没有生成新比较包，没有打开确认数据，没有运行训练或正式科学实验。

## 1. 冻结对象与实际可审核范围

| 对象 | 完整 SHA | 本轮用途 |
|---|---|---|
| W2 验收准备交付 | `329787241996631a6abb4fcd3b12d2c13a135777` | 本轮指定冻结提交；GitHub 分支 `codex/pc-a-w2-acceptance-prep-20260912` 当前精确指向此 SHA |
| W2 验收工具代码 | `8bdd5b2a7d045865d3a72b83a97d34ef822a3760` | `329787…` 的父提交；31 项见证检查器与 71 项检查器测试 |
| W2 历史保全快照 | `de2c04c3e690dba674850af9c4f7e126dbab910e` | 比较实现、五组旧测试、v5 与交接合同的可定位快照 |
| W2 历史实际运行源码 | `d6112489d0a09f7086286e223741be60051b99a5` | v5 报告登记的实际运行源码；不是本轮重新执行源码 |
| R6 攻击归档审核 | `97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274` | 60,757,458 B 的历史攻击包归档及历史 CLI 记录 |
| 当前共享集成分支 | `bdec3ee21b7db361e390496d97ff2eb30390dc6c` | 2026-09-13 本轮远端复核仍为此 SHA；不是统一冻结源码 |

GitHub 连接器确认仓库可读、W2 分支存在、交付提交存在；交付提交的 Git tree 为 `ab3ea1d707df80934ae5348e5dcb066fcaf12203`，未截断，共 1,373 个 blob。提交未签名（GitHub verification reason `unsigned`），因此本报告只使用 Git 对象 SHA 与内容摘要绑定，不把提交签名当作额外信任。

终端 `git clone --no-checkout https://github.com/goneveitvet240-svg/cpswm.git .../cpswm_b9_snapshot` 被执行环境网络策略拒绝，exit 128，约 6.01 s，错误为 `remote: Forbidden. Calls to this URL via the terminal are not allowed.`。这不是仓库权限失败：GitHub 连接器显示本账号对仓库 `pull=true`。因此本目录不是 Git checkout；本轮无法 `git fetch origin --prune`、无法本机重跑 71 项或正式 CLI，也没有 JUnit。所有“31/31”结论均明确是对冻结 Git 对象中**历史见证结构的独立机器解析**，不是本机新鲜重放。

环境：Ubuntu 24.04.3 LTS、Linux 6.18.35、x86_64、Python 3.12.14、Git 2.51.1、uv 0.12.11；pytest 未安装。原交付环境为 PC A/macOS arm64/Python 3.13.5，不能充当 B0/B1 或本 Linux 环境动态复现。

## 2. 31 类历史伪造与合法参考

机器解析 `329787…:docs/reviews/pc_a/w2_acceptance_prep_2026-09-12/archived_mutation_values.json` 得到：

- `records=31`，31 项 `before_sha256 != after_sha256`；每项均保留首个可查看的字段差异，不是只比较整包哈希。
- 30 项语义攻击的 `audit.source_bindings` 与合法参考相同；唯一 `source_binding` 明确归类为来源元数据攻击并实际改变绑定。
- 31 项历史 CLI 行均为 `REJECTED` 且有具体 stage/error；历史批次声明执行 fresh replay。
- 合法参考包的四文件 SHA-256：`audit.json=e1f0ab34774c5f788c498bc67d6e710c78e03154661df9ae2b82959a92cd4d36`、`timing.json=c9131341f553ed59b55a0cf4ad9175fa7daf0e476904bee3c794d81289d65d0e`、`attribution.json=506a20010640eb1934b3b07a6bf4b2ee4082e58c59cdcf353c2a54ebf1b1d63e`、`steps.jsonl.gz=d96b69fc2c65e8c2382568fc5f6efd26b69e9295629f48bae6344e8628bcd76c`。
- 攻击归档 SHA-256 为 `bdfc801b602a5ed55efe2502f3596010f372ab4b4f6e626a64a7f3e52137f17c`。历史报告说明每批都有合法参考 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，攻击按 21+6+4 逐包拒绝；本轮没有重新执行这些包。

逐项证据见 [mutation_matrix.json](mutation_matrix.json)。以下三个边界必须保留：

1. 这证明历史包中指定结论依赖发生非空变化，不证明攻击构造器或 CLI 在未来统一源码仍正确。
2. `corrected_memory=True`、`action_consequence=executed`、`nonempty_commit += 1` 在未来真实能力实现后可能成为 no-op；正式新包必须重新见证实际字段差异。
3. `r1_commits_999`、`source_rebound_state`、`forged_verification_receipt` 是不同威胁机制但共同改变 committed-events 依赖；不能把“31 个名称”误写成 31 个互不相同的科学能力。

检查器自身的正确边界：`mutation_witness` 拒绝 no-op、缺失依赖和语义攻击的 stale source；`check_cli_batch` 要求合法参考通过、攻击逐包拒绝、错误非空、数量/路径无缺失重复，并拒绝将语义攻击仅靠 `SOURCE_BINDING_MISMATCH` 过门。其 71 项历史回归是 31 no-op + 31 非空依赖 + 9 个来源/批次边界检查；本轮未复跑。

## 3. 公平性追溯

本表的“实现”绑定 W2 保全快照 `de2c04…`；“冻结规则”绑定 `329787…` 中可读的协议与报告。具体机器可读条目见 [fairness_traceability.json](fairness_traceability.json)。

| 维度 | 合同/实现追溯 | 当前结论 |
|---|---|---|
| 公共地图与候选支持 | `structure_two_comparison_dynamic.py:699-716` 明示 D0 在无 catalog 时由 `_locations` 扫完整 episode；`structure_two_comparison_audit.py:202,275,316-317` 用全 episode `states[0].locations` 解码，同时逐步记录 `future_support_count` | W2 v5 确有 future-location 暴露，三臂共享但会影响归一化和平局；公平性**未决定**，不是泄漏已获授权 |
| 缺 owner 先验 | `dynamic.py:718-739` 明示 P5 uniform、AMG last-detected fallback；历史对账为 53 个缺-owner 步、17 个 PUT_BACK 差额，共同先验开发对照使 AMG 102→85 | 该 17 步差额适用于 W2 v5/旧 D0 适配版本，不能归因于完整联合记忆，也不能自动外推到 A 新联合组件 |
| 实际消费特征 | `fairness.py:273-340` 的 `ConsumerProbe` 追踪真实 `_feature_row` 返回值；`dynamic.py:742-754` 记录 common packet/visible step，但 actor/role/temporal 特征消费不同 | 信息权限相同不等于特征、容量相同；特征权利与共同/原生消费仍需科研决定 |
| 数据划分与选择 | `audit.py:653-675` 强制 train/validation/test 不重叠；`fairness.py:161-260` 对 learned/AMG 在 validation PUT_BACK 网格独立选择，并拒绝冻结目标变化；test 仅评分 | 工程时序已冻结；动态场景复用选择且不重调，只能作敏感性，不是排序优越性 |
| 预算与 CIAV | 三臂协议冻结外生预承诺 micro-verify、三臂相同候选/结果，component costs 全 0、privacy budget 1；`fairness.check_step` 与三臂 receipt 合同逐字段比对 | 这是信息匹配接口，不是净效用或等算力证明；容量/训练/在线预算规则仍待用户选择 |
| 停止/判定规则 | death-test signal rule 冻结 3,000 episode bootstrap、95% CI、absolute 0.02、relative 0.1，P5 必须同时胜两基线；SEARCH/PUT_BACK 不聚合。最终 PCT/guardrail 协议为 `FROZEN_NOT_RUN` | 不得改阈值；但这不是在线停止规则。训练 early-stop、共同算力停止、实验停止均未在 W2 统一实现中建立 |
| 解码 | `structure_two_p5_three_arm_contract.py` 强制共同 typed decoder；SEARCH=current，PUT_BACK=owner habit；`fairness.py:77-101` 检查排序/平局/目标实例 | 共同解码规则冻结；当前 detected-current adapter 会抹去 native SEARCH 差异，是否保留共同接口或允许原生先验/头仍需明确合同 |
| 长期账本 | `audit.py:172-190` 读取真实 fast/surviving/regime/pooled 和 committed counts；历史 v5 的 direct P5 committed 在 1,920 步全为 0；普通 reference 非空不能冒充 P5 | 长期记忆/唯一账本公平收益未建立；修复后需同一连续历史检查提交、撤回、纠正、恢复与污染后果 |
| 实际动作与世界后果 | `CommitBarrier`/`SplitAccess.score_committed` 保证三臂 typed action 提交后才释放真值；但 `audit.py` coverage limits 明示 `No action-contingent environment`，dynamic execution 为 `MISSING` | 动作提交时序有工程证据；机器人/环境执行、世界状态变化和后续反馈闭环没有建立 |

## 4. future-location 与 owner-prior 的版本适用性

- **适用**：历史 v5、W2 实际运行源码 `d6112489…`、保全快照 `de2c04…` 及 `329787…` 对这些历史结果的验收准备。历史事实为 1,920 步 SEARCH 三臂相同、direct P5 committed 全零、P5/AMG PUT_BACK 错误 85/102，17 差额由缺-owner 冷启动规则解释。
- **不自动适用**：A 联合消费者实际代码 `1d24099…`、数据预检 `57e857…`、活动 scheduler、B 五边界修复或未来统一 SHA。它们的支持集/owner prior/adapter/消费者可能不同，必须在各自准确 SHA 重新构造相同前缀反事实。
- **历史 future-location 结论不是“所有未来位置都被模型真值消费”**：它证明候选支持由完整 episode 构造并在早期影响归一化/平局；需用“相同早期可见前缀、只改变晚到新地点”的对照定位实际动作影响。
- **owner-prior 混杂不是算法公平性已修复**：共同先验只作为开发对照；正式比较是选“共同无信息先验”还是“保留方法原生先验并分层报告”，必须由用户决定，不能选择对 P5 有利的版本。

## 5. 已冻结规则与待用户决策

已冻结、不得擅改：A1 外生预承诺共享 CIAV；B1 条件 location head；train/validation/test 访问时序；validation PUT_BACK 选择目标与现有网格；共同 typed decoder 及 SEARCH/PUT_BACK 任务分离；真值在动作提交后释放；3,000 bootstrap、95%、0.02 absolute、0.1 relative 信号门；最终 PCT/guardrail 定义；不运行 router calibration；保留 H/R/I/C/Z/r/V、三个 RB blocks、七算子、隐藏事件、多人物、开放世界、可逆归因和具身反馈范围。

仍需用户科研决策：

1. 公共完整地图 vs 共同因果前缀 catalog（含 unknown bucket 的精确定义）。
2. 缺 owner 时共同无信息先验 vs 保留方法原生先验并预注册冷启动分层。
3. native SEARCH head/adapter 与共同 decoder 的接口：是否允许原生信息进入同一类型化 posterior，不能靠当前 detected-current 读出掩盖差异。
4. “相同信息权限”与“相同实际特征消费”的目标；ordered-role 等字段的共同/原生权利。
5. 固定计算/延迟匹配容量 vs 冻结 PCT-online-compute Pareto 多预算；训练、fit、cache/warmup、在线运算与停止规则的统一计量。
6. 长期记忆与反馈 challenge distribution。不能看到效果后再选择稳定/变化/迟到纠正比例。

这些是决策点，不是把生产缺口推给用户：目标实例绑定、默认联合消费、唯一账本、真实执行桥、来源身份和失败原子性仍是工程责任。

## 6. 单一统一 SHA 到达后的可执行验收合同

1. A 发布经审查的单一完整 SHA；冻结源码、测试、配置、数据、解释器、依赖、加载字节、输出根与缓存域。若任一改变，整轮作废。
2. 在全新独占输出域依次生成 comparison 四文件、生成 attribution、主 CLI fresh verify、归因 CLI fresh verify；四步均 exit 0 且逐包语义正确后才运行测试。
3. 合法新参考包必须先通过两个真实 CLI；记录包四文件哈希、401+ 实际 source bindings、解释器及模块加载路径。
4. 在同一新参考包构造 31 类历史意图及新增状态机/依赖攻击。每项先产生 `mutation_witness`；no-op 不计入攻击数。同步重算所有可自算依赖；语义攻击不能靠旧 source mismatch 被拒绝。
5. 每批保留合法正例；单包和混合批次逐包检查。归档真实攻击包、完整命令/env/start/end/exit/stdout/stderr/JUnit，不用批次 exit 1 代替逐包结果。
6. 公平重算至少包含：同前缀晚到地点对照、缺 owner 两个预注册规则、消费特征/访问轨迹、预算/停止/解码、1,920 步与四类归因、长期账本、typed action、实际环境后果及反馈修订。
7. 分开结论：工程回归、独立审核、默认能力、统一验收、科学收益。旧 v5 与本轮报告只能作为历史对照，不能签新版本。

当前阻塞：共享分支仍为 `bdec3ee…`，未包含各窗口全部成果；没有 A 发布的单一统一冻结源码；本终端又无法物化 Git checkout。故本轮只交付验收准备，不拼接多分支结果，不签公平比较或科学收益。

## 7. 接收方

- A：审查并发布单一统一 SHA；明确哪些消费者/默认路径已整合，提供精确 source/test/config/data 清单。
- 用户：只需决定第 5 节六项科研规则；无需为工程缺口背书。
- B 后续独立窗口：在可物化的干净 checkout、Python 3.13.5 独立环境上执行第 6 节；新修复仍需 A 复核。

本报告没有 PR：当前连接器只有 `pull=true`、`push=false`，且目录不是 Git checkout。未推送成果只能称本地验收准备。
