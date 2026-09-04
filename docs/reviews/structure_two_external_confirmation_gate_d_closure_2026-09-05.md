# Structure Two D：外部确认门收口与两轮对抗审计（2026-09-05）

## 结论先行

**D 当前为 `BLOCKED_FAIL_CLOSED`，不是通过。外部强基线效能解释继续禁止。**

代码侧已经补齐 live-byte freeze（实时字节冻结）、独立 sealed opening（密封开启）、canonical per-episode executor（规范逐回合执行器）、macOS 真实隔离后端、三角色加 authority witness（授权机构见证）签名链、持久 opening consumption（开启消费）以及 raw-input combined verifier（原始输入组合验证器）。这些能力不能替代尚未产生的外部证据，也不能把组件级移植包装成原生复现。

当前六个邻居仍是 **6 个 component cores、0 个 native reproductions**：

| arm | 邻居方法 | 当前证据等级 |
|---|---|---|
| `corrected_amg` | Damen-Hogg Activity Manipulation Grammar | component core only |
| `o_star_matched` | O-STaR | component core only |
| `active_dreaming_matched` | Active Dreaming Memory | component core only |
| `auto_dreamer_matched` | Auto-Dreamer | component core only |
| `trustmem_matched` | TRUSTMEM | component core only |
| `brainctl_matched` | brainctl | component core only |

`structure_two_v0_6_evidence_index.json` 仍为 `DEVELOPMENT_EVIDENCE_NOT_COMPLETE`，所有外部 source acquisition、implementation bundle、fidelity result、Gate-A result、sealed holdout、signed Gate-B trace、trust registry 路径均为空或未登记。

## 六项要求的可核验状态

1. **六个邻居方法原生复现：未完成（0/6）。** 仓库中的六个实现是明确降级的 component cores；官方运行时、原协议、原数据/环境、构建命令、方法专属 fidelity tests（忠实度测试）和 adaptation parity（适配等价性）尚无完整外部证据。
2. **独立密封 Gate-B opening path：代码已实现，外部 ceremony 未发生。** commitment、freeze→commitment 双签链接、Gate-A lifecycle、custodian opening、一次性持久消费均有失败关闭校验；没有真实外部 sealed holdout 和 authority-owned WORM/transparency ledger（一次写入多次读取/透明日志）。
3. **canonical per-episode executor：代码已实现，尚未登记为真实外部执行证据。** 它强制十臂×回合笛卡尔覆盖、每任务 isolation receipt、runner/executor 签名与 aggregate hash；第二轮攻击发现整段 episode 可见性不能证明逐步因果信息边界，见下文 P0。
4. **真实隔离环境：macOS backend 已真实运行通过，但不等于容器/硬件级证明。** 本轮关闭继承 stdin，显式 `DEVNULL`、`close_fds=True`、空 `pass_fds`，移除 `/dev` 整树读权限，只开放 `/dev/null`、`/dev/random`、`/dev/urandom` 三个明确字符设备。真实探针验证网络、隐藏文件读取、代码/输入/外部目录写入、fork 和未登记 exec 均被拒绝。OCI 路径仍只是 `CONTRACT_ONLY_NOT_EXECUTED`。
5. **外部三角色登记与三签冻结：密码学流程已实现并专项通过，真实外部登记未发生。** reviewer、executor、custodian、enrollment authority 与两个 runner subkeys 共六把不同 Ed25519 key；runner possession、executor delegation、三角色 detached signatures、authority-after-three-roles 均被验证。caller 提供的 previous head/absence flag 不是 authority-owned atomic ledger，故不能称为完成的外部托管冻结。
6. **Gate A → sealed Gate B → combined authorization：按顺序失败关闭。** 见下一节。

## 顺序执行结果

| 阶段 | 结果 | 原因 |
|---|---|---|
| Gate A | `BLOCKED_BEFORE_EXECUTION` | 缺少真实 validation input、deterministic execution log、双签报告、外部冻结清单和 custodian-sealed holdout |
| sealed Gate B | `NOT_RUN` | Gate A 未通过；旧 v0.7 已于 2026-09-05 明确失效，当前 comparator-typed v0.8 为 `FROZEN_NOT_EXECUTED` 且没有 formal raw execution receipt |
| combined authorization | `BLOCKED_FAIL_CLOSED` | combined v1 现在要求 current formal Gate-B receipt；历史 v0.7 即便签名完整也会在角色签名前被拒绝 |
| 外部强基线效能解释 | `FORBIDDEN` | 上述顺序链没有通过，且六方法原生复现为 0/6 |

旧 `structure_two_sealed_dual_gate_b_v1_0` 现在仅能生成/验证 `HISTORICAL_V0_7_RECEIPT_INVALIDATED`，其 `formal_gate_b_passed=false`、`external_method_efficacy_comparison_allowed=false`。D combined verifier 不再把该历史结果提升为正向授权。

## 第一轮自我攻击：证据链、签名与状态机

覆盖 positive/consequential outputs（正向/后果性输出）、forged-but-complete paths（格式完整伪造路径）、substitution/replay/stale/fork（替换/重放/陈旧/分叉）和 signing order（签名顺序）。

发现并本轮修复：

- frozen verifier 的 live bundle/entrypoint/config/engine 未与 freeze snapshot 紧邻执行前后逐项对齐；现加入 admission、before、after 三次完整测量，并把实测 snapshot 与 isolation tree hash 写入三签内容。
- signed isolation receipt 未明确证明空 stdin；现增加真实 fd0 探针和 receipt 字段。
- Gate-B finalizer 曾接受 optional attestations；现要求并立即验证 reviewer、executor、custodian 以及覆盖三签后的 authority signature。
- standalone Gate-B verifier 缺 trusted clock upper bound（可信时钟上界）；现强制 `verification_time_utc`。
- “before seed commitment” 名称会与 v0.6 manifest 中已有 commitment hashes 混淆；现明确为 “before independent sealed Gate-B commitment record”。
- 旧 v0.7 receipt 可被 combined 硬编码提升；现 current Gate-B protocol 与 `formal_gate_b_passed` 双重失败关闭。

仍未关闭的 P0：

- opening consumption 后没有 authority-owned atomic terminal append，canonical/Gate-B/combined 仍缺真正的单一后继 CAS/WORM ledger；当前 combined 正向路径已因 v0.8 未正式运行而关闭，不能借此声称 anti-equivocation（抗等价分叉）。
- 没有未打桩的 production raw-chain positive；此前 synthetic combined positive 直接替换整条 chain verifier，已删除为正向证明的用途。
- standalone 历史 dual helper 接收已经类型化的上游对象；它只可用于失效 v0.7 历史重放，current combined public path 必须从 raw inputs 重建。

## 第二轮自我攻击：能力隔离、因果时序与机制真实性

发现并修复：

- inherited stdin 可作为未登记 opening/truth/seed 通道；已关闭并由真实 sandbox 探针验证。
- `/dev` 整树读取面过宽；已缩到三个明确字符设备。
- combined 对 verifier swap/restore 的追溯绑定不足；已加入 freeze snapshot、isolation receipt 和前后 live material 的交叉绑定，可检测如实记录的替换和 combined 验证期间的变化。

仍未关闭、会阻止 current formal Gate B 的 P0：

- **future observation capability**：canonical 与 dual v1.0 仍把完整 visible episode 交给单一进程，step 0 可读取未来 step。prefix hash 正确不等于进程当时只拥有 prefix。
- **pre-action ordering self-report**：`pre_action_pre_evaluator_truth` 及 instrumented flags 由 arm 输出；没有可信 broker 先不可变提交 belief/policy、再放行动作/下一 observation 的单调 transcript。
- **mechanism circularity**：机制 event 和 state hashes 由同一 arm 自报；缺少独立 observer/method-specific transition verifier 从输入、前态和实际输出重算。
- **pathname-level TOCTOU**：prehash 与真正 `exec` 打开路径之间仍可发生同用户 swap-execute-restore；彻底修复需要 open-fd pinning、content-addressed immutable staging 或只读 mount/container。
- macOS profile 以 `(allow default)` 起步，并非完整 capability deny-default；Mach/XPC 面由宿主实现决定。
- producer source snapshot 未闭包 interpreter、dependency lock、native libraries 和 imported runtime data；frozen verifier 也缺预登记 known-good semantic digest/独立第二实现。

因此第二轮不是“全部攻击通过”，而是发现了当前设计不能安全授权的原因；系统应保持关闭。

## 真实隔离探针与专项回归

- 独立 backend probe：`PASSED`；`stdin_is_devnull=true`，所有登记的拒绝探针通过。最终 receipt hash 为 `7591d694c8edf62cde8d2b95c98416d48d0193309a9d6332d6d97957aded0c7e`，rendered profile hash 为 `b424edb3001365db4674ac3ab614d8f0844c60fdebd4c28d22d51a536efffe68`，宿主 `/usr/bin/sandbox-exec` binary hash 为 `d1ee30dbde955aaa75c7f801fdfea4df05b10129454d7982eb6453f771436d42`。该 receipt 使用临时自签 key，只证明本机 backend 行为，不证明独立托管。
- ten-arm dual smoke：真实 macOS sandbox 执行 `10 arms × 2 episodes = 20 tasks`；每个任务保留完整 21,601 belief support 和 39 action support，首个两步输出 176,670 bytes；本轮样本耗时约 0.197381 秒。它是 synthetic smoke test，不是 72 episodes × 10 arms 的 production run。
- production 720-task run：未运行；没有真实冻结六方法 bundle 和 sealed holdout，运行合成替身会制造假绿。

最终 D 专项回归收集 `305` 项，结果为 `304 passed, 1 skipped`；唯一 skip 是受限外层环境不允许嵌套 `sandbox-exec`，对应真实 10-arm 用例随后在宿主权限下单独运行并通过。随后对 readiness 的 current-protocol 字段修正又单独得到 `12 passed`；它现在同时保留历史 v0.7 字段，并明确报告 v0.8 为 `FROZEN_NOT_EXECUTED`、formal receipt 未验证。D 相关 10 个本轮修改文件的 Ruff lint 与 format check 均通过。全局 source-bundle/manifest、全量回归和 checkpoint 不在本轮重算，按协调说明由 A 在 B、D 都停止写入后统一完成。

## 允许解释效能的最小剩余条件

只有同时完成以下事实，才可解除 `FORBIDDEN`：六个 native reproductions 与方法专属 fidelity/adaptation parity 全部外部验真；current v0.8 formal causal broker 与独立 mechanism verifier 完成；不可变执行 staging 与 authority-owned append-only terminal ledger 完成；真实 720-task raw chain 在外部六 key custody 下依次通过 Gate A、sealed Gate B、combined authorization。任何 synthetic fixture、component core 或历史 v0.7 receipt 均不能替代这些条件。
