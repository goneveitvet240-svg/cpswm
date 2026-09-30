# R1 对抗审查：当前 owner RGB-D 描述接口

**结论：在下列固定信任前提与有界覆盖内通过，可进入顺序 R2；不是完整消费事务或科研验收。** 审查源码为 `6faa17e178ad001de6b5c0e1094f9e62568d7a7e`，903 个 Python 文件与 `frozen-source.json` 逐项一致；四次执行前后和最终检查均 clean、字节未变。审核基于固定本地工作树。root 已另行确认该分支及父文档提交推送成功，本人没有把它当作电脑 B 的独立远端复现。

本轮未参与新增 helper 或测试实现。曾参与上游离线残差模型和数值诊断，因此本报告是电脑 A 的辅助审核，不是电脑 B 独立验收。没有启动 Unity、正式新采集、96 帧真实模型推理或新增训练；合法路径使用真实 owner/planner/Native/SQLite API、受控 RGB-D 相机和小型测试 checkpoint。

## 实际执行

固定 Python `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`，cwd `/private/tmp/cpswm-pc-a-owned-rgbd-descriptor-20261001`。每条 pytest 均显式 `-c <WT>/pyproject.toml -o addopts= -q`，`OPENBLAS_NUM_THREADS=1`、`PYTHONPATH=<WT>/src:<WT>/tests:<WT>/tools`。完整 argv、环境、退出码、日志摘要和前后源码映射保存在对应 `R1/*-01.json`。

| 实际入口 | 覆盖 | 结果 |
|---|---|---|
| `python R1/run_review.py new --attempt 01` | 新增 `test_owned_position_delivery.py` 六项 | 6 passed / 30.34 s / exit 0 |
| `python R1/run_review.py compat --attempt 01` | owned RGB-D、owned visual、joint camera feedback、native position production、native log weight continuation 五文件 | 73 passed / 142.26 s / exit 0 |
| `python R1/run_review.py extra --attempt 01` | 独立完整派生替换和 owner 子图信任边界 | 2 passed / 20.50 s / exit 0 |
| `python R1/run_profile.py profile --attempt 01` | 旧/新 action 分离、完整 core/P5、数据库与 cache 观察 | 1 passed / 6.48 s / exit 0 |

共 **82 项不同测试**。本次没有失败后删改测试、重复计数或生产源码修改。日志保留在 `R1/new-01.log`、`compat-01.log`、`extra-01.log`、`profile-01.log`。这是上述文件与外部检查的有界回归，不是整个仓库测试。

## 正路径与完整伪造后果

- 合法路径经原有 planner 准备 modeled command，owner 执行相机并接受三份 RGB-D/pose 原件，再以 action UUID 调用描述接口；验证完整 parent/source、原 scope、receipt 和 capture/arrival/decision 时间关系。pending、失败、unmodeled、普通 admit/archive、过时 publication/semantic revision/replay 均拒绝。未伪造物理命令或手工发布代替正常 owner 路径。
- 独立攻击逐一替换完整描述的全部 **25 个顶层字段**，保留完整结构并重新计算派生自摘要，包括相机、scope、时间、source、parent、log evidence、decoder/implementation 与权限字段；固定 owner 原件时全部拒绝。另对 **6 个 UUID 字段**使用 UUID 子类完整替换也拒绝。源码六项另外覆盖 bool/int、成员类型、原 delivery 顺序/重复/时间、单侧 pose、深度单位等。
- 每次攻击后比对 owner raw/命令/status/origin、workspace/Native、账本、producer checkpoint、DB checkpoint 及相机次数。恢复原描述后接受，原 current joint view 上的 planner 选择与攻击前相同，相机调用保持 **1→1**，数据库原件字节保持相同。它证明拒绝不会把这些描述成为新消费输入或额外执行相机；**没有证明新位置因子已接入决策或带来动作收益**。
- 有真正独立 Python 子进程仅从复制的 SQLite 与原配置恢复：不先建立临时新 owner、不执行新 P5 builder；重建的描述 SHA 为 `fe9f69561cea0b0be4d219c0419a559127f146e933416f38d40fe39932ef9c15`，与保存描述相同。原数据库前后 SHA 相同。恢复路径包括显示质量为 0 但有限且小于 −745 的 log 权重，未把显示零当作数学消失。子进程命令与脚本在固定 `test_owned_position_delivery.py::test_zero_display_mass_and_real_fresh_sqlite_descriptor`，日志及结果位于 `R1/new-01/test_zero_display_mass_and_rea0/`。

## 实际计算与副作用边界

使用 `sys.setprofile`，未替换被测实现或清空验证缓存。纯新进程 **resume** 阶段调用既有 `score_support` 1 次、旧 producer/condition 各 1 次；之后 first/warm helper 各调用旧 producer/condition 3 次。已签发 underflow 正路径的独立 profiler 明确 first/warm 的 readout 与 condition 各 3 次，所有 action 均为旧 `00000000-0000-0000-0000-000000000385`，没有处理新 capture `449b94a5-40d8-4bbb-bb10-703f75a77436` 的位置读出或似然。

该独立窗口完整 core 的 StateCodec 序列化（含 P5 状态）逐字节相同，原 DB 字节相同，相机调用仍为 1；未出现 measurements、execute、save、persist 或 posterior publication。观察到的验证 cache 项数为 1→1→1。签发可能已预热 cache，**不声称 cold helper 零推理、任意运行时零 memoization、全部进程内存不变**；保留完整旧证据重算。

## 明确接受边界与剩余工作

本接口的根信任是原 owner journal，描述自哈希不是独立的历史执行认证。独立实验先只改 raw 原件，因与原 delivery 不一致被拒绝；随后**一致改写新 capture 的 raw、delivery 和 receipt 相关子图，同时保持原 command 与 origin 不动**，接口可以描述被替换后的 yaw=23。其 `posterior_updated` 与 `consumption_authority` 仍为 False；旧描述相对新日志被拒绝，恢复原日志后原描述合法。

因此，文档中“整个 owner 目录一起改写”不能被解读为唯一超界情况：较小的一致 raw/delivery/receipt 子图就缺少独立接受时锚。本次按 root 明确接受的只读前置接口范围记录该限制，**不将这个接受结果计为攻击被阻止**。若未来发布或消费把描述直接当作不可伪造原观测 authority，必须先补完整 raw observation 事务、接受锚、重复消费/撤回与历史重放；现有 helper 本身没有提供这些保证。

真实相机数据泛化、新 capture 的自然身份绑定、位置后验更新、完整 collector 接线、动作效用、跨机器 B 验收均不在本报告内。顺序 R2 尚需独立执行，本报告不单独授权这些更强结论。

## 可核验证据

- `R1/extra-01/test_every_complete_derived_fi0/field-attacks.json`：25+6 完整替换、合法恢复、规划/DB/相机后果。
- `R1/extra-01/test_one_sided_raw_rejected_an0/owner-boundary.json`：单侧拒绝与一致子图接受边界。
- `R1/profile-01/test_old_proof_action_ids_only0/profile-actions.json`：旧 action 调用、完整 core/DB/cache。
- `R1/new-01/test_zero_display_mass_and_rea0/fresh-result.json`、`fresh.log`：纯新进程与分阶段 profiler。
- `R1/final-source-check.json`：最终 903 文件身份和 clean 状态。
- `R1/evidence-manifest.json`：本报告、冻结/计划锚与 R1 全部原件的 SHA-256；不把包内自摘要称为外部真实性根。
