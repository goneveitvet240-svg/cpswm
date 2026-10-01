# 当前工程依赖，不是验收证明

本轮修复：CI专门生成当前比较包、重新执行比较与归因验证、生成当前D0科学循环并完整重放、重建可变P0清单并运行清单消费者；只在所有真实命令完成后发布消费路径。读取路径、源文件与产物摘要变化均拒绝。旧科学循环文件继续单独测试为历史过期；三个当前语义对抗模块从全新合法对象开始，不改写其侧车后冒称当前。

仍未闭合：工程checkpoint测试需要当前Task7/8/10实际运行、五个P5当前生成、历史源复算、native命令矩阵实际回执，再生成新的checkpoint，且现有封存输出禁止覆盖。下一版本须显式新路径；不能只刷新旧摘要。现有全链的core_pytest不会自动准备当前比较包，需要传入已验证的材料。

额外阻断：tools/structure_two_unified_acceptance.py validate_runtime_records和JUnit检查拒绝任何skip/xfail；全仓含平台限定macOS sandbox tests、需真实历史/权重的显式artifact tests，以及tests/test_project_one_same_context_rls_ablation.py::test_shipped_wiring_shuffling_costs_real_discrimination的strict xfail。该用例断言现有RLS残差对打乱输入的区分收益超过0.1，而当前实现未达到，属于已知方法行为而非缺少test fixture。不得删除标记/降低阈值/改变先验以伪造工程回执。完整CI退出0与严格工程checkpoint通过须分开记录；用户科学选择与完整结构二范围不变。

本轮先获得完整收集/执行诊断和当前合法输入正路径，保留所有未过项。工程门槛未关闭，不启动后续观测更新事务或行为收益结论。

## 当前合法 P0 后的实际诊断

2026-10-01，功能源码 fd08b59bdc01ca9ffe4e9b159cb1393052711d15，在八阶段真实准备成功后单独执行完整 checkpoint 模块：7 failed、8 passed /9.69 秒，1024 Python 源摘要不变。七项失败都在合法基线验证处遇到旧 command receipt 与当前 P0 不匹配；因此对应攻击的拒绝分支尚未获得当前正路径覆盖，不能把它们描述成已通过安全测试。环境指纹的两个当前实测测试已通过，但这不刷新旧回执的权限。

原生矩阵 `run_structure_two_engineering_audit_receipt.py` 的 `uv_frozen_offline_check` 只声明 dev。相同当前环境运行其原命令退出 1，报告会卸载 33 个 perception/hand-perception 依赖；加入这两个与 CI 一致的 extras 后只读 `--check` 退出 0、检查 88 包且不作修改。该诊断没有卸载/安装包或改变锁文件。它是下一轮明确的工程契约修复项，不是源码已修复或矩阵已通过。

下一轮应同时校准真实依赖声明和新版本回执生命周期：固定新的非覆盖输出路径，显式生成 Task 7/8/10 当前合法输入，传入已验证比较/科学循环材料，实际执行矩阵并生成新 checkpoint；旧封存数据继续作为历史证据。现有严格门槛中的已知方法反例与平台/外部数据缺口保持显式，不靠改成 skip、删除 xfail 或修改科学阈值取得绿色状态。
