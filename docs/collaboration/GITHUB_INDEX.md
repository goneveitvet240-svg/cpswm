# GitHub 工作导航

核对日期：2026-09-13（北京时间）。本页是当前工作入口；完整科研框架与既有科学决策保持有效。

## 先看这里

| 入口 | 用途 | 当前状态 |
|---|---|---|
| [统一运行候选 #15](https://github.com/goneveitvet240-svg/cpswm/pull/15) | A 的源码汇总、RGB-D 入口与局部审核 | CI 失败，尚未合入共享集成 |
| [位姿与本地开发 #16](https://github.com/goneveitvet240-svg/cpswm/pull/16) | 在 #15 上继续的位姿/小预算开发 | 待源码绑定复核，静态检查失败 |
| [B4–B9 新交接 #17](https://github.com/goneveitvet240-svg/cpswm/pull/17) | B 的三文件修复及审计证据 | 已推送；未独立复跑；静态检查失败 |
| [W2 验收准备 #2](https://github.com/goneveitvet240-svg/cpswm/pull/2) | 比较协议与独立验收准备 | PARTIAL，等待当前统一版本重算 |
| [任务板](TASK_BOARD.md) | 所有权、阻塞、下一步 | A 汇总，B 复核 |
| [结构二完整框架](../结构二/README.md) | 研究合同与协议 | 文中历史实验结论绑定其原版本 |

## 分支怎么选

- `main`：仓库首页和历史代码基线；不是当前研究候选。
- `codex/dual-pc-handoff-20260912`：共享协作与集成入口。本轮仅合入文档证据、导航和状态整理；生产代码仍基于 `bdec3ee21b7db361e390496d97ff2eb30390dc6c`。
- `codex/pc-a-unified-runtime-20260913`：当前统一候选。
- `codex/pc-a-pose-local-dev-20260913`：位姿后续开发，在 #15 上叠加。
- `codex/pc-b-adversarial-audit-fix-20260913`：B 新交接，在 B 旧五边界分支上叠加，尚未接入 #15。
- 其余阶段分支及 `snapshot-*`：历史来源和回放依据；保留名称和提交，不删除或强制推送。

## PR 分类与冻结身份

“包含于 #15”仅表示候选已携带该提交或相同文件，不能解释为共享集成完成或验收通过。旧 PR 关闭后仍保留原报告、检查结果和分支。

| PR | 内容 | 核对时完整 SHA | 分类 |
|---|---|---|---|
| [#1](https://github.com/goneveitvet240-svg/cpswm/pull/1) | A: 三窗口第六轮独立审核与 W1 旧测试缓存反例 | `97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274` | 文档证据归并 |
| [#2](https://github.com/goneveitvet240-svg/cpswm/pull/2) | W2 本机独立验收准备与 W1/W3 精确交付复核（PARTIAL） | `329787241996631a6abb4fcd3b12d2c13a135777` | 独立验收准备，保留 |
| [#3](https://github.com/goneveitvet240-svg/cpswm/pull/3) | Repair W1 cached-code execution identity and seal R6 evidence | `21870b0bcd6c23d43518a27fcc1c4b538b3912b7` | 已包含于 #15，归档 |
| [#4](https://github.com/goneveitvet240-svg/cpswm/pull/4) | W3 R7: restore model, bind native posterior consumption, recover cancelled parents | `62870a3a38fce882b25d8d77f1d0526cca6fbc14` | 已包含于 #15，归档 |
| [#5](https://github.com/goneveitvet240-svg/cpswm/pull/5) | [PC-B audit] W3 R6 independent review + W1 static review | `9195dd4b3872cbf770bd73ad4c84cca007137c3d` | 21/21 文件已包含于 #15，归档 |
| [#6](https://github.com/goneveitvet240-svg/cpswm/pull/6) | PC-A crosscheck: reproduce PC-B five open findings on R6 and R7 candidate | `1b2b31e88c47fc232a7b4e2dcec56c02c9ac9636` | 文档证据归并 |
| [#7](https://github.com/goneveitvet240-svg/cpswm/pull/7) | fix(w3): close five PC-B prepared-boundary gaps | `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c` | 已包含于 #15，归档 |
| [#8](https://github.com/goneveitvet240-svg/cpswm/pull/8) | PC-A: joint CIAV consumer and conditional blocks (component scope) | `2a7a547fba30412d9349605aff3a7df7c60d6b3a` | 已包含于 #15，归档 |
| [#9](https://github.com/goneveitvet240-svg/cpswm/pull/9) | PC-A: train coverage, visible-prefix export, real simulator capture preflight | `6e07ab682a9ec15e959e1a50001e237877bc4773` | 已包含于 #15，归档 |
| [#10](https://github.com/goneveitvet240-svg/cpswm/pull/10) | PC-A proposal sample contracts and ProcTHOR scheduler — changes required | `5ec6204dfecc9137523b6c0e5dfb66658e574d41` | 已包含于 #15，归档 |
| [#11](https://github.com/goneveitvet240-svg/cpswm/pull/11) | PC-A two-round adversarial audit: seven OPEN defects and native pixel evidence | `f95086718ad2d7d6f0707bcae1dc6758d3417233` | 已包含于 #15，归档 |
| [#12](https://github.com/goneveitvet240-svg/cpswm/pull/12) | PC-A G1 fixes: full proposal binding, isolated samples, two post-fix audits | `6a008aedd9c588a7716206eba60b3a57f9fc94d4` | 已包含于 #15，归档 |
| [#13](https://github.com/goneveitvet240-svg/cpswm/pull/13) | PC-A: multiagent runtime diagnosis and fail-closed initialization guards | `ec2215ac7138c2b359d77219519e5628669c8b82` | 已包含于 #15，归档 |
| [#14](https://github.com/goneveitvet240-svg/cpswm/pull/14) | PC-A: frozen Unity post-house multi-agent build and partial adversarial evidence | `05836759cd96b89011efca71d3e9dc3ab393ce1b` | 已包含于 #15，归档 |
| [#15](https://github.com/goneveitvet240-svg/cpswm/pull/15) | 统一运行候选：合流源码、RGB-D入口与两轮审核修复 | `e6bdd018d3fd49cb304293d25651506e5342344f` | 当前统一候选，CI 阻塞 |
| [#16](https://github.com/goneveitvet240-svg/cpswm/pull/16) | Add local pose state and small-budget development configuration | `25ec3478476af6399321e17c8a4981753d578ce0` | 位姿开发，待复核 |
| [#17](https://github.com/goneveitvet240-svg/cpswm/pull/17) | PC-B B4–B9: preserve repair and audit handoff for independent review | `fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a` | B 新修复，待独立复核 |

## 整理依据和验收边界

- #3、#4、#7–#14 的十个 head 均通过 `git merge-base --is-ancestor <head> e6bdd018d3fd49cb304293d25651506e5342344f` 验证。
- #5 不按祖先关系归档：其相对 R6 快照的 21 个变更文件在 #15 中逐项 Git blob 相同。
- #1 与 #6 相对共享基线仅改 docs；本轮保留两者 Git 历史，完整保留各自证据。唯一冲突为 STATUS_A，双方原文另存 history，本页及当前状态提供新入口。
- #1/#6 静态检查成功，原 CI test 均 exit 124（超时）；不记为通过。本轮合并的是只含文档的审计档案，已核对除 README 导航外，所有非 docs 路径与共享基线相同。
- #15 的 static-quality/test 均失败；#16/#17 静态检查失败，整理时部分 test 仍运行。未忽略生产 PR 的失败检查，也未开启自动合并。
- B4/B5 的 808/812 等结果来自 B 的 Linux Python 3.12 历史报告，本轮没有复跑。工程检查、独立复核、跨机验收、统一验收、科学收益分别记录。
- 不改变 CI、科研阈值、模型选择、先验、预算或工作分工；完整 H/R/I/C/Z/r/V、三个 RB blocks、七算子、隐藏事件、多人物、开放世界、可逆归因与具身反馈均保留。

整理前快照与旧状态见 [history](history/2026-09-13-organization/)。精确复现必须 fetch 并绑定对应 PR 当前 SHA；新提交使旧源码审查过期。
