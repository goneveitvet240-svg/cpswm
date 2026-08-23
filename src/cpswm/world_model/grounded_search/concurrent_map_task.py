"""Scheme-B snapshot-isolated map/task coordination and constrained VOI.

Map updates and task execution run concurrently, but an action reads one
immutable belief snapshot.  A dual-graph dependency bridge identifies the
affected action suffix.  Learned relevance and VOI scores may expand/rank
candidates; hard dependencies and the exact Bayesian-risk verifier retain
authority.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import inf, isfinite
from typing import ClassVar, Protocol
from uuid import UUID, uuid4

from cpswm.system.continual.hybrid_statistics import NaturalRidgeResidual

_NIL_MAP_ID = UUID(int=0)


@dataclass(frozen=True, slots=True, order=True)
class BeliefNode:
    """One immutable map-belief graph node at a committed version."""

    node_id: str
    payload_hash: str
    uncertainty: float
    node_revision: int

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.payload_hash.strip():
            raise ValueError("node_id and payload_hash must be non-empty")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be in [0, 1]")
        if self.node_revision < 0:
            raise ValueError("node_revision must be non-negative")


@dataclass(frozen=True, slots=True)
class BeliefSnapshot:
    """Atomic immutable map-belief graph snapshot.

    ``snapshot_id`` is the *stable* identity of one committed map version: every
    read of the same version returns the same id, so ``DecisionContext`` can bind
    an exact snapshot rather than a fresh uuid per read.  ``map_id`` identifies the
    map lineage the version belongs to.
    """

    snapshot_id: UUID
    map_version: int
    nodes: tuple[BeliefNode, ...]
    content_hash: str
    map_id: UUID = _NIL_MAP_ID

    def __post_init__(self) -> None:
        if self.map_version < 0:
            raise ValueError("map_version must be non-negative")
        if self.nodes != tuple(sorted(self.nodes)):
            raise ValueError("belief snapshot nodes must be sorted")
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("belief snapshot node ids must be unique")
        if self.content_hash != self.compute_hash(self.map_version, self.nodes):
            raise ValueError("belief snapshot content hash mismatch")

    def node_map(self) -> dict[str, BeliefNode]:
        return {node.node_id: node for node in self.nodes}

    def changed_nodes(self, newer: BeliefSnapshot) -> frozenset[str]:
        old = self.node_map()
        new = newer.node_map()
        return frozenset(
            node_id
            for node_id in old.keys() | new.keys()
            if old.get(node_id) != new.get(node_id)
        )

    @staticmethod
    def compute_hash(map_version: int, nodes: tuple[BeliefNode, ...]) -> str:
        payload = {
            "map_version": map_version,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "payload_hash": node.payload_hash,
                    "uncertainty": repr(node.uncertainty),
                    "node_revision": node.node_revision,
                }
                for node in nodes
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class VersionedBeliefMap:
    """Thread-safe map writer that publishes only complete atomic snapshots."""

    def __init__(self, *, map_id: UUID | None = None) -> None:
        self._lock = threading.RLock()
        self._nodes: dict[str, BeliefNode] = {}
        self._version = 0
        self._map_id = map_id or uuid4()
        # One stable identity per committed version, minted at commit time.
        self._snapshot_id = uuid4()

    @property
    def map_id(self) -> UUID:
        return self._map_id

    def apply_update(
        self,
        changes: Mapping[str, tuple[str, float]],
        *,
        removals: Iterable[str] = (),
    ) -> BeliefSnapshot:
        """Commit all node changes as one map version; readers never see a partial batch."""

        with self._lock:
            next_nodes = dict(self._nodes)
            next_version = self._version + 1
            for node_id in removals:
                next_nodes.pop(node_id, None)
            for node_id, (payload_hash, uncertainty) in changes.items():
                previous = next_nodes.get(node_id)
                node_revision = 0 if previous is None else previous.node_revision + 1
                next_nodes[node_id] = BeliefNode(
                    node_id=node_id,
                    payload_hash=payload_hash,
                    uncertainty=float(uncertainty),
                    node_revision=node_revision,
                )
            self._nodes = next_nodes
            self._version = next_version
            # A new committed version gets a new stable identity, minted once.
            self._snapshot_id = uuid4()
            return self._snapshot_unlocked()

    def snapshot(self) -> BeliefSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> BeliefSnapshot:
        nodes = tuple(sorted(self._nodes.values()))
        return BeliefSnapshot(
            snapshot_id=self._snapshot_id,
            map_version=self._version,
            nodes=nodes,
            content_hash=BeliefSnapshot.compute_hash(self._version, nodes),
            map_id=self._map_id,
        )


@dataclass(frozen=True, slots=True)
class TaskAction:
    """One node in the task-action graph and its explicit map dependencies."""

    action_id: str
    order: int
    hard_read_nodes: frozenset[str] = frozenset()
    hard_write_nodes: frozenset[str] = frozenset()
    soft_relevance: tuple[tuple[str, float], ...] = ()
    safety_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.action_id.strip() or self.order < 0:
            raise ValueError("action_id must be non-empty and order non-negative")
        names = [node_id for node_id, _ in self.soft_relevance]
        if len(names) != len(set(names)):
            raise ValueError("soft_relevance node ids must be unique")
        if any(not 0.0 <= weight <= 1.0 for _, weight in self.soft_relevance):
            raise ValueError("soft relevance weights must be in [0, 1]")

    @property
    def hard_dependencies(self) -> frozenset[str]:
        return self.hard_read_nodes | self.hard_write_nodes

    def soft_relevance_map(self) -> dict[str, float]:
        return dict(self.soft_relevance)


@dataclass(frozen=True, slots=True)
class TaskActionGraph:
    task_id: UUID
    actions: tuple[TaskAction, ...]

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("task action graph must be non-empty")
        orders = [action.order for action in self.actions]
        ids = [action.action_id for action in self.actions]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            raise ValueError("task actions must have unique ascending order")
        if len(ids) != len(set(ids)):
            raise ValueError("task action ids must be unique")


class BridgeSupervisionSource(StrEnum):
    SYMBOLIC_RULE = "symbolic_rule"
    PLANNER_COUNTERFACTUAL = "planner_counterfactual"
    REAL_LOG = "real_log"
    ACTIVE_INTERVENTION = "active_intervention"
    RGRC_REVISION = "rgrc_revision"


@dataclass(frozen=True, slots=True)
class BridgeSupervision:
    """One B-BS3 label with provenance and explicit hard/soft authority."""

    action_id: str
    belief_node_id: str
    relevant: bool
    confidence: float
    source: BridgeSupervisionSource
    source_record_id: UUID
    hard_rule: bool = False

    def __post_init__(self) -> None:
        if not self.action_id.strip() or not self.belief_node_id.strip():
            raise ValueError("bridge label ids must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.hard_rule and self.source != BridgeSupervisionSource.SYMBOLIC_RULE:
            raise ValueError("only symbolic rules may create hard bridge labels")


class ConstrainedDependencyBridge:
    """B-DB3 hard candidates plus learned soft relevance without hard-edge deletion."""

    _SOURCE_WEIGHT: ClassVar[dict[BridgeSupervisionSource, float]] = {
        BridgeSupervisionSource.PLANNER_COUNTERFACTUAL: 1.0,
        BridgeSupervisionSource.REAL_LOG: 1.5,
        BridgeSupervisionSource.ACTIVE_INTERVENTION: 2.0,
        BridgeSupervisionSource.RGRC_REVISION: 2.0,
        BridgeSupervisionSource.SYMBOLIC_RULE: 1.0,
    }

    def __init__(self, labels: Iterable[BridgeSupervision] = ()) -> None:
        self._hard: dict[str, set[str]] = {}
        self._soft: dict[str, dict[str, float]] = {}
        self._soft_votes: dict[str, dict[str, list[BridgeSupervision]]] = {}
        self._provenance: list[BridgeSupervision] = []
        for label in labels:
            self.add_supervision(label)

    def add_supervision(self, label: BridgeSupervision) -> None:
        hard = self._hard.setdefault(label.action_id, set())
        soft = self._soft.setdefault(label.action_id, {})
        if label.hard_rule:
            if not label.relevant:
                if label.belief_node_id in hard:
                    raise ValueError("a hard positive dependency cannot be deleted")
            else:
                hard.add(label.belief_node_id)
        else:
            votes = self._soft_votes.setdefault(label.action_id, {}).setdefault(
                label.belief_node_id, []
            )
            votes.append(label)
            weighted_total = sum(
                self._SOURCE_WEIGHT[value.source] * value.confidence for value in votes
            )
            weighted_positive = sum(
                self._SOURCE_WEIGHT[value.source] * value.confidence
                for value in votes
                if value.relevant
            )
            soft[label.belief_node_id] = (
                weighted_positive / weighted_total if weighted_total > 0.0 else 0.0
            )
        self._provenance.append(label)

    def candidates(self, action_id: str, *, soft_threshold: float) -> frozenset[str]:
        if not 0.0 <= soft_threshold <= 1.0:
            raise ValueError("soft_threshold must be in [0, 1]")
        hard = self._hard.get(action_id, set())
        soft = {
            node_id
            for node_id, weight in self._soft.get(action_id, {}).items()
            if weight >= soft_threshold
        }
        return frozenset(hard | soft)

    def hard_dependencies(self, action_id: str) -> frozenset[str]:
        return frozenset(self._hard.get(action_id, set()))

    @property
    def provenance(self) -> tuple[BridgeSupervision, ...]:
        return tuple(self._provenance)


@dataclass(frozen=True, slots=True)
class BayesianRisk:
    expected_task_loss: float
    uncertainty_penalty: float
    hard_safety_violations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isfinite(self.expected_task_loss) or self.expected_task_loss < 0.0:
            raise ValueError("expected_task_loss must be finite and non-negative")
        if not isfinite(self.uncertainty_penalty) or self.uncertainty_penalty < 0.0:
            raise ValueError("uncertainty_penalty must be finite and non-negative")

    @property
    def total(self) -> float:
        if self.hard_safety_violations:
            return inf
        return self.expected_task_loss + self.uncertainty_penalty


class ExactActionRiskVerifier(Protocol):
    """Authoritative task counterfactual and safety evaluator."""

    def assess(self, action: TaskAction, snapshot: BeliefSnapshot) -> BayesianRisk: ...


class VersionSwitchKind(StrEnum):
    CONTINUE = "continue"
    REPLAN_SUFFIX = "replan_suffix"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class VersionSwitchDecision:
    kind: VersionSwitchKind
    old_snapshot_id: UUID
    new_snapshot_id: UUID
    changed_belief_nodes: frozenset[str]
    impacted_action_ids: tuple[str, ...]
    replan_from_order: int | None
    reason: str


class MapTaskCoordinator:
    """B-TC3 action-level map-version switching under an exact risk gate."""

    def __init__(
        self,
        *,
        soft_relevance_threshold: float = 0.5,
        risk_increase_threshold: float = 0.0,
        maximum_allowed_risk: float = inf,
    ) -> None:
        if not 0.0 <= soft_relevance_threshold <= 1.0:
            raise ValueError("soft_relevance_threshold must be in [0, 1]")
        if risk_increase_threshold < 0.0 or maximum_allowed_risk < 0.0:
            raise ValueError("risk thresholds must be non-negative")
        self.soft_relevance_threshold = soft_relevance_threshold
        self.risk_increase_threshold = risk_increase_threshold
        self.maximum_allowed_risk = maximum_allowed_risk

    def evaluate_switch(
        self,
        *,
        task: TaskActionGraph,
        current_action_order: int,
        old_snapshot: BeliefSnapshot,
        new_snapshot: BeliefSnapshot,
        verifier: ExactActionRiskVerifier,
        dependency_bridge: ConstrainedDependencyBridge | None = None,
    ) -> VersionSwitchDecision:
        if new_snapshot.map_version < old_snapshot.map_version:
            raise ValueError("new snapshot cannot be older than the pinned snapshot")
        changed = old_snapshot.changed_nodes(new_snapshot)
        future = tuple(action for action in task.actions if action.order >= current_action_order)
        impacted = tuple(
            action
            for action in future
            if self._is_impacted(action, changed, dependency_bridge)
        )
        if not impacted:
            return VersionSwitchDecision(
                kind=VersionSwitchKind.CONTINUE,
                old_snapshot_id=old_snapshot.snapshot_id,
                new_snapshot_id=new_snapshot.snapshot_id,
                changed_belief_nodes=changed,
                impacted_action_ids=(),
                replan_from_order=None,
                reason="no current-or-future action dependency changed",
            )

        replan_orders: list[int] = []
        for action in impacted:
            before = verifier.assess(action, old_snapshot)
            after = verifier.assess(action, new_snapshot)
            if after.hard_safety_violations:
                return VersionSwitchDecision(
                    kind=VersionSwitchKind.CANCEL,
                    old_snapshot_id=old_snapshot.snapshot_id,
                    new_snapshot_id=new_snapshot.snapshot_id,
                    changed_belief_nodes=changed,
                    impacted_action_ids=tuple(value.action_id for value in impacted),
                    replan_from_order=action.order,
                    reason="hard safety loss floor violated: "
                    + ", ".join(after.hard_safety_violations),
                )
            if (
                after.total > self.maximum_allowed_risk
                or after.total - before.total > self.risk_increase_threshold
            ):
                replan_orders.append(action.order)
        if replan_orders:
            first = min(replan_orders)
            suffix = tuple(action.action_id for action in future if action.order >= first)
            return VersionSwitchDecision(
                kind=VersionSwitchKind.REPLAN_SUFFIX,
                old_snapshot_id=old_snapshot.snapshot_id,
                new_snapshot_id=new_snapshot.snapshot_id,
                changed_belief_nodes=changed,
                impacted_action_ids=suffix,
                replan_from_order=first,
                reason="exact counterfactual risk crossed the action-level gate",
            )
        return VersionSwitchDecision(
            kind=VersionSwitchKind.CONTINUE,
            old_snapshot_id=old_snapshot.snapshot_id,
            new_snapshot_id=new_snapshot.snapshot_id,
            changed_belief_nodes=changed,
            impacted_action_ids=tuple(action.action_id for action in impacted),
            replan_from_order=None,
            reason="dependencies changed but exact risk remained inside constraints",
        )

    def _is_impacted(
        self,
        action: TaskAction,
        changed: frozenset[str],
        dependency_bridge: ConstrainedDependencyBridge | None,
    ) -> bool:
        bridge_hard = (
            frozenset()
            if dependency_bridge is None
            else dependency_bridge.hard_dependencies(action.action_id)
        )
        if (action.hard_dependencies | bridge_hard) & changed:
            return True
        soft = action.soft_relevance_map()
        if any(soft.get(node_id, 0.0) >= self.soft_relevance_threshold for node_id in changed):
            return True
        if dependency_bridge is None:
            return False
        learned_candidates = dependency_bridge.candidates(
            action.action_id,
            soft_threshold=self.soft_relevance_threshold,
        )
        return bool(learned_candidates & changed)


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    action_id: str
    residual_features: tuple[float, ...]
    action_cost: float

    def __post_init__(self) -> None:
        if not self.action_id.strip() or self.action_cost < 0.0:
            raise ValueError("candidate action id must be non-empty and cost non-negative")
        if not self.residual_features or any(
            not isfinite(value) for value in self.residual_features
        ):
            raise ValueError("residual_features must be finite and non-empty")


class OfflineGraphVOIProxy(Protocol):
    """B-PM3 offline graph model; it ranks candidates but cannot authorize them."""

    def predict_risk_reduction(
        self,
        candidate: ObservationCandidate,
        belief_snapshot: BeliefSnapshot,
        task_graph: TaskActionGraph,
    ) -> float: ...


@dataclass(frozen=True, slots=True)
class ExactObservationAssessment:
    risk_reduction: float
    hard_safety_violations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isfinite(self.risk_reduction):
            raise ValueError("risk_reduction must be finite")


class ExactObservationRiskVerifier(Protocol):
    def assess(
        self,
        candidate: ObservationCandidate,
        belief_snapshot: BeliefSnapshot,
        task_graph: TaskActionGraph,
    ) -> ExactObservationAssessment: ...


class LearnedVOIProxy:
    """B-VT3 offline graph score plus constrained online RLS residual."""

    def __init__(self, offline_proxy: OfflineGraphVOIProxy, *, feature_dim: int) -> None:
        self.offline_proxy = offline_proxy
        self.online_residual = NaturalRidgeResidual(feature_dim=feature_dim)

    def score(
        self,
        candidate: ObservationCandidate,
        belief_snapshot: BeliefSnapshot,
        task_graph: TaskActionGraph,
    ) -> float:
        base = float(
            self.offline_proxy.predict_risk_reduction(candidate, belief_snapshot, task_graph)
        )
        if not isfinite(base):
            raise ValueError("offline graph proxy returned a non-finite value")
        residual = self.online_residual.predict(candidate.residual_features)
        return base + residual - candidate.action_cost

    def calibrate(
        self,
        candidate: ObservationCandidate,
        belief_snapshot: BeliefSnapshot,
        task_graph: TaskActionGraph,
        *,
        exact_risk_reduction: float,
        weight: float = 1.0,
    ) -> None:
        base = float(
            self.offline_proxy.predict_risk_reduction(candidate, belief_snapshot, task_graph)
        )
        self.online_residual.update(
            candidate.residual_features,
            float(exact_risk_reduction) - base,
            weight=weight,
        )


@dataclass(frozen=True, slots=True)
class VerifiedObservationChoice:
    candidate: ObservationCandidate | None
    exact_assessment: ExactObservationAssessment | None
    rejected_action_ids: tuple[str, ...]


class ConstrainedVOISelector:
    """B-VOI3: learned ranking followed by mandatory exact risk verification."""

    def __init__(self, *, minimum_exact_net_risk_reduction: float = 0.0) -> None:
        if minimum_exact_net_risk_reduction < 0.0:
            raise ValueError("minimum risk reduction must be non-negative")
        self.minimum_exact_net_risk_reduction = minimum_exact_net_risk_reduction

    def choose(
        self,
        candidates: Iterable[ObservationCandidate],
        *,
        proxy: LearnedVOIProxy,
        exact_verifier: ExactObservationRiskVerifier,
        belief_snapshot: BeliefSnapshot,
        task_graph: TaskActionGraph,
    ) -> VerifiedObservationChoice:
        ranked = sorted(
            candidates,
            key=lambda candidate: proxy.score(candidate, belief_snapshot, task_graph),
            reverse=True,
        )
        rejected: list[str] = []
        for candidate in ranked:
            assessment = exact_verifier.assess(candidate, belief_snapshot, task_graph)
            net = assessment.risk_reduction - candidate.action_cost
            if (
                assessment.hard_safety_violations
                or net < self.minimum_exact_net_risk_reduction
            ):
                rejected.append(candidate.action_id)
                continue
            return VerifiedObservationChoice(candidate, assessment, tuple(rejected))
        return VerifiedObservationChoice(None, None, tuple(rejected))
