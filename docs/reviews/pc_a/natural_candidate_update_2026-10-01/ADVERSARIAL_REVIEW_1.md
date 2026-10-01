# 第一轮：自然候选实际更新及事务后果

绑定功能源码 `63b053fa30a508a0c73dcff44d47a645f5a1362f`。冻结后顺序第一轮 A 自审，非独立 B。35 passed，426.19s，无失败/跳过。测试官方权重显式可用，不用 skip 代替通过。

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth .venv/bin/python -m pytest tests/test_natural_candidate_position.py tests/test_owned_position_update.py --junitxml=/private/tmp/cpswm-natural-candidate-evidence-20261001/review1.xml
```

覆盖：真实固定权重 SSDLite + 原归档 RGB + 明示合成 depth/语义条件；自然候选默认 collector 确实更新同语义真实后验并驱动下一决策；原单测量去重及受控对照；空候选/无效深度保持交付与状态、之后合法新 capture 能更新；提交前后故障与计算回滚；删除 S+A 和删除其他 S 后保留 A 的逐更新重放；delivered/consumed/replayed 三个阶段新解释器直接恢复；拒绝后合法恢复。

完整伪造：原四类 known/unknown/aggregate/transition 保留有效 q；新增自然读出伪造把选中公开三维点与对应完整表面读出一起改写，真实 producer 产生合法 neural evidence，随后原 owner 消费端重算拒绝，全部状态不变且可合法重试。另改已加载选择函数，原 binding 拒绝更新，恢复函数后合法路径成功。没有替换 production verifier 或放宽模型/来源保护。

新自然配置不接受 caller 框、seed 或模型 score；真实检测输出由受保护方法重建。身份仍为原受控假设，所选 candidate 不是自然世界身份认证；这轮不证明实际仿真任务收益或跨帧关联。两轮有交叉测试，不把重复执行计作独立数据。
