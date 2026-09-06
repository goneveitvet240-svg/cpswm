# 结构二 action death test 搜索效用更正，2026-09-05

协议版本：`structure-two-action-death-test@0.2-search-utility-corrected`
被取代协议：`structure-two-action-death-test@0.1`（保留为历史 regression proxy）
证据等级：不改变任何证据等级。本次更正只修 evaluator（评估器），不产生新的科学结论。

---

## 1. 结论摘要

1. 旧 `@0.1` 的 `_search_cost` 与各方法的 `predict(SEARCH)` 是**两套互不相干的策略**。
   所有 `@0.1` 的 `search_cost` 与 `mean_search_cost` 数值**全部撤销**。
2. 旧 `_scientific_status` 只读 `put_back_error_rate`，却输出“strictly better”这种可被
   理解为完整科学胜负的措辞。该输出降级为 `legacy_put_back_only_diagnostic`，并硬编码
   `paper_claim_allowed=false`、`route_a_primary_utility_evaluated=false`。
3. 组合 A 冻结路线只冻结了「primary utility = cumulative action regret，越低越好」和三条
   硬护栏，**没有**冻结它的组成项权重、容器检查代价、搜索失败惩罚或每容器耗时。因此
   `SEARCH_UTILITY_CONTRACT_UNRESOLVED` / `ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED`
   为失败关闭状态，superiority 无法被授权。
4. `stage_local_forgetting_factor = 1.0` 经查是**冻结设计**而非未填参数，保持不变；补上
   合同表达、设计说明、拒绝非 1.0 的测试，以及与 runtime 默认值的绑定校验。
5. 当前 v0.4 benchmark 的搜索语义结构上是正确的（correctness 与 cost 消费同一个
   `search_order`），但它依赖两个未注册常数，已在报告中显式登记为未决，而不是改数。

---

## 2. bug 根因

### 2.1 缺陷一：评估器猜策略，并以元组顺序作为未注册 fallback

```python
belief_order = list(locations)                 # 未注册的 fallback 搜索策略
if isinstance(state, _PchmpCcrrRgrcMethod): ...
elif isinstance(state, (_OStarMethod, _STARMethod)): ...
```

`locations` 是一个**无序注册表**，元组顺序不携带任何机器人可见信息。AMG 与 DynaMem 没有
被 `isinstance` 分支命中，于是按原始元组顺序计价。

实测（seed 1，把真值位置从元组首位移到末位）：

| 方法 | 预测是否改变 | `search_cost` |
|---|---|---|
| AMG | 否 | 1 → 4 |
| DynaMem | 否 | 1 → 4 |

整份报告层面（seed 1，置换 `(2, 0, 3, 1)`）：

| 方法 | 旧 `mean_search_cost` | 置换后 | 逐日代价是否一致 |
|---|---:|---:|---|
| AMG | 1.7812 | 2.3125 | 否 |
| DynaMem | 1.7812 | 2.3125 | 否 |
| O-STaR | 1.5938 | 1.5938 | 是 |
| STAR | 1.5938 | 1.5938 | 是 |
| PCHMP×CCRR×RGRC | 1.6875 | 1.6875 | 是 |

### 2.2 缺陷二：被计价的行程不是任何方法给出的答案

五个方法的 `predict(SEARCH)` 全部返回“最后一次观察到的位置”。`_search_cost` 却给
O-STaR / STAR / 新方法**免费发放了一整条它们从未输出过的 belief ranking**（可以提前停止，
因而更便宜），给 AMG / DynaMem 发放了原始元组顺序。

seed 1，32 天内 `belief_order[0] != predict(SEARCH)` 的天数：

| 方法 | 不一致天数 |
|---|---:|
| AMG | 19 / 32 |
| DynaMem | 19 / 32 |
| O-STaR | 13 / 32 |
| STAR | 13 / 32 |
| PCHMP×CCRR×RGRC | 14 / 32 |

后果：`search_correct`（用 `predict`）与 `search_cost`（用 `belief_order`）可以互相矛盾——
一次“正确”的搜索可以被计为 4，一次错误的搜索可以被计为 1。

### 2.3 缺陷三：错误的单点搜索被固定计价为 1

单点方法猜错时，旧模型在它自己的 `belief_order` 上继续走，或直接返回 1，**从不收取失败
惩罚**。失败因此可能比一次诚实的、成功的多容器搜索更便宜。

---

## 3. 修正后的唯一搜索语义

每个方法必须输出显式的 `SearchPlan`（搜索计划）输出合同：

```text
SearchPlan(method_id, registered_locations, visit_order, plan_kind)
```

* `visit_order` 就是机器人真正打开的容器序列，按序打开，命中目标即停止；
* `plan_kind` 由内容推导并在校验器中比对，**无法伪造**；
* `visit_order` 不得重复、不得包含未注册位置、不得为空；
* 评估器**不再**追加“剩下的位置”——方法没点名的容器就是没被打开的容器。

计分（`score_search_plan`）：

| 量 | 定义 | 是否需要价格 |
|---|---|---|
| `first_choice_correct` | `visit_order[0] == target` | 否 |
| `target_found_in_plan` | `target in visit_order` | 否 |
| `inspected_container_count` | 命中位序，未命中则为 `len(visit_order)` | 否 |
| `search_path_length` | 与上者同一次行走 | 否 |
| `search_cost` | `inspected × 每容器代价`，未命中再 `+ 失败惩罚` | **是** |
| `search_time_seconds` | `inspected × 每容器秒数` | **是** |

`search_correct`、`search_cost`、search path length、search time 全部由**同一个** plan 读出。
禁止 `isinstance`；禁止 `list(locations)` fallback；错误的单点搜索是「1 次检查 + 失败惩罚」，
不再是固定的 1。

### 3.1 失败关闭

冻结材料没有注册每容器检查代价、失败惩罚和每容器耗时，因此**不自行发明权重**：
未提供 `SearchUtilityContract` 时，`search_cost`、`mean_search_cost`、
`search_time_seconds` 全部为 `None`，状态为 `SEARCH_UTILITY_CONTRACT_UNRESOLVED`。
不需要价格的维度（是否找到、检查了几个容器、路径长度）照常报告。

`SearchUtilityContract.frozen_protocol_reference = None` 表示开发用价格：能出数，
但 `authorizes_paper_claim` 恒为假。

### 3.2 更正后的判别力结论

五个方法的搜索计划完全相同（都是「最后观察到的位置」的单点计划）。因此：

* 更正后 `search_error_rate` 与 `mean_inspected_container_count` 在五个臂上一致；
* 旧数值中 O-STaR/STAR 看起来“搜索更便宜”，**完全是 evaluator 的产物，不是方法的性质**；
* **`@0.1` 的搜索维度对五个臂没有任何判别力**，任何基于它的排序都必须撤销。

---

## 4. scientific status 更正

### 4.1 旧 v0.1

`_scientific_status` 只比较 `put_back_error_rate`，输出 “new method strictly better on
put-back error”。现改为结构化的 `LegacyPutBackOnlyDiagnostic`：

```text
diagnostic_id                     = legacy_put_back_only_diagnostic
comparison_scope                  = put_back_error_rate_only
paper_claim_allowed               = False        （类型层面固定）
route_a_primary_utility_evaluated = False        （类型层面固定）
primary_utility_metric            = cumulative_action_regret
unresolved_contract_fields        = <12 项未决字段>
```

`scientific_status` 字符串一律以 `legacy_put_back_only_diagnostic: ` 开头，措辞中不再出现
`strictly better`（有测试断言整份报告 JSON 不含该措辞）。

### 4.2 当前 v0.4 审计

冻结路线（`docs/结构二/方向结构二_组合A技术路线冻结_2026-08-26.md` §已冻结的五项选择 1）
只说：primary utility 为 cumulative action regret、方向越低越好；owner contamination、
recovery latency、full-rerun equivalence 是硬护栏，不进入可被权重抵消的综合分数。

实测当前实现：

| 项目 | 现状 | 判定 |
|---|---|---|
| 组成项 | `put_errors + search_errors`，各为每步 0/1、权重 1 | 冻结材料**未**规定组成项与权重 |
| 单位 | 每 episode 的无权重错误事件计数 | 冻结材料**未**规定单位 |
| 搜索路径代价 | 完全**不在** regret 内，只作为 secondary | 冻结材料未规定是否应计入 |
| 搜索失败惩罚 | 目标不在计划内时按 `len(known_locations)` 计入 path cost | **未注册常数** |
| 每容器耗时 | `mean_search_time_seconds = 5.0 × path cost` | **未注册常数** |
| 三个指标别名 | `mean_search_path_cost` = `mean_search_path_length` = `mean_search_cost` | 同一个量的三个名字 |
| oracle reference | `oracle_upper_bound` 的 `cumulative_action_regret = 0.0` | 已登记 |

结论：v0.4 的**搜索语义结构正确**（correctness 与 cost 都消费 `_Prediction.search_order`，
有测试固定“首选命中 ⇒ 代价恰为 1；首选未命中 ⇒ 代价 > 1”），但 **cumulative action regret
的合同未决**。因此不改任何历史数值，改为在报告中显式输出：

* `primary_utility_definition`（组成项、单位、oracle reference、未决字段）；
* `unresolved_utility_contract_fields`（12 项）；
* `route_a_primary_utility_evaluated = False`；
* `unregistered_search_metric_assumptions`（3 条未注册常数/别名声明）；
* `scientific_verdict`：失败关闭的 `ScientificVerdict`。

`ScientificVerdict` 的判定顺序即为护栏本身：

1. 效用合同未决 → 先于任何数值比较直接阻断；
2. 硬护栏失败**或未测量** → 阻断，且不可被 primary utility 的任何改善抵消；
3. primary utility 必须严格优于每一个 reference 臂（打平不算赢）；
4. secondary 指标变差 → 记录为 `secondary_regressions` 并**扣留**判决；secondary 指标变好
   **永远不能**授予判决。

`superiority_supported` 现在同时要求 engineering superiority、无 paper gate failure、
verdict 授权、以及 route-A primary utility 已被评估；报告的 model validator 会拒绝任何
与 verdict 不一致的 superiority 断言。

---

## 5. `stage_local_forgetting_factor` 审计（不改值）

* **它是冻结设计。** `docs/结构二/方向结构二_神经摊销类型化粒子修订与可逆巩固方法冻结_v1.0.md`
  §2 原文：「阶段内遗忘因子固定为 1。分布变化由显式阶段竞争处理，不能用无来源指数遗忘替代。」
  即：regime 内不遗忘，阶段变化由 CF-BOCPD / CCRR 处理。
* 因此**没有**把 `ge=1.0, le=1.0` 放宽为 `ge=0.0, le=1.0`。RLS runtime 接受 `(0, 1]` 是
  runtime 的可行域，不是这份回执的可选域。
* **它此前确实是无效字段**：除选择合同与 JSON 回执外无人读取。现补上
  `STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS` 与
  `verify_stage_local_forgetting_runtime_binding()`，对四处 runtime 默认值做绑定校验：

  ```text
  cpswm.system.continual.rls.core.RLSConfig.forgetting_factor
  cpswm.system.continual.rls.habit_head.RLSHabitScoreHead.__init__.forgetting_factor
  cpswm.system.continual.project_one_regime_loop.PrototypeLoopConfig.forgetting_factor
  cpswm.system.evaluation_operations.project_one_protocol.ProjectOneProtocolConfig.forgetting_factor
  ```

  四处默认值均为 1.0，与回执一致；任何一处漂移都会让测试失败。
* 合同表达改为具名 `StageLocalForgettingFactor` 注解 + 常量
  `FROZEN_STAGE_LOCAL_FORGETTING_FACTOR` + 显式报错信息（说明「重新调参需要新的回执版本和
  独立 binding-resolution protocol，而不是改这份回执」），并新增拒绝
  `0.0/0.5/0.9/0.99/0.999/1.0001/2.0` 的测试。
* **哈希不变**（有测试固定）：
  * file SHA-256 `eff5e472346209053fe867e2ab53fdc455861e1e20125f192e6993e33bb33951`
  * content SHA-256 `a3ccafd6612a6ee57a855e82572524622b6f15f305924b3de99bd3e94e17ed2f`

  Task 9 (`structure_two_task9_protocol.py`)、backbone open-task protocol、授权 DAG 与
  binding-resolution 协议的 pin 全部保持有效，未做任何“同步重哈希”。

---

## 6. 受影响的历史报告与指标

### 6.1 必须撤销

| 项目 | 处置 |
|---|---|
| `@0.1` 的 `ActionDayResult.search_cost`（全部） | 撤销 |
| `@0.1` 的 `ActionMethodReport.mean_search_cost`（全部） | 撤销 |
| 依据 `@0.1` 搜索代价对五个臂做的任何排序 | 撤销（该维度无判别力） |

参考：`@0.1` 在 seeds (1, 2, 3) 上曾输出的 `mean_search_cost`
（AMG 1.7812、O-STaR 1.7604、DynaMem 1.7812、STAR 1.7604、PCHMP×CCRR×RGRC 1.6250）
仅作为“被撤销数值”的记录，不得再引用。

**没有**任何仓内工件存储过 `@0.1` 的报告：该 runner 只被测试调用，
`apps/evaluation_runner/run_structure_two_action_death_test.py` 早已改跑 v0.4。
`docs/` 与 `benchmarks/` 中也不存在旧的三种 status 字符串。

### 6.2 仅为 legacy diagnostic

`@0.1` 的 `scientific_status`（“strictly better / ties / worse on put-back error”）
仅为 `legacy_put_back_only_diagnostic`，`paper_claim_allowed=false`、
`route_a_primary_utility_evaluated=false`。

### 6.3 当前 v0.4 / v0.3 evidence 是否受影响

**不受本 bug 影响。** `ProjectTwoActionBenchmarkV02._score_predictions` 与
`project_two_multiseed_evidence` 都从同一个 `_Prediction.search_order` 读 correctness 与
cost，从未使用 `isinstance` 猜策略。以下工件的数值**不变**：

* `benchmarks/project_two_action/replay_evidence_v0_3/{run_summary,d0,d1}.json`
* `docs/experiments/project_two_action_benchmark_v0_2.md` §3 的全部表格

但它们的 `mean_search_cost` / `mean_search_time_seconds` 现在**必须**连同
`unregistered_search_metric_assumptions` 一起引用：5.0 秒/容器与 `len(known_locations)`
失败惩罚都不是冻结常数。

---

## 7. 仍需用户决定的效用合同选项

以下四项**必须由用户或预登记规则决定**，本次更正一律没有代为选择：

1. **cumulative action regret 的组成项与权重**
   - 选项 A：维持现状——只计 put-back 错误 + 搜索首选错误，各权重 1（须显式冻结成协议，
     并承认搜索路径长度不进入 primary utility）；
   - 选项 B：把搜索路径代价并入 regret，需给出 put-back 错误 : 每容器检查 : 搜索失败
     的三元权重与单位；
   - 选项 C：改为“净行动损失/步”，需同时冻结 verification cost 项。
2. **搜索失败惩罚**：目标不在计划内时收多少？（现 v0.4 隐含 `len(known_locations)`，
   v0.1 更正后为未决。）
3. **每容器检查的真实代价与耗时**：现 v0.4 隐含 5.0 秒/容器，无来源。需要真实机器人
   search/place/transfer 时间，或明确登记为仿真常数。
4. **三条硬护栏的数值阈值**与 primary utility 的 superiority margin：冻结文档已把它们列为
   fail-closed 执行绑定，目前全部“未测量”，因此 verdict 恒为不授权。

在 (1)–(4) 落定之前，`superiority_supported` 只能保持 `False`。

---

## 8. 边界声明

* 本次更正**没有**改变七算子范围、没有改变任何方法的预测、没有改变 v0.4 的任何历史数值。
* 测试通过**不等于**科学门通过：D0 合成回放的证据等级、AMG/O-STaR/DynaMem/STAR 的
  matched-adapter 身份、以及 D1–D4 门禁全部保持关闭。
* 本文件只更正 evaluator 与合同表达，不产生任何新的科学结论。

---

## 9. 因源码改动而漂移的「当前状态」工件（未在本分支重生成）

改动 `src/` 后，四个**按设计记录当前源码状态**的工件必然漂移。经用户决定，本分支**不**重新生成，
留待与 codex 的并行改动合并后在主工作树统一跑一次；在此之前下列 6 个测试为已知红灯，
根因唯一，与搜索效用语义无关。

| 工件 | git | 绑定内容 | 受影响测试 |
|---|---|---|---|
| `benchmarks/p0_checkpoint/content_manifest_v0_2.json` | 已跟踪 | `src/**/*.py`、`apps/**/*.py`、`configs/**/*.json` 内容哈希 | `test_p0_checkpoint_manifest.py::test_p0_checkpoint_v0_2_is_current_and_self_consistent` |
| `benchmarks/structure_two/structure_two_world_source_bundle_v0_5_compatibility_audit.json` | 已跟踪 | `current_file_count` 279→280、`current_source_bundle_sha256` | `test_structure_two_world_v0_5_protocol.py::test_round_one_frozen_source_bundle_is_bound_and_current_drift_is_explicit` |
| `benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/engineering_checkpoint.json` | 已跟踪 | 上面两个工件（`P0 content manifest is not current`） | `test_structure_two_engineering_trust_checkpoint.py`（2 项） |
| `artifacts/project_two_v04_development/structure_two_corrected_instrument_v0_3.json` | gitignore | `project_two_action_benchmark.py` 的 `action_evaluator_source_sha256` | `test_structure_two_corrected_instrument.py`（2 项） |

合并后的重生成顺序（必须按此顺序，后者绑定前者）：

```bash
# 1. P0 内容清单（v0.1 历史工件绝不重生成）
.venv/bin/python apps/evaluation_runner/generate_p0_checkpoint_manifest.py

# 2. v0.5 源码包兼容性审计：只刷新 current_* 两个字段，保留 claim_boundary，
#    FROZEN_V0_5_SOURCE_BUNDLE_{FILE_COUNT,SHA256} 常量绝不改
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (
    audit_v0_5_source_bundle_evidence,
)
path = Path(
    "benchmarks/structure_two/structure_two_world_source_bundle_v0_5_compatibility_audit.json"
)
stored = json.loads(path.read_text(encoding="utf-8"))
stored.update(audit_v0_5_source_bundle_evidence(Path(".")))
path.write_text(json.dumps(stored, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

# 3. 结构二工程信任检查点（绑定 1 与 2）
.venv/bin/python apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py

# 4. corrected-instrument 报告（未跟踪的本地产物，绑定 action evaluator 源码哈希）
.venv/bin/python apps/evaluation_runner/run_structure_two_corrected_instrument.py --recompute
```

**不得重生成、本次也确实没有动过的冻结工件**：

* `benchmarks/p0_checkpoint/content_manifest_v0_1.json` 及其 git baseline audit；
* `FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT = 245` 与 `FROZEN_V0_5_SOURCE_BUNDLE_SHA256`；
* corrected-instrument v0.2 immutable manifest 与其历史报告；
* selected-method 回执的 file / content 双 SHA-256（已由测试固定，本次修改后仍完全一致）。
