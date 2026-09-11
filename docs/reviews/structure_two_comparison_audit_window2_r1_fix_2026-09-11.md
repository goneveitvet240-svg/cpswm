# 窗口二 R1 修复、完整伪造路径与重新验证

日期：2026-09-11。独立分支 `codex/s2-comparison-audit-window2-20260911`，工作树 `/private/tmp/s2-comparison-audit-window2-20260911`。本轮起始 HEAD 为独立复核过的 `46ba30fcc9a9b52a46647246382f93eb9d06b3ab`，起始工作树干净；没有回退、合并其他窗口或修改原工作区。原实验共同起点仍为 `09eb4d48e1c11082e90ca18332d04333e6b5b47a`。

**窗口二本轮修复完成。** 修复代码与对抗测试提交：`f6d960dad0c6e756b420000792ac242296f12c65`。原有 20 项及新增 6 项测试全部通过（26 项）；其中真实独立 CLI 的完整矩阵包含 1 个合法包通过、21 个攻击包拒绝。主 CLI 的 60 episode / 1920 步三臂新鲜验证也 exit 0 通过。本报告所称完成限于以下 R1 验收矩阵与当前固定源码，不宣称整个系统不存在其他缺陷。

本报告补充原[比较审计](structure_two_comparison_audit_window2_2026-09-11.md)。已完整阅读主工作区的 `structure_two_windows2_3_adversarial_review_2026-09-11.md` 及其 `counterexamples.py`。本轮只修复窗口二的诊断模块与两个 CLI（命令行入口），保留生产算子、窗口一/三实现、历史 benchmark、全局 manifest 与 checkpoint。

## 1. R1 与证据级别

**已证实的缺陷：旧独立归因 `--verify` 只重算归因，未新鲜重放其原始步骤依赖。** 将 1920 步的 `raw_state.p5_readouts.state_counts._committed_events` 全改为 999，再重算 semantic SHA 和 attribution，旧真实命令行仍 exit 0 并输出 `attribution verified`。这证明该成功声明过强；不证明原始三臂数值本身错误。修改前命令、退出码和伪造直方图保存在 [r1_before.json](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/r1_before.json)，原输出在 [r1_before_verify.log](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/r1_before_verify.log)。原伪造目录 `/private/tmp/s2-w2-r1-before-forged` 保留。

| 证据级别 | 本轮含义 | 能否证明 P5 原始状态来自当前算法 |
|---|---|---|
| 原始三臂结果 | 原协议与原配置下的历史结果；本轮新鲜重放逐步对账 | 需要本轮完整重放证据，不能只信旧归因文件 |
| 共同冷启动规则 | 固定已打开数据/支持/公共 decoder 的开发反事实 | 只能诊断该读出规则，不能替换原协议结果 |
| 文件自洽 | `--check-file-consistency` 重算步骤摘要和派生 attribution | 不能；完整 R1 伪造仍可能自洽 |
| 当前源码的新鲜重放一致 | 正式诊断 `--verify` 内部重新训练、验证选择、全量重放并逐字段比较 | 对本地当前源码与固定配置的确定性结果成立 |
| 正式科学验证 | 新注册目标、分布、预算、隔离测试的确认实验 | 本轮未进行，也未授权冻结或打开新测试集 |

新入口的成功状态是 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，同时明确 `formal_scientific_verification=false`、`independent_historical_custody=false`。快速检查只输出 `FILE_CONSISTENCY_ONLY`；默认归因生成只输出 `UNVERIFIED_ATTRIBUTION_WRITTEN`。可重放一致性不等于独立历史托管或对整个生产系统的穷尽安全证明。

## 2. 结论依赖与验证来源

机器清单 [dependency_inventory.json](data/structure_two_comparison_audit_window2_r1_2026-09-11/dependency_inventory.json) 列出轨迹全部 105 种已观察叶字段路径，以及归因/聚合的全部直接读取字段。UUID 字典键归一化为占位符，列表路径表示所有成员；不是只验证这 105 个固定名字，新增/遗漏键也会被全量比较拒绝。

| 重要输出 | 直接依赖 | 当前验证来源 |
|---|---|---|
| episode / step 分组、P5 胜负、各臂错误 | episode_id、tags 全部键值、category、各臂 put_back_error | 按原顺序比较完整 fresh rows，随后比较完整 summary / attribution |
| 冷启动触发与共同均匀读出 | step_id/index、episode_id、observation_age、visible_step_sha256、support、P5/AMG 动作及 AMG 错误、真值 owner habit；selection 中 AMG 参数 | 当前配置重建数据及 AMG 跨步状态；触发只用 `amg_owner_location is None`；原输入/参数先与完整重放比较 |
| 长期提交、快慢状态与 fast 动作一致 | p5_readouts.state_counts 的全部键、P5 put_back、alternative.fast.put_back | 新鲜 P5 系统逐步输出及完整读出/计数比较，不接受调用者直方图 |
| SEARCH 分布、原生排序差异、错误/后悔值 | 各臂 current、search_order、search_error、normalized_search_regret；detected_location；amg_native_search_order | 三臂重放→后验→公共 decoder→提交→真值释放→评分，所有行字段比较 |
| learned 联合头混淆 | learned_joint、derived_cause_event_labels | 重新训练/验证选择与逐步预测，当前数据重建标签 |
| 替代读出指标 | alternative_readouts_development_only 下每种读出的三项指标 | 相同观测/支持/decoder 的开发读出重放 |
| 条件分组 | observation_age、detected_location、P5 habit 全分布、AMG put_back、support[0]、category | 同上；所有条件输入参与重放比较 |
| 在线支持暴露 | future_support_count | 当前数据与前缀审计重新计算 |
| 历史动作链一致 | episode_id、各臂 SEARCH 首选及 PUT_BACK；历史 holdout_episode_metrics | 当前源绑定的原历史文件＋fresh actions；报告历史差异，不将历史答案硬编码到算法 |
| 版本/来源 | 完整 audit 元数据、source_bindings、script_sha256、split ids、selection 等 | 本地源码/配置/历史字节绑定＋内部 fresh run；摘要只做漂移定位 |

归因不直接读取但同样核验：packet/visible 摘要、actor posterior、所有 P5 分布、learned counts、其余 truth、输入/动作相关留存字段。完整步骤的长度、顺序、成员重复、字典键集、值类型和值都参与比较；audit 全部字段和 attribution 全部字段也参与比较。

唯一步骤语义排除是 `arms.*.provenance`（含随机运行身份造成变化的状态/后验/动作摘要）；没有归因结论读取它。`timing.json` 不参与归因真实性验证，硬件与计时只作为独立诊断测量。源码绑定包括两个实际 CLI、所有 `src/**/*.py`、所有 `configs/**/*.json` 和指定历史输入；不证明本地解释器/OS/第三方库未被恶意替换。

## 3. 修复机制与攻击覆盖

输入先读取一次为内存快照；源码绑定在重放前后检查。正式 `--verify` 无调用者参考答案参数、无磁盘结果缓存、无 `verified=true` 证书信任路径。它在同一进程调用主审计 `run_audit`，从当前源码和固定数据配置重做 train、validation 选择、60 个 episode 三臂执行，再派生参考 attribution。先逐字段比较全部语义步骤，再比较 audit 与 attribution。重复 `--bundle` 只是让同一内部新鲜参考验证多个独立快照，避免为每个攻击重新训练；任何一个拒绝使整条批处理 exit 1，合法包仍独立报告通过。

重放异常输出 `VERIFICATION_FAILED`，不会退回快速自洽检查。错误包含失败阶段与路径，例如 `steps[0].raw_state.p5_readouts.state_counts._committed_events`。JSON 重复键和非有限常量也被拒绝。模块内部保留的低层 `verify(output, payload, rows)` 仅是向后兼容的比较函数，文档明确外部自供参考不构成真实性证明；两个真实 CLI 均内部生成参考。

对抗构造器 `tests/structure_two_comparison_audit_adversary.py` 将攻击步骤、summary、semantic SHA 与派生 attribution 同步重算。测试通过真实 Python subprocess 调用生产 CLI，不 mock 重放，也不以旧哈希失败代替语义攻击。归因单独篡改是额外负例，其余为重生成归因的完整路径。

21 条矩阵包括：R1 提交 999；全部快慢计数/分布/动作同步伪造；动作/分数/标签同步伪造；learned joint；真值/原因标签/评分；支持/未来暴露；step 缺失/重复/重排/替换；episode 缺失/重复/重排；输入数据摘要/actor posterior；选择配置；seed 对应 split 成员；源绑定；伪造后重新绑定当前源码；验证版本；归因单独替换；伪造成功回执。另保留真实新鲜包正路径、强弱声明隔离、严格 JSON 和拒绝外部参考参数测试。

实际结果见 [adversarial_matrix.json](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/adversarial_matrix.json) 和 [真实 CLI 日志](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/adversarial_cli.log)。批处理按设计 exit 1；它逐包报告合法包 `CURRENT_SOURCE_FRESH_REPLAY_MATCH`，21 个攻击均 `REJECTED`，没有把批次非零退出误称为合法包失败。R1、重绑定当前源码后的 R1、伪造成功回执三条都定位到 `FRESH_REPLAY_STEP_MISMATCH: steps[0].raw_state.p5_readouts.state_counts._committed_events`。其他攻击分别定位到新鲜步骤内容/顺序/长度、选择结果、split 成员、数据配置来源、验证版本或 attribution 字段。

配置选择攻击的错误最先定位到 `audit.selection.content_sha256`，**该摘要已按攻击者的新参数重算**；这里比较的是本进程新鲜验证选择的参考摘要，不是拿旧摘要检查单字段篡改。seed 不作为 bundle 的独立自由参数：由当前 DATA_CONFIG 固定；测试覆盖该来源替换与其 split 成员替换，没有生成或打开新的种子数据。

另保留与真实 CLI 所拒绝输入逐字节相同的 [当前源码 R1 伪造包](data/structure_two_comparison_audit_window2_r1_2026-09-11/counterexamples/r1_current_source/audit.json)，仅供对抗复现，不能当作诊断结果。其文件摘要及原命令在 [version_and_execution.json](data/structure_two_comparison_audit_window2_r1_2026-09-11/version_and_execution.json)。快速检查该攻击确实 exit 0，但只输出 `FILE_CONSISTENCY_ONLY` / `p5_state_authenticity_verified=false`，见 [日志](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/r1_file_consistency_only.log)。

## 4. 运行、版本与结果

本轮使用项目 `.venv/bin/python`（Python 3.13.5）。新产物目录为 [structure_two_comparison_audit_window2_r1_2026-09-11](data/structure_two_comparison_audit_window2_r1_2026-09-11)，旧目录 `structure_two_comparison_audit_window2_2026-09-11` 原字节保留。新版源绑定按设计拒绝旧合法包及原 R1 包，日志分别为 `evidence/old_bundle_rejected.log` 和 `evidence/r1_old_source_after.log`；没有修改旧 source_bindings 将其修绿。

最终测试日志：[tests_final.log](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/tests_final.log)，测试清单：[test_collection.log](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/test_collection.log)。26 项全部通过，exit 0。ruff check / format（5 个 Python 文件）及诊断模块 mypy 均通过，提交钩子的 ruff 检查也通过。全量生成与主验证分别见 [fresh_generation.log](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/fresh_generation.log)、[main_verify.log](data/structure_two_comparison_audit_window2_r1_2026-09-11/evidence/main_verify.log)；独立归因矩阵在另一进程内部再次完整重放。新包的 398 项来源绑定均已逐一核对为修复提交中的文件字节；提交前生成产物的源码内容与提交后的源码相同。文档/证据提交不在源绑定集合内，不需通过修改旧 bundle 来源字段追随文档 HEAD。

旧包全部 11 个文件与 `46ba30f` 中原字节相同；独立复核报告及反例脚本的只读摘要一并保存在 [preservation_and_review_inputs.json](data/structure_two_comparison_audit_window2_r1_2026-09-11/preservation_and_review_inputs.json)。

新旧数值与语义的完整机器对账见 [old_vs_v2.json](data/structure_two_comparison_audit_window2_r1_2026-09-11/old_vs_v2.json)。新旧语义步骤 SHA 都是 `d32b9d7bd2ff4963d8a71939fe752b260806e8775b692d602ac4588205f70c76`；逐步差异为 null，完整 summary 相等。audit 顶层只变化 `source_bindings` 和 `verification_schema_version`；attribution 只变化 `evidence_level` 与 `script_sha256`。

| 再次核对的结论 | 新鲜生成结果 | 证据 |
|---|---|---|
| 原协议 PUT_BACK | P5 85，AMG 102，learned 533 / 1920 | bundle_v2/audit.json summary；180 个 episode×arm 历史错误对账无差异 |
| 逐步差额 | 17 胜、0 负、85 共同错误、1818 共同正确 | summary.overall.categories；逐行记录 |
| 冷启动规则开发反事实 | 53 个 AMG 无 owner 估计步骤：原错误 53，共同均匀后 36；全批 AMG 错误变为 85 | attribution.common_uniform_when_amg_has_no_owner_estimate，含逐步例子 |
| 差额归因 | 17 步差额全部由该冷启动规则差异解释 | 反事实触发依赖新鲜 AMG 状态，不依赖 P5 胜负或真值筛选 |
| P5 长期提交 | `_committed_events=0` 共 1920 步；完整 P5 与 fast 动作差异 0 | attribution.p5_state_count_histograms / p5_vs_fast_put_back_disagreement_steps |
| SEARCH | 三臂 current 分布相等 1920 步 | summary.search_three_arm_distribution_equal_steps |
| 历史动作链 | 180/180 一致 | attribution.historical_action_chain_checks |

这些数字只在报告中作观察值，验证器没有把 85、102、17、0 或上述 SHA 硬编码为答案。训练、模型选择、阈值与算法均未修改。原 0.008854 改善仍低于注册门槛 0.02，未变成新的科学信号。

**已证实缺陷：** R1 的旧弱入口过度声明，以及原报告登记的 SEARCH/在线支持/比较设计问题。**本批已排除假设：** R1 本身已使原始留存数值或上述冷启动/零长期提交结论错误；当前新鲜重放逐步支持原结论。**样本限制：** 只测原有 60×32 步与已有标签，不外推未测的长期提交、迟到反证或动作反馈能力。**待用户决定：** 下一版目标、数据分布、信息权限和预算；原协议草案保留，没有在修复验证器时擅自实施。

本轮生成附带 1 次重复×固定第 1 条 episode×32 步/臂的计时，仅满足验证重放的独立诊断记录，不替换原报告 3 次×2 条 episode 的成本测量。新 timing.json 记录 macOS 26.4 / arm64、10 个逻辑 CPU、Python 3.13.5、NumPy 2.5.2；沙箱中的 CPU 型号/内存 sysctl 不可用，如实记录 unavailable。范围包括 consume、状态哈希、trace、posterior、decoder，排除训练、数据加载、真值/评分、磁盘与真实机器人观测执行；训练/验证耗时另有一次墙钟记录。没有把零物理观测成本或信息匹配解释为净效用/等算力。

实际运行命令（均在独立工作树；日志目录缩写为 `$E`）：

```sh
cd /private/tmp/s2-comparison-audit-window2-20260911
AUDIT_PY=/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python
R=docs/reviews/data/structure_two_comparison_audit_window2_r1_2026-09-11
E="$R/evidence"
export PYTHONPATH=src

# 修改前在 46ba30f 运行，exit 0（旧源码）；原伪造包事先同步重算全部依赖
"$AUDIT_PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle /private/tmp/s2-w2-r1-before-forged --verify

# 新源码拒绝旧合法包；日志 old_bundle_rejected.log，exit 1
"$AUDIT_PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle docs/reviews/data/structure_two_comparison_audit_window2_2026-09-11 --verify

# 新鲜生成：fresh_generation.log / fresh_attribution_generation.log
"$AUDIT_PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$R/bundle_v2" --timing-repeats 1 --timing-episodes 1
"$AUDIT_PY" apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle "$R/bundle_v2"

# 20 原有 + 新测试；真实独立 CLI 内部重放，正包与同步伪造包同时验证
S2_AUDIT_EVIDENCE_DIR="$E" "$AUDIT_PY" -m pytest -q tests/test_structure_two_comparison_audit.py tests/test_structure_two_comparison_audit_verification.py

# 主 CLI 的合法新鲜重放正路径，日志 main_verify.log
"$AUDIT_PY" apps/evaluation_runner/run_structure_two_comparison_audit.py --output "$R/bundle_v2" --verify --timing-repeats 1 --timing-episodes 1
```

复现时生成命令必须改用新的空目录，生成器拒绝覆盖。测试通过 `S2_AUDIT_BUNDLE=/新目录` 选择该新包；不设 `S2_AUDIT_EVIDENCE_DIR` 时日志写入 pytest 临时目录，不覆盖留存证据。完整攻击构造逻辑在测试 helper 中，批量 CLI 原始输出与每例重算说明会留存在 `evidence/adversarial_cli.log` 和 `evidence/adversarial_matrix.json`。

## 5. 比较设计边界与交接

在线支持集未来信息、公共 detected-location SEARCH 读出、基线信息权限与训练/容量/计算预算差异仍为比较设计问题。本轮没有改变正式基线、搜索预算、0.02 门槛或原已打开测试集，也没有启动 router calibration。原报告的完整结构二能力范围保留；长期记忆、迟到反证、动作影响后续观测等未覆盖能力仍写“未测”。

对窗口一：旧窗口二 bundle 的源码绑定和旧独立 `attribution verified` 成功声明均不能作为新源码的通过证明。旧原始 benchmark 数值无需因此重写。将本轮诊断源码整合到最终组合源码后，必须重新运行主审计到新目录，再运行独立 attribution `--verify`；不能替换旧包里的来源字段。由于新绑定覆盖所有 src/config，合入窗口一/三或任何其他源码变化也会使本轮 v2 包按设计过期。下游若把旧窗口二 audit/attribution/源码摘要作为依赖，必须在最终代码树重算对应证明与派生报告。本轮没有修改或替窗口三重新背书其实现/证据。

精确失效/保留清单（前缀 `docs/reviews/data/structure_two_comparison_audit_window2_2026-09-11/`）：

| 文件 | 交接要求 |
|---|---|
| audit.json | 对当前源码的绑定过期；仅保留历史证据，最终源码重新生成新包 |
| attribution.json、attribution_verification.log | 旧独立通过只代表自洽；不能作为 P5 状态真实性证明，最终包必须完整独立重放 |
| fresh_verification.log、validation.json、diagnostic_tests.log | 是旧版本的执行记录；不冒充当前版本通过，最终树运行新日志/测试 |
| steps.jsonl.gz | 原字节保留；本轮已逐步语义一致，但不能单独承载新的源码来源证明 |
| timing.json、hardware_supplement.json | 保留原范围/机器/重复次数的描述性测量，不作为新版归因通过凭据 |
| baseline_binding_issue.json、truth_barrier_suggestion.patch | 既有独立问题/建议保留；不是 R1 修复，也不因本轮自动解决 |

本轮新包 `.../structure_two_comparison_audit_window2_r1_2026-09-11/bundle_v2/*` 只对本轮记录的源码字节有效。优先整合代码与测试，再在最终组合代码树生成一个新目录、生成归因、执行完整独立验证、运行对抗矩阵，最后更新窗口一使用的最终证明与报告引用。尚未发现或枚举的下游全局证明只按其实际依赖失效，不宣称已替它们全部完成验证。

修复提交中的文件清单：

- `src/cpswm/system/evaluation_operations/structure_two_comparison_audit.py`：快照、严格 JSON、来源绑定与逐字段新鲜比较。
- `apps/evaluation_runner/run_structure_two_comparison_audit.py`：主入口先捕获输入，再运行参考与比较。
- `apps/evaluation_runner/summarize_structure_two_comparison_audit.py`：强验证内部全量重放，弱检查另名，逐包可定位状态。
- `tests/structure_two_comparison_audit_adversary.py`：同步重算依赖的 21 种完整攻击构造。
- `tests/test_structure_two_comparison_audit_verification.py`：真实 CLI 正路径/攻击矩阵及辅助检查。

未覆盖：恶意替换本地执行器或第三方库、敌手控制整个源码树并伪装历史、OS 级竞态/资源耗尽、独立托管与签名认证、未出现的数据能力、正式新分布优越性。源码重放解决当前验证入口的依赖真实性缺口，不能把上述边界抹去。未来评测目标、分布和预算由用户决定；本轮没有冻结这些选择。
