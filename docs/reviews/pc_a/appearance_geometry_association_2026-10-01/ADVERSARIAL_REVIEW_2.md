# 第二轮 A 对抗自审

绑定 `5a4e3a0660114b3e7bc5b2482f4d49456b825239`；R1 完成后启动。R1/R2之间没有生产或测试源码改动；926项冻结清单一致。实现方 A 自审，不是独立 B。

`PYTHONHASHSEED=227`，完整命令见 [COMMANDS.md](COMMANDS.md)。范围：`test_owned_position_update.py`、`test_native_raw_candidate_verification.py`、`test_continuous_camera_collection.py`、`test_natural_candidate_position.py`，加新关联 profile 的完整重封读出攻击、已加载解码别名攻击和 replayed 阶段全新解释器恢复。

结果：**62 passed / 526.61秒 / 零失败、零错误、零跳过**。详 evidence/round2.log/xml。全源码 mypy 394无错误，ruff src/tests通过，803文件format通过。未执行全仓测试，不能覆盖历史CI缺口。

第二轮逐项检查：

- 旧受控/自然单候选的原子更新、重复消费、SQLite提交不确定性、原始交付整图伪造、同语义新帧、撤回重放与默认采集器仍通过。新 reference 字段与闭合注册表未绕过原 raw 验证。
- 新关联结果即使内部重新归一化、获得真实神经 q 证明，仍需完整原始观测重建；后验/账本失败后不变，合法重试可用。
- 新的多候选数量和位置条件统计来自第一轮真实检测 montage 正例；第二轮没有把它改称物理仿真正例。
- 三个实际仿真源库的 fresh 复核均读取原SQLite副本，无重新建流/P5/相机执行；两个未知消费恢复摘要一致；空检测那次仍拒绝，物理交付保留，后验/producer/语义/SQLite及原DB摘要不变。
- 原数据上固定模型六帧分数第二次重算逐字段相同。SDK事后诊断与模型输入分开；相机命令成功、尺寸320×320，不能将候选丢失归为已知窗口尺寸错误。源码没有降低检测阈值或导入SDK身份。

**仍开放的 consequential finding**：自然候选供给不稳定，三次诊断没有一个真实已知跨视角匹配。两个试验的 `status=passed` 仅是事务检查；没有位置改善或任务完成。规划器仍选择进一步观察，而 single-pair profile 不支持消费第三帧，所以这里没有宣称长时闭环已闭合。下一步应解决候选稳定性与持续查询更新，不再把更多回执/局部通过数量当主线收益。

全空历史、长期依赖/持续身份、自然初始锚定、正式校准、公平任务收益、异机迁移、完整CI及B复核仍是明确缺口。完整统一框架未缩小。
