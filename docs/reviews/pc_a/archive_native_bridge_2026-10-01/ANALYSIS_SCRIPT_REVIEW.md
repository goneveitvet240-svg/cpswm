# 外部分析脚本只读审查：首轮发现

本审查只针对独立验算、绘图和报告脚本，不改 901 份冻结产品源码、不重开产品 R1/R2、不运行真实 bridge/bare 或 Unity。根任务已收到问题并在修复；**本文件保留原问题，不表示修复版已经通过。** 后续复核另记 `ANALYSIS_SCRIPT_REVIEW_FOLLOWUP.md`。

审阅人未编写本轮三个分析脚本；此前编写过 residual model/diagnostic，属于电脑 A 辅助检查，并非 B 独立验收。实际交付原件尚未生成，以下是在运行前的代码/受控算术审查。

## 版本与实际检查

原绘图/报告以及验算脚本的中间快照由根任务保存为：

| 保存文件 | SHA256 |
| --- | --- |
| `independent_result_check_before_analysis_review.py` | `451e1b4192db455aaafb766258426f56ee152f735dc6cfa991ab2d50dcc7c9ce` |
| `plot_results_before_analysis_review.py` | `904044ce14d44c111c6528acef5970794b6dc970803c734c571d9f3a578c3a0f` |
| `write_report_before_analysis_review.py` | `a33bade8dbe0ecab6716f61484e6d7362890325a94d857c45388a47fe141f72e` |

验算中间快照已包含根任务首个修复：记录 checker SHA、结束前再次核查成员；没有把该中间快照误称为最早读取版本。下文行号针对最初读取的三个同名脚本，函数名/表达式是稳定定位入口。

只读调用了 checker 的 `metric`/`match_dict`，以封存 `R1/BareCLI/legal-output` 的 8064×3 训练残差及原模型为输入，raw/corrected train 指标均与原报告相符。未执行 checker.main、真实新训练、Native 或绘图。还运行了两个纯矩阵例子，用于核查 Kalman 消减误差；没有写入 R1。

## 需要修正的问题

1. **报告/绘图读取的当前字节未重新绑定已验算的字节（优先修复）。** 原 `write_report.py:6–12,22–24` 仅核旧 `independent-analysis.json` 的 ledger hash、源码 map、两行 ledger 彼此相等；没有把当前 `bare/bridge` inventory 对比 ledger。验算后只改 `bare/report.json` 的 RMSE、保留 source_files，旧验算 JSON 与 ledger 均不动，报告仍会使用新数值并声称“逐字节不变”。原 `plot_results.py:8–9` 更直接读取报告，完全不查外部绑定。建议渲染前后共享检查：当前输出全成员、父包 pin/全成员、checker 本体 SHA、source SHA、两轮报告 SHA 与结果 JSON 都匹配；记录渲染脚本身份，最后再封存输出。
2. **纵轴只按 raw RMSE 设置，可能截掉更差的 corrected 结果。** 原 `plot_results.py:14–15,24` 的上限是 `1.2×max(raw)`。例如 raw 最大 1 m、某 corrected=2 m，柱体与标签会被裁切，隐藏坏结果。必须同时考虑全部有限 raw/corrected 值。`None` 在 raw 或已存在的 corrected 空指标字典中也不会被 `.get(...,nan)` 自动替换，`max`/`isfinite`/bar 可报错；应显式映射 `None→NaN` 并标注 N/A，保留空帧/失败模型。
3. **独立 Native 数值核对可以空转成功。** 原 checker `main` 的 `for name,result in bridge['results'].items()` 没有要求恰好四个预定义组合；`status=='unavailable'` 直接跳过，也没有核对父 `model_status`。少行或错误标记不可用时，`native` 可以为空而 `all_numeric_checks_passed=True`。建议精确枚举四组合、状态严格限定、不可用必须对应父 fit_failed，fitted 必须存在两 arm；报告的“四个模型均消费”等文字由实际已核状态生成，不能无条件硬编码。
4. **Native 数学的输入点仍取本轮 correspondence。** 原 checker 以 `correspondence['observations'][estimator]['world_point_m']` 同时计算 LL 和 posterior，没有自行把该点与外 pin 的父公开帧/seed/estimator 观测对齐。公式是独立的，输入点身份却仍依赖前级完整 fresh 验证。建议至少明确这一条件，最好直接将 correspondence 的完整公共字段与固定父 frame/seed 观测核对；full/single measurement ID 按现有桥接语义分别保留，不能强行相等。
5. **`inv(I-K)` 在合法小 R 下可能误拒。** 原 checker `K=solve(I+R,I)`、`cov[:3,:3]-=K` 后逆矩阵。纯矩阵例子 `R=1e-12 I` 时，与精确信息形式 `I+R^-1` 的相对误差为 `8.889268072989158e-05`，远大于配置的 `2e-10`；`R=1e-6 I` 误差约 `6.11e-11`。建议保持独立 Kalman 推导，但使用 Joseph 形式 `(I-K)(I-K)^T + K R K^T`，不加 epsilon、不改变模型。

以上 1、2 是直接的渲染可靠性缺陷；3、4 是独立验算的缺失覆盖；5 是可复现的合法数值边界，不表示真实本轮模型一定触发。

## 独立性、配对口径与证据边界

- **算术确实另写。** checker 不调用生产 fit/condition/summarize；train bias/`np.cov(ddof=1)`、SciPy logpdf/logsumexp、Kalman mean/covariance、RMSE/median/最大误差是另一套表达。被动复制结果或调用生产 helper 充作“独立”这一问题没有发现。但仍使用同样 NumPy/线性代数库，不是独立数据收集或跨机器复现。
- **比较在固定同 seed 上成立。** bare 从父完整 neighborhood 中找到原 seed 点，不扩框、不挑私有标签；soft/uniform 共用的双标签字段核对后每 seed 只计一次，训练只按既定 houses1–8，validation9–12不入矩估计。同像素但不同完整邻域仍是不同 seed；应并列列出 unique pixel、eligible seed、对象帧/屋分母，不能将 seed 视为独立样本。原脚本 split/house 主要分母有重算；逐对象帧指标、VOID原因、每行训练 provenance 没有完全独立重算，limitations 已诚实承认大部分范围。
- **soft/uniform 指标沿用已经外 pin 的父报告。** 本轮 checker 验证其原件与拷贝一致，不重新计算两种聚合的所有指标。表格可以描述三个读出，但不应称为三方法全部由本脚本重新独立验算。建议明确“bare重算；聚合继承已复核父结果”。
- **SQLite和执行声明没有被此脚本独立证明。** checker 对 `fresh_processes/neutral_steps/duplicate_unchanged/raw_packet_unchanged/physical_camera_commands` 的处理是读取受 pin 的报告声明；它并未打开 SQLite，也未观察子进程。独立公式只验证保存的数字。真正 owner/receipt/原 DB 副本恢复来自冻结运行和前级 review，应保持两条证据链，不把 SciPy pass 写作数据库真实性验收。
- **报告科学边界总体充分。** 已披露训练屋单 capture、合成身份/语义/prior、未知分支人为高斯、无自然身份/校准/动作收益、无 B 验收、相关且已曝光的 validation，以及下步 raw-observation 事务。建议把“真实位置似然”写成“实际训练模型产生的位置似然”，避免被读成已校准真似然；使用固定参考各自误差，不以 pivot/AABB 的数值大小选择正式参考。
- **图上还宜显示分母与暴露范围。** 总验证柱图也标“exposed development validation”、监督 seed/house 数和不确定性缺失；逐屋线只有12个屋级点，不能当 IID 样本推显著性。没有要求新增检验或选模型。

本轮只读发现已反馈根任务；修复后应在单独受控副本上验证“旧 checker 成功→当前报告被改→渲染拒绝→合法恢复通过”，以及 corrected 大于 raw 上限、None/fit_failed/空监督可见。实际数据桥接仍等待正在进行的产品 R2。
