# 冻结 AI2-THOR 源码构建补丁

上游：Allen Institute for Artificial Intelligence / AI2-THOR，
https://github.com/allenai/ai2thor ，固定 base
`f0825767cd50d69f666c7f282e54abfe58f1e917`。上游授权文本见 `LICENSE.ai2thor`。
补丁保留上游文件版权头；新增及修改部分是 CPSWM 开发实验，不是 AllenAI 官方发布。

- `post_house_a86468d6.patch`：已构建的原型。真实多人生成及部分状态机检查通过，扩展审核发现缺失对象资产仍能建房“成功”，**CHANGES_REQUIRED**。
- `post_house_f52271cf_UNVERIFIED.patch`：包含以上原型并修复缺失资产静默跳过；当前 Mac 锁屏，**未重新编译/未复测**。旧原型结果不转移给它。
- 两份补丁均从同一 upstream base 生成，只选一份，不叠加。应用到新的独立源码 checkout，先 `git apply --check <patch>`，再 `git apply <patch>`；不得覆盖已有工作。
- 2020.3.25f1 是冻结编辑器版本；不要以升级到 Unity 6 代替复现。
- 直接命令行初始化许可在本机失败；通过已登录 Hub 添加并打开 `unity` 子目录成功。编辑器中选择 `CPSWM > Build Frozen Mac Development`，输出为系统临时目录中的全新 `cpswm-unity-gui-build-*`，不覆盖原官方 Player。
- 菜单只执行本地构建，不复制登录令牌。未自动接受条款或绕过系统授权。日志中可能含许可信息，原始 Editor 日志不能公开提交。

开发 API（仅上面定制构建可用，不是官方 SDK 的既有能力）：

1. `Initialize(agentCount=1)` → `CreateHouse` → 合法 `TeleportFull` 到房屋允许位置。
2. `CpswmHouseContext` 返回真实 `generation` / `houseReady`。
3. `CpswmSpawnAgents(agentCount=N, generation=<刚返回值>, requestId=<本次稳定标识>)`，N 为 1..6。
4. 使用真实 `agentId` 寻址动作。重复同一生成请求不增生；新代次不能重用旧 generation。

这是默认 robot agent 的物理多实体路径，不是可识别人类角色的执行后端，也不生成完整提议训练标签。框架中的多人、隐藏事件、开放世界、可逆归因和具身闭环范围不变。

报告：`docs/reviews/pc_a/procthor_unity_build_2026-09-13/PROGRESS_AFTER_AUTH.md`。
