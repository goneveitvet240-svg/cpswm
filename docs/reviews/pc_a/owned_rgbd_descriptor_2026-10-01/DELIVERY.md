# 当前拥有者 RGB-D 描述交付

分支 `codex/pc-a-owned-rgbd-descriptor-20261001`，冻结功能/顺序两审源码 `6faa17e178ad001de6b5c0e1094f9e62568d7a7e`，903 Python 文件。父功能82c7a81fba0c3af3688978ce222b1b94e4cc5bd9，父交付dc57a687f6cfe0912de7415357765fff79f2c2ff，合入父文档a8d957bb2a9c4796446976f3a2c60723ed906c9c。仅新增owned_position_delivery.py及其测试；文档交付head不替代功能SHA。

- ADVERSARIAL_REVIEW_1.md: 82项通过（6新增+73兼容+2独立+1 profiler），完整派生替换/合法恢复/有限log零显示支持/旧新action与P5后果；一致owner子图改写为信任边界；SHA256 `99389e2ead8124a092d26e04784d6f1213160abbf7253a250736f0761797d91c`
- ADVERSARIAL_REVIEW_2.md: 4项独立核心测试通过，另1项harness诊断通过；完整跨capture替换/90位Decimal父log支持/fresh及P5、SQL、DB后果；保留失败及一致owner子图信任边界；SHA256 `3941ebf8a1e9ab1b0b0aa182ee4225156492e09ec31d3f8450c67900b592d9d5`

作者6项、正式两审按各报告实际范围；A辅助审查不等于B独立或全仓CI。相机正路径由实际prepare/execute/accept调用受控fixture，真实SQLite新进程恢复，不是新Unity采集。原source、父支持、typed完整描述与读出后果均有原日志；不混算参数改动次数与pytest项数。首轮开发失败保留，后续通过不擦除。

接口通过action UUID重建当前owner实际记录的RGB-D/位姿和Native来源描述。调用者派生描述必须逐类型逐字段匹配重新构造结果；语义/代际变化及不支持的camera-feedback prior明确拒绝。posterior_updated和consumption_authority均False。完整owner的capture delivery/raw/receipt子图一致替换没有独立历史锚，此接口不认证其历史；不能以自签描述替代未来消费协议。旧q/raw位置证据验证可重算，profiles分别记录恢复、首次、重复窗口；没有对新capture A位置读出/发布或物理动作。

原始证据244成员（244常规文件，0保留测试symlink），211966285原始bytes，压缩42835377bytes，完整SHA256 `d9e925c3ac86042e8bb724709540a5448b76bea53f57897aac0f8faa976aeb98`。全部成员读回及原件不变检查通过；缓存和pytest别名在archive.json逐条列出，其真实文件及失败、数据库、日志保留。

- `owned-rgbd-descriptor.tar.gz`: 42835377 bytes, SHA256 `d9e925c3ac86042e8bb724709540a5448b76bea53f57897aac0f8faa976aeb98`

按archive.json顺序拼接二进制分片，校验完整SHA后解压；inventory逐成员列类型/大小/摘要。对符号链接保留文本，不盲目解引用。运行环境见runtime-environment.json；测试原argv、前后源码映射、日志分别在R1/R2。使用对应冻结源码与记录环境运行受控测试，不执行归档中不受信任的任意argv。原数据库副本受Python/runtime/配置/模型约束，本轮未解决Windows迁移，不承诺直接搬移复现。

[实现结果](REPORT.md)，[R1](ADVERSARIAL_REVIEW_1.md)，[R2](ADVERSARIAL_REVIEW_2.md)。父真实数据和结果：[PR79](https://github.com/goneveitvet240-svg/cpswm/pull/79)。本轮草稿PR叠加PR79，不合并共享分支，不修改用户原checkout/STATUS_B。

下一完整主项仍为同语义S后的新capture A真正更新Native：接受锚、typed observation context、canonical producer/deep重算、一次消费、失败回滚、逐cluster重放、关联撤回及fresh恢复必须整体实施。当前只完成前置描述。自然身份、正式参考/未知模型/时间相关性、朝向、长期与动作收益、B复核保持开放；完整H/R/I/C/Z/r/V、三RB块、七算子、分类对照和主动澄清保持。
