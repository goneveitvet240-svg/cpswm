"""PC-B regression for the resealed event-chain ingestion finding.

The legal control and attack use the real frozen production fixture.  The
expected value comes from the runtime-owned source frame, not from a particle
readout produced after the call under test.
"""

from __future__ import annotations

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_particles import candidates

from cpswm.system.reproducibility import content_sha256


def _direct_arguments(core):
    arguments = candidates(core)
    revision_id = arguments["receipts"][0].proposal.proposed_state.revision_id
    history = core._event_histories[revision_id]
    event = core._observed_events[revision_id]
    chains = {chain.hypothesis_id: chain for chain in history.latest.hypotheses}
    source_frame = (
        {
            revision_id: (
                history,
                event.evidence,
                event.propensity_weight,
                event.regime_frame,
                event.identity_switch_probability,
            )
        },
        core.current_cause_snapshot,
    )
    return arguments, chains, source_frame


def _advance(core, arguments, chains, source_frame):
    return core._particle_workspace.advance(
        receipts=arguments["receipts"],
        statistics=arguments["statistics"],
        chains=chains,
        snapshot_id=core.current_snapshot.snapshot_id,
        allowed_locations=core._registered_particle_locations,
        source_frame=source_frame,
        ledger_head_sha256=core._hybrid_loop.ledger.export_state().manifest.head_hash,
        unresolved_log_weight=arguments["unresolved_log_weight"],
    )


def test_direct_workspace_rejects_resealed_chain_atomically_and_remains_usable():
    core = old._legacy_history(1).system.core
    workspace = core._particle_workspace
    arguments, chains, source_frame = _direct_arguments(core)
    before = content_sha256(workspace.state_payload())

    target = arguments["receipts"][0].proposal.proposed_state.event_hypothesis_id
    original = chains[target]
    forged = original.model_copy(
        update={"explanation_code": original.explanation_code + "-audit-forged"}
    )
    assert forged != original
    assert forged.hypothesis_id == original.hypothesis_id
    assert tuple(step.actor_key for step in forged.steps) == tuple(
        step.actor_key for step in original.steps
    )
    chains[target] = forged

    with pytest.raises(ValueError, match="differs from its runtime source history"):
        _advance(core, arguments, chains, source_frame)

    assert content_sha256(workspace.state_payload()) == before
    assert not workspace.records
    assert not workspace.input_journal
    assert core.stage_prepared_particle_candidates(**arguments).particle_weights
    assert core.prepared_particle_location_marginal()[1] > 0.0


def test_direct_workspace_legal_chain_control_is_nonempty():
    core = old._legacy_history(1).system.core
    arguments, chains, source_frame = _direct_arguments(core)
    batch = _advance(core, arguments, chains, source_frame)
    assert len(batch.particle_weights) == 2
    assert core._particle_workspace.state_payload()


def test_direct_workspace_detaches_accepted_chain_from_caller_alias():
    core = old._legacy_history(1).system.core
    workspace = core._particle_workspace
    arguments, chains, source_frame = _direct_arguments(core)
    target = arguments["receipts"][0].proposal.proposed_state.event_hypothesis_id
    caller_chain = chains[target]

    _advance(core, arguments, chains, source_frame)
    accepted = content_sha256(workspace.state_payload())
    object.__setattr__(
        caller_chain,
        "explanation_code",
        caller_chain.explanation_code + "-post-acceptance-alias-mutation",
    )

    assert content_sha256(workspace.state_payload()) == accepted
