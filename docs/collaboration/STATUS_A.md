# A 目录整理（2026-10-27，本地完成，待推送）

- 任务：将本地数据/权重/输出集中到 data，将 π0.5、SAM2、LIBERO 入口集中到 integrations。
- 分支：`codex/pc-a-directory-layout-20261027`。
- base/共享集成 SHA：`19ddf26830348a2f0b33f0af54d6ba702c5cfb1c`。
- 本机主目录源码 SHA：`09eb4d48e1c11082e90ca18332d04333e6b5b47a`。
- π0.5 接入源码 SHA：`3e1662542fe3299248eb1f1a25dc37416fe56bc2`。
- 文件边界：新目录导航/忽略规则、整理证据和本人状态；本机仅移动未跟踪资源并建立兼容链接。
- 已核验远端并读取交接和 π0.5 报告；工作树/已提交数据/历史证据原位保留。
- 测试与证据：6 项同卷迁移，所有条目的 inode/大小/mtime/链接状态一致；旧启动器运行 `tests/test_libero_stack.py`：16 passed in 4.74s，exit 0；37 个导航链接验证通过。
- 证据：[迁移与检查记录](directory-layout-20261027.json)，[目录导航](../../DIRECTORY_LAYOUT.md)。
- 局限：迁移以同卷 rename 保留文件，并核对 inode/大小/mtime/链接；未逐字节重算全部内容哈希。原输出已有 14 个失效的历史链接，迁移未新增。未重新运行模型推理或科研验收。
- 下一步：推送独立分支，通过 PR 交接目录约定；共享集成不自动合并。

---

# 电脑 A 当前状态

2026-09-13：执行用户授权的 GitHub 分类、文档归并和导航整理。

- 整理分支：`codex/pc-a-github-organization-20260913`；base `bdec3ee21b7db361e390496d97ff2eb30390dc6c`。
- 本次只合入 #1/#6 文档审查历史与导航；非 docs 代码/测试/配置保持 base 字节。不继承或宣布统一验收通过。
- 当前统一候选：[#15](https://github.com/goneveitvet240-svg/cpswm/pull/15)，完整代码和审查状态见其 PR。
- 最新 A 位姿开发：[#16](https://github.com/goneveitvet240-svg/cpswm/pull/16)，[该分支 STATUS_A](https://github.com/goneveitvet240-svg/cpswm/blob/codex/pc-a-pose-local-dev-20260913/docs/collaboration/STATUS_A.md)。
- 最新 B 交接：[#17](https://github.com/goneveitvet240-svg/cpswm/pull/17)，已推送但尚未由 A 独立复跑。
- 检查：纯文档路径核对、历史证据 Git blob 对照、PR 祖先关系/21 文件同一性、Markdown 本地链接核对；本轮没有运行生产测试。
- 阻塞与下一步：#15–#17 CI/独立验收、#2 W2 重算。具体分工见 TASK_BOARD。

旧状态原文：[初始化](history/2026-09-13-organization/integration_STATUS_A.md)、[第六轮](history/2026-09-13-organization/round6_STATUS_A.md)、[B 五项交叉复核](history/2026-09-13-organization/crosscheck_STATUS_A.md)。
