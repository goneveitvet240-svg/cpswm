# 结构一 / 结构二核心原型主干

本原型用于尽快回答一个问题：现有项目的核心思想能否形成一条可运行的数据链，而不是
继续等待 M01-M32 的正式成熟度门全部完成。

```text
ObservationOpportunityRecord
  -> IPW observation correction
  -> CHEH/ORRER hidden-event hypotheses
  -> PCHMP actor/event posterior
  -> CF-BOCPD candidate + CCRR confirmation
  -> person-conditioned Dirichlet habit baseline
  -> regime-local RLS scores
  -> Hybrid RGRC reversible sufficient statistics
  -> versioned belief-map snapshot
  -> suggested search / put-back location
```

## 当前已经接入

- 选择性观察倾向校正；
- 多人物、unknown actor 和隐藏事件多假设；
- 人物条件化习惯更新与非住户隔离；
- 显式阶段切换和旧阶段 RLS 模型复用；
- 自动区分持续习惯变化、短期扰动与证据不足；
- 来源绑定的可逆充分统计量；
- 原子信念地图版本；
- 可直接供搜索或放回策略消费的位置建议。

## 原型阶段明确延后

- M05-M12 真实感知、SLAM、实例关联和人物识别；
- M13-M16 的生产存储、完整联合信念服务；
- 生产级执行反馈解释、完整 actor responsibility 与 ORRER outbox；
- M20-M27 完整语言、规划、导航和操作服务；
- 授权签名、持久防重放、红队门和正式成熟度升级。

这些能力只是延后，不从结构一或结构二范围中删除。原型运行成功也不得改写正式进度账本
或声称 B1、真实数据、具身验证及论文创新门已经通过。

## 运行

```bash
PYTHONPATH=src .venv/bin/python apps/prototype_spine/run_core_demo.py
```
