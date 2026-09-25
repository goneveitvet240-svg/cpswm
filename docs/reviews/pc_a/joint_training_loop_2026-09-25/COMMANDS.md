# 固定源码复跑与 B 复核入口

## 版本与环境

实现 SHA：`bfe876cdb3fd702f4ac856e1f0d37245cb59d1e4`。分支 `codex/pc-a-joint-training-loop-20260925`，叠加 PR35。取最新报告提交后，确认 `src/tests/tools` 对这个 SHA 没有差异；文档晚于源码是有意保留的证据边界。不要在共享集成分支直接写入。

```sh
git fetch origin --prune
git diff bfe876cdb3fd702f4ac856e1f0d37245cb59d1e4 -- src tests tools
uv sync --frozen --extra dev --extra perception --extra hand-perception
```

A 用 Python 3.13.5 / macOS / CPU 两线程。B 用 Windows/WSL 自建环境，不复制 A 的 `.venv`。下列 `.venv/bin/python` 按平台替换。

## 公开证据获取

HO-Cap 示例和 RPL/交接数据小文件已有固定作者来源及字节摘要。第一条获取辅助文件，第二条获取作者的两个训练视频样本，最多四路 1 MiB Range 请求，并核验完整包 MD5。不下载完整 9.2 GB 训练集或验证/测试视频。

```sh
.venv/bin/python docs/reviews/pc_a/joint_training_loop_2026-09-25/fetch_public_auxiliary.py output/review-public-evidence
.venv/bin/python tools/fetch_handover_training_sample.py --output output/review-public-evidence
.venv/bin/python tools/inspect_public_joint_evidence.py --source output/review-public-evidence --output output/review-public-package
```

预期 1680 位姿对、801 RPL 时刻、897 视频帧；不看退出码就宣布标签独立可靠。必须复核示例模型身份未验证、原始旋转未处理对称性、单一人工标注者、全 idle 负例、大量零力矩、1 帧超出力矩范围、没有全局人物 ID 等具体输出。`fetch_public_auxiliary.py` 本机对已下载字节执行过完整校验；B 新联网下载仍受源站可达性约束。

全部数据须按各自作者许可和来源引用；RPL 仓库 MIT、HFD CC BY 4.0。HO-Cap 数据许可见其官方项目，不把工具 GPL 当数据许可。

## 完整本批检查

原 540 HO-Cap 帧在 A 主仓的两个旧开发数据目录，路径见 `evidence/input-spec.json`。B 需通过已有文件交接取得同一数据，或用原固定下载工具重取。只改 spec 中的根路径，不能改预期源 manifest/回执 SHA；所有输入和作者标签仍由包工具复验。三个窗口属于同一人/三条序列，不能当九个独立序列。

```sh
.venv/bin/python docs/reviews/pc_a/joint_training_loop_2026-09-25/run_checks.py output/review-joint-checks /absolute/path/input-spec.json output/review-public-evidence
```

输出目录必须尚不存在。预期：383 passed（10 个既有负例序列化 warnings），mypy 356，相关 Ruff 通过；八条命令成功、源码前后相同。文件摘要来自实际 checkout，不能只引用报告的 SHA。

其中关键独立入口：

```sh
.venv/bin/python tools/build_joint_supervision_package.py --spec /absolute/path/input-spec.json --output output/review-hocap
.venv/bin/python tools/run_typed_proposal_development.py --output output/review-three-arms --steps 4
.venv/bin/python tools/run_joint_correction_continuation.py --output output/review-joint-correction --seed 11
.venv/bin/python tools/run_correction_replay_comparison.py --output output/review-existing-correction --seed 11
```

三候选运行仅夹具诊断；默认 3×4 次真实优化器更新，不是正式训练协议。核对全六操作概率质量、九因子、无标签运行上下文、保存恢复精确性，不按夹具损失排名选架构。

条件重算核对：2 个活动原子、24 条记录、祖先深度 12；1 个真实已提交来源撤回；每原子 11 个保留后续测量重算，Dirichlet/RLS/Gaussian 均改变，恢复完全相同。纠正后实际 joint 生产/读出仍应拒绝旧批次，不能以“让它通过”为由清空 invalidation 标记。

## 留存证据

- 最终输出：本机独立工作树 `output/joint-training-loop/final-checks-02`；Git 精简证据在 `evidence/`。
- `final-checks-01` 因提交未完成而 lint 范围误扩，保留失败；`data-package-01.log` 保留重复回执诊断；整包首次下载超时留下的部分文件不作为接受工件，实际接受文件为 `sample_training_set.verified.tar.gz`。
- 原始包、视频、逐帧标签、模型权重、SQLite、完整日志在 A 主仓持久备份 `output/joint-training-loop-20260925/`；Git 不收录媒体/权重。
- B 记录实际 HEAD、解释器、命令、源摘要、正路径后果与剩余矩阵到自己的 STATUS_B。A 组织后续集成；本 PR 不自动集成，不代表 B 已签收。
