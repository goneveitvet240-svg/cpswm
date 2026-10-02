# 复现与检查

功能/测试冻结源码：`ccccacc8ced5245ee6c38b2466632bac37d37cd0`。独立 worktree `/private/tmp/cpswm-pc-a-joint-target-observations-20261002`；借用已有 Python 3.13.5 开发环境，并非独立重建依赖。未改原用户工作树和共享集成分支。

```bash
export CPSWM_SSDLITE_WEIGHTS=/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth
.venv/bin/python -m mypy src
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m pytest tests/test_temporal_target_position.py tests/test_natural_target_sequence.py tests/test_visual_target_tracking.py -x
.venv/bin/python -m pytest tests/test_owned_position_update.py tests/test_appearance_geometry_position.py tests/test_native_joint_full_replay.py tests/test_native_raw_candidate_verification.py -x
```

权重必须为原固定 SSDLite 权重，SHA256 `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`（以运行时 `natural_vision.WEIGHTS_SHA256` 校验为准）。缺文件时测试会跳过；本轮要求显式提供权重且报告跳过数，不把跳过计入通过。

冻结代码下，真实采集诊断和恢复：

```bash
PYTHONPATH=src:tests:tools .venv/bin/python docs/reviews/pc_a/joint_target_observations_2026-10-02/evidence/live_probe.py /private/tmp/cpswm-joint-target-evidence-20261002/live-frozen
PYTHONPATH=src:tests:tools .venv/bin/python -c 'from test_temporal_target_position import fresh_restore; fresh_restore("/private/tmp/cpswm-joint-target-evidence-20261002/live-frozen")'
```

目录必须不存在才能新采集。脚本使用本机 AI2-THOR Python、固定 Unity 二进制、仓库内既有 house；原数据库内的权重/神经 checkpoint 路径仍绑定本机目录。异机应重建环境、运行上述测试/诊断来复现，不覆盖原数据库或伪造已绑定路径。恢复脚本只读取原 SQLite 副本，不创建新的语义历史，不重拍。

脚本依赖明确标注的受控语义/残差/效用测试夹具。其真实外部输入为 Unity RGB-D + 理想相机自身位姿；SDK 的目标框单独存于 evaluator_only，未送入推断。提前停止属于保留结果，不能为了四次动作修改模型或停止阈值后仍沿用原比较名义。

第一轮：33 passed / 798.98s，零跳过；397 源文件 mypy、src/tests Ruff、808 文件 format 通过。925 个 src/tests/tools Python 文件的冻结清单见归档。

`evidence/transactions-r1.tar.gz`：125 个原件，展开 283,736,087 字节，压缩 37,149,651 字节；SHA256 `1862f645c480be37328a6d8ef3f931cc3465c25481578843513d80f001c203a4`。每个成员与内部 MANIFEST.json 逐项读回核验。包含本轮数据库/神经测试 checkpoint、真实传感器原件、冻结前失败/中止日志、冻结结果和两项实际后验直接数值复核。模型大权重与系统 Unity 二进制不打包。第二轮：61 passed / 655.64s，零跳过。`evidence/regression-r2.tar.gz`：134个原件，展开494,243,385字节，压缩57,107,875字节；SHA256 `c9e64b6f55e0beec8637d160ae24bc8bda340dca69d1e7a05427301ef014e115`，所有成员逐项读回。包含旧模式回归数据库/日志、受控双候选两次事务、初始/中间采集撤回的两次全新解释器恢复，以及对应独立检查脚本。

两轮同冻结源码依次执行，合计94项定向测试；两份归档合计259个原件，另含各自MANIFEST.json。未声称全仓或B独立验收。

额外检查脚本均在 `evidence/`：`verify_duplicate_posterior.py` 读取第一轮重复采集 SQLite，直接比较实际权重和统计；`verify_withdrawal_joint.py` 对中间帧撤回后的 SQLite 做整段联合矩阵复算；`multi_candidate_probe.py` 运行受控双候选两次事务；`capture_withdrawal_fresh.py prepare <新目录> <第一轮pytest目录>` 用两个新解释器恢复首帧/中间帧撤回数据库。原路径、运行日志、复制的数据库和恢复配置均在归档。
