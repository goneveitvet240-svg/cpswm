# 双参考位置开发与受控原生消费复现

实际功能源码 `1bd6c204d349024196c23df12cca61dbcea91e6c`，base 为 PR77 head `8623e7890594fce2b3c872bd2484b30138a9f408`；895 份 src/tests/tools Python 内容摘要在 frozen-source.json。受控位置 producer 移到 canonical production module，新增 owner 固定配置、实际输入时间/原件登记与完整目标重算。保护范围仅显式受控 raw profile，legacy 行为与可选 torch 依赖保留；不授予自然模型权威。

初版 `493e057` 的728项通过未覆盖完整目标似然替换，已被第二轮阻断。修复开发中34文件859项通过，随后另修 collector 首次发布合法路径；该859结果属于 repair-source-01.json，不能称最后修复的同源码回归。该97项通过后的第二次冻结仍被追加合法有限似然压力阻断：显示概率0导致下一步log(0)。最终修复改为传递owner接受的原始log证据、保留accepted支持，并保留完整代码检查范围。最终相关兼容与外部Decimal算术测试见 frozen-source.json 的 final_validation_manifest 及同名log，与本次冻结源码逐文件一致。首次通用组合171项中170通过、1项合法初始发布误报helper代码改变，原始失败保留；随后对同组件两处指纹统一完整字段稳定编码；重复探针未复现具体变化成员，不把推测写成已确认原因。各次失败记录均保留。后续顺序两审须各自绑定此功能 SHA；电脑 A 辅助、非 B 独立或全仓 CI。

本轮依赖 PR73 固定采集、PR74 缓存检测、PR76 亲和模型及 PR77 固定特征对照。历史入口均在各自匹配源码工作目录中运行，不能把当前 895 文件源码冒充旧 865/869/875/879 文件来源。Python 路径保留虚拟环境入口，不将符号链接解析成基础解释器；已使用环境版本和锁文件摘要在 runtime-environment.json，非独立重建环境。

## 实际运行入口

准备父轮完整归档与匹配源码后，在本轮冻结源码根目录运行：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 "$PYTHON" tools/run_soft_position_development.py \
 --controls-results "$PR77_ARTIFACTS" --controls-source "$PR77_SOURCE" \
 --controls-ledger-sha256 5eaabaaae15e4ed453c0f84b4f243103e25e5e9c1125f87f23e82e2be352bad2 \
 --affinity-results "$PR76_ARTIFACTS" --affinity-source "$PR76_SOURCE" --historical-python "$HISTORICAL_PYTHON" \
 --affinity-ledger-sha256 32e0dc7cec8fce6dfca5bc36755cfba5cf3551b454c1f746f20ac2076936e842 \
 --collection "$COLLECTION_ATTEMPT02" --capture-source "$PR73_SOURCE" --archive "$PROCTHOR_ARCHIVE" \
 --sdk-python "$SDK_VENV_PYTHON" --binary "$UNITY_BINARY" \
 --frontends "$PR74_ARTIFACTS" --frontend-source "$PR74_SOURCE" \
 --inventory-sha256 9791a946543b9158890324d3ff35a80ea04d51c9cabb6e09540f569abd903d47 \
 --frontend-ledger-sha256 517fc5b24afd80e4311d0de66dcfa6d113de6cd11763d61aeaaecd345740ccf6 \
 --output "$NEW_OUTPUT"
```

新目录不得覆盖输入/来源或已有实验。追加 `--verify` 会使用匹配历史入口 fresh 重算整个父链，再从原公开 RGB-D 重建本轮全部读出、拟合和诊断，对全部保存文件逐字节比较；不会仅恢复现有四个模型。实际 argv、时间、退出码和全部产物摘要由 run_experiment.py 保存 case-results.json。该脚本只在顺序两审均已完成且工作树仍为冻结提交时执行。

成功模型与拟合失败均保留四个组合的 model 文件和 training/residuals.npy、members.json。每帧 public/labels/corrected 三份 JSON，保留全部 96 帧，包括零候选、无效深度和 VOID。另有受控数字消费 diagnostic 与 report，总计 302 文件。失败模型不补协方差地板，也不以人工模型替代；公开可用性与模型可用性分别保存。

## 已固定的统计含义

soft_affinity 与 uniform 使用同一完整 8×8 网格、有效性和所有 seed。相同动作内的相同完整邻域与 seed 去重并保留全部来源；这不意味着样本独立。亲和分数只作为固定加权读出系数，未解释为校准责任度。输出是世界坐标表面代表点，不是已经识别的世界对象或对象中心。

每个 seed 的唯一合格 rendered mask 仅在离线标签连接时使用，分别保留 SDK transform pivot 与 AABB center。标签不选择公开候选/seed。真实深度对透明物体可能不对应渲染归属，误差包含前景、混合邻域、参考定义等影响，不能称纯传感器位姿误差校准。

原训练屋 1–8 拟合 residual=代表点−参考真值的均值 bias 与 ddof=1 全 3×3 协方差。全部公开读出先完成，train 标签拟合后生成全部公开修正与受控诊断，随后才连接 validation 9–12 标签。这是拟合的数据隔离：历史 fresh 验证进程仍可读取原件私有内容，并非对恶意进程的安全隔离。所有这些场景已开发曝光，不作为独立 holdout。

报告按 seed、对象帧、对象、房屋列分母，并保存逐屋/对象帧原始与去 bias 误差。相关 seed、重复 uniform 代表点不充作独立校准证据。尚未包含裸 seed 反投影基线，不能只因 soft 比 uniform 好就宣称聚合有效。

## 两种消费证据必须区分

`controlled-position-consumption.json` 使用实际拟合参数和只含公开字段的 96 帧投影，固定按原顺序取首个 available seed，各模型只用一个观测。参考原点与初始 6D Gaussian N(0,I6)、unknown/aggregate 的世界 3D N(0,100I3) 均为预先声明的受控假设，三支初始权重各 1。三维位置观测用 H=[I3,0]，更新前 predictive covariance 是 HΣHᵀ+R；条件统计仍以 R 更新。其他两个 RB 块零信息，不捏造旋转测量。此文件检验数值消费、重建和重复拒绝，**不产生 native receipt，不执行 owner pipeline**。

`tests/test_native_position_production.py` 则以显式受控像素、固定框/seed、合成训练残差模型和真实 proposal checkpoint 验证实际 Native 发布、原始似然与 q/integration 抵消后的权重、三步完整纠正重放、SQLite 恢复、加载代码/常量和完整原件重签攻击。当前没有把真实 96 帧训练模型接入这个 Native 测试，因此两者不能拼接宣称完整实数据 Native 接通。早期 12 步开发验证与最终冻结的三步测试分开记录于 NATIVE_COMPONENT_DEVELOPMENT.md。

正式自然 I→Z 关联、未知/杂波模型、跨帧依赖、正式位置参考及朝向、观测后的 owner 更新事务和动作效用收益仍待完成。原分类对照、主动澄清、位置+朝向及完整统一框架保留。

## 独立算术复核

在实际 run/verify 成功后，用 case ledger 的外部 SHA256 和冻结源码完整 SHA 调用 `independent_result_check.py --ledger-sha256 ... --source-sha ...`。异机复现可另传 `--result-dir`、`--collection` 和 `--affinity-experiment` 指向解包目录；固定外 pin 保持不变。脚本只复用原传输反序列化及其契约校验，独立重建固定候选网格、原像素世界点、亲和系数、表面点、mask seed 连接、四模型矩和公开修正、主要分母/误差及一条受控 Gaussian 更新。保留的检测候选与亲和参数作为固定依赖；不是重新训练检测器或另一套原始采集验收。具体独立检查字段和未重算的 object-frame 指标/全部 provenance hash 公式列在输出 JSON，不能扩大为全链独立验收。

`plot_results.py` 从已经封存的 report 生成逐屋 RMSE 图与 PDF，不重选模型、参考或阈值。实际运行结果与两审结论由最终 REPORT.md、ADVERSARIAL_REVIEW_1.md 和 ADVERSARIAL_REVIEW_2.md 给出。
