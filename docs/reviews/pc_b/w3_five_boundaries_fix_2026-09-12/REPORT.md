# PC-B W3 五项边界修复交接报告

## 被测对象与结论

- 分支：`codex/pc-b-w3-five-boundaries-fix-20260912`；PR #7。
- R7 基线：`62870a3a38fce882b25d8d77f1d0526cca6fbc14`；历史 R6 证据保存在 `docs/reviews/data/pc_b_w3_r6_independent_20260912/`，未被覆盖。
- 五项修复：`17220e6e22de81508a2e4e34dce81b8dccc9e44f`；锁回归修复：`ccf2cf0`。
- 本文只能报告修复方工程证据，不能自签独立验收、默认完整联合能力、公平比较、统一验收或科学收益。

R6 与 R7 的原六项均为合法正例通过、五项攻击被接受（`1 passed / 5 failed`）。修复后原六项为 `6/6`，增强矩阵在 `PYTHONHASHSEED=0/1/8675309` 各为 `47/47`；其中保留合法初代/多代、未知质量、配对重排和重复调用。逐项入口、信任边界、状态后果、生产者/消费者、R6/R7/修后证据见 `BOUNDARY_MATRIX.json`；覆盖映射见 `COVERAGE_INDEX.md`。

## 锁回归与完整集

`2350602` 的首轮 exact-812 在 CRLF 为 `800 passed / 12 failed`，LF 为 `804 passed / 8 failed`。首轮 CRLF 12 项中的 9 项为冻结原始字节的 CRLF 身份前提，3 项为锁 deadline 回归；失败原件及 Windows/LF 对照在 `post_fix/`，不可覆盖。

锁修复将十个工作区方法的完整加载代码/源码编译核验固定为 import-time anchor；热路径每次仍核验工作区对象和精确类型、实例 shadow、类声明及函数对象、代码指纹、磁盘整文件 SHA、locations 和 world support。独立三轮锁测试均 `3/3`，新增防绕过为 `12/12`，受影响集为 `129/129`；新冻结工作树上的原六项 `6/6`、三 seed 矩阵 `47/47`。

但新的 CRLF exact-812（`ccf2cf0`）仍为 **`800 passed / 12 failed / 0 error / 0 skipped`**，其中三个锁节点在 `-n 4` 的完整并行环境分别为 `1.687/1.825/1.936s`，仍超出 1 秒合同；其他九项仍是既有 CRLF 原始字节/路径前提。该轮完整日志、JUnit、命令和冻结源码核验位于 `post_lock/`。所以锁问题在低负载对照关闭、在完整并行 812 **未关闭**；本分支当前不得报告完整工程回归通过。

## 环境与平台

Windows 11 `10.0.22631`，CPython `3.13.5`，pytest `9.1.1`，pytest-xdist `3.8.0`，Git `core.autocrlf=true`；无可用 WSL。CRLF/LF 的实际加载路径、解释器、依赖、Git tree、字节 SHA 和命令均写入 `post_fix/repair_environment_metadata_*_test_harness.json` 与每项 `*.command.json`。初始依赖安装的外层命令/退出码未被捕获，`environment_bootstrap_provenance.json` 如实标为不完整。

## 其余工作包

- 七算子诊断：`seven_operator/REPORT.md`，74 项工程回归通过；默认联合粒子为 0、普通路径 information block 为 0、CIAV 不消费完整粒子，不能签默认完整能力。
- W1：`w1_audit/REPORT.md`，524/524 静态交付一致，Windows 可移植入口范围通过；Linux/controller/xdist 动态复现受无 WSL 阻塞。
- W2：`w2_audit/REPORT.md`，71 与 19 项局部检查通过、31/31 历史伪造非 no-op；没有 A 发布的统一冻结 SHA，公平和科学结论保持阻塞。

下一步是先定位 full `-n 4` 环境中锁 deadline 的余量不足，再在新的生产 SHA 上重跑完整 CRLF/LF 812；不得把当前局部绿色或平台分类写成完整验收。
