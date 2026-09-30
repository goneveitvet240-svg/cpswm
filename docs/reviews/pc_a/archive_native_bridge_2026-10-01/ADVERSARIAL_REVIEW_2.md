# 第二轮对抗审核：真实父包数值重算、公开映射及保存状态

结论：**本报告所列有界范围 PASS，未发现新的产品阻断。** 这是电脑 A 辅助第二轮审查，不是电脑 B 独立验收，也不是自然身份关联、独立校准或动作效用验收。真实的新 archive bridge / bare 实验由根任务在双审 gate 更新后另行执行；本审核没有运行它们。

## 源码与顺序绑定

- 当前冻结工作树：`/private/tmp/cpswm-pc-a-archive-native-bridge-20261001`，HEAD `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，`src/tests/tools` 共 901 个 Python 文件。各执行前后逐项匹配 `frozen-source.json`，HEAD 不变、git clean；未修改产品源码。
- 先核对已停止写入的 R1：报告 SHA256 `0acac1f1ce90a19af16fa1fe7553e7d68f0523d6909bfb547d63a2d7e95b1a9e`，manifest SHA256 `96bedfefc4b6db0663de128460da238a5db2ab40fc3e159f9e3e008a237effe3`；9,062 个文件、单列符号链接及 4 项外部锚全部核对。最终再次检查原件未变。
- 审查者未编写本轮生产 helper/bridge/bare 源码；参与过只读方案准备和上一轮 helper 绑定诊断，明确披露。远端已推送依据根任务交接；本轮结论直接绑定本地完整 SHA/map，不声称独立刷新了最新远端。
- 所有新证据仅在 `R2/`；原 R1、旧 SO 和实际采集原件只读。固定解释器为 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`。

## 实际执行与计数

**最终 11 项 pytest 通过**：`integrity-02` 为 10 passed / 174.08 s；`private-selection-01` 为 1 passed / 1.64 s。另完成旧真实 302-member parent 的原外 pin 拒绝、新 self-ledger pin 下历史深层拒绝、原包完整 fresh 接受三项检查；不把这些混报为 pytest 数量。

执行入口（`R2` 为本证据目录的绝对路径，`PY` 为上述固定解释器）：

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 PY R2/parent_attack.py prepare
PY R2/run_stage.py parent-forged 01
PY R2/run_stage.py parent-legal 01
PY R2/run_stage.py integrity 02
PY R2/run_stage.py private-selection 01
```

前一个准备命令在冻结工作树执行。runner 中的 pytest 均显式使用 `-c /private/tmp/cpswm-pc-a-archive-native-bridge-20261001/pyproject.toml -o addopts=`，独立 basetemp，`--maxfail=1`。每阶段外层超时 720 s，超时会终止该阶段自己的进程组；本轮没有超时。每次实际 argv/cwd/environment、日志 SHA256、前后源码 map 和耗时见对应 `.json`。真实历史 CLI 的完整白名单 argv、固定路径和外部 pins 另见 `historical-commands.json`。两条父包验证并行读同一原件，不修改它们。

保留失败尝试：`integrity-01` 输出 9 passed / 1 failed，但不计入最终计数。外部审计钩子在 selector 阶段结束后仍启用，把后续源码 `handover_phase_supervision.py` 误当私有数据；其中若干负例也可能因该钩子得到错误拒绝理由，故整组重新运行。原脚本在 `attempt01-harness/`，原日志和数据目录保留；修正只限定钩子作用域，并将保存包负例限定为产品 `ValueError`。另一个 `private-selection` 启动路径拼字错误在 Python 打开脚本前 exit 2，记录在 `private-selection-launch-01.json`，没有执行测试。均为 harness 问题，没有修改产品。

## 1. 完整真实父包：自签通过后必须重新拟合

原父包为 `output/soft-position-factor-20261001`，外部 ledger pin `9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc`。固定真正历史源 `/private/tmp/cpswm-pc-a-soft-position-factor-20261001` 及原 controls/affinity/frontend/collection pins；没有采用 R1 controlled/fake SDK parent，也没有替换历史验证 CLI 或让 ledger 中的任意命令执行。

在新副本中给全部可用 public world points 和 observations 加 `[0.41,-0.23,0.19]` m，保留原 RGB-D、相机、候选、私有目标和完整 96 帧顺序。重新生成四模型训练 residuals/members、labels 的 readout 摘要、模型及 pin、corrected、train/validation/逐屋/对象帧统计、controlled consumption、report members 和两条 ledger 的完整 output map。保留全部 302 成员，188 个成员字节改变。

构造阶段复用 `build` 的派生产物逻辑，只在该构造调用中令 `collect_public` 返回已平移的完整读出、`private_readout` 返回原标签及更新后的读出绑定；两个回调随后恢复。它们没有进入被测 `verify_position_parent` 或任何历史子进程。每个模型都重新 fit 2,004 个训练 residual，独立断言均值、协方差与新模型一致，bias 相对原模型增加指定向量。例如 soft-affinity / transform 的 bias 从 `[0.0325811061,0.3936195430,0.0420329250]` 变为 `[0.4425811061,0.1636195430,0.2320329250]`。原始深度没有变化，所以这仍是有意错误的几何派生数据。

三个层次的实际结果：

1. 保持调用方原 external pin：`position ledger pin differs`。这是外部锚拒绝，**没有计作数学重算**。
2. 改用新完整 self-ledger pin：`_inspect` 接受其来源声明、成员集合、完整 report 和四模型状态；随后真正历史 CLI 重算原 affinity 及三种 controls、96 个公开位置读出、四模型拟合和统计。最后在 `save_or_verify` 以 `fresh trained outputs differ` 拒绝，外层收到 `historical position fresh refit failed`。用时 385.46 s（runner 386.58 s）。这是从原数据重新得到预期数值后比较完整产物的拒绝，不能简化成原 ledger hash 拒绝。
3. 未改原包完整 fresh：接受 302 成员，用时 385.52 s（runner 386.50 s）。原包及原祖先保持不变；验证过程没有采集新帧或启动 Unity。

细节见 `parent-forgery-construction.json`、`parent-forged/`、两个 `parent-*-result.json` 和真实历史日志。

## 2. 全支持重算与私有 seed 偏好

- 在受控完整 RGB-D/readout 上，使用 soft/uniform 两套归一系数的共同零空间改变三个支持点；两个 estimator 的代表 XYZ 在 `1e-12` 内保持不变。`correspondence` 从原 RGB-D 重算 single-candidate 全支持后，以 `full neighborhood correspondence differs: world_points_m` 拒绝。它确实检查了支持点，不只检查代表 XYZ。
- 分别修改完整 raw/normalized/total 系数、candidate 来源成员和 pixel grid 顺序，得到 `complete seed weights differ`、`source membership differs`、`... pixels_uv`。每例随后用原完整数据重新建立合法对应，raw packet binding 前后不变。
- selector 调用窗口内的文件审计没有私有数据读取。另一项检查实际读取受控 private labels，选择一个 eligible 且不同于公开首点的 seed，证明它自身可以有合法几何对应；将其完整 seed/observation 列表重新排序企图成为首点时，`first_seed` 重新生成全部公开读出并拒绝。原顺序恢复后通过；扩大私有 eligibility 会改变 labels，但公开选择不变。
- **边界明确：** `correspondence` 单独接受其他合法 candidate/seed 的几何对应；公开首点策略属于上游 `first_seed`。不能声称每个 helper 都单独拒绝所有合法替代点。本轮没有利用私有误差选出所谓最优自然 seed，也不以 private label 推断自然身份。

## 3. 完整保存包改动、恢复与数值后果

复用 R1 同 SHA 的完整 8-arm Native fixture，复制到 R2 后才改动。原件已包含实际 active→neutral→撤回、16 次 fresh SQLite 子进程的结果；本轮不重复其全部昂贵 arms，也不把这些 R1 次数计作新增 R2 次数。

四种新修改均保留完整成员集合并重签 `members.json`：

- 改保存 seed 配置，或改 synthetic 语义时间；重算 configuration `source_identity`，同时更新 SQLite checkpoint/deployment 的本地 source 列。仍由原输入生成的 expected configuration 在 `saved owner configuration differs from original inputs` 拒绝。此为输入/配置边界，不称为位置 likelihood 深层重算。
- 改完整已保存 Native 条件统计的 information vector，重新 StateCodec 编码并更新 SQLite document digest。恢复时以 `raw candidate source, cutoff or prior differs from owner admission` 拒绝。这里保留了原 owner 锚，没有把 source/prior 拒绝说成已通过全部原始数值复算。
- 将完整类型的归档 command 及其内容摘要放入保存的 issued-command 表，补相应 status，再重编码并重签 DB。恢复后的保存包检查以 `saved archive has camera commands` 拒绝。未调用执行器，物理 camera commands = 0；该结果证明本桥接保存包禁止此变更，不声称通用 SQLite 恢复入口本身能够认证任意离线改写的命令来源。

随后真正恢复未改完整 8-arm 包，验证当前 known/unknown/aggregate 概率及原始 normalized log weights、完整 6D information matrix/vector 和其余统计，duplicate publication 不改变 workspace/ledger/view/producer。所有原 DB 文件保持字节不变。另在一份恢复后的 active-arm 副本上继续撤回后的下一 neutral（index 4）：数值状态保持一致，consumed keys = 0，issued camera commands = 0。它是对实际恢复运行时的后果检查，不是仅比较 JSON 摘要。结果见 `integrity-02/**/result.json`。

## 覆盖限制与交付

本轮对真实旧父包执行完整历史重算；新 Native 后果仍是受控 RGB-D/语义/残差模型 fixture。没有运行当前新真实 archive bridge 或 bare CLI；没有新增真实 camera 动作、自然 I/world 身份、独立误差校准、online next-observation 事务、任务成功/动作效用、长期泛化或全仓回归。未选择正式位置参考或获胜 estimator，四组合范围保持完整。

本轮没有再次执行旧 R2 的完整后代 q/history 重签矩阵，也没有对每个内部 owner 锚被同时改写的组合穷举；保存状态负例的拒绝层已逐项说明。实际恢复走生产 resume/raw-owner 检查，但本轮没有额外 profiler trace，因此不把每次恢复概括为独立的逐函数数学审计。整体科学验收仍是 partial coverage。

`R2/final-check.json` 记录最终 901 源码、R1 全封存及真实父包 302 原件复核；`R2/evidence-manifest.json` 对本报告与新增脚本、日志、保存包、失败尝试逐项封存，符号链接单列不跟随。封存完成后审查者停止全部写入；review-gate 由根任务更新。
