# 远端失败原件保存实证

GitHub运行36639386505，实际源码4ae76850ffd99d86703b4e45e837d4e402203c78，Ubuntu环境。运行最终failure；执行器3900秒预算后先SIGINT，子进程退出2，运行器如实返回124/TIMED_OUT，3911.26秒完成清理，不需要强杀。

归档SHA256 93085faae3d8fab8bd7d5664580e0b66ad93a7659f80138f39dc18471171b9b7与GitHub官方digest一致，归档内原始pytest.log的SHA与结果记录一致。保留4335条JUnit结果：4215通过、90失败、29跳过、1预期失败（后两者JUnit共30）。这只是部分运行，6050项完整集合未完成；覆盖率XML没有生成，明确记录缺失。上传步骤成功不是测试或科学验收成功。

失败分布包括历史来源依赖（60项）、两个严格1秒锁交接测试、旧清单/回执、旧材料schema/缺包、trace冲突，以及8项完整科学循环测试在学习交互材料重生成条件之前就拒绝，未到达原定攻击位置。最后一组不得通过放宽错误字符串就宣布覆盖，必须先恢复合法正路径并重新生成其当前材料。

此源码尚未包含后继的完整历史检出、虚拟环境入口及当前比较测试适配，不能把90项全部归因于当前最终候选，也不能提前认定后继已解决全部问题。原始90项回溯在remote-4ae-failure-nodes.json；当前Windows/B独立验收仍单列。

## Full-history checkout run

Run36641464926 at21619f014b43c724b28a93fa4612e03e5a10e2c7 also timed out, with raw artifacts successfully uploaded and digest/log hashes verified. Named JUnit outcomes:3393 passed,4 failed,1 expected failure. Three anonymous empty testcase elements are retained separately and never counted as passes. The earlier run also contained three such anonymous elements in addition to its4335 named outcomes. Of the60 previous history-dependent failures,53 finished and passed in the new run;7 were not completed. This paired node comparison, not the change in total failure count, is the evidence for the checkout fix. Complete CI remains open. Artifact SHA2568553e1ed09e252b3c232637fa9afdd067d56cf0f220ee6b9e32a5fc0278bb267.
