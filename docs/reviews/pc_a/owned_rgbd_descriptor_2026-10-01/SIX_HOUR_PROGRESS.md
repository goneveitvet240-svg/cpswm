# 六小时主干推进交接

工作窗口：2026-10-01 00:18:40–06:18:40（上海）。本文件汇总该窗口实际完成结果，不把预算时长当作实际运行时长。四个独立工程轮各自冻结源码并经过顺序两轮A辅助对抗审查，修复变更后重新审查；未把早期失败版本列为通过。

## 已完成

| 轮次 | 实际源码 | 结果与交接 |
| --- | --- | --- |
| 固定特征对照 | a6c026963b5fec1503fa0d582fe016eccf60c756 | 同一原数据、RGB/几何/联合对照，真实run与fresh 292输出复核；两审各447项；[PR77](https://github.com/goneveitvet240-svg/cpswm/pull/77) |
| 位置因子与数值继续 | 1bd6c204d349024196c23df12cca61dbcea91e6c | 两估计器×两位置参考共四残差模型；补完整raw重算与有限log质量传递；真实run/fresh 302输出复核；最终两审68/35；[PR78](https://github.com/goneveitvet240-svg/cpswm/pull/78) |
| 实际归档接入Native与裸点对照 | 82c7a81fba0c3af3688978ce222b1b94e4cc5bd9 | 真实RGB-D和四模型影响权重/六维统计，重复/中性继续/撤回/SQLite fresh；bridge/bare各run+verify四次成功，76/103原输出不变；[PR79](https://github.com/goneveitvet240-svg/cpswm/pull/79) |
| 新相机原件描述前置接口 | 6faa17e178ad001de6b5c0e1094f9e62568d7a7e | 当前owner action→原command/delivery/RGB-D/pose/Native source重建；完整typed派生匹配、stale与后果检查；仅描述，无新观测消费权限或后验更新 |

当前描述两审：82项通过（6新增+73兼容+2独立+1 profiler），完整派生替换/合法恢复/有限log零显示支持/旧新action与P5后果；一致owner子图改写为信任边界；4项独立核心测试通过，另1项harness诊断通过；完整跨capture替换/90位Decimal父log支持/fresh及P5、SQL、DB后果；保留失败及一致owner子图信任边界。所有测试计数属于各自审核范围，包含跨轮回归重复，不可累加成全仓独立覆盖。审查者均为本机A辅助；Windows电脑B尚未验收。

最重要的修复不是增加审查数量：早期完整likelihood/aggregate自洽替换能改变目标权重，已改为从受保护原件和真实父链深重算；随后显示概率下溢为0导致下一步log(0)，已保留原finite-log支持并完成继续路径。两个失败及后来的验证失败原件均保留。当前owner描述仍信任接受目录，一致重写raw/delivery/receipt子图不会被独立历史锚认证，已明确不赋消费authority。

## 方法目前运行得怎样

固定12屋96帧：8屋训练，4屋已曝光开发验证；下表使用同一1664个合格验证seed，单位米，都是减去训练集bias后的RMSE。soft为学习亲和度加权表面读出，bare为单点深度，uniform为同公开网格均匀平均。

| SDK参考 | bare | soft | uniform |
| --- | ---: | ---: | ---: |
| 物体transform pivot | 0.661757 | 0.615581 | 0.785566 |
| 轴对齐包围盒中心 AABB | 0.561687 | 0.523058 | 0.711919 |

soft在总体上比裸点低约7%误差，但房屋9存在裸点更好的反例；验证seed强相关且房屋11/12占76.98%，不是1664次独立试验。38/96帧无候选，55/96无合格监督。去bias也不是全面改善：soft AABB原始0.513540m→0.523058m退化。没有基于这些结果选择正式参考、身份阈值或宣称校准/泛化。

亲和度联合特征BCE/Brier=0.298310/0.087341，比几何特征0.317563/0.089888略好；不同实例负类Brier仍0.482991，不能宣称已经解决身份分离。

真实归档与四个训练模型已改变Native位置likelihood、log权重与六维Gaussian信息统计。已观察三维位置被更新，未观察的朝向保持；受控身份/语义/prior/unknown使known质量很小，不能把它直接解释为识别失败率。这个实验采用训练屋首个公开有效seed，不能代表自然全场景任务。bridge/bare四次实际执行约761.56/722.54/354.22/398.48秒；fresh检查原输出未变，不声称新建SQLite字节完全相同。

本窗口没有新增物理Unity相机命令；实际数据来自此前保留原始回执的仿真采集。新描述接口的相机使用受控fixture经过真实owner API。当前结果分别证明实际归档因子接线和新capture原件适配，没有合起来冒称在线自然闭环。

## 下一步优先级

最高优先级是同一semantic source下的新owner capture A产生真正Native更新。依次完成但同轮交付：签发/接受锚与typed上下文；canonical producer及consumer完整原件/父链重算；消费一次和完整失败回滚；逐观测簇重放与来源撤回；纯fresh SQLite恢复与collector接线。完整协议设计见继承的archive_native_bridge_2026-10-01/NEXT_OBSERVATION_IMPLEMENTATION.md。

受控开发正路径应先neutral语义S→真实owner签发A→位置target变化，保留P5/语义UUID/原时间不变，重复A无增量，第二capture B保留并明确暂不支持，撤回S及其A后等于保留来源S0的no-factor。不能靠重发semantic、改UUID、清消费记录或默认邻帧独立来造闭环。

该工程路径已可继续自主实施。正式位置定义、自然I对应、未知/杂波模型、跨帧依赖与接受阈值仍需科学论证及用户决策；用户既有RGB-D/self-pose、离线监督、主动澄清授权保持有效，不重复索取。长时程/真实动作收益、公平任务对照、独立测试场景与B/统一验收仍开放。

## GitHub与证据状态

PR77/78/79及本轮均为叠加草稿交接，不自动合并共享集成分支。交付前fetch确认集成19ddf26830348a2f0b33f0af54d6ba702c5cfb1c、B fd4ca6ef5e81c90d7cf7987b42c0b2810d8a810a未变。用户原checkout HEAD09eb4d48e1c11082e90ca18332d04333e6b5b47a与原未跟踪文件保留，STATUS_B未修改。

每轮完整运行、失败、checkpoint/数据库、审查和源码映射均封存并逐成员读回。包内摘要不等于独立外部真实性认证；既有Python/模型/绝对路径与Mac SDK限制仍存在，Windows不能直接搬原DB运行。完整H/R/I/C/Z/r/V、三个RB blocks、七算子及原分类对照/主动澄清保持。
