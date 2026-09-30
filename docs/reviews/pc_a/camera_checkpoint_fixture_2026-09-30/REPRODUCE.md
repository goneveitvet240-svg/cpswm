# 复现

检出14409b3beabbd298196ea8f65c4e4f7a0cf719f2，创建实体本地.venv：uv sync --frozen --extra dev --extra perception --extra hand-perception --python 3.13.5。

默认正路径：env -u CPSWM_CHECKPOINTS .venv/bin/python -m pytest -o addopts= -q tests/test_camera_policy_identifiability_artifacts.py。必须13通过而非因无模型skip。

将仓库docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/development-checkpoints完整复制到新的目录，核对原字节，设置CPSWM_CHECKPOINTS后再次运行完整模块。显式缺失或空路径必须出错，不回落；将复制目录第一个模型manifest的arm改成另一个合法arm，其余完整模型保留，实际正路径节点必须拒绝arm不符。

evidence.tar.gz内run_reviews.py与supplement.py记录本次完整命令、模型原件和拒绝输入。复现时仅修改脚本副本中的绝对路径和空输出目录；保留源码SHA及原件，不覆盖历史证据。不复用别的工作树editable环境。实际开发checkpoint没有自然训练/校准效力。
