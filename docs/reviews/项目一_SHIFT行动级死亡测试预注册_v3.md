# 项目一 SHIFT 行动级死亡测试预注册 v3

冻结日期：2026-08-22

v3 保留 v2 的全部 P0/P1 修复：双轨公平搜索、每轨四项精确 power topology、pilot artifact 方差重算绑定、TEST 前功效门和逐案例可重算产物。

## v3 行动状态修正

v2 对 false consolidation 计入污染成本，却把真实 habit shift 的 reset 当作已经恢复，即使随后没有 consolidation。这会使 validation 策略偏向抬高 consolidation threshold。

v3 冻结以下顺序状态：

- `RESET_OLD_REGIME → CONSOLIDATE_NEW_REGIME`：完成新 regime 恢复；
- `RESET_OLD_REGIME → VERIFY_NEW_REGIME`：仍未恢复，直到 horizon 结束持续承担 unrecovered-habit regret；
- 真实 habit 未 consolidation 记录 `missed_consolidation=true`；
- `task_success_proxy` 同时要求不漏 reset、不漏 consolidation、无 false reset/consolidation。

成本数值不变；变化只是 recovery time 与既有 `missed_reset_daily_cost` 绑定到“完成 consolidation 才恢复”的状态语义，不新增事后成本权重。

## 双轨、公平预算和功效

- shared-policy：每臂 18 detector candidates；
- independently-retuned-policy：每臂相同的 18 detector × 117 calibration/policy candidates，共 2106；
- primary：downstream action regret，MDE 0.05；
- key secondary：corrupted habit mass，MDE 0.02；
- 每轨固定 joint−ordinary 与 joint−legacy 的两终点，共四项；两轨八项。

v3 pilot-only required n：shared 为 14、151、7、141；retuned 为 6、145、14、130。全局冻结 n=151。

最终 TEST 使用从未运行的 151 个奇数 seeds：11101–11401。跨轨判决规则与 v2 相同；只有 shared 和 independently-retuned 两轨都显示 legacy 相对 joint 的 regret 区间下界至少为 +0.05，才能判 `REBUILD_JOINT`。

所有 task success 和 habit pollution 仍是 synthetic proxy，不得外推为真实具身任务或实体模型参数损失。
