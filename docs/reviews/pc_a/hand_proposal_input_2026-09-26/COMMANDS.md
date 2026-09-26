# 固定复跑

按完整报告源码SHA独立检出并用uv.lock安装dev/perception/hand-perception环境，然后：

```sh
.venv/bin/python docs/reviews/pc_a/hand_proposal_input_2026-09-26/run_frozen_hands.py --main <已登记原始资料主仓> --output <新的证据目录>
```

顺序：两轮不同审查 → mypy/Ruff → 前轮已经从完整原始归档重建且本轮使用固定外部manifest pin的128原帧/32窗前端 → 原三种微型夹具权重的执行派生（参数逐字保持，显式65,536节点）→ 每个预定试次首窗前2帧的三个网络消费/恢复实验。

消费入口 `tools/run_hfd_hand_proposals.py` 会重新从已绑定的视觉/手部记录生成上下文、全部支持和几何特征。原输入、移除手、x平移1像素三个对照使用完全相同的目标集合及UUID。最后复核依赖文件哈希。固定两帧检查消费；它们不足以证明完整交接事件链。

本轮不重新下载或选择数据，不读取作者标签，不训练或选定网络。原权重的训练内容是既有component fixture；概率变化不能作为准确率或控制收益。若后续扩四帧，需要单独记录实际矩阵、耗时、两审和覆盖，不将两帧结果外推。
