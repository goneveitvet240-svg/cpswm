# 外观＋三维几何关联开发基线

[草稿 PR #90](https://github.com/goneveitvet240-svg/cpswm/pull/90) 已创建，叠加 PR #89；代码与证据 `bc0fdaa47640729ce6274e7c61a10e3a7da42b89` 已推送，未合并。

用户已同意本方案，先前“待选择关联开发基线”的状态已解除。分支 `codex/pc-a-appearance-geometry-association-20261001`；base `0a5e38c0e59ce2a42342925be7dc5de6fc994c19`（PR #89）；实际功能/测试源码 `5a4e3a0660114b3e7bc5b2482f4d49456b825239`。开工 fetch 成功，集成 `19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`，B `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a`。未自动合并或修改用户原树、STATUS_B。

## 本轮实质变化

此前把首个有效自然检测候选接到受控身份；现在新增显式可选 `AppearanceGeometryPositionProducer` / `appearance-geometry-single-pair-raw@1`：

1. 默认 collector 先接收一个 owner 参考帧，返回 `REFERENCE_ONLY`，不更新后验。
2. 查询帧到达后，从原始 issue/delivery/raw 重建合法参考。需同一原始语义来源、runtime、parent，先于查询决策到达且属于查询 source IDs；不用 caller 指定的框/ID/匹配分数。
3. 重新执行固定官方 SSDLite、RGB-D 表面读出、RGB 直方图/三维几何比较。对参考候选求和、保留每个查询候选及未知分支，进入真实 Native 后验与每个分支的条件统计。检测置信度不充当身份概率。
4. 原观察事务接管去重、回滚、历史 cutoff、语义撤回/重放和 SQLite 恢复；后续语义推进保留各分支。原 natural-candidate / controlled / disabled 对照保留。

方法常量与数学定义见 [METHOD.md](METHOD.md)。它是**未校准整体观测能量**，而非经验独立似然；观测依赖门控没有记成转移先验。同一参考帧不再次计似然。初始“参考候选可能对应语义对象”的锚定仍是受控假设，未冒称家庭级身份识别。

## 实际仿真：事务可工作，真实匹配正例尚未拿到

全部使用原固定房间、320×320 RGB-D/self-pose、固定官方权重/0.5 候选阈值。两帧一组，共 3 次启动、6 次真实模型相机命令、6 帧，RGB 原件仅 5 组不同字节；**只有 1 间房，不能当 6 个独立泛化样本**。SDK 准备动作另存，不计模型命令。

| 诊断 | 自然候选 | 更新结果 | 新进程复核 |
|---|---|---|---|
| 15° → 再转 15° | dining table → bottle | 无同类关联，转入未知；无已知位置更新；下一规划仍想观察 | 实际 DB 直接恢复，视图/语义/update 一致，原 DB 字节未改 |
| 30° → 再转 5° | bottle → bowl | 无同类关联，转入未知；无已知位置更新；下一规划仍想观察 | 同上 |
| 30° → 再转 1° | bottle → 无候选 | 查询计算失败并回滚；两次物理交付仍在，零查询消费 | 实际 DB 直接恢复，再次计算仍拒绝；后验/producer/语义/SQLite 不变 |

后两组是根据前面结果选择的定点诊断，**不是预注册评估，也没有挑选成功角度替代失败**。三组均未完成真实跨视角已知匹配。live/result.json 的 `status=passed` 只指其事务断言；判断关联必须看 association_branches=0 和上表。第三组 status=failed 原样保留，fresh 的 expected_failure_verified 也不能当作关联成功。

离线重算固定模型原始分数：瓶子在约 30° 为 0.514、35° 为 0.439、31° 为 0.258；0.5 阈值保持未改。事后 SDK evaluator-only 记录中 WineBottle 在这些视角仍 visible=true；6 次 actionSuccess 均为 true、尺寸均320×320。该离线标签只用于失败定位，没有送入推断或赋运行时身份。支持的结论是**这一局部序列的自然候选供给不稳定**，不是关联模型泛化、校准或行为收益。

## 工程证据与二轮自审

- 开发验证 3 / 18 项通过；冻结后 R1：21 passed / 349.97 秒，零跳过；见 [第一轮](ADVERSARIAL_REVIEW_1.md)。
- R2：**62 passed / 526.61 秒，零跳过**；见 [第二轮](ADVERSARIAL_REVIEW_2.md)。
- 严格 mypy：394 源文件无错误；全 `src/tests` ruff 通过，803 个文件 format 检查通过。
- 926 项源码/测试/工具清单在 R1/R2 后均一致；最终功能源码未变。
- 两轮均是 A 实现方自审。不是 B、全仓 CI 或独立重建环境验收。core venv 借用本机已有环境；Unity SDK 用既有独立本地 SDK，详 environment.json。

完整 source-bound 单测含：多个真实检测分支（公开图像人工拼接的受控 montage，非实际抓拍）、未知/歧义/数量不变性、完整重封假结果+真神经 q、原参考位姿包整图重封、依赖替换、去重、两处故障回滚、撤回/重放和 fresh 恢复。合法路径与拒绝路径分别覆盖，不以拒绝数量代替全面验收。

## 明确未完成与下一优先项

本 profile 仍只消费**一个参考—查询因子**；第二个查询及跨帧相关性建模尚未支持。仿真只验证下一次决策读到了新状态，**没有执行第三次查询并完成更新**，更没有证明任务成功。全空历史恢复、跨机器旧 DB/绝对权重路径迁移、自然初始语义锚定、长期重识别/记忆、可靠校准及行动收益保持开放。全仓工程验收和 B 复核也未完成。

下一步主线应先处理**目标候选在相邻视角丢失**：冻结并保留这批 RGB-D 失败序列，评估能维持候选支持且保留未知的参考引导方案，再扩展第二、第三次查询事务。不能先用降低阈值、选角度或扩大测试计数来宣称闭环理想运行。完整 H/R/I/C/Z/r/V、三个 RB blocks、七算子及隐藏事件/多人/可逆记忆研究范围未缩小。

## 证据位置

`evidence/round*.log/xml` 为逐项测试；frozen-source 与 source-check 为源码清单；live*-summary/log、fresh-verification、detector-score-diagnostic、offline-sdk-visibility 区分事务、匹配与离线定位。`live-transactions.tar.gz` 保留三个真实运行的原始 SQLite、全部 SDK 数据、q checkpoints、完整诊断及恢复结果；省略已验证相同的 copy.db 副本。官方 SSDLite 外部权重按源码全 SHA 固定，未重复提交。

脚本保留在 evidence，运行根目录为该源码工作树；`PYTHONPATH=src:tests:tools`。重放已绑定当前源码及绝对模型路径，不承诺任意源码或异机直接恢复旧数据库。
