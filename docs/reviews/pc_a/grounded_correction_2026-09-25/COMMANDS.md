# 固定源码复现及 B 交接

复核生产/工具/测试提交 `d23438d4724d48a093439303b7db3988165ed567`；后续文档提交不改变该源码。结果是开发诊断，不是完整自然 P5 或科学验收。请先 fetch 并记录完整 SHA，避免继承其他临时目录状态。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/pytest -q tests/test_visual_target_tracking.py tests/test_natural_vision.py tests/test_natural_hands.py tests/test_hand_object_evidence.py tests/test_structure_two_continuous_input.py tests/test_continuous_state_recovery.py tests/test_joint_camera_policy.py tests/test_continuous_camera_collection.py tests/test_continuous_camera_cli.py
.venv/bin/mypy src
.venv/bin/ruff check src/cpswm/perception_mapping/visual_target_tracking.py tests/test_visual_target_tracking.py tools/run_initialized_target_tracking.py tools/run_correction_replay_comparison.py
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-grounded-seed7 --seed 7
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-grounded-seed11 --seed 11
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-grounded-seed19 --seed 19
```

输出目录必须尚不存在，失败也不覆盖原目录。当前工具导入测试夹具作为显式 oracle（语义已知的受控输入）；不能换掉声明或称为自然像素识别。种子 7/11/19 三例均有 1 个实际撤销；动作读出改变分别为 false/true/true。恢复及 `full_semantic_replay.semantic_state_equal` 均 true；语义分区无差异；source_unchanged 为 true。同时 `before.joint_readout.available` 为 false，`batch_present` 为 false；这项阻断必须保留，不能只检查命令退出码。

真实像素开发重跑：

```sh
.venv/bin/python tools/run_initialized_target_tracking.py --pixels /Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/handover-phase-20260920/pixels --annotations docs/reviews/pc_a/grounded_correction_2026-09-25/development_annotations.json --output output/review-initialized-tracking
```

Windows 需将 `--pixels` 指向同字节输入的本地目录；逐帧及原 result.json 哈希必须匹配，不能通过改 manifest 适应错误输入。预期留存数量 17/17、15/15、3/17、14/15，数量不是准确率。运行时只把首帧区域传给 tracker；后续支撑代理标签不参与跟踪。源视频先去掉烧录标签的前置证据沿用 PR33，本批不读取作者阶段 CSV。

主仓持久完整工件目录：`/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/grounded-correction-20260925/`。包含初版失败、最终数据库、输入日志、算子轨迹、图像复查和测试日志；本目录 VALIDATION.json 保留其相对于执行仓根目录的原哈希键。

B 重点复核：

1. 非空目标是否真从 observed 与 committed 集合撤销，重建是否复活，恢复与从头重放是否同语义状态；不要只读布尔结论。
2. 重放语义对应是否唯一，记录运行时身份重绑定；“整日剔除”的反事实对照不得替代同序列重放。
3. 比较双方共同输入只覆盖下游软计数记忆消融，不是独立强基线；保持未完成标记。
4. 默认 P5 不手动 stage 测试候选时联合决策视图是否仍缺失；不得绕过来源校验填入人为粒子。
5. 原像素/首帧提示/模型辅助标签边界及失败片段；后续若有语义写入，需继续合法与完整伪造正路径、状态机、账本和动作后果的全矩阵。

A 没有宣称独立审核或 B 复核通过，未修改 B 所有的比较模块，也未合并共享集成。
