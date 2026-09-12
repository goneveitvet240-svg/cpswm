"""PC-B repair-side regression matrix for the five prepared-particle boundaries.

These checks deliberately distinguish the public prepared-candidate API from
direct internal-state attacks.  They preserve legal prepared inputs while
requiring runtime world support, evidence-cluster lineage, and receipt/statistic
closure to fail closed.  They are repair-side tests, not an independent signoff.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import asdict, replace
from math import fsum
from uuid import UUID, uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_particles import candidates
from test_structure_two_w3_round5_boundaries import state

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRevisionReceipt,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import (
    ConditionalAnalyticState,
    native_content_sha256,
)


def _observable(core) -> tuple[object, ...]:
    """Capture persistent effects, including the noncommitting prepared seam."""

    workspace = core._particle_workspace
    return (
        state(core),
        id(workspace),
        native_content_sha256(workspace.state_payload()),
        content_sha256(core._hybrid_loop.ledger.export_state()),
        core.action_location_distribution(core.current_snapshot),
    )


def _assert_mass(core) -> tuple[dict[UUID, float], float]:
    probabilities, unresolved = core.prepared_particle_location_marginal()
    assert fsum((*probabilities.values(), unresolved)) == pytest.approx(1.0)
    assert unresolved > 0.0
    return probabilities, unresolved


def _replace_receipt(
    arguments,
    index: int,
    *,
    proposal_updates: dict[str, object] | None = None,
    state_updates: dict[str, object] | None = None,
    receipt_updates: dict[str, object] | None = None,
) -> None:
    """Apply an attack and fully revalidate all public receipt contracts."""

    raw = arguments["receipts"][index].model_dump(mode="python")
    raw.update(receipt_updates or {})
    raw["proposal"].update(proposal_updates or {})
    raw["proposal"]["proposed_state"].update(state_updates or {})
    receipts = list(arguments["receipts"])
    receipts[index] = ParticleRevisionReceipt.model_validate(raw)
    arguments["receipts"] = tuple(receipts)


def _reseal_statistic(
    arguments,
    index: int,
    *,
    locations: tuple[UUID, ...] | None = None,
    alpha: tuple[float, ...] | None = None,
    clusters: tuple[UUID, ...] | None = None,
    bypass_duplicate_constructor: bool = False,
) -> ConditionalAnalyticState:
    """Replace a statistic and reseal the state reference in its receipt."""

    receipt = arguments["receipts"][index]
    particle_id = receipt.proposal.proposed_state.particle_id
    original = arguments["statistics"][particle_id]
    updates = {
        "locations": original.locations if locations is None else locations,
        "alpha": original.alpha if alpha is None else alpha,
        "evidence_cluster_ids": (
            original.evidence_cluster_ids if clusters is None else clusters
        ),
    }
    if bypass_duplicate_constructor:
        statistic = deepcopy(original)
        for name, value in updates.items():
            object.__setattr__(statistic, name, value)
    else:
        statistic = replace(original, **updates)
    arguments["statistics"][particle_id] = statistic
    _replace_receipt(
        arguments,
        index,
        state_updates={"statistic_state_ref": statistic.reference},
    )
    assert (
        arguments["receipts"][index].proposal.proposed_state.statistic_state_ref
        == statistic.reference
    )
    return statistic


def _second_generation():
    probe = old._legacy_history(1)
    core = probe.system.core
    core.stage_prepared_particle_candidates(**candidates(core))
    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    return probe, core, candidates(core, step=1)


def _reject_without_effect_then_retry(core, bad, good, *, match: str) -> None:
    before = _observable(core)
    with pytest.raises(ValueError, match=match):
        core.stage_prepared_particle_candidates(**bad)
    assert _observable(core) == before

    batch = core.stage_prepared_particle_candidates(**good)
    assert batch.particle_weights
    _assert_mass(core)
    accepted = _observable(core)
    assert core.stage_prepared_particle_candidates(**good) == batch
    assert _observable(core) == accepted


def test_legal_initial_unknown_unresolved_and_idempotent_replay() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    arguments = candidates(core)
    workspace = core._particle_workspace

    batch = core.stage_prepared_particle_candidates(**arguments)
    probabilities, unresolved = _assert_mass(core)

    assert set(probabilities) == set(core.locations)
    assert batch.unresolved_probability > 0.0
    assert any(
        record.state.instance_association_key == "unknown_instance"
        for record in workspace.records.values()
    )
    assert any(
        role.actor_key == "unknown_actor"
        for record in workspace.records.values()
        for role in record.state.ordered_actor_roles
    )
    assert unresolved > batch.unresolved_probability

    accepted = _observable(core)
    assert core.stage_prepared_particle_candidates(**arguments) == batch
    assert _observable(core) == accepted


def test_legal_zero_increment_second_generation_still_appends_cluster() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    workspace = core._particle_workspace
    first = core.stage_prepared_particle_candidates(**candidates(core))
    parent_ids = tuple(weight.particle_id for weight in first.particle_weights)
    parent_records = {pid: workspace.records[pid] for pid in parent_ids}

    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    arguments = candidates(core, step=1)
    current_cluster = arguments["receipts"][0].proposal.evidence_cluster_id
    second = core.stage_prepared_particle_candidates(**arguments)

    for parent_id, weight in zip(parent_ids, second.particle_weights, strict=True):
        parent = parent_records[parent_id]
        child = workspace.records[weight.particle_id]
        assert child.state.parent_particle_id == parent_id
        for field in ("locations", "alpha", "a", "b", "information", "information_vector"):
            assert getattr(child.statistics, field) == getattr(parent.statistics, field)
        assert child.statistics.evidence_cluster_ids == (
            *parent.statistics.evidence_cluster_ids,
            current_cluster,
        )
        assert child.evidence_cluster_id == current_cluster
    _assert_mass(core)


def test_legal_location_alpha_pair_reordering_preserves_the_marginal() -> None:
    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    original = arguments["statistics"][
        arguments["receipts"][0].proposal.proposed_state.particle_id
    ]
    paired = tuple(zip(original.locations, original.alpha, strict=True))
    _reseal_statistic(
        arguments,
        0,
        locations=original.locations[::-1],
        alpha=original.alpha[::-1],
    )

    batch = core.stage_prepared_particle_candidates(**arguments)
    probabilities, unresolved = _assert_mass(core)
    known = batch.particle_weights[0].posterior_probability
    total_alpha = fsum(alpha for _, alpha in paired)
    for location, alpha in paired:
        assert probabilities[location] == pytest.approx(known * alpha / total_alpha)
    assert unresolved == pytest.approx(1.0 - known)


def test_legal_siblings_may_share_one_statistic_object_and_reference() -> None:
    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    particle_ids = tuple(
        receipt.proposal.proposed_state.particle_id for receipt in arguments["receipts"]
    )
    shared = arguments["statistics"][particle_ids[0]]
    arguments["statistics"][particle_ids[1]] = shared

    assert arguments["statistics"][particle_ids[0]] is arguments["statistics"][particle_ids[1]]
    assert all(
        receipt.proposal.proposed_state.statistic_state_ref == shared.reference
        for receipt in arguments["receipts"]
    )
    batch = core.stage_prepared_particle_candidates(**arguments)

    assert batch.particle_weights
    assert all(
        core._particle_workspace.records[particle_id].statistics == shared
        for particle_id in particle_ids
    )
    _assert_mass(core)


def _shared_projection_arguments(core, *, step: int = 0, source=None):
    source = core.current_posterior_projection_source() if source is None else source
    arguments = candidates(core, step=step)
    first, unknown = arguments["receipts"]
    first_particle_id = first.proposal.proposed_state.particle_id

    sibling_particle_id = UUID(int=901_001 + step)
    sibling_state = first.proposal.proposed_state.model_copy(
        update={"particle_id": sibling_particle_id}
    )
    sibling_proposal = first.proposal.model_copy(
        update={
            "proposal_id": UUID(int=902_001 + step),
            "proposed_state": sibling_state,
        }
    )
    sibling = ParticleRevisionReceipt.model_validate(
        first.model_copy(update={"proposal": sibling_proposal}).model_dump(mode="python")
    )
    arguments["statistics"][sibling_particle_id] = arguments["statistics"][first_particle_id]

    projected = []
    for receipt in (first, sibling):
        projected.append(
            ParticleRevisionReceipt.model_validate(
                receipt.model_copy(
                    update={
                        "observation_log_likelihood": 0.0,
                        "posterior_projection_log_factor": source.log_factor(receipt),
                        "evidence_semantics": "posterior_projection_not_likelihood",
                        "source_posterior_snapshot_id": source.source_id,
                    }
                ).model_dump(mode="python")
            )
        )
    arguments["receipts"] = (*projected, unknown)
    return arguments, source


def test_one_posterior_source_may_weight_multiple_siblings_in_one_batch() -> None:
    """One observation source is shared evidence, not consumed per candidate row."""

    core = old._legacy_history(1).system.core
    arguments, source = _shared_projection_arguments(core)

    batch = core.stage_prepared_particle_candidates(**arguments)
    assert len(batch.particle_weights) == 3
    assert core._particle_workspace.consumed_posterior_sources == {
        source.source_id: batch.evidence_cluster_id
    }
    assert all(weight.posterior_probability > 0.0 for weight in batch.particle_weights)
    _assert_mass(core)


def test_one_posterior_source_cannot_be_recounted_in_a_later_batch() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    first, source = _shared_projection_arguments(core)
    core.stage_prepared_particle_candidates(**first)
    before = _observable(core)

    reused, _ = _shared_projection_arguments(core, step=1, source=source)
    with pytest.raises(ValueError, match=r"already consumed|previous batch|recount"):
        core.stage_prepared_particle_candidates(**reused)
    assert _observable(core) == before

    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    fresh, fresh_source = _shared_projection_arguments(core, step=1)
    assert fresh_source.source_id != source.source_id
    assert core.stage_prepared_particle_candidates(**fresh).particle_weights
    _assert_mass(core)


@pytest.mark.parametrize("replacement", ["foreign", "reordered"])
@pytest.mark.parametrize("surface", ["stage", "readout", "parent", "replay"])
def test_public_support_rebinding_fails_closed_on_every_surface(
    replacement: str, surface: str
) -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    original_locations = core.locations

    if surface in {"readout", "parent", "replay"}:
        first_arguments = candidates(core)
        core.stage_prepared_particle_candidates(**first_arguments)
    if surface == "parent":
        core.process_transition(probe.transition_for(probe.observed_days()[1]))
        arguments = candidates(core, step=1)
    elif surface == "replay":
        arguments = first_arguments
    else:
        arguments = candidates(core)

    before = _observable(core)
    rebound = (
        tuple(uuid4() for _ in original_locations)
        if replacement == "foreign"
        else original_locations[::-1]
    )
    core.locations = rebound
    try:
        with pytest.raises(ValueError, match=r"support|location|binding"):
            if surface == "readout":
                core.prepared_particle_location_marginal()
            else:
                core.stage_prepared_particle_candidates(**arguments)
    finally:
        core.locations = original_locations

    assert _observable(core) == before
    if surface in {"stage", "parent"}:
        core.stage_prepared_particle_candidates(**arguments)
    else:
        _assert_mass(core)


@pytest.mark.parametrize("fault", ["foreign", "missing", "reordered", "duplicate"])
def test_fully_resealed_false_cluster_lineage_is_rejected_and_retryable(fault: str) -> None:
    _, core, good = _second_generation()
    bad = deepcopy(good)
    statistic = bad["statistics"][
        bad["receipts"][0].proposal.proposed_state.particle_id
    ]
    lineage = statistic.evidence_cluster_ids
    assert len(lineage) == 2 and lineage[0] != lineage[1]
    attacked = {
        "foreign": (lineage[0], uuid4()),
        "missing": lineage[:-1],
        "reordered": lineage[::-1],
        "duplicate": (lineage[0], lineage[0]),
    }[fault]
    resealed = _reseal_statistic(
        bad,
        0,
        clusters=attacked,
        bypass_duplicate_constructor=fault == "duplicate",
    )

    # The attack is not a stale reference: the attacker recomputed the full
    # conditional-statistic digest and resealed the public particle state.
    assert (
        bad["receipts"][0].proposal.proposed_state.statistic_state_ref
        == resealed.reference
    )
    _reject_without_effect_then_retry(
        core,
        bad,
        good,
        match=r"cluster|lineage|statistic",
    )


def _closure_attack(arguments, fault: str) -> None:
    receipts = arguments["receipts"]
    particle_ids = tuple(r.proposal.proposed_state.particle_id for r in receipts)
    if fault == "extra":
        arguments["statistics"][uuid4()] = deepcopy(arguments["statistics"][particle_ids[0]])
    elif fault == "missing":
        arguments["statistics"].pop(particle_ids[0])
    elif fault == "both":
        arguments["statistics"].pop(particle_ids[0])
        arguments["statistics"][uuid4()] = deepcopy(arguments["statistics"][particle_ids[1]])
    elif fault == "duplicate_particle":
        arguments["statistics"].pop(particle_ids[1])
        _replace_receipt(
            arguments,
            1,
            state_updates={
                "particle_id": particle_ids[0],
                "statistic_state_ref": arguments["statistics"][particle_ids[0]].reference,
            },
        )
    elif fault == "duplicate_proposal":
        _replace_receipt(
            arguments,
            1,
            proposal_updates={"proposal_id": receipts[0].proposal.proposal_id},
        )
    elif fault == "mixed_snapshot":
        foreign_snapshot = uuid4()
        _replace_receipt(
            arguments,
            1,
            proposal_updates={"source_snapshot_id": foreign_snapshot},
            state_updates={"source_snapshot_id": foreign_snapshot},
        )
    elif fault == "mixed_cluster":
        foreign_cluster = uuid4()
        _reseal_statistic(arguments, 1, clusters=(foreign_cluster,))
        _replace_receipt(
            arguments,
            1,
            proposal_updates={"evidence_cluster_id": foreign_cluster},
        )
    else:  # pragma: no cover - keeps the attack table total.
        raise AssertionError(fault)


@pytest.mark.parametrize(
    "fault,match",
    [
        ("extra", r"closure|unreferenced|statistic"),
        ("missing", r"closure|missing|statistic"),
        ("both", r"closure|missing|unreferenced|statistic"),
        ("duplicate_particle", r"duplicate particle|unique"),
        ("duplicate_proposal", r"duplicate proposal|unique"),
        ("mixed_snapshot", r"snapshot"),
        ("mixed_cluster", r"cluster"),
    ],
)
def test_receipt_statistic_input_closure_attacks_are_atomic(
    fault: str, match: str
) -> None:
    core = old._legacy_history(1).system.core
    good = candidates(core)
    bad = deepcopy(good)
    _closure_attack(bad, fault)

    _reject_without_effect_then_retry(core, bad, good, match=match)


def test_caller_alias_mutation_before_acceptance_is_revalidated_atomically() -> None:
    core = old._legacy_history(1).system.core
    good = candidates(core)
    bad = deepcopy(good)
    particle_ids = tuple(
        receipt.proposal.proposed_state.particle_id for receipt in bad["receipts"]
    )
    shared = bad["statistics"][particle_ids[0]]
    bad["statistics"][particle_ids[1]] = shared
    object.__setattr__(shared, "alpha", (9.0, 1.0, 1.0, 1.0))

    # Both receipts retain the old reference; changing their shared caller
    # object immediately before the call cannot smuggle it into the workspace.
    assert any(
        receipt.proposal.proposed_state.statistic_state_ref != shared.reference
        for receipt in bad["receipts"]
    )
    _reject_without_effect_then_retry(
        core,
        bad,
        good,
        match=r"statistic|reference|lineage",
    )


def test_caller_alias_mutation_after_acceptance_cannot_change_or_block_replay() -> None:
    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    batch = core.stage_prepared_particle_candidates(**arguments)
    accepted = _observable(core)
    accepted_marginal = _assert_mass(core)

    caller_statistic = next(iter(arguments["statistics"].values()))
    object.__setattr__(caller_statistic, "alpha", (99.0, 1.0, 1.0, 1.0))
    object.__setattr__(
        arguments["receipts"][0].proposal.proposed_state,
        "statistic_state_ref",
        "caller-tampered-after-acceptance",
    )
    arguments["statistics"].clear()

    assert _assert_mass(core) == accepted_marginal
    assert _observable(core) == accepted

    fresh_equivalent = candidates(core)
    assert core.stage_prepared_particle_candidates(**fresh_equivalent) == batch
    assert _observable(core) == accepted


class _SelfMutatingStatisticMap(dict):
    """A caller mapping that changes itself as its first items view is consumed."""

    def __init__(self, source):
        super().__init__(source)
        self.items_calls = 0

    def items(self):
        self.items_calls += 1
        if self.items_calls != 1:
            raise AssertionError("statistics mapping was read more than once")
        rows = tuple(super().items())

        def mutate_after_rows():
            yield from rows
            self.clear()
            self[uuid4()] = rows[0][1]

        return mutate_after_rows()


class _DuplicateStatisticItems(dict):
    def items(self):
        rows = tuple(super().items())
        return (rows[0], rows[0])


def test_statistics_mapping_toctou_is_bound_to_one_detached_snapshot() -> None:
    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    original_particle_ids = set(arguments["statistics"])
    volatile = _SelfMutatingStatisticMap(arguments["statistics"])
    arguments["statistics"] = volatile

    batch = core.stage_prepared_particle_candidates(**arguments)

    assert volatile.items_calls == 1
    assert set(volatile) != original_particle_ids
    assert set(core._particle_workspace.records) == original_particle_ids
    assert batch.particle_weights
    _assert_mass(core)


def test_statistics_mapping_duplicate_items_are_rejected_before_persistence() -> None:
    core = old._legacy_history(1).system.core
    good = candidates(core)
    bad = {**good, "statistics": _DuplicateStatisticItems(good["statistics"])}
    _reject_without_effect_then_retry(core, bad, good, match=r"duplicate|closure")


def test_cross_runtime_record_transplant_is_rejected_even_with_current_batch_snapshot() -> None:
    donor = old._legacy_history(1).system.core
    donor.stage_prepared_particle_candidates(**candidates(donor))
    receiver = old._legacy_history(1).system.core
    donor_workspace = donor._particle_workspace
    receiver_workspace = receiver._particle_workspace

    receiver_workspace.records = deepcopy(donor_workspace.records)
    receiver_workspace.batch = donor_workspace.batch.model_copy(
        update={"snapshot_id": receiver.current_snapshot.snapshot_id}
    )
    receiver_workspace.receipts = deepcopy(donor_workspace.receipts)
    receiver_workspace.input_journal = deepcopy(donor_workspace.input_journal)
    receiver_workspace.input_bodies = deepcopy(donor_workspace.input_bodies)
    assert all(
        record.workspace_runtime_id == donor_workspace.runtime_id
        for record in receiver_workspace.records.values()
    )
    assert receiver_workspace.runtime_id != donor_workspace.runtime_id

    with pytest.raises(ValueError, match=r"runtime|binding|support"):
        receiver.prepared_particle_location_marginal()


@pytest.mark.parametrize("fault", ["support_hash", "record_statistic"])
def test_direct_private_single_field_tampering_fails_closed(fault: str) -> None:
    core = old._legacy_history(1).system.core
    core.stage_prepared_particle_candidates(**candidates(core))
    workspace = core._particle_workspace
    expected_marginal = _assert_mass(core)

    if fault == "support_hash":
        original = workspace._world_support_sha256
        workspace._world_support_sha256 = "f" * 64 if original != "f" * 64 else "e" * 64
        try:
            with pytest.raises(ValueError, match=r"support|binding"):
                core.prepared_particle_location_marginal()
        finally:
            workspace._world_support_sha256 = original
    else:
        record = next(iter(workspace.records.values()))
        original = record.statistics
        tampered = replace(
            original,
            alpha=(original.alpha[0] + 1.0, *original.alpha[1:]),
        )
        object.__setattr__(record, "statistics", tampered)
        try:
            with pytest.raises(ValueError, match=r"record|binding|statistic"):
                core.prepared_particle_location_marginal()
        finally:
            object.__setattr__(record, "statistics", original)

    assert _assert_mass(core) == expected_marginal


@pytest.mark.parametrize(
    "fault",
    ["journal_digest", "journal_body", "batch", "receipts", "consumption"],
)
def test_persisted_workspace_tampering_blocks_semantic_readout(fault: str) -> None:
    core = old._legacy_history(1).system.core
    core.stage_prepared_particle_candidates(**candidates(core))
    workspace = core._particle_workspace
    backup = deepcopy(workspace)
    ledger_sha256 = content_sha256(core._hybrid_loop.ledger.export_state())
    cluster = workspace.batch.evidence_cluster_id

    if fault == "journal_digest":
        workspace.input_journal[cluster] = "f" * 64
    elif fault == "journal_body":
        body = workspace.input_bodies[cluster]
        particle_id = next(iter(body.statistics))
        statistic = body.statistics[particle_id]
        body.statistics[particle_id] = replace(
            statistic,
            alpha=(statistic.alpha[0] + 1.0, *statistic.alpha[1:]),
        )
    elif fault == "batch":
        workspace.batch = workspace.batch.model_copy(
            update={"particle_weights": workspace.batch.particle_weights[::-1]}
        )
    elif fault == "receipts":
        workspace.receipts = workspace.receipts[::-1]
    else:
        workspace.consumed_posterior_sources[uuid4()] = cluster

    with pytest.raises(ValueError, match=r"prepared|journal|batch|receipt|source|state"):
        core.semantic_memory_identity()
    assert content_sha256(core._hybrid_loop.ledger.export_state()) == ledger_sha256

    # This is test-only repair of the deliberately corrupted private state.
    vars(workspace).clear()
    vars(workspace).update(deepcopy(vars(backup)))
    assert core._particle_workspace is workspace
    _assert_mass(core)


@pytest.mark.parametrize(
    "fault",
    [
        "delete_historical_record",
        "inject_orphan_record",
        "reseal_source_frame",
        "empty_chain_history",
        "clear_projection_consumption",
    ],
)
def test_persisted_cross_relations_are_rechecked_on_direct_readout(fault: str) -> None:
    if fault == "delete_historical_record":
        _, core, second = _second_generation()
        current = core.stage_prepared_particle_candidates(**second)
        current_ids = {weight.particle_id for weight in current.particle_weights}
    elif fault == "clear_projection_consumption":
        core = old._legacy_history(1).system.core
        projected, _ = _shared_projection_arguments(core)
        core.stage_prepared_particle_candidates(**projected)
        current_ids = set()
    else:
        core = old._legacy_history(1).system.core
        core.stage_prepared_particle_candidates(**candidates(core))
        current_ids = set()

    workspace = core._particle_workspace
    backup = deepcopy(workspace)
    expected_marginal = _assert_mass(core)
    ledger_sha256 = content_sha256(core._hybrid_loop.ledger.export_state())

    if fault == "delete_historical_record":
        historical_ids = set(workspace.records) - current_ids
        assert historical_ids
        del workspace.records[next(iter(historical_ids))]
    elif fault == "inject_orphan_record":
        original = next(iter(workspace.records.values()))
        orphan_id = uuid4()
        orphan_state = original.state.model_copy(update={"particle_id": orphan_id})
        workspace.records[orphan_id] = replace(original, state=orphan_state)
    elif fault == "reseal_source_frame":
        particle_id, original = next(iter(workspace.records.items()))
        foreign_frame = ("fully-resealed-foreign-frame", deepcopy(original.source_frame))
        workspace.records[particle_id] = replace(
            original,
            source_frame=foreign_frame,
            source_frame_sha256=native_content_sha256(foreign_frame),
        )
    elif fault == "empty_chain_history":
        particle_id, original = next(iter(workspace.records.items()))
        workspace.records[particle_id] = replace(original, event_chain_history=())
    else:
        assert workspace.consumed_posterior_sources
        workspace.consumed_posterior_sources.clear()

    with pytest.raises(ValueError, match=r"prepared|record|journal|parent|source|chain"):
        core.prepared_particle_location_marginal()
    assert content_sha256(core._hybrid_loop.ledger.export_state()) == ledger_sha256

    vars(workspace).clear()
    vars(workspace).update(deepcopy(vars(backup)))
    assert _assert_mass(core) == expected_marginal


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
@pytest.mark.parametrize("step", [0, 1])
def test_actual_advance_return_interruption_rolls_back_and_is_retryable(
    exception: type[BaseException], step: int
) -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    if step:
        core.stage_prepared_particle_candidates(**candidates(core))
        core.process_transition(probe.transition_for(probe.observed_days()[1]))
    arguments = candidates(core, step=step)
    workspace = core._particle_workspace
    advance_code = workspace.advance.__func__.__code__
    before = _observable(core)

    def interrupt_after_real_advance(frame, event, value):
        if frame.f_code is advance_code and event == "return":
            raise exception("interrupt after actual prepared commit boundary")

    previous = sys.getprofile()
    try:
        sys.setprofile(interrupt_after_real_advance)
        with pytest.raises(exception, match="prepared commit boundary"):
            core.stage_prepared_particle_candidates(**arguments)
    finally:
        sys.setprofile(previous)

    assert core._particle_workspace is workspace
    assert _observable(core) == before
    batch = core.stage_prepared_particle_candidates(**arguments)
    assert batch.particle_weights
    _assert_mass(core)
    accepted = _observable(core)
    assert core.stage_prepared_particle_candidates(**arguments) == batch
    assert _observable(core) == accepted


def test_conditional_state_copy_is_content_based_not_object_identity_based() -> None:
    """Document the trust contract used by the legal sibling-alias control."""

    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    particle_ids = tuple(arguments["statistics"])
    first = arguments["statistics"][particle_ids[0]]
    second = ConditionalAnalyticState(**asdict(first))
    assert first == second and first is not second and first.reference == second.reference
    arguments["statistics"][particle_ids[1]] = second

    assert core.stage_prepared_particle_candidates(**arguments).particle_weights
    _assert_mass(core)
