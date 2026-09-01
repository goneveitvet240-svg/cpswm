# 正式数据接入前修复与两轮对抗审核（2026-08-27）

结论：开发态契约、fixture（样例）和回放纵向链可以跑通；四条路线均未达到真实数据或真实具身
系统验证完成。`pre_data_integration_complete`、方法有效性和论文结论继续 `BLOCK`。

## 修复闭环

- 修复结构一 selected stack（选定栈）错误导入 `EvidenceRef`，并补齐 M21 constrained compiler
  （受约束编译器）的强制 invocation provenance（调用来源）。
- 修正 RLS 极端异常测试的虚假判据：FULL 与 NO_RLS 的最终 change probability 都会饱和到
  `1.0`，可识别差异是饱和前 habit signal；未改超参数伪造成方法增益。
- 为搜索反馈 opportunity、oracle 落地点、AMG before observation、回放 lineage、canonical
  数值载荷等边界增加 fail-closed（失败即关闭）检查。
- 保持 Mypy strict（严格类型），启用 Pydantic 插件并清零 201 个 source files 的全部类型错误；
  Ruff lint 和 format 同步清零。
- 结构一路线账本改为 9 个 `implemented_vertical_slice`、3 个 `contract_only`、0 个
  `integrated/validated`；未实现项没有通过改名升级。

## 两轮对抗证据

第一轮是定向负向攻击：118 passed，1.74 秒。覆盖硬 actor truth（行为者真值）泄漏、跨 split
污染、缓存/内容篡改、伪造 replay、重复反馈、陈旧 lineage、未知/拒答、外部复现不完整和
checkpoint 以外的 fail-closed 门。

第二轮按 CI 的 `pytest -n auto --dist=loadscope --cov=src` 执行，最终 2479 passed、1 xfailed，
coverage 89%，耗时 35:59。功能门通过，但旧 22 分钟预算被实测证伪；CI 已修正为 45 分钟执行
预算和 50 分钟 job 预算，没有删除慢测。最终 checkpoint 在本文件落盘后单独生成和验签。

## 四条路线的诚实完成度

| 路线 | 当前能跑通 | 仍然阻断真实接入/论文结论 |
|---|---|---|
| 结构一 | 统一 ingress、显式降级回执、选定身份/查询/策略适配器及 9 个纵切 | 3 个 contract-only 路线；无原生完整 posterior 方法臂；无真实传感器、长期家庭流和整体 WS validation |
| 结构二 | D0 replay、Combination A、CHEH/PCHMP/ORRER/Project One feedback/action 链和 artifact verifier | D1/D2 真实数据、外部强基线、独立重调参、action/utility 与 external-validity 门仍未通过 |
| 结构三 | oracle/controlled-noise、FindingDory metadata/layered ingress、prediction cache 和 execution-feedback replay | 官方真实 rows/video prediction 尚未接入；VIO/VLM/触觉/规划器/机器人硬件未验证 |
| OAM-PHM | WP0 内部 floor baselines、双头评分、预算/identity/truth 隔离契约可执行 | O-STaR/STREAK 等外部忠实复现和独立调参未完成；当前 external manifest 按设计 fail closed |

因此，“能跑通”只指仓库内的契约、样例和离线回放，不指真实数据闭环、部署可用或研究创新已证实。
