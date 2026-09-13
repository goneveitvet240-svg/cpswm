# 结构二窗口二：统一重算前交接合同（2026-09-12）

本轮仅交接清单和使用说明。结论保持：**局部诊断可靠，完整机制、公平性和科学收益尚未建立。** 本轮没有运行新实验、重生成 bundle_v5、修改测试或实现，也没有合并、推送、指定统一工作树。

## 1. 固定状态、保全范围与证据边界

- 当前工作树 `/private/tmp/s2-comparison-audit-window2-20260911`，分支 `codex/s2-comparison-audit-window2-20260911`；开始时 HEAD 为 `aa9690146e5261d826b642c7bc4c54d2c43be31b`，工作区干净。
- 已完整阅读主工作区 `docs/reviews/structure_two_three_windows_round5_independent_review_2026-09-12.md`，其路径和字节摘要登记在本次 [inventory.json](data/structure_two_window2_handoff_2026-09-12/inventory.json)。该文件是保全与路径清单，不是新重放证明或独立历史托管证明。
- 本机解释器 `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python`，本轮只查询版本：Python 3.13.5。既有验证也使用此解释器。
- 本次清单保全 **889 个文件**：包括 v5 的 401 项源码绑定、五个测试文件和攻击构造 helper、既有窗口二诊断工件及此前保全对象。全部逐文件 SHA-256 在 inventory；完成文档后再次比较。本轮没有重新签发 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`。
- 既有运行实际源码提交 `d6112489d0a09f7086286e223741be60051b99a5`；之后 `e8b5cee9601a35bb1220480ebe60b0c74f3c4799` 增补迟到输入测试；`aa969014...` 留存报告与证据。本轮读取确认 v5 的全部 401 个绑定仍与当前磁盘源码一致。此项只证明字节未变。

以下路径以本工作树为根，**仅用于定位历史工件，不是对未来统一工作树的指定**：

| 工件 | 路径 | 用法 |
|---|---|---|
| 已独立复核的 v5 | `docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/bundle_v5` | 本分支当前历史参考，4 个包文件保持原字节 |
| 成功 v5 的全部证据 E5 | `docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500` | 命令、日志、77 项 JUnit、31 类攻击矩阵、来源攻击、动态场景导出 |
| 首次失败 v5 | `docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1415/bundle_v5` | 保留序列化类型不一致拒绝与中止日志；不能当作成功包 |
| 旧 v4 | `docs/reviews/data/structure_two_comparison_audit_window2_fairness_2026-09-12/bundle_v4` | 数值对账历史输入；源码已过期 |
| 旧 v2 | `docs/reviews/data/structure_two_comparison_audit_window2_r1_2026-09-11/bundle_v2` | 部分测试的危险缺省值；不应被统一运行隐式使用 |
| 更早证据 | `structure_two_comparison_audit_window2_2026-09-11`、`structure_two_comparison_audit_window2_round3_2026-09-11`（均在 `docs/reviews/data/`） | 同样只保留，不修改来源字段“修绿” |

E5 中 `pytest.xml` 实际记录 77 项、零失败/错误/跳过；独立复核另行确认 77 项和 31 类完整伪造。本轮不把读取既有记录写成重新跑过测试。31 个攻击包当时位于 pytest 临时目录；**本轮逐一检查，这些临时包已不在原路径**。保全的是完整构造源码、输入参考包、同步重算过程、逐包结果、命令及完整日志，不能声称 31 个临时包原字节已归档。inventory 逐项记录原路径和 `exists_at_handoff=false`；未来应在新测试临时目录生成，并在该目录被清理前归档攻击包，不能提前用 v5 重建冒充历史原件。

## 2. 生产者—消费者合同

### 2.1 必须遵守的依赖顺序

固定实际统一源码及测试预期 → 生成主比较包 → 生成归因 → 两个真实 CLI 完整验证 → 同一包供回归与完整伪造测试消费 → 数值对账、证据归档及统一验收。

| 生产者/消费者 | 输入 | 写入 | 成功声明的含义 |
|---|---|---|---|
| `apps/evaluation_runner/run_structure_two_comparison_audit.py --output B` | 实际脚本根目录的源码、配置和历史 benchmark；真实构造的数据 | 新目录 B 的 `audit.json`、`steps.jsonl.gz`、`timing.json` | 生成；不是独立验证 |
| `summarize_structure_two_comparison_audit.py --bundle B` | B 的主比较包、实际根目录 | 以排他创建写 `B/attribution.json` | `UNVERIFIED_ATTRIBUTION_WRITTEN` |
| 主入口 `--output B --verify` | B + 当前执行源码下新鲜重放 | stdout/stderr；不改 B | 完整主审计重算匹配（主入口输出 `verified` 字段） |
| 归因入口 `--bundle B --verify` | 同上，含归因；批次共享一次真实重放 | stdout/stderr；不改 B | **逐包** `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，科学认证仍为 false |
| 归因 `--check-file-consistency` | 包内文件 | stdout/stderr | 只有 `FILE_CONSISTENCY_ONLY`，`fresh_replay_performed=false` |
| 五个测试文件 | 下表列明的新鲜 B 或直接构造的数据 | 证据目录及 pytest 临时目录 | 受测工程断言通过；不代表科学门通过 |
| E5 的 `export_evidence.py` / `summarize_validation.py` | 既有包和真实日志/JUnit | 场景矩阵、数值对账、验证汇总 | 描述性导出，不是认证入口 |

B 必须包含四个文件后才作为完整测试输入冻结；记录生成完成后的文件摘要，验证和测试结束后检查未变。生成入口拒绝覆盖已有工件，归因同样不能覆盖。一个攻击批次 exit 1 是预期的混合结果，**不等于每个攻击被拒绝**：必须逐包核验合法参考 MATCH、所有攻击 REJECTED 且有定位错误。错误来源批次不得出现任何肯定认证或弱检查回退。

主入口 `--repository-root` 只能表示**执行该 CLI 的实际源码根目录**；不是数据重定位参数，也不能声明 A 而加载 B。归因入口根目录由脚本位置确定。两个入口及本地依赖继续使用已经通过的来源保护；不能为统一编排方便关闭它。测试故意建立的 A/B 镜像只用于攻击或同源码正例，不是生产依赖来源。

### 2.2 真实数据与本地文件输入

- `configs/project_two_datasets/d0_unseen_p5_holdout_v0_6.json`：训练 seed 1–20、验证 1001–1020、测试 12001–12060，每 episode 32 步；20/20/60 划分，测试 1920 步。具体 episode ID 清单在 inventory。数据由本地 adapter 构造，不读取一个额外的外部数据目录；名称含 unseen，但已打开，只是开发诊断。
- `configs/project_two_experiments/structure_two_p5_three_arm_death_test_v0_1.json`：冻结三臂开发选择网格和预算。
- `benchmarks/structure_two/structure_two_p5_unseen_d0_holdout_v0_1.json`：历史对照输入，只读；不覆盖。
- `configs/project_two_experiments/structure_two_final_utility_guardrail_external_validation_protocol_v0_1.json`：动态合同检查读取冻结 PCT/guardrail 协议，**没有在此运行最终效用实验**。
- 源码绑定覆盖 `src/**/*.py`、`configs/**/*.json`、历史 benchmark 和两个 CLI 及 `_structure_two_audit_source.py`，既有包共 401 项。测试与解释器必须另外绑定，不能因包内有 source_bindings 就声称它包含所有测试和环境。
- 单元夹具从真实训练划分建立小模型（width 8、learning rate .05、L2 0，smoothing 1、AMG parameter .2）；它不替代完整 CLI 的独立验证集选择。动态场景来自 `structure_two_comparison_dynamic.PLANS/fixture`，标为 development-only，三臂同历史；普通生产 reference 的学习不是 P5 额外预热。

### 2.3 五组测试的包、环境、输出

这些是参数展开后的数量，来源为既有 `pytest.xml`，不是本轮新测试结果。

| 测试文件（均在 `tests/`） | 项数 | 包输入与默认值 | 写入位置 |
|---|---:|---|---|
| `test_structure_two_comparison_audit.py` | 20 | 不读取 S2_AUDIT_BUNDLE；直接构造真实数据/三臂 | `tmp_path` 中小型 `audit.json`、`steps.jsonl.gz`、`timing.json` 及篡改文件 |
| `test_structure_two_comparison_audit_verification.py` | 6 | **模块导入时**读取 S2_AUDIT_BUNDLE；缺省旧 v2 | `tmp_path/<21 case>/` 攻击包；S2_AUDIT_EVIDENCE_DIR 下日志与矩阵 |
| `test_structure_two_comparison_audit_execution_source.py` | 16 | 独立在导入时读同一变量；缺省 `<ROOT>/not-generated-round3-bundle` | `tmp_path/A`、B、forged、foreign_dependency.py、pyc；S2_SOURCE_EVIDENCE_DIR 下记录 |
| `test_structure_two_comparison_fairness.py` | 16 | 从 verification 模块导入 BUNDLE，因此缺省旧 v2；其他夹具直接构造数据 | `tmp_path/<6 case>/`；S2_FAIRNESS_EVIDENCE_DIR 下日志与矩阵 |
| `test_structure_two_comparison_dynamic.py` | 19 | 同上，4 类伪造消费 B；其他夹具直接运行生产接口 | `tmp_path/<4 case>/`；S2_DYNAMIC_EVIDENCE_DIR 下日志、矩阵和迟到输入记录 |

共享 `tests/structure_two_comparison_audit_adversary.py` 读取参考 B，构造 `audit.json`、`steps.jsonl.gz`、`attribution.json`，其中 receipt 攻击额外写 `verified.json`。21 类 helper 攻击不要求 timing 文件；六类公平性与四类动态攻击经 `audit.save` 还会写 timing。没有额外的网络数据输入。

必须在 pytest **收集前**给出绝对路径，xdist worker 继承同一环境；收集后修改变量不会改变已导入的 BUNDLE，也不会改变来源测试 `arguments` 的默认实参。

| 环境变量 | 统一运行必须提供的值（R 为未来新输出根） | 未提供时的真实行为 |
|---|---|---|
| `S2_AUDIT_BUNDLE` | 已生成且由两个入口验证的 `R/comparison` | 上表的旧 v2 或不存在的占位目录；不是自动生成 |
| `S2_AUDIT_EVIDENCE_DIR` | `R/r1_matrix` | `tmp_path/evidence` |
| `S2_SOURCE_EVIDENCE_DIR` | `R/source_tests` | **调用根目录/source-evidence**；可能写入被绑定的源码区 |
| `S2_FAIRNESS_EVIDENCE_DIR` | `R/fairness_tests` | `tmp_path/evidence` |
| `S2_DYNAMIC_EVIDENCE_DIR` | `R/dynamic_tests` | `tmp_path/evidence` |
| `PYTHONPATH` | 实际源码根的 `src` | 顶层 pytest 导入受启动环境影响；正式 CLI 仍核验来源 |
| `OMP_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`VECLIB_MAXIMUM_THREADS` | 既有运行均为 `1` | 数学库缺省，不能据此宣称等算力 |

`cli()` 和来源 `invoke()` 都用 **sys.executable** 启动子进程。前者强制子进程 PYTHONPATH 为 ROOT/src；后者根据具体攻击故意切换为 B/src 或预加载脚本。不要把这些攻击的环境覆盖“修正”掉。脚本没有 S2 开头的其他隐藏输出变量。

明确的输出文件：

- `r1_matrix/{r1_file_consistency_only.log,adversarial_cli.log,adversarial_matrix.json}`。
- `fairness_tests/{fairness_forgery_cli.log,fairness_forgery_matrix.json}`。
- `dynamic_tests/{dynamic_forgery_cli.log,matrix.json,fresh_identifier_late_input.json}`。
- `source_tests/<name>.{json,log}`，16 个 name：`main`、`attribution_single`、`attribution_mixed`、`repository_root_mismatch`，以及 `downstream_symlink`、`preloaded_old`、`preloaded_downstream`、`runtime_drift`、`stale_entry`、`full_positive_stale_pyc` 各自的 `_main` / `_attribution`。
- pytest 临时根：A/B 镜像、故意污染的 pyc、攻击包及测试隔离目录；临时根由 pytest/xdist 分配。当前历史绝对路径逐包登记在 inventory；不能作为下一轮输入。
- pytest 框架输出：JUnit、缓存、终端完整日志；Python 普通导入还可能创建 `__pycache__`。统一编排须显式配置 `--basetemp`、`-o cache_dir=...`、`--junitxml=...`、字节码输出策略。`PYTHONDONTWRITEBYTECODE=1` 可约束隐式缓存，但来源测试显式构造的 pyc 必须保留在其临时镜像。若使用 TMPDIR/TMP/TEMP，也须记录并放入声明输出域。

**每次 pytest 使用全新且独占的 basetemp 子目录**：pytest 会清理它，绝不能指向包目录、历史证据根、整个 R 或源码根。同一证据目录会被测试 `write_text` 覆盖，不同运行/重试必须换新目录；不要让两个并行测试任务共用上述四个证据目录。

## 3. 给窗口一的编排使用说明（未来执行，本轮未执行）

第五轮复核发现：W1 将消费测试排在 comparison/attribution 生成前，未绑定 S2_AUDIT_BUNDLE；来源测试缺省输出进入源码快照；验证 `.venv/bin/python` 却运行可能带旧 shebang 的 `.venv/bin/pytest`。这是生产者—消费者和解释器合同问题，不应靠跳过测试或放宽来源保护处理。本窗口不修改 W1。

以下变量由统一集成负责人提供，不指定统一工作树或新科学配置。`SOURCE_ROOT` 必须是最终实际执行源码；`RUN_ROOT` 为全新输出目录，与旧包及源码输入文件不重叠。先确认该源码已更新下节中的缺陷断言，再冻结源码。命令模板中的所有日志均应由编排器记录完整 command/cwd/env/start/end/exit，不能只收最后一行：

```sh
# 仅为未来命令模板；三个路径先由统一编排赋值并校验。
: "${SOURCE_ROOT:?需要实际固定源码根}"
: "${RUN_ROOT:?需要全新独立输出根}"
: "${PY:?需要经核验的 Python 3.13 解释器}"
cd "$SOURCE_ROOT"
export PYTHONPATH="$SOURCE_ROOT/src"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export S2_AUDIT_BUNDLE="$RUN_ROOT/comparison"
export S2_AUDIT_EVIDENCE_DIR="$RUN_ROOT/r1_matrix"
export S2_SOURCE_EVIDENCE_DIR="$RUN_ROOT/source_tests"
export S2_FAIRNESS_EVIDENCE_DIR="$RUN_ROOT/fairness_tests"
export S2_DYNAMIC_EVIDENCE_DIR="$RUN_ROOT/dynamic_tests"

"$PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$S2_AUDIT_BUNDLE"
"$PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle "$S2_AUDIT_BUNDLE"
"$PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$S2_AUDIT_BUNDLE" --verify
"$PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle "$S2_AUDIT_BUNDLE" --verify
# 以上每一步必须 exit 0，并核验真实逐包状态，才执行测试。
"$PY" -m pytest -q -o addopts= \
  -o "cache_dir=$RUN_ROOT/pytest-cache" \
  --basetemp="$RUN_ROOT/pytest-temp-unique" \
  --junitxml="$RUN_ROOT/pytest.xml" \
  tests/test_structure_two_comparison_audit.py \
  tests/test_structure_two_comparison_audit_verification.py \
  tests/test_structure_two_comparison_audit_execution_source.py \
  tests/test_structure_two_comparison_fairness.py \
  tests/test_structure_two_comparison_dynamic.py
```

模板列出顺序，不是替代 W1 的失败关闭编排器；若按脚本使用，必须配置失败即停并检查逐包状态。**使用 `$PY -m pytest`，不用 `.venv/bin/pytest`**。预检与测试实际进程/worker 的解释器和关键模块来源必须一致；日志绑定实际加载身份，不能以另一个 Python 查询到的版本代替。现有 E5/run_validation.py 硬编码本机解释器和证据目录层级，verify 阶段并行三个任务，且未设置 basetemp/cache_dir；export/summarize 同样写固定位置，summarize 还固定期望77。它们是历史运行记录，不应原样作为未来统一编排，也不要现在在 E5 再执行。

W1 源码快照应包含真实源码、测试、配置、环境依赖；输出域仅排除显式声明、校验过且不与源码输入别名重叠的路径，不能宽泛忽略真实源码变动。完整归档临时攻击包之后再清理。正确性测试可并行，但共享机器争用下的墙钟时间不作为性能优越证据；性能实验需另行受控条件，不能混用此模板的耗时。

## 4. 哪些通过断言记录了“当前缺陷/限制存在”

以下标识均为实际测试函数名；其历史通过不意味着相应行为应永久保留。**本轮原样保全，不提前改测试。**

| 文件/函数 | 当前断言 | 统一版本后的处理 |
|---|---|---|
| dynamic / `test_current_production_revision_defect_is_not_promoted_to_success` | 公开 CORRECT 有非空目标、返回 operations=[correct]，但 old/new committed 均 false，新项未 quarantine；重复语义不变 | 核心旧缺陷快照，不能作为统一接受条件；按下节拆合法提交和非法完整回滚 |
| dynamic / `test_real_long_term_positive_is_not_misattributed_to_direct_p5` | 普通 reference commit>0、direct P5=0、全部场景 MISSING | 保留“reference 不能冒充 P5”；零提交/MISSING 只是当前覆盖结果，能力进入生产后按必要非空路径检验，不强制维持零 |
| audit / `test_same_location_full_p5_observes_but_does_not_commit_long_term` | 七算子被调用，observed/fast 非空，但 committed 为空 | 当前路径限制，不等于长期能力通过；依真实合法写入资格更新 |
| dynamic / `test_real_feedback_nonempty_mass_and_duplicate_invariant` | 反馈有非空贡献、重复不增量；execution=MISSING | 保留重复/反馈证据；真实执行桥进入后重新检查行动与环境状态，不能仍把缺失当通过 |
| audit / `test_amg_native_search_order_is_discarded_by_adapter`；`test_learned_joint_changes_do_not_route_into_search_but_habit_head_is_live` | 原生 SEARCH/joint 的扰动被当前读出丢弃 | 记录比较区分力限制；读出变更需共同解码合同与授权，不能为“测试变绿”改生产读出 |
| audit / `test_episode_diagnostic_partition_and_search_equality` | 当前 episode 的三臂 SEARCH 32 步分布相同 | 保留分组及先提交后真值；相同分布是当前快照，不是未来方法永远必须打平 |
| audit / `test_feature_bottleneck_ignores_ordered_role_evidence`；fairness / `test_consumer_probe_records_actual_values_and_restores_tracer` | ordered_role 未被特征消费者读取 | 保留真实消费探针，已授权特征接入后应验证消费及影响，不能把“永远不读”当公平条件 |
| audit / `test_full_episode_support_contains_future_visible_locations` | 当前 D0 缺公共 catalog，完整支持集含未来位置 | 记录设计未决；未来地图规则需用户决定，不能擅自改成因果前缀 |
| audit / `test_initial_amg_fallback_encodes_ignorance_as_a_different_point_mass` | 缺失 owner 时 P5/AMG 默认点质量不同 | 记录冷启动差额来源；共同先验只是开发对照，正式默认规则须按合同/决策处理 |
| fairness / `test_old_validation_consumer_rejected_new_consumer_matches_real_scores`、`test_safe_selection_preserves_frozen_grid_and_results` | 旧消费者早读真值被拒；安全消费者分数/选择与旧值相同 | 始终保留“动作提交前禁止验证真值”正负测试；若旧消费者也被修复，不应继续要求它必须抛错，不把旧实现当永久 oracle |
| dynamic / `test_fresh_identifier_out_of_order_is_not_just_duplicate_rejection` | 新 record ID、旧 timestamp 被严格时序拒绝，已报状态不变 | 当前入口合同的限制；未来若合法支持迟到重放，改为真实重放/无双计数/回滚不变量，不混淆重复与乱序 |

其余来源攻击、完整依赖伪造、严格 JSON、真值屏障、目标实例匹配、非空覆盖拒绝等是一般约束，不能因旧行为改变而删除。CIAV 同位置/异位置/负观测的路径断言须继续对照冻结共享合同。`scientific_acceptance=false`、冻结 PCT 不被重新定义等边界也不能因工程通过而自动翻转。

### 4.1 CORRECT 的更新验收合同

第五轮复核支持的是 W3 **实际交付快照**（HEAD `281e888...` 加当时未提交修改）已拒绝旧反例并完整回滚，不能只凭该 HEAD 或声明“合入了 W3”就认定使用了修复。未来先固定准确源码树和实际加载身份，确认变化确实存在。

1. **合法正路径**：通过公开入口和合法历史形成真实非空长期贡献；满足真实纠正资格后调用 CORRECT。断言原贡献撤回、新贡献真实提交、统计差额与 ledger/来源/资格一致，相关快慢记忆及后续读出反映纠正；无双计数、无幽灵隔离项。不能注入私有状态、替换生产方法或强制授权使其提交。执行与行动影响只有真实可达时才另行声称覆盖。
2. **非法负路径**：旧 W2 反例不能一律改成“应提交”。若按修复后的资格合同它不合法，应验证指定拒绝类型/原因，原贡献仍提交、新贡献不存在；完整可观察状态以及 Hybrid/CCRR/CF/particle workspace 的对象身份保持，统计、账本、资格、隔离区、反馈与相关预算无残留。不能“捕获任意异常就通过”，也不能只比较 committed 数量。覆盖已有纠正历史及重复请求，按明确接口合同检查幂等或拒绝，不重复扣减/入账。
3. **诊断消费者同步更新**：`structure_two_comparison_dynamic.boundary_probes` 当前记录 RETURNED/operations 及丢失贡献；修复后可能是 REJECTED/异常细节。先明确两个案例输入与资格预期，再更新报告字段及对应测试，不把缺失字段当默认成功。旧 v5 保留旧模式与旧数值。
4. **攻击不可变成无操作**：`test_new_dynamic_dependency_forgeries_real_cli` 的 `corrected_memory` 当前把 `new_committed` 写成 true；合法纠正真实提交后这可能已是真值。下一轮必须先证明新攻击确实改变参与结论的字段，再同步重算哈希和归因，经真实 CLI 拒绝；例如篡改合法纠正账本/贡献量，或把非法纠正改为已提交。不能仅改哈希或继续依赖旧 source_bindings 过期。
5. 同样审查 `action_consequence` 的硬设 PASSED/executed=true 是否仍是有效变异；`nonempty_commit += 1` 等也应确认改变真实结论。保留 21+6+4 类攻击意图与逐包断言，允许修复后的合法模式使具体字段更新，不能为了维持77这个数删除正负路径。普通参考的纠正成功仍不证明 direct P5 自动长期学习已可达。

## 5. 实际统一源码固定后的完整重算清单

此清单需统一版本负责人执行；本轮只交接，不提前生成新的 v5 或选择集成目录。

| 顺序 | 必做事项 | 留存/接受条件 |
|---:|---|---|
| 1 | 固定真实源码、测试、配置、数据、解释器与关键依赖；更新上述已知缺陷预期并经审查 | 精确 commit + 未提交差异/文件摘要、实际模块路径；不动态混用窗口三变化中的树；新输出域无重叠 |
| 2 | 新目录完整主比较，60 episodes / 1920 steps / 三臂，原选择网格及分割 | 四阶段信息流、真实后验/状态/动作/评分、source_bindings、计时范围；保留失败运行 |
| 3 | 新包生成归因，再由两个正式入口完整新鲜重放验证 | 主入口成功；归因逐包 MATCH、fresh replay true；实际源一致。不是 file consistency 或历史托管证明 |
| 4 | 动态 PLANS 全部运行，及同/异位置/负 CIAV、反馈、纠正/撤回/迟到边界 | 预声明路径、变/不变项、必要非空条件，逐场景矩阵与原始输入；更新后的合法/非法 CORRECT；真实主干未到达仍 MISSING，不伪造执行 |
| 5 | 五组原77项及受修复影响新增回归，来源攻击与两个完整正例 | 解释器一致；S2 包及四输出目录显式绑定；原有攻击意图/断言不丢。旧缺陷快照若被修复替换须逐项登记，而非静默删除 |
| 6 | 当前源码新包构造 21+6+4 类完整伪造；A/B、下游、预加载、陈旧 pyc、运行漂移等来源攻击 | 攻击非空、依赖同步重算，真实单/混合 CLI；逐包正负结果正确；临时包及时归档。没有通过源过期冒充语义拒绝 |
| 7 | 新旧逐 episode/step 数值与语义对账 | 三臂错误、四类归因、53 缺 owner 步与17差额、共同规则对照、SEARCH 相等、P5 提交、full/fast、场景 CORRECT 差异；不硬编码数字当答案 |
| 8 | 重新导出证据并检查包/源码在整轮未漂移 | 新 scenario/contract/contrast/boundary 矩阵、完整命令退出码日志、JUnit、攻击矩阵、源码/环境身份、保全检查；exports 不代替真实验证 |
| 9 | W1/W3 受影响的联合生产回归、统一入口生产者→消费者正负集成检查、后续验收依赖 | W1 修复顺序/环境/输出域/解释器；W3 正负纠正和受影响状态链重算；最终 receipt/闭包/工程 checkpoint 等由责任窗口按其合同重算，本窗口不代改 |

当前历史核对事实仍为：D0 PUT_BACK P5/AMG/learned 错误 85/102/533；17 步差额来自冷启动规则；53 步缺 owner 的共同先验开发对照使 AMG 102→85；长期提交0，full/fast PUT_BACK差异0，SEARCH 1920步分布一致。动态6场景84输入、83合法三臂步；普通 reference 有长期提交不代表 direct P5 已触发完整机制。这些是对账起点，**不是冻结期望答案**。若生产修复后变化，定位真实因果差异并同时留存两侧原始数据；不能改算法维持数字。

### 5.1 合入后的失效清单与责任边界

源码/诊断绑定改变后，旧 v2/v4/v5 及其 main/attribution verifier 日志、来源正例、攻击矩阵、validation_summary、scenario/contract/contrast/boundary 导出、numeric_reconciliation 的“当前版本证明”资格均不能沿用。旧包作为原分支历史证据仍有效且保持原字节。测试内容若改变，即使未触及401项源码绑定，旧77项结果也不能代表新测试已经运行。若 W1 的最终闭包、回执或工程检查点引用这些来源/产物摘要，必须在**实际统一源码**下按生产者依赖顺序全部重算；不能只刷新 manifest/source 字段。

W3 prepared particle 的 provenance/support/overflow 问题仍有独立复核未解决项，不在本窗口交接文档中宣称已修复；完整 P5、七算子联合与真实执行闭环仍按非空条件判断。地图/因果前缀权限、缺省 owner 先验、特征/预算差异的未决项仍待用户决策。共同类型化解码器、共享 CIAV、最终 PCT 与 guardrail 冻结规则不能擅自重开；0.02 科学阈值不变，不启动 router calibration、新确认集或正式消融。

本次只保全和说明：**来源可信与数值可重算已有局部工程证据；比较公平、完整机制与科学收益尚未建立。**
