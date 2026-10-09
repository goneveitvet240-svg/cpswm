# 参考特征几何核验修复报告（2026-10-09）

## 结论

本轮修复达到了预声明的局部目标：在同一冻结三帧、同一三动作预算和同一严格未扩张 AABB 评分下，PR100 中两次错误的 re-identification（重识别）接受降为 0；原先 LOST 的 `dining table` detector anchor 在首帧实际锚定的 `Kettle|surface|2|6` 于 step 1 正确恢复身份和位置，并在 step 2 保持正确。完整重复候选控制继续输出 `UNKNOWN_AMBIGUOUS_REIDENTIFICATION`，两次重放逐字节一致，原三个查询槽无退化。

完整 matched transition death test（匹配过渡死亡测试）仍为 **FAIL**。查询仍固定为 `bottle:0`、`bottle:1`、`bowl:0`，本轮自然恢复的 kettle 不在查询集合中，所以旧版与最终修复版的查询身份、位置、联合成功仍同为 `7/9、6/9、6/9`，`query_level_joint_gain=false`。因此不启动完整 S1 fixed/active/no-update 与 retain/withdraw 矩阵，也不把局部身份修复写成主动观察已有任务收益。

## 最终方法

- `InitializedPixelTargetTracker` 在整体 box 越界但当前 LK forward-backward（前后向光流）仍有效时，保留仅限本次相邻帧的 feature ID 与像素对应；真正 LOST 后的下一帧清空该通道，禁止跨缺口补接。
- 首帧围绕公开表面读点保存最邻近的既有最小四点 cohort（局部特征组）。候选同时通过原外观—几何能量、四点候选 mask 支持、`FB ≤ 1.5 px`、有效公开深度和既有 `0.5 m` 几何尺度才可接受。
- 重初始化只使用四个已核验原 feature ID，不再在完整宽语义 mask 上重新抽取新角点。缺谱系、少于四点、无有效深度、几何失败、多个候选或共享候选继续 UNKNOWN。
- 接受时选择三维残差最小的 cohort feature，并在后续帧保持这个 feature lineage（特征谱系），避免切换到残差更小的静止背景点。亚像素边界只在该 feature 的 floor/ceil 四邻域中，用公开 RGB-D 世界点残差确定像素；SDK 真值没有进入推理。
- 普通未发生重识别的连续轨迹沿用原 mask 概率读点规则，避免修复改写 bottle/bowl 查询位置。

## 保留的失败迭代

| 精确源码 SHA | 结果 | 暴露的问题 |
|---|---|---|
| `d75865c4d088c8e750377693a5948a5c01bab224` | 查询 `7/9、3/9、3/9`；kettle 仍误报 countertop | 在全部 80 个宽区域特征中取最小三维残差，静止桌面占优，并使正常查询位置退化 |
| `8cc7f29d52a286123df169258d2a64db6acd054e` | 查询恢复 `7/9、6/9、6/9`；step 1 kettle 正确，step 2 又变 countertop | 四点局部 cohort 修正首次恢复，但后续帧重新选择最小残差 feature，身份漂到静止背景 |
| `bce135bfa2da89bbc7307ec42501bd77d0d0331a` | 查询 `7/9、6/9、6/9`；step 2 仍误报 countertop | 已固定 feature ID，但亚像素坐标从 `114.52` 四舍五入至相邻 countertop 像素 |
| `8acab228c6cdaa85865088f73c82b9455fb3fea1` | 查询 `7/9、6/9、6/9`；step 1/2 kettle 均正确 | 最终实现；用同一 feature 的公开深度残差解决亚像素边界 |

这些失败输出和评分均保存在 [`evidence`](evidence)；没有删除、覆盖或改名成成功结果。

## 冻结门结果

| 门 | 结果 | 证据 |
|---|---:|---|
| 候选两次逐字节确定性重放 | PASS | `subpixel-a.json` 与 `subpixel-b.json` SHA 均为 `4c9e8590d11c41b3e3083832c195581e29f0aa90ec01fec1800e424d0814340b` |
| 自然 LOST 后身份＋位置联合恢复 | PASS | step 1 报告 `Kettle|surface|2|6`，identity/AABB/joint 均 true |
| 恢复后下一帧保持同一身份＋位置 | PASS | step 2 同一 anchor 仍为 kettle，identity/AABB/joint 均 true |
| 错误重识别为零 | PASS | `false_reidentifications=[]` |
| 接受的重识别均可评分 | PASS | 1/1 有 SDK 离线身份和 AABB 真值 |
| 原查询无退化 | PASS | `query_regressions=[]`；旧版与最终版联合成功均 `6/9` |
| 完整重复候选保持 UNKNOWN | PASS | step 1 为 `UNKNOWN_AMBIGUOUS_REIDENTIFICATION` |
| 晚出生隔离 | PASS | late birth 未进入首帧 ordinal query |
| 查询级联合成功净增益 | **FAIL** | 旧版 `6/9`，最终版 `6/9` |

机器汇总见 [`evidence/subpixel-summary.json`](evidence/subpixel-summary.json)，SHA-256 为 `a429119a8b8cdf837a00f634e5db3c824e74769ef841757505f4cfe67d9b6901`。最终离线诊断见 [`evidence/subpixel-diagnostic.json`](evidence/subpixel-diagnostic.json)，SHA-256 为 `565d6613f621ef9fc0667dba6e28b43dcb7d301a33f3cf58fd9548e479842e39`。

## 覆盖边界

本轮只证明单屋三帧中的一条真实 LOST 轨迹可以在不使用 SDK 推理真值、不新增动作和不制造跨缺口对应的条件下正确恢复；它没有证明新视角提升了三个既定查询任务，也没有验证多屋、多人物、开放世界、隐藏事件、可逆归因、具身反馈、长期记忆或完整七算子。工程修复、局部诊断、电脑 B 独立验收、共享集成和科学收益继续分开记录。

最终聚焦验证覆盖 feature seed 伪造、无谱系、跨帧缺口、共享候选、完整重复候选、payload/mask/candidate ordering/完整重封 mask/源码 SHA 攻击、事务回滚和晚出生隔离。54 项测试、Ruff check/format、mypy、Python 编译与 diff check 通过。证据目录共 14 个 JSON 文件（其中 13 个被清单散列）、被散列内容 7,125,614 bytes；清单见 [`evidence/evidence-files.json`](evidence/evidence-files.json)。

## 下一主干门

当前最关键的缺口已从“错误重识别”收缩为“既定查询没有因主动观察增加联合成功”。下一轮若继续使用同一科研主干，应建立预先冻结且包含自然 LOST 查询目标的 matched task panel（匹配任务面板），同时保留现有 bottle/bowl 面板作为无退化控制；仍用相同动作预算比较 fixed、active、no-update 与 retain/withdraw。目标选择会改变任务构成，属于新的指标/实验选择，需按协作规则由用户决定后再启动。
