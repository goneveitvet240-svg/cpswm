# 方向结构二 N4：方案 B 混合可逆充分统计量与并发地图—任务规格 v1.0

日期：2026-08-22  
状态：N1 formal specification（正式规格）冻结；N2/N3 以本文件为验收依据。

## 1. 范围与决策权

本规格不删除、不替换结构二的七个候选算子：OPCEU、CHEH/ORRER、PCHMP、
CF-BOCPD、RGRC、CCRR、CIAV。方案 B 是这些算子的公共在线状态与地图—任务并发
骨架，不把论文范围缩小为计算成本、失效检测或单一 RLS 模块。

已有工作覆盖提醒必须保留：Damen–Hogg AMG 已覆盖多事件全局解释、事件似然和角色/
共享约束；O-STaR 已覆盖动态场景图、Dirichlet–Categorical 位置信念和个性化迁移；
DynaMem 已覆盖操作与探索中的在线动态三维语义记忆；STAR 已覆盖统一记忆—行动循环。
这些工作是必须公平增强的强基线，不是避开 RGRC、RLS 或地图—任务并发的理由。若要
形成创新，结构二必须提出新的状态、更新或优化机制，并在相同证据、感知、行动预算与
独立调参下验证。

用户已经选择以下组合，后续改变其中任何一项都需要用户决定：

| 编号 | 已选方案 | 本规格中的含义 |
|---|---|---|
| B | C2 + F4 + R4 | 混合充分统计量；阶段内不遗忘；快速可逆更新，数值失败时回放 |
| B-R3 | unresolved quarantine | 未决证据先进入隔离投影，通过路由/复核后晋升 |
| B-F1 | Dirichlet + RLS residual | 基础位置概率由 Dirichlet 表示，情境残差由 RLS 表示 |
| B-DC3 | source-cluster-excluded residual | 计算残差时排除同一来源证据簇，禁止自证和双计数 |
| B-P3 | constrained Bayesian risk gate | 晋升、动作和重规划均服从受约束贝叶斯风险门 |
| B-L3 | hard floors + counterfactual risk + uncertainty | 硬安全损失下限、任务反事实风险和不确定性惩罚同时存在 |
| B-TC3 | action-level version switch | 以动作级风险决定是否切换地图版本，只重规划受影响后缀 |
| B-AO3 | risk-reduction active observation | 主动观察优化预期风险下降，而不只优化熵下降 |
| B-VOI3 | learned proxy + exact verification | 学习型 VOI 代理只排序，精确风险验证器拥有最终否决权 |
| B-VT3 | offline oracle + online residual | 离线精确 oracle 监督，在线只校准残差并受约束 |
| B-PM3 | graph proxy + online RLS residual | 离线任务—地图图代理，在线 RLS 只学习残差 |
| B-GM3 | dual graphs + explicit bridge | 地图信念图与任务动作图分离，由显式依赖桥连接 |
| B-DB3 | hard candidates + soft relevance | 硬候选/依赖边不可被学习器删除；软相关权重可扩展候选 |
| B-BS3 | multi-source constrained supervision | 符号规则、规划器反事实、真实日志、主动干预、RGRC 修订共同监督 |

## 2. 第一轮审核与对抗审核冻结结论

| 路线 | 当前实现证据 | 对抗结论 | N4 处理边界 |
|---|---|---|---|
| OPCEU | inverse/stabilized propensity weighting（逆倾向/稳定化加权） | 不是潜在未观察事件的后验期望统计；同一证据可重复写入 | 作为基线保留；新账本必须按证据簇去重并承载期望统计增量 |
| CHEH/ORRER | 开放角色、修订/撤销/重激活与匹配 AMG 死亡测试 | 与 matched open-world AMG 同为 1.0，强基线优势未成立 | 不删除；输出修订必须成为 RGRC 的受约束输入 |
| PCHMP | 仅规格/接口 | 没有消息传递、人物置换等变或解释子图实现 | 本轮只定义它与证据簇/图代理的接口，不宣称完成 |
| CF-BOCPD | 联合 run-length × cause beam（游程长度×原因束） | 原因已经作为分离通道输入；identity cause 缺失；公平基线未完成 | 原因后验作为写入门，但不能宣称已解决因果可识别性 |
| RGRC | 标量 soft-count 追加账本与 O(k) 撤销 | 任意父修订、错修订撤销、非法状态转换和无完整性链可被接受 | 修复状态机；扩展为多统计量证据簇增量 |
| CCRR | hard regime routing（硬阶段路由） | 没有 stay/create/reactivate/unresolved 后验竞争 | 新状态提供阶段候选接口，不宣称完整 CCRR |
| CIAV | 方向三信息增益/行动效用规划器 | 未接 CF/RGRC/方案 B 风险；DecisionContext 未接运行时 | 新建双图依赖桥、动作级切换和精确风险否决接口 |

当前全量测试通过，只证明已有断言没有回归；不等价于上述研究路线闭合。

## 3. 混合充分统计量

### 3.1 基础状态

对每个 `(actor, object, regime, location, parameter_block)` 键维护：

1. Dirichlet soft count（Dirichlet 软计数）

\[
\alpha = \alpha_0 + \sum_c \Delta\alpha_c
\]

2. RLS / ridge natural statistics（递归最小二乘/岭回归自然充分统计量）

\[
A = \lambda I + \sum_c w_c x_c x_c^\top,\qquad
b = \sum_c w_c x_c y_c,\qquad
\theta = A^{-1}b
\]

3. information-form belief（信息形式信念）

\[
\Lambda = \Lambda_0 + \sum_c \Delta\Lambda_c,\qquad
\xi = \xi_0 + \sum_c \Delta\xi_c
\]

其中 `c` 是 evidence cluster（证据簇）。阶段内遗忘因子固定为 1；阶段切换不是渐进遗忘，
而是 CCRR 在 stay/create/reactivate/unresolved 间进行显式竞争。

### 3.2 来源绑定增量

每个证据簇生成一个不可分割的增量 bundle（增量束）；bundle 可包含多个位置/参数键的
不可变记录，但必须共享事件、修订、来源和授权身份，并整簇原子晋升：

\[
\Delta S_c=(\Delta A_c,\Delta b_c,\Delta\alpha_c,\Delta\Lambda_c,\Delta\xi_c)
\]

记录必须绑定 `event_hypothesis_id`、`revision_id`、`parent_revision_id`、
`evidence_cluster_id`、源记录集合、授权范围、模型/代码版本、输入 watermark（高水位）与
内容哈希。`semantic_dedup_id` 和 `evidence_cluster_id` 均不得重复生效。

### 3.3 B-DC3 排除同源残差

对簇 `c` 产生 RLS 残差监督时，基础预测必须从排除 `c` 的投影计算：

\[
e_c = y_c - \hat y(S_{-c})
\]

禁止先让 `c` 更新 Dirichlet，再用含 `c` 的后验产生同一条 RLS 标签。实现必须暴露
leave-one-cluster-out（留一证据簇）查询，并由测试证明重复簇不能增加质量。

## 4. RGRC 状态机与撤销

合法状态转换只有：

```text
QUARANTINED --promote--> PROMOTED --retract--> RETRACTED
QUARANTINED --supersede-by-named-revision--> RETRACTED
RETRACTED --new corrected revision with valid parent--> REACTIVATED
```

`REACTIVATED` 不是原记录复活，而是同一事件的新修订进入；旧记录保持撤销。必须拒绝：

- promoted 的重复 promotion；
- 多键证据簇的部分 promotion；
- quarantined 的直接 reversal；
- reversal 中的 revision 与目标不一致；
- 不存在、跨事件或形成环的 parent revision；
- 已撤销记录再次晋升；
- record、watermark、授权或内容哈希不一致；
- 同一 evidence cluster / semantic dedup 的重复有效写入。

快速 downdate（降阶更新）后若 `A` 或 `Λ` 不再正定、条件数越界或与从日志完整重建不一致，
必须标记 `replay_required` 并从受影响阶段日志重建；不得静默裁剪后继续。

## 5. 地图维护与任务执行并发语义

答案是“同时进行，但不是共享可变对象”。采用 MVCC-style snapshot isolation
（类似多版本并发控制的快照隔离）：

1. 地图写入器继续接收新观察并生成单调 `map_version`；
2. 当前任务动作固定读取不可变 `belief_snapshot_id + map_version`；
3. 地图信念图保存实体、关系、统计量和不确定性；任务动作图保存动作、顺序、安全条件；
4. 显式依赖桥保存每个动作的 hard read/write dependencies（硬读写依赖）与 learned soft
   relevance（学习型软相关性）；
5. 新版本到达时先比较动作后缀依赖和受约束贝叶斯风险；无关更新继续执行，相关但安全的
   更新只切换后缀，违反硬安全下限则取消并重新获取快照。

因此“并发”不意味着执行器随时读到半写地图，也不意味着每次地图更新都全局重规划。

## 6. 风险门、主动观察与 VOI

对候选动作或证据晋升定义：

\[
R = \mathbb E[L_{task}] + \beta U + L_{safety-floor}
\]

其中 `L_task` 来自计划器反事实；`U` 是后验不确定性惩罚；任何硬安全规则失败时风险为
不可接受。学习型 PM3/VOI3 代理输出排序分和估计风险下降：

\[
\widehat{VOI}(a)=g_{offline}(G_b,G_t,B)+x(a)^\top\theta_{online}
\]

但代理无权直接执行。排在前面的候选必须通过 exact verifier（精确验证器）；验证器可以
降级为继续、主动观察、后缀重规划或取消。

## 7. N2 接口与 N3 验收

### 7.1 N2 必须实现

- 可相加、可撤销、可从日志重建的 `HybridStatisticDelta/State/Ledger`；
- RLS `A/b/theta` 与 Dirichlet `alpha`，并预留 `Lambda/xi`；
- quarantine/promote/retract/corrected-revision 合法状态机；
- source-cluster-excluded projection（排除同源簇投影）；
- 不可变地图快照、双图依赖桥、动作后缀风险切换；
- learned proxy + online RLS residual + exact verifier 的权限分离；
- B-BS3 多来源监督标签与硬规则优先级接口。

PCHMP 的神经消息传递、CCRR 的完整阶段后验竞争和真实机器人数据训练不在本轮伪装为已完成；
它们保留为下一轮实装与死亡测试对象。

### 7.2 N3 对抗验收

1. 自然统计量结果与公平 batch ridge（批量岭回归）一致；
2. 任意顺序的合法增量/撤销后，缓存投影与从日志重建一致；
3. 重复证据簇、错修订撤销、跨事件父修订、非法状态转换全部失败；
4. downdate 破坏正定性时明确要求 replay；
5. RLS 残差读取的基础投影确实排除了同源证据簇；
6. 无关地图更新不重规划，硬依赖变化只重规划最早受影响动作及其后缀；
7. 学习型代理即使给危险动作最高分，也不能越过精确风险验证器；
8. 学习型软边不能删除符号/安全硬边；分布外变化可扩展候选而不覆写硬边；
9. 并发更新不会让执行动作观察到半完成统计量；
10. 与 O-STaR/DynaMem/STAR/AMG 等合理增强基线比较时，分别报告推理正确率、错误动作率、
    任务成功率、环境 regret（遗憾）、重规划成本、恢复延迟和计算成本，不以成本单指标替代
    完整创新判断。

## 8. 论文主张门

在上述 N3 通过前，只能写“方案 B 的可审计基础设施已实现”。即使 N3 全部通过，也只能
证明实现正确；只有在公平、独立调参、相同证据与行动预算下产生稳定的行动/效用收益，且
消融能把收益归因到来源绑定可逆统计量、阶段竞争、双图依赖与风险验证机制，才能升级为
结构二的创新证据。任何单个组件被已有工作覆盖时必须明确提醒，但不据此删除完整路线。

## 9. 2026-08-22 N4 执行记录

### N1

本文件已经冻结全部已选 B 系列决策、数学状态、并发语义、RGRC 状态机、风险权限与
论文主张门。第一轮审核和对抗审核的缺口没有被改写成“已完成”。

### N2

已完成的核心实现：

- `src/cpswm/system/continual/hybrid_statistics.py`：来源绑定的混合充分统计量、整簇原子
  晋升、可逆撤销、隔离修订取代、修订谱系、风险证书绑定、留一簇投影、batch-ridge
  等价的 `A/b/theta`、Dirichlet+RLS 融合、`Lambda/xi` 与 replay gate；
- `src/cpswm/world_model/grounded_search/concurrent_map_task.py`：原子地图版本、不可变哈希
  快照、双图依赖、硬规则保护、五源软监督、动作级版本切换、硬安全/反事实风险门、
  learned VOI proxy（学习型 VOI 代理）+ online RLS residual（在线 RLS 残差）+ exact
  verifier（精确验证器）；
- `event_derived_update_ledger.py`：旧标量 RGRC 原型补齐父修订/同事件约束、晋升/撤销
  状态检查、授权绑定和防篡改 JSONL hash chain；
- `rls/habit_head.py`：移除重复 restore，并清理本文件的 lint 问题。

### N3

- 结构二方案 B + RGRC 定向对抗测试：34/34 通过；
- 新增测试覆盖：自然统计量与 batch ridge 等价、整簇原子晋升/排除、隔离修订取代、
  错谱系/错授权/凭证复用拒绝、缓存—日志重放一致、数值回放门、Dirichlet+RLS 融合、
  地图批次原子发布、快照防篡改、相关动作后缀重规划、无关更新继续、硬安全取消、
  多来源依赖监督、学习型 VOI 不能绕过精确验证器；
- 相关改动 `ruff` 全部通过；两个新核心模块 strict `mypy` 通过；
- 排除工作区中正在独立修改的 `tests/test_project_one_shift_action_death_test.py` 后，其余
  624 个测试全部通过。该方向一文件单独复跑时有 3 个 regex 期望文字与当前验证错误文字
  不一致；本轮未修改、未回退、也未把它计入结构二成败。

### 尚未完成，禁止升级主张

- OPCEU 的潜在未观察事件后验期望更新；
- PCHMP 的 provenance-constrained neural message passing（来源约束神经消息传递）与人物
  置换等变实验；
- CF-BOCPD 从共享原始证据识别原因及 BOCPDMS 公平匹配；
- CCRR 的 stay/create/reactivate/unresolved 完整阶段后验竞争；
- ORRER→混合 RGRC→真实习惯模型→地图→任务执行的端到端接线；
- PM3 图模型和 VOI3 exact oracle 的真实离线训练；
- 与 AMG、O-STaR、DynaMem、STAR 及其合理增强版本的独立调参行动/效用死亡测试；
- 真实机器人或真实感知日志的外部有效性。

因此 N4 的准确结论是：**方案 B 的可审计正确性骨架已完成并通过内部对抗测试；结构二
完整算法、强基线优势和论文创新证据仍未完成。**
