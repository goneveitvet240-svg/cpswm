# 复现

检出本分支实际源码 8f7edafd51cdf735ca9c65a7c8e4ac367cebdc68 的独立工作树。在该工作树使用 uv sync --frozen --extra dev --extra perception --extra hand-perception 创建真实环境。不要复制或符号链接另一工作树的 .venv 来声称环境独立。

基础命令：.venv/bin/python -m mypy src；.venv/bin/python -m ruff check src tests；.venv/bin/python -m ruff format --check src tests；.venv/bin/python -m pytest --collect-only -q。

两轮精确命令、cwd、环境、时长和退出码见 evidence/summary.json 的 review1 / review2；异目录与污染环境探针见归档 run_foreign_probe.py。部分探针含本机绝对路径，搬移时显式改为当前工作树及新输出目录，不能直接以旧路径结果声称新树复现。run_check.py 的子检查成功/失败以对应 JSON exit_code 为准，其封装进程本身仅写记录，不传递子退出码。

原版基线应在 base b6c6317a35c99cd95fe636251ce1e63bfba5f402 的独立树运行，不能覆盖修复树。原CI失败31节点及本机剩余27节点映射见 evidence/failure-triage.json；同一条件下本机19失败/8通过，不得当作LinuxCI验收。当前全仓命令仍会因当前材料准备/旧回执阻断；不能先改成skip再称通过。

归档包含失败、中间失败和成功日志及元数据；不含每个pytest临时数据库。哈希清单与逐成员读回只能核对记录完整性，不能证明独立执行。正式工程验收需冻结源码、实际运行所有准备/测试/回执生命周期并完整收集执行对账；既有入口 tools/structure_two_unified_acceptance.py 尚不能被当作已完成验收。
