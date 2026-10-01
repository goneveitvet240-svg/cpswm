# 原生审计依赖声明修复

功能源码 `488c7a62e5562e340b61bbe735c1c2bad858933e`，base `c8f1d29b90b60ef4ddc5303628c87def428d1d1b`，独立分支 `codex/pc-a-audit-environment-20261001`。源改动仅应用与现有契约测试各增加四行，将原生审计的 frozen/offline/check 依赖补齐为 dev、perception、hand-perception，与完整 CI 安装契约一致。锁文件、科学阈值、回执权限和全部测试选择未改。

按当前 uv.lock 在独立工作树离线同步实体环境，共88包。旧 dev-only 只读检查实际退出1并建议移除33包；修复命令实际退出0且无需修改环境。两轮在同一功能 SHA 上顺序完成，均为实现者A自审，非独立B或全仓验收。

第一轮：现有命令契约测试1 passed /2.47s，两份修改文件lint/format通过；调用生产 `_execute_audit_command` 执行完整依赖命令接受，旧dev-only命令拒绝。源摘要及distribution metadata均保持。

第二轮：再次接受完整环境后，临时隔离本工作树 transformers 的distribution metadata；真实 frozen/offline/check 退出1，报告缺少必需包且没有安装；finally恢复原目录，真实检查再次退出0。全部源字节和distribution metadata恢复前后相同。原件、命令、可执行文件身份、时间、退出码见evidence。此用例证明依赖契约仍拒绝缺包，不证明包内容完整性、独立执行认证或完整工程回执。

当前输入准备分支 fd08b59 的完整回归继续在另一工作目录运行，不借用其结果为本修复版本颁发全仓通过。历史checkpoint仍过期；当前合法回执生成、新观测原子更新事务、自然身份/长期记忆/行动收益和B独立验收均未完成。完整研究范围及原分类/主动澄清对照保留。

复现：在本分支独立工作树运行 uv sync --frozen --extra dev --extra perception --extra hand-perception；然后执行现有 test_audit_matrix_contains_frozen_offline_uv_environment_check 及生产声明的只读命令。evidence/reproduce_probe.py 是本机诊断脚本，复用前修改其root/output为新的独立开发环境；第二轮会临时移动该环境的transformers metadata并在finally中恢复，不能针对共享运行环境执行。
