# 结构二实验版本与证据链修复：窗口一（2026-09-11）

本窗口共同起点为 `09eb4d48e1c11082e90ca18332d04333e6b5b47a`，独立分支为
`codex/s2-evidence-repair-window1-20260911`，工作树为
`/private/tmp/cpswm-s2-evidence-repair-window1`。未修改原工作区，未合并其他窗口分支。
本报告只评价工件、源码与验证器的工程证据；不改变七算子算法、动作语义、预注册阈值、种子、
确认集或路由器训练策略，也不作新的科学方向选择。

## 1. 复现与根因

在共同起点运行下面两个定向测试，得到 **2 failed**：

```bash
.venv/bin/pytest \
  tests/test_structure_two_p5_readout_posthoc_diagnostic.py::test_posthoc_config_discloses_opened_test_and_forbids_positive_receipt \
  tests/test_structure_two_engineering_trust_checkpoint.py::test_checkpoint_is_current_without_repeating_the_expensive_fresh_run
```

分别报 `retained v0.1 result file hash drifted` 和 `P0 content manifest is not current`。
复现原始日志见 `benchmarks/structure_two/evidence_repair_2026_09_11/baseline_failures.log`。

三臂旧路径 `structure_two_p5_three_arm_death_test_v0_1.json` 被重复用于不同源码版本。
post-hoc 配置引用的是 `4103bea` 的失败重放，文件 SHA-256 为
`1a617567a224d11eca20f589a9aa84ddc2195494263bc58f2c4fb21030643c04`。
`09eb4d4` 把它替换为修复后开发结果，文件 SHA-256 变为
`a25b8619fd0270b863bfd0aa8e91767a0cd6274d164f3529424175fe7218bfcf`，旧期望哈希因而失效。
二者 signal gate（信号门）均为失败，但数值和实现版本不同，不能互换。

Git 中更早的首次失败标签记录在 `557ff9c`，文件 SHA-256 为
`ca30ac7db2ff26476a17fa9ca9d19760763508010a312acd8b18d4ba194dca94`，
content SHA-256 为 `df44a16e4b450fc77239d0e3e3bbcf9f3fbb3fbbcca9a2db6a0844ce8a6267b5`。
它与 `4103bea` 失败重放不是同一份原始工件。`4103bea` 还改变了来源绑定、历史措辞和两条链哈希。
因此不能把修复解释为“把期望哈希更新到最新版”。

P0 清单和工程检查点是上一个源码/配置/测试/工件状态的快照。后续源码、配置、工件变化之后，
它们原有的本地通过记录仍有历史意义，却不能证明共同起点当前通过。

### 独立工作树暴露的两个未跟踪依赖

扩大回归的预检查在中断时记录 12 failed、23 errors、2300 passed、1 xfailed。
失败/初始化错误均指向两个被 `.gitignore` 忽略的文件：

- `artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json`，
  SHA-256 `5be8a0c5c87b2272049ed6e283e63feab12bcaa97b1f7b91ecaec69ad8986478`；
  共同起点的 `benchmarks/structure_two/structure_two_action_utility_construct_gate_v0_1.json`
  已在 `source_binding` 固定此哈希。
- `output/method_falsification/round_two_structure_one_placement_v0_1.json`，
  SHA-256 `4a4758b3ecc8fd1b409bddef66825259d1a0ed85dcddc5b1a0d94938832b7ef4`；
  共同起点的 `configs/method_falsification/placement_authority_v0_2_preregistration.json`
  已固定它为必须保留的历史失败。

两者不在 Git blob 中，因此不能声称从 Git 恢复文件本身。本窗口只读原目录，先与上述 Git 中
已有的固定哈希逐字节核验，再复制到自己的工作树并显式加入版本控制；没有复制其他窗口源码或分支，
没有重新训练模型，也没有用新结果代替旧失败。P0 `test_fixture_contract` 扩展为包含这两个实际
被消费的旧路径，并检查必需覆盖、固定哈希和符号链接；缺失或重新哈希替换都不能通过。
相关 fixture/preregistration（测试工件/预注册）定向回归已得到 28 passed（排除尚待最终生成的当前清单测试）。
这说明仅覆盖 `benchmarks/**/*.json` 的旧清单不足以让全套测试在干净工作树中复现。

### 完整回归补充发现与恢复

第一次正式全套审计还发现 12 failed、5 errors：其中 11 项失败及 5 项初始化错误来自其他缺失旧依赖；
另 1 项失败是 v0.5 当前兼容性审计仍写旧源码数量 301，当前实际为 310。失败回执和压缩原始日志保存在
`benchmarks/structure_two/evidence_repair_2026_09_11/failed_full_audit_attempt/`，不作为最终通过回执。

额外恢复 19 份文件，逐项 SHA-256、共同起点引用和来源等级见 `additional_fixture_restoration.json`：
D1 的四份样例与共同起点已跟踪的 benchmark 文件逐字节相同；horizon probe 失败结果、其源码快照、
两个 strongest-neighbor 结果匹配共同起点配置固定哈希。corrected-instrument v0.3 结果及十份 D2
样例未找到共同起点文件哈希锚点，因此只记录为现有本地开发测试工件，不能声称已恢复可信历史执行。
D2 名称不赋予真实感知数据成熟度；反例测试确认它仍不能通过外部采集回执要求。没有执行新数据采集或
打开新确认集。上述恢复只补齐已有测试依赖，所有旧科学配置保持不变。

P0 明确固定全部恢复文件的哈希，包括 JSONL 数据和历史 Python 源码快照；限定路径可以进入测试工件
范围，其他路径仍必须满足原 benchmark JSON 规则。所有固定条目必须存在且精确匹配，不能删除后重哈希。
关联测试 38 passed，扩展 P0 测试 23 passed。v0.5 兼容性报告由现有审计脚本重新生成；历史冻结数量
245、历史摘要、签名和不兼容/真实性未证实边界不变，没有重写旧冻结来源以匹配当前源码。

## 2. 可追溯时间线与历史声明边界

以下时间均为 Git 提交记录的 +08:00 时间；不是独立可信时钟，也不能证明文件第一次执行或首次访问。

| 提交 | 时间 | 记录及可支持范围 |
|---|---|---|
| `883f676` | 09-10 23:38:53 | 三臂协议冻结记录；冻结参数保留 |
| `0e9373e` | 09-11 00:23:36 | 三臂实现记录，早于首次结果提交 |
| `557ff9c` | 09-11 00:40:23 | Git 中最早三臂失败工件；独立保存原字节 |
| `d0bd9c1` | 09-11 01:18:23 | PCHMP→CIAV 人物后验传递修复记录 |
| `966701e` | 09-11 01:29:47 | 首次 post-hoc 诊断记录，使用已开启开发数据 |
| `80d0457` / `b1b120b` | 01:39:42 / 01:54:32 | debt-replay 工程协议和首次结果记录；非科学确认 |
| `4dbeb3c` | 09-11 12:54:20 | Structure One 传递依赖稳定化记录 |
| `df5bd6b` | 09-11 13:46:54 | 精确 replay 绑定、完整源码/锁绑定、D0 12001–12060 配置冻结记录 |
| `4103bea` | 09-11 14:44:24 | 析因、失败重放、D0 初次工件及语义链修复记录；提交内部执行次序不能由 Git 单独证明 |
| `09eb4d4` | 09-11 16:33:31 | 三臂修复后开发结果覆盖旧路径；另有 D0 开启后重放工件 |
| 本修复分支 | 09-11 | 恢复与分版、历史审核、当前源码重算、最终本地工程检查点 |

`configs/project_two_experiments/structure_two_evidence_history_v0_1.json` 列出 **11 份**历史工件的
完整 Git 提交、原路径和保存路径。所有副本逐字节对照对应 Git blob，再验证各自 content hash。
`historical_source_audit.json` 另逐项检查声明的源码哈希，并在独立历史快照中构造对应版本的完整装配清单。

重要降级：

- `557ff9c`、`966701e`、`b1b120b` 的完整已提交源码快照不能导入：
  `prototype_spine.py` 需要 `project_one_regime_loop.RegimeStage`，但对应快照没有该符号。
  本窗口尝试历史重算并记录该失败；没有借用后来的依赖假装原版已经可重算。
  这些工件的字节、内容一致性和直接声明绑定可查，但完整历史执行环境无法由这些提交恢复。
- `4103bea` 的失败重放、post-hoc 重放、debt-replay 重放、析因工件，直接绑定与该提交装配清单匹配。
  其中被 post-hoc 引用的三臂失败重放已使用 `4103bea` 完整源码全量重算，整个工件逐字段相等；
  其余三份此次只核验来源快照，不把来源匹配冒充历史数值重算。
- D0 `initial_open` 工件原字节保留，content SHA 为
  `9320c4388aa1435284e9163a6d8dfebab72d1a61147c541b5be659e90c88963b`。
  它的 `posthoc_adapter` 和装配哈希与记录提交 `4103bea` 不一致；本地冻结记录和种子区间不重合
  不能证明过去从未访问过数据，也不能证明执行时源码恰为冻结提交。
  因而“首次未见确认”降级为“仓库标记为初次开启的内部 D0 历史记录”。
- `09eb4d4` 中修复后三臂工件的 execution-module 哈希不匹配记录提交；该提交中的析因与 D0
  重放也不能匹配其完整装配哈希。与结果生成后源码继续变化相容，但不能据此确定具体执行时点。
- 任何 `confirmatory=false`、独立托管缺失、SEARCH/PUT_BACK 不聚合和 Task 7/8/9 未通过边界均保留。
  本窗口的新 D0 工件明确设置 `previously_unused_test_seed_range=false`，只声明 post-open replay
  （开启后重放），不打开新确认集。

## 3. 修复和版本规则

1. 将 `557ff9c` 中最早记录的失败保存为
   `history/three_arm_first_failure.json`；将 `4103bea` 的被引用失败重放逐字节恢复到旧 v0.1 路径。
   **旧 v0.1 路径现在是历史兼容引用，不代表最早失败，也不代表当前结果。**
   post-hoc 期望哈希没有改动。所有原配置及阈值也没有改动。
2. `09eb4d4` 覆盖前的修复后开发结果另存
   `history/three_arm_repaired_development_09eb4d4.json`；其他相关历史结果也各自保存。
   原有 `structure_two_p5_unseen_d0_holdout_initial_open_v0_1.json` 未改动。
3. 五类当前结果统一写到
   `benchmarks/structure_two/evidence_repair_2026_09_11/current/*_v0_2.json`。
   协议/分析规则版本保留，结果证据版本为 `0.2`，生命周期为
   `POST_OPEN_CURRENT_SOURCE_REPLAY`。不赋予首次、未见、确认性或历史替代权。
4. 所有五个 CLI 在运行前拒绝写入历史路径、目录逃逸和符号链接。
   当前验证器拒绝旧版本/生命周期，即使补写标签、重算外层哈希，旧来源绑定仍会失败。
5. 通过共同起点的 Git 字节固定 P5 配置、数据种子配置、读出预注册和 post-hoc 历史依赖；
   通过 `4103bea` 的 Git 字节固定被引用失败结果。同时修改结果和期望哈希也不能变更历史触发依据。
   检查在执行前发生，不能先使用替换种子、执行后才报错。
6. 当前进程导入时记录源码、JSON 配置和锁文件清单；运行前及装配绑定时检查它们。
   拒绝已导入旧实现的进程通过重新哈希磁盘新源码，给缓存实现赋予新来源身份。

## 4. 传递绑定、重算和测试范围

生产装配清单已经覆盖全部 `src/cpswm/**/*.py`、`pyproject.toml` 和 `uv.lock`。
本窗口核验的是 `source_binding → production_assembly_manifest_sha256 → 全量源码/环境锁`，
没有因顶层未列出某个模块而判定漏绑。新增拒绝传递源码和环境锁符号链接，防止清单越界读取。
Structure One 依赖替换、增加/删除源码、环境锁变化均改变清单或直接被拒绝。

历史 `typed_action_chain_sha256` / `ciav_receipt_chain_sha256` 混有随机运行期标识，
不能用其跨运行变化直接判定指标变化，也不能简单忽略整个工件。当前实现已经使用动作位置以及
CIAV packet/outcome/cost/closure 语义字段构造可重复链；本窗口保留这套既有语义。
当前五个验证器仍完整重算并逐字段比较，未放宽数值、科学阈值或当前链哈希核验。
历史脚本对最早版本只允许显式排除这两项旧随机链及由它们决定的外层哈希，其他字段必须相同；
由于历史导入失败，不能声明该历史数值重放已完成。

| 输出/风险 | 验证路径 | 权限边界 |
|---|---|---|
| 历史字节已核验 | 固定 Git blob + content hash | 本地 Git 记录，不证明首次执行 |
| 历史来源可恢复 | 直接绑定 + 对应提交装配清单 | 未全量重算则不声称数值复现 |
| 当前五类结果、汇总、配对门、诊断、执行计数 | 独立进程全量重算 + 完整结果相等 | 已开启数据，仍不作新科学确认 |
| 修改数值并重哈希 | 每个当前验证器的完整伪造输入测试；独立真实 runner 审计 | 单元比较边界与真实实验重算分别记录 |
| 旧工件冒充当前 | 生命周期、来源绑定、完整重算 | 补写版本标签亦不够 |
| 源码/锁替换、增删、符号链接 | 全量装配核验、进程导入清单 | 不能以缓存运行时绑定新源码 |
| 同时改失败结果与期望哈希 | 冻结配置和工件的固定 Git 对照 | 不授权重新定义历史 |
| 本地工程通过 | 真实命令回执、P0 前后相等、环境指纹、当前结果清单 | 非独立托管/历史执行真实性证明 |

测试覆盖上述窗口内输出和攻击类别；不声称对完整 CPSWM 所有正向授权状态机完成穷尽安全审计。

审计器还区分 invocation executable（调用入口）与 resolved executable（解析后二进制）。
原来直接用解析后的系统 Python 路径启动命令，会丢失 `.venv` 上下文。现在保留 `.venv/bin/python`
启动入口，同时记录实际二进制路径与 SHA-256，检查点核验两者，测试确认实际 `sys.prefix` 是本工作树
的虚拟环境。版本探测只运行 `--version`，实验校验只出现在正式命令回执中。
当前与历史 P5 校验是两个只读、互不依赖的作业，并行执行；每条命令在实际执行线程内记录开始/结束
时间，回执仍按固定命令清单记录。其余审计命令保持原有顺序，清单的执行前后核验均保留。

## 5. 验证记录

最终本地工程审计的 **10 条命令全部退出 0**：当前五组 P5 全量重算、历史源码与失败重放核验、
P0 对抗测试、完整核心 pytest、mypy、Ruff lint/format、compileall、冻结离线环境检查和 Git 差异检查。
核心套件实际执行 **3857 项：3855 passed、1 skipped、1 xfailed，0 failed、0 errors**。
P0 对抗矩阵 121 项全部通过；mypy 覆盖 309 个源码文件，Ruff format 覆盖 659 个文件。
审计执行前后的清单摘要相同，执行环境指纹相同。

- 最终 P0 manifest SHA-256：`12cd9f51373c4303b25f3f3e79a7c1a16399d97ef1901a808055a88708da3952`。
- 最终审计回执 content SHA-256：`1222e737f4f37dae6a8da40480cd7309221b1613e3e2a22ba49664ee0596b6ae`。
- 回执、10 条命令的原始日志和最终 `engineering_checkpoint.json` 位于
  `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/`。

最终检查点绑定本报告与上述清单/回执，并由生成器强制重新执行 Task 7/8/10 重算。
随后进行当前性核验和 15 项检查点定向测试；相应原始输出随封存提交保存为该目录下
`engineering_audit_logs/checkpoint_generation.stdout.log`、`checkpoint_verification.stdout.log`、
`checkpoint_tests.stdout.log`。这些后续检查不回填为先前审计矩阵的执行记录。
当前性核验使用 `--no-fresh-recomputation`，只避免重复刚由生成器强制完成的昂贵计算；
生成器本身仍禁止关闭 fresh recomputation（重新计算），检查点数值验证没有放宽。


已完成的定向验证：新增证据测试 26 passed；动作效用构造门与 readiness（就绪性）测试
75 passed；P0 清单测试 21 passed；缺失旧工件修复关联的 P0/placement 测试 28 passed
（其中 1 项当时未执行的当前清单测试已在上述 21 项中验证）。

当前与历史 P5 正式审计均已退出 0，其中历史失败重放整个工件相等，当前五类结果均通过完整重算。
另逐字段对比共同起点保存的五份开发结果：排除来源绑定、版本元数据和外层内容哈希后，
四份完全相同；D0 仅有 `previously_unused_test_seed_range` 与 `claim_boundary` 两处声明降级。
所有实验数值和语义结果保持一致。
科学与工程状态分别保留如下，不将工程通过改写为信号通过：

| 当前 v0.2 工件 | 保留状态 |
|---|---|
| 三臂 | `P5_ACTION_SIGNAL_NOT_DETECTED` |
| post-hoc | `POSTHOC_READOUT_DEGENERACY_REMOVED` |
| debt replay | `PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED`，仅工程语义等价 |
| 析因 | `DEVELOPMENT_FACTORIAL_COMPLETE` |
| D0 | `INTERNAL_UNSEEN_D0_SIGNAL_NOT_DETECTED` 为兼容旧标识；生命周期明确为开启后重放 |

检查点输入也完成一次 `fresh_recomputation=True` 的完整预检查：Task 7 v0.4、Task 8 v0.4、
Task 10 G1/G2 四份工件均匹配，P0 清单当前。Task 7/8 的失败、Task 10 的非正式授权边界均未改变。
该预检查不代替最终审计回执之后的检查点生成。

测试边界保留：已有一项 `xfail(strict=True)` 是 Structure One 同上下文 RLS 的压缩残差信号限制，
本窗口没有修改它；另有一项 macOS 隔离测试因外层环境禁止嵌套 `sandbox-exec` 而跳过，已用 `-rs`
单独确认原因。不能把这项未执行的隔离探针表述为已验证通过。

五类结果均全量生成。三臂、post-hoc 和 D0 还完成了生成器内的第二次完整验证；待所有 JSON
生成后结束生成器剩余的重复校验计算，统一由正式审计的 `p5_evidence_current` 对全部五类结果
重新执行完整验证。这不绕过任何当前验证器，也不将生成器的中断退出当作通过回执。

## 6. 提交、复现和整合顺序

- `7d66258818bdde2ee57efdf44f084e778ca01427`：历史/当前版本隔离、验证器、对抗测试。
- `505e723170c29f8707ee19d113a5b8646680c5f6`：固定旧依赖恢复、当前五组结果、历史源码审计。
- 最终审计、检查点和本报告由后续封存提交共同提交；其完整哈希见交付回复及本分支 `git log`。
  检查点绑定内容清单及本工作树路径/环境，不依靠在自身内容中嵌入封存提交哈希。

在此分支工作树、匹配的 `.venv` 中运行；历史快照需要保留共同起点的 Git 历史，不能仅复制源码目录。

```bash
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py \
  --recompute-first-failure --recompute-failed-replay \
  --output benchmarks/structure_two/evidence_repair_2026_09_11/historical_source_audit.json
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
.venv/bin/python apps/evaluation_runner/audit_structure_two_world_source_bundle_v0_5.py
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
.venv/bin/python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py \
  --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/engineering_checkpoint.json
.venv/bin/pytest tests/test_structure_two_engineering_trust_checkpoint.py
```

审计矩阵新增 `p5_evidence_history`（重建历史源码核验并重算可恢复失败重放，逐字段核对历史审核报告）
和 `p5_evidence_current`，实际在五个独立进程中完整重新核验五类结果；检查点绑定这些结果
的路径、文件哈希、内容哈希、状态和生命周期，且保留原 Task 7/8/10 验证链。
更新顺序必须为：最终源码/测试/配置 → 当前实验工件 → P0 manifest（内容清单）→ 真实审计回执 →
工程检查点 → 检查点定向验证。不能只改 `passed`，也不能用旧回执搭配新清单。

**三个窗口成果合并后，必须对整合后的源码重新计算工件、生成 manifest、执行审计并生成最终检查点。
本分支通过不能自动继承。** 整合时应保留历史副本及原始失败哈希，避免其他窗口再次覆盖旧 v0.1 路径；
当前工件对整个 `src/cpswm` 及锁文件绑定，任何其他窗口的源码变化都会使本分支当前工件失效。
如果需要改冻结科学配置，必须另建有明确决策来源的新协议版本，而不是改共同起点固定输入来让工程核验通过。
