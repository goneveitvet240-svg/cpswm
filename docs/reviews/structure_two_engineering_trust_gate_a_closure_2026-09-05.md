# 结构二工程可信门 A 收口

日期：2026-09-05
结论：`PASS_WITH_STRICT_SCOPE`

冻结语义：只有 checkpoint 明列的 Task 7 v0.4、Task 8 v0.4、Task 10 G1/G2 v0.1
工件可称为“可复算 D0 证据”。该称谓不外推到科学通过、七算子正式授权、外部确认、效能解释
或方法优越性。

## P0 修复

要求中的三个工程 P0 已关闭：

1. **伪造但完整的正向路径可穿透旧验证器。** 旧 D0 envelope/checkpoint 只验证自一致哈希，攻击者
   可同时修改阳性字段并重算无密钥哈希。旧 checkpoint 已显式撤销；Task 7/8/10 新工件为每个
   正向布尔叶子保存 `positive_output_trust_chain`，验证器从冻结配置与实现做 fresh
   recomputation（新鲜复算），最终 checkpoint 也拒绝完整重哈希后的授权伪造。
2. **授权契约与实现/配置/托管链漂移。** 唯一七算子授权 DAG 现在绑定 config/spec
   commitment（配置/规范承诺）、正式 policy/root signature（策略/根签名）与 custody
   anchors/signatures（托管锚点/签名）；Task 7/8/10 工程结果不能自行铸造授权。
3. **全局 manifest/source-bundle 与任务文档、结果工件漂移。** 在 B、D 停止写入后，Task 10、
   readiness、旧 checkpoint 撤销记录、v0.5 当前树兼容审计、P0 manifest 和最终工程 checkpoint
   已按依赖顺序重算；Task 7/8/10、证据总表和结果报告已对齐到当前版本。

B 的两轮对抗审计又发现并关闭四个 P0：formal runtime engine/trace digest 未冻结、registry
clone/identity replacement、final authorization 未绑定 frozen policy/root signature、
caller-backdated freshness。另封堵 `--no-fresh-recomputation` 生成绕过：该选项只能验证已有
checkpoint，不能生成新 checkpoint。

## 正向输出 trust chain

- Task 7 v0.4：282 个正向路径；科学门 `FAIL`。
- Task 8 v0.4：6 个正向路径；matched three-arm confirmatory 科学门 `FAIL`。
- Task 10 G1 v0.1：41 个正向路径；定义与确定性复算完成，formal authorization 为 false。
- Task 10 G2 v0.1：9 个正向路径；定义与确定性复算完成，formal authorization 为 false。
- 工程 checkpoint：20 个正向路径；绑定当前 P0 manifest、source inventory、任务路径映射、
  新鲜复算与当前报告。

## 两轮最终态对抗自查

- 第一轮，v0.4 科学门、raw formal chain、registry identity replay 与唯一授权 DAG：
  `275/275 passed`。
- 第二轮，checkpoint 伪造、manifest/source drift、外部链、隔离、sealed receipt 与状态机组合：
  `417 collected = 416 passed + 1 skipped`。唯一 skip 是嵌套 macOS sandbox；D 收口已记录同一
  宿主隔离探针在真实宿主权限下单跑通过。

最终文件树全量回归：`3346 collected = 3344 passed + 1 xfailed + 1 skipped`，无失败。

- Ruff lint：通过。
- Ruff format：565 个 Python 文件通过。
- strict mypy：A 初次冻结改动 32 个文件通过；B v0.4 最终 delta 13 个文件通过，均使用
  `--follow-imports=silent` 隔离未触碰历史文件。仓库 `mypy src` 的 19 个旧文件、66 个既存错误
  没有被声称为清零。
- `git diff --check`：通过。

## 冻结 checkpoint

- checkpoint content SHA-256：`b0b8d20921ce425bbadba03cbcc76d73563a9091ef285f9eca8ee04e149a6032`
- checkpoint file SHA-256：`dd34a8771b634336384c2463d71c00f17bca48cfa7057ff9705e81fa6e721741`
- P0 manifest semantic SHA-256：`06e1b67bc76ed3701430ab0ad5c1f58ae37ad3f177f28867d725b9780b52fd0d`
- P0 manifest file SHA-256：`f5344af4086f79f1acc5984e949082f0646cc11a55adc31dbc6ccfdf5aeabd2e`
- current v0.5 inventory：`279 files / 603ceca3e4e836b4f1b7f062763d69db51d8675d773d66d87f7dc85c6fc6b066`

## 不可越界的当前事实

- Task 7 v0.4 `FAIL`：belief TV mean/worst `0.244625/0.750140`；action TV
  `0.112464/0.398628`；contamination `+0.00291836`。
- Task 8 v0.4 `FAIL`：paired mean `-0.000858330`；one-sided 95% lower
  `-0.002058701`，未超过 `+0.001`。
- 六邻居仍是 `6 component cores / 0 native reproductions`。
- Gate A：`BLOCKED_BEFORE_EXECUTION`。
- current comparator-typed Gate B v0.8：`FROZEN_NOT_EXECUTED/NOT_RUN`。
- raw formal execution chain：`REGISTERED_NOT_EXECUTED/NOT_ENROLLED`。
- combined：`BLOCKED_FAIL_CLOSED`；efficacy interpretation：`FORBIDDEN`。
- 七算子正式消融：未授权、未运行；五项 binding 仍未形成已登记的正式回执链。
- 历史 v0.5 缺少冻结的 245 行 inventory 与外部不可变锚点，不能声称历史真实性或独立托管。

因此，A 门通过只建立上述四个任务工件的工程可复算性，不改变 B 的科学失败或 D 外部确认门的
失败闭合结论，也不构成论文级效能证据。
