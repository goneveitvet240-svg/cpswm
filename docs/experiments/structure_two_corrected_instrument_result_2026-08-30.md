# 结构二校正评测仪器 v0.2 结果

日期：2026-08-30  
证据等级：D0 synthetic validation-only（D0 合成验证集，仅诊断）

## 结论先说

评测仪器修复成功，但本次方法比较无效，不能声称 CARE-WM 优于现有方法。

- instrument integrity（仪器完整性）：通过。
- comparison validity（比较有效性）：失败。
- v0.1 历史文件：保持原字节与原哈希，未被改写。
- sealed holdout（密封留出集）：未读取、未计分。

## 修复后读数

| 方法 | raw action regret/step（原始行动遗憾/步） | net environment regret/step（净环境遗憾/步） | search success（搜索成功率） |
|---|---:|---:|---:|
| corrected AMG | 0.138021 | 0.140799 | 0.904514 |
| BrainCTL matched | 0.147569 | 0.158342 | 0.904514 |
| CARE no-action-regret | 0.147569 | 0.153212 | 0.904514 |
| CARE-WM | 0.147569 | 0.239323 | 0.904514 |

修复 search readout（搜索读出）后，各主要方法的搜索成功率一致；原先由错误搜索排序制造的差距消失。CARE-WM 相对最强的合格总体对手 corrected AMG，净环境遗憾每步高 0.098524；相对最强已发表近邻 BrainCTL matched，高 0.080981。由于有效性门失败，这两个差值只能作为诊断，不能作为正式优劣结论。

## 有效性门为什么失败

- 已发表近邻平均成对行动分歧率为 0.006510，低于 0.01。
- 只有 16.67% 回合出现不止一种已发表近邻行动轨迹，低于 20%。
- Active Dreaming matched 与 BrainCTL matched 的整体验证集行动分歧率为 0。
- CARE-WM 在 48/48 回合都用满 4 次物理验证，共 192 次，预算饱和率 1.0，高于 0.95。

这说明当前 benchmark（基准）既难以区分部分强近邻，又让 CARE 的验证策略退化成“有预算就全部用完”。

## 成本边界修复

CARE-WM 内部出现 416 次 `retract` 和 416 次 `corrected_revision`。这些现在被正确记录为内部账本审计事件，不再冒充外部环境维修。当前回放没有 model-selected external execution receipts（模型选择的外部执行凭据），所以外部回滚数和环境维修成本都为 0。

## 可复核信息

- 报告：`artifacts/project_two_v04_development/structure_two_corrected_instrument_v0_2.json`
- 报告内容哈希：`7e4d2882f4bb3f278f8ff045c1387e56b71a697447653ac40898c767222411b7`
- 运行入口：`apps/evaluation_runner/run_structure_two_corrected_instrument.py`
- manifest：`configs/project_two_experiments/structure_two_corrected_instrument_manifest_v0_2.json`

