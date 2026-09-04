# 结构二：Gate B "0.0 分歧率" 归因（2026-09-04）

协议：`structure-two-world-arm-distinguishability-gate-b@0.5`
被查产物：`benchmarks/structure_two/structure_two_world_dual_gate_authorization_v0_5.json`
证据等级：**D0 合成开发证据**
复现：`apps/evaluation_runner/diagnose_gate_b_zero_disagreement_2026_09_04.py`

---

## 0. 一句话结论

`active_dreaming_matched` 与 `brainctl_matched` 的分歧率为 `0.0`，**不是因为两条臂相同，
也不是因为它们在这个世界里无法被分开**，而是因为 Gate B 记录的读出 token
把臂之间的差别几乎全部丢掉了。

在被抽样的 24 条轨迹里这两条臂有 **6 次记忆决策不同**，签名轨迹在全部 24 372 步上
**0 个 token 不同**。六条邻居臂在 `predict()` 真正算出的行动分布上平均相差
**TV 0.05–0.25**（71–97% 的步上非零），Gate B 的 argmax 读出记录到 **0**。

**b1 与 b2 的近端原因同为读出。** 45 个臂对里有 10 对低于 b2 阈值，
而这 10 对**恰好是"从不做物理验证"的那五条臂之间的全部 $\binom{5}{2}$ 对**。

需要说清楚的一点：**"读出丢掉了差别"是机制陈述，不自动等于"读出错了"。**
Gate B 的判据字面上问的是"两条臂的预测是否相同"，而在当前读出定义下它们确实相同，
所以 Gate B 没有算错。要不要改读出，取决于结构二的主张是关于**行动**还是关于**信念**——
见 §6。本文档只负责把因果定死，不替这个选择下结论。

---

## 1. Gate B 记录的是什么

`structure_two_world_arm_adapter_v0_4.py:578-583` 每步发出一个字符串：

```python
f"verify={verification_executed}|{prediction.put_back}>{prediction.search_order[0]}"
```

`run_gate_b` 对这些字符串做逐位比较。一条臂在 Gate B 眼里只有三个符号：
verify 位、put_back、search_order[0]。

### 缺陷 D3 —— token 的两半在七条臂上是同一个值

`structure_two_fresh_triarm.py:166-167`：

```python
def _argmax_distribution(values): return _rank_distribution(values)[0]
```

而 `_NeighborMemoryState.predict()` 用**同一个 `distribution`** 构造二者，
于是 `put_back ≡ search_order[0]`，是恒等式，不是巧合。实测（1 条轨迹 326 步）：

| 臂 | `put_back == search_order[0]` | |
|---|---:|---|
| active_dreaming / brainctl / auto_dreamer / trustmem / care_no_action_regret / care_wm / sequential_no_consolidation | 326/326 | **恒等，token 右半是左半的副本** |
| corrected_amg | 217/326 | 两个真正不同的量 |
| o_star_matched | 280/326 | 同上 |
| full_rerun | 67/326 | 同上 |

`_CountMethod` 系（`project_two_action_benchmark.py:285`、`:363`）用
`search_first = self.last or put_back`（最后一次观测位置），所以那三条臂的 token
携带两个独立量；邻居系携带一个。
**同一个可区分性门里，token 的信息容量按臂族不同——这是可区分性门最不该有的性质。**

### 签名轨迹的全局形态（72 条轨迹，24 372 步）

| 臂 | `verify=1` 步数 | `put_back≠search[0]` 步数 | 不同 token 数 |
|---|---:|---:|---:|
| active_dreaming_matched | 0 | 0 | 116 |
| brainctl_matched | 0 | 0 | 116 |
| auto_dreamer_matched | 0 | 0 | 116 |
| trustmem_matched | 0 | 0 | 116 |
| care_no_action_regret | 0 | 0 | 116 |
| sequential_no_consolidation | 0 | 0 | 116 |
| care_wm | 288 | 0 | 158 |
| corrected_amg | 0 | 7 907 | 1 017 |
| o_star_matched | 0 | 5 336 | 797 |
| full_rerun | 0 | 17 990 | 560 |

六条臂在 24 372 步上从不 verify、从不预测变化，各自只有 116 个不同 token。

---

## 2. 缺陷 D2 —— 记忆决策进得去信念，进不去读出

### 受控消融（同一条臂，blend 权重固定 0.28，4 条轨迹 1 304 步）

强制改写 `choose_neighbor_decision` 的返回动作，其余一切不变：

| 对比 | 行动分布平均 TV | TV>1e-9 的步 | **argmax 不同的步** |
|---|---:|---:|---:|
| 原臂 vs 强制 ESCROW | 0.000000 | 0/1 304 | 0 |
| 原臂 vs 强制 PROMOTE | 0.081806 | 928/1 304 | **0** |
| 强制 ESCROW vs 强制 PROMOTE | 0.081806 | 928/1 304 | **0** |

把记忆决策从 escrow 翻成 promote，**71% 的步上行动分布被改动、平均 TV 0.082，
top-1 一次都没变。** 这就是 b2 失败的机制。

### 跨臂（6 条轨迹 1 956 步）

| 臂对 | 平均 TV | TV>1e-9 | argmax 不同 | **token 不同** | top-3 读出 | top-4@2dp 读出 |
|---|---:|---:|---:|---:|---:|---:|
| auto_dreamer / trustmem | 0.253704 | 1 894 | 0 | **0** | 0.7761 | 0.9479 |
| trustmem / care_no_action_regret | 0.222742 | 1 792 | 0 | **0** | 0.7802 | 0.9131 |
| active_dreaming / trustmem | 0.219886 | 1 869 | 0 | **0** | 0.7689 | 0.9346 |
| active_dreaming / auto_dreamer | 0.115037 | 1 391 | 0 | **0** | 0.2265 | 0.4688 |
| active_dreaming / care_no_action_regret | 0.088686 | 1 439 | 0 | **0** | 0.2362 | 0.4893 |
| auto_dreamer / care_no_action_regret | 0.055624 | 1 458 | 0 | **0** | 0.0925 | 0.4637 |
| active_dreaming / brainctl | 0.000000 | 0 | 0 | 0 | 0.0000 | 0.0000 |

同一批运行的记忆决策计数（每条轨迹前 2 步走早退分支，记为 `none`）：

| 臂 | 参数 | 决策 |
|---|---:|---|
| active_dreaming_matched | 0.60 | escrow 1 942 |
| brainctl_matched | 0.75 | escrow 1 942 |
| auto_dreamer_matched | 0.04 | promote 1 942 |
| trustmem_matched | 0.80 | promote 222 / escrow 1 720 |
| care_no_action_regret | 0.85 | promote 1 729 / escrow 213 |
| care_wm | 1.25 | promote 1 918 / physically_verify 24 |

`auto_dreamer` 与 `active_dreaming` **每一步的记忆决策都相反**（全 promote vs 全 escrow），
token 差 0。

### 机制

决策进入 `predict()` 的唯一通道是 `self._ledger.active_distribution`
（`structure_two_strongest_neighbor_gate.py:815-834` 的 0.28 权重混合）。
`ReversibleParticleConsolidationLedger`（`structure_two_sequential_gate.py:495-540`）里
只有 `promote` / `corrected_revision` 会写 `active_distribution`；
`escrow()`（同文件 `:580-591`）只追加一条记录，**不碰 `active_distribution`**。
于是 escrow 对预测是空操作，promote 只把当前分布朝一份陈旧分布拉 0.28——
足以改动分布，不足以翻转 argmax。

---

## 3. 缺陷 D1 —— b1 也是读出缺陷，不是"两条臂相同"

`active_dreaming_matched`（参数 0.60，score 落在 0.2186–0.5659）与
`brainctl_matched`（参数 0.75，score 落在 0.4562–0.5131）在多数步上都 escrow，
但**不是全部**：

| 轨迹区间 | 步数 | active_dreaming | brainctl | 决策不同 | 签名轨迹 token 不同 |
|---|---:|---|---|---:|---:|
| 0–18 | 6 078 | escrow 6 025 / promote 4 | escrow 6 029 | **4** | 0 |
| 36–42 | 2 064 | escrow 2 043 / promote 2 | escrow 2 045 | **2** | 0 |
| 合计（24/72 条轨迹） | 8 142 | promote 6 | promote 0 | **6** | **0** |

两条臂在采样到的 24 条轨迹里有 6 次做了相反的记忆决策，b1 判据
（"没有两条臂给出完全相同的预测"）仍然判它们完全相同。
**b1 的失败不能靠调臂参数修，它和 b2 是同一个读出缺陷。**

---

## 4. 唯一越过 b2 阈值的差异来自真值读取

失败的 10 个臂对**恰好等于**下面这五条臂之间的全部 $\binom{5}{2}=10$ 对：

> `active_dreaming_matched`、`auto_dreamer_matched`、`brainctl_matched`、
> `care_no_action_regret`、`trustmem_matched`

这五条正是**从不返回 `physically_verify`** 的臂。`care_wm` 是唯一会验证的邻居臂，
它对任何其他臂的最小分歧率是 `0.011817`，而

$$\frac{288}{24\,372}=0.011817$$

——**恰好等于它的物理验证次数占比**。也就是说 care_wm 越过 0.01 阈值的全部余量，
就是那 288 次验证，其他步一步都没贡献。

而 VERIFY 分支走 `_physical_verification_distribution`，该函数读
`truth.true_owner_habit_location`（`structure_two_strongest_neighbor_gate.py:729-730`；
在动作选择之后读，receipt 里已声明）。

**当前 Gate B 里唯一越过 b2 阈值的臂间差异，其来源是一次真值读取。**

---

## 5. 撤回

2026-09-04 对话中我给出过下面三条判断，**现予撤回**：

1. ~~"Gate B 的 b1/b2 失败与任务 8 的 $H\perp C$-given-support 是同一个事实从两头看"~~
   —— 两者是不同代码路径、不同问题。b1/b2 有本地的、已证明的近端原因（escrow 空操作 ＋
   argmax 读出），与支撑型耦合无关。这条桥接没有依据。
2. ~~"这个世界只能分辨『重算 vs 不重算』"~~ —— 准确的说法是：**观测到的 1e-4 级 token
   分歧率不能作为"世界分辨力不足"的证据**，因为读出之前臂的输出已相差 TV 0.05–0.25。
   （注意：臂之间信念不同不等于世界能分辨谁更好——两条臂可以差得很远而同样错。
   本次工作没有测量后者。）
3. ~~"Gate B 现在不可能靠改方法过"~~ —— 前提不成立，结论待定，见 §6。

当时 Task 8 v0.1 的结论（精确后验上 I-投影因子化臂 TV=0.0000）不受该 Gate B
调查影响；但它后来已被 Task 8 v0.2 的 full-support relative-probability coupling 取代，
不得再作为当前 Task 8 结论引用。

---

## 6. 修哪里：先决定 Gate B 是什么门

读出模拟（6 条轨迹，六条邻居臂 15 对，b2 阈值 0.01）：

| 读出 | 低于阈值的臂对 |
|---|---:|
| 仅 argmax | **15 / 15** |
| top-3 排序 | 1 / 15 |
| top-4 带两位小数概率 | 1 / 15 |

唯一在三种读出下都不过的是 `active_dreaming / brainctl`（6 条轨迹上恰好都全 escrow）；
§3 显示扩大轨迹范围后这一对也会分开。

但**"加宽读出"不是自动正确的修法**，先要回答一个问题：

- **若结构二的主张是关于行动质量**（put_back / search_order 是行动端点），
  那么"24 372 步里 top-1 放回位置从不依赖记忆策略"就是诚实的判决——
  **任务在行动层面是平凡的**，该修的是世界/任务，让记忆策略能改变 top-1 行动
  （引入代价结构、或制造 top-1 会翻转的状态），而不是让读出去看更细的小数位。
- **若主张是关于信念/巩固质量**，那么读出必须记录信念（排序或量化分布），
  当前 token 是错的仪器。

两条路都要求把 b2 的**实质性下限**预注册（例如"臂对行动分布 TV 的中位数 ≥ δ"），
否则"记录更多位"会让 b2 变成可以用浮点噪声通过的空判据。

### 三项与上述选择无关、无论如何都该修的缺陷

1. `escrow()` 不写 `active_distribution`，使 escrow 对预测成为空操作——
   要么让它有语义，要么在文档里写明"全 escrow 的臂在读出上等价于无记忆基线"。
2. `put_back ≡ search_order[0]`（七条臂）而另三条臂不是——
   同一门内 token 信息容量按臂族不同。
3. `care_wm` 的可区分性余量恰好等于其真值读取次数（§4），应在 Gate B 报告里显式标注。

---

## 7. 复现与局限

**复现**：`apps/evaluation_runner/diagnose_gate_b_zero_disagreement_2026_09_04.py`。
`--sections A` 重建 v0.5 世界（分布与三组种子逐字取自冻结 manifest），
断言 `rollout_id[0]` 与签名轨迹一致，并核到 **652/652 token 与签名轨迹逐位相同**，
证明探针与产出轨迹走的是同一条生产路径。B/C/D/E 对应 §1/§2/§2/§3。

在 Linux 侧运行（仓库 `.venv` 指向 macOS 解释器）：

```bash
uv run --no-project --python 3.13 \
  --with pydantic --with numpy --with cryptography --with scipy --with scikit-learn \
  python apps/evaluation_runner/diagnose_gate_b_zero_disagreement_2026_09_04.py \
  --sections A,B,C,D --rollouts 6
```

**绕过的检查**：`load_frozen_validation_gate_design_v0_5` 的源码包摘要校验被绕过。
该校验**在本次工作之前就已失效**——冻结时记 245 个文件（238 个 `src/cpswm/**/*.py`
＋ 7 个 app），当前 HEAD 已有 255 个 `src/cpswm` 文件，工作区 257 个；
`structure_two_world_seed_attestation_v0_5.py:80-87` 的 docstring 自己就写明
"原始 245 行清单未持久化，冻结摘要无法在今天的源码树上重算"。
**这意味着 v0.5 Gate B 报告在当前树上已不可重算验证**，是一条独立的、
先于本次调查存在的问题，应单列跟踪。

**局限**：
- §2 的分布级数字来自 4–6 条轨迹（1 304 / 1 956 步），非全部 72 条；
  签名轨迹给出的全量 token 级数字与之一致（active_dreaming vs brainctl = 0/24 372，
  其余邻居臂对 1.2e-4 – 4.1e-4）。
- §3 的决策分歧计数覆盖 24/72 条轨迹、8 142 步；全量计数未跑。
- §6 的读出模拟基于 6 条轨迹；分离幅度（0.05–0.95）远高于阈值 0.01，
  子集噪声不足以翻转结论，但数字本身应视作估计。
- §6 的"仅 argmax = 15/15"与签名轨迹的"45 对中 10 对失败"口径不同：
  前者只看 argmax、只含六条邻居臂；后者是含 verify 位的完整 token、十条臂。
  两者一致——care_wm 靠 verify 位（即真值读取）单独越线，见 §4。
- 探针自查：每条轨迹的第 0、1 步走 `predict()` 的早退分支（belief/particles 未建立），
  此时未捕获到分布。该情形在**所有臂上完全相同**（144/24 372 = 0.59%），
  对任何跨臂比较贡献恒为 0。
