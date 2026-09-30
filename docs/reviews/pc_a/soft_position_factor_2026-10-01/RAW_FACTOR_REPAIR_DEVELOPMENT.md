# Raw factor 修复开发记录

本记录由实现作者 编写；属于电脑 A 开发验证，不是 R1、R2 或电脑 B 独立验收。真实 96 帧训练/评价/Unity 未由本轮修复执行。原 493e057 失败证据保留，gate 仍等待新冻结源码的顺序双审。

基线 HEAD：`d5dc2432f686132a30fa67259899f831a679bfb0`。本次工作是该 HEAD 上未提交的修复；**不得把开发测试归为这个 HEAD 本身通过**。最终 9 个源/测试文件的逐文件 SHA256 在 `repair-author-source-files.json`，root 后续冻结提交并扩大回归。已明确停止全部 src/tests/tools 写入。

## 实际修复

- ControlledPositionProducer 实现移至 canonical `src/cpswm/system/controlled_position_producer.py`；tools 原入口仅重导出。固定注册分支不能由 proof 指定 module/path。
- owner 配置 profile 保存原 configuration、两模型内容与外 pin、candidate implementation，以及 raw verifier 原文件 SHA。workspace 保存 profile SHA，core 在其外部另保留同一原锚。protected profile 的删除、替换或 missing proof 不会落回 q-only。
- P5 owner 在其真实 cutoff 保存完整 NativeJointContext 原件；payload/envelope/receipt/sampling/depth-unit 的完整摘要另锚定于 core。实际 source、prior、ledger 读取与 catalogue 提交在 core RLock 下。登记前也检查 verifier 原 source 与 loaded implementation。
- deep validate_neural_input_body 对当前/历史实际父链重建 context，先与 owner 保存的 source、cutoff、prior、ledger 相等，再从固定模型和原 RGB-D 重推完整 base。全部 known/unknown/aggregate LL、prior/transition/constraints、完整六维与其他 RB 统计、support/lineage 都比较；不是只校验一个 LL。
- 重算使用新的 canonical candidate，consumed 状态从实际 ancestor source 图推导，不接收 proof 自报的 mutable checkpoint，也不消费线上 producer 状态。
- replay generation 保留原 raw catalogue 的可重算摘要与 archived originals，新代由 owner 内部登记；core transaction 备份/恢复 raw 独立锚。旧 raw 不因撤回被挪到另一 semantic source。
- raw authority 在 ContinuousEvidenceInput 模块顶层固定导入，纯新进程 resume 无需先构造临时 stream。profile_for 对 None/非 neural producer 不导入 Torch，保持可选依赖边界。
- raw 登记位于 pending-step 完成标记之前。若 P5 已运行但登记失败，保留 durable pending 并 fail-closed；**这不是把已执行的物理或语义步骤全部撤销**。

## 文件范围

- `src/cpswm/system/controlled_position_producer.py`
- `src/cpswm/system/native_raw_verification.py`
- `src/cpswm/system/native_neural_production.py`
- `src/cpswm/system/structure_two_particle_workspace.py`
- `src/cpswm/system/prototype_spine.py`
- `src/cpswm/system/structure_two_continuous_input.py`
- `src/cpswm/system/native_joint_replay.py`
- `tools/controlled_position_producer.py`
- `tests/test_native_raw_candidate_verification.py`

## 命令与结果

最终状态上：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' -q tests/test_native_raw_candidate_verification.py tests/test_native_position_production.py --maxfail=1
```

exit 0，**25 passed in 60.56s**；完整输出 `repair-final-targeted-3.log`。包含新增 14 项与原 11 项。9 文件 `ruff check` / `ruff format --check` 均 exit 0，`git diff --check` exit 0；这些简短原输出保留于工具会话，未伪造另一个原始日志。

其中三个专门恢复/依赖用例独立先运行：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' -q tests/test_native_raw_candidate_verification.py::test_registration_failure_retains_durable_pending_and_recovers tests/test_native_raw_candidate_verification.py::test_fresh_process_resume_without_constructing_another_stream tests/test_native_raw_candidate_verification.py::test_non_neural_collection_keeps_torch_optional --maxfail=1
```

exit 0，3 passed in 12.71s；输出 `repair-final-recovery-probes-2.log`，随后也包含于最终 25 项。

中间版兼容集：

```sh
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -q tests/test_native_raw_candidate_verification.py tests/test_native_position_production.py tests/test_native_neural_production.py tests/test_native_neural_recovery.py tests/test_native_joint_full_replay.py tests/test_native_joint_producer_binding.py tests/test_owned_visual_neural.py tests/test_owned_rgbd_support.py tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_round6_prepared_boundary.py --maxfail=1
PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1 /private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -o addopts='' --collect-only -q tests/test_native_raw_candidate_verification.py tests/test_native_position_production.py tests/test_native_neural_production.py tests/test_native_neural_recovery.py tests/test_native_joint_full_replay.py tests/test_native_joint_producer_binding.py tests/test_owned_visual_neural.py tests/test_owned_rgbd_support.py tests/test_structure_two_w3_native_posterior_projection.py tests/test_structure_two_w3_round6_prepared_boundary.py
```

运行 exit 0；`repair-regression-3.log` 显示全部通过。独立 collection exit 0，**166 tests collected**，见 `repair-regression-collection.log`。该 166 项发生在最后 authority import、pending/RLock 顺序、optional Torch 修补之前，**不是最终源码完整兼容回归的替代**；最终扩大回归由 root 接续执行。

## 覆盖的实际后果

- 完整 known LL+2、unknown LL+2、aggregate+2、合法 transition=-2：保留原模型/implementation/dependency，真实 q 核验通过，materialize 完整包后原 owner stage 拒绝；workspace、ledger、producer checkpoint 不变，恢复原 producer pre-state 后合法发布成功。
- 真正执行 neural producer 的 future cutoff 包缺 owner admission，拒绝后原 cutoff 可发布。
- profile None/修改、catalogue 清空、missing proof：当前 stage 与历史读取拒绝，恢复原 owner state 后合法读取/发布。
- selected_index=1 的三步 actual prior：neutral LL 伪造拒绝；真实 neutral 保持全部条件统计，概率在 1e-14 浮点容差内不变；反转 records 字典顺序仍合法。
- loaded raw verifier 替换拒绝，不因已有 q cache 绕过；恢复后合法发布。
- 新进程从原配置/模型/pin/SQLite 恢复，**未构造任何其他 ContinuousEvidenceInput**：精确 view、producer state、workspace、ledger 一致，重复零增量，下一 neutral 保留统计与一条 consumed key。
- 登记 fault 注入在 class method 层：保存 pending、阻断后续 mutation，以原 CIAV context 恢复，effects 表数量不增，随后真实 native 发布成功。这个 fault 恢复是同进程新 owner 对象；新进程恢复的独立用例没有注入同一 fault，不能写成完整交叉矩阵。
- 显式阻断所有 Torch import 的干净子进程中，None 与 legacy JointFixture 两种 collector 构造成功。
- 原 11 项再次通过，含 pre-update Gaussian、完整六维更新、重复消费、防源替换、撤回 replay 与 no-factor baseline 相等、SQLite 恢复、loaded H/helper/producer 修改拒绝、受控 CIAV 映射边界。

## 保留的开发失败

原日志均未覆盖：

- `repair-first-test.log`：新 authority 方法的 future-annotations 编译标志不一致，被 loaded-code guard 拒绝；补齐声明。
- `repair-second-test.log`：replay 对 vars(workspace) 全哈希遇到新增 raw bytes；改为对原 context 重算摘要，原 bytes 仍保存。
- `repair-third-test.log`：该版原 11 项 exit 0。
- `repair-regression-1.log`：新增 transition 攻击 +2 不满足合法 log-probability，先被 schema 拒绝；修成 -2，后续证明到达 raw 重算拒绝。
- `repair-regression-2.log`：测试要求 neutral 权重逐位相等，实际差约 1e-17；改为 1e-14 概率容差，统计仍完全相等。
- `repair-final-targeted-1.log`：fault 函数挂到实例触发 codec 不允许函数类型，尚未到目标 fault；改为 class method 注入。
- `repair-final-targeted-2.log`：pending guard 先报错，测试 regex 原先只接受 durability guard；修正 test expectation。
- `repair-final-recovery-probes.log`：fixture 重新生成随机 CIAV context 导致 pending hash 不同；恢复使用原 context。没有把该 harness 失败写成恢复产品失败。

## 边界与后续检查

这是 owner 配置与接受锚保持可信时的受控代码/输入完整性，不是任意 Python 内存或数据库全部信任根可被篡改时的安全沙箱。只有 canonical controlled raw profile 获得本次完整 base 重算；其他 legacy candidate model 仍保留原合同。

本作者没有执行 root 的 6 项独立数值检查，没有声称完整磁盘+loaded 一起修改矩阵已由本人覆盖，也未把当前/历史/跨进程/故障恢复各维度写成全部交叉组合。真实 private validation 标签未读取调参；无需新科学阈值、正式位置参考或自然身份规则。本修复不证明 natural I 因子、正式 likelihood 校准或动作收益。后续由 root 完成扩大回归、冻结与顺序双审，之后才可继续真实归档数值工作。

## 追加：正常 collector 首次发布边界

前述 25 项之后，外部开发诊断（不是正式 R1）发现正常 collector 的合法首发路径被拒绝：已有 P5 source、尚未 publish，随后 `advance` 返回 None 并推进 cutoff，新的 owner context 未登记。原证据保留于 `RepairR1/dev-first-collector-02.log`，不能用先手动 publish 的测试绕开它。root 在旧 source map 上完成 34 文件回归后，明确授权本小修复；原 `repair-author-source-files.json` 未覆盖。

本小修复只改两个文件：

- `src/cpswm/system/structure_two_continuous_input.py`：None 与重复语义两条早返，在变更 cutoff/persist 之前登记真实 owner epoch。helper 在 core RLock 内先校验原 profile/core 锚与 source catalogue 接受锚；仅在 owner/core 的真实 source 集合都为空时允许无 source 返回。严格 P5 分支仍要求真实 source。不捕获任意 ValueError，也不清除 catalogue。
- `tests/test_native_raw_candidate_verification.py`：新增 None/duplicate 的完整首次 collector 两项、初始真空 source 一项、已存在 source 被移除时拒绝一项。测试实际现有受控 utility/camera，并没有切换效用来制造动作。后续无语义 advance 不重算已发布因子，模型/相机/producer 仍各一次。

命令（cwd 为工作树，环境 `PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1`）：

```sh
/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python -m pytest -c /private/tmp/cpswm-pc-a-soft-position-factor-20261001/pyproject.toml -o addopts='' -q tests/test_native_raw_candidate_verification.py -k 'first_normal_collector or insufficient_initial or removed_owned_source or genuine_network_with_future_cutoff' --maxfail=1
```

exit 0，**5 passed, 13 deselected in 9.93s**，完整输出 `repair-collector-targeted-1.log`。其中一项为原 future direct-stage 拒绝，四项是新增正路径/来源边界检查。两文件 ruff check/format 通过，原输出在工具会话。新的完整 9 文件 source map 为 `repair-collector-author-source-files.json`，其中明确列出相对上一 map 仅这两个文件变化。

完成后再次停止所有 src/tests/tools 写入。root 已开始最终六个完整兼容文件、三个点名 replay/restore 路径及十二项外部检查；本附录不预报这些尚在运行的结果。已发布同 semantic source 的新 raw 更新仍是后续单独任务，本小修复不改变测量消费规则，也不声称新增相机帧已进入 target density。
