from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from cpswm.system.evaluation_operations.structure_two_comparator_typed_dual_gate_b_v0_8 import (
    ACTION_SCHEMA_ID,
    BELIEF_SCHEMA_ID,
    EXPECTED_ARMS,
    INVALIDATED_PROTOCOL_ID,
    PROTOCOL_STATUS,
    ComparatorEvidence,
    ComparatorType,
    DecisionReadout,
    DistributionKind,
    EpisodeDistribution,
    EpisodePublicOntology,
    MetricRelation,
    PublicActionKind,
    ReadoutStage,
    RuntimeAction,
    RuntimeActionMapping,
    RuntimeActionProjection,
    canonical_comparator_specs_v0_8,
    canonical_protocol_payload_v0_8,
    load_frozen_protocol_v0_8,
    make_runtime_action,
    runtime_action_from_mapping,
    score_frozen_gate_b_v0_8_diagnostic,
    validate_protocol_payload_v0_8,
)
from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    PROTOCOL_STATUS as V0_7_STATUS,
)
from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    SUPERSEDED_BY_PROTOCOL_ID,
    canonical_frozen_protocol_payload_v0_7,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project_two_experiments/structure_two_gate_b_v0_8.json"


def _uuid(label: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"gate-b-v0.8-test:{label}"))


def _ontology(
    *,
    episode_id: str = "episode-001",
    location_count: int = 8,
    guest_count: int = 2,
) -> EpisodePublicOntology:
    return EpisodePublicOntology(
        episode_id=episode_id,
        target_object_uuid=_uuid(f"{episode_id}:object"),
        owner_actor_uuid=_uuid(f"{episode_id}:owner"),
        robot_actor_uuid=_uuid(f"{episode_id}:robot"),
        location_uuids=tuple(
            sorted(_uuid(f"{episode_id}:location:{index}") for index in range(location_count))
        ),
        guest_actor_uuids=tuple(
            sorted(_uuid(f"{episode_id}:guest:{index}") for index in range(guest_count))
        ),
    )


def _projection(arm: str, ontology: EpisodePublicOntology) -> RuntimeActionProjection:
    return RuntimeActionProjection(
        episode_id=ontology.episode_id,
        arm=arm,
        ontology_manifest_sha256=ontology.manifest_sha256,
        entries=tuple(
            RuntimeActionMapping(
                public_action=public_action,
                runtime_action=_runtime_for_public(public_action, ontology),
            )
            for public_action in ontology.action_support
        ),
    )


def _runtime_for_public(
    public_action: str,
    ontology: EpisodePublicOntology,
) -> RuntimeAction:
    kind_text, parameter = public_action.split("|", 1)
    parameter_name, parameter_value = parameter.split("=", 1)
    kind = PublicActionKind(kind_text)
    return make_runtime_action(
        kind=kind,
        target_object_uuid=ontology.target_object_uuid,
        location_uuid=parameter_value if parameter_name == "location" else None,
        guest_actor_uuid=parameter_value if parameter_name == "guest" else None,
    )


def _distribution(
    kind: DistributionKind,
    ontology: EpisodePublicOntology,
    *,
    peak: int,
) -> EpisodeDistribution:
    support = (
        ontology.belief_support if kind is DistributionKind.BELIEF else ontology.action_support
    )
    probabilities = tuple(1.0 if index == peak else 0.0 for index in range(len(support)))
    return EpisodeDistribution(
        kind=kind,
        schema_id=BELIEF_SCHEMA_ID if kind is DistributionKind.BELIEF else ACTION_SCHEMA_ID,
        ontology_manifest_sha256=ontology.manifest_sha256,
        support=support,
        probabilities=probabilities,
    )


def _action_distribution(
    ontology: EpisodePublicOntology,
    first: float,
    second: float,
) -> EpisodeDistribution:
    return EpisodeDistribution(
        kind=DistributionKind.ACTION,
        schema_id=ACTION_SCHEMA_ID,
        ontology_manifest_sha256=ontology.manifest_sha256,
        support=ontology.action_support,
        probabilities=(first, second, *(0.0 for _ in ontology.action_support[2:])),
    )


def _readout(
    *,
    arm: str,
    ontology: EpisodePublicOntology,
    projection: RuntimeActionProjection,
    window_id: str,
    belief_peak: int,
    action_peak: int,
    utility: float | None,
) -> DecisionReadout:
    public_action = ontology.action_support[action_peak]
    return DecisionReadout(
        arm=arm,
        episode_id=ontology.episode_id,
        decision_id=f"{ontology.episode_id}:decision-0",
        causal_window_id=window_id,
        information_set_sha256=content_sha256(
            {"episode": ontology.episode_id, "visible_through": 10}
        ),
        ontology_manifest_sha256=ontology.manifest_sha256,
        projection_manifest_sha256=projection.manifest_sha256,
        readout_stage=ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
        evaluator_truth_accessed=False,
        readout_event_index=10,
        action_commit_event_index=11,
        belief=_distribution(DistributionKind.BELIEF, ontology, peak=belief_peak),
        action_policy=_distribution(DistributionKind.ACTION, ontology, peak=action_peak),
        selected_public_action=public_action,
        selected_runtime_action=projection.inverse(public_action, ontology=ontology),
        realized_utility=utility,
        utility_event_index=12 if utility is not None else None,
    )


def _complete_fixture() -> tuple[
    EpisodePublicOntology,
    dict[tuple[str, str], RuntimeActionProjection],
    tuple[ComparatorEvidence, ...],
]:
    ontology = _ontology()
    projections = {(arm, ontology.episode_id): _projection(arm, ontology) for arm in EXPECTED_ARMS}
    evidence: list[ComparatorEvidence] = []
    for spec in canonical_comparator_specs_v0_8():
        if spec.comparator_type is ComparatorType.CAUSAL_DUAL_DIFFERENCE:
            left_belief, right_belief = 0, 1
            left_action, right_action = 0, 1
            left_utility = right_utility = None
        elif spec.comparator_type is ComparatorType.ACTION_REGRET_AT_EQUIVALENT_BELIEF:
            left_belief = right_belief = 0
            left_action, right_action = 0, 1
            left_utility, right_utility = 0.7, 0.2
        else:
            left_belief = right_belief = 0
            left_action = right_action = 0
            left_utility = right_utility = None
        evidence.append(
            ComparatorEvidence(
                comparison_id=spec.comparison_id,
                left=_readout(
                    arm=spec.left_arm,
                    ontology=ontology,
                    projection=projections[(spec.left_arm, ontology.episode_id)],
                    window_id=spec.causal_window.window_id,
                    belief_peak=left_belief,
                    action_peak=left_action,
                    utility=left_utility,
                ),
                right=_readout(
                    arm=spec.right_arm,
                    ontology=ontology,
                    projection=projections[(spec.right_arm, ontology.episode_id)],
                    window_id=spec.causal_window.window_id,
                    belief_peak=right_belief,
                    action_peak=right_action,
                    utility=right_utility,
                ),
            )
        )
    return ontology, projections, tuple(evidence)


def _score(
    *,
    ontology: EpisodePublicOntology | None = None,
    projections: dict[tuple[str, str], RuntimeActionProjection] | None = None,
    evidence: tuple[ComparatorEvidence, ...] | None = None,
) -> dict[str, object]:
    default_ontology, default_projections, default_evidence = _complete_fixture()
    return score_frozen_gate_b_v0_8_diagnostic(
        evidence or default_evidence,
        protocol=load_frozen_protocol_v0_8(CONFIG),
        ontologies=(ontology or default_ontology,),
        projections=projections or default_projections,
    )


def test_v0_7_is_explicitly_invalidated_and_cannot_authorize() -> None:
    payload = canonical_frozen_protocol_payload_v0_7()
    assert V0_7_STATUS == "INVALIDATED_SUPERSEDED_FOR_FUTURE"
    assert canonical_protocol_payload_v0_8()["protocol"] == SUPERSEDED_BY_PROTOCOL_ID
    assert payload["positive_authorization_paths_disabled"] is True
    assert payload["official_execution"]["formal_gate_b_passed"] is False
    assert payload["official_execution"]["seven_operator_ablation_authorized"] is False


def test_v0_8_config_freezes_each_comparator_type_relation_bounds_and_window() -> None:
    protocol = load_frozen_protocol_v0_8(CONFIG)
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert protocol.status == PROTOCOL_STATUS
    assert protocol.formal_run_present is False
    assert protocol.formal_gate_b_passed is False
    assert protocol.seven_operator_ablation_authorized is False
    assert len(protocol.comparators) == 9
    assert payload == canonical_protocol_payload_v0_8()

    by_id = {spec.comparison_id: spec for spec in protocol.comparators}
    action_regret = by_id["action-regret-ablation"]
    assert action_regret.belief.relation is MetricRelation.EQUIVALENT
    assert action_regret.action.relation is MetricRelation.MATERIALLY_DIFFERENT
    assert action_regret.utility.relation is MetricRelation.MATERIALLY_DIFFERENT
    assert action_regret.causal_window.utility_end_offset_events == 3
    rerun = by_id["full-rerun-control"]
    assert rerun.belief.relation is MetricRelation.EQUIVALENT
    assert rerun.action.relation is MetricRelation.EQUIVALENT
    assert rerun.utility.relation is MetricRelation.NOT_SCORED
    for comparison_id, spec in by_id.items():
        assert spec.belief.equivalence_lower_bound == 0.0, comparison_id
        assert spec.belief.equivalence_upper_bound == 0.01, comparison_id
        assert spec.action.equivalence_lower_bound == 0.0, comparison_id
        assert spec.action.equivalence_upper_bound == 0.01, comparison_id


@pytest.mark.parametrize(
    "field",
    (
        "formal_run_present",
        "formal_gate_b_passed",
        "seven_operator_ablation_authorized",
    ),
)
def test_frozen_v0_8_object_rejects_direct_positive_construction(field: str) -> None:
    protocol = load_frozen_protocol_v0_8(CONFIG)
    with pytest.raises(ValueError, match="not an authorization surface"):
        replace(protocol, **{field: True})


def test_v0_8_config_rejects_duplicate_keys_and_relation_direction_substitution(
    tmp_path: Path,
) -> None:
    duplicated = CONFIG.read_text(encoding="utf-8").replace(
        "{", '{"protocol":"attacker-shadow",', 1
    )
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(duplicated, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_frozen_protocol_v0_8(duplicate_path)

    payload = canonical_protocol_payload_v0_8()
    action_regret = next(
        row for row in payload["comparisons"] if row["comparison_id"] == "action-regret-ablation"
    )
    action_regret["belief_relation"]["relation"] = "materially_different"
    with pytest.raises(ValueError, match="differs from the canonical preregistration"):
        validate_protocol_payload_v0_8(payload)


@pytest.mark.parametrize(("locations", "guests"), ((8, 1), (8, 3), (12, 1), (12, 3)))
def test_episode_public_ontology_covers_frozen_uuid_cardinalities_and_four_actions(
    locations: int,
    guests: int,
) -> None:
    ontology = _ontology(location_count=locations, guest_count=guests)
    assert len(ontology.location_uuids) == locations
    assert len(ontology.guest_actor_uuids) == guests
    assert len(ontology.action_support) == 2 * locations + 2 * guests
    assert {label.split("|", 1)[0] for label in ontology.action_support} == {
        "put_back",
        "search",
        "deliver",
        "ask",
    }
    assert len(ontology.belief_support) == locations * (2 + guests) + 1


def test_episode_public_ontology_rejects_count_uuid_and_identity_substitutions() -> None:
    with pytest.raises(ValueError, match="8-12"):
        _ontology(location_count=7)
    with pytest.raises(ValueError, match="1-3"):
        _ontology(guest_count=0)
    base = _ontology()
    with pytest.raises(ValueError, match="independent UUIDs"):
        replace(base, guest_actor_uuids=(base.owner_actor_uuid,))
    with pytest.raises(ValueError, match="canonical UUID"):
        replace(base, target_object_uuid="location-not-a-uuid")


def test_runtime_action_projection_is_an_exact_lossless_bijection() -> None:
    ontology = _ontology()
    projection = _projection("care_wm", ontology)
    projection.validate_against(ontology)
    for entry in projection.entries:
        assert projection.project(entry.runtime_action, ontology=ontology) == entry.public_action
        assert projection.inverse(entry.public_action, ontology=ontology) == entry.runtime_action


def test_runtime_action_projection_rejects_collisions_and_incomplete_support() -> None:
    ontology = _ontology()
    projection = _projection("care_wm", ontology)
    first, second, *rest = projection.entries
    with pytest.raises(ValueError, match="public-action collision"):
        replace(
            projection,
            entries=(first, replace(second, public_action=first.public_action), *rest),
        )
    with pytest.raises(ValueError, match="runtime-action collision"):
        replace(
            projection,
            entries=(first, replace(second, runtime_action=first.runtime_action), *rest),
        )
    incomplete = replace(projection, entries=projection.entries[:-1])
    with pytest.raises(ValueError, match="exactly cover"):
        incomplete.validate_against(ontology)


def test_runtime_projection_rejects_semantic_permutation_despite_round_trip_bijection() -> None:
    ontology = _ontology()
    projection = _projection("care_wm", ontology)
    first, second, *rest = projection.entries
    permuted = replace(
        projection,
        entries=(
            replace(first, runtime_action=second.runtime_action),
            replace(second, runtime_action=first.runtime_action),
            *rest,
        ),
    )
    with pytest.raises(ValueError, match="changed the typed action semantics"):
        permuted.validate_against(ontology)


def test_runtime_projection_rejects_wrong_object_location_guest_and_hidden_field() -> None:
    ontology = _ontology()
    projection = _projection("care_wm", ontology)
    location_entry = next(
        entry for entry in projection.entries if entry.public_action.startswith("put_back|")
    )
    wrong_object = make_runtime_action(
        kind=location_entry.runtime_action.kind,
        target_object_uuid=_uuid("attacker-other-object"),
        location_uuid=location_entry.runtime_action.location_uuid,
    )
    entries = tuple(
        replace(entry, runtime_action=wrong_object)
        if entry.public_action == location_entry.public_action
        else entry
        for entry in projection.entries
    )
    with pytest.raises(ValueError, match="another episode object"):
        replace(projection, entries=entries).validate_against(ontology)

    wrong_location = make_runtime_action(
        kind=location_entry.runtime_action.kind,
        target_object_uuid=ontology.target_object_uuid,
        location_uuid=_uuid("attacker-other-location"),
    )
    entries = tuple(
        replace(entry, runtime_action=wrong_location)
        if entry.public_action == location_entry.public_action
        else entry
        for entry in projection.entries
    )
    with pytest.raises(ValueError, match="location is absent"):
        replace(projection, entries=entries).validate_against(ontology)

    guest_entry = next(
        entry for entry in projection.entries if entry.public_action.startswith("ask|")
    )
    wrong_guest = make_runtime_action(
        kind=guest_entry.runtime_action.kind,
        target_object_uuid=ontology.target_object_uuid,
        guest_actor_uuid=_uuid("attacker-other-guest"),
    )
    entries = tuple(
        replace(entry, runtime_action=wrong_guest)
        if entry.public_action == guest_entry.public_action
        else entry
        for entry in projection.entries
    )
    with pytest.raises(ValueError, match="guest is absent"):
        replace(projection, entries=entries).validate_against(ontology)

    runtime = location_entry.runtime_action
    with pytest.raises(ValueError, match="missing or extra hidden fields"):
        runtime_action_from_mapping(
            {
                "runtime_action_id": runtime.runtime_action_id,
                "kind": runtime.kind.value,
                "target_object_uuid": runtime.target_object_uuid,
                "location_uuid": runtime.location_uuid,
                "guest_actor_uuid": runtime.guest_actor_uuid,
                "hidden_opcode": "delete",
            }
        )


def test_runtime_command_rejects_kind_parameter_and_identifier_lies() -> None:
    ontology = _ontology()
    with pytest.raises(ValueError, match="require only a location UUID"):
        RuntimeAction(
            runtime_action_id="put_back|forged",
            kind=PublicActionKind.PUT_BACK,
            target_object_uuid=ontology.target_object_uuid,
            location_uuid=None,
            guest_actor_uuid=ontology.guest_actor_uuids[0],
        )
    with pytest.raises(ValueError, match="derived from every typed semantic field"):
        RuntimeAction(
            runtime_action_id="delete|object=attacker",
            kind=PublicActionKind.PUT_BACK,
            target_object_uuid=ontology.target_object_uuid,
            location_uuid=ontology.location_uuids[0],
            guest_actor_uuid=None,
        )


def test_forged_complete_diagnostic_can_never_mint_formal_or_ablation_authorization() -> None:
    report = _score()
    assert report["diagnostic_typed_relations_passed"] is True
    assert report["formal_run_present"] is False
    assert report["independent_attestation_present"] is False
    assert report["formal_gate_b_passed"] is False
    assert report["gate_b_passed"] is False
    assert report["seven_operator_ablation_authorized"] is False


@pytest.mark.parametrize(
    ("field", "right_value", "failed_key"),
    (
        ("belief", 1, "belief_relation_passed"),
        ("action_policy", 0, "action_relation_passed"),
        ("realized_utility", 0.7, "utility_relation_passed"),
    ),
)
def test_action_regret_requires_predecision_belief_equivalence_and_action_utility_difference(
    field: str,
    right_value: int | float,
    failed_key: str,
) -> None:
    ontology, projections, evidence = _complete_fixture()
    index = next(
        i for i, row in enumerate(evidence) if row.comparison_id == "action-regret-ablation"
    )
    target = evidence[index]
    if field == "belief":
        replacement = replace(
            target.right,
            belief=_distribution(DistributionKind.BELIEF, ontology, peak=int(right_value)),
        )
    elif field == "action_policy":
        public = ontology.action_support[int(right_value)]
        projection = projections[(target.right.arm, ontology.episode_id)]
        replacement = replace(
            target.right,
            action_policy=_distribution(DistributionKind.ACTION, ontology, peak=int(right_value)),
            selected_public_action=public,
            selected_runtime_action=projection.inverse(public, ontology=ontology),
        )
    else:
        replacement = replace(target.right, realized_utility=float(right_value))
    changed = (*evidence[:index], replace(target, right=replacement), *evidence[index + 1 :])
    report = _score(ontology=ontology, projections=projections, evidence=changed)
    results = report["comparison_results"]
    assert isinstance(results, list)
    result = next(row for row in results if row["comparison_id"] == "action-regret-ablation")
    assert result[failed_key] is False
    assert result["typed_relation_passed"] is False


@pytest.mark.parametrize(
    ("kind", "peak"),
    ((DistributionKind.BELIEF, 1), (DistributionKind.ACTION, 1)),
)
def test_full_rerun_requires_belief_and_action_equivalence(
    kind: DistributionKind,
    peak: int,
) -> None:
    ontology, projections, evidence = _complete_fixture()
    index = next(i for i, row in enumerate(evidence) if row.comparison_id == "full-rerun-control")
    target = evidence[index]
    if kind is DistributionKind.BELIEF:
        right = replace(
            target.right,
            belief=_distribution(kind, ontology, peak=peak),
        )
        failed_key = "belief_relation_passed"
    else:
        public = ontology.action_support[peak]
        projection = projections[(target.right.arm, ontology.episode_id)]
        right = replace(
            target.right,
            action_policy=_distribution(kind, ontology, peak=peak),
            selected_public_action=public,
            selected_runtime_action=projection.inverse(public, ontology=ontology),
        )
        failed_key = "action_relation_passed"
    changed = (*evidence[:index], replace(target, right=right), *evidence[index + 1 :])
    report = _score(ontology=ontology, projections=projections, evidence=changed)
    results = report["comparison_results"]
    assert isinstance(results, list)
    result = next(row for row in results if row["comparison_id"] == "full-rerun-control")
    assert result[failed_key] is False
    assert result["typed_relation_passed"] is False


@pytest.mark.parametrize(
    ("comparison_id", "left_probabilities", "right_probabilities"),
    (
        ("event-inference-adaptation", (0.6, 0.4), (0.5, 0.5)),
        ("full-rerun-control", (0.501, 0.499), (0.499, 0.501)),
    ),
)
def test_action_relation_also_enforces_selected_public_action_relation(
    comparison_id: str,
    left_probabilities: tuple[float, float],
    right_probabilities: tuple[float, float],
) -> None:
    ontology, projections, evidence = _complete_fixture()
    index = next(i for i, row in enumerate(evidence) if row.comparison_id == comparison_id)
    row = evidence[index]
    left_public = ontology.action_support[0]
    right_public = ontology.action_support[
        0 if comparison_id == "event-inference-adaptation" else 1
    ]
    left_projection = projections[(row.left.arm, ontology.episode_id)]
    right_projection = projections[(row.right.arm, ontology.episode_id)]
    left = replace(
        row.left,
        action_policy=_action_distribution(ontology, *left_probabilities),
        selected_public_action=left_public,
        selected_runtime_action=left_projection.inverse(left_public, ontology=ontology),
    )
    right = replace(
        row.right,
        action_policy=_action_distribution(ontology, *right_probabilities),
        selected_public_action=right_public,
        selected_runtime_action=right_projection.inverse(right_public, ontology=ontology),
    )
    changed = (*evidence[:index], replace(row, left=left, right=right), *evidence[index + 1 :])
    report = _score(ontology=ontology, projections=projections, evidence=changed)
    results = report["comparison_results"]
    assert isinstance(results, list)
    result = next(item for item in results if item["comparison_id"] == comparison_id)
    assert result["action_relation_passed"] is True
    assert result["selected_action_relation_passed"] is False
    assert result["typed_relation_passed"] is False


def test_ontology_substitution_projection_mismatch_and_selected_action_lie_fail_closed() -> None:
    ontology, projections, evidence = _complete_fixture()
    row = evidence[0]
    other = _ontology(episode_id=ontology.episode_id + "-substitute")
    forged_belief = replace(
        row.left.belief,
        ontology_manifest_sha256=other.manifest_sha256,
    )
    changed = (replace(row, left=replace(row.left, belief=forged_belief)), *evidence[1:])
    with pytest.raises(ValueError, match="substituted another ontology"):
        _score(ontology=ontology, projections=projections, evidence=changed)

    wrong_projection = replace(
        projections[(row.left.arm, ontology.episode_id)],
        ontology_manifest_sha256=other.manifest_sha256,
    )
    altered_projections = dict(projections)
    altered_projections[(row.left.arm, ontology.episode_id)] = wrong_projection
    with pytest.raises(ValueError, match="substituted another episode ontology"):
        _score(ontology=ontology, projections=altered_projections, evidence=evidence)

    lied = replace(row.left, selected_public_action=ontology.action_support[2])
    changed = (replace(row, left=lied), *evidence[1:])
    with pytest.raises(ValueError, match="does not project"):
        _score(ontology=ontology, projections=projections, evidence=changed)


@pytest.mark.parametrize(
    "mutation",
    (
        {"readout_stage": ReadoutStage.POST_ACTION},
        {"evaluator_truth_accessed": True},
        {"readout_event_index": 11},
        {"intervening_exogenous_event": True},
    ),
)
def test_post_action_truth_and_causal_window_substitutions_fail_closed(
    mutation: dict[str, object],
) -> None:
    ontology, projections, evidence = _complete_fixture()
    row = evidence[0]
    changed = (replace(row, left=replace(row.left, **mutation)), *evidence[1:])
    with pytest.raises(ValueError, match=r"post-action|causal.window|exogenous"):
        _score(ontology=ontology, projections=projections, evidence=changed)


def test_action_regret_utility_outside_preregistered_window_fails_closed() -> None:
    ontology, projections, evidence = _complete_fixture()
    index = next(
        i for i, row in enumerate(evidence) if row.comparison_id == "action-regret-ablation"
    )
    row = evidence[index]
    changed_right = replace(row.right, utility_event_index=15)
    changed_left = replace(row.left, utility_event_index=15)
    changed = (
        *evidence[:index],
        replace(row, left=changed_left, right=changed_right),
        *evidence[index + 1 :],
    )
    with pytest.raises(ValueError, match="outside the frozen causal window"):
        _score(ontology=ontology, projections=projections, evidence=changed)


def test_caller_supplied_noncanonical_protocol_object_is_rejected() -> None:
    ontology, projections, evidence = _complete_fixture()
    protocol = load_frozen_protocol_v0_8(CONFIG)
    mutated = replace(protocol, content_sha256="f" * 64)
    with pytest.raises(ValueError, match=r"noncanonical Gate B v0.8 freeze"):
        score_frozen_gate_b_v0_8_diagnostic(
            evidence,
            protocol=mutated,
            ontologies=(ontology,),
            projections=projections,
        )


def test_comparator_model_rejects_type_bound_and_window_cross_mixing() -> None:
    action_regret = next(
        spec
        for spec in canonical_comparator_specs_v0_8()
        if spec.comparison_id == "action-regret-ablation"
    )
    with pytest.raises(ValueError, match="identity, type, domain, or arms were mixed"):
        replace(action_regret, comparator_type=ComparatorType.FULL_RERUN_EQUIVALENCE)
    with pytest.raises(ValueError, match="relation bounds differ"):
        replace(
            action_regret,
            belief=replace(action_regret.belief, equivalence_upper_bound=0.02),
        )
    with pytest.raises(ValueError, match="causal window differs"):
        replace(
            action_regret,
            causal_window=replace(
                action_regret.causal_window,
                utility_end_offset_events=4,
            ),
        )


def test_invalidated_v0_7_protocol_identifier_is_not_v0_8() -> None:
    assert canonical_protocol_payload_v0_8()["protocol"] != INVALIDATED_PROTOCOL_ID


@pytest.mark.parametrize(
    "legacy_protocol",
    (
        "structure-two-stratified-mechanism-action-gate-b@0.6",
        "structure-two-stratified-mechanism-dual-readout-gate-b@0.7",
        "structure-two-sealed-gate-b-opening@0.9",
        "structure-two-formal-sealed-dual-gate-b-receipt@1.0",
    ),
)
def test_legacy_self_consistent_receipt_cannot_substitute_for_v0_8_protocol(
    legacy_protocol: str,
) -> None:
    with pytest.raises(ValueError, match="differs from the canonical preregistration"):
        validate_protocol_payload_v0_8(
            {
                "protocol": legacy_protocol,
                "content_sha256": content_sha256({"protocol": legacy_protocol}),
                "formal_gate_b_passed": True,
            }
        )
