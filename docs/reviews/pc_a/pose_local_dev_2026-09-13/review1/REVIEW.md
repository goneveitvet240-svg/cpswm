# 第一轮独立审核：C 位姿和本地开发

审查固定 SHA：b33992da1bd775f180d915e80b7e7746546adbd9。源目录 /private/tmp/cpswm-pc-a-pose-local-dev-20260913。只读审查；未修改源、测试、配置或 HEAD。独立脚本及原始 JSON 均在本目录，使用候选自己的 .venv 运行。

## 结论

发现 1 项需要修复的 P2 时间绑定缺陷，及 1 项边界异常一致性改进。不能将当前源码判为本批边界完全通过。独立几何和不等维数数值正例通过；不表示真实姿态输入、训练、统一主干或动作闭环完成。

## P2：同一 ZoneInfo 的 DST fold 不同瞬间被当成同一 epoch

位置：src/cpswm/system/structure_two_pose.py，pose_residual 中 reference.valid_at != observed.valid_at。

构造 America/New_York 的 2026-11-01 01:30，fold=0 对应 -04:00、fold=1 对应 -05:00。二者实际时间戳相差 3600 秒，但 Python 同一 tzinfo 下 datetime 相等忽略 fold。当前公开函数返回六个零残差，接受把不同实际时刻的状态作为同一时刻处理。这破坏本模块声称的固定 epoch 边界，且不依赖伪造类型：两个输入均为正常合法构造的 PoseState。

建议：在比较前明确转为 UTC 时间（避免浮点 timestamp 精度丢失），保留同一瞬间用不同 UTC offset 表示的正例，并增加同一 ZoneInfo fold 两个瞬间的拒绝例。若构造时规范化，仍需对 model_copy 伪造实例在入口重新处理。

证据：probe.py；result.json 的 dst_fold 项。

## 边界异常一致性

经 model_copy 将 qx 改为有限但极大的 1e308 后，apply_pose_delta 泄漏 OverflowError，原因是 _pose 先构造 Pose3D、其验证器对 qx 平方发生溢出，之后才检查数值有限性。没有错误合法输出，因此不是接受绕过；但调用者仅捕获 ValueError 时会异常退出。建议在新公开边界把超范围四元数转换为一致的输入拒绝错误，或用稳定 norm 验证后进入原合同。与现有 Pose3D 全局行为相关，不能简单说本批独立产生了全部上游问题。

## 独立正例及反例

- 1000 个随机 SO(3) 参考姿态、随机小于 pi 的旋转和独立世界平移：apply/residual 往返最大绝对误差 8.881784197001252e-16。
- q 与 -q 表示等价；pi 分支拒绝。
- 普通对象不同、时间差 1 微秒、坐标系不同均拒绝。
- 同一瞬间 UTC 与 +08:00 表示被接受，保留合法时间转换。
- RLS/Gaussian/measurement 维数分别 (1,6,3)、(7,2,4)、(2,6,6)；随机矩形 H、随机正定非单位协方差，和独立直接矩阵公式逐项比较 a/b/precision/natural，全部通过；空保留序列恢复 prior。
- H 错误宽度、RLS 错误维数、负定噪声协方差和重复证据簇均拒绝。
- model_copy 的 NaN 与未知字段被拒绝；巨大 quaternion 见上述异常。

命令：候选目录下 `.venv/bin/python /private/tmp/cpswm-pose-review1/probe.py` 和 `.venv/bin/python /private/tmp/cpswm-pose-review1/boundaries.py`，两者退出 0。probe 是诊断记录，退出 0 不表示其中发现的 DST 漏洞通过。

## 维数及配置静态追踪

检索本批结构二 information_vector / information / len(b) 消费，workspace 构造按两个块分别检验，conditional update 的 H 按 Gaussian dim，joint consumption 复制两块，没有发现剩余强制相等假设。此为所检索原生块路径的有限静态覆盖，并非全仓所有潜在反射消费者证明。

配置明确写 local_development_only_not_formal_selection、CPU、三架构、三种子、无历史截断、超预算报错、正式排名禁用，model_trainer_available / training_started / production_pose_tracker_available 全 false。工作报告明确预算配置不是执行器，缺观测/校准/监督/默认接线，不存在宣称训练已完成或把全框架缩成位置跟踪的文字。

旋转是右乘局部轴增量、平移为命名世界轴，和 R3 x SO3 说明一致；其刻意不是 SE3 对数。这里没有验证姿态分布、误差协方差传播、物体对称多模态、连续重线性化、真实检测或动作后果，均为明确未实现/未覆盖部分。没有重跑作者的整套 812 回归。
