# 结构二 W3 R6：电脑 B 独立审核

审核日期：2026-09-12

审核对象：`1bd513f51ab7e54a7290870a5f34b524254d55c6`（远端 `origin/codex/snapshot-w3-r6-20260912`）；父提交为 `281e88894fca527df1d54018b5053469e8c422d5`。

结论：**CHANGES_REQUIRED**。本审核不签收 W3 R6，也不据此宣称窗口三、结构二或科学效果通过。作者新增的 67 项 R6 测试在精确提交上通过，但独立攻击确认地点支持授权可被伪造，另有条件统计 lineage/输入闭包缺口和原生 Windows 字节哈希不可移植问题。

完整交接证据：`docs/reviews/data/pc_b_w3_r6_independent_20260912/`。原始 R6 日志在该目录中保持原文件名和 SHA-256；后续 R7 必须写入新目录/新报告，不能覆盖这里的历史。

## 审核边界与环境

- 独立工作目录：`F:\庞惟\codex\cpswm-w3-r6-review`。
- 分支：`codex/pc-b-w3-r6-review-20260912`，基于上述精确 W3 SHA 建立；没有复用集成工作目录的 `.venv`。
- 环境：Windows 11 23H2（10.0.22631），Git 2.53.0.windows.3，CPython 3.13.5，pytest 9.1.1。解释器为独立工作树的 `.venv\Scripts\python.exe`；元数据枚举为 57 条 distribution 记录/56 个不同名称（editable `cpswm==0.1.0` 出现两次），完整清单和实际导入路径见证据包 `metadata.log`。
- 所有结论绑定该提交的实际源码和实际运行；另一台电脑的报告只作为待核材料。
- 本轮只增加 B 侧审核测试和报告，没有修改生产代码、科学阈值、旧证据或授权状态。

被测提交的 Git tree 为 `0050c04511be8f2268ad80678ee180d06095cea0`。全树 tracked SHA-256 已冻结在该提交的 `docs/collaboration/SNAPSHOT_SCOPE.json`；本审核实际触达的核心源码、夹具和边界测试同时记录 Windows 磁盘字节 SHA-256、Git 规范 LF SHA-256及 LF 对照字节 SHA-256。解释器、`pyproject.toml`、`uv.lock` 和 Git 配置来源也在 `metadata.log` 中逐项记录。

## 五项反例的入口与信任假设

| ID | 公开入口 | 攻击准备 | 信任/能力边界 | R6 实际与状态后果 |
|---|---|---|---|---|
| W3-PCB-01 | public stage | 直接重绑定实例字段 `core.locations` 的一个成员 | 同进程插件/调用者持有 core；未调用正式世界注册 API；不写私有字段 | 接受；外来地点获约 0.0902255639 质量，workspace/semantic state 入库而 habit/embedding 仍是旧支持 |
| W3-PCB-02 | public readout | 先合法 stage，再直接把 `core.locations` 全量重绑定 | 同进程调用者可在 stage/readout 之间改实例字段 | readout 返回；输出支持与当前 `core.locations` 完全不相交，调用本身不写账本或 semantic state |
| W3-PCB-03 | public stage | 合法父批次和 transition 后直接全量重绑定支持 | 同进程调用者可跨代改实例字段 | 子批次接受；records 从 2 增至 4，新 marginal 全落外来支持；攻击调用期间 ledger head 不变 |
| W3-PCB-04 | public stage | 仅构造 schema-valid statistic/receipt，自洽重算 statistic ref | 不可信或有缺陷的 prepared-input 生产者；不改 core 状态 | cluster 错配接受并进入 record/input body/semantic identity；ledger head 不变 |
| W3-PCB-05 | public stage | 仅在 caller-owned statistics 映射加入未引用条目 | 不可信或有缺陷的 prepared-input 生产者；不改 core 状态 | 接受；额外项不进 records，却进入 input body 并改变 semantic identity；ledger head 不变 |

前三项虽然改的是无下划线的可访问字段，但不是“纯外部 payload 攻击”，本报告不把它们夸大为远程输入边界。测试只读取 `_habit._locations`、`_embeddings` 等私有状态作为旁证，从未写入这些私有字段。后两项才是不修改 core 状态、只经公开 prepared-input 接口提交自洽输入的攻击。

显式合法正例 `test_legal_prepared_input_control_is_preserved` 保持同一 public stage/readout 成功、原支持不变、总质量为 1。五项反例的函数名与输入语义未改；逐项 before/pre-attack/after、input bodies、record cluster、ledger head、semantic identity 和 marginal 原始 JSON 位于 `logs/five-case-observations-r6.json`。

## 发现 1：[P1 / W3-2 blocker] 地点授权源可重绑定，跨代可切换到全外来支持

`PrototypeSystemCore.__init__` 在 `src/cpswm/system/prototype_spine.py:1018` 把构造时支持保存为普通公开属性 `self.locations`，没有不可变锚点、版本或内容哈希。公开入口 `stage_prepared_particle_candidates` 又在同文件 `:2676` 直接把当前可重绑定字段作为 `allowed_locations`。`NativeParticleWorkspace.advance` 在 `src/cpswm/system/structure_two_particle_workspace.py:135-137` 只检查这个传入集合自身非空且无重复，并在 `:229-230` 让条件统计与同一个可伪造值比较。`:2694-2711` 的生产绑定检查只核对 workspace 实例和方法身份，不核对世界支持内容。

独立测试确认：

1. 将一个构造时地点替换成外来 UUID 后，公开 stage 没有拒绝；外来地点获得约 `0.0902255639` 后验质量。
2. 首批使用真实支持成功后，执行下一次 transition，再把 `core.locations` 全部换成外来 UUID；`step=1` 子粒子仍被接受，边缘分布全部落在外来支持。
3. 此时 `core._habit._locations` 和 `core._embeddings` 仍保持构造时支持，证明运行时内部已经分裂成两个世界支持，而不是经过了注册扩展。
4. 正常入库后仅重绑定 `core.locations`，`prepared_particle_location_marginal`（`prototype_spine.py:2685-2692`）也不会判 stale；它会返回与当前 `core.locations` 完全不相交的旧支持。

这直接否定 R6 报告中“绑定本运行既有注册支持、无动态扩展授权”的 W3-2 签收结论。建议把构造时支持绑定为不可变锚点或 support-version，并在 stage、父子延续和 readout 三处同时核对；habit、embeddings、统计与粒子记录应共享同一版本。

## 发现 2：[P2] 条件统计 evidence cluster 未绑定 receipt lineage

`ConditionalAnalyticState.evidence_cluster_ids` 在 `structure_two_particle_workspace.py:48-49` 只检查自身去重。`advance` 没有要求该字段与 `receipt.proposal.evidence_cluster_id`、父统计或真实 history cluster 一致。方法合同在 `structure_two_selected_method.py:525` 将原子单元声明为 `evidence_cluster_statistic_bundle`，但当前实现没有闭合这条关系。

B 侧将首个统计的 cluster 改为随机外来 UUID，并同步重算真实 `statistic_state_ref`；公开 stage 接受并持久化了 cluster 不一致的记录。建议至少要求每个统计的 cluster 谱系与本批 receipt cluster 以及父子 lineage 满足明确合同；若空 tuple 有合法语义，也应显式区分“无观测贡献”与“未绑定”。

## 发现 3：[P2] 未被 receipt 引用的统计可进入持久化语义状态

`structure_two_particle_workspace.py:132-147` 克隆并哈希整个 `statistics` 字典，但 `:224-230` 只验证 receipt 实际引用的条目；随后 `:257-263` 将整个字典写入 `input_bodies`。`structure_two_semantic_identity.py:293` 和 `:309-315` 又把完整 body 纳入语义状态。

B 侧加入一个没有任何 receipt 引用、包含全外来地点的额外统计对象后，stage 仍接受。它不进入 `records`，却进入 `input_bodies`，其 particle ID 和外来地点会改变重放指纹及 semantic memory。建议在生成 fingerprint 前要求：

```text
set(statistics) == {receipt.proposal.proposed_state.particle_id for receipt in receipts}
```

## 发现 4：[P2 / portability] 干净 Windows checkout 会破坏原始字节哈希验收

本机 Git 的 `core.autocrlf=true` 来自 Codex 运行时 Git 配置，仓库没有 `.gitattributes`。受绑定文本在 Git 中为 LF，但正常 Windows checkout 为 CRLF（`git ls-files --eol` 显示 `i/lf w/crlf`）。因此提交内容本身正确，磁盘原始字节 SHA-256 却不同。

报告列出的 affected 50 实跑结果为 `31 passed / 9 failed / 10 errors`：

- 其中 7 个失败由 LF→CRLF 后的原始字节哈希不一致直接触发；
- 在同一 SHA、同一 Python/依赖、仅以 `core.autocrlf=false` 建立的 LF 对照 checkout 中，`selected_method` 与 `neural_amortized` 共 15 项全部通过，确认这是 EOL 可移植性问题而非这些文件的 Git 内容漂移；
- 其余 2 个失败和 10 个 setup error 由下述神经模型工件缺失触发。

建议用 `.gitattributes` 固定需按原始字节绑定的文本为 LF，或把合同改成显式的跨平台规范化哈希；不应要求 Windows 用户依赖未记录的个人 Git 配置。

## 证据完整性 BLOCK

R6 报告引用的 `docs/reviews/data/w3_repair_r6_20260912T084200Z/final_results_summary.json`、`r6_final_incremental.patch`、`final_source/manifest.json` 等不在该提交中。`docs/collaboration/SNAPSHOT_SCOPE.json` 也明确写明：生成的审核数据只在完整传输归档中。因此仅靠 Git 无法独立验证报告声称的 647/67/50 各组原始退出结果，也无法从父提交单独重建“R6 只改三个生产文件和一个测试文件”的增量。

仓库还缺少：

`artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json`

合同预期文件 SHA-256 为 `5be8a0c5c87b2272049ed6e283e63feab12bcaa97b1f7b91ecaec69ad8986478`，模型内容 hash 为 `a35f06274ac702e7173b1135ffdb784a9dfdb5a1369917240e59af637f08b2bf`。必须从电脑 A 的原始证据/工件包取得，先落 `F:\庞惟\dataset` 并校验 manifest；不能由 B 临时重生成一个替代模型来制造通过。

## 正向复核结果

- `tests/test_structure_two_w3_round6_prepared_boundary.py`：`67 passed`。这支持作者已覆盖的 posterior 拒绝、地点参数攻击、极端数值、事务恢复和合法重试路径，但不覆盖上述 B 侧攻击。
- W3 快照自带的 7 个专项文件（native bundle/particles、operator/revision acceptance、R5 boundaries、R6 boundaries、supplement）合计 `306 passed, 10 warnings`，耗时 868.79 秒。警告均来自故意构造的畸形 Pydantic 输入；没有把警告改成跳过或静默通过。
- 上一轮独立探针 SHA-256 `148D80B9DA238BEE69444E63E939507C03BAA727A5F3B378769E7B7F5E27FF4C` 在精确 W3 SHA 重跑：control 返回且总质量 1；foreign location、foreign posterior、weight overflow 均明确拒绝且状态/账本/默认行动不变；alpha overflow 合法返回且总质量 1。脚本退出 0 只代表采集完成，本结论来自逐字段检查输出。
- W3-1 的原生入口确实明确拒绝 native posterior projection，也拒绝 raw likelihood 夹带 posterior source；该入口仍明确标为 `explicit_prepared_inputs_not_calibrated`。
- W3-3 的 Fraction/Decimal 对齐、稳定 α 读出与派生总值拒绝未发现新的主体实现错误；尚未验证大粒子规模性能预算。

## 实际命令结果与本地证据

| 范围 | 结果 | 本地证据 SHA-256 |
|---|---:|---|
| R6 新增边界测试 | 67 passed | `B584980479DBE08C84217AB104FD8C15F0597281AC69D1EAAAF6214768C1DFB5` |
| W3 快照 7 文件专项组 | 306 passed, 10 warnings | `BB2232EA8B337686984C4FA1BBAADC0BC0E698521A70E090A6FCCF848911D96E` |
| affected 50 | 31 passed, 9 failed, 10 errors | `20FC21635750C0CDDD2AB530D0EF98BDF044AE23D62942E925B9DD5EFEA936E5` |
| LF 对照定向组 | 15 passed | `2A407CD7A90F525D64C384D66DB019AD1BC83F07E9FA29D4F7C8EBEFD1FDFA63` |
| 上一轮独立探针输出 | 字段复核符合上文 | `30DEE28C08CBC514B90F42E1D76C4F427314583B46FAC13CF7C817696D8D1CA1` |
| B 侧新增对抗测试 | 5 failed（均为预期应拒绝但实际接受/读出） | `301F3D4F09BD4C6D207B9EB6BB5DDDD602C1F9C54D1D42CAFF84413590679858` |

上表最后一行是加显式 control 之前的 R6 原始历史，文件保持不变。当前审核测试复核为 `1 passed, 5 failed`；合法 control 通过，五项原反例仍因 `DID NOT RAISE` 失败。新日志、逐项状态 JSON、命令、退出码和最终文件 manifest 均在上述证据目录，不能反向覆盖原始日志。

原始日志仍保留在原 `output/` 目录，同时逐字节复制到可跟踪的证据目录 `docs/reviews/data/pc_b_w3_r6_independent_20260912/logs/`。完整 argv、cwd、退出码、日志映射、LF worktree 创建命令及元数据采集命令见 `COMMANDS.md`；最终 `manifest.sha256` 可验证交付副本。

## 签收条件

1. 修复并新增回归：构造支持重绑定（首批和父链）、入库后支持重绑定 readout、cluster lineage 错配、未引用额外统计。
2. 解决 Windows EOL 哈希合同，并在默认 Windows checkout 和 LF/POSIX checkout 各复核一次。
3. 提供原始 R6 证据目录和缺失神经模型工件，核对 manifest/hash 后重跑 affected 50。
4. 发布包含修复的全新精确 SHA；旧审核随源码变化失效，B 必须绑定新 SHA 重新执行。
