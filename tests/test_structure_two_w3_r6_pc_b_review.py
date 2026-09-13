"""Independent PC-B adversarial checks for the W3 R6 input boundary."""

from dataclasses import replace
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_particles import candidates

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRevisionReceipt,
)


def _replace_statistic(arguments, index, statistic) -> None:
    receipt = arguments["receipts"][index]
    particle_id = receipt.proposal.proposed_state.particle_id
    arguments["statistics"][particle_id] = statistic
    raw = receipt.model_dump()
    raw["proposal"]["proposed_state"]["statistic_state_ref"] = statistic.reference
    receipts = list(arguments["receipts"])
    receipts[index] = ParticleRevisionReceipt.model_validate(raw)
    arguments["receipts"] = tuple(receipts)


def test_legal_prepared_input_control_is_preserved() -> None:
    """The public R6 stage/readout path still accepts its legal control."""

    probe = old._legacy_history(1)
    core = probe.system.core
    registered_locations = core.locations

    batch = core.stage_prepared_particle_candidates(**candidates(core))
    probabilities, unresolved = core.prepared_particle_location_marginal()

    assert batch.particle_weights
    assert set(probabilities) == set(registered_locations)
    assert sum(probabilities.values()) + unresolved == pytest.approx(1.0)


def test_prepared_support_is_bound_to_the_constructed_world() -> None:
    """A reassigned public tuple must not become registered world authority."""

    probe = old._legacy_history(1)
    core = probe.system.core
    original_locations = core.locations
    foreign_location = uuid4()

    assert foreign_location not in core._habit._locations
    assert foreign_location not in core._embeddings

    # The W3 R6 public entry currently forwards this mutable attribute as the
    # authority set, although the rest of the runtime still has the original
    # construction-time world support.
    core.locations = (*original_locations[:-1], foreign_location)

    with pytest.raises(ValueError, match=r"support|location|binding"):
        core.stage_prepared_particle_candidates(**candidates(core))


def test_prepared_readout_rejects_a_rebound_world_support() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    original_locations = core.locations
    core.stage_prepared_particle_candidates(**candidates(core))

    core.locations = tuple(uuid4() for _ in original_locations)

    with pytest.raises(ValueError, match=r"support|location|binding|stale"):
        core.prepared_particle_location_marginal()


def test_particle_parent_and_child_cannot_switch_world_support() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    original_locations = core.locations
    core.stage_prepared_particle_candidates(**candidates(core))
    core.process_transition(probe.transition_for(probe.observed_days()[1]))

    core.locations = tuple(uuid4() for _ in original_locations)

    with pytest.raises(ValueError, match=r"support|location|binding|parent"):
        core.stage_prepared_particle_candidates(**candidates(core, step=1))


def test_conditional_statistics_are_bound_to_the_receipt_cluster() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    arguments = candidates(core)
    receipt = arguments["receipts"][0]
    particle_id = receipt.proposal.proposed_state.particle_id
    foreign_cluster = uuid4()
    statistic = replace(
        arguments["statistics"][particle_id],
        evidence_cluster_ids=(foreign_cluster,),
    )
    _replace_statistic(arguments, 0, statistic)

    assert foreign_cluster != receipt.proposal.evidence_cluster_id
    with pytest.raises(ValueError, match=r"cluster|statistic|lineage"):
        core.stage_prepared_particle_candidates(**arguments)


def test_unreferenced_statistics_cannot_enter_the_persisted_input_body() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    arguments = candidates(core)
    extra_particle = uuid4()
    template = next(iter(arguments["statistics"].values()))
    arguments["statistics"][extra_particle] = replace(
        template,
        locations=tuple(uuid4() for _ in template.locations),
        evidence_cluster_ids=(uuid4(),),
    )

    with pytest.raises(ValueError, match=r"candidate|particle|statistic|unreferenced"):
        core.stage_prepared_particle_candidates(**arguments)
