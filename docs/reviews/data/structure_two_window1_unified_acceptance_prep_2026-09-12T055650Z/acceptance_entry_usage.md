# 统一版本验收入口：运行与交接

入口：`tools/structure_two_unified_acceptance.py`。它编排既有验证器，不替代验证器，不签发授权，也没有任何科学 PASSED 状态。当前只有窗口一准备任务完成条件；统一验收为 `WAITING_UNIFIED_SOURCE`。

## 现在可以复跑的准备命令

在窗口一真实工作树运行，选择此前不存在的运行目录：

```sh
cd /private/tmp/cpswm-s2-evidence-repair-window1
.venv/bin/python tools/structure_two_unified_acceptance.py \
  --run-dir /private/tmp/cpswm-s2-evidence-repair-window1/docs/reviews/data/structure_two_unified_acceptance_runs/prepare-NEW-TIMESTAMP
```

此命令真实运行受保护的原生布局/来源探针，读取匹配的 `.venv`、依赖与环境，保存输入快照，退出 0 只表示完成准备，状态仍为 `WAITING_UNIFIED_SOURCE`。没有运行五类长实验、训练比较器或生成新 checkpoint。不能把退出 0 解释为统一验收通过。

运行日志必须在固定 `docs/reviews/data/structure_two_unified_acceptance_runs/` 下新建子目录。该区域作为输出排除，避免“准备 A → 执行 B”因 A 的日志被当成新输入而永远无法匹配；编排器、本分支测试、配置、源码、静态工件与其他文档仍纳入输入快照。已经核验的比较包虽在该输出区，却从实际生成阶段开始单独冻结其文件内容，并持续复核，不能在后续阶段换入其他窗口的包。

## 明确统一源码之后

本轮**没有**指定统一工作树，也不会推测一个。后续必须先完成：

1. 在用户明确指定的统一工作树整合源码；保留两套受保护入口各自在全新子进程内执行，不在同一进程混用来源 guard。
2. 依据影响清单，将五类 `DEFAULT_OUTPUT`、`CURRENT_DIRECTORY`、历史报告、原生 receipt/checkpoint 消费路径及 P0 具体排除项全部改成新证据版本。旧结果不动。聚合器没有 `--output-dir`，不能仅向最后 checkpoint 传 `--output` 就假定全部消费者已切换。
3. 窗口三真实关闭第四轮三个缺口后，将经过源码审查的新增测试 node ID 填入入口源码的 `CLOSURE_TESTS`：公开低层修订原子性、已纠正历史重新冻结、纠正后跨运行语义身份。当前映射有意为空，执行会拒绝；不能由运行参数、任意报告或三个重复旧正例替代。测试节点本身仍需人工/独立代码审查，编排器不能证明断言的科学完备性。
4. 完成匹配 `.venv`，固定统一 HEAD 和全部输入，先执行一次准备命令读取真实输入摘要。必须使用 Python 3.13，`.venv` 不能指向别的工作树；不伪造环境指纹。外加 `PYTHONPATH`、`PYTEST_ADDOPTS`、`PYTEST_PLUGINS`、优化模式或禁用插件会被拒绝，防止暗中缩减矩阵。

随后才可运行以下命令（占位符必须来自该统一树的实际准备结果，不是本窗口旧摘要）：

```sh
cd /absolute/path/to/EXPLICIT-UNIFIED-CHECKOUT
.venv/bin/python tools/structure_two_unified_acceptance.py \
  --unified-root /absolute/path/to/EXPLICIT-UNIFIED-CHECKOUT \
  --expected-head ACTUAL-UNIFIED-COMMIT \
  --expected-input-sha256 ACTUAL-PREPARED-INPUT-DIGEST \
  --execute \
  --run-dir /absolute/path/to/EXPLICIT-UNIFIED-CHECKOUT/docs/reviews/data/structure_two_unified_acceptance_runs/full-NEW-TIMESTAMP
```

不能在窗口一入口传另一个 root 冒充统一代码；必须执行统一树自己的入口，入口代码对象也必须对应其磁盘冻结源码。既有或后来出现的正式结果、receipt、checkpoint、审计日志目录会阻止生成。两个可变索引 P0/v0.5 audit 先保存原字节，禁止不安全别名；本轮并未执行这些写入。

## 固定运行顺序

源与环境在每阶段前后核对；每个命令使用统一树实际 `.venv`，命令行由源码固定，不接收自定义替代命令或外来通过回执。

1. W1 入口/历史覆盖/发布保护矩阵（含真实跨根完整历史重放）。
2. W2 四文件比较、归因、执行来源及完整伪造矩阵。
3. W3 原16文件、后续修订/主干三文件、邻接与自动阶段组，以及明确新增的三类缺口闭环测试。
4. W2 比较包真实生成、完整重算、归因生成、归因完整重算。
5. 五类当前结果真实生成、完整重算。
6. 历史报告生成、完整历史验证、第二入口的完整历史验证。
7. v0.5 兼容性记录、P0、真实原生工程矩阵（其中包含全部核心测试、P0、mypy、Ruff、编译和离线锁环境检查）。
8. 新 checkpoint 强制 fresh 生成及再次完整 fresh 验证，没有 `--no-fresh-recomputation` 替代项。
9. 检查点对抗与当前性矩阵；末尾再次核对原生入口布局、实际环境、已生成工件、完整输入。

实际精确 argv 由每阶段写入 `state.json`；原生工程矩阵自己的命令与完整日志仍由原生 receipt 保存。关键三窗口及 checkpoint 矩阵要求非空 JUnit，任何 failure/error/skipped/xfail 都阻止完成。完整核心的既有科学 xfail 与可能的宿主限制仍由原生回执如实记录，不能更改断言或把 skip 计作通过；若有关键宿主受限项，按原生要求在正确权限下另行完成并记录。

只有本次所有固定阶段真实完成、前后来源和环境相同、已验证工件未被替换，状态才可为 `COMPLETED_REQUIRED_RECOMPUTATION`。它表示本地规定命令完成，不建立独立托管、执行认证、方法有效性、科学门通过或消融授权。

## 失败、中断、重试

- 非零退出、源码/HEAD/环境变化、已验证工件被修改、空/跳过矩阵：`FAILED`，后续阶段不执行。
- SIGINT/SIGTERM：`INTERRUPTED`，终止整个子进程组，不能让后代继续发布。保留完整已输出 stdout/stderr、退出码、前后来源与错误。
- SIGKILL、掉电或磁盘不可写可能无法写终态；留下的 `RUNNING/STARTING` 用 `--inspect-run` 只报告 `INCOMPLETE_RUN`，不推断成功。
- 没有 resume，也不接受载入旧状态跳过阶段。相同 run 目录被拒绝。使用新目录从第一阶段完整开始；若上次已发布部分正式产物，应保留它们，在重新冻结源码前选择新的证据版本和消费者路径，再全量重跑。不能删除失败证据争取重试通过。
- `--inspect-run` 是读诊断记录，不承认它为可复用的执行证明；手改 JSON、重新哈希或拼接旧状态无法成为执行输入。

## 本轮测试的边界

最小 Git fixture 使用真实子进程、真实 pytest 和实际共用编排引擎验证顺序、故障、退出码、日志、重试与产物替换；其完成标识为 `STAGES_COMPLETED_NOT_AUTHORIZATION`。另有真实窗口一 CLI 准备、错误 root、合法/旧入口缓存、真实原生布局的五类正负路径。它们不是三个窗口在统一源码上的实验，不以 fixture 成功声称统一验收完成。

当前仍依赖可信解释器、标准库、OS 和进程完整性；不能抵抗任意恶意解释器/整个协调器替换、进程内 monkeypatch 或所有瞬时修改再恢复竞态。可验证的本地流程与来源边界不应升级成独立认证体系。
