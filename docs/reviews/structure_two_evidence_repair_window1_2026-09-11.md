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

更早的真实首次失败记录在 `557ff9c`，文件 SHA-256 为
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

1. 将 `557ff9c` 的真正首次失败保存为
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

## 5. 验证记录

最终验证结果在完成审计矩阵和检查点核验后填入本节。当前中间产物不应作为最终通过声明。

## 6. 复现和整合顺序

在此分支工作树、匹配的 `.venv` 中运行；历史快照需要保留共同起点的 Git 历史，不能仅复制源码目录。

```bash
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py \
  --recompute-first-failure --recompute-failed-replay \
  --output benchmarks/structure_two/evidence_repair_2026_09_11/historical_source_audit.json
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
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
