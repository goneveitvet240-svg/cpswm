# 同语义后续 RGB-D 的单测量 Native 更新事务

功能源码：`d84d570d0c12ec56d5f47f699f7211ffd99422b9`。分支 `codex/pc-a-owned-observation-update-20261001`，base `cab777ff69c250696611a65e387aa305f7b5f30d`。集成基准 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`、B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` 已 fetch 核验。原用户工作树及 STATUS_B 未修改。

本轮直接补同一语义 S 后的 owner-issued RGB-D A 消费事务。新 profile `owned-single-position-raw@1` 在语义发布时产生中性 Native 状态；物理观测返回后，按实际父簇有限对数权重，更新 known/unknown/aggregate 及位置条件统计，再发布供下一决策使用的视图。原分类对照保留；该位置 profile 不同时叠加同图分类似然。

## 接口与事务

- `ContinuousEvidenceInput.consume_owned_position_observation(action_id)` 只接受原 owner 发出的成功观测，复核独立保留的命令/父状态/来源/交付锚点，完整重算 RGB-D 因子与神经证明。
- 首次消费原子更新；再次调用同 action 返回相同逻辑回执，不追加证据或重发相机。第二个新 measurement 明确 unsupported。此限制不代表缩小完整研究框架。
- 计算失败恢复后验、条件统计、账本、producer 和 owner 发布状态，保留已发生的物理 delivery。SQLite 保存前后不确定故障会封锁当前实例，依据实际数据库恢复后决定首次消费或去重，不伪称撤销外界动作。
- 重放按语义更新及观测更新的原序列执行，同一语义可以对应多个更新簇；每步使用原历史 cutoff 和新实际父状态。撤回 S 同时去掉 A；撤回其他 S 时重新计算保留的 A。
- 默认 posterior collector 已接线；不必人为制造另一条语义转移来触发更新。

## 可重复检查

工作目录 `/private/tmp/cpswm-pc-a-owned-observation-update-20261001`；证据原目录 `/private/tmp/cpswm-owned-observation-evidence-20261001`。`.venv` 借用现有完整开发环境，不是独立重建环境。两轮均为实现者 A 顺序自审，不是独立 B 验收；仅相关范围，不代表全仓通过。

严格类型检查：`.venv/bin/mypy`，391 个源文件无问题。`ruff check src tests/test_owned_position_update.py` 通过；系统目录和新增测试格式检查通过。冻结前开发失败及修正日志保留，不能计为正式通过。

顺序第一轮 32 passed / 396.69s；第二轮 `PYTHONHASHSEED=193` 为 44 passed / 215.92s。均无失败或跳过。两个集合有重叠，不将次数相加视为独立覆盖。详 [R1](ADVERSARIAL_REVIEW_1.md)、[R2](ADVERSARIAL_REVIEW_2.md) 和 evidence 中原始日志/JUnit。1020 个已跟踪源码、测试、工具及所列配置文件摘要冻结前后相同；这是明确路径清单，不代表所有仓库文件。

## 覆盖和边界

合法路径包括中性语义→真实 owner 命令→受控 RGB-D→真实网络 q→位置后验→下一决策来源，以及 SQLite 新解释器首次操作直接恢复、撤回保留/删除观测、闭式 Gaussian 算术、无因子对照。攻击包含真实神经证明下完整伪造 known/unknown/aggregate/transition、整份 packet/receipt/catalogue 重写、重复消费、事务故障及持久化前后不确定故障。逐项以测试和日志为准。

身份、固定候选框/seed、Gaussian 先验、unknown 密度、残差模型及动作效用仍是显式受控开发条件。本轮不证明自然身份、可靠校准、多帧独立性、跨房泛化、长期记忆收益或实际任务成功。全空保留历史仍不支持；历史旧版本持久化状态没有跨源码迁移验收。现有全仓 CI 和旧验收回执缺口不因本轮局部成功关闭。

下一主项是以冻结版本验证真实仿真新输入确实进入事务，再将自然候选/身份不确定性接入同一接口，随后做固定任务、匹配预算的行为收益比较。多个相关帧如何联合计证据需显式模型，不能简单重复首帧似然。

## 实时 Unity 单次接线验证

双审后运行冻结源码，第一尝试 `live_probe.py` 在 READY 前 45 秒超时，未发出相机命令。只读 import traceback 停于旧 `.venv-ai2thor` 文件读取；该依赖目录存在 iCloud dataless 占位文件。控制器完整导入实际 122.173 秒。原失败日志和数据库保留，不计成功，不提高超时或修改生产实现。

新建 `/private/tmp/cpswm-ai2thor-owned-20261001`，按原环境版本约束安装 27 个 SDK 依赖，导入 1.866 秒。第二次是新 scene/runtime/数据库，非重发旧命令。SDK 5.0.0、Python 3.11.16、Unity 构建 f0825767、320×320 RGB-D/self pose；原45秒门槛不改。启动器/环境约束/冻结依赖与首失败见 evidence。

`live_probe_local_sdk.py` 实际通过：默认 collector 选择 RotateRight 30°，唯一 owner command `17c3a648-5e82-4c0a-9d6c-2dd08f9a77d7` 成功；新 RGB-D 进入真实位置后验，semantic hash 不变，重复消费无副作用。下一 problem 绑定更新后视图并真实执行 planner，should_act=false，原因是该受控效用认为继续观测没有增益。不存在第二次模型驱动物理动作，也不能将停止解释为任务已成功。

SDK 轨迹有初始事件及 PausePhysicsAutoSim / Pass / Pass 三次准备动作，再加一次模型选择的 RotateRight；不能把准备动作算成模型动作。原始 SDK/私有 evaluator 日志只用于验证动作轨迹，未作为自然身份/位置输入。位置输入为公开 RGB-D，候选仍是预先固定的 4×4 左上角区域及正确关联假设；这不是从真实图像识别目标。

`live_fresh.py` 在新解释器 `PYTHONHASHSEED=102731` 上直接恢复实际 live DB 的副本，不构造传感器、不重跑语义生产；实际 posterior digest 与 live 结果一致，重复消费数据库不变，原 DB 完整字节摘要未变。结果见 evidence/live-fresh-verification.json。两次 runtime、raw DB、模型、SDK 原始轨迹归档在 evidence/live-transactions.tar.gz，脚本以实际绝对路径记录，异目录复现需显式改路径。

本轮因此支持“受控条件下，一次实时观测驱动的工程闭环及恢复”。它不支持自然多步任务闭环、泛化或效果改善结论；下一主项仍是自然身份/候选及相关多帧因子接入，然后评估行为收益。
