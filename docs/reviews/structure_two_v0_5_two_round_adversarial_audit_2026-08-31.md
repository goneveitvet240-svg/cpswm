# Structure Two v0.5 两轮对抗审核与 Gate A/B 入口验证

日期：2026-08-31

## 建立结论

v0.5 是独立的新协议，不继承 v0.4 commitments、seed/salt、签名或结果。公开 DRAFT SHA-256 为 `48c29dc35e6fdfcf8a36301dd7c18b6baf1ddaab787602995a7c31b6b54e72d1`；245 文件 source bundle SHA-256 为 `a9f7ecba788304aec010380bdb2da1b5e5be75723f24c3caf004ab1db8619c4c`。

## 第一轮：custody 与 protocol-reset 攻击

攻击项及结果：

1. 把已暴露的 v0.4 seeds/salt 或 commitments 混入 v0.5：DRAFT 明确全部不继承，fresh commitment 列表在外部签名前必须为空。
2. 候选方自己选 Ed25519 key：未先登记外部 public key 时，fresh-seed 生成器 fail closed。
3. 公钥登记后更换 DRAFT：attestation 绑定 DRAFT 文件哈希，修改即拒绝。
4. 使用错误私钥或攻击者自选同名 key：public-key SHA-256 trust anchor 不同，拒绝。
5. 把 raw seeds 或 salt 写入公开 attestation：回归测试验证公开 JSON 不含任一 preimage。
6. 把“从未进入候选环境”改成 false 后重新哈希：验证器检查 assertions，拒绝；只有已登记私钥能形成有效签名。

第一轮结果：通过。

## 第二轮：Gate B 与声明升级攻击

攻击项及结果：

1. 使用攻击者签名的 arm trace：拒绝。
2. 修改 trace 内容后自重算 content hash：Ed25519 signature 不匹配，拒绝。
3. 缺臂、多臂、不同 producer run、错误 rollout 顺序/长度：Gate B 精确集合契约拒绝。
4. Gate B 失败但把 proxy comparison 改为 true：授权一致性验证拒绝。
5. Gate A/B 通过、fidelity 未通过，却把 official-method comparison 改为 true：验证器拒绝。
6. 透明代理/合理基线与官方完整方法声明混写：报告分成 `proxy_method_comparison_allowed` 与 `official_method_comparison_allowed`；后者必须额外通过 external fidelity gate。

第二轮结果：通过。

## Gate A/B 正式入口试跑

Gate A 入口已执行，但在生成任何 validation world 前正确停止：

`v0.5 frozen manifest is missing; external public-key enrollment and fresh seed-block attestation must complete before Gate A`

Gate B 入口已执行，并正确停止：

`v0.5 Gate A report is missing; Gate B remains forbidden`

这不是 Gate A 或 Gate B 指标失败，而是前置 custody 证据尚未完成。没有 validation metric 被观察，没有十臂 trace 被生成，也没有方法比较被授权。

## 为什么现在不能继续自动跑

独立性不能由候选执行环境自我授予。下一步必须由外部 custodian：

1. 在候选环境之外生成 Ed25519 key，只交付 public-key PEM 与 key ID；
2. 候选侧把 public trust anchor 写入 DRAFT；
3. custodian 在外部生成全新 24 seeds 和 salt，签发 fresh commitment block，只返回公开 attestation；
4. 候选侧验证、冻结，然后才运行 Gate A。

所谓“最高权限”可以授权本地变更和执行，但不能把同一候选进程变成科学意义上的独立 custodian。
