# 来源与复核方法

实际功能代码 `69ebcf90ea271798b8f0c1eb89df501065954ebd`；本目录后续提交只增加文档与非执行证据。不要在已执行的源码目录新增 Python 文件后仍声称同源复现。`source.json` 保存所有受测 Python/依赖文件摘要；实际加载当前任务 src/tests/tools，模型虚拟环境复用上一批锁定环境，不声称独立依赖复现。

## 原命令和范围

`evidence/archive-audit-attempt02/commands.json` 与 `evidence/repeatability-attempt01/commands.json` 记录完整实参、退出码、耗时和前后源码一致性。对应同名日志与 JUnit 可逐项检查。第一阶段使用旧图完整 132 帧，第二阶段使用新采集完整 128 帧，夹具与共享反例的额外重算不并入两者的统计分母。

外部编排脚本以 `.py.txt` 保存，避免改变被冻结的 Python 源图。脚本中的本机绝对路径是当时执行记录，迁移后必须显式改为当地资源；不要直接执行另一台机器的虚拟环境。`runtime-before.json`/`runtime-after.json` 记录本次 SDK、解释器、Unity app、默认质量等身份；它们不能倒推证明旧 132 帧运行时的所有资源都相同。

## 完整矩阵复核

先建立对应 SHA 的工作目录及锁定依赖，并提供两个官方 torchvision 权重、AI2-THOR SDK Python 与匹配的模拟器二进制。原件目录见 REPORT.md；Git 只有全部轻量证据和一条完整序列，复核整个 128 帧还需要从 A 取得完整原件并核对 RAW_INVENTORY.json，不能拿单条共享序列代替整矩阵。

```sh
export PYTHONPATH=src:tests:tools
export PYTHONHASHSEED=0 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
.venv/bin/python tools/run_simulator_repeatability.py \
  --mode verify --output "$CPSWM_CAPTURE_DIR" \
  --sdk-python "$CPSWM_SDK_PYTHON" --binary "$CPSWM_UNITY_BINARY" \
  --ssdlite-weights "$CPSWM_SSD_WEIGHTS" \
  --fasterrcnn-weights "$CPSWM_FRCNN_WEIGHTS"
```

以上变量须指向真实资源；`verify` 从拥有者记录解码公共 RGB，重新执行两个神经前端，之后重算私有几何及全部汇总。`--mode run` 需要不存在的新输出目录，会实际启动 16 次模拟器；不得覆盖原件。新的采集不是旧图逐字复制，若跨平台/依赖出现差异，应原样报告，不能更改比较条件以掩盖差异。

## Git 内八帧完整序列

以相同 PYTHONPATH 和两个权重路径运行以下代码，可直接核对共享的 south-320-direct-0 全部八帧。该例是为展示四组都存在的首帧变化而选取，不是性能基准。

```python
import os
from pathlib import Path
import torch
from run_simulator_repeatability import analyze, plan

torch.set_num_threads(2)
cell = next(c for c in plan() if c["name"] == "south-320-direct-0")
directory = Path("docs/reviews/pc_a/sim_reliability_2026-09-29/evidence/raw-example") / cell["name"]
result = analyze(directory, cell, weights={
    "ssdlite": Path(os.environ["CPSWM_SSD_WEIGHTS"]),
    "fasterrcnn": Path(os.environ["CPSWM_FRCNN_WEIGHTS"]),
}, verify=True)
assert len(result["frames"]) == 8
```

此复制位置已实际执行上述检查，结果见 `evidence/shared-example-verification.json`。Git 证据逐文件摘要见 `evidence/SHARED_INVENTORY.json`；清单自身不递归包含自身。摘要证明记录后未变与本机计算一致，不提供解释器/模拟器/数据被共同伪造情况下的外部真实性担保；仍需 B 独立复核。
