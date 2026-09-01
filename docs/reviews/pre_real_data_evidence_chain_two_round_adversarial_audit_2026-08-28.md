# 正式数据前证据链两轮对抗审核（2026-08-28）

## 结论

两轮审核在修复后均通过。通过范围是仓库内证据契约、攻击测试和全量回归，不代表真实
FindingDory 视频、O-STaR/STREAK 忠实复现或机器人硬件证据已经接入。

## 第一轮：证据链红队攻击

首次新增的五个攻击全部命中缺口：签名后原始文件漂移、帧 locator 与原始文件脱钩、子进程
软链接输出越界、退出主进程遗留后台后代、泛化 requirement 冒充完整外部复现。修复包括：

- 帧清单签发时重新读取并验签原始文件，逐帧重新物化 encoded/decoded bytes；
- 帧 locator 的基础路径必须等于已签原始文件；
- 子进程结果在签发时再次 resolve，软链接不得逃出工作树；
- 主进程已退出但管道仍被后代持有时终止整个进程组并拒绝签发；
- O-STaR/STREAK 接纳回执要求各自精确的 canonical fidelity requirement 集合，验证端也复查。

修复后第一轮定向安全回归：87 passed。

## 第二轮：全仓回归与预算攻击

命令：`pytest -n auto --dist=loadscope --durations=25 --cov=src --cov-report=term-missing`。

结果：2550 passed、1 xfailed，coverage 89%，耗时 53:41。功能回归通过，但实测证伪了旧
45 分钟执行预算和 50 分钟 job 预算；现已分别调整为 65 和 70 分钟，没有删除慢测或降低
覆盖率。

## 仍保持 BLOCK 的边界

- 当前 O-STaR/STREAK manifest 仍不是 `REPRODUCTION_COMPLETE`，不能签发真实接纳回执；
- 原始数据首次签发仍需要独立 custodian 核对官方来源和许可；
- 结构三尚未获得正式视频逐帧解码及真实 VLM/VIO/机器人执行证据；
- 两轮通过不构成 action/utility、external validity 或论文创新结论。
