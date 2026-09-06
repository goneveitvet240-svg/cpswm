# 结构二行动读出 v0.6：两轮对抗自查后的开发推进（2026-09-06）

## 结论

本轮先完成两轮 adversarial self-audit（对抗自查），再推进当前最紧要的
put-back/recovery（放回／恢复）问题。结果不是论文级胜出，但已经改变 D0 开发判定：

- v0.6 完整 Project Two 在新的 60-episode development holdout（开发留出集）上，
  `cumulative_action_regret = 3.455556`；
- 当前最强参考 matched AMG 为 `3.933333`；
- 配对差值 `AMG - Project Two = +0.477778`，95% paired bootstrap interval（配对自助区间）
  为 `[+0.338889, +0.633333]`；
- put-back regret（放回遗憾）完全打平，均为 `1.716667`；
- Project Two 的 search regret（搜索遗憾）为 `1.738889`，AMG 为 `2.216667`；
- recovery cost（恢复成本）均为 `0`；
- Project Two 的 owner contamination（主人习惯污染）为 `0.007292`，AMG 为 `0`。

因此当前准确表述是：**v0.6 在 D0 注册开发效用上取得工程优势，并闭合了旧读出的放回与恢复差距；
污染护栏和论文级证据门仍未通过。**

## 两轮对抗自查

第一轮针对 forged-but-complete positive path（伪造但字段完整的正结论路径），发现并封闭 6 类绕过：

1. 同时伪造 utility definition、verdict 和 status 后宣称论文胜出；
2. 替换 primary comparison（主比较）文本；
3. 擦除 paper-level gates（论文级门）；
4. report 与 definition 的 unresolved fields（未决字段）分裂；
5. 重复 aggregate identity（聚合指标身份）；
6. 把 validation 未胜出的参数伪装成 selected parameters（选中参数）。

第二轮针对 identity/type/plan/state boundary（身份／类型／计划／状态边界），发现并封闭 10 类可接受绕过，
并修正 1 条错误失败路径：baseline fairness 缺项、aggregate fidelity 替换、重复 case row、validation ID
替换、visible hash 擦除、`bool` 冒充数值权重、重复 search location、未登记 search location、未登记
put-back location、非法 unknown probability；空 search plan 原先抛 `IndexError`，现改为合同级 `ValueError`。

回归入口为 `tests/test_structure_two_action_benchmark_v0_5_adversarial.py`。两轮覆盖的是本轮枚举的攻击矩阵，
不声称已经穷尽所有未来攻击。

## 训练诊断与验证选择

方法开发只查看 TRAIN seeds `1--20`。matched AMG 的训练累计遗憾为 `3.95`；主要 Project Two
读出结果如下：

| 读出 | 累计遗憾 | 放回 | 搜索 | 污染 | 恢复 |
|---|---:|---:|---:|---:|---:|
| slow surviving | 6.766667 | 4.900000 | 1.866667 | 0 | 0.441667 |
| latest owner | 3.733333 | 1.700000 | 2.033333 | 0 | 0 |
| dual 0.8 fast + 0.2 surviving | 3.566667 | 1.700000 | 1.866667 | 0 | 0 |
| dual 0.7 fast + 0.2 surviving + 0.1 regime | **3.266667** | 1.700000 | 1.566667 | 0.006250 | 0 |
| v0.5 revision aware | 7.866667 | 6.300000 | 1.566667 | 0.006250 | 1.333333 |
| v0.5 pooled hybrid | 12.366667 | 10.800000 | 1.566667 | 0.006250 | 4.341667 |

随后冻结三个等预算机制候选，在 validation seeds `1001--1020` 上按唯一主效用选择：

| 候选 | validation 累计遗憾 | 污染 |
|---|---:|---:|
| latest owner | 3.400000 | 0 |
| dual 0.8 / 0.2 / 0.0 | 3.266667 | 0 |
| dual 0.7 / 0.2 / 0.1 | **3.050000** | 0.006250 |

最终选择第三点。它没有删除 OPCEU、ORRER、PCHMP、CF-BOCPD、RGRC、CCRR 或 CIAV；变化仅发生在
planner read boundary（规划器读取边界），即快行动账本、存活修订和当前 regime-local 分量如何供下一行动读取。

## 开启前记录与新留出集

- 开启前记录：
  `configs/project_two_experiments/structure_two_action_readout_v0_6_preregistration.json`
  - SHA-256：`bb274d3822d30c06a1571d2b1951e575576e81ae5b22dc6de9a4d1e47e1ac63c`
- 数据配置：`configs/project_two_datasets/d0_multiseed_readout_v0_5.json`
  - SHA-256：`c2ce79d46ef9aa1335b092ca06dde0ce170e8c766dce68db63b7b04dde716cb8`
- 首次评估源码：`src/cpswm/system/evaluation_operations/project_two_action_benchmark.py`
  - 评估时 SHA-256：`c0ad6c01cd4a4361949bb3d31161a29e0a48f7bffa3dc3bc287401aea72524f2`
- 首次评估工件：
  `artifacts/project_two_v04_development/structure_two_action_benchmark_v0_6_dual_timescale_2026_09_06.json`
  - SHA-256：`2887a0281535b8eca0301e3ce5b3fecd1af194319b3afffcf455c26cbd2ba289`

留出集 seeds `6001--6060` 只在候选与验证选择冻结后运行一次。它仍由同一开发环境持有，raw seeds
也没有对候选环境隐藏，因此只能是 development holdout，不能冒充 independent custody（独立托管）。

首次运行后只做了 mypy 变量名消歧，不改变控制流或数值语义；当前源码 SHA-256 为
`9267432af7b4798a038445dc93503471d21cbf57ae54c7007fdd825458ae434f`。为了保留一次开启边界，
没有用类型清理后的源码重跑这 60 个 episode。

## 仍未通过

1. contamination、recovery latency、full-rerun equivalence 的数值护栏尚未注册；
2. real task-cost calibration（真实任务成本标定）与 superiority margin（优效界值）尚未注册；
3. D1--D4 外部有效性仍关闭；
4. 六个外部强邻居仍不是 faithful native reproduction（忠实原声复现）；
5. 没有独立托管、外部签名和封存后开启。

`scientific_verdict` 因此继续为 `superiority_authorized=false`、`paper_claim_allowed=false`。

## 验证

- 10 个相关测试文件、156 项测试：通过；
- v0.6 工件重新载入并通过强类型 report validator：60 个 test episode、600 个 case rows、170 个 aggregates；
- 触及文件 Ruff：通过；
- 3 个核心 source 文件 strict mypy：通过；
- `git diff --check`：通过。
