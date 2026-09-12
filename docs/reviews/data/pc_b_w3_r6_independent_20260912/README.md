# PC-B W3 R6 独立审核证据包

本目录冻结电脑 B 在 2026-09-12 对 W3 R6 的独立审核输入、命令、原始输出与解释边界。它是历史证据，不能被后续 R7 结果覆盖或改写。

## 被测对象

- W3 R6 完整提交：`1bd513f51ab7e54a7290870a5f34b524254d55c6`
- W3 R6 父提交：`281e88894fca527df1d54018b5053469e8c422d5`
- W3 R6 Git tree：`0050c04511be8f2268ad80678ee180d06095cea0`
- 远端冻结引用：`origin/codex/snapshot-w3-r6-20260912`
- W1 静态审核提交：`b6202bec015679461b06056571bd47a5446045b8`
- W1 父提交：`f5089d94ba217b377f88067bc36fdb976e12a4cf`
- W1 Git tree：`1a1d384fbf1ddf7380dc80b8f1b388b355511337`

W3 的完整 tracked 文件摘要已由该提交中的 `docs/collaboration/SNAPSHOT_SCOPE.json` 冻结。本目录的 `metadata.log` 另记录实际 Windows 工作树字节摘要、LF 对照摘要、解释器、依赖和 Git 换行状态。

## 信任边界

五项反例的被测调用入口均是公开的 `PrototypeSystemCore.stage_prepared_particle_candidates` 或 `prepared_particle_location_marginal`，但准备攻击的能力不相同：

1. 前三项先直接重绑定实例字段 `core.locations`，再调用公开入口。该字段虽无下划线且可公开访问，但重绑定不是通过正式世界注册/mutator API；因此这三项对应同进程扩展、插件或持有 core 实例的调用方，不应描述成纯序列化外部输入攻击。测试只读取 `_habit._locations` 和 `_embeddings` 作为分裂世界的旁证，没有写入这两个私有字段。
2. 后两项不修改 core 内部状态，只构造 schema-valid 的 prepared-input DTO/映射后调用公开 stage；它们对应不可信或可能有缺陷的上游候选生产者。
3. 所有五项都要求公开边界 fail closed。pytest 的 `FAILED` 表示“预期拒绝没有发生”，不是测试基础设施失败；对应安全/一致性结论为 `CONFIRMED_OPEN`。

## 合法正例

提交的测试文件保留一项显式合法 control：原始 `candidates(core)` 经公开 stage/readout 成功，地点支持不变，总质量为 1。五项反例名称和语义未改变。原始 R6 运行日志仍保留为 `logs/independent-adversarial.log`（当时只有五项反例，`5 failed`）；新增 control 后的复核运行另存新日志，不覆盖原文件。

R6 自带的 67 项边界正向/拒绝/重试测试、W3 七文件 306 项专项组和旧独立 probe 也原样保留。它们证明合法正路仍存在，但不关闭本审核发现的五项反例。

## 文件说明

- `COMMANDS.md`：实际测试 argv、退出码、对应原始日志和复现顺序。
- `case_results.json`：五项反例逐项入口、前提、信任假设、期望、实际与状态后果。
- `collect_metadata.ps1` 与 `metadata.log`：可重复的环境、源码摘要、W1 Git-object 静态核对及换行对照。
- `w3_five_case_observations.py` 与对应 JSON：逐项采集调用是否接受以及 workspace/ledger/semantic/marginal 状态后果。
- `logs/`：未编辑的历史 stdout/stderr 或 JSON 输出副本。
- `manifest.sha256`：本目录所有交付文件的 SHA-256；在最终提交前生成。

本交接只增加审核报告、审核测试和证据，不修改生产代码、科学阈值、旧 R6 日志或共享集成分支。
