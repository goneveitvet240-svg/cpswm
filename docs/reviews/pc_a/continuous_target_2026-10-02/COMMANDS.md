# 源码与复现命令

实际源码 `19986b08c7605f84e73533cf71a7efa776a0a20d`；工作目录 `/private/tmp/cpswm-pc-a-continuous-target-20261002`。

Python3.13.5环境借用 PR90 `.venv`；SDK使用 `/private/tmp/cpswm-ai2thor-owned-20261001/bin/python`。官方权重 `/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth`，SHA256 `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`。

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth PYTHONHASHSEED=217 .venv/bin/python -m pytest tests/test_natural_target_sequence.py tests/test_visual_target_tracking.py tests/test_natural_vision.py tests/test_unity_rgbd.py --junitxml=/private/tmp/cpswm-continuous-target-evidence-20261002/visual-regression.xml
.venv/bin/mypy src/cpswm/perception_mapping/natural_target_sequence.py
.venv/bin/ruff check src/cpswm/perception_mapping/natural_target_sequence.py tests/test_natural_target_sequence.py tools/run_natural_target_sequence.py tools/verify_natural_target_sequence.py tools/unity_target_sequence_worker.py
PYTHONPATH=src:tools .venv/bin/python tools/run_natural_target_sequence.py --output <全新输出目录> --weights /private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth --sdk-python /private/tmp/cpswm-ai2thor-owned-20261001/bin/python --binary /Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR --house docs/reviews/pc_a/sim_timing_control_2026-09-29/evidence/raw-examples/south-320-frozen-0/evaluator_house.json --degrees 30 1 1 1 1 1 1 1 1 1 1
# 第二序列相同命令、新目录，--degrees 30 5 5 5 5
PYTHONPATH=src:tools .venv/bin/python tools/verify_natural_target_sequence.py <采集目录> /private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth
```

采集参数是预先固定诊断；没有事后补拍/选帧替换失败。不把固定扫描称为主动策略比较。
