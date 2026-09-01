# Structure Two v0.5 外部 custodian 交接

公开 DRAFT：`configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json`

## 1. 外部环境生成 key

独立 custodian 生成 Ed25519 private/public key。private key 不得进入候选机器、Codex session、仓库或聊天；只返回 public-key PEM 与 key ID。

候选侧收到公钥后执行：

```bash
.venv/bin/python apps/evaluation_runner/configure_structure_two_custodian_trust_anchor_v0_5.py \
  --public-key-file /path/to/external-public-key.pem \
  --key-id structure-two-v0.5-independent-custodian-01
```

## 2. 外部环境生成 fresh commitments

把登记公钥后的 DRAFT 和固定 source bundle 交给 custodian。custodian 在外部运行：

```bash
.venv/bin/python apps/evaluation_runner/generate_structure_two_fresh_seed_block_v0_5.py \
  --private-key-file /custodian/secret/ed25519-private-key.pem \
  --key-id structure-two-v0.5-independent-custodian-01 \
  --custodian-run-id structure-two-v0.5-fresh-seed-run-01 \
  --secret-output-dir /custodian/secret/structure-two-v0.5 \
  --public-output /custodian/public/structure_two_world_seed_block_attestation_v0_5.json
```

只把公开 attestation JSON 返回候选侧。不要返回 secret output directory。

## 3. 收到 attestation 后

将公开 JSON 放到 `configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_5.json`，然后依次执行：

```bash
.venv/bin/python apps/evaluation_runner/finalize_structure_two_world_manifest_v0_5.py
.venv/bin/python apps/evaluation_runner/run_structure_two_world_validation_gate_v0_5.py
```

若 Gate A 通过，再运行 unsigned trace producer。十臂 trace 必须在同一外部 custodian 环境逐臂重算、签名后返回，再运行 Gate B。

Gate A/B 通过后，可以比较透明代理和合理内部基线；只有 external fidelity gate 也通过，才允许把结果写成对官方完整 Active Dreaming、brainctl、O-STaR 等方法的比较。
