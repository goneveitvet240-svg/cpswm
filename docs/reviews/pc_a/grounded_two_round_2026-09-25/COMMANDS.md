# 固定版本复跑与 B 交接

先 `git fetch origin --prune`，在独立工作目录记录完整 SHA。本批 PR34 二轮修后版本为 `1e6e0373248d3881be67f00922cc7c330b6f1bba`；后续连接生产/测试/工具版本为 `7a534842ec3b1206bc4c3389e11e558c4a0f31d5`。文档证据与运行器随后提交，不能以旧审核覆盖新代码。

## PR34 修复与第二轮

在二轮修后版本，用锁文件建环境，然后运行：

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/pytest -o addopts= -q tests/test_grounded_development_audit.py tests/test_visual_target_tracking.py tests/test_natural_vision.py tests/test_natural_hands.py tests/test_hand_object_evidence.py tests/test_structure_two_continuous_input.py tests/test_continuous_state_recovery.py tests/test_joint_camera_policy.py tests/test_continuous_camera_collection.py tests/test_continuous_camera_cli.py
.venv/bin/mypy src
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-seed7 --seed 7
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-seed11 --seed 11
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-seed19 --seed 19
```

预期 114 passed、350 mypy；三个种子各 1 个实际撤销，恢复/同语义序列重放一致，动作读出改变 false/true/true。完整伪造内容即使哈希自洽也只有像素测量权限；不是真实性认证。

首轮修前反例文件在修后提交中。在独立的首轮基线工作树中只复制 `tests/test_grounded_development_audit.py`，选前四个测试（名称包含 legal_tracking_positive、changed_annotation_mid_run、forged_payload_and_annotation、truncating_failure_suffix），预期 1 passed / 3 failed。不要把修后的工具同时复制过去。

实际 64 帧跟踪的输入/标注入口沿用 PR34 的 [COMMANDS.md](../grounded_correction_2026-09-25/COMMANDS.md)，本批输出另设新目录。原输入在本机主仓 output；需 B 通过用户已有文件交接取得，不能凭 Git 精简 JSON 还原原像素。

## 后续连接独立验证

取本批交付文档，再确认 src/tests/tools 的内容与后续连接固定 SHA 相同；运行器记录实际 checkout SHA 和逐文件哈希：

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python docs/reviews/pc_a/grounded_two_round_2026-09-25/run_next_step_checks.py output/review-native-checks
```

预期 264 passed / 10 既有坏类型构造 warnings，mypy 351、Ruff 通过，manifest 的 source_unchanged=true。固定版本内可直接运行 `tests/test_native_joint_production.py`（12 项）。每个输出目录必须尚不存在，失败也不要覆盖。

真实 Unity 命令使用本机已安装的 SDK Python 与二进制，按环境替换路径，不拿 Windows 路径或旧虚拟环境直接复制：

```sh
.venv/bin/python tools/run_configured_joint_unity_probe.py \
  --output output/review-native-live-unity \
  --sdk-python /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv-ai2thor/bin/python \
  --binary /Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR
```

必须同时检查 action=RotateLeft、success、pixels_changed、same_ready_command_after_resume、source_unchanged；不能只看退出码。模型明确为受控夹具，natural_semantic_transitions=0、selected_neural_kernel_bound=false、complete_natural_closed_loop=false 必须保留。该探针恢复 Python/SQLite 所有者，未重新启动 Unity。

B 审核应分别绑定两个源码 SHA；确认合法自动正路径、完整伪造批次拒绝、同快照不同来源、恢复/持久化失败与动作后果。检查默认缺模型仍不可用、失效修订仍需内核、科学阈值与 B 专属核心未改。不把本机 A 回归登记为 B 或完整统一验收。
