# 实际归档位置模型 Native 桥接与裸采样点对照

本轮将原始仿真RGB-D/相机自身位姿、公开候选与实际训练的四个残差模型接入了受控Native发布：真实位置似然改变目标权重和六维Gaussian条件统计，重复/中性步骤不重复计证据，撤回实际已发布来源后恢复到无该因子的数值结果，另进程SQLite恢复与完整fresh复算通过。**身份关联、语义事件、prior与unknown分布仍为明示的合成设定；这不等于自然身份推断、实时新观测循环或动作收益已完成。**

实际冻结/双审/运行源码 `82c7a81fba0c3af3688978ce222b1b94e4cc5bd9`，901 Python；父PR78实际源码1bd6c204d349024196c23df12cca61dbcea91e6c，父case ledger `9b9ed2d9208c1907d8295d5edc5aeb2f48af7b9b3625108b9642430a06780efc`。本轮分支codex/pc-a-archive-native-bridge-20261001。两轮顺序A辅助审核绑定实际源码，详见ADVERSARIAL_REVIEW_1/2；不是B独立、全仓CI或自然系统验收。后续文档提交不替代功能SHA。开发中间源码160项及四模型8臂/16fresh受控验证与最终审核按各自source map区分。

## 实际后验消费

固定公开顺序的第一个有效输入：frame000，house01/SDK004，SSDLite候选de8a15ab-6a24-503c-87e3-f3dbd7646311，seed[21,33]，64完整支持点。来自训练屋，不是held-out任务。原raw字节/UUID/采集回执/相机位姿均未改，完整full/single支持与原始/归一系数对应复推；合法不同ID分别保存。私有mask或对象标签未用于在线选seed/关联，历史父包复算仍会访问离线训练与评价资料，不能称恶意进程隔离。

四模型各active/no-factor两臂；每臂重复不增量、三次neutral继续、active与撤回后两次新进程恢复，撤回实际published after revision后replay。原离线command不进入本owner物理命令表，本轮相机命令0。此轮复用原typed_factor_graph_transformer检查点作工程载体，原三种提议备选保留；checkpoint是历史合成语义训练，不是新自然提议训练或优化收益。

known初始N(0,I6)、reference世界原点0，unknown/aggregate共用N(0,100I3)，三分支初始等权。known按更新前S=HΣHᵀ+R计LL，再用原R更新同份测量，H=[I3,0]；朝向没有新观测。此世界原点prior与实际场景点可能距离很远，以下known权重不能解释为识别正确率或自然任务完成率。

| 模型/参考 | known LL | unknown/aggregate LL | known后验概率 | known归一log权重 |
| --- | ---: | ---: | ---: | ---: |
| soft_affinity/sdk_aabb_center_m | -100.233133 | -10.770109 | 7.00926e-40 | -90.156171 |
| soft_affinity/sdk_transform_position_m | -97.751394 | -10.770109 | 8.38451e-39 | -87.674432 |
| uniform/sdk_aabb_center_m | -97.237980 | -10.768323 | 1.39854e-38 | -87.162805 |
| uniform/sdk_transform_position_m | -95.950432 | -10.768323 | 5.06815e-38 | -85.875257 |

原模型/配置和完整保存数据库通过对应源码恢复；实际fresh重新从父原件及模型运行，再对原数据库的临时副本复核，原件未变。模型、public readout、全部302父产物与各祖先输入的外pin/全清单/匹配历史源码均检查；不执行ledger内任意argv。原件完整性测试与真正数学重算分开记录，不能仅凭自签文件清单放行。

## 同分母位置对照

裸seed直接取同一公开深度点，独立schema，不改soft/uniform生产身份。所有公开点先生成，仅原train1–8屋拟合两参考bias/full covariance；validation9–12不参与参数估计。全部公开校正在打开validation标签前生成。两份聚合label的共同字段逐项相同，每seed计一次。保留96帧、VOID/空帧/无监督，另报unique(action,u,v)，相关seed不算独立样本。

| 估计器 | 离线参考 | validation seed | 原始RMSE(m) | 去train bias RMSE(m) |
| --- | --- | ---: | ---: | ---: |
| bare_seed | sdk_transform_position_m | 1664 | 0.750330 | 0.661757 |
| soft_affinity | sdk_transform_position_m | 1664 | 0.674738 | 0.615581 |
| uniform | sdk_transform_position_m | 1664 | 0.833717 | 0.785566 |
| bare_seed | sdk_aabb_center_m | 1664 | 0.549088 | 0.561687 |
| soft_affinity | sdk_aabb_center_m | 1664 | 0.513540 | 0.523058 |
| uniform | sdk_aabb_center_m | 1664 | 0.712308 | 0.711919 |

全部逐屋/对象帧/对象/seed指标和不可用模型详见bare/report.json；103个裸seed产物包含公开点、训练输入和模型。参考不同的误差是不同目标定义，不能据此选正式参考；不做p-value或校准/泛化宣称。本轮没有根据validation重训/选择模型或改变在线似然配置。

## 复算与独立公式

- bridge：run 761.56s / fresh verify 722.54s，76保存文件在复核后逐字节不变。
- bare：run 354.22s / fresh verify 398.48s，103保存文件在复核后逐字节不变。

全部case ledger pin `328b4b10276c44a05b91cfcbb7f24d370ff8092e85a9fe729939311bc6b4fc42`；独立复核JSON `58b9a26a0e86614a73dbb6b3fc7b6b081c4ba3a61994a1cdd12b2e56e75dacdd`。外部脚本使用父PR78已独立核验并外pin的原公开点/标签，重新计算bare残差、train矩、split/house指标/主要分母和全部公开校正；Native用SciPy logpdf与Kalman后验形式重新计算原始LL、log/probability和完整6D信息参数，同时核对未知分支/其他RB不增量与撤回等同无因子。它不代替SQLite来源/receipt真实性验收，不独立重复逐对象帧指标的每条公式或所有provenance哈希，也不是新采集/检测验收。

## 下一主项和未完成

实际单capture到Native数值消费的桥接已完成。下一主项仍为同一语义来源后续新raw observation的拥有者事务及逐cluster重放：现在相机结果可被接收，但没有完成同语义多capture各一次消费、失败回滚与关联撤回全链。不能通过改semantic UUID、清缓存、未来图像或重复堆乘相关seed来绕过。

自然跨视角身份/未知与杂波分布、正式位置参考与prior/校准、朝向、长时程、实际动作效用、公平任务对照、B独立和统一验收仍开放。完整H/R/I/C/Z/r/V、三个RB blocks、七算子、原分类对照和主动澄清保持。

协议PLAN.md、双审报告、run_experiment.py/case-results.json、independent_result_check.py/independent-analysis.json、position-comparison.png/PDF和全部开发/失败记录构成本轮证据入口。
