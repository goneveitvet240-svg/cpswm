# 第一轮对抗审核：归档桥接与 bare-seed 诊断

结论：**所列有界范围通过，未发现新的产品阻断；可以进入同 SHA 的第二轮审核。** 本结论不授权跳过 R2，也不等于真实归档实验、自然身份闭环或电脑 B 验收。

- 冻结源码：`82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`；工作树 `/private/tmp/cpswm-pc-a-archive-native-bridge-20261001`。审核前后 HEAD 一致、git clean，`src/tests/tools` 共 901 个 Python 文件逐项匹配 `frozen-source.json`。
- 审核人未参与本轮 6 个新增文件实现；此前参与过 position residual model / numeric diagnostic，因此仍披露旧组件作者重合。本轮为电脑 A 辅助复核。
- 远端：根任务声明该 SHA 已推送。本审核 `git fetch origin --prune` 因共享 Git `FETCH_HEAD` 写权限失败，未亲自完成远端刷新；不把本地缓存称为最新远端。
- 环境：Python 3.13.5，固定虚拟环境 `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`；`OPENBLAS_NUM_THREADS=1`，`PYTHONPATH=WT/src:WT/tests:WT/tools`。环境原件见 `runtime-environment.json`。

## 实际执行

| 执行 | 结果 | 证据 |
|---|---|---|
| 本轮 `test_archive_native_bridge.py` 全集 | 13 passed，442.50 s | `R1/bridge-02.log`、`.json` |
| 父包、bare、surface、dataset、position、native log continuation、native position 共 7 文件 | 160 passed，138.78 s | `R1/extended-01.log`、`.json` |
| 新增完整保存包后果攻击与合法恢复 | 7 passed | `R1/additional-01.log`、`.json` |
| 当前 bare 顶层 CLI：合法 run → 全数值产物重签 verify → 合法 fresh verify → 父原外 pin 拒绝 | exit `[0,1,0,1]`；103 成员 | `R1/BareCLI/*-01.json`、日志、`attack-results.json` |

**共 180 项 pytest 通过，另有上述 4 次实际 bare CLI 调用。** 全部 pytest 显式使用 `-c /private/tmp/cpswm-pc-a-archive-native-bridge-20261001/pyproject.toml -o addopts=`，未执行会覆盖根任务日志的脚本。完整 argv、cwd、环境、退出值、前后源码和日志哈希保存在每项 `.json`；调用入口为：

```text
PY R1/run_stage.py bridge --attempt 02
PY R1/run_stage.py extended --attempt 01
PY R1/run_stage.py additional --attempt 01
PY R1/prepare_bare_cli.py
PY R1/run_bare_cli.py legal-run-01
PY R1/forge_bare_and_verify.py
```

启动桥接的第一次 Python 路径拼字错误在 harness 执行前 exit 2，原始命令与错误保留于 `R1/bridge-launch-01.*`；修正后为独立 attempt02。没有生产测试失败、没有修改冻结源码。`prepare-bare-01.*` 保存准备命令和工具返回；各攻击均操作新副本，旧封存输出及本轮原输入前后字节一致。

## 正路径与后果

1. **实际 Native 消费、连续状态和撤回。** 受控 RGB-D/camera/候选和合成残差模型经过公共完整邻域读出、single-candidate 对应、`ControlledPositionProducer`、Native publication、真实 6D 条件统计、known/unknown/aggregate 归一化权重。四估计器/参考组合各有 active 与 no-factor，共 8 arms。独立 `solve/slogdet` 公式核对更新前 likelihood、完整 normalizer、precision 和 information vector；active 数值改变，其他块与无因子对照按固定协议核对。
2. **16 次真正 SQLite 新进程。** 每 arm 分 active 和 retracted 两次子进程：校验原快照、重复发布不变、neutral 延续不重复消费。撤回原语义源后走既有 replay，消费键归零，所有 after-retraction 数值等于对应 no-factor。16 份配置/结果/日志及可重建实际 argv 的 pin 明细见 `R1/native-subprocess-evidence.json`。全程 physical camera commands = 0；没有把归档 action ID 伪装成新发物理命令。
3. **原始 scope/time 与原件保护。** 适配的是受控语义 fixture 的 scope 与时间，原 raw delivery、RGB-D/camera 包绑定不变；full 与 single provenance 的 seed ID 不同则保留二者，逐像素支持、系数和观测对应完整比较，不凭 XYZ 相同认定同一证据。已保存 DB 的复核只在临时副本上 resume；8 arm 原 DB 及整个保存目录校验前后字节一致。
4. **bare 真实数值流程。** 新顶层 CLI 从 302 成员受控父包进入固定旧源码的 position `--verify`，真正重算三组 affinity controls、96 个公开读出和四个 position models，再构建 bare 的两参考训练/预测/报告。没有替换本轮几何、拟合、汇总核心。保留 96 帧，其中 8 空帧；每参考训练 8064 个监督 seed / 56 非空帧 / 7 有监督屋 / 14 对象 / 112 对象帧，validation 4608 / 32 / 4 / 8 / 64；与父 soft/uniform 同分母。配置仍为 8 train + 4 validation 屋，空屋不被替换。VOID、双标签严格对应、同像素不同邻域不误合并、公开读出先于私有评价、train-only 拟合、rank/样本不足 fit_failed 保留分别由定向测试覆盖。
5. **父包外部 pin 与历史白名单。** 固定外 pin 绑定恰好两条成功 run/verify 记录和 302 精确成员；源码 map、祖先四项 pin、load 时原成员 bytes 复核；历史子进程只运行固定 `run_soft_position_development.py` 和显式白名单参数，不执行账本命令。虚拟环境入口保持 absolute、不 resolve 成系统 Python。非零子进程、bool/int 状态混淆、源/成员替换、符号链接及祖先变化有实际拒绝与原件恢复检查。

## 完整伪造路径

全部先有合法完整包，保留配置、产物集合和可解析格式；保存包攻击额外重签 `members.json`，证明单独的自签成员检查可通过，再到实际后果验证：

- 有限 known/unknown/aggregate 诊断 likelihood 同加常数，保留所有字段与类型：拒绝于 fresh active diagnostic 比较。
- `active: true` 改为数值 `1`：规范内容哈希拒绝，不用 Python 的 bool/int 相等冒充严格 JSON 一致。
- 将终态数值已同为 no-factor 的另一 arm SQLite DB 完整移植到 active arm：拒绝原 source/dependency 绑定。
- 增加成员、删除一份历史日志并同步重签：拒绝与完整 fresh 包的精确成员集合不一致。
- public correspondence 的 full seed 身份替换并重签：拒绝原公开桥接输入比较。
- 上述攻击后再次用未改合法保存包复核全部 arms；原 DB bytes 不变。
- **全 103 成员数值攻击：** 对全部 bare 原点施加 `[0.41,-0.23,0.19]` m 平移，同步修改双模型 bias、训练 residual 数组和 train/validation/逐屋统计，保留 corrected 输出，并验证残差均值/协方差与伪模型一致，重新签完整 report members。原父外 pin 不变，当前 CLI 经完整历史重算后以 `fresh trained outputs differ` 拒绝（exit1）。合法包随后 fresh exit0、103 原成员逐字节不变。
- **完整父包重签：** 改双参考标签、重签父 report 与两行账本、保留调用方原外 pin；在 `position ledger pin differs` 处拒绝（exit1）。这是信任锚拒绝，未伪称该 case 已到数学核对。

逐攻击拒绝理由与保存目录哈希见 `R1/additional-01/**/attack-result.json`；完整数值攻击副本与新自签账本保留在 `R1/BareCLI/forged-output*` 和 `forged-parent`。

## 覆盖限制

- Native 完整正路径的公开输入、候选、残差参数和语义关联均为受控 fixture。bare 的 96 帧源自上一轮封存受控包，明确含 fake SDK / controlled historical wrapper；本轮确实重新执行了固定历史 position CLI，但不是官方 SDK 再采集或真实 96 帧科研结果。
- 本轮没有对真实父包运行顶层 archive bridge，也没有启动 Unity。`select_input` 固定原 affinity pin、真实归档公开帧选择和祖先接线做了源码阅读，完整受控 `run_comparison`→Native→SQLite 已执行；这两个层面不冒称为一条已经运行的真实归档 CLI 链。真实 trained model 单 capture 桥接须 R2 通过后由根任务运行并 fresh verify。
- 验证保存 DB 当前 owner 状态、diagnostic 数值、配置和精确成员集合；不主张每份历史 stdout、incidental runtime UUID 都独立认证。fresh 当前重建与受保护 owner state 才是本轮后果依据。
- 没有自然 I/world 身份、独立误差校准、多邻帧独立似然假设、在线新增观测事务、动作效用/仿真任务成功、长期泛化或全仓完整回归证据；也没有选择正式位置参考或优胜估计器。两参考/四模型分别保留，失败模型不替补。

`R1/final-source-check.json` 记录最终源码与旧原件复核；`R1/evidence-manifest.json` 对本报告、脚本、日志、配置、数据库、完整产物及保留失败记录逐项列 SHA256（符号链接单列且不跟随）。交付后审核人停止写入，等待同 SHA 顺序 R2。
