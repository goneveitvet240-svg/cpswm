# 结构二成本—护栏校准 v0.1（2026-09-06）

## 结论

本轮把行动读出 v0.6 的开发优势转成了可审计的 cost sensitivity envelope
（成本敏感性包络），并对 TRAIN 执行 Hybrid RGRC cache-versus-log replay
（混合可逆统计缓存对追加日志重放）检查。结果如下：

- 60 个 development holdout（开发留出）episode 中，Project Two 相对 matched AMG
  的搜索遗憾严格更好 36 次、打平 24 次、变差 0 次；
- 平均 normalized search-regret advantage（归一化搜索遗憾优势）为 `0.477778`/episode，
  95% paired bootstrap interval（配对自助区间）为 `[0.333333, 0.627778]`；
- 由逐例 `mean_search_path_length × step_count` 直接得到的实际容器检查次数优势为
  `1.433333` 次/episode，95% 区间为 `[1.000000, 1.883333]`；
- Project Two 平均多出 `0.233333` 个 owner-contamination event（主人污染事件）/episode，
  95% 区间为 `[0.133333, 0.350000]`；
- 检查次数口径的均值 break-even ratio（盈亏平衡比）为 `6.142857`：若一次额外污染
  事件的成本小于一次容器检查成本的 `6.142857` 倍，则在当前三项诊断成本模型下
  均值净优势仍为正；对应 bootstrap ratio 区间为 `[4.000000, 10.500000]`；
- 用检查次数优势区间下界除以污染区间上界得到的保守敏感性边界为 `2.857143`；
- 另保留 `2.047619` 作为“每个污染事件对应的 D0 归一化搜索遗憾单位”，不再把它
  误称为容器检查成本倍数；
- TRAIN 20/20 episode 的 Hybrid RGRC 缓存充分统计与日志重放在 `1e-10` 绝对容差内等价，
  最大差为 `7.105427357601002e-15`。

这仍然不是 paper-level pass（论文级通过）。真实机器人时间、能耗、安全、隐私、未找到目标、
放回失败等成本尚未测量，污染／恢复／优效界值也尚未由外部协议冻结。

## 成本关系

本轮只使用已经存在的逐 episode 配对结果，不重新运行 seeds `6001--6060`：

```text
AMG - ProjectTwo 净成本
= put_back_cost × put_back_advantage
+ inspection_cost × search_advantage
- contamination_event_cost × contamination_excess
```

当前数据中每个 episode 的 put-back regret（放回遗憾）和 recovery latency
（恢复时延）逐例相等，因此均值关系化简为：

```text
1.433333 × inspection_cost - 0.233333 × contamination_event_cost
```

正值表示 Project Two 成本更低。`6.142857` 是由现有开发数据推导的检查次数灵敏度边界，
不是替真实机器人选定的成本，也不是污染阈值。`2.857143` 只是把两个边际区间机械组合的
敏感性下界，并非正式的 simultaneous 95% confidence bound（同时 95% 置信界）。

## 完整重跑范围

本轮“完整重跑”等价只覆盖：

```text
Hybrid RGRC cached sufficient statistics
vs
the same Hybrid RGRC statistics rebuilt from its append-only log
```

它不覆盖整条 ORRER/PCHMP/CCRR/CIAV 行动轨迹，不验证行动分布完全等价，也没有独立托管。
缓存更新与日志重放的浮点运算次序不同，因此逐字节 hash 允许不同；判定依据是注册的
`1e-10` 绝对容差和逐位置最大差。本轮开发测量的最大差为约 `7.11e-15`。

## 证据与边界

- 源行动工件：
  `artifacts/project_two_v04_development/structure_two_action_benchmark_v0_6_dual_timescale_2026_09_06.json`
  - SHA-256：`2887a0281535b8eca0301e3ce5b3fecd1af194319b3afffcf455c26cbd2ba289`
- 校准工件：
  `artifacts/project_two_v04_development/structure_two_cost_guardrail_calibration_v0_1_2026_09_06.json`
  - SHA-256：`2481ff2cd745c0b3678da3f2ccf0dc70c88b4d889310ad817617af510afe5d9b`
- 配对 bootstrap：10,000 次，固定 seed
  `structure-two-cost-guardrail-calibration@0.1:paired-episode-bootstrap`。
- 本轮没有重新开启 development holdout；训练重放只用了 TRAIN seeds `1--20`。
- 工件由同一开发环境生成，没有 independent custody（独立托管）。

## 完成后的两轮对抗审核

第一轮攻击 forged positive and dependency trust chain（伪造正结论与依赖信任链），发现并修复：

1. 仅靠 report validator 可伪造逐例行并同步伪造派生包络；新增 dependency verifier，
   重新读取绑定的行动工件和数据配置、复算逐例行，并重新执行 TRAIN 重放；
2. 原构建器只比较 dataset version 和 TRAIN ID；现同时核对配置 SHA、配置路径、证据阶段、
   confirmatory 标志、三个 split 的 episode ID，以及 validation/test visible hash；
3. 源文件先解析、长时间重放后再读文件计算 hash 存在 TOCTOU 错绑；现对同一次读取的字节
   同时解析和哈希；
4. Hybrid 重放按 UUID 集合遍历，跨进程浮点累加顺序不稳定；现固定为追加日志顺序。

第二轮攻击 boundary, replay state and metric semantics（边界、重放状态与指标语义），发现并修复：

1. `0.477778` 是归一化遗憾而非检查次数；新增逐 episode 检查次数差，纠正检查成本边界为
   `6.142857`；
2. serialized receipt（序列化回执）可放宽 tolerance；现将开发容差锁为 `1e-10`；
3. 回执可遗漏未触及位置却仍为真；现逐 TRAIN episode 绑定完整 registered location catalogue
   （已登记位置目录）并要求精确覆盖；
4. `bool`、数字字符串和非有限数可经 Pydantic 强制转换进入数值字段；相关合同现使用 strict
   finite types（严格有限数类型）；
5. 搜索优势为非正时原逻辑会产生负的“最大允许成本”或验证失败；现闭合为 0，且不签发正
   break-even ratio。

两轮审核覆盖上述枚举攻击矩阵，不宣称穷尽未来攻击；依赖重算仍是同一开发环境内的
internal consistency（内部一致性），不能替代外部签名和独立托管。

## 仍未通过

1. 真实机器人放回失败、容器检查、未找到目标、时间、能耗、安全与隐私成本；
2. primary superiority margin（主效用优效界值）；
3. owner contamination upper bound（主人污染上界）；
4. recovery latency upper bound（恢复时延上界）；
5. confirmatory full-rerun tolerance（确认性完整重跑容差）以及整条行动轨迹等价；
6. D1--D4 外部有效性；
7. 六个外部强邻居的 faithful native reproduction（忠实原声复现）；
8. independent custody（独立托管）。

因此 `paper_claim_allowed=false` 保持不变。

## 验证

- 22 个直接相关测试文件、312 项测试：通过；
- 新增成本—护栏合同测试：13 项，覆盖内部一致伪造、依赖替换、容差放宽、位置遗漏、
  非有限数、`bool`/字符串数值冒充、非正优势边界及日志顺序复现；
- dependency verifier（依赖重验器）：通过，复算 60 个配对行并重新执行 20 个 TRAIN 重放；
- 两个独立 Python 进程生成的工件逐字节一致，SHA-256 均为
  `2481ff2cd745c0b3678da3f2ccf0dc70c88b4d889310ad817617af510afe5d9b`；
- 触及代码 Ruff 与 format：通过；
- 6 个核心 source 文件 strict mypy：通过；
- checkpoint JSON 解析与 `git diff --check`：通过。
