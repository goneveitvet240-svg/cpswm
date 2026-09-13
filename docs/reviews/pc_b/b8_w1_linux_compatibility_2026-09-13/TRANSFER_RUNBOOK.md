# W1 Linux 可移交复现说明

本说明绑定交付 `21870b0bcd6c23d43518a27fcc1c4b538b3912b7`，实际代码父提交
`6fcff45c71eff3f3457d0b6eac6cd872102db89d`。必须在 Linux 文件系统中的全新工作树执行；不要
复用 Windows 挂载目录、其他任务虚拟环境、旧 pytest 缓存或已存在的结果目录。

## 前提

- CPython 3.13.5；
- `uv.lock` 原字节不变；
- pytest 9.1.1、pytest-xdist 3.8.0 以及锁文件中的完整 `dev` 依赖；
- Git 工作树 HEAD 精确为交付 SHA；
- `PYTEST_ADDOPTS`、`PYTEST_PLUGINS`、`PYTHONPATH`、`PYTHONOPTIMIZE` 未设置，
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD` 不得由外部设置；
- 为每次测试指定新的 JUnit 和运行目录，不能覆盖封存证据。

## 建议命令

```bash
git fetch origin --prune
git worktree add ../cpswm-b8-w1-linux 21870b0bcd6c23d43518a27fcc1c4b538b3912b7
cd ../cpswm-b8-w1-linux
uv python install 3.13.5
uv venv --python 3.13.5 .venv
uv sync --frozen --offline --extra dev --no-cache
git rev-parse HEAD
git status --short
.venv/bin/python --version
.venv/bin/python -m pytest --version
.venv/bin/python -m pytest -p xdist.plugin -o addopts= -q \
  tests/test_structure_two_runtime_cache_identity.py \
  --junitxml=/absolute/new/output/w1_runtime_cache_identity.junit.xml
```

若离线缓存未预装完整锁定依赖，应由管理员按同一 `uv.lock` 提供 wheel/cache；不要改锁文件或降级
版本绕过。运行后保存：完整 argv/cwd、环境变量摘要、解释器和 pytest 包源码哈希、退出码、墙时、
stdout/stderr、JUnit、controller/worker runtime JSON，以及运行前后的 Git HEAD 和输入文件清单。

完整原生保护和合法生产者—消费者链应使用交付报告登记的入口，在新的 run 名称下运行，不复制
旧绿色 `state.json`：

```bash
.venv/bin/python docs/reviews/pc_a/w1_cache_repair_2026-09-12/run_native_protection.py
.venv/bin/python docs/reviews/pc_a/w1_cache_repair_2026-09-12/run_integration.py \
  /absolute/new/output/comparison
```

这两条长命令须串行独占资源；执行前先读脚本参数和交付报告中的输出目录合同，避免覆盖既有封存
证据。完成后仍只能称 W1 独立动态复现，不能据此签署统一源码验收或科学收益。
