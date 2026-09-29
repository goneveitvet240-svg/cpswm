# 复现

检出实际源码21619f014b43c724b28a93fa4612e03e5a10e2c7，按冻结uv.lock在本机创建实体.venv：

```sh
uv sync --frozen --extra dev --extra perception --extra hand-perception --python 3.13.5
```

证据包run_reviews.py顺序执行两轮，逐项核验已提交Python、依赖与CI工作流前后不变；命令和JUnit在attempt02。第一轮3个测试函数合计7案例，第二轮2个测试函数包含跨目录完整历史重放及9类完整伪造。运行历史审查需要完整Git历史。不能仅解压文件后把缺Git失败误判为算法失败。

history_checkout_probe.py在独立本地浅克隆固定HEAD，保留12份材料；补全历史前后通过真实historical_entries/verify_historical_record比较，并实际修改/重签一份完整JSON后确认拒绝、恢复字节。脚本中的可信本机路径按部署修改，不修改证据或验证器。此为本机因果对照，不是B独立验收或历史首次执行真实性证明。

证据封存时读取每个tar成员并复核原始长度与SHA256，inventory和archive单列。完整CI结果另行记录，局部双审不代表当前完整集合已通过。
