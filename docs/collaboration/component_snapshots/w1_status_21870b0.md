# 电脑 A 状态：A2 / W1 R6 缓存执行身份修复

- 窗口状态：本轮限定修复与回归完成；统一验收 **WAITING_UNIFIED_SOURCE**；科学门 **NOT_PASSED**；未签发消融授权。
- 分支：`codex/pc-a-w1-cache-runtime-r6-20260912`。
- 审核源码基线：`b6202bec015679461b06056571bd47a5446045b8`；审核报告提交：`97e1d2c1e83a4532e2b3bab3bf87cc6a2927f274`。
- 最终被测代码：`6fcff45c71eff3f3457d0b6eac6cd872102db89d`。后续文档/证据提交不回写测试时来源清单。
- 旧窗口：`e93ea35187e25a4a3ede70f05cf64a2e35216623` 保持原样、未合并。
- 修改范围：两个编排/运行时工具、工程回执测试启动合同及两个测试文件；七算子、比较算法、科学配置不变。
- 修复：真实 controller/xdist worker 的本地代码执行与冻结源码比较；支持 pytest 断言重写和合法缓存，拒绝 timestamp、unchecked-hash、重写旧缓存；同份核验字节生成代码预期；嵌套 P0/core 使用同一实际运行时检查。
- 最终回归：原 65 + 新 20 + 受影响合同 1 = **86 passed**，原命令 101.14 秒、正式引擎包装 72.67 秒，均退出 0；原生保护 **115 passed**（4272.18 秒），退出 0，来源前后相同；真实五阶段比较链 **五阶段退出 0，消费者 77 passed**（2410.50 秒），包内容/集合与源码前后冻结一致。
- 比较链仅为隔离组装：W2 `de2c04c3e690dba674850af9c4f7e126dbab910e` 加本轮两个 W1 工具，fixture `07fc56983ae93d2d3abd63736abd78201b9c34fa`。不指定为正式统一源码。
- 证据报告：`docs/reviews/pc_a/w1_cache_repair_2026-09-12/REPORT.md`。精确命令、退出码、失败原件、helper 字节、缓存/镜像归档和来源环境清单见同目录及 `docs/reviews/data/structure_two_unified_acceptance_runs/r6_execution_records/`。
- PR：https://github.com/goneveitvet240-svg/cpswm/pull/3；base 为审核 W1 快照，等待审查者决定整合，不自动合并。
- 边界：信任解释器、标准库、安装工具链和进程/OS 完整性；不是独立执行认证。嵌套入口用最小真实正负负载验证，未声称本轮完成全局核心工程审计或新 checkpoint。
- 整合后必跑：固定统一源码 → 比较/归因与全消费者矩阵 → W1/W3 完整矩阵与五类当前结果、历史重放及跨目录核验 → P0 → 真实完整工程矩阵回执 → 强制 fresh checkpoint 生成及 fresh 验证。不得拼接各分支通过结果。
