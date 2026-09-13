# B7 数据预检、可见前缀与泄漏独立审核（电脑 B）

## 结论

本轮冻结并独立审核 A 数据预检实际代码 `57e8576c7dd48203839cdd0ae3a4cdb295db7185`；对应交付提交为 `6e07ab682a9ec15e959e1a50001e237877bc4773`，实际代码提交的父提交为 `bc051fa5f7ffb64e5bfbdada1ef277a2c8764b5f`。未修改 A 生产实现，未运行训练或方法臂，未读取或生成封存验证/确认世界。

结果：A 原有 43 项检查的独立直接等价执行为 **43/43 通过**；训练世界 method-free 重算与 A 的 `run_03/coverage.json` **逐字段完全一致**。新增 7 个对抗探针中 3 个防御通过、3 个确认实现缺陷、1 个确认时间一致性风险（其是否升级为缺陷取决于 `metadata.recorded_time` 的正式语义）。因此 B7 组件回归通过，但泄漏/重复边界不能签收。

## 冻结对象和运行环境

| 项目 | 实际值 |
|---|---|
| 仓库 | `goneveitvet240-svg/cpswm` |
| A 交付 SHA | `6e07ab682a9ec15e959e1a50001e237877bc4773` |
| 实际被测代码 SHA | `57e8576c7dd48203839cdd0ae3a4cdb295db7185` |
| 实际代码父 SHA | `bc051fa5f7ffb64e5bfbdada1ef277a2c8764b5f` |
| 平台 | Linux 6.18.35 x86_64, glibc 2.39 |
| 解释器 | CPython 3.12.14，`/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python` |
| 依赖 | numpy 2.3.5；pydantic 2.13.5；pytest 未安装 |
| 加载路径 | `PYTHONPATH=src:tests`，根目录 `/workspace/scratch/b158d995e8cc/cpswm_b7_snapshot` |
| 执行方式 | 用最小 `fixture/parametrize/raises/approx` 断言垫片直接调用冻结测试文件中的 43 个展开测试函数；没有重写被测断言 |

关键被测文件的本地 Git blob 与冻结提交树一致：

| 文件 | Git blob |
|---|---|
| `src/cpswm/data_preflight/__init__.py` | `c637c54abbfd013d8fa4de07964a6fa5fd7fed50` |
| `src/cpswm/data_preflight/simulator_capture.py` | `fb2fa03afbc296369d14b6395dfa049146dbb086` |
| `src/cpswm/data_preflight/train_coverage.py` | `20f74fb4b4826500d384100b4d45e924a6fc61e6` |
| `src/cpswm/data_preflight/visible_prefix.py` | `4cacd8e68b07ef2ed3123d7de60f42b595e751be` |
| `tests/test_structure_two_data_preflight.py` | `04a1152ba568486d7d31e7a7d00ecc3493b2a070` |
| `tests/test_d0_shift_scenarios.py` | `f7e0ca5057f5af1c737ef218d0314d1d1c0c4d45` |
| `tools/structure_two_data_preflight.py` | `0e9bc159b725691a455af8053847410b0c902e87` |
| rolling-train v0.4 配置 | `6cbb41e710bf0a1e7bd2cd38a0513dbbe1ee3e74` |
| v0.2 世界 manifest | `f1343b8cb4ff2143d87cf203ec97b0f96bb17d67` |

完整 SHA-256 在 `independent_audit_final_linux_py312.json` 与 `coverage_independent.json` 中。测试结束后才生成源码摘要，因此也是执行后的源码身份；运行没有改写源码。

## 完整命令与结果

```bash
PYTHONPATH=src:tests python tools/b7_preflight_independent_audit.py \
  --output docs/reviews/pc_b/b7_preflight_audit_2026-09-13/independent_audit_final_linux_py312.json \
  --junit docs/reviews/pc_b/b7_preflight_audit_2026-09-13/independent_audit_final_linux_py312.junit.xml
```

- 退出码：0
- 耗时：审计脚本记录 3.197 秒，外层命令约 3.94 秒
- 结果：原 43 项 43 passed / 0 failed；扩展 3 defense_passed / 4 vulnerable / 0 probe_error
- JUnit：两个 testsuite；`b7-delivery-43` 为 43 tests / 0 failures / 0 errors，`b7-adversarial-extensions` 为 7 tests / 4 failures / 0 errors。扩展 failure 是确认的防御缺口，不是审计基础设施失败。
- 唯一警告：冻结负例以 `model_copy(update={"outcome": "not_observed"})` 故意绕过枚举后，pydantic 序列化发出一条与 A `run_03` 相同性质的 warning。

```bash
PYTHONPATH=src python tools/structure_two_data_preflight.py coverage \
  --output docs/reviews/pc_b/b7_preflight_audit_2026-09-13/coverage_independent.json
```

- 退出码：0
- 耗时：1.418 秒（user 2.093 秒，sys 0.054 秒）
- 与 A `run_03/coverage.json`：解析后的 JSON 完全相等

```bash
PYTHONPATH=src python tools/structure_two_data_preflight.py simulator-preflight \
  --output docs/reviews/pc_b/b7_preflight_audit_2026-09-13/simulator_preflight_linux_py312.json
```

- 退出码：2（合同规定的未安装状态）
- `ai2thor_installed=false`、`real_simulator_run_verified=false`、`status=BLOCKED_MISSING_AI2THOR`
- 未尝试安装 SDK、启动 Unity 或伪造成功。

## 可见前缀扩展覆盖

| 类别 | 合法非空参考 | 对抗/边界 | 结果 |
|---|---|---|---|
| 事件时 + 到达时 | 机会、检测、人物证据均在 cutoff 精确边界 | 晚到检测、晚到人物证据、全部未来、空前缀 | 通过；边界为包含语义 |
| 乱序 | 两条合法观察及检测 | 机会、检测、arrival map 同时反序 | 通过，输出及回执完全相同 |
| 重复 | 单人物证据簇 | 同一检测、同一 `evidence_cluster_id`、新 record UUID 的内容副本 | **缺陷：接受并输出两次** |
| oracle/额外真值 | controlled-noise 人物证据 | oracle actor、CLI 顶层 truth、confirmation partition | 原冻结负例通过 |
| JSON 封装 | 唯一 `partition=development` | 同一 JSON object 同时出现 confirmation 和 development | **缺陷：last-wins 后成功导出** |
| 嵌套字段 | `Pass` 合法采集请求 | 合法 action 名下嵌套 `evaluator_truth.true_actor` | **缺陷：原样进入候选及磁盘** |
| prior/后验 | posterior 与 reference prior 分开导出 | 仅改变 prior、保持 posterior | 通过；两字段仍可区分，特征回执改变 |
| 来源回执 | 单机会/检测/人物记录 | 独立重算每条内容摘要和整体特征摘要 | 通过 |
| 记录时间一致性 | event/received/recorded 同时 | `received_at <= cutoff < metadata.recorded_time` | **风险：记录仍进入前缀** |

## 确认缺陷和最小后果

### B7-DUPLICATE-ACTOR-CLUSTER（高）

`visible_prefix.py:59-61` 只对 `metadata.record_id` 去重；`visible_prefix.py:86-96` 不检查人物证据簇唯一性；`visible_prefix.py:123-133` 会把同一来源检测、同一 `evidence_cluster_id`、相同 posterior/prior 的新 UUID 副本全部输出。

实测合法参考有 1 条 actor evidence；攻击后有 2 条，两个模型输入 payload 完全相同，整体 `feature_sha256` 被改变。因此攻击不是 no-op，后续消费者若逐条累积会把同一证据重复计权。

建议：在任何输出构造前，至少拒绝重复 `(source_detection_result_id, evidence_cluster_id)`；如允许同簇分片，必须有冻结的分片身份、权重守恒和聚合合同，不能按 record UUID 默认视为独立证据。

### B7-DUPLICATE-JSON-KEY（高）

`tools/structure_two_data_preflight.py:39-43` 使用默认 `json.loads`，重复 key 被静默 last-wins。最小输入同时包含 `"partition":"confirmation"` 和 `"partition":"development"`，CLI 返回 0、创建输出，并在回执中报告 development。它绕过了该 CLI 明确表达的 confirmation 拒绝边界；原始输入 SHA 虽能事后显示字节变化，但不能消除已经发生的歧义解析。

建议：使用递归 `object_pairs_hook` 拒绝任一 object 的重复 key，再执行 envelope/partition 验证；将拒绝测试覆盖顶层 partition、received_at UUID 和嵌套记录字段。

### B7-NESTED-REQUEST-LEAK（高）

`simulator_capture.py:98-100` 只校验 action 名是否位于允许集合；`simulator_capture.py:132-146` 将整个任意 request 原样放进方法侧 observation candidate。实测请求 `Pass + nested.evaluator_truth.true_actor` 被 controller 执行，并原样出现在返回候选和 `observations/000000.json`。

建议：为每个允许 action 冻结可见参数 schema/allowlist，拒绝未知和递归未授权字段；完整原始 request 只能进入 evaluator/audit-only 回执，候选中仅保留验证后的动作及公开参数（或其绑定摘要）。这不要求替用户选择动作集合或连续状态含义。

### B7-ARRIVAL-PRECEDES-RECORDED-TIME（中，需合同确认）

`visible_prefix.py:78-84` 只要求 arrival 不早于业务事件时间，`visible_prefix.py:97-102` 也只用业务事件和 arrival 决定前缀。将 opportunity 的 `metadata.recorded_time` 改为 cutoff 后三天，同时声明 `received_at=cutoff`，记录仍进入模型输入。

如果 `recorded_time` 表示该来源记录的创建/登记时间，这是违反因果顺序的未来记录泄漏，应要求 `received_at >= metadata.recorded_time`，并决定 `recorded_time >= event_time` 的时钟/回填规则。如果它被明确定义为不可信来源时钟，则不能用于接纳，但应把矛盾记录隔离并在 audit-only 中报告；当前合同没有把这一语义写清楚。

## 训练世界独立重算

仅使用已花费、明确 train sampling 的 v0.4 配置以及绑定的 v0.2 generator；没有使用 `downstream_prereservation_not_authorized_for_use` 中的 seed。

| 指标 | B 独立结果 |
|---|---:|
| 世界 | 24 |
| 轨迹 | 144 |
| 步 | 49,428 |
| observed / not_observed | 26,512 / 22,916 |
| unknown actor truth | 4,176 |
| handoff mechanism | 2,218 |
| perceived/true location mismatch | 3,505 |
| `true_identity_match=false` | 0 |
| 事件链模板 | 1（全部 `pick_up -> carry -> place`） |
| 六种 proposal operation 标签 | 每类 0 |

完整 H/R/I/C/Z/r/V 仍不具备训练覆盖：H、C、Z 仅部分；R、I、r、V 缺失。`verified_absence`、unknown location、真实 late arrival、execution feedback、连续测量/噪声模型未表示。`full_scope_training_ready=false` 是正确结论。

静态加固项：`audit_train_worlds` 校验 base manifest 的固定 SHA，但 rolling-train design 自身只在输出中报告 SHA，没有在执行前对期望摘要做 fail-closed 验证。当前冻结文件的实际 SHA-256 为 `ae538b466102a5b8282c24ab251989bf5f51e16451b1ffc9960736c09233e9f7`；统一验收必须把该摘要作为外部冻结输入，而不能只接受工具自报。本轮为遵守 method-free/封存边界，没有用替代 seed 动态攻击该点。

## 可用数据与明确缺项

本环境可用并已独立执行的是：冻结 train 配置、冻结 base manifest、确定性世界 generator，以及 method-free 24/144/49,428 重算。这里的“可用”不表示新训练授权。

本环境没有 A 机器的实际摄取 arrival journal、partition 托管证明、`.venv-ai2thor`、Unity 可执行文件或真实 controller；也没有 OS 级 evaluator/method 目录隔离证明。GitHub 交付中的真实 iTHOR 记录不是本轮可重跑的 B 本机资源，因而没有把它记作 B 独立仿真复现。封存 validation/confirmation 数据故意未读取，这不是遗漏。

## 分层结论与接收方

- 工程回归：原交付 43 项在冻结源码上直接等价执行 43/43 通过。
- 独立审核：确认 3 个可执行非 no-op 缺陷及 1 个需语义裁定的时间风险；B7 不能标为无缺陷签收。
- 默认能力：当前导出器只是初版 visible-prefix 组件；到达日志与 partition custody 仍依赖可信所有者，unknown map、完整类型化主干、修订记录和动作特征尚未接入。
- 统一验收：阻塞；需要 A 修复后发布单一新 SHA，再由 B 复跑 43 项和全部新增探针。
- 科学收益：本轮没有运行方法臂、训练或确认数据，不能据此主张科学收益。

下一接收方为 A 数据预检所有者：修复前三个确认缺陷；明确 `recorded_time` 语义；给 rolling-train design 增加外部冻结摘要入口。A 发布新 SHA 后，B 应在新冻结工作树复跑并记录修前/修后对照。电脑 B 汇总者可将本报告摘要串行写入 `STATUS_B.md`；本任务没有并发修改该文件。
