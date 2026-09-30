# 外部分析脚本修复复核

结论：**修复在下述有界范围通过，未发现阻止按既定协议生成分析产物的新缺陷。** 这不是产品 R2、真实实验、B验收或新的科学结论；901份冻结产品源码与封存R1均未改。本报告必须与首轮 `ANALYSIS_SCRIPT_REVIEW.md` 一起保留。

## 绑定版本

| 当前脚本 | 实际复核 SHA256 |
| --- | --- |
| `analysis_binding.py` | `9d83cd04f8bbf098e16365a7e059171388b7f2c6858e18426deeca1b08445131` |
| `independent_result_check.py` | `aa8e5fef3d83090324c363c07f607d922cca7e3f1e685a26ed5065ad1657fd33` |
| `plot_results.py` | `dae6ad1e04f77cb73d10498d16b3308b3770f3fc0c2da1ea60e34d574cd7984e` |
| `write_report.py` | `50e067e5d9e15a27156b5e0d354b59f2c3e5c35084c3df1739e4409f23aaa72c` |

主测试实际入口：`/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python AnalysisReview/probe_analysis_binding_02.py`，exit 0。完整脚本、stdout/stderr、两轮脚本字节副本、受控输出与篡改副本见 `AnalysisReview/`。四脚本前后哈希逐项一致；测试没有修改脚本正文。

测试将绑定模块的 `OUT` 指向新受控副本，保留固定真实父包路径/pin，仅对父包进行只读完整性检查。当前 `write_report.py`/`plot_results.py` 原样复制并实际执行；受控case ledger和两份review占位文件被明确标为模拟绑定，**不能视为正式运行/审核记录**。本测试验证绑定规则与渲染后果，不证明模拟ledger陈述真实。生产fit/Native/SDK流程没有运行，旧R1原件只用于复制。

## 实際执行及后果

| 输入/变化 | 实际结果 |
| --- | --- |
| 完整受控合法输入与调用者持有的原 `--analysis-sha256` | 报告生成成功 |
| 只改当前 `bare/report.json` 的RMSE，原ledger/checker外pin不变 | 报告拒绝；没有使用改后的数值 |
| 恢复原报告 | 生成与首次逐字节相同的报告 |
| 只改 `independent-analysis.json` 的known LL/概率，保留其身份字段及原调用者pin | 报告拒绝 |
| 恢复原独立验算JSON | 报告再次字节一致 |
| 单独布局夹具：raw=1 m、一个corrected=5 m、另组None | PNG/PDF成功；两个上图ylim均为[0,6]，坏柱与5.000标签完整，None显示N/A |
| 绘图后只改checker数字，仍用原绘图CLI pin | 拒绝，原PNG/PDF哈希不变 |
| 纯矩阵Joseph公式，R=1e-12 I | 与 `I+R^-1` 在rtol/atol=2e-10下一致，无epsilon |

布局产物 `AnalysisReview/layout-02/position-comparison.png` 已目视检查，数值仅为刻意构造的绘图夹具，**不是实际模型性能图**。N/A不会当成0值展示。第一组两根柱均缺失时，一个N/A文字位于坐标轴左边缘之外；属于非阻断的排版改进，可在后续版本固定xlim(-0.6,2.6)，未影响本次缺失标识或数值范围判定。

## 修复覆盖

- 新 `analysis_binding(expected_analysis_pin)` 在读取前校验整个独立验算JSON的调用者外部摘要，之后校验checker脚本SHA、source SHA、父ledger pin、当前bridge/bare全部成员、两轮报告SHA。report/plot在开始与写入前调用同一检查。
- 首轮仅记录checker本体SHA仍不足：攻击者可只改其输出JSON中的数字，保留所有身份字段。现在调用者持有的**输出JSON外pin**补上该缺口。正式运行必须在checker成功后由根任务记录这个摘要，并把固定值写进实际命令；不得验证时从待验证JSON重新计算摘要并当成外部授权。
- checker在结束前再次核原件与父包inventory；Native现在要求恰好四组合、父状态对应、fitted model pin及两arm完整。不可用只能对应父fit_failed。此新增分支做了源码阅读，**本次没有执行完整96帧checker.main**，不能冒称所有分支已独立动态覆盖。
- checker从外pin父frame000读取full seed，核候选属于source、seed像素以及两估计器的point/estimator pin/domain/frame/action/time/available/reason。原full/single measurement ID仍分别保留。对当前固定父frame000实际schema做了只读确认；未执行实际Native。固定frame000是本轮协议限定，未来更换公开选择策略需同步改此检查。
- Kalman后验改用Joseph表达，保留与生产信息形式不同的算术路径。小R合法边界已动态复核。
- y上限来自全部有限raw和corrected；None显式转NaN并标记N/A。本次实际绘图确认其后果。

## 保留的首次失败与限制

`probe_analysis_binding_01.py` 的首次运行exit1，保留 `probe-01.log`、`probe-01-status.json`、`fixture-01`与版本映射。它先生成了合法报告、恢复报告以及“仅改checker数值”的错误报告，随后根任务正在应用已商定的外pin修复，末尾四脚本SHA一致性断言因此失败。该尝试证明了中间版缺口，但未满足最终版本稳定性检查；不得计作正式通过。`probe_analysis_binding_02.py` 是另存的新尝试，没有覆盖首次失败。Matplotlib/Fontconfig因默认缓存目录不可写而改用临时缓存；渲染仍exit0，警告原文保留。

这些分析脚本在普通Python解释模式下运行，使用assert检查；没有把它们提升为恶意进程隔离或通用安全验证器，也没有检验并发换文件/解释器优化关闭assert等情形。SciPy复算仍是条件于固定已pin数据的算术证据；SQLite owner真实性、原始receipt、真实子进程/相机命令及执行顺序由前级冻结运行和产品审核承担。per-object-frame每条公式、所有provenance哈希、真实96帧本轮checker主路径没有在本子任务重复。

图表仍为描述性配对比较，不增加独立样本、显著性、校准或动作收益。soft/uniform完整指标由已复核父报告继承，bare算术另算；原脚本科学边界保持。真实产物与正式REPORT的数值只能在产品R2和根任务既定实际运行完成后生成。后续若四脚本改动，本复核只对上表SHA有效。
