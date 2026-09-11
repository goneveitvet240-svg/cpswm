# 结构二窗口一三项补修与新证据版本（2026-09-11）

本轮起点为已审查的 `91dbdc57968071be29976d1a7b99de51d9288cdd`；开始时分支
`codex/s2-evidence-repair-window1-20260911`、HEAD 和工作树核对一致，工作树干净。
所有修改、复制反例、实验和 Python 3.13.5 验证均在
`/private/tmp/cpswm-s2-evidence-repair-window1` 及其 `.venv` 进行。
独立复核报告和 `counterexamples.py` 从原仓库只读；未修改审查者临时工作树，未合并其他窗口。

本文补充并限定上一轮报告 `structure_two_evidence_repair_window1_2026-09-11.md`。
上一轮 v0.2 五类结果完整重算、11 份 Git 字节吻合、4103bea 失败重放相等、169 项定向测试及
当时检查点当前性通过，仍是被保留的历史事实。新发现是保护机制可被反例绕过，不能据此推断
既有实验已经造假。旧报告关于缓存来源保护和写入保护的概括不能作为本轮修复前的安全保证。

## W1-R1：实际加载代码与来源绑定

根因：原守卫直到 `evidence_versions` 被导入才记录磁盘摘要，无法判断此前已经加载的依赖。
Python 的普通时间戳 pyc 缓存还允许同长度、同 mtime 的新源码与旧字节码同时存在。
两次磁盘摘要相等不能证明实际执行的是磁盘上的实现。

修改前：原独立脚本 `late_import` 和 `stale_pyc` 均实际运行 0.5，却接受对应 0.9 磁盘源码的
真实 P5 `_source_binding`。原始 stdout/stderr、命令、退出码及反例脚本摘要在
`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/before/`。

修复：正式五个 P5 CLI、聚合入口、历史审核入口及 checkpoint 入口先用标准库从原始字节编译
`structure_two_source_bootstrap.py`，再导入任何 `cpswm`。测试启动对应根目录 `conftest.py`。
启动器冻结全量 cpswm Python 源码、apps Python、JSON 配置、环境锁与根测试启动文件；为所有
cpswm 模块安装来源加载器，直接编译捕获的源字节，绝不读取 pyc。提前导入任何 cpswm 模块的
普通进程不能再建立正式身份。来源绑定和最终发布重复核对进程、根路径、实际模块加载器及
冻结内容；动态加载的审核应用辅助模块也从冻结字节编译。正式来源加入
`execution_source.policy=frozen-source-compile-no-pyc@1` 和完整清单摘要。

回归检查真实语义：普通未启动进程、提前导入后改盘、守卫建立后改盘、加载前改盘被拒绝；
合法新进程和合法缓存通过；旧缓存反例仍先由普通进程实测为 0.5，正式入口实际得到 0.9。
验证中及发布后检查前的源码变化会拒绝发布并清理。诊断入口只输出诊断，不发布实验产物。

边界：这是可信本地 Python/标准库和正式入口下的执行来源保护，不是远程证明或独立托管。
不证明解释器、原生扩展、操作系统未被篡改；不防具有任意进程内代码执行权限的攻击者直接改写
守卫本身或函数对象。冻结加载保证使用捕获的 cpswm 源字节；不声称连续监控每一次文件系统事件。

## W1-R2：必需历史覆盖与真实完成状态

根因：原入口只遍历清单；空清单真空通过。数值重放依赖可变展示 ID，改名即可跳过必需执行，
而成功输出仍不变。

修改前：原脚本 `empty_history` 两个真实 CLI 均退出 0；`renamed_history` 保留合法 11 份文件，
重算计数为 0，仍输出重放成功。对应原始日志在 `before/`，没有仅靠报告推断漏洞。

修复：两个入口各自调用同一必需映射核验，严格匹配已审查 Git 对象中完整清单，固定每一条
ID、完整提交、原路径、保存路径与生命周期。固定参照不在调用者可一起修改的清单或相容报告中。
数值执行按提交/原路径/生命周期元组选择。完成守卫要求必需的 4103bea 行真实重算并全字段相等，
才能输出“1 required full failed replay completed”。聚合 `--verify-history` 也执行此完整重放。

报告分别列出 Git 字节核验数量、来源可恢复数量、数值重算数量；来源检查模式允许不重算，
但显式报告 0，不声称失败重放完成。正式 `--verify` 总是重新执行必需重放后比较报告。
18 个真实 CLI 攻击同时修改清单和相容报告，覆盖空、删项、改名、替换提交/原路径/副本路径/
生命周期、重复和冲突。另检查合法来源报告没有执行重算时不能获得完成声明。

历史边界不变：11 份副本保持原字节；4103bea 失败重放要求全量重算相等；最早版本缺少
`RegimeStage` 而无法导入，仍记录阻塞，未借用新依赖。其余来源可恢复不等于已经数值重算。
本地 Git 记录不证明首次执行、首次未见、可信时间或独立托管。
历史快照只提取对应 Git 的 src/configs/环境锁；本轮标准库加载器仅控制这些字节的加载，
不复制当前 cpswm 依赖进去。数值重放在本轮本地 Python 环境执行，不额外声称恢复了过去的独立执行环境。

## W1-R3：最终安全发布

根因：原路径检查只能看到路径，`write_text` 随后截断已有 inode。current 目录的硬链接可与
历史文件共享 inode，因此通过路径检查仍能覆写历史字节；检查与写入之间也有替换窗口。

修改前：原脚本 `hardlink` 实测链接计数为 2，路径检查通过，历史字节被覆盖；复制反例只破坏
自己的隔离样本，仓库历史副本没有被覆盖。

修复：五个 CLI 与聚合生成器统一调用 `publish_verified_json`。完整校验冻结后的 JSON 值，
序列化字节与校验值一致；写入全新隐藏临时 inode，fsync 后通过不覆盖的原子 link 发布。
逐层持有目录描述符并拒绝符号链接，发布前后核对父目录身份、目标 inode 和来源状态。
现有目标一律拒绝，即使内容相同；不会截断已有硬链接。验证、发布或捕获到的中断失败时清理
自己的临时文件和已链接目标；不打印成功。昂贵计算前的路径检查只用于尽早报错，最终写入仍保护。

回归使用真实历史失败样本，调用正式共用发布实现，比较攻击前后字节摘要。覆盖新建、已有文件、
硬链接、文件/目录符号链接、路径逃逸、验证失败、发布失败、中断、最终 link 时替换目标为
符号链接/硬链接、替换父目录、执行期来源变化、调用方在验证后改变原 payload。
六个实际生成入口也分别拒绝现有硬链接目标。

边界：批量五类结果逐件验证发布，不声称全批次原子事务；若批量中断，已完成单件保留，不能
把部分完成记作五类全通过。SIGKILL/断电可能留下隐藏 `.partial-*`；它不是正式 JSON 产物，
不会被当作完成回执。发布后的恶意同权限修改仍须由消费者完整验证检出；本地磁盘不是不可变托管。

## 版本、失效与交接

- 科学协议、阈值、种子、正式基线、七算子和动作接线不改；结果证据版本从 0.2 独立升级到 0.3。
- 新五类路径：`benchmarks/structure_two/evidence_repair_supplement_2026_09_11/current_v0_3/structure_two_p5_{three_arm_death_test,readout_posthoc_diagnostic,debt_replay_confirmation,readout_prior_factorial,unseen_d0_holdout}_v0_3.json`。
- 新历史报告：同一补修目录的 `historical_source_audit_v0_2.json`；旧报告原字节保留。
- 新 checkpoint/审计回执/原生十条命令日志：`benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/`。
- P0 当前消费者仍使用 `benchmarks/p0_checkpoint/content_manifest_v0_3.json`；旧版原字节另存
  `evidence_repair_supplement_2026_09_11/p0_reviewed_manifest_snapshot.json`。
- 原 v0.2 五类、11 份历史、旧历史报告、旧 checkpoint 与回执逐字节核对已审查提交，完整列表见
  `preserved_reviewed_evidence.json`。它们仍可作为对应历史源码版本证据，不能手改来源摘要升级为当前。
- 源码变更使原 v0.2 不再对应本轮源码；P0、审计回执和 checkpoint 必须随后再生。
  新来源身份额外覆盖 apps 和正式测试启动器；这些入口变化同样使新来源身份失效。
- 可能与窗口二/三重叠：五个 `src/cpswm/system/evaluation_operations/structure_two_p5_*.py`、对应
  CLI、生产装配消费者、P0 与 checkpoint/audit 入口、根 `conftest.py`。本轮五个 P5 源文件仅改
  默认输出路径及来源绑定字段，整合时保留其他窗口算法修改并重新计算来源，不复制旧摘要。
- 新增共用模块为 `structure_two_evidence_publication.py`、stdlib 启动器、正式诊断入口和补修测试；
  修改证据版本模块、历史两个入口、五个 CLI、P0/审计/checkpoint 路径及对应测试。

所有新结果继续 `confirmatory=false`、`previously_unseen_established=false`、
`first_execution_established=false`、`independent_custody_established=false`。D0 是开启后重放。
工程绿色不赋予科学通过；没有新确认集、路由器训练或科学选择待用户授权。

## 验证记录与复现命令

执行位置始终为本分支实际工作树。原始命令、开始/结束、退出码、stdout/stderr 摘要及 gzip
原始日志在补修目录 `validation_logs/commands.jsonl`。失败尝试也保留，不归入成功计数。
首轮新增测试 41 passed / 3 failed；其中两项是攻击输入没有真正替换相同原路径，另一项是聚合
入口局部 import 作用域错误，已修复。随后当时的 47 项补修测试全部通过，继续补齐历史来源
零重算和旧 v0.2 拒绝测试。单独启动 xdist 时一次重复自动加载失败（未收集测试）；随后使用
项目审计相同的 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 加显式 xdist 启动，不替换导入或关闭断言。

旧 169 项所对应套件与新增套件先整体运行；此时 P0 和新 checkpoint 尚未生成，其依赖当前性
失败单独记录。不会通过删除这些测试或改断言解决依赖次序：完成新证据链后再次整体运行。

```bash
# 五类真实生成；每件在发布前还需完整独立重算验证
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --generate-current
# 五类再一次新鲜全量核验
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-current
# 历史报告生成及两个独立入口的必需重放
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py \
  --recompute-first-failure --recompute-failed-replay \
  --output benchmarks/structure_two/evidence_repair_supplement_2026_09_11/historical_source_audit_v0_2.json
.venv/bin/python apps/evaluation_runner/audit_structure_two_evidence_history.py \
  --verify benchmarks/structure_two/evidence_repair_supplement_2026_09_11/historical_source_audit_v0_2.json
.venv/bin/python apps/evaluation_runner/run_structure_two_evidence_repair.py --verify-history
# 当前兼容性审计 -> P0 -> 完整原生工程审计矩阵 -> 强制 fresh checkpoint
.venv/bin/python apps/evaluation_runner/audit_structure_two_world_source_bundle_v0_5.py
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py
.venv/bin/python apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py
# fresh 生成完成后的当前性核验
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py \
  --verify benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2/engineering_checkpoint.json \
  --no-fresh-recomputation
```

原独立脚本五种模式已在补修源码上再执行，原始输出在 `after_original_attacks/`：

| 原反例 | 补修后真实拒绝 |
|---|---|
| late_import | exit 1，未正式启动的普通进程无法取得来源身份 |
| stale_pyc | exit 1，同上；新增正式入口语义测试另证旧缓存无法影响正式执行 |
| empty_history | 脚本外层只是收集输出，exit 0；其中两个真实历史 CLI 均 exit 1，固定映射拒绝 |
| renamed_history | exit 1，改名清单在任何来源/数值成功声明前拒绝 |
| hardlink | exit 1，已有目标拒绝，未执行截断写入 |

预封存定向套件完成 222 项：211 passed、11 failed、0 skipped、0 xfailed。
其中 1 项是旧 P0 不再当前；10 项依赖尚未生成的新检查点/回执。全部 53 项补修测试通过。
此次双重 `-q` 隐藏汇总计数，计数取原始 pytest 进度标记，11 个失败名称及详细异常完整保留。
后续原生审计将显式 `-o addopts=` 消除重复静默参数，并使用 xdist `--dist=worksteal` 分散
昂贵测试；只调整报告和调度，测试选择、断言及重算不变。

其余正式统计与最终结果在完成命令后记录，不以旧的 169/3855 充当本轮结果。

## 覆盖范围与最终整合要求

本轮覆盖上述明确来源、历史覆盖和发布攻击类别，不声称整个 CPSWM 已被穷尽审计。
可信本地工具链、Git 对象和操作系统是明确边界；没有另建签名或证书体系。

三个窗口最终整合后，必须在统一源码和匹配虚拟环境上重新生成五类当前产物、历史来源审核、
P0 清单、真实审计回执和强制 fresh engineering checkpoint，随后验证当前性及对抗回归。
任何被绑定输入变化都必须重验受影响层。本分支通过不能自动继承，不能把三个分支各自的绿色
结果拼成整体通过。
