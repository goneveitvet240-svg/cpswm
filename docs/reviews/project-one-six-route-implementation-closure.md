# 项目一六路线实现闭环记录

状态：`implemented_pending_full_pytest_environment`

本记录只声明代码结构已经接通，不声明真实家庭部署有效、论文新颖性成立或完整实验已经验收。

## 已覆盖结构

1. `HierarchicalDirichletHabitModel` 保留默认基线行为，并新增：
   - observation opportunity（观测机会）与 propensity correction（倾向校正）的强来源绑定；
   - resident actor registry（常住行为者注册表）和 non-resident quarantine（非住户隔离计数）；
   - shrinkage actor residual（收缩行为者残差）及分量概率解释；
   - 每次更新的 applied weight、resident mass、isolated mass 和 clipping audit。
2. `CauseFactorizedBOCPD` 为 observation、actor、habit、noise 分别维护 run-length posterior，允许多原因同时变化；在线 held-out suite 增加 noise-only family。
3. CHEH 修订持久化 actor evidence 的 endpoint detection ID 与 endpoint role；最终责任者修订只接受 destination endpoint evidence。
4. `ActionUtilityPlanner` 计算 expected value of sample information（样本信息期望价值），扣除 motion/time/interruption/privacy/safety cost；`DirectionThreePipeline` 默认使用效用目标，`InformationGainPlanner` 保留为消融基线。
5. M20-M22 查询契约新增机器可检查的 evidence DAG、claim-to-node binding 和 baseline closure gate；基线门未全部通过时禁止返回审计证据路径。
6. 公平消融契约强制相同 observation/model/tuning budget、相同 observation trace、相同冻结测试集和不同 tuning run；联合报告 ECE、Brier、NLL、行动成功、效用、时间、打扰和真实环境 regret。

## 项目一强制消融臂

- `habit-baseline`
- `habit-observation-corrected`
- `habit-visitor-isolated`
- `habit-actor-residual`
- `ordinary-bocpd`
- `cause-factorized-bocpd`
- `cheh-internal-consistency`
- `cheh-source-aligned`
- `retuned-threshold-verification`
- `decision-utility-verification`

每个实验臂必须独立调参。不得用新方法的验证集最优参数对比旧方法默认参数，也不得把 ECE/Brier/NLL 单独作为 go/no-go 依据。

## 尚未解除的验收门

- 当前机器的默认 Python 缺少 `pydantic`；工作区 Python 有项目依赖但缺少 `pytest`，因此完整 pytest suite 尚未运行。
- 已完成变更模块导入、36-case 在线 suite 生成、oracle 在线评估以及核心闭环手工断言。
- M20-M22 证据路径结构已实现但未激活；只有真实 baseline closure evidence 全部通过后才能进入启用状态。
- 真实家庭外部有效性、用户干扰成本估计及新颖性检索不在本次代码闭环的已验收声明中。
