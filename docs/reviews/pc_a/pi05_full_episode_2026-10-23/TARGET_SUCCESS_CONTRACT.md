# 目标匹配成功判据：已核对接口与未完成边界

核对官方LIBERO源码 `f78abd68ee283de9f9be3c8f7e2a9ad60246e95c`。`bddl_files/libero_spatial/pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate.bddl` 的目标是 `(On akita_black_bowl_1 plate_1)`；同场景还有另一个黑碗，不能把任何黑碗上盘都算成功。`LiberoTabletopManipulation._check_success` 逐个求值该文件目标，环境step直接用它作为done。`On`调用目标对象的`check_ontop`。

本次官方指令与该目标一致，因此done适用于固定plate基线。现有 `configs/simulation/libero_goal_fixture.json` 也可发出stove指令；它不能复用原始done。场景声明了 `flat_stove_1` 和 `flat_stove_1_cook_region`，灶台对象与烹饪区域的谓词语义不同，当前没有擅自把二者合并或选为新科研成功指标。

后续目标评价接口应绑定：任务/初始状态、当前command_id、目标destination、goal_memory_revision、实际执行步范围、明确目标对象及谓词。旧指令上的成功不能结算新指令；修订后目标不匹配应拒绝，未标定目标返回unknown；不得由SAM预测或夹爪闭合替代成功。对象真值/谓词仅进入隔离evaluator，不能泄露给π0.5、SAM或人物记忆。

需要覆盖合法plate/stove目标、第二个黑碗替代、旧命令成功、完整一致伪造记录、错误后修正、未完成动作及重规划取消等路径。当前实际完成的是plate固定目标运行与逐步官方成功记录；stove成功评价实现、正式反馈来源权限、多目标配对实验仍未完成。本文件是源码核对和接口准备，不是这些测试已经通过的声明。
