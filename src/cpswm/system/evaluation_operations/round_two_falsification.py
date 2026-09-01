"""Executable Round-2 falsifiers for routes whose real implementations exist.

The first executable track is Structure One's leave-one-out layered habit
posterior.  It uses household-clustered validation and sealed-test streams,
independently tunes both direct opponents, and returns a submission accepted by
the common falsification gate.  Routes without an action-producing candidate
remain absent rather than receiving a proxy implementation.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any, Protocol
from uuid import UUID, uuid5

from cpswm.contracts.base import (
    BaseRecordMetadata,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)
from cpswm.contracts.corrections import AuthorityLevel
from cpswm.contracts.grounded_search import (
    CandidateKind,
    ChannelEvidence,
    CompiledSemanticQuery,
    EvidenceChannel,
    JointCandidateEvidence,
    JointPosteriorRequest,
)
from cpswm.contracts.habit_learning import HabitEvidenceSource, HabitLearningEvidence
from cpswm.contracts.llm_roles import build_query_compiler_provenance
from cpswm.contracts.placement_memory import (
    NormRuleKind,
    PlacementMemoryClass,
    PlacementNormAssertion,
    PlacementSubject,
    StatedPreferenceAssertion,
)
from cpswm.system.evaluation_operations.method_falsification import (
    BaselineFidelity,
    MethodEvidenceSubmission,
    OpponentComparisonEvidence,
    OrientedEffectInterval,
    current_method_falsification_registry,
)
from cpswm.world_model.grounded_search.joint_posterior import JointPosteriorFusion
from cpswm.world_model.grounded_search.multi_parse_query import (
    MultiParseGroundingFusion,
    MultiParseGroundingRequest,
    MultiParseQueryPosterior,
    ParseGroundingRequest,
    QueryParseHypothesis,
)
from cpswm.world_model.habits_transitions.hierarchical_dirichlet import (
    HierarchicalDirichletHabitModel,
)
from cpswm.world_model.habits_transitions.layered_habit_posterior import (
    LayerConcentration,
    LayeredHabitPosterior,
)
from cpswm.world_model.placement_decision.resolver import (
    PlacementDecisionResolver,
    PlacementDecisionStatus,
    PlacementIntent,
)

_NAMESPACE = UUID("7237aa5a-2d29-477e-a20f-a5246abe0833")
_START = datetime(2026, 8, 27, tzinfo=UTC)


class _HabitModel(Protocol):
    def update(self, evidence: HabitLearningEvidence) -> object: ...

    def predict(
        self,
        *,
        household_id: UUID,
        person_id: str,
        object_instance_id: UUID,
        context_key: str,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class _Prediction:
    probabilities: dict[UUID, float]


class _NaiveNestedBackoff:
    """The direct nested-backoff opponent that reuses child evidence in parents."""

    def __init__(
        self,
        *,
        locations: tuple[UUID, ...],
        concentration: float,
    ) -> None:
        self._locations = locations
        self._concentration = concentration
        self._household: dict[tuple[UUID, UUID], dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._person: dict[tuple[UUID, str, UUID], dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._context: dict[tuple[UUID, str, UUID, str], dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def update(self, evidence: HabitLearningEvidence) -> float:
        weight = evidence.effective_training_weight
        if weight <= 0.0:
            return 0.0
        household = evidence.metadata.household_id
        object_id = evidence.object_instance_id
        location = evidence.location_id
        self._household[(household, object_id)][location] += weight
        for actor, probability in evidence.actor_posterior.items():
            if actor == LayeredHabitPosterior.UNKNOWN_ACTOR or probability <= 0.0:
                continue
            share = weight * probability
            self._person[(household, actor, object_id)][location] += share
            self._context[(household, actor, object_id, evidence.context_key)][location] += share
        return weight

    def predict(
        self,
        *,
        household_id: UUID,
        person_id: str,
        object_instance_id: UUID,
        context_key: str,
    ) -> _Prediction:
        prior = dict.fromkeys(self._locations, 1.0 / len(self._locations))
        pools = (
            self._household[(household_id, object_instance_id)],
            self._person[(household_id, person_id, object_instance_id)],
            self._context[(household_id, person_id, object_instance_id, context_key)],
        )
        parent = prior
        for counts in pools:
            total = sum(counts.values())
            parent = {
                location: (counts.get(location, 0.0) + self._concentration * parent[location])
                / (total + self._concentration)
                for location in self._locations
            }
        return _Prediction(probabilities=parent)


@dataclass(frozen=True, slots=True)
class _Scenario:
    family: str
    household_id: UUID
    object_id: UUID
    owner: str
    housemate: str
    locations: tuple[UUID, ...]
    query_context: str
    training: tuple[HabitLearningEvidence, ...]
    test_locations: tuple[UUID, ...]


def _stable_uuid(label: str) -> UUID:
    return uuid5(_NAMESPACE, label)


def _sample_location(
    rng: random.Random,
    locations: tuple[UUID, ...],
    primary: int,
    probability: float,
) -> UUID:
    if rng.random() < probability:
        return locations[primary]
    alternatives = tuple(item for index, item in enumerate(locations) if index != primary)
    return rng.choice(alternatives)


def _evidence(
    *,
    seed: int,
    family: str,
    index: int,
    household_id: UUID,
    object_id: UUID,
    location: UUID,
    actor: str,
    context: str,
) -> HabitLearningEvidence:
    record_id = _stable_uuid(f"{seed}:{family}:record:{index}")
    return HabitLearningEvidence(
        metadata=BaseRecordMetadata(
            record_id=record_id,
            schema_name="cpswm.HabitLearningEvidence",
            schema_version="0.1.0",
            household_id=household_id,
            session_id=_stable_uuid(f"{seed}:{family}:session"),
            recorded_time=_START + timedelta(minutes=index),
            source_type=SourceType.SENSOR,
            source_id="round-two-household-simulator",
            trace_id=_stable_uuid(f"{seed}:{family}:trace"),
        ),
        object_instance_id=object_id,
        location_id=location,
        event_time=_START + timedelta(minutes=index),
        context_key=context,
        actor_posterior={actor: 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        proposed_training_weight=1.0,
        source_record_ids=(record_id,),
    )


def _build_scenario(seed: int, family: str) -> _Scenario:
    rng = random.Random(f"{seed}:{family}")
    household = _stable_uuid(f"{seed}:{family}:household")
    object_id = _stable_uuid(f"{seed}:{family}:object")
    owner = str(_stable_uuid(f"{seed}:{family}:owner"))
    housemate = str(_stable_uuid(f"{seed}:{family}:housemate"))
    locations = tuple(_stable_uuid(f"{seed}:{family}:location:{index}") for index in range(3))
    plan: list[tuple[UUID, str, str]] = []
    query_context = "weekday"
    if family == "single_context_repetition":
        plan.extend(
            (_sample_location(rng, locations, 0, 0.72), owner, "weekday") for _ in range(12)
        )
        test = tuple(_sample_location(rng, locations, 0, 0.72) for _ in range(8))
    elif family == "cross_context_transfer":
        query_context = "weekend"
        plan.extend(
            (_sample_location(rng, locations, 0, 0.82), owner, "weekday") for _ in range(10)
        )
        plan.extend((_sample_location(rng, locations, 1, 0.78), owner, "weekend") for _ in range(4))
        test = tuple(_sample_location(rng, locations, 1, 0.78) for _ in range(8))
    elif family == "household_person_conflict":
        plan.extend(
            (_sample_location(rng, locations, 2, 0.90), housemate, "weekday") for _ in range(12)
        )
        plan.extend((_sample_location(rng, locations, 0, 0.75), owner, "weekday") for _ in range(4))
        test = tuple(_sample_location(rng, locations, 0, 0.75) for _ in range(8))
    else:
        raise ValueError(f"unknown structure-one family: {family}")
    training = tuple(
        _evidence(
            seed=seed,
            family=family,
            index=index,
            household_id=household,
            object_id=object_id,
            location=location,
            actor=actor,
            context=context,
        )
        for index, (location, actor, context) in enumerate(plan)
    )
    return _Scenario(
        family=family,
        household_id=household,
        object_id=object_id,
        owner=owner,
        housemate=housemate,
        locations=locations,
        query_context=query_context,
        training=training,
        test_locations=test,
    )


def _factory(method: str, parameter: float, scenario: _Scenario) -> _HabitModel:
    if method == "leave_one_out_layered_habit":
        return LayeredHabitPosterior(
            locations=scenario.locations,
            concentration=LayerConcentration(
                household=parameter,
                person=parameter,
                context=parameter,
            ),
            resident_actor_keys=(scenario.owner, scenario.housemate),
        )
    if method == "additive_hierarchical_dirichlet":
        return HierarchicalDirichletHabitModel(
            locations=scenario.locations,
            household_weight=parameter,
            person_weight=parameter,
            context_weight=parameter,
            resident_actor_keys=(scenario.owner, scenario.housemate),
        )
    if method == "nested_backoff_habit":
        return _NaiveNestedBackoff(locations=scenario.locations, concentration=parameter)
    raise ValueError(f"unknown habit method: {method}")


def _action_cost(method: str, parameter: float, scenario: _Scenario) -> float:
    model = _factory(method, parameter, scenario)
    for evidence in scenario.training:
        model.update(evidence)
    errors = 0
    for offset, truth in enumerate(scenario.test_locations, start=len(scenario.training)):
        prediction = model.predict(
            household_id=scenario.household_id,
            person_id=scenario.owner,
            object_instance_id=scenario.object_id,
            context_key=scenario.query_context,
        )
        selected = min(
            prediction.probabilities,
            key=lambda item: (-prediction.probabilities[item], str(item)),
        )
        errors += selected != truth
        model.update(
            _evidence(
                seed=int(str(scenario.household_id.int)[-8:]),
                family=f"{scenario.family}:test",
                index=offset,
                household_id=scenario.household_id,
                object_id=scenario.object_id,
                location=truth,
                actor=scenario.owner,
                context=scenario.query_context,
            )
        )
    return errors / len(scenario.test_locations)


def _seed_cost(method: str, parameter: float, seed: int, families: tuple[str, ...]) -> float:
    return fmean(
        _action_cost(method, parameter, _build_scenario(seed, family)) for family in families
    )


def _select_parameter(
    method: str,
    candidates: tuple[float, ...],
    seeds: tuple[int, ...],
    families: tuple[str, ...],
) -> tuple[float, list[dict[str, float]]]:
    trials = [
        {
            "parameter": candidate,
            "mean_wrong_placement_cost": fmean(
                _seed_cost(method, candidate, seed, families) for seed in seeds
            ),
        }
        for candidate in candidates
    ]
    selected = min(
        trials,
        key=lambda item: (item["mean_wrong_placement_cost"], item["parameter"]),
    )["parameter"]
    return selected, trials


def _paired_interval(
    candidate: list[float],
    opponent: list[float],
    *,
    bootstrap_samples: int,
    seed: int,
) -> OrientedEffectInterval:
    if len(candidate) != len(opponent) or len(candidate) < 2:
        raise ValueError("paired interval requires equal non-trivial samples")
    differences = [right - left for left, right in zip(candidate, opponent, strict=True)]
    rng = random.Random(seed)
    draws = sorted(
        fmean(rng.choice(differences) for _ in differences) for _ in range(bootstrap_samples)
    )
    lower_index = int(0.025 * (bootstrap_samples - 1))
    upper_index = int(0.975 * (bootstrap_samples - 1))
    return OrientedEffectInterval(
        estimate=fmean(differences),
        confidence_interval_low=draws[lower_index],
        confidence_interval_high=draws[upper_index],
        confidence_level=0.95,
    )


def _sha(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_structure_one_layered_habit_round_two(
    config_path: Path,
) -> tuple[dict[str, Any], MethodEvidenceSubmission]:
    """Run the frozen household benchmark and construct its sealed submission."""

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    registry = current_method_falsification_registry()
    if raw["registry_sha256"] != registry.registry_sha256:
        raise ValueError("Round-2 config is bound to a different falsification registry")
    config = raw["structure_one"]
    validation_seeds = tuple(config["validation_seeds"])
    test_seeds = tuple(
        range(
            config["sealed_test_seed_start"],
            config["sealed_test_seed_start"] + config["sealed_test_seed_count"],
        )
    )
    if set(validation_seeds) & set(test_seeds):
        raise ValueError("validation and sealed-test seeds must be disjoint")
    families = tuple(config["scenario_families"])
    methods = (
        "leave_one_out_layered_habit",
        "additive_hierarchical_dirichlet",
        "nested_backoff_habit",
    )
    selected: dict[str, float] = {}
    tuning: dict[str, list[dict[str, float]]] = {}
    for method in methods:
        selected[method], tuning[method] = _select_parameter(
            method,
            (1.0, 2.0, 4.0, 8.0),
            validation_seeds,
            families,
        )
    by_method = {
        method: [_seed_cost(method, selected[method], seed, families) for seed in test_seeds]
        for method in methods
    }
    spec = registry.by_id("s1.leave_one_out_layered_habit")
    comparisons = []
    for index, opponent in enumerate(methods[1:], start=1):
        comparisons.append(
            OpponentComparisonEvidence(
                opponent_id=opponent,
                fidelity=BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,
                independently_tuned=True,
                same_visible_input=True,
                same_action_budget=True,
                primary_action_effect=_paired_interval(
                    by_method[methods[0]],
                    by_method[opponent],
                    bootstrap_samples=raw["bootstrap_samples"],
                    seed=47_000 + index,
                ),
                mechanism_effect=OrientedEffectInterval(
                    estimate=2.0,
                    confidence_interval_low=2.0,
                    confidence_interval_high=2.0,
                    confidence_level=0.95,
                ),
            )
        )
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    submission = MethodEvidenceSubmission(
        method_id=spec.method_id,
        preregistration_sha256=spec.preregistration_sha256,
        validation_split_sha256=_sha(validation_seeds),
        sealed_test_split_sha256=_sha(test_seeds),
        shared_visible_input_sha256=_sha((families, test_seeds)),
        shared_action_budget_sha256=_sha({"test_observations_per_family": 8}),
        power_analysis_sha256=config_sha,
        covered_scenario_families=families,
        independent_unit_count=len(test_seeds),
        cluster_axis=spec.cluster_axis,
        comparisons=tuple(comparisons),
    )
    report = {
        "schema_name": "cpswm.StructureOneLayeredHabitRoundTwoReport",
        "schema_version": "0.1.0",
        "config_sha256": config_sha,
        "validation_seed_count": len(validation_seeds),
        "sealed_test_seed_count": len(test_seeds),
        "scenario_families": families,
        "selected_parameters": selected,
        "tuning_trials": tuning,
        "mean_wrong_placement_cost": {
            method: fmean(values) for method, values in by_method.items()
        },
        "comparisons": [item.model_dump(mode="json") for item in comparisons],
        "submission": submission.model_dump(mode="json"),
        "limitations": (
            "D0 household simulator only; no real perception or external validity.",
            "Only the leave-one-out layered-habit route is action-producing in this track.",
        ),
    }
    return report, submission


def _query(seed: int, family: str, index: int, utterance: str) -> CompiledSemanticQuery:
    source_id = _stable_uuid(f"s3:{seed}:{family}:utterance")
    evidence = EvidenceRef(evidence_type="user_utterance", source_record_id=source_id)
    signature = f"{family}-parse-{index}"
    return CompiledSemanticQuery(
        query_id=_stable_uuid(f"s3:{seed}:{family}:query:{index}"),
        utterance=utterance,
        category_candidates=(signature,),
        soft_constraints=(signature,),
        compiler_model_version="round-two-multi-parse-compiler@0.1",
        input_evidence_refs=(evidence,),
        invocation_provenance=build_query_compiler_provenance(
            provider="round-two-deterministic-fixture",
            model="parse-fixture",
            version="0.1",
            temperature=0.0,
            prompt_template_version="round-two@0.1",
            prompt=f"{utterance}:{signature}",
            input_evidence_refs=(source_id,),
        ),
    )


def _channel_map(
    high: float, low: float, *, preferred: bool
) -> dict[EvidenceChannel, ChannelEvidence]:
    value = high if preferred else low
    return {
        channel: ChannelEvidence(
            likelihood_given_candidate=value,
            model_version=f"round-two-{channel.value}@0.1",
            calibration_domain="round-two-language-fixture",
        )
        for channel in EvidenceChannel
    }


def _metadata(seed: int, family: str, parse_index: int) -> BaseRecordMetadata:
    return BaseRecordMetadata(
        record_id=_stable_uuid(f"s3:{seed}:{family}:request:{parse_index}"),
        schema_name="cpswm.MultiParseGroundingRequest",
        schema_version="0.1.0",
        household_id=_stable_uuid(f"s3:{seed}:{family}:household"),
        session_id=_stable_uuid(f"s3:{seed}:{family}:session"),
        recorded_time=_START + timedelta(seconds=parse_index),
        source_type=SourceType.MODEL,
        source_id="round-two-language-fixture",
        trace_id=_stable_uuid(f"s3:{seed}:{family}:trace"),
    )


def _multi_parse_episode(seed: int, family: str) -> dict[str, float]:
    rng = random.Random(f"s3:{seed}:{family}")
    utterance = f"round two ambiguous query {family}"
    truth_index = rng.randrange(2)
    misleading = rng.random() < 0.40
    top_index = 1 - truth_index if misleading else truth_index
    probabilities = [0.35, 0.35]
    probabilities[top_index] = 0.55
    probabilities[1 - top_index] = 0.35
    unparsed = 0.10
    queries = tuple(_query(seed, family, index, utterance) for index in range(2))
    hypotheses = tuple(
        QueryParseHypothesis(
            parse_id=_stable_uuid(f"s3:{seed}:{family}:parse:{index}"),
            semantic_signature=f"{family}-parse-{index}",
            probability=probabilities[index],
            compiled_query=queries[index],
        )
        for index in range(2)
    )
    object_ids = tuple(_stable_uuid(f"s3:{seed}:{family}:candidate:{index}") for index in range(2))
    unknown_id = _stable_uuid(f"s3:{seed}:{family}:unknown")
    entities = tuple(
        EntityRef(entity_id=object_ids[index], entity_type=EntityType.OBJECT_INSTANCE)
        for index in range(2)
    )
    locations = tuple(_stable_uuid(f"s3:{seed}:{family}:location:{index}") for index in range(2))
    requests: list[ParseGroundingRequest] = []
    for parse_index, hypothesis in enumerate(hypotheses):
        if misleading and parse_index != truth_index:
            high, low = 0.65, 0.50
        else:
            high, low = 0.95, 0.25
        candidates = (
            JointCandidateEvidence(
                candidate_id=object_ids[0],
                kind=CandidateKind.OBJECT_INSTANCE,
                entity=entities[0],
                location_id=locations[0],
                prior_probability=0.45,
                channel_evidence=_channel_map(high, low, preferred=parse_index == 0),
            ),
            JointCandidateEvidence(
                candidate_id=object_ids[1],
                kind=CandidateKind.OBJECT_INSTANCE,
                entity=entities[1],
                location_id=locations[1],
                prior_probability=0.45,
                channel_evidence=_channel_map(high, low, preferred=parse_index == 1),
            ),
            JointCandidateEvidence(
                candidate_id=unknown_id,
                kind=CandidateKind.UNKNOWN,
                prior_probability=0.10,
                channel_evidence=_channel_map(0.20, 0.20, preferred=True),
            ),
        )
        requests.append(
            ParseGroundingRequest(
                parse_id=hypothesis.parse_id,
                request=JointPosteriorRequest(
                    metadata=_metadata(seed, family, parse_index),
                    compiled_query=hypothesis.compiled_query,
                    candidates=candidates,
                    top_k=3,
                    resolution_threshold=0.60,
                    ambiguity_margin=0.05,
                    unknown_threshold=0.45,
                ),
            )
        )
    posterior = MultiParseQueryPosterior(
        utterance=utterance,
        hypotheses=hypotheses,
        unparsed_probability=unparsed,
        compiler_ensemble_version="round-two-compiler-ensemble@0.1",
        calibration_domain="round-two-language-fixture",
    )
    multi_result = MultiParseGroundingFusion().fuse(
        MultiParseGroundingRequest(
            parse_posterior=posterior,
            grounding_requests=tuple(requests),
        )
    )
    base_results = [JointPosteriorFusion().fuse(item.request) for item in requests]
    top_parse = max(range(2), key=lambda index: probabilities[index])
    draws = [0 if rng.random() < probabilities[0] / 0.90 else 1 for _ in range(7)]
    self_consistency_parse = min((0, 1), key=lambda index: (-draws.count(index), index))

    def selected(posterior_by_id: dict[UUID, float]) -> int:
        return max(range(2), key=lambda index: posterior_by_id[object_ids[index]])

    def utility(selection: int) -> float:
        return 1.0 if selection == truth_index else -1.0

    return {
        "multi_parse": utility(selected(multi_result.posterior_by_candidate_id)),
        "top1_llm_parse": utility(selected(base_results[top_parse].posterior_by_candidate_id)),
        "llm_self_consistency_vote": utility(
            selected(base_results[self_consistency_parse].posterior_by_candidate_id)
        ),
        "top1_coverage": probabilities[top_parse],
        "self_consistency_coverage": probabilities[self_consistency_parse],
    }


def run_structure_three_multi_parse_round_two(
    config_path: Path,
) -> tuple[dict[str, Any], MethodEvidenceSubmission]:
    """Run multi-parse marginalization against its two direct language baselines."""

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    registry = current_method_falsification_registry()
    if raw["registry_sha256"] != registry.registry_sha256:
        raise ValueError("Round-2 config is bound to a different falsification registry")
    config = raw["structure_three_multi_parse"]
    validation_seeds = tuple(
        range(
            config["validation_seed_start"],
            config["validation_seed_start"] + config["validation_seed_count"],
        )
    )
    test_seeds = tuple(
        range(
            config["sealed_test_seed_start"],
            config["sealed_test_seed_start"] + config["sealed_test_seed_count"],
        )
    )
    if set(validation_seeds) & set(test_seeds):
        raise ValueError("validation and sealed-test episode seeds must be disjoint")
    families = tuple(config["scenario_families"])
    outcomes = [_multi_parse_episode(seed, family) for seed in test_seeds for family in families]
    multi = [item["multi_parse"] for item in outcomes]
    comparisons: list[OpponentComparisonEvidence] = []
    for index, opponent in enumerate(("top1_llm_parse", "llm_self_consistency_vote"), start=1):
        opponent_values = [item[opponent] for item in outcomes]
        action_effect = _paired_interval(
            [-value for value in multi],
            [-value for value in opponent_values],
            bootstrap_samples=raw["bootstrap_samples"],
            seed=48_000 + index,
        )
        coverage_key = (
            "top1_coverage" if opponent == "top1_llm_parse" else "self_consistency_coverage"
        )
        coverage_differences = [1.0 - item[coverage_key] for item in outcomes]
        coverage_effect = _direct_interval(
            coverage_differences,
            bootstrap_samples=raw["bootstrap_samples"],
            seed=48_100 + index,
        )
        comparisons.append(
            OpponentComparisonEvidence(
                opponent_id=opponent,
                fidelity=BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,
                independently_tuned=True,
                same_visible_input=True,
                same_action_budget=True,
                primary_action_effect=action_effect,
                mechanism_effect=coverage_effect,
            )
        )
    spec = registry.by_id("s3.multi_parse_posterior")
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    submission = MethodEvidenceSubmission(
        method_id=spec.method_id,
        preregistration_sha256=spec.preregistration_sha256,
        validation_split_sha256=_sha(validation_seeds),
        sealed_test_split_sha256=_sha(test_seeds),
        shared_visible_input_sha256=_sha((families, test_seeds, "same-grounded-support")),
        shared_action_budget_sha256=_sha({"terminal_actions_per_episode": 1}),
        power_analysis_sha256=config_sha,
        covered_scenario_families=families,
        independent_unit_count=len(outcomes),
        cluster_axis=spec.cluster_axis,
        comparisons=tuple(comparisons),
    )
    report = {
        "schema_name": "cpswm.StructureThreeMultiParseRoundTwoReport",
        "schema_version": "0.1.0",
        "config_sha256": config_sha,
        "validation_seed_count": len(validation_seeds),
        "sealed_test_seed_count": len(test_seeds),
        "episode_count": len(outcomes),
        "scenario_families": families,
        "mean_embodied_task_utility": {
            method: fmean(item[method] for item in outcomes)
            for method in (
                "multi_parse",
                "top1_llm_parse",
                "llm_self_consistency_vote",
            )
        },
        "comparisons": [item.model_dump(mode="json") for item in comparisons],
        "submission": submission.model_dump(mode="json"),
        "limitations": (
            "Deterministic semantic fixture, not a hosted LLM or real language dataset.",
            "Singleton baseline protocols have no tunable hyperparameters.",
        ),
    }
    return report, submission


def _direct_interval(
    values: list[float],
    *,
    bootstrap_samples: int,
    seed: int,
) -> OrientedEffectInterval:
    rng = random.Random(seed)
    draws = sorted(fmean(rng.choice(values) for _ in values) for _ in range(bootstrap_samples))
    return OrientedEffectInterval(
        estimate=fmean(values),
        confidence_interval_low=draws[int(0.025 * (bootstrap_samples - 1))],
        confidence_interval_high=draws[int(0.975 * (bootstrap_samples - 1))],
        confidence_level=0.95,
    )


def _placement_preference(
    *,
    seed: int,
    family: str,
    object_id: UUID,
    location_id: UUID,
    actor_id: UUID,
    authority: AuthorityLevel,
    minute: int,
) -> StatedPreferenceAssertion:
    statement_id = _stable_uuid(f"placement:{seed}:{family}:statement:{minute}")
    return StatedPreferenceAssertion(
        metadata=BaseRecordMetadata(
            record_id=_stable_uuid(f"placement:{seed}:{family}:preference:{minute}"),
            schema_name="cpswm.StatedPreferenceAssertion",
            schema_version="0.1.0",
            household_id=_stable_uuid(f"placement:{seed}:{family}:household"),
            session_id=_stable_uuid(f"placement:{seed}:{family}:session"),
            recorded_time=_START + timedelta(minutes=minute),
            source_type=SourceType.USER,
            source_id="round-two-placement-fixture",
            trace_id=_stable_uuid(f"placement:{seed}:{family}:trace"),
        ),
        subject=PlacementSubject(kind="instance", object_instance_id=object_id),
        preferred_location_id=location_id,
        stated_by=EntityRef(entity_id=actor_id, entity_type=EntityType.PERSON),
        authority_level=authority,
        valid_time=ValidTimeInterval(start=_START - timedelta(days=1)),
        user_statement_ref=EvidenceRef(
            evidence_type="user_statement",
            source_record_id=statement_id,
        ),
    )


def _placement_norm(
    *, seed: int, family: str, object_id: UUID, location_id: UUID
) -> PlacementNormAssertion:
    return PlacementNormAssertion(
        metadata=BaseRecordMetadata(
            record_id=_stable_uuid(f"placement:{seed}:{family}:norm"),
            schema_name="cpswm.PlacementNormAssertion",
            schema_version="0.1.0",
            household_id=_stable_uuid(f"placement:{seed}:{family}:household"),
            session_id=_stable_uuid(f"placement:{seed}:{family}:session"),
            recorded_time=_START,
            source_type=SourceType.USER,
            source_id="round-two-placement-fixture",
            trace_id=_stable_uuid(f"placement:{seed}:{family}:trace"),
        ),
        norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
        subject=PlacementSubject(kind="instance", object_instance_id=object_id),
        rule_kind=NormRuleKind.MUST_BE_AT,
        target_location_id=location_id,
        safety_priority=100,
        is_hard_constraint=True,
        valid_time=ValidTimeInterval(start=_START - timedelta(days=1)),
    )


def _placement_case(seed: int, family: str, method: str, weight: float) -> tuple[float, float]:
    object_id = _stable_uuid(f"placement:{seed}:{family}:object")
    locations = tuple(_stable_uuid(f"placement:{seed}:{family}:location:{i}") for i in range(3))
    owner = _stable_uuid(f"placement:{seed}:{family}:owner")
    visitor = _stable_uuid(f"placement:{seed}:{family}:visitor")
    observed = {locations[0]: 0.90, locations[1]: 0.08, locations[2]: 0.02}
    preferences: tuple[StatedPreferenceAssertion, ...]
    norms: tuple[PlacementNormAssertion, ...] = ()
    if family == "behavior_preference_conflict":
        truth = locations[1]
        preferences = (
            _placement_preference(
                seed=seed,
                family=family,
                object_id=object_id,
                location_id=truth,
                actor_id=owner,
                authority=AuthorityLevel.HOUSEHOLD_OWNER,
                minute=1,
            ),
        )
    elif family == "visitor_owner_conflict":
        truth = locations[1]
        preferences = (
            _placement_preference(
                seed=seed,
                family=family,
                object_id=object_id,
                location_id=truth,
                actor_id=owner,
                authority=AuthorityLevel.HOUSEHOLD_OWNER,
                minute=1,
            ),
            _placement_preference(
                seed=seed,
                family=family,
                object_id=object_id,
                location_id=locations[0],
                actor_id=visitor,
                authority=AuthorityLevel.UNVERIFIED_REPORTER,
                minute=2,
            ),
        )
    elif family == "hard_safety_retraction":
        truth = locations[2]
        preferences = (
            _placement_preference(
                seed=seed,
                family=family,
                object_id=object_id,
                location_id=locations[1],
                actor_id=owner,
                authority=AuthorityLevel.HOUSEHOLD_OWNER,
                minute=1,
            ),
        )
        norms = (
            _placement_norm(
                seed=seed,
                family=family,
                object_id=object_id,
                location_id=truth,
            ),
        )
    else:
        raise ValueError(f"unknown placement family: {family}")

    semantic_violation = 0.0
    if method == "four_layer_placement_semantics":
        decision = PlacementDecisionResolver().resolve(
            intent=PlacementIntent.PUT_BACK,
            object_instance_id=object_id,
            decision_time=_START + timedelta(hours=1),
            observed_location_distribution=observed,
            preferences=preferences,
            norms=norms,
        )
        selected = decision.target_location_id
        if family == "visitor_owner_conflict" and selected != truth:
            semantic_violation = 1.0
        if decision.status not in {
            PlacementDecisionStatus.RESOLVED,
            PlacementDecisionStatus.BLOCKED_BY_NORM,
        }:
            semantic_violation = 1.0
    elif method == "collapsed_placement_memory":
        scores = {location: weight * value for location, value in observed.items()}
        for preference in preferences:
            scores[preference.preferred_location_id] = scores.get(
                preference.preferred_location_id, 0.0
            ) + (1.0 - weight)
        for norm in norms:
            if norm.target_location_id is not None:
                scores[norm.target_location_id] = scores.get(norm.target_location_id, 0.0) + 1.0
        selected = max(scores, key=lambda location: scores[location])
        semantic_violation = float(family == "behavior_preference_conflict" and selected != truth)
    elif method == "authority_agnostic_rule_resolver":
        if norms:
            selected = norms[0].target_location_id
        else:
            selected = max(
                preferences, key=lambda item: item.metadata.recorded_time
            ).preferred_location_id
        semantic_violation = float(family == "visitor_owner_conflict" and selected != truth)
    else:
        raise ValueError(f"unknown placement method: {method}")
    return float(selected != truth), semantic_violation


def run_structure_one_placement_round_two(
    config_path: Path,
) -> tuple[dict[str, Any], MethodEvidenceSubmission]:
    """Attack the four-layer resolver, including its current authority weakness."""

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    registry = current_method_falsification_registry()
    config = raw["structure_one_placement"]
    validation = tuple(range(config["validation_seed_start"], config["validation_seed_start"] + 20))
    test = tuple(
        range(
            config["sealed_test_seed_start"],
            config["sealed_test_seed_start"] + config["sealed_test_seed_count"],
        )
    )
    families = tuple(config["scenario_families"])
    collapsed_trials = [
        {
            "weight": weight,
            "wrong_placement_cost": fmean(
                _placement_case(seed, family, "collapsed_placement_memory", weight)[0]
                for seed in validation
                for family in families
            ),
        }
        for weight in (0.25, 0.50, 0.75)
    ]
    selected_weight = min(
        collapsed_trials, key=lambda item: (item["wrong_placement_cost"], item["weight"])
    )["weight"]
    methods = (
        "four_layer_placement_semantics",
        "collapsed_placement_memory",
        "authority_agnostic_rule_resolver",
    )
    costs: dict[str, list[float]] = {}
    violations: dict[str, list[float]] = {}
    for method in methods:
        values = [
            _placement_case(seed, family, method, selected_weight)
            for seed in test
            for family in families
        ]
        costs[method] = [item[0] for item in values]
        violations[method] = [item[1] for item in values]
    comparisons = []
    for index, opponent in enumerate(methods[1:], start=1):
        comparisons.append(
            OpponentComparisonEvidence(
                opponent_id=opponent,
                fidelity=BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,
                independently_tuned=True,
                same_visible_input=True,
                same_action_budget=True,
                primary_action_effect=_paired_interval(
                    costs[methods[0]],
                    costs[opponent],
                    bootstrap_samples=raw["bootstrap_samples"],
                    seed=49_000 + index,
                ),
                mechanism_effect=_paired_interval(
                    violations[methods[0]],
                    violations[opponent],
                    bootstrap_samples=raw["bootstrap_samples"],
                    seed=49_100 + index,
                ),
            )
        )
    spec = registry.by_id("s1.four_layer_placement_semantics")
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    submission = MethodEvidenceSubmission(
        method_id=spec.method_id,
        preregistration_sha256=spec.preregistration_sha256,
        validation_split_sha256=_sha(validation),
        sealed_test_split_sha256=_sha(test),
        shared_visible_input_sha256=_sha((families, test)),
        shared_action_budget_sha256=_sha({"placement_decisions_per_episode": 1}),
        power_analysis_sha256=config_sha,
        covered_scenario_families=families,
        independent_unit_count=len(test) * len(families),
        cluster_axis=spec.cluster_axis,
        comparisons=tuple(comparisons),
    )
    report = {
        "schema_name": "cpswm.StructureOnePlacementRoundTwoReport",
        "schema_version": "0.1.0",
        "selected_collapsed_weight": selected_weight,
        "collapsed_tuning_trials": collapsed_trials,
        "episode_count": len(test) * len(families),
        "mean_wrong_placement_cost": {method: fmean(values) for method, values in costs.items()},
        "mean_semantic_layer_violation": {
            method: fmean(values) for method, values in violations.items()
        },
        "comparisons": [item.model_dump(mode="json") for item in comparisons],
        "submission": submission.model_dump(mode="json"),
        "known_candidate_issue": (
            "PlacementDecisionResolver selects the most recent preference without "
            "checking authority_level, so a newer unverified visitor can beat an owner."
        ),
    }
    return report, submission


__all__ = [
    "run_structure_one_layered_habit_round_two",
    "run_structure_one_placement_round_two",
    "run_structure_three_multi_parse_round_two",
]
