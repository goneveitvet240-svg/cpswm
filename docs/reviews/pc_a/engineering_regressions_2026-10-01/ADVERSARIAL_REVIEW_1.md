# 第一轮修复审查

源码 8f7edafd51cdf735ca9c65a7c8e4ac367cebdc68，1021 Python 文件摘要核验不变。本轮为实现者顺序自审，不是独立 B 审查，也不是全仓验收。

范围：类型补全是否绕过运行时边界；源码指纹是否丢字段；完整 raw 因子伪造、模型绑定、父链、owner 描述和无副作用合法重试。

- 冻结后严格 mypy src：389 文件，0 错误；原严格配置不变，没有新增 ignore。
- 最终 Ruff src/tests 与格式检查通过；完整 pytest 收集仍为 6738 项，没有删减收集。
- review1.log / review1.json：283 passed，96.78 秒，source_unchanged=true。覆盖实例亲和/对照、软表面位置、位置模型、Native 位置生产、完整原件伪造、owner 描述。
- 审阅生产 cast 均位于既有 schema/运行时检查之后，marshal code payload 保留完整字段。未修改粒子数值算法、观测似然公式、研究先验、阈值或测试跳过规则。

本范围通过。其余 27 项既有 CI 失败尚未修复；65 分钟超时留下未执行用例。不能把 283 通过解释成整体通过；未新增后续观测事务。下一轮独立时序自审关注有限 log 支持的继续/恢复/撤回及异地 cwd 和污染 PYTHONPATH 子进程。
