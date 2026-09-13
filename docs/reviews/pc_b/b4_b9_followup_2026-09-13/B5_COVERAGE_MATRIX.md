# B5 扩展状态机与长历史覆盖矩阵

基线：`c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`；最终本地三文件摘要见 `FINAL_HANDOFF_REPORT.md`。`passed` 仅表示本次 Linux LF 修复方回归，不等于 A 独立复核或统一验收。

| 需求 | 状态 | 本轮证据/剩余缺口 |
|---|---|---|
| 合法初代、多代、重排、未知/未决质量 | passed | 47 项矩阵三 seed、native suite 与 B5 状态机均覆盖合法非空控制 |
| 世界支持篡改、外来 runtime | passed | stage/readout/parent/replay 表面及 runtime transplant 拒绝 |
| 实例/类方法替换 | partial | 既有锁/来源绑定负例覆盖；未在 Windows 3.13 `-n4` 关闭 1 秒合同 |
| 完整重封伪来源、父子谱系、统计簇 | passed | 新增 workspace source-chain 与 core-owned input anchor；拒绝后合法重试 |
| 粒子/proposal/统计项缺失、多余、重复 | passed | 47 项 closure 矩阵与 native 粒子测试覆盖 |
| 投影来源缺失、多余、重复 | partial | 来源跨批重用和 closure 有覆盖；所有投影来源组合未穷举 |
| 正规化、未知候选保留 | passed | 独立 recurrence 最大误差 ≤ `1.11e-16`、质量和为 1 |
| 延期、晋升、纠正、撤回、取消、恢复 | partial | 27 项 cancellation suite + 4 项 B5 状态机；尚无更大随机全排列模型 |
| cancellation staged/published 完整重封 | passed | 接收时摘要锚、拓扑校验、统一写入口复核；攻击拒绝且 receipt/derived/action 无副作用 |
| 同事件重复、陈旧重放 | passed/partial | replay receipt 和 fresh legal replay 覆盖；超长整批陈旧历史组合未穷举 |
| 故障中断、拒绝无副作用 | passed | RuntimeError/KeyboardInterrupt、workspace 伪链和 cancellation 两类拒绝均有断言 |
| 长历史账本一致性 | passed to N=20 | seed 7、N=4/8/12/16/20；40 records、深度 20；该性能 JSON 早于 cancellation anchors |
| 校验时间/内存增长 | measured | wall 2.179→18.636 s，RSS N20 115,532 KiB；未证明理想渐进复杂度 |
| 实际动作后果 | gap | 仅 action distribution/observable state；无真实 controller 世界后果 |
| Windows CRLF/LF 双树 | blocked | 本轮仅 Linux LF；历史 Windows 失败保留，不能改写为通过 |

新增生成器/测试不从系统最终输出反推正确答案；每类攻击配合法非空控制。历史探索中两类 cancellation 修前接受未保存独立原始日志，因此只作为探索观察；正式可提交证据是修后拒绝、无副作用与合法 replay 回归。
