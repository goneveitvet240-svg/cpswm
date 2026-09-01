# Structure Two v0.4 外部 custodian 交接包

状态：历史材料已恢复，但因存在于候选方可访问的 session 日志中，原封存边界已失效；本交接包不得再用于签发“未披露”的 v0.4 seed-block attestation。

恢复审核见 `artifacts/project_two_v04_development/structure_two_custody_material_recovery_2026-08-31.json`。该审核只保存 seed-list 与 salt 指纹、24/24 commitment 精确重算结果和不相交结论，不保存秘密原值。原 Ed25519 私钥与独立 trust anchor 未找到。

## 已由用户明确批准

- User approval ID：`structure-two-v0.4-freeze-approved-by-user-2026-08-31`
- 批准含义：允许在独立 seed-block attestation 验证通过后冻结 v0.4 manifest，并按 Gate A → Gate B → fidelity gate 顺序执行。
- 此 ID 只是可审计批准记录，不冒充用户数字签名。

## 当前公开绑定

- 已失效 Validation DRAFT SHA-256：`4e29fd16ff242a5cb3dcb2a6bcbd68ce87c1dc06baa8af72a8e23eb61e66e326`
- Base v0.2 manifest SHA-256：`88fbf4a47601401b0b95642c99d2bf0644a8d97ac5ae03171cd60bbfabc62cd4`
- Train artifact content SHA-256：`b231e30fcd6a61e8138fddf834fc94b06bcb205f88562522e5bf361250298470`
- Holdout commitment count：`24`
- Holdout commitment-set SHA-256：`9e13bb788e88d7a5ead61f225fdd4d58e33df95ee8d529a33f98f1f39e8cf749`
- Producer source bundle：`1e9d0f39edc712065bf4e898e987fbef7b7137c1905ef2e558e194800080f921`，共 237 个文件。
- 新 validation world seeds：`440001` 至 `440012`。

登记外部公钥后 DRAFT 哈希必然变化。seed-block signature 必须绑定变化后的最终 DRAFT，不能绑定上面的登记前哈希。

## 以下原 v0.4 流程已被恢复审核阻断

即使现在另行生成 Ed25519 密钥，也不能追溯性地修复已经向候选环境暴露的 seed/salt。新密钥只能用于新协议，不能给旧材料补发“从未披露”的证明。

原登记命令保留作历史说明，不得在 v0.4 上继续执行：

```bash
.venv/bin/python apps/evaluation_runner/configure_structure_two_custodian_trust_anchor_v0_4.py \
  --public-key-file /path/to/custodian-public-key.pem \
  --key-id structure-two-v0.4-independent-custodian-01
```

登记后把最终 DRAFT 和固定代码包交给 custodian。

## 阶段二：custodian 在外部环境生成 seed-block attestation

只有 custodian 持有：

- 能重算 v0.2 commitments 的全部 24 个 raw holdout world seeds；
- 原始 evaluator custody salt；
- 与已登记公钥匹配的 Ed25519 private key。

外部执行：

```bash
.venv/bin/python apps/evaluation_runner/attest_structure_two_seed_block_v0_4.py \
  --raw-holdout-seeds-file /custodian/secret/raw-holdout-seeds.json \
  --custody-salt-file /custodian/secret/custody-salt.txt \
  --private-key-file /custodian/secret/ed25519-private-key.pem \
  --key-id structure-two-v0.4-independent-custodian-01 \
  --custodian-run-id structure-two-v0.4-seed-audit-01 \
  --output /custodian/public/structure_two_world_seed_block_attestation_v0_4.json
```

custodian 只返回公开 attestation JSON；不得返回三项秘密材料。

## 阶段三：候选方收到有效 attestation 后的自动链

```bash
.venv/bin/python apps/evaluation_runner/finalize_structure_two_world_manifest_v0_4.py
.venv/bin/python apps/evaluation_runner/run_structure_two_world_validation_gate_v0_4.py
```

只有 Gate A 报告给出 `gate_a_passed=true` 与 `gate_b_allowed=true`，才继续：

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_world_arm_traces_v0_4.py
```

十个 unsigned traces 必须分别由同一独立 custodian 在固定代码包上重算一致后签名。签名输出放入 `benchmarks/structure_two/gate_b_arm_traces_v0_4/`，然后执行：

```bash
.venv/bin/python apps/evaluation_runner/run_structure_two_world_gate_b_v0_4.py
```

## 方法声明边界

当前 Active Dreaming、brainctl、O-STaR 是 `non_faithful_proxy`；AMG、Auto-Dreamer、TrustMem 是 `not_independently_audited`。即便 Gate A/B 通过，外部 fidelity gate 仍会 fail closed，正式官方方法效能比较仍不获授权。

允许的表述只有“固定代理适配器比较”。要声称与官方完整方法比较，必须先将所有外部臂升级为 `faithful_reproduction`，完成组件等价测试和论文协议复测。
