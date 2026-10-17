# 仿真框架复现命令

在独立checkout中运行；正式证据代码SHA为`be7f6a175f37b08ddcbce01d7a3b1e9e377d2c28`。以下输出目录必须不存在，复现时更换为新的路径。

```bash
uv sync --frozen --extra dev --inexact
uv pip install --python .venv/bin/python -r requirements/small-sim.txt
.venv/bin/ruff check src/cpswm/simulation tests/test_small_sim_framework.py tools/run_small_sim.py
.venv/bin/ruff format --check src/cpswm/simulation tests/test_small_sim_framework.py tools/run_small_sim.py
.venv/bin/mypy src/cpswm/simulation --follow-imports=silent
.venv/bin/python -m pytest tests/test_small_sim_framework.py tests/test_particle_support_sampling.py tests/test_current_event.py tests/test_current_event_adversarial.py tests/test_current_event_task_receipt.py tests/test_shared_location.py tests/test_current_location.py tests/test_executed_search.py tests/test_active_location_search.py tests/test_task_readout_repair.py tests/test_full_mechanism_value_diagnostic.py tests/test_structure_two_stateful_full_joint.py tests/test_structure_two_stateful_full_joint_adversarial.py tests/test_structure_two_w3_native_posterior_projection.py --junitxml=/private/tmp/cpswm-small-sim-final-tests.xml
.venv/bin/python tools/run_small_sim.py --backend event --output /private/tmp/cpswm-small-sim-final-event
.venv/bin/python tools/run_small_sim.py --backend mujoco --output /private/tmp/cpswm-small-sim-final-mujoco
.venv/bin/python tools/run_small_sim.py --backend mujoco --arms native_joint --conditions delayed_attribution execution_failure --video --output /private/tmp/cpswm-small-sim-final-videos
```

固定seed7；运行条件是六个确定性夹具，不构成多seed独立实验。Mac录像需可用CoreGraphics会话，本机受限沙箱第一次渲染失败后在获准的图形会话中成功重跑。无录像物理积分不依赖可视化窗口。所有正式原件和最终环境见evidence。

证据包核对示例（从本报告目录运行）：

```python
import hashlib, json, tarfile
from pathlib import Path
p = Path("evidence")
for name, expected in json.loads((p / "SHA256.json").read_text()).items():
    assert hashlib.sha256((p / name).read_bytes()).hexdigest() == expected, name
with tarfile.open(p / "raw-runs.tar.gz") as archive:
    files = [m for m in archive.getmembers() if m.isfile()]
    assert len(files) == 110
print("evidence hashes and archive file count verified")
```

原运行目录与归档解压后的逐字节比较已本机完成；此简短校验只验证归档完整性，不重新执行实验，不代替B复核。
