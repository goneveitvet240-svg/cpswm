# Unity 工具链与基线构建准备

后续进展见 [授权后真实构建与两轮审核](PROGRESS_AFTER_AUTH.md)。下文保留授权前历史状态，不覆盖新报告。

状态：环境安装完成；实际基线构建等待 macOS 管理员授权，尚未成功。

## 固定来源与边界

- CPSWM base: `ec2215ac7138c2b359d77219519e5628669c8b82`。
- 工作分支：`codex/pc-a-procthor-unity-build-20260913`；不覆盖共享集成或电脑 B 的修改。
- AI2-THOR upstream: `f0825767cd50d69f666c7f282e54abfe58f1e917`，完整 Git 资源下载成功，下载后工作树干净。
- 固定项目编辑器：2020.3.25f1，changeset `9b9180224418`；没有升级项目或包锁。
- 官方 Unity Hub 3.21.2 arm64 安装包 SHA-256：`1f8881fd1b985a2b945387feb4be89dac95e5d754a58e7f72c0612dcf9552ecf`，与 Homebrew cask 元数据一致。
- 编辑器安装命令实际成功：`Unity Hub -- --headless install --version 2020.3.25f1 --changeset 9b9180224418 --architecture x86_64 --errors`。本机现有 Rosetta 可执行 x86_64 命令。
- Hub UI 已显示登录后的账户菜单，以及 Personal 许可和激活日期 2026-09-13。该观察不是旧编辑器已完成许可初始化的证明。

## 本地源码和构建入口

上游源码目录：`/private/tmp/cpswm-ai2thor-source-f082-20260913`。
本地派生源码提交：`dc44ce2139cd026622fa3613421b6ed724850861`，仅增加 `CpswmBuild.cs` 和 meta。未修改 `AgentManager.cs` 或 `BaseFPSAgentController.cs`，未向 AllenAI 推送。

交付模板在 `tools/unity/CpswmBuild.cs`，运行器在 `tools/structure_two_unity_build.py`。入口构建真实 FloorPlan1 / Procedural 两个场景，沿用上游资源目录生产器，检查 Unity BuildReport，而非仅依赖进程退出。双场景仅用于开发能力对照，不是完整实验环境或人物执行验收。

运行器是准备代码，仅 Ruff format/check 已通过，尚未由成功的 Unity 编译验证。它记录关键源码/包锁前后摘要、编辑器摘要和构建回执；关键文件摘要不能代替全部资源的完整供应链审查。旧版单元测试不证明此入口正确。

实际启动命令：

```sh
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python tools/structure_two_unity_build.py \
  --editor '/Applications/Unity/Hub/Editor/2020.3.25f1/Unity.app/Contents/MacOS/Unity' \
  --source /private/tmp/cpswm-ai2thor-source-f082-20260913 \
  --output /private/tmp/cpswm-unity-baseline-build-20260913-01 \
  --timeout 3600
```

该目录是本机私有日志目录，不提交 Git。复跑必须选择新的输出目录，以保留失败记录。

## 当前阻塞的直接证据

旧编辑器起初拒绝 Hub 新许可客户端签名，随后自动启动自己的客户端并成功连接，日志显示 licenses updated successfully。因此不能把首个签名错误单独当作最终失败原因。

随后的直接阻塞是编辑器提示许可文件目录不存在，需要提权辅助进程创建；只读检查确认 `/Library/Application Support/Unity` 不存在，同时 macOS SecurityAgent 已启动。计算机自动化不允许操作此安全进程，用户须在系统窗口确认。未尝试绕过签名、许可或操作系统安全保护。

尚未生成成功回执，尚未编译任何修复后的游戏程序集。两轮新后端对抗审核 **未运行**；真实 post-house 多 agent、人物执行、原生监督及完整联合连续闭环均不据此签收。

## 后续顺序

1. 用户完成官方 macOS 授权后，检查基线构建是否真正完成；有错误则保留原始本机日志并公开脱敏摘要。
2. 固定实际 DLL / 程序摘要，验证普通场景及 ProcTHOR 的单/双 agent 正负对照。
3. 实施 post-house 生命周期与生成逻辑，编译并执行两轮作者对抗审核，覆盖合法正路径、完整伪造输入、失败原子性、重置/重复调用、动作寻址及独立反馈。
4. 将人物证据与机器人胶囊能力分开；不开始训练、不宣称完整主干默认生产路径已闭合。
