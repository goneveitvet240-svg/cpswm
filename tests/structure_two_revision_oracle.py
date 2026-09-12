"""Frozen-input revision reference; never reads final membership to define expectations.

Independence: own operation journal, own storage/replay traversal and scalar Hybrid
sum; fresh leaf CCRR, Dirichlet and RLS implementations are shared dependencies.
This detects integration, membership and accounting errors, not errors common to
those leaf models, perception, or historical custody before the journal freeze.
"""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from math import log, tanh

import numpy as np
import pytest

from cpswm.system.continual.execution_feedback_projector import ExecutionFeedbackProjector
from cpswm.system.continual.project_one_regime_loop import (
    AutomaticCFBOCPDCCRRRouter,
    HabitStateConclusion,
    PrototypeStatisticOperation,
)
from cpswm.system.continual.rls import RLSHabitScoreHead, RLSRegimeBank
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import native_content_sha256
from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    HierarchicalDirichletHabitModel,
)


class FrozenRevisionOracle:
    def __init__(self, probe):
        core = probe.system.core
        self.core_ref = core
        self.frozen_current_events = deepcopy(core._observed_events)
        self.parent_events = deepcopy(core._revision_parent_events)
        self.raw_eligibility = deepcopy(core._write_eligibility)
        self.baseline_operations = tuple(core.revision_transactions)
        self.cancellations = deepcopy(core._correction_cancellations)
        corrected_ids = {op.corrected_revision_id for op in self.baseline_operations}
        # Recover original inputs from the retained pre-revision records. Never
        # infer missing parents from the system's final membership or statistics.
        self.events = {
            rid: deepcopy(event)
            for rid, event in {**self.frozen_current_events, **self.parent_events}.items()
            if rid not in corrected_ids
        }
        self.eligibility = {
            rid: deepcopy(core.observation_write_eligibility(rid)) for rid in self.events
        }
        self.locations = tuple(core.locations)
        self.owner = core.owner_key
        self.object_id = core.object_instance_id
        self.config = deepcopy(core.loop_config)
        self.embeddings = deepcopy(core._embeddings)
        self.operations = []
        self.projector = ExecutionFeedbackProjector()
        self.authorized = []
        self._validate_frozen_lineage()

    def _validate_frozen_lineage(self):
        operations = {}
        consumed = set()
        for op_index, op in enumerate(self.baseline_operations, 1):
            assert op.superseded_revision_id not in consumed, "duplicate historical operation"
            consumed.add(op.superseded_revision_id)
            assert op.superseded_revision_id in self.parent_events, "missing original parent input"
            assert op.evidence_source_record_ids, "missing historical evidence"
            if op.kind.value == "correct":
                assert op.corrected_revision_id not in operations, "duplicate corrected identity"
                operations[op.corrected_revision_id] = op
            for cancellation in self.cancellations:
                if cancellation.after_operation_count != op_index:
                    continue
                request = cancellation.request
                request_body = {
                    "kind": request.kind.value,
                    "superseded_revision_id": str(request.superseded_revision_id),
                    "corrected_revision_id": str(request.corrected_revision_id),
                    "event_hypothesis_id": str(request.event_hypothesis_id),
                    "owner_key": request.owner_key,
                    "object_instance_id": str(request.object_instance_id),
                    "location_id": str(request.location_id),
                    "owner_mass_before": repr(float(request.owner_mass_before)),
                    "owner_mass_after": repr(float(request.owner_mass_after)),
                    "owner_mass_delta": repr(float(request.owner_mass_delta)),
                    "source_feedback_record_id": str(request.source_feedback_record_id),
                }
                assert (
                    cancellation.request_fingerprint
                    == hashlib.sha256(json.dumps(request_body, sort_keys=True).encode()).hexdigest()
                )
                assert cancellation.body_sha256 == native_content_sha256(
                    (
                        cancellation.request_fingerprint,
                        request,
                        cancellation.parent_event,
                        cancellation.corrected_event,
                        cancellation.after_operation_count,
                        cancellation.trigger_revision_id,
                        cancellation.rationale,
                        cancellation.restore_events,
                        cancellation.restore_fast_events,
                    )
                ), "invalid cancellation body"
                rid = request.corrected_revision_id
                assert rid in operations, "cancellation without correction"
                correction = operations[rid]
                assert correction.superseded_revision_id == request.superseded_revision_id
                assert (
                    cancellation.parent_event == self.parent_events[request.superseded_revision_id]
                )
                assert cancellation.corrected_event.revision_id == rid
                assert correction.corrected_location_id == request.location_id
                assert correction.corrected_owner_mass == request.owner_mass_after
                assert correction.evidence_source_record_ids == (request.source_feedback_record_id,)
                assert cancellation.trigger_revision_id in (
                    self.frozen_current_events.keys() | self.parent_events.keys()
                ), "cancellation without trigger"
                assert request.superseded_revision_id in consumed
                consumed.remove(request.superseded_revision_id)
        assert all(
            0 < c.after_operation_count <= len(self.baseline_operations) for c in self.cancellations
        )
        assert len({c.corrected_event.revision_id for c in self.cancellations}) == len(
            self.cancellations
        )
        visiting, checked = set(), set()

        def visit(rid):
            assert rid not in visiting, "cyclic qualification lineage"
            if rid in checked:
                return
            assert rid in self.raw_eligibility, "missing historical qualification"
            row = self.raw_eligibility[rid]
            assert row.revision_id == rid, "wrong qualification reference"
            visiting.add(rid)
            if row.parent_revision_id is not None:
                visit(row.parent_revision_id)
                parent = self.raw_eligibility[row.parent_revision_id]
                assert row.parent_eligibility_sha256 == content_sha256(parent), (
                    "forged parent qualification"
                )
                assert rid in operations, "missing historical correction operation"
                op = operations[rid]
                assert op.superseded_revision_id == row.parent_revision_id, "wrong parent reference"
                assert op.evidence_source_record_ids == row.correction_evidence_source_record_ids
                assert row.correction_outcome_sha256 == content_sha256(op)
                assert row.origin_path == "formal_correction_transaction"
                formal = [
                    g for g in row.authorizations if g.authority == "formal_correction_transaction"
                ]
                assert len(formal) == 1
                grant = formal[0]
                assert grant.authority == "formal_correction_transaction"
                assert grant.granting_revision_id == row.parent_revision_id
                assert grant.basis_sha256 == content_sha256(op)
                for additional in row.authorizations:
                    if additional is grant:
                        continue
                    assert additional.authority == "ccrr_habit_change_promotion"
                    basis = json.loads(additional.basis_json)
                    assert additional.basis_sha256 == content_sha256(basis)
                    assert basis["conclusion"] == "habit_change"
                    assert additional.granting_revision_id in self.raw_eligibility
                    assert not self.raw_eligibility[
                        additional.granting_revision_id
                    ].origin_write_blocked
            else:
                assert row.origin_path != "formal_correction_transaction", (
                    "missing correction parent"
                )
                for grant in row.authorizations:
                    basis = json.loads(grant.basis_json)
                    assert grant.basis_sha256 == content_sha256(basis)
                    if grant.authority == "ccrr_habit_change_promotion":
                        assert basis["conclusion"] == "habit_change"
                        assert basis["ccrr_decision"] in ("create", "reactivate")
                        assert grant.granting_revision_id in self.raw_eligibility
                        assert not self.raw_eligibility[
                            grant.granting_revision_id
                        ].origin_write_blocked
                    elif grant.authority == "unblocked_transition_commit":
                        assert not row.origin_write_blocked
                        assert grant.granting_revision_id == rid
                        assert basis["allow_long_term_write"] or not basis["rgrc_gate_enabled"]
                    elif grant.authority == "ccrr_rebuild_replay_promotion":
                        assert not row.origin_write_blocked and grant.granting_revision_id is None
                        assert (
                            content_sha256(tuple(basis["observation_log_revision_ids"]))
                            == basis["observation_log_sha256"]
                        )
                    else:
                        raise AssertionError("unknown historical authority")
            visiting.remove(rid)
            checked.add(rid)

        for rid in self.raw_eligibility:
            visit(rid)

    def prepare(self, bundle, policy):
        feedback, binding, model = bundle
        projected = self.projector.prepare_execution_feedback(
            feedback=feedback, binding=binding, likelihood_model=model
        )
        interpretation = policy.interpret(feedback=feedback, projected=projected)
        return feedback, projected, interpretation

    def accept(self, core, prepared):
        feedback, projected, interpretation = prepared
        if projected.is_replay:
            return
        expected = interpretation.operation
        journal = tuple(core.revision_transactions)
        if expected not in (
            PrototypeStatisticOperation.CORRECT,
            PrototypeStatisticOperation.RETRACT,
        ):
            assert journal == (*self.baseline_operations, *self.operations)
            self.projector.commit_execution_feedback(projected)
            return
        assert len(journal) == len(self.baseline_operations) + len(self.operations) + 1, (
            "missing or duplicated revision transaction"
        )
        assert journal[:-1] == (*self.baseline_operations, *self.operations)
        operation = journal[-1]
        assert operation.kind.value == expected.value
        assert operation.superseded_revision_id == interpretation.target_revision_id
        assert operation.evidence_source_record_ids == (feedback.metadata.record_id,)
        if expected is PrototypeStatisticOperation.CORRECT:
            assert operation.corrected_revision_id not in self.events
            assert operation.corrected_location_id == interpretation.corrected_location_id
            assert operation.corrected_owner_mass == interpretation.evidence_strength
        self.operations.append(operation)
        self.authorized.append(deepcopy(interpretation))
        self.projector.commit_execution_feedback(projected)

    def reference(self):
        events = deepcopy(self.events)
        eligibility = deepcopy(self.eligibility)
        self._validate_frozen_lineage()
        for operation_index, operation in enumerate(
            (*self.baseline_operations, *self.operations), 1
        ):
            assert operation.superseded_revision_id in events, "operation outside frozen journal"
            parent = events.pop(operation.superseded_revision_id)
            if operation.kind.value == "correct":
                mass = operation.corrected_owner_mass
                posterior = parent.evidence.actor_posterior
                alternatives = {key: value for key, value in posterior.items() if key != self.owner}
                total = sum(alternatives.values())
                corrected = {self.owner: mass}
                if total:
                    corrected.update(
                        {key: (1 - mass) * value / total for key, value in alternatives.items()}
                    )
                elif mass < 1:
                    corrected["unknown_actor"] = 1 - mass
                weight = mass * parent.evidence.effective_training_weight * parent.propensity_weight
                rid = operation.corrected_revision_id
                events[rid] = replace(
                    parent,
                    revision_id=rid,
                    evidence=parent.evidence.model_copy(
                        update={
                            "location_id": operation.corrected_location_id,
                            "actor_posterior": corrected,
                            "source_record_ids": tuple(
                                dict.fromkeys(
                                    parent.evidence.source_record_ids
                                    + operation.evidence_source_record_ids
                                )
                            ),
                        }
                    ),
                    location_id=operation.corrected_location_id,
                    owner_mass=mass,
                    statistical_owner_weight=weight,
                    source_record_id=operation.evidence_source_record_ids[0],
                    rls_sample=replace(
                        parent.rls_sample,
                        target_location_id=operation.corrected_location_id,
                        gate=weight,
                    ),
                )
                eligibility[rid] = deepcopy(eligibility[parent.revision_id])
            for cancellation in self.cancellations:
                if cancellation.after_operation_count != operation_index:
                    continue
                request = cancellation.request
                assert request.corrected_revision_id in events, (
                    "cancelled child absent from journal"
                )
                events.pop(request.corrected_revision_id)
                # The frozen pre-correction input is the reference, never the
                # system's final observed/committed event or model value.
                events[request.superseded_revision_id] = deepcopy(
                    self.parent_events[request.superseded_revision_id]
                )

        def eligible(rid):
            row = eligibility[rid]
            assert row is not None, "missing frozen eligibility"
            if not row["origin_write_blocked"]:
                return True
            return any(
                grant["authority"] == "ccrr_habit_change_promotion"
                and grant["granting_revision_id"] in {str(key) for key in events}
                and content_sha256(grant["basis"]) == grant["basis_sha256"]
                for grant in row["authorizations"]
            )

        router = AutomaticCFBOCPDCCRRRouter(
            object_instance_id=self.object_id,
            actor_id=self.owner,
            owner_actor_id=self.owner,
            config=self.config,
        )

        def habit_model():
            return HierarchicalDirichletHabitModel(
                locations=self.locations, resident_actor_keys=(self.owner,)
            )

        def bank():
            return RLSRegimeBank(
                head_factory=lambda: RLSHabitScoreHead(
                    context_feature_dim=1,
                    location_embedding_dim=len(self.locations),
                    forgetting_factor=self.config.forgetting_factor,
                )
            )

        habit, rls = habit_model(), bank()
        survivors, pending, assignments = {}, [], {}
        previous = None

        def commit(event, regime):
            assignments[event.revision_id] = regime
            if not eligible(event.revision_id):
                return
            event = replace(event, rls_sample=replace(event.rls_sample, regime_id=regime))
            survivors[event.revision_id] = event
            habit.update_audited(event.evidence, weight_multiplier=event.propensity_weight)
            rls.update(event.rls_sample, self.embeddings)

        for event in sorted(
            events.values(), key=lambda item: (item.evidence.event_time, str(item.revision_id))
        ):
            regime = router.ccrr.active_regime(
                object_instance_id=self.object_id, actor_id=self.owner
            )
            prediction = habit.predict(
                household_id=event.evidence.metadata.household_id,
                person_id=self.owner,
                object_instance_id=self.object_id,
                context_key=event.evidence.context_key,
            )
            scores = rls.score_candidates(
                object_instance_id=self.object_id,
                actor_id=self.owner,
                context_features=event.rls_sample.context_features,
                candidate_locations=self.locations,
                location_embeddings=self.embeddings,
                regime_id=regime,
            )
            # Independently stated scalar surprise equation, shared frozen calibration.
            excess = max(
                0.0,
                -log(max(1e-12, prediction.probabilities[event.location_id]))
                / log(len(self.locations))
                - 1.0,
            )
            surprise = 1.0 - np.exp(-excess)
            residual = min(1.0, abs(1.0 - scores[event.location_id]))
            changed = float(previous is not None and previous != event.location_id)
            move = changed * (1 - (1 - surprise) * (1 - residual) ** 2)
            signals = dict(event.regime_frame.signals)
            signals[ChangeCause.ACTOR] = 1 - event.owner_mass
            signals[ChangeCause.HABIT] = max(
                move,
                self.config.dirichlet_surprise_weight * surprise,
                self.config.rls_residual_weight * residual,
            )
            assessment = router.observe(
                frame=CauseSignalFrame(timestamp=event.evidence.event_time, signals=signals),
                state_key=f"{event.location_id}|{event.evidence.context_key}",
                context_features=(
                    *(float(loc == event.location_id) for loc in self.locations),
                    tanh(float(event.rls_sample.context_features[0])),
                ),
                owner_probability=event.owner_mass,
                evidence_source_record_ids=event.evidence.source_record_ids,
                identity_switch_probability=event.identity_switch_probability,
            )
            active = router.ccrr.active_regime(
                object_instance_id=self.object_id, actor_id=self.owner
            )
            if assessment.conclusion is HabitStateConclusion.HABIT_CHANGE:
                for item in pending:
                    commit(item, active)
                pending.clear()
                commit(event, active)
            elif (
                assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
                and not assessment.allow_long_term_write
            ):
                pending.append(event)
                assignments[event.revision_id] = assessment.old_regime
            else:
                pending.clear()
                if assessment.allow_long_term_write:
                    commit(event, active)
            previous = event.location_id
        # The final stores are reconstructed in chronological order, independently
        # from the prefix models used to classify each observation.
        final_habit, final_rls = habit_model(), bank()
        for rid in sorted(
            survivors, key=lambda rid: (survivors[rid].evidence.event_time, str(rid))
        ):
            item = survivors[rid]
            final_habit.update_audited(item.evidence, weight_multiplier=item.propensity_weight)
            final_rls.update(item.rls_sample, self.embeddings)
        return survivors, final_habit, final_rls

    def check(self, probe):
        core = probe.system.core
        assert core._correction_cancellations == self.cancellations, (
            "cancellation log changed after freeze"
        )
        assert tuple(core.revision_transactions) == (*self.baseline_operations, *self.operations), (
            "unvalidated or missing operation log"
        )
        expected, habit, rls = self.reference()
        assert set(core._committed_events) == set(expected), "live revision membership mismatch"
        for rid, event in expected.items():
            actual = core._committed_events[rid]
            assert actual.location_id == event.location_id, "wrong location"
            assert actual.statistical_owner_weight == pytest.approx(
                event.statistical_owner_weight
            ), "wrong weight"
            assert actual.evidence.actor_posterior == pytest.approx(event.evidence.actor_posterior)
            assert actual.source_record_id == event.source_record_id, "wrong correction source"
            assert actual.evidence.source_record_ids == event.evidence.source_record_ids, (
                "wrong observation evidence lineage"
            )
            records = core._hybrid_loop.ledger.live_promoted_records_for_revision(
                actual.hybrid_revision_id or rid
            )
            assert len(records) == int(event.statistical_owner_weight > 1e-12), (
                "ledger multiplicity"
            )
        for location in self.locations:
            mass = sum(
                item.statistical_owner_weight
                for item in expected.values()
                if item.location_id == location
            )
            assert core.hybrid_alpha(location) == pytest.approx(mass, abs=1e-9), (
                "Hybrid mass mismatch"
            )
        assert core._habit.canonical_state_hash() == habit.canonical_state_hash(), (
            "Dirichlet mismatch"
        )
        for regime in set(rls._heads) | set(core._regimes._heads):
            assert content_sha256(core.rls_regime_snapshot(regime)) == content_sha256(
                rls.regime_snapshot(regime)
            ), "RLS mismatch"
        return expected
