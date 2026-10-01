# 复核命令

绑定源码 `5a4e3a0660114b3e7bc5b2482f4d49456b825239`。工作树 `/private/tmp/cpswm-pc-a-appearance-geometry-association-20261001`；core Python3.13.5 环境借用已有 .venv，并非独立重建。官方 SSDLite 路径 `/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth`，全 SHA `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`。

```sh
CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth PYTHONHASHSEED=117 .venv/bin/python -m pytest tests/test_appearance_geometry_position.py --junitxml=/private/tmp/cpswm-appearance-geometry-evidence-20261001/round1.xml

CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth PYTHONHASHSEED=227 .venv/bin/python -m pytest tests/test_owned_position_update.py tests/test_native_raw_candidate_verification.py tests/test_continuous_camera_collection.py tests/test_natural_candidate_position.py tests/test_appearance_geometry_position.py::test_complete_resealed_association_readout_rejected tests/test_appearance_geometry_position.py::test_loaded_appearance_alias_change_rejected_then_recovers 'tests/test_appearance_geometry_position.py::test_fresh_interpreter_natural_reconstruction[replayed]' --junitxml=/private/tmp/cpswm-appearance-geometry-evidence-20261001/round2.xml

.venv/bin/mypy
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

三个 live launcher 位于 evidence，运行时 `PYTHONPATH=src:tests:tools .venv/bin/python <launcher> <独立新输出目录> 5a4e3a0660114b3e7bc5b2482f4d49456b825239`，并使用本机 SDK `/private/tmp/cpswm-ai2thor-owned-20261001/bin/python`。真实控制相机分别15+15、30+5、30+1度。不要覆盖已有诊断或把后两组当盲测。完整输出已压缩；其实际 DB 新进程复核脚本也保留。

`score_diagnostic.py <解压live归档的父目录> <固定SSDLite权重>` 仅重算既有公共图像上的原模型分数，不更新推断状态/阈值。

旧数据库在异目录/异源码/异机恢复仍受权重绝对路径与实现绑定限制；没有自动迁移承诺。新单测可用当前有效权重路径重建实验，但这不等于旧事务迁移验收。
