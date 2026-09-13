# PC-A 对 PC-B R6 / R7 候选五反例的交叉复核

日期：2026-09-12。结论：**CHANGES_REQUIRED；五项在两版均独立复现，不能签收这些边界。** 本次只审查，不改生产算法，不合并其他分支。

## 版本与交接真实性

- 共享集成 base：`bdec3ee21b7db361e390496d97ff2eb30390dc6c`，分支 `codex/dual-pc-handoff-20260912`。
- B 原始交付：`9195dd4b3872cbf770bd73ad4c84cca007137c3d`，PR #5；相对 R6 为 21 个审核文件，0 个生产路径改动。manifest 中 20 个载荷文件逐项按 Git blob 校验一致。
- R6 被测：`1bd513f51ab7e54a7290870a5f34b524254d55c6`。
- R7 候选被测：`62870a3a38fce882b25d8d77f1d0526cca6fbc14`。这是明确可复现的代码身份，但本次不把候选预检升级为正式冻结 R7 的完整验收。
- 本人交付分支：`codex/pc-a-crosscheck-pcb-r6-r7-20260912`。

已 fetch 核验上述远端 ref，并读取协作入口、B 原始报告及 R7 候选报告。B 审核已共享；B 交付 commit 不含 STATUS_B，集成分支的旧 STATUS_B 初始化文字不能用于断言 B 尚未开工。建议 B 后续单独同步状态入口。

## 原样复跑结果

| 被测版本 | 合法正例 | 五项反例 | pytest 退出码 |
| --- | --- | --- | --- |
| R6 `1bd513f…` | 1 passed | 5 failed，均未抛出预期 ValueError | 1 |
| R7 候选 `62870a3…` | 1 passed | 5 failed，均未抛出预期 ValueError | 1 |

同一个 macOS Python / 依赖环境、不同独立源码目录，使用 B 原始测试和状态采集器，字节完全一致。禁用插件自动加载、项目 addopts、pytest cacheprovider 和字节码写入；记录实际导入的 prototype_spine 路径、解释器身份、命令、退出码及执行前后源码哈希。两版的已跟踪源码均未变化。失败不是环境导入错误，而是公开调用接受了本应拒绝的状态或输入。

| 项目 | 两版共同观测后果 | 信任边界 |
| --- | --- | --- |
| 01 构造支持重绑定 | 外来地点获得 0.09022556390977444 概率，记录 0 → 2 | 同进程调用者重绑定公开 core.locations |
| 02 stale readout（过期读出） | 返回地点集合与当前 core.locations 完全不相交；本次读取没有新增记录 | 同上 |
| 03 父子跨支持 | 记录 2 → 4，全部有名地点输出均外于构造支持集；仍另有未解析概率 | 同上 |
| 04 cluster lineage（证据簇谱系）错配 | 外来证据簇进入统计记录及保存输入体，记录 0 → 2 | 只修改调用方持有的类型化输入，不改 core |
| 05 未引用 statistic（统计状态）入库 | 保存的 input_bodies 含 1 个未被 receipt 引用的统计；记录仍只有合法引用的 2 个 | 同上 |

控制用例正常接受，保留未知支持。全部采集用例的长期账本 head/hash 未变。01、03、04、05 改变粒子工作区语义状态；02 返回不一致读出。这里的“保存/入库”指工作区记录、input_bodies 和语义状态，**不是已证明写入磁盘长期记忆、污染长期账本或触发错误动作**。

## 源码解释与修复边界

在 R7 `src/cpswm/system/prototype_spine.py:2800`，stage 仍把可重绑定的 `self.locations` 当作 allowed_locations 传入；`prepared_particle_location_marginal` 只检查工作区绑定和 snapshot。工作区的身份/方法绑定不等于构造时地点授权内容的锚定。

在 R7 `src/cpswm/system/structure_two_particle_workspace.py:283` 起，整个 statistics 字典被复制并加入 fingerprint/body；迭代 receipts 时仅检查被引用项。统计地点与本次 allowed_locations 比较，但没有把该支持、父代支持及构造授权绑定为同一条不变量。statistic_state_ref 的自洽内容引用也不等于 evidence_cluster_ids 的来源谱系授权。最后整个 body 保存，允许未引用项进入语义状态。

建议下一轮明确关闭三个修复组，不替换或撤销 R7 已有有效进展：

1. **支持授权与生命周期**：以运行时构造的世界支持为稳定依据，在 stage、readout、父子继承及恢复/重放中检查一致性；若产品需要合法世界扩展，采用明确且可审计的更新契约，不通过普通字段重绑定暗中授权。
2. **统计来源谱系**：校验当前 receipt、真实父代统计和证据簇历史之间的合法关系，不只校验重新封装后自洽的摘要。不能粗暴要求所有历史簇等于当前簇，必须保留合法跨代累计和明确的零增量路径。
3. **输入闭包**：在摘要、重放判定和保存之前验证 receipt 所引用统计与输入键集合的闭包，拒绝孤儿/多余项；失败不得留下工作区、语义指纹或账本副作用。

修复回归须同时覆盖：合法初代和多代累积、未知支持、配对重排、合法恢复/重放；原五反例；完整自洽伪造；拒绝前后状态/摘要/账本不变，以及通过主干消费者读取后的后果。若新实现选择在重绑定时立即拒绝，早期拒绝是合理修复，不应为了让旧测试仅在 stage 内捕获 ValueError 而延后防护；保留旧测试原件作历史证据，新增回归明确区分预期早期拒绝和无关崩溃。

## 对先前结论的更正及限制

- 先前 A 侧 R6 旧四项 prepared probes（预备粒子探针）关闭，仅覆盖固定支持等限定前提；不能外推为构造支持授权、跨代谱系和输入闭包已完整验收。B 的五项揭示了先前矩阵遗漏，本次独立复现支持收紧结论。
- 本次证明 B 五项判断可靠，并证明指定 R7 候选未关闭它们；不能推断后续任何新 SHA 仍然如此。
- 本次 macOS 复现排除了 Windows 换行是这五项现象的必要原因。没有重新执行 Windows 默认 checkout / LF 全套对照，也没有重新运行 R6 缺失工件相关 50 项或 R7 全部 812 项。
- B 的 R7 候选本地 F: 路径预检原件不在该 21 文件交付内；本报告提供的是 A 自己的 R7 原样复跑证据，不冒充校验了 B 那份本地候选目录。
- 首次审核身份查询直接导入 prototype_spine 触发既有循环导入，发生在测试前。按 B fixture 顺序调整本次审核 helper 后两版六项测试均实际执行；详见 preflight_note.md。这不是新增生产修复，也不算五项反例之一。
- B 原始观察脚本顶层硬编码 R6 tested_sha。为保持原样未改动，R7 观察日志该字段仍是 R6；**R7 实际身份以 r7.command.json 的 tested_sha、实际导入路径及源码摘要为准**。summary.json 显式同时保留真实与嵌入标签，不能单用观察日志顶层标签作版本证明。
- 未运行主干/七算子全链路因果消融、公平基线或科学收益实验，不能据此判定完整协作或方法收益。工程边界修复、统一验收和科学结论继续分开记录。

## 证据与命令

- `summary.json`：载荷核验、两版逐项结果、实际后果摘要。
- `r6.command.json` / `r7.command.json`：完整 argv、cwd、解释器、依赖、实际导入和执行前源码摘要；执行后相同。
- `r6.xml` / `r7.xml`：JUnit 逐项结果。
- `r6_tests.stdout.log` / `r7_tests.stdout.log` 及对应 stderr：原始 pytest 日志，退出码 1 如实保留。
- `r6_observations.stdout.log` / `r7_observations.stdout.log` 及对应 stderr：B 原始采集器输出。
- `run_crosscheck.py`：本机执行器；`summarize.py`：独立解析结果与核对 B manifest。脚本内绝对路径忠实记录本次运行，不声称跨机开箱即用。

执行入口：主仓库 `.venv/bin/python run_crosscheck.py r6` 和 `r7`，随后运行 `summarize.py`（脚本相对位置为本目录）。实际 pytest 为 `python -m pytest -o addopts= -q -p no:cacheprovider --junitxml=<相应日志目录> tests/test_structure_two_w3_r6_pc_b_review.py`；具体完整命令和环境以 command.json 为准。执行器返回 0 仅表示采集完成，不表示内部 pytest 通过。

交付仅本人状态与本目录审核材料；无生产改动，无共享集成分支改动，未合并 PR #4/#5。报告自身提交身份由 Git 历史/PR 记录，避免自引用。
