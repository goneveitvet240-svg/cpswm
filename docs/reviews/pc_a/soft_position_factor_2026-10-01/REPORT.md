# 公开表面位置开发、双参考误差与受控原生消费

本轮完成公开 RGB-D 软表面读出、四个训练分区残差模型的开发流程，以及位置似然实际消费的工程接线。真实归档使用两估计器×两参考，不根据验证结果选择正式参考；Native 发布测试仍采用受控像素与合成残差模型。**真实训练模型到 Native 发布的单 capture 桥接尚未完成，完整自然 I→Z、实时观测更新和行动收益没有关闭。**

实际双审/运行源码 `1bd6c204d349024196c23df12cca61dbcea91e6c`，895 份 Python 源码；base PR77 head `8623e7890594fce2b3c872bd2484b30138a9f408`。分支 codex/pc-a-soft-position-factor-20261001。后续文档提交不替代实际功能 SHA。初版冻结前定向组合回归曾有 728 passed in 581.84s，但第二轮审核发现完整观测似然/aggregate可被替换，初版未通过；原报告与后果保留在 ATTEMPT_1 文档。修复中间版本34文件859项通过；随后还修复正常collector稍晚cutoff首次发布误拒绝，所以859属于其单独源码清单。第二次冻结37981c3的97项兼容测试及新R1的49项通过；新R2完整历史3项与恢复32项通过，但追加合法极端似然发现显示概率下溢后log(0)中断，故第二版也被阻断，失败原件保留于ATTEMPT_2。最终增加原始log权重证据与稳定支持传递。首次通用171项组合170通过、1项合法初始发布被helper代码校验误拒，完整失败保留。重复探针未复现具体变化成员，不能宣称已锁定其原因；同组件两处指纹统一为全字段稳定编码后，冻结前相关通用兼容/数值/外部Decimal复核结果为 `174 passed, 10 warnings in 501.39s (0:08:21)`，源码清单与本次冻结逐文件一致。新源码两轮顺序电脑 A 辅助对抗详见对应报告；作者参与范围逐项披露，非电脑 B 独立、非全仓 CI/统一验收。

## 实际数据结果

原 12 屋 96 帧，train 1–8、validation 9–12；验证来源已开发曝光。公开候选 176，规范邻域 176，完整 seed 11240，公开有效 11240，有合格离线参考 3668。零候选 38/96 帧，无监督 55/96 帧，均保留。seed 强相关，不充作独立校准样本。

| 估计器 / 离线参考 | train / validation seed | 验证原始 RMSE (m) | 验证去 bias RMSE (m) | 验证去 bias 平均 NLL |
| --- | ---: | ---: | ---: | ---: |
| soft_affinity/sdk_aabb_center_m | 2004 / 1664 | 0.513540 | 0.523058 | 0.584141 |
| soft_affinity/sdk_transform_position_m | 2004 / 1664 | 0.674738 | 0.615581 | 1.360417 |
| uniform/sdk_aabb_center_m | 2004 / 1664 | 0.712308 | 0.711919 | 1.385137 |
| uniform/sdk_transform_position_m | 2004 / 1664 | 0.833717 | 0.785566 | 1.982686 |

模型拟合成功 4/4；拟合失败项保持显式失败，不加协方差地板或人工补位。完整逐屋、对象帧、对象与 seed 分母、原始/修正误差见 experiment/report.json，四份 residuals.npy 和 members.json 保留拟合输入。参数只由原训练屋估计；全部公开读出→train 标签拟合→全部公开修正与 diagnostic→validation 标签评价。历史 fresh 校验仍会访问原私有资料，不能称恶意进程隔离。

soft_affinity 与 uniform 都输出邻域表面代表点，不自动成为对象中心或世界身份。离线 seed 渲染归属只用于训练/评价，不改变公开采样；透明物体深度未必等于其渲染表面。误差混合前景、邻域、参考定义与几何因素，不是纯相机位姿误差校准。尚缺裸 seed 世界点基线，不能用两种聚合的相对结果证明聚合有益。

## 实际消费证据与边界

初版 `493e057` 的 q 重算未核验 base raw likelihood，完整替换使 known 概率从 0.097778 错误变为 0.444687，aggregate 同族缺陷也被复现。该版本被阻断，实数据未运行；修复实现及最终双审详见新审核报告，不用初版728项通过抵消缺陷。

修复让拥有者固定受控模型配置、真实输入前缀及时间、实际语义来源与父链，并在当前发布/历史消费/重放/恢复重新计算完整base候选似然与RB统计。独立core锚阻止删除profile降级；数学重算不信任提交者的自洽证明或可变producer预状态，也不改写活producer。此保护仅覆盖显式canonical受控位置profile，不能推广到所有旧候选模型。正常None/重复语义advance也登记真实owner时刻，首次collector可自动发布和恰好一次相机执行；真正无语义源保持INSUFFICIENT，直接提交未来时刻仍拒绝。这里的一次相机动作只验证后果完整性，返回的新测量尚未通过同语义多观测事务加入后验。

第二次冻结版本的有限LL为−2465.7563115023117，known显示为0后下一中性步骤失败。最终修复从owner已接受前批receipt原始项重建稳定归一化log权重，接受但显示为0的known/unknown/aggregate仍保留支持；超出有限log表示范围显式拒绝，不加概率地板。测试覆盖两类下溢的继续、新进程恢复、撤回重放及独立高精度Decimal计算。加载代码检查保留全部字段/范围，并用局部无引用共享标记的编码，避免持有异常traceback时旧编码误拒绝合法恢复；未改全局checkpoint身份协议。

真实训练参数已经通过受控**数值**消费 diagnostic：固定首个公开可用 seed，一模型一次测量；先从更新前 prior 计算三维预测密度，再以 H=[I3,0] 和原 R 更新六维自然参数。其他 RB 块零信息，无旋转观测。known 初始 N(0,I6)/reference 原点、unknown 与 aggregate 共用 N(0,100I3)，三支初权各 1，全部是预先明示的开发假设；后验高低不能解释为自然识别正确率。该文件明确 native_receipts_produced=False、owner_pipeline_executed=False。

另有受控 Native 正路径：原始 admitted RGB-D 经重算读出和真实 proposal checkpoint，raw observation receipt 的非零似然改变实际发布权重与条件统计；q/integration 精确抵消、重复不增量、三步完整撤回重放、SQLite 新实例恢复及完整原件/代码/常量替换拒绝均有测试。其像素、关联、模型和参考为显式fixture；早期 12 步开发测试与冻结三步回归分开。不能把两份分离证据合称真实训练模型已进入实际 Native。

## 重算与来源

真实 run 324.36s，另进程完整 fresh verify 326.64s，均 exit 0，302 个保存产物逐字节相同。case ledger 外部 pin `9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc`。全过程复用已有采集和检测缓存，本轮没有重新启动 Unity 或检测器。

独立脚本重新核对外部输入/产物 pin、固定框网格、原公开像素几何和亲和系数、mask seed 连接、残差矩与主要分母/指标、公开修正及一条受控 Gaussian 更新。independent-analysis.json SHA256 `1d14def93f3f9a62ad807ca2dec4b8afd5a47c17a87c6efa71b0ff9e837c6b9c`。只复用传输反序列化及契约校验；检测模型与固定亲和参数视为已 pin 依赖，不是独立采集/检测验收。未独立重算的 object-frame 指标及全部 provenance 公式在 JSON 中明列。图和 PDF 只读取已经固定的 report。

## 下一主项

先把原始归档、实际拟合模型和公开候选严格桥接到 Native 发布；保留原 raw 字节/UUID/回执，合成的仅是显式语义上下文。然后补 owner 逐 raw-observation 事务及逐 cluster replay：当前新相机结果只被接收，同语义来源会 early return，重放又按 semantic revision 去重，尚不能正确承载同一来源的多次独立观测更新。不得清缓存、改 semantic UUID 或借未来图像绕过。

正式位置参考、自然身份规则、未知/杂波模型、跨帧依赖、朝向和任务收益仍待解决。原分类对照、主动澄清、位置+朝向，以及完整 H/R/I/C/Z/r/V、三个 RB blocks 和七算子研究范围保持。

## 证据入口

- PLAN.md：实数据运行前固定协议与受控先验。
- ADVERSARIAL_REVIEW_1.md / ADVERSARIAL_REVIEW_2.md：顺序对抗与实际执行边界。
- REPRODUCE.md / run_experiment.py / case-results.json：精确入口、返回码和产物摘要。
- independent_result_check.py / independent-analysis.json：独立算术及明确检查范围。
- NATIVE_COMPONENT_DEVELOPMENT.md：开发失败、中间 12 步和最终三步证据分别记录。
- NEXT_RAW_UPDATE_DESIGN.md / ARCHIVE_NATIVE_BRIDGE_DESIGN.md：下一轮只读设计，不计本轮已实现成果。

独立算术脚本第一次运行因逐点重复解压掩膜而由root中止，未计通过；缓存每帧原掩膜后同公式全部复核通过（8.22s），首版脚本、日志与修改说明均保留。图PNG已实际查看，四面板轴/训练验证边界与逐屋seed标注正常。
