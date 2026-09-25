# 固定版本复跑

本机双轮不代替 B。base 为 PR38 `26736d5acde0112c4a69863a56977bb044aff3eb`，修前 `fc3537d8fd0540ff95a3cab3724004f69502e88a`，修后及第二轮 `69d8b6a615c2c12f49e4573905596b709b16e809`。在独立工作树按锁文件重建，不复制 macOS 虚拟环境。

```sh
git fetch origin --prune
uv sync --frozen --extra dev --extra perception --extra hand-perception
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python docs/reviews/pc_a/joint_revision_runtime_2026-09-26/run_checks.py output/conditional-round2 /absolute/path/pr37-training
```

A 输入检查点为主仓 `output/joint-audit-next-20260925/round2/training`。五命令预期：466 回归、11 专项、三检查点实际 88 候选条件计算/恢复、mypy 363、Ruff 成功。输入路径与模型版本不同应重新产生本机证据，不修改旧摘要过门。

复现修前四个问题时，将修复版 `audit_round1.py` 复制到修前工作树同一相对路径，保持其 `src/tests/tools` 为 fc3537d：

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python -m pytest -o addopts= -q docs/reviews/pc_a/joint_revision_runtime_2026-09-26/audit_round1.py
```

修前预期四失败，修后四通过。不要把一般回归 466 通过解释为当时未存在缺陷，第一轮失败与真实检查点恢复失败都须保留。

逐项检查：完整原评分目标是否保留；计算后统计引用是否准确；三块是否与独立公式一致；替换潜在后缀是否误删原始记录；并发/重入/数值故障后下一请求及 RNG 是否相同；外部依赖损坏时是否停止错误会话；完整自洽伪造是否经实际模型重算拒绝。模型自报摘要不等于校准和授权，不得把本阶段输出直接改名为原生 prepared 输入。

B 记录自己的源码 SHA、导入位置、环境、命令、完整正路径和伪造后果；本轮无 B 签收或整体科学收益。
