# 项目一评测协议 v0.3：多 seed 与首个 CONCLUSIVE 判决

日期：2026-08-24
状态：**`CONCLUSIVE`（合成基准）** —— 项目历史上第一次不是 `UNDERPOWERED`
性质：合成基准上的功效充足对照。**不构成外部有效性、真实具身效用或 B1 完成。**

---

## 0. 一句话

把每个场景族从 1 条确定性序列扩到 60 条 seeded 变体（测试流 5 → **300**）之后，
`full` 相对自己的两个消融首次拿到**功效充足且显著**的正向结果：
相对 `no_rls` 变化确认 **+0.100**（CI [+0.078, +0.123]，误切换代价为 0），
相对 `shuffled_rls` 配对间隔 **+0.043**（CI [+0.036, +0.051]）。
24 项对照中 SIG=13 / NULL=11 / **inconclusive=0**。

---

## 1. 改了什么

### 1.1 多 seed 场景层

十个场景族各自获得一个 **seeded 变体生成器**，抖动流长、变化点位置、扰动位置、
位置分配和观测质量；**确定性锚点原样保留**（`SCENARIO_VERSION @0.1`），
变体单独版本化（`@0.2`），所以多 seed 运行不会和单锚点运行被静默混同。

家族含义在每个 seed 下都不变，且由测试而非约定保证：

- `ZERO_CHANGE_POINT_FAMILIES`（stable / periodic / short_disturbance /
  context_change / missing_observations / biased_observation）在**任何 seed** 下
  都不得产生变化点——生成器内置断言，`build_randomized_scenario` 直接抛错；
- 变化点必须是其 regime 的**第一天**，且反过来，任何 regime 切换都必须被标记；
- 没有变化点可以落在 8 天暖机窗口内；
- `expected_location` 永远精确可算——扰动族里它停在 home，访客族里它停在主人的位置。

`tests/test_project_one_randomized_scenarios.py` 对 10 族 × 12 seed 逐一断言以上全部。

### 1.2 功效模块

`project_one_power.py`。两个决定承担了主要重量：

**重采样单元是 stream，不是事件。** 一条场景里的 20 个事件不是 20 次独立观测——
它们共享 regime、位置词表和变化点。按事件 bootstrap 会把区间缩小约 √L 倍，
把相关性制造成显著性。这与 SHIFT v5 绕了四轮才定下的单元一致。

**SD 先放大再使用。** `powered_sd = max(empirical_sd × 1.5, 0.05)`，
`required_pairs = ceil(7.849 × σ² / MDE²)`（双侧 α=0.05，power 0.8）。
该式复现了 SHIFT v5 报告的 `powered SD 0.072521 → required n = 17`，有测试钉住。

**三分judgment，而不是二分。** 早期版本只报 powered/underpowered，结果打印出
`need=290` 紧挨着一个明显排除 0 的区间，读者无法判断那是"发现了"还是"看不出"。现在分成：

| 结论 | 含义 |
|---|---|
| `significant` | 区间排除 0——检出了效应，无论设计为多大效应设计 |
| `null_result` | 功效充足且区间跨 0——**关于"不存在 ≥MDE 效应"的证据**，这是个发现 |
| `inconclusive` | 功效不足且区间跨 0——这项研究两头都答不了 |

整体判决只有在 `inconclusive` 为零时才是 `CONCLUSIVE`。让已答出的端点替全局背书，
正是欠功效研究被写成结论的方式。

### 1.3 多实体数据层

`project_one_household_generator.py`：多住户 × 多住民 × 多物体的**单条交织日志**，
每个 `(household, resident, object)` 三元组分配一个场景族与自己的 seed，
逐分桶真值仍然精确。默认 3×2×4 = 24 分桶 / 626 事件；5×4×8 = 160 分桶 / 3000+ 事件。

两个设计选择：

- **位置词表是声明的，不是观测的。** `stable_habit` 三元组只出现在一个位置，
  按自身记录推导候选集会得到一个成员、分桶不可评估。生成器随日志输出显式候选清单
  ——真实部署本来就走这条路——**把误报家族留在分母里**而不是悄悄丢掉。
- **seed 由三元组派生（sha256），不是计数器。** 同一家庭的两个物体不能共享抖动，
  否则日志看起来有很多实体，实际只携带一个自由度。首版曾用 `hash()`，
  而 CPython 对字符串哈希按进程加盐——那会让每次运行的日志都不同，
  而所有产物都还声称自己有 seed。已修，并有测试钉住。

### 1.4 一处语义修正：分桶键改用 `subject_id`

`bind_stream` 原先按 `(household, **actor**, object)` 分桶。多住民数据一接进来立刻暴露：
`biased_observation` 的访客日被切成了**独立分桶**，等于给访客凭空造出一个
"访客的杯子习惯"模型。

习惯属于 `subject_id`（谁的习惯），`actor_id` 是谁动的手。改为按 `subject_id` 分桶后：
访客事件留在主人的分桶内、被 `owner_mass` 正确降权——而这正是 WS6/RQ8
"避免同屋其他人污染主人的个体习惯"要研究的对象。按 actor 分桶会把这个问题从数据里删掉。

---

## 2. 结果：60 seed，300 条测试流

调参协议不变：每臂独立 12 点网格、只在 validation 选择、TEST 跑一次、
划分仍按**场景族**（validation 5 族 / test 5 族，seed 不跨划分）。

### 2.1 核心问题：RLS residual 通道值不值

| 对照 | 端点 | 差值（full − 对照） | 95% CI | 结论 |
|---|---|---:|---|---|
| **no_rls** | 变化确认↑ | **+0.1000** | [+0.0783, +0.1233] | **显著** |
| | 配对间隔↑ | **+0.0136** | [+0.0055, +0.0222] | **显著** |
| | 误切换↓ | +0.0000 | [0, 0] | null（**零代价**） |
| | 异常检出↑ | +0.0013 | [0, +0.0033] | null |
| **shuffled_rls** | 配对间隔↑ | **+0.0431** | [+0.0364, +0.0505] | **显著** |
| | 误切换↓ | **−0.0026** | [−0.0039, −0.0014] | **显著**（full 更少） |
| | 变化确认↑ | +0.0000 | [0, 0] | null |
| | 异常检出↑ | +0.0000 | [0, 0] | null |

两句话：

1. **相对 `no_rls`：残差通道多买到 10 个百分点的变化确认，误切换代价恰好为零。**
2. **相对 `shuffled_rls`：打乱配对会损失 0.043 的配对间隔并增加误切换。**
   也就是说残差携带的不只是量级，还有与当前事件的**配对信息**——
   这正是修复前（单 seed、legacy wiring）无法区分的那一条。

但同样要说清楚：**变化确认上 `full` 与 `shuffled_rls` 完全相同（差值精确为 0，CI 零宽）。**
残差的配对信息体现在间隔与误切换上，不体现在确认率上。

### 2.2 修复前 vs 修复后：sigmoid 修复把残差通道的符号翻了过来

同样 60 seed / 300 条流，`--calibration legacy_sigmoid` 复现修复前的 wiring：

| 端点 | legacy（修复前） | as_is（修复后） |
|---|---:|---:|
| full vs **no_rls**，配对间隔 | **−0.1001** CI[−0.1202, −0.0801] **显著更差** | **+0.0136** CI[+0.0055, +0.0222] **显著更好** |
| full vs **no_rls**，误切换 | **+0.0148** CI[+0.0110, +0.0188] **显著更差** | **0.0000** CI[0, 0] 零代价 |
| full vs **shuffled_rls**，配对间隔 | +0.0025 CI[+0.0004, +0.0047] | **+0.0431** CI[+0.0364, +0.0505]（**17×**） |

两条读数：

1. **修复前，加上 RLS residual 会让方法显著变差**——配对间隔 −0.100、误切换 +0.0148，
   都是功效充足的显著结果。不是"看不出收益"，是**有害**。
2. **修复前打乱残差只损失 0.0025 的间隔**，即"残差只是尺度信号"那一档；
   修复后是 0.0431，17 倍。配对信息在双重压缩下几乎被完全抹掉。

值得单独说明的是方法论意义：**同一个比较，在单 seed 下判 `UNDERPOWERED`（两边都答不了），
在 300 条流下两个方向都是决定性的。** 之前"无法判定 residual 有没有用"不是方法的性质，
是样本量的性质。

### 2.3 一条对 Dirichlet 通道不利的读数

`full` vs `rls_only` 的配对间隔差是 **+0.0001**（CI [+0.0001, +0.0001]）。
技术上显著，实质上是零：**在这批家族上，Dirichlet surprise 通道叠加在残差之上
几乎没有增量。** 四个端点里三个是精确的 0。这条应当写进论文的消融讨论，
而不是留在脚注里。

### 2.4 基线不是全输

| 对照 | 端点 | 差值 | 结论 |
|---|---|---:|---|
| categorical_bocpd | 异常检出↑ | **−0.0165** | 显著，**基线更好** |
| context_frequency | 异常检出↑ | **−0.0190** | 显著，**基线更好** |
| persistence | 误切换↓ | −0.2175 | 显著，full 远好（persistence 靠乱切换蒙确认率） |

**两个地板基线在异常检出上显著优于链式臂。** `full` 赢在配对间隔和变化确认，
输在异常检出。这不是可以略过的细节——协议 §7 早就单列了"查异常检出率只有 0.133
的原因"，现在有了功效支撑的证据说明这条缺口是真的。

---

## 3. 这个结论能走多远

**能说的**：在这套合成基准、这套家族划分、这套 MDE 下，
RLS residual 通道的贡献是真实的、方向为正的、功效充足的，且携带配对信息而非仅有量级。

**不能说的**：

1. **没有外部有效性。** 全部是合成流。真实数据轨只有绕过 B 层的短路版（见
   `real_data_adapters/`），M05–M12 感知层仍全部 absent。
2. **没有具身效用。** 这些端点是变化判断链的内部指标，不是搜索/放回/递送的行动收益。
   结构二的 D0 已经给出反面教训：修订质量提升没有转化成更好的放回选择。
3. **家族划分本身是一个假设。** validation 5 族与 test 5 族测的是不同能力，
   所以这是跨能力泛化的读数，不是同分布泛化的读数。换一种划分结论可能变。
4. **异常检出输给地板基线这件事没有解决。**
5. MDE 0.05 是沿用 SHIFT 护栏的选择，不是从效用推出来的。真实效用阈值应当另行确定。

---

## 4. 复现

```bash
PYTHONPATH=src .venv/bin/python apps/evaluation_runner/tune_project_one.py \
  --output artifacts/project_one/tuning_seed60_as_is \
  --budget 12 --calibration as_is --seeds 60
```

修复前对照（同样 60 seed）：

```bash
PYTHONPATH=src .venv/bin/python apps/evaluation_runner/tune_project_one.py \
  --output artifacts/project_one/tuning_seed60_legacy \
  --budget 12 --calibration legacy_sigmoid --seeds 60
```

多实体数据层：

```bash
PYTHONPATH=src .venv/bin/python apps/evaluation_runner/run_project_one_data_pilot.py \
  --generated --households 3 --residents 2 --objects 4 \
  --output artifacts/project_one/generated_pilot
```

`--seeds 0` 回到十个确定性锚点，与多 seed 之前的全部读数逐字节一致。

---

## 5. 下一步

1. **异常检出**：地板基线显著更好，先查清是指标定义问题还是链式臂的真实缺口。
2. **具身效用**：把这条链接到搜索/放回决策，看内部指标的改进能否转化成行动收益。
   结构二在这一步上已经失败过一次，不能假设它会自动成立。
3. **结构二同样需要多 seed**：D0 行动级死亡测试目前是 **2 个 validation + 2 个 test
   episode**，比项目一多 seed 之前还小一个量级。同一套 `project_one_power.py`
   可以直接复用。
4. **真实数据**：短路版（dataset → ProjectOneStream → 评测臂）今天可跑；
   完整版需要 M05 的 `ObservationEnvelope` 适配器，那是 B 层门，本轮没有触及。
