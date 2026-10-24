# π0.5 完整官方任务：118步首次成功，动作物理重放通过

官方pi05_libero在table_center、init0、simulator seed7、policy seed0的一次完整运行中，执行118个动作、24次模型推理，在第118步首次触发官方成功条件并停止。220步为官方spatial上限，每5步重规划，前置10步静置。总墙钟1031.493秒，模型推理合计980.340秒；不是受控性能基准。

运行源码 `611e9dbee986a7fe6a2af33661d7a7d284402d03`，起点Git干净，所有绑定源码运行中未变。核验源码 `2c2b6035382501dee7cf10a7a61a90c7ac82873a`；base `ea0d6f231ba9971d75131e9fa9fc4820ab4452cc`。官方openpi `215abfb217dbac7d5f1273282331b9b1866c0479`，LIBERO `f78abd68ee283de9f9be3c8f7e2a9ad60246e95c`，模型/Tokenizer校验清单绑定在manifest。

## 实际证明的范围

- 本地适配器调用官方网络、Tokenizer、归一化和输出变换，使用已有官方权重、JAX CPU；不是smoke控制器，也不是模型训练或权重修改。
- 官方正确指令要求指定黑碗放在plate。官方BDDL成功谓词为 `(On akita_black_bowl_1 plate_1)`，不是任意黑碗；本结果不额外证明松爪后长时间稳定，也没有测后续持久成功。
- 从同一官方初始状态重新执行全部118个保存动作，逐步EEF/夹爪与done一致；24份策略输入（双RGB、状态、prompt）重建匹配；最终公开观测和图像匹配，录像119帧。核验没有重新执行模型推理。
- 本运行固定官方目标，没有启用CPSWM目标选择或SAM。成功不能归因于CPSWM，也不能估计总体成功率。

## 工程检查与证据

相关集成/记录合同/运行边界测试33项通过，Ruff通过。另以实际完成轨迹构造两个格式自洽副本：把成功提前一帧、同时修改策略输出及执行动作；记录合同接受两者，但物理重放分别在done和EEF轨迹处拒绝。[反例回执](evidence/physics-negatives.json)。这是部分一致篡改覆盖，不能证明对任意完整伪造的认证能力。反例脚本首次仅因错误匹配多行traceback文本而未通过；修正匹配后重新执行两例，没有放宽物理断言。覆盖首次成功在第1/5/6步、无成功到上限、输出最终帧、部分动作块，以及错误成功时刻/缺动作/缺推理/错误prompt/smoke冒充/脏源码/提前结束等合同反例。

[原始summary](evidence/completed_run/summary.json)、[运行manifest](evidence/completed_run/manifest.json)、[动作日志](evidence/completed_run/journal.json)、[完整录像](evidence/completed_run/rollout.mp4)、[核验回执](evidence/verification.json)、[测试日志](evidence/tests.log)。最终帧已目视检查，成功结论以官方谓词与物理重放为准。

首次run01在20动作/4次已返回推理后以143终止，没有summary，原因未确证；它单独完整保留为中断证据，不纳入完成次数或拼接轨迹。后台run02未实际启动，无manifest/动作。run03从头执行完成，本报告不隐去这两次启动问题。

## 与任务书的位置

E0首批条件参考、E2四修订条件见PR119；可选后缀重放及成本见PR120；两步全路径参考与bootstrap比较见PR121。本批推进E6到固定正确目标的完整成功实例。

E1强基线/任务矩阵、E3机制切换、E4自然视觉与噪声、E5长期闭环收益均未完成确认性实验。E6的CPSWM多目标完整轨迹、stove成功评价、自然人物归因和真实视觉成功反馈仍未完成。源码核对及目标匹配接口边界见[TARGET_SUCCESS_CONTRACT.md](TARGET_SUCCESS_CONTRACT.md)。

完整H/R/I/C/Z/r/V、三个RB blocks、七算子与隐藏事件/多人物/开放世界/可逆归因/具身反馈均保留。没有代替用户选择新主指标、确认集或科学路线。全部结果为工程与局部开发证据；B独立复核、统一验收、科学优势尚未成立，草稿交接不自动合并。
