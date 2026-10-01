"""Owned frame-pair association branches in the Native development posterior.

One reference-conditioned query transaction, not a temporal independence model.
The initial reference-to-semantic anchor, actors, spatial prior/residual and
utility remain controlled. RGB/geometry branch gates are uncalibrated energies;
position contributes a known/background likelihood ratio once per alternative.
"""

from __future__ import annotations

import inspect
from hashlib import sha256
from math import log, pi
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from cpswm.perception_mapping import appearance_geometry_association as association
from cpswm.perception_mapping import natural_vision, unity_rgbd
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system import natural_candidate_position as natural
from cpswm.system.controlled_position_producer import _helper_code_sha256, _require, packet_binding
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
)
from cpswm.system.native_joint_production import NativeJointContext, ProducedJointCandidates
from cpswm.system.natural_candidate_position import NaturalCandidatePositionProducer
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_conditional_updates import rebuild_conditional_state

PROFILE = "appearance-geometry-single-pair-raw@1"


def implementation_binding() -> str:
    _require(
        association.decode_rgb is natural_vision.decode_rgb, "appearance decoder alias changed"
    )
    _require(
        association.OBSERVATION_KEYS == natural.OBSERVATION_KEYS,
        "association observation keys changed",
    )
    return content_sha256(
        (
            PROFILE,
            association.MODEL,
            association.CONFIG,
            tuple(
                (
                    m.__name__,
                    sha256(Path(str(m.__file__)).read_bytes()).hexdigest(),
                    tuple(
                        (k, _helper_code_sha256(v.__code__))
                        for k, v in sorted(vars(m).items())
                        if inspect.isfunction(v) and v.__module__ == m.__name__
                    ),
                )
                for m in (association,)
            ),
            sha256(Path(__file__).read_bytes()).hexdigest(),
            tuple(
                (k, _helper_code_sha256(v.__code__))
                for k, v in sorted(globals().items())
                if inspect.isfunction(v) and v.__module__ == __name__
            ),
        )
    )


def background_logpdf(observation: dict[str, Any]) -> float:
    xyz = np.asarray(observation["world_point_m"])
    return float(-0.5 * (3 * log(2 * pi * 100.0) + np.dot(xyz, xyz) / 100.0))


class AppearanceGeometryPositionProducer(NaturalCandidatePositionProducer):
    def _content_binding(self) -> str:
        return content_sha256((PROFILE, super()._content_binding(), implementation_binding()))

    def _pair(self, context: NativeJointContext) -> dict[str, Any]:
        _, query_diagnostic = self._observation_and_diagnostic(context)
        update = context.observation_update
        assert update is not None
        ref = update.reference
        _require(ref is not None and ref.reference is None, "one original reference required")
        assert ref is not None
        _require(
            ref.action_id != update.action_id
            and ref.received_at <= update.decision_time
            and ref.semantic_revision_id == update.semantic_revision_id
            and ref.issued_source_id == update.issued_source_id
            and ref.original_parent_sha256 == update.original_parent_sha256
            and ref.original_runtime_id == update.original_runtime_id
            and ref.packet["scope"] == update.packet["scope"]
            and not set(ref.packet["observation_ids"]) & set(update.packet["observation_ids"]),
            "association reference is outside original query support",
        )
        lookup = {str(r.envelope().identity.observation_id): r for r in context.visible_prefix}
        _require(all(k in lookup for k in ref.packet["observation_ids"]), "reference raw missing")
        rows = tuple(lookup[k] for k in ref.packet["observation_ids"])
        _require(packet_binding(rows) == ref.packet, "original reference packet differs")
        camera, _ = unity_rgbd.decode_unity_rgbd(rows, cutoff=ref.received_at)
        _require(
            ref.decision_time <= camera.capture_time <= ref.received_at,
            "reference capture exceeds its original epoch",
        )
        reference = natural.candidate_readout(
            rows,
            cutoff=ref.received_at,
            weights_path=Path(self.configuration["weights_path"]),
            affinity_model=self.affinity_model,
            affinity_pin=self.affinity_pin,
            estimator=self.position_model["estimator"],
            raw_sha256=ref.packet["raw_sha256"],
        )
        query = query_diagnostic["natural_candidates"]
        ref_candidates = association.candidates(reference, rows[0], ref.received_at)
        query_candidates = association.candidates(
            query, lookup[update.packet["observation_ids"][0]], update.received_at
        )
        result = association.associate(ref_candidates, query_candidates)
        result.update(
            reference=reference,
            query=query,
            reference_candidates=ref_candidates,
            query_candidates=query_candidates,
            reference_action=str(ref.action_id),
            query_action=str(update.action_id),
        )
        return result

    def _position_record_ids(self, context: NativeJointContext) -> tuple[UUID, ...]:
        update = context.observation_update
        assert update is not None and update.reference is not None
        return tuple(
            UUID(k)
            for k in (
                *update.reference.packet["observation_ids"],
                *update.packet["observation_ids"],
            )
        )

    def produce(self, context: NativeJointContext) -> ProducedJointCandidates:
        if context.previous_batch is None:
            _require(context.observation_update is None, "association requires an actual parent")
            return super().produce(context)
        # Preserve each existing branch on later semantic advances. Never merge
        # alternatives by actor or multiply this frame pair again.
        binding = self.binding_sha256
        source = context.source
        source.validate_content()
        active = self._active(context)
        update = context.observation_update
        if update is not None:
            _require(
                self._selected(source)
                and update.semantic_revision_id == source.history_after.latest.revision_id,
                "association query requires its selected live semantic source",
            )
        _require(not active or not self.consumed_keys, "association pair already consumed")
        evidence = context.previous_weight_evidence
        _require(
            evidence is not None and evidence.batch() == context.previous_batch,
            "association requires actual prior log weights",
        )
        assert evidence is not None
        weights, aggregate = evidence.normalized_logs()
        pair = self._pair(context) if active else None
        cluster = self._cluster(context, binding)
        record_id = source.transition.after.metadata.record_id
        receipts, statistics, branches = [], {}, []
        for parent in sorted(
            (r for r in context.records if r.state.particle_id in weights),
            key=lambda r: str(r.state.particle_id),
        ):
            actor = parent.state.ordered_actor_roles[0].actor_key
            chains = [
                h
                for h in source.history_after.latest.hypotheses
                if len(h.steps) == 3 and h.responsible_actor_key == actor
            ]
            _require(len(chains) == 1, "association actor source is not uniquely supported")
            chain = chains[0]
            known = parent.state.instance_association_key != "unknown_instance"
            alternatives = (
                [(b["query_id"], b["observation"], b["log_gate"], True) for b in pair["branches"]]
                + [("unmatched", None, pair["unknown_log_gate"], False)]
                if pair is not None and known
                else [("preserve", None, 0.0, known)]
            )
            for key, observation, gate, associated in alternatives:
                prior = parent.statistics
                measure = self._neutral(prior, cluster, record_id)
                log_ratio = 0.0
                detail = None
                if observation is not None:
                    reference = dict(
                        reference_id=content_sha256(
                            (PROFILE, "controlled-origin-zero", self.position_pin)
                        ),
                        reference_kind=self.position_model["reference_kind"],
                        domain_id=observation["domain_id"],
                        frame_id=observation["frame_id"],
                        valid_at=observation["valid_at"],
                        xyz_m=[0.0, 0.0, 0.0],
                    )
                    measure, detail = position.condition(
                        self.position_model,
                        self.position_pin,
                        observation,
                        reference,
                        prior,
                        evidence_cluster_id=cluster,
                        source_record_ids=self._position_record_ids(context),
                    )
                    log_ratio = detail["observation_log_likelihood"] - background_logpdf(
                        observation
                    )
                analytic = rebuild_conditional_state(prior, (measure,))
                pid = content_uuid(PROFILE + ":branch", (cluster, parent.state.particle_id, key))
                statistics[pid] = analytic
                state = parent.state.model_copy(
                    update=dict(
                        particle_id=pid,
                        parent_particle_id=parent.state.particle_id,
                        parent_revision_id=parent.state.revision_id,
                        source_snapshot_id=source.snapshot_id,
                        event_hypothesis_id=chain.hypothesis_id,
                        revision_id=source.history_after.latest.revision_id,
                        ordered_actor_roles=tuple(
                            OrderedActorRole(role=r, actor_key=actor)
                            for r in ("pickup_actor", "carrier", "placer")
                        ),
                        instance_association_key=str(source.object_instance_id)
                        if associated
                        else "unknown_instance",
                        run_length=len(prior.evidence_cluster_ids),
                        statistic_state_ref=analytic.reference,
                        ledger_lineage_ref="hybrid-ledger:" + context.ledger_head_sha256,
                    )
                )
                receipts.append(
                    ParticleRevisionReceipt(
                        proposal=NeuralParticleProposal(
                            proposal_id=content_uuid(PROFILE + ":proposal", pid),
                            evidence_cluster_id=cluster,
                            operation="branch" if associated else "preserve_unresolved",
                            source_particle_id=parent.state.particle_id,
                            source_snapshot_id=source.snapshot_id,
                            proposed_state=state,
                            proposal_log_probability=0.0,
                            proposer_model_version="explicit-prepared-candidates@1",
                            proposer_code_version=PROFILE,
                        ),
                        prior_log_weight=weights[parent.state.particle_id],
                        # Observation-dependent routing is not a transition prior.
                        # One composite development potential; no independence claim.
                        transition_log_probability=0.0,
                        observation_log_likelihood=gate + log_ratio,
                        constraints=tuple(
                            StructuredConstraint(factor=f, accepted=True, log_potential=0.0)
                            for f in StructuredWeightFactor
                            if f.value.endswith("constraint")
                        ),
                    )
                )
                branches.append(
                    dict(
                        particle_id=str(pid),
                        parent=str(parent.state.particle_id),
                        query_id=key,
                        instance=state.instance_association_key,
                        log_gate=gate,
                        position_log_ratio=log_ratio,
                        position=detail,
                    )
                )
        result = ProducedJointCandidates(
            context.content_sha256,
            source.source_id,
            source.body_sha256,
            binding,
            tuple(receipts),
            statistics,
            aggregate,
        )
        self.calls += 1
        if active:
            self.consumed_keys.append(self._measurement_key())
        self.last_diagnostic = dict(
            active=active,
            association=pair,
            branches=branches,
            aggregate_log_weight=aggregate,
            semantic_anchor="CONTROLLED_INITIAL_REFERENCE_SET",
            density="SINGLE_COMPOSITE_UNCALIBRATED_FRAME_PAIR_POTENTIAL",
        )
        return result
