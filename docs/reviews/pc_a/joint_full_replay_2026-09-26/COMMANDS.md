# 固定版本复现与 B 交接

最终受审源码 `348d11a172d0d26cb6ec990ad930664912f8495d`；前次 `92e1960a815ac6ae0afa2e0a7516ab764628ba25` 被追加反证否决，分支 `codex/pc-a-joint-full-replay-20260926`，base 为 PR39。请独立 fetch、检出和重建环境，不复制 A 的虚拟环境，不改写旧结果。

```sh
git fetch origin --prune
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python docs/reviews/pc_a/joint_full_replay_2026-09-26/run_checks.py output/joint-full-replay-independent 2
```

入口要求源码与审核脚本已提交；记录开始 SHA、所有 src/tests/tools 和本轮审核脚本的摘要，按顺序执行回归、第一审、第二审、受控完整续跑、全量 mypy 和 Ruff，最后再次比对源码。目标 654 回归、第一审 5、第二审 7；以实际退出码和日志为准。

单独追踪后果：

```sh
.venv/bin/python tools/run_native_joint_full_replay.py --output output/joint-full-replay-consequences
```

核对 result.json 中原 12 个输入、一次撤回、11 个保留重算来源、22 个记录、2 个原子、11 步统计历史、6 维位姿、账本无新增、精确恢复及受控相机一次；另与 before/after 完整状态和 SQLite 核对。不要将 23 个仍有效语义源误当 23 个原联合输入。

修前实验保留：`round1-complete`、`round1-recheck.json`、`round2-initial/adversarial.log`、`round2-initial/schedule-and-ready.log`。第一次通过字样不覆盖后来的实际反证；开发/环境/脚本错误单独见 RUN_NOTES.md。B 应另记录实际环境、CRLF/LF、完整伪造后果与独立来源，而不是转录 A 的 passed 数。
