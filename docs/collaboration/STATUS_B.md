# 电脑 B 状态

## B1-W3 五项边界临时接管：开工登记

- 更新时间：2026-09-12T21:59:59+08:00（Asia/Shanghai）。
- 任务：在用户明确授权的有限范围内修复 `W3-PCB-01` 至 `W3-PCB-05`，随后执行扩展状态机回归、真实七算子协作诊断、W1 最新版本独立复现及 W2 公平性验收准备。
- 本人分支：`codex/pc-b-w3-five-boundaries-fix-20260912`。
- 工作目录：`F:\庞惟\codex\cpswm-w3-five-boundaries-fix-20260912`。
- base SHA / 当前实际被测源码：`62870a3a38fce882b25d8d77f1d0526cca6fbc14`，来自远端 `codex/pc-a-w3-backbone-r7-20260912`。
- 开工远端核验：`git fetch origin +refs/heads/*:refs/remotes/origin/* --prune --verbose` 成功；集成 SHA `bdec3ee21b7db361e390496d97ff2eb30390dc6c`、B 原审核 `9195dd4b3872cbf770bd73ad4c84cca007137c3d`、A 五项交叉复核 `1b2b31e88c47fc232a7b4e2dcec56c02c9ac9636`、W1 `21870b0bcd6c23d43518a27fcc1c4b538b3912b7`、W2 `329787241996631a6abb4fcd3b12d2c13a135777` 均与任务登记一致；远端无 R7 冻结 tag/snapshot。
- 所有权核对：A 的五项交叉复核分支只含 `STATUS_A`、报告、测试日志和采集工具，没有生产修复；R7 分支已交付并请求 B 源绑定复核。依据用户本次临时授权，本分支是五项边界修复的唯一写入分支。A 继续拥有完整默认联合主干、七算子主干实现和集成职责。
- 允许生产路径：仅五项缺陷直接相关的 `src/cpswm/system/prototype_spine.py`、`src/cpswm/system/structure_two_particle_workspace.py` 及确有必要的关联类型；另可增加 PC-B 专属测试、审计工具、证据和本文件。
- 禁止范围：W1 生产编排器与执行身份保护、A 的 `STATUS_A`、A 维护的 `TASK_BOARD`、共享集成分支、完整默认联合主干功能、科学指标/阈值/先验/数据权限/预算/模型选择规则。
- 修前身份：R6 `1bd513f51ab7e54a7290870a5f34b524254d55c6` 与 R7 候选 `62870a3a38fce882b25d8d77f1d0526cca6fbc14` 均已由 A/B 独立复现为合法正例 PASS、五项反例 OPEN（`1 passed / 5 failed`）。本分支仍将原样重跑并保存新的修前日志，不以历史运行替代。
- 环境：Windows 11 10.0.22631，Git 2.53.0.windows.3，`core.autocrlf=true`；WSL 命令存在但当前没有已安装发行版，因此现阶段只能声明原生 Windows 验证。将从本分支锁文件重建独立环境并记录实际解释器、依赖、导入路径和 EOL。
- 计划证据：`docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/`；修前日志、修后矩阵、JUnit、命令、SHA-256 和耗时分别保留。
- 交付边界：本人只报告“修复方工程回归通过”；独立验收仍交给 A 或另一独立环境。W1 审计、W2 工具与 W3 修复保持可分别审核的提交范围，不自动合并 PR #3/#4/#5/#6。
- 下一步：重建环境并原样复现六项；按支持生命周期、统计证据簇谱系、输入集合闭包三个最小批次提交；随后扩大状态机、三 hash seed、812 回归和协作/公平性检查。

## 更新：五项修复、复测与当前阻塞

- 五项生产修复为 `17220e6e22de81508a2e4e34dce81b8dccc9e44f`；其后证据提交 `5605d5446ff151e4b35586c819c2e48b567f56b0`；锁回归修复为 `ccf2cf0`。
- 原六项修后 `6/6`；增强矩阵在 seed `0/1/8675309` 各 `47/47`；合法正例保留。逐项机器矩阵和覆盖索引位于 `docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/BOUNDARY_MATRIX.json` 与 `COVERAGE_INDEX.md`。
- 首轮 812 证据保留：CRLF `800/12`、LF `804/8`；均为正式失败，见 `post_fix/`。CRLF 的九项字节身份前提和 LF 的五项 Windows 路径表示前提均未误标为代码通过。
- `ccf2cf0` 在独立锁三轮均 `3/3`，新增防绕过 `12/12`，但新 CRLF exact-812 仍 `800/12`；三个锁节点在 `-n 4` 下仍超 1 秒。因此当前只可写“局部锁对照通过、完整并行回归未关闭”。
- 七算子、W1、W2 的报告分别位于本 W3 目录的 `seven_operator/`、`w1_audit/`、`w2_audit/`；默认完整主干、W1 Linux 复现、W2 统一公平验收仍为阻塞。
- 远端最近已核验 SHA 为 `c4eb20b045edb9dc34937f2b9d1038475a02e74a`；本地后续提交待网络恢复推送并再次 `ls-remote` 核验。不得自动合并或自签独立验收。

## 首次同步节点：修前基线已固化

- 草稿 PR：<https://github.com/goneveitvet240-svg/cpswm/pull/7>；开工提交 `49f80b2a3503b44ebfed2c86897fc8c78bc28fe3` 已推送。
- 新环境：由本机独立 CPython 3.13.5 创建本工作树 `.venv`，安装本分支 `.[dev]`；实际 pytest 9.1.1。完整安装输出保存在修复证据目录，不复用其他工作树的虚拟环境。
- 修前运行：在 R7 交付 SHA `62870a3a38fce882b25d8d77f1d0526cca6fbc14` 上原样执行 PC-B 六项文件，得到 `1 passed / 5 failed`、退出码 1；日志与 JUnit 分别为 `baseline_r7_five_seed0.log` 和 `baseline_r7_five_seed0.junit.xml`。
- 历史隔离：R6 原始报告、测试、命令、日志、观察 JSON 和校验清单从提交 `9195dd4b3872cbf770bd73ad4c84cca007137c3d` 原样纳入本分支；它们位于 `docs/reviews/data/pc_b_w3_r6_independent_20260912/`，不会被 R7/修后输出覆盖。
- 当前结论：五个缺口均在最新交付源码上独立复现；合法公开入口正例仍通过。尚未修改生产代码。
