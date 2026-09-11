# 故意伪造的开发测试输入

`r1_current_source/` 是已被真实独立 CLI 拒绝的输入的逐字节副本：全部 `_committed_events` 改为 999，步骤 SHA 和 attribution 同步重算，且源绑定来自当前修复源码。它不是有效诊断结果。

在本独立代码树运行 `apps/evaluation_runner/summarize_structure_two_comparison_audit.py --bundle 此目录/r1_current_source --verify` 会进行完整新鲜重放并拒绝；`--check-file-consistency` 只可能报告文件自洽。真实拒绝结果与原命令见上级 `evidence/adversarial_matrix.json`、`version_and_execution.json`。源码整合变化后会先按来源漂移拒绝；重新构造当前来源攻击应使用测试 helper，不能修改有效历史 bundle。
