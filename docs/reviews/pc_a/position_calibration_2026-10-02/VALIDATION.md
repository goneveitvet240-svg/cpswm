# 电脑A局部验证范围

最终功能 SHA `27d396d6db4c248992f37285d3b7ad42b20df408`。本页是具体文件/测试范围记录，不是B审查、全仓统一验收或科学收益证明。

| 检查 | 实际结果 | 来源与范围 |
|---|---|---|
| 新拟合/公开预测/隔离评分初版 | 26通过，9.28秒 | `4d1082a16ed043bddb88747b1832cd6dfedafacc`，`review-r1.log` |
| 新路径最终检查 | 27通过，10.84秒 | 最终27d396d对应文件，`review-r1-final.log`；增加已有账本不覆盖 |
| 旧报告与连续事务兼容 | 49通过，885.63秒，零跳过 | `review-r2.log`；报告、owner报告、temporal三文件；见下文版本范围 |
| 类型检查 | 399个source文件无问题 | 最终源码，`mypy.log` |
| Ruff/格式 | 通过／816文件符合 | src/tests与本次两个tools，`ruff.log`、`format.log` |
| 最终实数据run/fresh | 6个独立步骤退出码0，四JSON逐字相同 | `execution-ledger.json`、`fresh-equality.json`，最终27d396d |
| 独立算术 | 6模型、12分布、269760预测、120组计数一致 | `independent-check.json`，不导入拟合/后验实现 |
| 原自然归档两次重建 | public/result逐字相同，0新动作 | `surface-equality.json`；原ccccacc8 core，探针工具4d1082a后不变 |

R2启动于4d1082a冻结后，期间只改了外侧 `tools/run_position_calibration.py` 与其专用 `tests/test_position_calibration_driver.py` 的输出防覆盖逻辑。R2所测src、三份测试及其原有辅助代码均未变化，399个生产模块逐文件相同；修改的两个文件由最终27项另行检验。**不把这组证据写成“完整仓库同一SHA两次独立审查”。** 其他审查者需绑定最终交接head重新审查，旧审查不自动升级。`frozen-source-before.json` 与 `source-unchanged.json` 记录最终933份src/tests/tools文件，最终实数据前后未变。

新增正路径包含训练分区拟合、公开坐标转换、全高斯联合结果、公开预测与含边界评分。反例覆盖完整重签坏分区、重复/缺失帧、缺消融臂、NaN、反向盒、读出模型错配、外部pin替换，全部保留合法重试；验证标签改变不改变模型或公开预测，密集对象重复样点不夺取额外对象权重。已有账本不覆盖检查是实际发现后追加，初版26项不冒充覆盖此行为。

旧兼容回归包含未知分支、相同图像不重复加证据、原子失败回滚、完整似然/统计伪造、SQLite恢复、语义撤回和第一/中间采集撤回后重放。它保持旧受控模型，**没有验证本次新校准模型进入Native**，也没有新真实多步相机闭环或任务收益。旧真实WineBottle仍为原先停止的一帧，无新增动作。

封存tar SHA及各成员摘要在 `position-calibration-frozen.info.json`。13,629,006字节，SHA256 `74d303fce744285ca8d5a98fd3f8d69bd5fbd15f5f2a5c40f6bb40ac92640489`；10个成员逐个回读校验，内容再次核对与最终27d396d实跑产物一致。未重复放入字节相同的fresh结果；未把父轮302份原件或旧SQLite重新伪装成新采集。

开发期被中断的慢prepare没有完成产物，原日志保留。图片缓存不可写后由Matplotlib自动使用临时目录，仅影响诊断绘图，不进入模型或评分。当前没有完整B矩阵、所有依赖攻击、全仓CI或独立未曝光数据，覆盖状态明确为部分。
