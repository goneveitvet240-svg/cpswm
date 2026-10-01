# 复现当前输入准备与全仓诊断

功能源码为 `fd08b59bdc01ca9ffe4e9b159cb1393052711d15`，文档交接 `c8f1d29b90b60ef4ddc5303628c87def428d1d1b` 的功能文件相同。使用独立工作树和当前 `uv.lock` 重建实体环境；不要复制归档中的 macOS `.venv`。

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception
.venv/bin/python -m mypy src
.venv/bin/python -m ruff check src tests tools/prepare_current_validation_inputs.py tools/run_ci_regression.py
.venv/bin/python -m ruff format --check src tests tools/prepare_current_validation_inputs.py tools/run_ci_regression.py
.venv/bin/python tools/prepare_current_validation_inputs.py --output output/current-inputs-reproduction
```

输出必须是不存在的新目录。准备实际执行八条生成/完整重放/消费者命令；3900 秒预算及 60 秒收尾由独立进程组执行器管理。失败产物保留，不能复用其目录或把状态改成通过。脚本重建可变 P0，旧 P0 原字节保存在 `preserved-p0.json`；运行期间不要手工覆盖 P0。

准备成功后：

```sh
mkdir -p output/current-regression-reproduction
.venv/bin/python -m pytest -o addopts= --collect-only -q > output/current-regression-reproduction/collection.log
git rev-parse HEAD > output/current-regression-reproduction/source-sha.txt
.venv/bin/python tools/run_ci_regression.py --inputs output/current-inputs-reproduction --output output/current-regression-reproduction/execution --workers 4 --budget-seconds 3900 --grace-seconds 60
```

先核对收集命令实际退出 0，再启动回归；不要把收集失败忽略后继续。当前完整收集为 6758 项，不增加 `-k`、忽略模块或只跑此前成功的节点。本机运行设置 `OMP_NUM_THREADS=1` 与 `OPENBLAS_NUM_THREADS=1`，使用四个 worker；CI 使用自动 worker 数。准备和完整回归各自拥有 65 分钟执行预算，不意味着单个作业 65 分钟内完成二者。

搬移准备包时完整复制目录，将其中 `current-p0.json` 安装到新工作树的 `benchmarks/p0_checkpoint/content_manifest_v0_3.json`；然后从 `consumer_environment` 校验源码、材料和实际 P0，导出新目录路径。不要直接信任包内自报的旧绝对路径。输入准备只授予 `PREPARED_NOT_ACCEPTED`，不是工程验收或历史执行认证。

同实现者 A 自审的精确 argv、环境、时长、退出码、源文件摘要和日志保存在证据归档。原 R1 在 R2 之前完成；后一次 R1 重复执行是云端占位后恢复可读证据，不是新增独立样本。21 类完整重签攻击需要实际 CLI fresh replay，不能以重新计算 JSON 哈希替代。

全仓结果应将每个收集 node ID 与 JUnit 的唯一有名终态逐项对齐。匿名中断记录、缺失记录、重复记录不能算通过；skip/xfail 单列。严格统一工程回执仍要求其完整既有门槛，不因普通 pytest 退出 0 自动获得授权。当前历史 checkpoint 的 7 项失败及 dev-only 环境契约冲突另见 `ENGINEERING_DEPENDENCIES.md`。
