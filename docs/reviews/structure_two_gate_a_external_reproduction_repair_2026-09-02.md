# Structure Two Gate A、Gate B 与外部复现独立审核门修复（2026-09-02）

## 阶段结论

本轮关闭的是已知 false-positive authorization（假阳性授权）路径，不是完成外部复现。

当前 `world_arm_adapter_v0_4` 产生的十臂动作已明确降级为 `structure-two-gate-b-proxy-diagnostic@0.8`。它仍可用于 development diagnostic（开发诊断），但 canonical Gate B scorer（规范 Gate B 评分器）、combined authorization（组合授权）和 readiness（就绪度）都会拒绝把它当成 external efficacy（外部效能）证据。

仓库尚未实现由六个 fidelity-validated implementation bundles（通过忠实度验证的实现包）逐 episode 产生 Gate B 动作的统一执行器。因此当前状态必须继续保持：

- `gate_b_fidelity_implementation_executor_registered=false`
- `gate_b_actions_from_fidelity_validated_implementation_verified=false`
- `externally_frozen_manifest_verified=false`
- `gate_a_passed=false`
- `v0_6_gate_b_scored=false`
- `external_fidelity.external_fidelity_gate_passed=false`
- `external_fidelity.isolated_external_execution_environment_verified=false`
- `sealed_confirmatory_gate_b_holdout_verified=false`
- `external_method_efficacy_comparison_allowed=false`
- `lifecycle_state=DEVELOPMENT_EVIDENCE_INCOMPLETE`

## 本轮修复

### 1. Implementation identity split（实现身份分裂）

- proxy action artifact（代理动作产物）现在携带 `action_execution_mode=reduced_proxy_diagnostic`、`external_actions_from_fidelity_validated_implementation=false` 和逐臂实际 producer ID。
- artifact protocol（产物协议）不再叫 canonical execution，而是 `structure-two-gate-b-proxy-diagnostic@0.8`。
- canonical verifier 会先完整验证该诊断产物，然后明确拒绝用于 Gate B 评分。
- combined authorization 新增 `gate_b_actions_from_fidelity_validated_implementation_verified` 必要条件；当前没有真实逐 episode implementation executor，因此该条件只能为 false。
- readiness 将“缺少规范逐 episode 实现执行器”同时列为 design freeze blocker（设计冻结阻断项）和 authorization blocker（授权阻断项）。

这关闭了“六臂哈希 + implementation 标签 + proxy 动作即可授权”的漏洞，但没有虚构尚不存在的真实外部实现执行链。

### 2. External fidelity（外部忠实度）

- test node（测试节点）集合由 method specification（方法规格）固定，不再接受回执中的任意 `::` 字符串。
- test files（测试文件）必须位于独立、内容哈希固定的 verifier-owned test bundle（验证方测试包），不得位于被测 implementation bundle 内。
- 正向证据由 `run_fidelity_tests_and_make_receipt_v0_7()` 实际启动固定、无 shell 的 pytest argv，成功后才生成结构化日志和 Ed25519 回执。
- verifier（验证器）不把签名 JSON 当成执行证明；它会在第三个临时工作目录中再次运行同一冻结 test nodes。解释器以 `-I -S -B` 启动：不处理 `site`、`.pth`、`sitecustomize.py`、`usercustomize.py` 或继承的 Python 路径，并禁止写入 `.pyc`；pytest 先从验证器运行时导入，之后才装入测试所需的可信源码路径。执行还禁用插件自动加载和 `conftest.py`，清空 `PYTEST_ADDOPTS/PYTEST_PLUGINS/PYTHONPATH/PYTHONSTARTUP`，并检查 JUnit test set、失败状态、退出码以及执行前后两个 bundle hash 不变。
- clean subprocess（清洁子进程）仍不等于隔离容器，所以 `isolated_external_execution_environment_verified=false` 会强制正式 fidelity 结果保持 false。
- 当前 canonical six-arm specifications（规范六臂规格）尚未登记真实 fidelity test nodes，因此正式 external fidelity 仍必为 false。非规范 unit fixture（单元夹具）的通过只验证协议机制，不代表任何外部方法通过。

### 3. Public preregistered validation（公开预注册验证集）

Gate A spec 与源码同时固定：

- v0.5 world distribution hash；
- 12 个 validation world seeds；
- 3 个 trajectory seeds；
- 2 个 observation seeds；
- train/prior-validation spent seeds（训练/旧验证已使用种子）互斥集合；
- `window_days=35`、`context_shrinkage_pseudocounts=0.0`、`owner_probability_threshold=0.5`；
- `bootstrap_draws=4000`。

验证器还检查分布字段集合、上下界、概率范围、有限数值、abrupt/recurrence 顺序和 habit probability mass（习惯概率质量）约束。即使攻击者先选择 tiny set（微型集合）、重新计算 commitment（承诺）、再改写 Gate A spec，仍会因偏离 code-pinned public validation set（代码固定的公开验证集）而失败。

这些种子在实现冻结前公开，因此不再称为 sealed/canonical holdout（密封/规范留出集）。Gate A 报告固定携带 `evaluation_set_role=public_preregistered_validation`、`sealed_gate_b_holdout_verified=false` 和 `gate_b_allowed=false`；canonical Gate B 也会独立拒绝该 opening。确认性 Gate B 必须等待外部 custodian 在实现哈希冻结后交付新的密封集合。

### 4. Executor conformance（执行器符合性）

- 固定 pytest argv、六个规范 test nodes、源码清单和 assertion digest（断言摘要）。
- tester/executor 提交的 JUnit、日志与签名仍会被检查，但它们不再是决定性证据。
- verifier 会从当前已哈希源码独立重跑固定测试，并在完成后再次核对源码哈希；独立重跑失败时，即使提交的 JUnit、日志、六个 `passed=true` 和两方签名全部结构完整，conformance 仍失败。
- verifier 重跑使用共同的 `-I -S -B` 隔离启动器、禁用插件自动加载、`--noconftest` 和控制变量白名单。仓库源码不会在 Python 启动阶段进入 `sys.path`；pytest 从解释器运行时导入后，才显式加入已哈希的验证方源码。因此本轮实测的 `src/sitecustomize.py -> PYTEST_ADDOPTS -> 恶意插件` 链没有执行，六个 `assert False` 仍被拒绝。

软件无法仅凭文件判断密钥持有者是否曾手工填写 JUnit；本轮采取的是更强的判定方式：不依赖该声明，验证方自己执行。它不是 hardware attestation（硬件证明）。

上述隔离只关闭 Python/pytest startup hook（启动钩子）注入，并不等于容器、虚拟机或操作系统级沙箱；网络、系统调用和被测实现的进程内恶意行为仍由后续外部隔离执行器负责。因此 `isolated_external_execution_environment_verified` 继续为 false。

### 5. Official checkout root（官方检出根目录）

除 commit、tree、dirty/untracked/submodule 检查外，验证器现在要求传入路径精确等于 `git rev-parse --show-toplevel`。干净仓库的任意嵌套子目录不能再冒充官方 checkout root。

对于要求官方代码的 arm，适配合同中的任意 build command（构建命令）不再足够。命令必须来自冻结 method specification，验证器会复制已核验的 clean checkout、使用清洁环境实际执行固定 argv，并要求重建输出与提交的 implementation bundle hash 完全相同。派生 provenance（来源链）绑定 checkout、commit、命令、环境协议和输出哈希；当前仍因不是隔离容器而不能产生正式 fidelity pass。

### 6. Noncanonical diagnostic（非规范诊断）

- `enforce_canonical_protocol=false` 的 Gate B 使用独立 `...-diagnostic@0.6` 协议；顶层和嵌套正式 `gate_b_passed` 均固定为 false，原始结果只在 `diagnostic_gate_b_passed`/`diagnostic_gate_b` 中出现。
- `enforce_canonical_catalog=false` 的 fidelity 使用独立 `...-diagnostic@0.2` 协议；所有正式 fidelity pass 与组合授权前置条件固定为 false。

## 仍未完成的工作

1. 为六个外部方法建立统一、逐 episode、由冻结 implementation bundle 实际执行的 Gate B action interface（动作接口）。在此之前 Gate B 不得评分。
2. 为 canonical six-arm catalog（规范六臂目录）登记并外部冻结真实 component parity、native protocol 和 adaptation parity 测试；目前正式 fidelity 仍不得通过。
3. 将外部测试执行迁移到真正的隔离 executor/container（执行器/容器）。当前是固定 argv、timeout 和独立重跑，不是网络、系统调用和资源完全隔离的沙箱。
4. 外部 ledger（账本）时序仍是 enrollment authority attestation（登记权威声明），代码没有查询独立账本。
5. 路径型输入仍有残余 TOCTOU（检查与使用时差）；正式运行应改为一次性摄取的 content-addressed objects（内容寻址对象）。

因此准确表述是：本轮把新增审核发现转化为可执行的失败关闭边界，并补上 verifier-owned tests（验证方测试）、清洁 subprocess、可重建 build provenance、公开验证集降级和 diagnostic protocol 分离；协议仍未冻结、Gate B 未评分、外部忠实度未通过、效能比较未授权。

## 本轮验证结果

- 完整目标回归：`108 passed`。
- 第一轮 startup-hook（启动钩子）定向攻击：`4 passed`，覆盖 conformance/fidelity 的 `sitecustomize.py`、继承 `PYTHONPATH/PYTHONSTARTUP` 和 bundle `conftest.py`。
- 第二轮 forged-complete/trust-chain/state-machine（伪完整证据/信任链/状态机）攻击：`12 passed`。
- 本轮变更 Python 文件：Ruff 通过。
- 本轮 3 个直接相关源码文件：strict mypy（`follow-imports=silent`）通过；未把仓库其他历史 mypy 问题计作本轮通过。
