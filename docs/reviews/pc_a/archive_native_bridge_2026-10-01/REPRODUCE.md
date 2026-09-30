# 实际归档桥接与裸点对照复现

功能源码固定为 `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，901 个 Python 文件；不要使用后续文档提交或默认 main 替代源码身份。先读 PLAN.md、REPORT.md、两轮审核及 frozen-source.json。当前仅 A 本机复核，B 尚未验收。

当前 SQLite fresh resume 只在所记录的 A/macOS 环境验证。原 DB 含配置路径、完整 Python 环境和实现依赖绑定，不支持直接搬运到 Windows；保留原件，不修改 config/DB/pins 绕过。B 可先独立核完整归档/hash、审查源码并在新环境跑受控测试。顶层历史 verify 仍与 POSIX 清单名称、原 SDK Python executable/runtime 及 Mac Unity binary 指纹耦合，不能承诺换路径即可复现。跨平台端到端复核需要另轮受审适配及实际运行；详见 PORTABILITY_REVIEW.md，所列是静态限制，未实际运行 Windows。

以下命令仅用于满足原绑定的同环境复算，不是已通过的跨平台教程。按 PR73、74、76、77、78 的交付说明恢复原始输入与匹配历史源码。各个不可变 case-ledger/inventory 外部摘要及实际绝对路径已写入 `run_experiment.py` 和 `case-results.json`；用户提供的新路径不能改变这些摘要。历史 Python 应指向原虚拟环境 executable，不要解析成基础解释器后丢失依赖。运行环境见 runtime-environment.json。

当前轮的两个顶层入口是：

- `tools/run_archive_native_bridge.py`：固定祖先重新验证、从公开输入选择第一有效 candidate/seed、四模型的 active/no-factor 比较及 SQLite 新进程恢复。
- `tools/run_bare_seed_development.py`：从完全相同 seed 的原深度点建立两参考模型与误差对照，保留全部帧/无监督分母。

实际完整参数见四条 case-results.json 的 argv。代码只构造固定历史 verify 入口，不从不可信 ledger 执行任意命令。复现到新的输出目录；不要覆盖已封存证据。环境设 `PYTHONPATH=src:tests:tools`、`OPENBLAS_NUM_THREADS=1`，工作目录是冻结源码树。每个入口先 run，再在同一产物目录传 `--verify`，验证会重算并检查原始输出未变。bridge 原 SQLite 只在临时副本上验收。

如本机完整路径相同且原 BO 还不存在 `case-results.json`，`run_experiment.py` 提供顺序两审和源码冻结的门控封装。已封存 BO 不得直接重跑该封装；在新目录复制 harness/双审记录、按原 argv 使用新输出路径即可。平台、临时路径或归档解压后绝对符号链接可能不同，跨机应按 inventory 逐成员校验并将测试符号链接作为数据审查，不能盲目跟随链接或覆盖原工作树。

实验全部完成后，先从四条实际 ledger 原件计算外部 SHA，再传给 `independent_result_check.py --ledger-sha256 ...`。它使用独立 SciPy/Joseph 公式，不调用生产拟合/condition/报告函数。成功后从整个 `independent-analysis.json` 计算外部 SHA，分别传给 `plot_results.py --analysis-sha256 ...` 与 `write_report.py --analysis-sha256 ...`。渲染前后必须重新检查所有原件、当前源码map、两审报告与完整独立复核结果的绑定。具体本次分析 argv 与 pin 另见 analysis-commands.json；不要重签已改结果来冒充原外部 pin。

父 PR78 已独立复核原像素几何及私有评价字段。本轮独立 checker 以外 pin 的父公开点/标签为已验证输入，再核 bare 点、训练矩、主要分母、split/house 指标与 Native 数值后果；不宣称重复验收所有原始采集/检测/身份真实性。正式参考、自然身份/未知模型、朝向、时序相关性及任务效用仍未完成。

原始执行日志、失败与修正轨迹均随包交付。产品源码一旦改变，旧双审不自动延续；报告/绘图脚本的专项修正绑定另存的脚本 SHA，不计为产品源码测试。
