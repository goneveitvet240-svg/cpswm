"""Executable readiness ledger for 结构一's twelve routes.

`项目结构一` defines RQ1-RQ12 and the audit assigned each a judgement and a
gap.  Six of those gaps have since been closed with code and tests; six have
not, and two of the six that have not are module-sized subsystems (M05-M12
perception, M20-M22 query) that no amount of careful writing turns into an
implementation.

The failure mode this module exists to prevent is the one
``oam_phm_baselines`` already guards against in its `§9.1` registry:

    不可运行的也登记, 避免"没比过"被读成"比过并赢了".

The same asymmetry applies here.  A route with a contract and no runnable path
reads, in a progress summary, exactly like a route with both — unless something
refuses to let it.  :func:`assert_route_claim` is that refusal, and
:func:`verify_registry` is the second half: a declared status whose named
modules or tests do not exist on disk is itself a finding, so the registry is
checked against the tree rather than trusted.

Statuses, coarsest first.  The jump that matters is ``CONTRACT_ONLY`` →
``VERTICAL_SLICE``: below it nothing runs, and a route that has not crossed it
cannot support any empirical statement at all.

Nothing here infers a status from code existing.  A route with a full
implementation and no comparison against an outside baseline is
``INTEGRATED``, not ``VALIDATED``, and saying so is the point.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

__all__ = [
    "EMPIRICAL_CLAIM_THRESHOLD",
    "STRUCTURE_ONE_ROUTES",
    "STRUCTURE_ONE_ROUTES_VERSION",
    "RouteClaimError",
    "RouteEntry",
    "RouteStatus",
    "RouteVerificationError",
    "StructureOneRoute",
    "assert_route_claim",
    "readiness_report",
    "verify_registry",
]

STRUCTURE_ONE_ROUTES_VERSION = "structure-one-routes@0.1"


class StructureOneRoute(StrEnum):
    """RQ1-RQ12 of `项目结构一 §2`."""

    RQ1_SELECTIVE_OBSERVATION = "rq1_selective_observation"
    RQ2_INSTANCE_IDENTITY = "rq2_instance_identity"
    RQ3_SCENE_ATTRIBUTES_COMMONSENSE = "rq3_scene_attributes_commonsense"
    RQ4_MOBILITY_PROFILE = "rq4_mobility_profile"
    RQ5_LAYERED_PERSONAL_HABIT = "rq5_layered_personal_habit"
    RQ6_MULTI_LOCATION_TRANSITION = "rq6_multi_location_transition"
    RQ7_HIDDEN_EVENT = "rq7_hidden_event"
    RQ8_MULTI_PERSON_ATTRIBUTION = "rq8_multi_person_attribution"
    RQ9_NONSTATIONARY_REGIME = "rq9_nonstationary_regime"
    RQ10_HABIT_PREFERENCE_NORM = "rq10_habit_preference_norm"
    RQ11_LANGUAGE_QUERY = "rq11_language_query"
    RQ12_EMBODIED_LOOP = "rq12_embodied_loop"


class RouteStatus(StrEnum):
    """How far a route has actually got."""

    #: Nothing exists beyond the document.
    NOT_STARTED = "not_started"
    #: Types and validation exist; no code path runs end to end.
    CONTRACT_ONLY = "contract_only"
    #: A narrow path runs and is tested, on synthetic input.
    VERTICAL_SLICE = "vertical_slice"
    #: Wired into the project-one evaluation path, not just its own tests.
    INTEGRATED = "integrated"
    #: Compared against an outside baseline under matched conditions.
    VALIDATED = "validated"


_ORDER: tuple[RouteStatus, ...] = (
    RouteStatus.NOT_STARTED,
    RouteStatus.CONTRACT_ONLY,
    RouteStatus.VERTICAL_SLICE,
    RouteStatus.INTEGRATED,
    RouteStatus.VALIDATED,
)

#: The lowest status from which any empirical statement may be made.  Below it
#: a route has no numbers, so a sentence containing one is about something
#: else.
EMPIRICAL_CLAIM_THRESHOLD = RouteStatus.VERTICAL_SLICE


class RouteClaimError(RuntimeError):
    """Raised when a claim exceeds a route's declared status."""


class RouteVerificationError(RuntimeError):
    """Raised when a declared status is not backed by the files it names."""


@dataclass(frozen=True, slots=True)
class RouteEntry:
    """One route: where it stands, what is missing, and what would move it."""

    route: StructureOneRoute
    title: str
    audit_judgement: str
    status: RouteStatus
    remaining_gap: str
    #: What has to be true for the *next* status.  Written as a test or an
    #: experiment, never as "finish the module".
    next_gate: str
    modules: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.remaining_gap.strip():
            raise ValueError("a route entry needs a title and a gap statement")
        if not self.next_gate.strip():
            raise ValueError("a route entry needs a gate that would advance it")
        if self.status is not RouteStatus.NOT_STARTED and not self.modules:
            raise ValueError(f"{self.route.value} claims {self.status.value} but names no module")
        if _rank(self.status) >= _rank(RouteStatus.VERTICAL_SLICE) and not self.tests:
            raise ValueError(
                f"{self.route.value} claims {self.status.value} but names no test; "
                "a runnable path with no test is a contract with extra steps"
            )

    @property
    def supports_empirical_claim(self) -> bool:
        return _rank(self.status) >= _rank(EMPIRICAL_CLAIM_THRESHOLD)

    def payload(self) -> dict[str, object]:
        return {
            "route": self.route.value,
            "title": self.title,
            "audit_judgement": self.audit_judgement,
            "status": self.status.value,
            "remaining_gap": self.remaining_gap,
            "next_gate": self.next_gate,
            "modules": list(self.modules),
            "tests": list(self.tests),
            "supports_empirical_claim": self.supports_empirical_claim,
            "note": self.note,
        }


def _rank(status: RouteStatus) -> int:
    return _ORDER.index(status)


#: The registry.  Every status here was set from what is on disk at the time of
#: writing, and :func:`verify_registry` re-checks the file half of that.
STRUCTURE_ONE_ROUTES: Mapping[StructureOneRoute, RouteEntry] = {
    entry.route: entry
    for entry in (
        RouteEntry(
            route=StructureOneRoute.RQ1_SELECTIVE_OBSERVATION,
            title="长期选择性观察",
            audit_judgement="路线正确",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "机会/倾向/遮挡/缺失机制已统一为一个契约并有测试; "
                "但没有任何真实运行声明过 MAR 的协变量集合, "
                "所以 IPW 目前只在合成流上是有意义的"
            ),
            next_gate=(
                "让 project-one 的数据管线为每条 habit 更新产出一个 "
                "ObservationMechanismEnvelope, 并在报告里打印 correction_validity 分布"
            ),
            modules=(
                "cpswm.contracts.observation_mechanism",
                "cpswm.contracts.habit_learning",
                "cpswm.world_model.habits_transitions.propensity_correction",
            ),
            tests=(
                "tests/test_observation_mechanism.py",
                "tests/test_ws4_propensity_correction.py",
            ),
            note="MNAR 是任务驱动机器人的默认情形; 契约要求它被声明而不是被纠正掉. ",
        ),
        RouteEntry(
            route=StructureOneRoute.RQ2_INSTANCE_IDENTITY,
            title="跨天实例身份",
            audit_judgement="必要, 已有受限纵切",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "learned metric + Bayesian association 已保留 unknown_object、"
                "拒绝未来证据并有测试; "
                "但没有真实 tracker 到 world entity 的 merge / split / undo 谱系, "
                "模型权重和跨天真实标定也尚未产生"
            ),
            next_gate=(
                "实现一层显式 identity resolution: perception track id -> world entity id, "
                "带 merge/split/retract 与谱系; "
                "OAM-PHM WP0 §5 已记下这个迁移点"
            ),
            modules=(
                "cpswm.system.structure_one_identity_commonsense",
                "cpswm.world_model.grounded_search.identity_verification",
            ),
            tests=("tests/test_structure_one_selected_routes.py",),
            note=(
                "F0 固定样例里 gt_entity_id 与 object_instance_id 共用一个 UUID 命名空间, "
                "真实感知接入后这个相等比较会失效. "
            ),
        ),
        RouteEntry(
            route=StructureOneRoute.RQ3_SCENE_ATTRIBUTES_COMMONSENSE,
            title="场景图, 物体属性与常识",
            audit_judgement="框架合理, 接口与参考融合器已实现",
            status=RouteStatus.CONTRACT_ONLY,
            remaining_gap=(
                "已有 provenance-weighted hybrid provider, 但没有独立行为测试、真实 KG/VLM/LLM "
                "source adapter、属性模型或 project-one 侧 split-bound prediction cache"
            ),
            next_gate=(
                "为 P_common 提供一个带 model_version 与 split-bound cache 的 provider 接口, "
                "并让 LayeredHabitPosterior 的 common_prior 只能来自它"
            ),
            modules=("cpswm.system.structure_one_identity_commonsense",),
            tests=(),
            note=(
                "LayeredHabitPosterior 已经为这一层留好了插座: common_prior 是它唯一的外部输入. "
            ),
        ),
        RouteEntry(
            route=StructureOneRoute.RQ4_MOBILITY_PROFILE,
            title="七类移动性画像",
            audit_judgement="研究动机合理, 形式有问题",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "阈值是声明的, 不是学出来的; "
                "七类的投影在合成流上分得开, 未在任何真实或仿真轨迹上验证过"
            ),
            next_gate=(
                "在 D1 轨迹上跑一次投影, 报告 resolution 分布: "
                "若 AMBIGUOUS 占比过高, 说明轴选得不够, 而不是阈值调得不好"
            ),
            modules=(
                "cpswm.world_model.habits_transitions.mobility_axes",
                "cpswm.world_model.habits_transitions.mobility_profile",
            ),
            tests=("tests/test_mobility_axes.py", "tests/test_ws4_mobility_profile.py"),
            note="七类不互斥, 所以表示是轴, 名字是投影; 歧义被报告而不是被隐藏. ",
        ),
        RouteEntry(
            route=StructureOneRoute.RQ5_LAYERED_PERSONAL_HABIT,
            title="分层个性化习惯",
            audit_judgement="路线正确",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "back-off 估计器已实现且证据重复度为 1; "
                "但 project-one 的决策链仍在用 additive 的 "
                "HierarchicalDirichletHabitModel (重复度 3.0) , 两者尚未做对照"
            ),
            next_gate=(
                "把 LayeredHabitPosterior 作为第八个 arm 接入 tune_project_one, "
                "在同一 300 条流上比较 NLL / Brier / ECE 与变化确认率"
            ),
            modules=("cpswm.world_model.habits_transitions.layered_habit_posterior",),
            tests=("tests/test_layered_habit_posterior.py",),
            note=(
                "文档 §4.2 的乘法公式已被证明与实现不符且会重复计数; "
                "正确形式是偏差 (似然比) 相乘, 或等价地 leave-one-out back-off. "
            ),
        ),
        RouteEntry(
            route=StructureOneRoute.RQ6_MULTI_LOCATION_TRANSITION,
            title="多位置与转移",
            audit_judgement="正确",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "停留时间, 活动条件, 开放位置质量, 未决状态四项已实现; "
                "但没有任何下游决策消费它们——"
                "转移矩阵仍未进入 planner, 开放位置质量仍未进入搜索排序"
            ),
            next_gate=(
                "让 put-back / search 的读出消费 per-context 转移矩阵, "
                "并在开放位置质量高时触发 unresolved 而不是强行 argmax"
            ),
            modules=("cpswm.world_model.habits_transitions.mobility_axes",),
            tests=("tests/test_mobility_axes.py",),
            note="contexts_disagree 为真时, 池化转移矩阵描述的是一个从不发生的平均行为. ",
        ),
        RouteEntry(
            route=StructureOneRoute.RQ7_HIDDEN_EVENT,
            title="隐藏事件",
            audit_judgement="正确, 主要由结构二承担",
            status=RouteStatus.CONTRACT_ONLY,
            remaining_gap=(
                "CHEH/ORRER 的输出目前只经 ProjectOneStatRequest 影响项目一的统计, "
                "而 ProjectOneDatasetRecord 里没有任何 inferred-event 通道; "
                "所以隐藏事件仍是旁路实验, 不是结构一的正式输入"
            ),
            next_gate=(
                "为 HabitEvidenceSource.INFERRED_EVENT 建立一条到 project-one 决策链的"
                "受限通道: 可以降权进入, 但不得与 DIRECT_OBSERVATION 同权, "
                "并且必须携带产生它的假设集合而不是 top-1"
            ),
            modules=(
                "cpswm.system.counterfactual_event_hypergraph",
                "cpswm.system.continual.project_one_feedback",
            ),
            tests=(),
            note=(
                "matched AMG 在 D0 上同样拿到 1.0, "
                "所以在这条通道建立之前, CHEH 的创新收益无法在结构一侧被观测到. "
            ),
        ),
        RouteEntry(
            route=StructureOneRoute.RQ8_MULTI_PERSON_ATTRIBUTION,
            title="多人物归因",
            audit_judgement="核心路线正确",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "actor 通道已建立且遮蔽是结构性的; "
                "但默认策略仍是 LEGACY_HARD_ACTOR, "
                "所有已发表的 v0.3 读数都是在链式臂持有人物真值, "
                "三个基线不持有的条件下取得的"
            ),
            next_gate=(
                "在 ABSENT / CONTROLLED_NOISE 两种策略下重跑 300 条流的多 seed 对照, "
                "并把 policy 写进报告; 差值就是人物信息值多少"
            ),
            modules=("cpswm.system.evaluation_operations.project_one_actor_evidence",),
            tests=("tests/test_project_one_actor_truth_isolation.py",),
            note=(
                "实测: 在十个场景族上置换 actor 标签会改变 223/234 = 95.3% 的事件预测, "
                "gradual_drift 上有 12/24 次决策翻转. "
            ),
        ),
        RouteEntry(
            route=StructureOneRoute.RQ9_NONSTATIONARY_REGIME,
            title="非平稳阶段",
            audit_judgement="正确",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "权限矩阵与晋升门已实现, 但尚未接入 AutomaticCFBOCPDCCRRRouter; "
                "'补强公平基线'的另一半——匹配权限的基线——只有检查函数, 没有基线"
            ),
            next_gate=(
                "让 router 通过 OperatorAuthorityLedger 记账, "
                "并在四臂对照里对每个臂声明 AuthorityProfile"
            ),
            modules=(
                "cpswm.system.continual.operator_authority",
                "cpswm.system.continual.project_one_regime_loop",
            ),
            tests=("tests/test_operator_authority.py",),
            note="CF-BOCPD 只能提出候选; RGRC 是唯一的长期写入者, 且必须先晋升. ",
        ),
        RouteEntry(
            route=StructureOneRoute.RQ10_HABIT_PREFERENCE_NORM,
            title="行为/偏好/规范",
            audit_judgement="分层思想很好, 但未实现",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "审核判断已过期: 独立 schema, 冲突规则, 授权来源三项此前已实现, "
                "更新策略本轮补上; "
                "真正剩下的是没有任何评测端点测量'行为/偏好/规范区分准确性' (§15.3) "
            ),
            next_gate=(
                "构造一组偏好与习惯冲突的情境, "
                "测 find 与 put-back 两个意图是否给出不同答案——"
                "这正是 §9 '最可能在哪里找到 ≠ 应该放回哪里' 的可证伪形式"
            ),
            modules=(
                "cpswm.contracts.placement_memory",
                "cpswm.world_model.placement_decision.resolver",
                "cpswm.world_model.placement_decision.update_policy",
            ),
            tests=(
                "tests/test_placement_memory_separation.py",
                "tests/test_placement_update_policy.py",
            ),
            note="偏好永远不能撤销一条硬规范; 它只能与之共存并由 resolver 裁决. ",
        ),
        RouteEntry(
            route=StructureOneRoute.RQ11_LANGUAGE_QUERY,
            title="自然语言查询",
            audit_judgement="作为下游接口合理",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap=(
                "确定性 M21 baseline 已能弃答, constrained-LLM adapter 只允许目录内结构化查询; "
                "但真实 provider、三类查询准确率、unknown/unanswerable 校准与引用完整性尚未验证"
            ),
            next_gate=(
                "定义三类查询 (历史事实 / 习惯分布 / 下一位置预测) 各自的可回答条件, "
                "并让不可回答返回 unresolved 而不是最可能项"
            ),
            modules=(
                "cpswm.contracts.llm_roles",
                "cpswm.system.llm_evidence",
                "cpswm.system.m21_query_compiler",
                "cpswm.system.structure_one_learning_backends",
            ),
            tests=("tests/test_structure_one_certified_runtime.py",),
            note="结构三的 stop/拒答已有先例, 可以直接复用它的 episode contract. ",
        ),
        RouteEntry(
            route=StructureOneRoute.RQ12_EMBODIED_LOOP,
            title="具身闭环",
            audit_judgement="必须保留",
            status=RouteStatus.CONTRACT_ONLY,
            remaining_gap=(
                "action regret 与搜索成本在 SHIFT 死亡测试里有实现, "
                "但误放成本, 隐私打扰与执行反馈写回三项没有端点; "
                "而 SHIFT v5 的结论正是没有 detector 打得过 never-act"
            ),
            next_gate=(
                "把误放成本与打扰次数加入 balanced regret, "
                "并加入能测量可逆性的端点 (增量修订代价, 错误恢复延迟, "
                "污染—恢复联合前沿) ——"
                "当前端点是单点 argmax, 对更丰富的后验不敏感"
            ),
            modules=(
                "cpswm.system.evaluation_operations.project_one_shift_action_death_test",
                "cpswm.world_model.grounded_search.execution_feedback",
            ),
            tests=(),
            note=("这是项目一与项目二共同的根因: 方法优势在表示层, 端点在行动层的单点 argmax. "),
        ),
    )
}


def assert_route_claim(
    route: StructureOneRoute,
    claimed_status: RouteStatus,
    *,
    registry: Mapping[StructureOneRoute, RouteEntry] | None = None,
) -> None:
    """Refuse a claim stronger than the route's declared status."""

    entries = registry or STRUCTURE_ONE_ROUTES
    entry = entries.get(route)
    if entry is None:
        raise RouteClaimError(f"{route.value} is not registered")
    if _rank(claimed_status) > _rank(entry.status):
        raise RouteClaimError(
            f"{route.value} is {entry.status.value}, so it cannot be claimed as "
            f"{claimed_status.value}; remaining gap: {entry.remaining_gap}"
        )


def assert_empirical_claim(
    route: StructureOneRoute,
    *,
    registry: Mapping[StructureOneRoute, RouteEntry] | None = None,
) -> None:
    """Refuse a number from a route that has nothing that runs."""

    entries = registry or STRUCTURE_ONE_ROUTES
    entry = entries.get(route)
    if entry is None:
        raise RouteClaimError(f"{route.value} is not registered")
    if not entry.supports_empirical_claim:
        raise RouteClaimError(
            f"{route.value} is {entry.status.value}; no empirical statement can come from it. "
            f"Next gate: {entry.next_gate}"
        )


def verify_registry(
    *,
    repository_root: Path | None = None,
    registry: Mapping[StructureOneRoute, RouteEntry] | None = None,
) -> tuple[str, ...]:
    """Check every declared status against the files it names.

    Returns the problems found rather than raising, because the useful output
    is the whole list: one stale entry is a typo, several is a registry that
    has stopped tracking the tree.
    """

    entries = registry or STRUCTURE_ONE_ROUTES
    root = repository_root or _repository_root()
    problems: list[str] = []
    for entry in entries.values():
        for module in entry.modules:
            if importlib.util.find_spec(module) is None:
                problems.append(
                    f"{entry.route.value} names module {module!r}, which cannot be imported"
                )
        for test in entry.tests:
            if not (root / test).exists():
                problems.append(f"{entry.route.value} names test {test!r}, which does not exist")
    return tuple(problems)


def readiness_report(
    *,
    registry: Mapping[StructureOneRoute, RouteEntry] | None = None,
) -> dict[str, object]:
    """A summary that leads with what is missing rather than what is done."""

    entries = registry or STRUCTURE_ONE_ROUTES
    counts: dict[str, int] = {status.value: 0 for status in RouteStatus}
    for entry in entries.values():
        counts[entry.status.value] += 1
    blocking = tuple(
        entry.route.value for entry in entries.values() if not entry.supports_empirical_claim
    )
    return {
        "registry_version": STRUCTURE_ONE_ROUTES_VERSION,
        "route_count": len(entries),
        "status_counts": counts,
        "routes_that_cannot_support_a_number": list(blocking),
        "empirical_claim_threshold": EMPIRICAL_CLAIM_THRESHOLD.value,
        "routes": [entry.payload() for entry in entries.values()],
    }


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]
