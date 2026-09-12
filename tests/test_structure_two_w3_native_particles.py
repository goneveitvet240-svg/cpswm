"""Explicit native prepared candidates; never a default neural/CIAV claim."""

import sys
from math import log
from uuid import UUID, uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_operator_acceptance import ActualCalls
from test_structure_two_w3_round5_boundaries import direct_outcome, state

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
    TypedParticleState,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import (
    ConditionalAnalyticState,
    NativeParticleWorkspace,
)
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


def candidates(core, step=0, q=0.25):
    rid = list(core._event_histories)[-1]
    histories = core._event_histories[rid].latest.hypotheses
    chains = [
        next(h for h in histories if len(h.steps) == 3 and h.responsible_actor_key == actor)
        for actor in ("owner", "unknown_actor")
    ]
    receipts, statistics = [], {}
    cluster_id = UUID(int=3000 + step)
    for index, chain in enumerate(chains):
        pid = UUID(int=1000 + step * 10 + index)
        parent = None if step == 0 else core._particle_workspace.batch.particle_weights[index]
        parent_clusters = (
            ()
            if parent is None
            else core._particle_workspace.records[
                parent.particle_id
            ].statistics.evidence_cluster_ids
        )
        analytic = ConditionalAnalyticState(
            core.locations,
            (4.0, 1.0, 1.0, 1.0),
            ((2.0, 0.0), (0.0, 2.0)),
            (1.0, 2.0),
            ((3.0, 0.0), (0.0, 3.0)),
            (2.0, 1.0),
            (*parent_clusters, cluster_id),
        )
        statistics[pid] = analytic
        typed = TypedParticleState(
            particle_id=pid,
            parent_particle_id=None if parent is None else parent.particle_id,
            parent_revision_id=None
            if parent is None
            else core._particle_workspace.records[parent.particle_id].state.revision_id,
            source_snapshot_id=core.current_snapshot.snapshot_id,
            event_hypothesis_id=chain.hypothesis_id,
            revision_id=rid,
            ordered_actor_roles=tuple(
                OrderedActorRole(role=role, actor_key=chain.responsible_actor_key)
                for role in ("pickup_actor", "carrier", "placer")
            ),
            instance_association_key=str(core.object_instance_id)
            if index == 0
            else "unknown_instance",
            change_cause="unresolved",
            regime_decision="unresolved",
            regime_id=None,
            run_length=step,
            statistic_state_ref=analytic.reference,
            ledger_lineage_ref="hybrid-ledger:"
            + core._hybrid_loop.ledger.export_state().manifest.head_hash,
        )
        proposal = NeuralParticleProposal(
            proposal_id=UUID(int=2000 + step * 10 + index),
            evidence_cluster_id=cluster_id,
            operation="preserve_unresolved" if step == 0 else "branch",
            source_particle_id=typed.parent_particle_id,
            source_snapshot_id=typed.source_snapshot_id,
            proposed_state=typed,
            proposal_log_probability=log(q if index == 0 else 1 - q),
            proposer_model_version="explicit-prepared-candidates@1",
            proposer_code_version="r5-fixture",
        )
        receipts.append(
            ParticleRevisionReceipt(
                proposal=proposal,
                prior_log_weight=0.0 if parent is None else log(parent.posterior_probability),
                transition_log_probability=0.0,
                observation_log_likelihood=0.0,
                constraints=tuple(
                    StructuredConstraint(factor=f, accepted=True, log_potential=0.0)
                    for f in StructuredWeightFactor
                    if f.value.endswith("constraint")
                ),
            )
        )
    return dict(receipts=tuple(receipts), statistics=statistics, unresolved_log_weight=0.0)


def edit(arguments, **updates):
    receipts = list(arguments["receipts"])
    raw = receipts[0].model_dump()
    for key, value in updates.items():
        if key in raw:
            raw[key] = value
        elif key in raw["proposal"]:
            raw["proposal"][key] = value
        else:
            raw["proposal"]["proposed_state"][key] = value
    receipts[0] = ParticleRevisionReceipt.model_construct(
        **{
            **receipts[0].__dict__,
            "proposal": NeuralParticleProposal.model_construct(
                **{
                    **receipts[0].proposal.__dict__,
                    **{k: v for k, v in raw["proposal"].items() if k != "proposed_state"},
                    "proposed_state": TypedParticleState.model_construct(
                        **raw["proposal"]["proposed_state"]
                    ),
                }
            ),
            **{k: v for k, v in raw.items() if k not in {"proposal", "constraints"}},
        }
    )
    return {**arguments, "receipts": tuple(receipts)}


def test_native_cross_step_ancestry_and_actual_log_q_consumer():
    probe = old._legacy_history(1)
    core = probe.system.core
    ws = core._particle_workspace
    arguments = candidates(core)
    before = core._hybrid_loop.ledger.export_state()
    with ActualCalls(ws.advance, ws.location_marginal) as calls:
        first = core.stage_prepared_particle_candidates(**arguments)
        distribution, unresolved = core.prepared_particle_location_marginal()
    assert {r[0] for r in calls.rows} == {"advance", "location_marginal"}
    assert first.particle_weights[0].posterior_probability == pytest.approx(4 / (4 + 4 / 3 + 1))
    assert sum(distribution.values()) + unresolved == pytest.approx(1.0) and unresolved > 0
    assert content_sha256(core._hybrid_loop.ledger.export_state()) == content_sha256(before)
    saved = state(core)
    assert core.stage_prepared_particle_candidates(**arguments) == first
    assert state(core) == saved
    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    with pytest.raises(ValueError, match="stale"):
        core.prepared_particle_location_marginal()
    second = core.stage_prepared_particle_candidates(**candidates(core, step=1))
    assert core._particle_workspace is ws and len(ws.records) == 4
    for weight in second.particle_weights:
        record = ws.records[weight.particle_id]
        parent = ws.records[record.state.parent_particle_id]
        assert len(record.event_chain_history) == 2
        assert record.event_chain_history[0] == parent.event_chain_history[0]
        assert record.state.parent_revision_id == parent.state.revision_id
        assert record.statistics.reference == record.state.statistic_state_ref
        assert all(
            getattr(record.statistics, f)
            for f in ("alpha", "a", "b", "information", "information_vector")
        )
    assert core.prepared_particle_location_marginal()[1] > 0
    semantic_memory_state(core)


def test_log_q_and_constraint_interventions_change_only_prepared_readout():
    outputs = []
    for q, rejected in ((0.25, False), (0.75, False), (0.25, True)):
        core = old._legacy_history(1).system.core
        arguments = candidates(core, q=q)
        before = content_sha256(core._hybrid_loop.ledger.export_state())
        action = core.action_location_distribution(core.current_snapshot)
        if rejected:
            receipt = arguments["receipts"][0]
            constraints = list(receipt.constraints)
            constraints[0] = StructuredConstraint(
                factor=constraints[0].factor,
                accepted=False,
                log_potential=0.0,
                rejection_reason="explicit prepared counterexample",
            )
            arguments["receipts"] = (
                receipt.model_copy(update={"constraints": tuple(constraints)}),
                arguments["receipts"][1],
            )
        batch = core.stage_prepared_particle_candidates(**arguments)
        outputs.append(core.prepared_particle_location_marginal())
        assert content_sha256(core._hybrid_loop.ledger.export_state()) == before
        assert core.action_location_distribution(core.current_snapshot) == action
        if rejected:
            assert batch.particle_weights[0].posterior_probability == 0.0
            assert core._particle_workspace.receipts[0].constraints[0].rejection_reason
    assert outputs[0][0][next(iter(outputs[0][0]))] > outputs[1][0][next(iter(outputs[1][0]))]
    assert outputs[2][1] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "fault",
    [
        "snapshot",
        "chain",
        "roles",
        "instance",
        "parent",
        "statistics",
        "ledger",
        "neural",
        "reactivate",
        "rejuvenate",
        "nan",
        "self_parent",
        "unknown_support",
        "stat_nan",
    ],
)
def test_public_prepared_boundary_rejects_without_mutation(fault):
    core = old._legacy_history(1).system.core
    args = candidates(core)
    if fault == "snapshot":
        args = edit(args, source_snapshot_id=uuid4())
    elif fault == "chain":
        args = edit(args, event_hypothesis_id=uuid4())
    elif fault == "roles":
        args = edit(args, ordered_actor_roles=())
    elif fault == "instance":
        args = edit(args, instance_association_key="foreign")
    elif fault == "parent":
        args = edit(args, parent_revision_id=uuid4())
    elif fault == "statistics":
        args = edit(args, statistic_state_ref="missing")
    elif fault == "ledger":
        args = edit(args, ledger_lineage_ref="hybrid-ledger:" + "f" * 64)
    elif fault == "neural":
        args = edit(args, proposer_model_version="unselected-neural-artifact")
    elif fault in ("reactivate", "rejuvenate"):
        args = edit(args, operation=fault)
    elif fault == "nan":
        args = edit(args, proposal_log_probability=float("nan"))
    elif fault == "self_parent":
        args = edit(
            args, parent_particle_id=args["receipts"][0].proposal.proposed_state.particle_id
        )
    elif fault == "unknown_support":
        args["receipts"] = args["receipts"][:1]
    elif fault == "stat_nan":
        analytic = next(iter(args["statistics"].values()))
        object.__setattr__(analytic, "alpha", (float("nan"), 1.0, 1.0, 1.0))
    before = state(core)
    with pytest.raises(ValueError):
        core.stage_prepared_particle_candidates(**args)
    assert state(core) == before


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
def test_actual_prepared_call_interruption_is_atomic_and_retryable(exception):
    core = old._legacy_history(1).system.core
    args = candidates(core)
    ws = core._particle_workspace
    code = ws.advance.__func__.__code__
    before = state(core)

    def profile(frame, event, value):
        if frame.f_code is code and event == "return":
            raise exception("actual advance interrupted")

    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        with pytest.raises(exception, match="actual advance interrupted"):
            core.stage_prepared_particle_candidates(**args)
    finally:
        sys.setprofile(previous)
    assert core._particle_workspace is ws and state(core) == before
    assert core.stage_prepared_particle_candidates(**args).particle_weights


def test_public_correction_invalidates_native_parent_and_refuses_unselected_replay():
    core = old._legacy_history(1).system.core
    args = candidates(core)
    core.stage_prepared_particle_candidates(**args)
    target = next(iter(core._committed_events))
    core.apply_event_revision_outcome(direct_outcome(core, target))
    assert target in core._particle_workspace.invalidated_revisions
    with pytest.raises(ValueError):
        core.prepared_particle_location_marginal()
    with pytest.raises(ValueError):
        core.stage_prepared_particle_candidates(**args)


@pytest.mark.parametrize("attack", ["instance", "method"])
def test_native_identity_guards_preserve_actual_implementation(attack, monkeypatch):
    core = old._legacy_history(1).system.core
    args = candidates(core)
    if attack == "instance":
        monkeypatch.setattr(core, "_particle_workspace", NativeParticleWorkspace())
    else:
        monkeypatch.setattr(core._particle_workspace, "advance", core._particle_workspace.advance)
    with pytest.raises(ValueError, match=r"replaced|shadowed"):
        core.stage_prepared_particle_candidates(**args)


def test_prepared_semantic_identity_preserves_raw_references_across_runs():
    states = []
    executions = []
    for _ in range(2):
        probe = old._legacy_history(1)
        core = probe.system.core
        core.stage_prepared_particle_candidates(**candidates(core))
        probe.system.core.process_transition(probe.transition_for(probe.observed_days()[1]))
        core.stage_prepared_particle_candidates(**candidates(core, step=1))
        states.append(content_sha256(semantic_memory_state(core)))
        executions.append(state(core))
    assert states[0] == states[1] and executions[0] != executions[1]
