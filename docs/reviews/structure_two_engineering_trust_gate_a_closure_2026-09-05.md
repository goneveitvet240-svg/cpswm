# 结构二工程可信门 A 收口

日期：2026-09-05
结论：`PASS_WITH_STRICT_SCOPE`
冻结语义：只有 checkpoint 明列的 Task 7 v0.3、Task 8 v0.3、Task 10 G1/G2 v0.1 工件可称为“可复算 D0 证据”；该称谓不外推到七算子正式授权、外部确认、效能解释或方法优越性。

## 三个 P0 缺陷

1. **伪造但完整的正向路径可穿透旧验证器。** 旧 D0 envelope/checkpoint 只验证自一致哈希，攻击者可同时修改阳性字段并重算所有无密钥哈希。旧 checkpoint 已显式撤销；Task 7/8/10 新工件为每个正向布尔叶子保存显式 `positive_output_trust_chain`，验证器从冻结配置与实现做任务专用 fresh recomputation（新鲜复算），最终 checkpoint 也拒绝完整重哈希后的授权伪造。
2. **授权契约与实现/配置/托管链漂移。** 七算子授权原先没有完整绑定配置、协议、独立角色和签名。v1.0 授权现在绑定 config/spec commitment（配置/规范承诺）及 custody anchors/signatures（托管锚点/签名）；任何 Task 7/8/10 工程结果仍不得自行铸造正式授权。
3. **全局 manifest/source-bundle 与任务文档、结果工件漂移。** 在 B、D 停止写入后，readiness、旧 checkpoint 撤销记录、v0.5 当前树兼容审计、P0 manifest 和最终工程 checkpoint 已按依赖顺序重算；Task 7/8/10、当前证据总表和各结果报告已对齐到同一版本与声明边界。

额外发现并封堵一条生成绕过：`--no-fresh-recomputation` 只能用于验证已有 checkpoint，不能用于生成新 checkpoint。

## 正向输出 trust chain

- Task 7 v0.3：66 个正向路径；总门 `FAIL`，仅 strict window complexity（严格窗口复杂度）子门通过。
- Task 8 v0.3：341 个正向路径；任务专用 belief/action/utility（信念/行动/效用）合取为 `PASS`，但无正式独立托管授权。
- Task 10 G1 v0.1：41 个正向路径；定义与确定性复算完成，formal authorization（正式授权）为 false。
- Task 10 G2 v0.1：9 个正向路径；定义与确定性复算完成，formal authorization 为 false。
- 工程 checkpoint：18 个正向路径；逐项绑定当前 P0 manifest、当前 source inventory（来源清单）、任务工件路径映射、新鲜复算与报告。

## 两轮对抗自查

第一轮聚焦正向伪造、完整重哈希、任务替换、配置漂移、陈旧工件与 checkpoint 降级生成：`47/47 passed`。

第二轮跨 Gate A/B、外部来源获取、适配器 fidelity（保真度）、隔离、密封承诺、托管、状态机和 Task 9/七算子授权：`381 collected = 380 passed + 1 skipped`。唯一 skip 是嵌套 macOS sandbox；D 收口已记录同一宿主隔离探针在真实宿主权限下单跑通过。

最终文件树全量回归：`3291 collected = 3289 passed + 1 xfailed + 1 skipped`，无失败。

- Ruff lint：通过。
- Ruff format：560 个 Python 文件通过。
- strict mypy：本轮新增/修改的 32 个生产模块与生成器通过（`--follow-imports=silent`，避免把 19 个未触碰历史文件的 66 个既存错误混入本门）；仓库全局历史类型债务没有被声称为清零。
- `git diff --check`：通过。

## 冻结 checkpoint

- checkpoint content SHA-256：`00817000048e1126eaeabee38b460bfad3c609ed97d980f2cc490f2ca997ed6f`
- checkpoint file SHA-256：`462d24679739e60527fb3629699d8ad53ad03a6db965d1d87a9fab8e22bf001d`
- P0 manifest semantic SHA-256：`76642184bf8087645ffd39472da10cc7153a8e28abff7c1bb577bbae54503a2e`
- P0 manifest file SHA-256：`67a03f1133c0f5995f1c7048b9f923933fc7ba0be793357470020ca6e1bd5b7c`

## 不可越界的当前事实

- 六邻居仍是 `6 component cores / 0 native reproductions`。
- Gate A：`BLOCKED_BEFORE_EXECUTION`。
- current comparator-typed Gate B v0.8：`FROZEN_NOT_EXECUTED/NOT_RUN`。
- combined：`BLOCKED_FAIL_CLOSED`。
- efficacy interpretation（效能解释）：`FORBIDDEN`。
- 七算子正式消融：未授权、未运行。
- 历史 v0.5 工件虽可验证当前声明的内部签名链，但缺少冻结的 245 行 inventory 与外部不可变锚点，不能声称历史真实性或独立托管。

因此，A 门通过只建立上述四个任务工件的工程可复算性，不改变 D 外部确认门的失败闭合结论，也不构成论文级效能证据。
