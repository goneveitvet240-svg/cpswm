# 完整测试依赖与真实行动报告

Base778e35418d79b350148c774d98377b0a4ab6e6d4，修复后源码c87b6bb1e3c72986afe517f7f29ebf3d028f2283，分支codex/pc-a-ci-action-report-20260930。完整回归尚未通过，局部工程证据与自然任务收益分别记录。

## 改动

CI使用冻结锁文件并显式安装dev/perception/hand-perception；opencv-contrib-python沿用锁定5.0.0.93，仅新增perception依赖关系。pytest在项目配置中声明src/tests/tools搜索路径，完整回归前先收集所有测试，收集失败立即退出。两个继承格式失败修复前后AST相同；未删除测试、放宽方法检查或更改锁定包版本。

实验报告把action_started、action_stopped、action_unchanged、action_replaced和no_action分别记录。decision_changed表示包含有无动作的决策变化；action_changed只在两端都有动作且动作/角度不同成立。新命令UUID或新快照本身不算物理动作变化。正常采集和完整复算使用同一含义，历史原件不改。

新环境暴露的源码搬移失败源于陈旧editable搜索路径；测试子进程明确移除旧源码入口，同时继续禁止所有原目录读取。该修复不掩盖跨环境差异，不放宽源码、权重或q校验。部署移机仍应按协作规则重建环境。

## 当前验证

初版f41eb1f第一审74通过，第二审30通过/1失败；原日志保留。新源码顺序74/31双审全部通过、零跳过。完整新环境中不设置PYTHONPATH也成功收集6035项/367模块；全仓382源码mypy、757文件Ruff/格式通过。远端run36629644083的static-quality已成功，测试收集成功，完整回归仍待结果。[两轮记录](REVIEWS.md)。

新源码真实RGB-D历史已完成3次观察、1次受控来源撤回、11源/22记录和一次重放代际，首次完整复算通过。旧左转90度READY取消，新代先Pass再继续观察；报告action_replaced、decision_changed=true和action_changed=true均对应保存的实际命令。保存的旧PR65无READY案例则重新解释为action_started、action_changed=false；这项旧命令解释不冒充新源码对旧实验的完整复核。

本轮同时进行本机首失败诊断和远端完整回归，记录的耗时不是专门的延迟/性能基准。旧基线CI在65分钟到达82%后超时，前面已有多项失败；超时没有完整错误回溯，因此新增首失败诊断用于定位，不能把其中通过的前缀写成全仓通过。

自然语义、可靠世界身份/事件监督、自然目标密度、校准、B独立与长期自然闭环仍未完成。没有训练新的私有标签模型，没有更换先验、正式阈值或任务效用；完整统一框架和所有原对照保留。

## 完整选择的首失败诊断

新环境完整选择使用--maxfail=1和2个worker，实际1750 passed、1 xfailed、1 failed（821.03秒）；不是全仓通过。首失败test_v02_calls_real_feedback_revision_loop_and_project_one_interface：旧测试为统计调用次数替换ProjectTwoFeedbackRevisionLoop.ingest_feedback，生产运行时的声明成员检查拒绝该测试替身。下一轮用观察真实调用的方式修复测试，保持生产来源检查及成功/失败反馈正路径断言。

新源码另进程完整视觉复算通过；源码与模型异目录恢复293.17秒、11源/22记录，workspace/证明/视图/动作/账本哈希完全一致，审计未读取原源码目录，原历史与搬移源码均未变。SDK27/Unity166前后未变。最终未决97.5440%，无自然语义转换、无物体操作；不是任务成功。并行诊断期间的耗时不能作为性能基准。

完整历史报告对抗：正常视觉复算结束后重新固定原件清单，再复制完整历史。erase_previous_plan和invent_replacement两种字段自洽伪造分别经228.23/207.37秒完整重放，被history claimed result differs from recomputation拒绝；原件清单未变。提前启动而主动中断的旧审计完整保留，不计通过。托管根整体同时被替换仍不在此保证内。

完整封存1,248文件/356,394,634字节，压缩48,530,479字节，SHA256 28bd25e25a1eef66d621d47f11f1f796e900bf95aae1c9c471b9641b75ce546d，逐文件读回核验；仅排除派生Python/pytest缓存。远端完整CI仍在运行，未冒充已完成。
