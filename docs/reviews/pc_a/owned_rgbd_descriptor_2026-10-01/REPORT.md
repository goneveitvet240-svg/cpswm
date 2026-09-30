# 当前拥有者 RGB-D 原件描述接口

本轮补上 action UUID→当前拥有者实际签发/接受原件的只读描述重建。它验证原命令/接收回执、RGB-D/相机自身位姿、scope/时间/单位、当前 Native origin/source 及完整父权重证据；完整派生描述必须从原 owner 重新生成后逐类型逐字段匹配。**不更新后验、不执行新的相机动作、不赋予观测消费 authority，也不独立认证 owner journal 的历史。**

实际冻结/两审源码 `6faa17e178ad001de6b5c0e1094f9e62568d7a7e`，903 Python文件。只新增 `owned_position_delivery.py` 和对应测试，无既有core/collector/持久化格式改动。功能base82c7a81fba0c3af3688978ce222b1b94e4cc5bd9；先合入父交付dc57a687f6cfe0912de7415357765fff79f2c2ff，再冻结源码。后续文档交付SHA不能替代上述功能SHA。

## 已实现与实际审查

只支持原 modeled problem基于仍未改变的 canonical Native base的成功RGB-D capture。origin、原source、父batch或generation变了就明确stale拒绝；基于额外camera-feedback prior的第二个problem不猜原历史。普通admit/archive、unmodeled、READY/失败或完整原件配对不合格均不当作合法来源。

完整父支持取已接受input body与原receipt log weights，保留显示为0但finite-log的分支；不从decision view省略后的atoms反推。helper只以严格UUID检索原件；不接受调用者的新XYZ、source、cutoff或“verified”标记。return值的posterior_updated与consumption_authority均为False。

作者开发6项通过；首轮4过2失败（profiler误计JSON解码、既有policy合法STOP）及全部原件保留。正式两轮由未参与这两文件实现的A辅助审核者顺序完成：

- ADVERSARIAL_REVIEW_1.md: 82项通过（6新增+73兼容+2独立+1 profiler），完整派生替换/合法恢复/有限log零显示支持/旧新action与P5后果；一致owner子图改写为信任边界；SHA256 99389e2ead8124a092d26e04784d6f1213160abbf7253a250736f0761797d91c
- ADVERSARIAL_REVIEW_2.md: 4项独立核心测试通过，另1项harness诊断通过；完整跨capture替换/90位Decimal父log支持/fresh及P5、SQL、DB后果；保留失败及一致owner子图信任边界；SHA256 3941ebf8a1e9ab1b0b0aa182ee4225156492e09ec31d3f8450c67900b592d9d5

合法路径实际调用prepare→execute→accept并从新进程SQLite副本恢复；camera为显式受控fixture，不是Unity新采集。实际计数、合法恢复、完整类型描述改动、单侧原件错误、stale和后果检查均以两个报告及原日志为准；不把子循环攻击数量混报成pytest项数。A辅助不是B独立或全仓/自然系统验收。

## 计算与信任边界

完整Native原证据验证保留。在cold/resume窗口可重算旧proposal和旧raw位置证据；首次/重复helper也会执行旧位置验证，详profile原件。它没有新增对本次capture A的视觉检测、选点/位置似然或后验发布，不能笼统写“零推理”。恢复启动、helper窗口、验证memoization分别记录。

无副作用指semantic/P5、Native批次/统计、producer消费状态、账本、owner命令/receipt/raw目录及持久数据库；不声称整个Python进程不写缓存。原DB保留，验收使用副本。

原owner目录是可信输入。描述自签改动、单侧raw/delivery不一致可被拒绝；但把新capture相关delivery/raw/receipt子图一致重写，即使命令/origin保持，也没有独立接受锚证明历史原字节。这不是完整消费authority；不能将这类一致重写的边界冒称已被认证。双审中相关可接受/拒绝边界以报告明确区分。

## 下一完整主项

下一轮仍需同一语义S后新的owner capture A产生真正Native更新：签发/接受锚、typed observation context、canonical producer与deep重算、逻辑一次消费、失败回滚、逐cluster重放、关联撤回及fresh恢复必须作为同轮完整协议。当前描述接口可以提供前置原件核对，不能替代上述环节；不能改semantic UUID、清缓存或默认相关帧独立来制造进展。

父轮PR79已完成实际归档四模型到Native和裸点对照：bare/soft/uniform验证去biasRMSE为pivot .661757/.615581/.785566m、AABB .561687/.523058/.711919m；38/96空候选、55/96无监督，存在房屋反例与曝光相关样本。它仍为受控身份/prior、0新物理相机命令。父完整报告在本分支继承的 `docs/reviews/pc_a/archive_native_bridge_2026-10-01/`。

本轮没有选择正式参考、未知模型或时间相关性，不缩减H/R/I/C/Z/r/V、三RB块、七算子、分类对照和主动澄清。自然身份、朝向、长时程/动作收益与B独立复现仍开放；原Windows可移植性限制未在本轮修改。
