"""Owned multi-capture development inference with persistent identity alternatives.

Natural pixel tracks supply candidate surface observations. The initial semantic
anchor, spatial prior and unknown prior are controlled. A static shared-bias
model handles temporal correlation; its fraction is explicit and uncalibrated.
Track loss is missing information, never an absence or automatic reassociation.
"""

from __future__ import annotations

import inspect
from copy import deepcopy
from hashlib import sha256
from math import log
from pathlib import Path
from typing import Any
from uuid import UUID

from cpswm.data_preflight import soft_surface_position
from cpswm.perception_mapping import (
    natural_target_sequence,
    natural_vision,
    temporal_position,
    unity_rgbd,
    visual_target_tracking,
)
from cpswm.system.controlled_position_producer import _helper_code_sha256, _require, packet_binding
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
)
from cpswm.system.native_joint_production import (
    NativeJointContext,
    NativeObservationUpdate,
    ProducedJointCandidates,
)
from cpswm.system.natural_candidate_position import (
    OBSERVATION_KEYS,
    NaturalCandidatePositionProducer,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

PROFILE = "natural-target-temporal-joint-raw@1"


class TemporalTargetPositionProducer(NaturalCandidatePositionProducer):
    profile_id = PROFILE

    def _validate_configuration(self) -> None:
        c = self.configuration
        _require(
            set(c)
            == {
                "semantic_record_id",
                "enabled",
                "weights_path",
                "shared_fraction",
                "unknown_prior",
            },
            "explicit temporal configuration required",
        )
        base = {k: v for k, v in c.items() if k not in ("shared_fraction", "unknown_prior")}
        self.configuration = base
        try:
            super()._validate_configuration()
        finally:
            self.configuration = c
        _require(
            type(c["shared_fraction"]) is float and 0 <= c["shared_fraction"] < 1,
            "invalid shared noise fraction",
        )
        _require(
            type(c["unknown_prior"]) is float and 0 < c["unknown_prior"] < 1,
            "finite unknown support required",
        )

    def _content_binding(self) -> str:
        _require(
            vars(natural_target_sequence)["InitializedPixelTargetTracker"]
            is visual_target_tracking.InitializedPixelTargetTracker
            and vars(natural_target_sequence)["decode_rgb"] is natural_vision.decode_rgb
            and vars(natural_target_sequence)["NaturalAppearanceDetector"]
            is natural_vision.NaturalAppearanceDetector,
            "temporal perception alias changed",
        )
        modules = (natural_target_sequence, temporal_position, visual_target_tracking)
        bodies: list[tuple[str, ...]] = []
        for module in modules:
            for name, value in sorted(vars(module).items()):
                if inspect.isfunction(value):
                    bodies.append((module.__name__, name, _helper_code_sha256(value.__code__)))
                elif inspect.isclass(value) and value.__module__ == module.__name__:
                    for key, item in sorted(vars(value).items()):
                        body = item.fget if isinstance(item, property) else item
                        if inspect.isfunction(body):
                            bodies.append(
                                (module.__name__, name, key, _helper_code_sha256(body.__code__))
                            )
        return content_sha256(
            (
                PROFILE,
                super()._content_binding(),
                sha256(Path(__file__).read_bytes()).hexdigest(),
                bodies,
                natural_target_sequence.MINIMUM_PATCH_CORRELATION,
                temporal_position.MODEL,
                tuple(
                    (m.__name__, sha256(Path(str(m.__file__)).read_bytes()).hexdigest())
                    for m in modules
                ),
            )
        )

    def checkpoint_state(self) -> dict[str, Any]:
        return dict(
            binding=self.binding_sha256,
            calls=self.calls,
            consumed_keys=deepcopy(self.consumed_keys),
            last_diagnostic=deepcopy(self.last_diagnostic),
            captures=deepcopy(getattr(self, "_captures", [])),
            branches=deepcopy(getattr(self, "_branches", {})),
        )

    def restore_state(self, state: dict[str, Any]) -> None:
        _require(
            type(state) is dict
            and set(state)
            == {"binding", "calls", "consumed_keys", "last_diagnostic", "captures", "branches"}
            and state["binding"] == self.binding_sha256
            and type(state["calls"]) is int
            and state["calls"] >= 0,
            "invalid temporal checkpoint",
        )
        captures = state["captures"]
        _require(
            type(captures) is list
            and all(type(c) is NativeObservationUpdate for c in captures)
            and state["consumed_keys"] == [c.logical_key for c in captures]
            and len(set(state["consumed_keys"])) == len(captures)
            and type(state["branches"]) is dict,
            "temporal capture history differs",
        )
        self.calls, self.consumed_keys, self.last_diagnostic = deepcopy(
            (state["calls"], state["consumed_keys"], state["last_diagnostic"])
        )
        self._captures, self._branches = deepcopy((captures, state["branches"]))

    def recompute_updates(
        self, context: NativeJointContext, predecessors: tuple[NativeJointContext, ...]
    ) -> ProducedJointCandidates:
        _require(self.calls == 0 and not self.consumed_keys, "temporal verifier must start fresh")
        # Each canonical predecessor contains all earlier records. This is a
        # topological order, independent of set/dictionary iteration and wall time.
        ordered = sorted(predecessors, key=lambda c: len(c.records))
        _require(
            len({len(c.records) for c in ordered}) == len(ordered), "ambiguous predecessor order"
        )
        # Earlier analytic states/weights are independently validated by the
        # workspace. Reconstruct only branch identities and accepted captures;
        # never trust the mutable producer checkpoint or caller-supplied boxes.
        mapping: dict[str, Any] = {}
        captures: list[NativeObservationUpdate] = []
        anchors = []
        for prior in ordered:
            if prior.previous_batch is None:
                continue
            active = self._active(prior)
            first = not captures
            if active and first:
                anchors = sorted(self._sequence(prior)["history"])
            evidence = prior.previous_weight_evidence
            _require(evidence is not None, "temporal predecessor weights missing")
            assert evidence is not None
            weights, _ = evidence.normalized_logs()
            cluster = self._cluster(prior, self.binding_sha256)
            for parent in prior.records:
                if parent.state.particle_id not in weights:
                    continue
                known = parent.state.instance_association_key != "unknown_instance"
                if active and known:
                    keys = (
                        [*anchors, "unmatched"]
                        if first
                        else [mapping.get(str(parent.state.particle_id))]
                    )
                    _require(
                        all(type(k) is str for k in keys), "temporal predecessor identity missing"
                    )
                else:
                    keys = ["preserve"]
                for key in keys:
                    pid = content_uuid(
                        self.profile_id + ":branch", (cluster, parent.state.particle_id, key)
                    )
                    mapping[str(pid)] = (
                        key
                        if active and known and key != "unmatched"
                        else mapping.get(str(parent.state.particle_id))
                    )
            if active:
                assert prior.observation_update is not None
                captures.append(prior.observation_update)
        self._branches = mapping
        self._captures = captures
        self.consumed_keys = [c.logical_key for c in captures]
        return self.produce(context)

    def _sequence(self, context: NativeJointContext) -> dict[str, Any]:
        update = context.observation_update
        assert update is not None
        captures = [*getattr(self, "_captures", []), update]
        _require(
            len({c.logical_key for c in captures}) == len(captures), "capture already consumed"
        )
        _require(
            all(c.semantic_revision_id == update.semantic_revision_id for c in captures),
            "temporal static sequence crosses semantic revision",
        )
        lookup = {str(r.envelope().identity.observation_id): r for r in context.visible_prefix}
        _require(len(lookup) == len(context.visible_prefix), "duplicate visible raw identity")
        tracker = natural_target_sequence.NaturalTargetSequence(
            weights_path=Path(self.configuration["weights_path"])
        )
        history: dict[str, list[dict[str, Any]]] = {}
        signatures: dict[str, set[str]] = {}
        records = []
        for capture in captures:
            keys = capture.packet["observation_ids"]
            _require(all(k in lookup for k in keys), "temporal raw prefix missing")
            rows = tuple(lookup[k] for k in keys)
            _require(packet_binding(rows) == capture.packet, "temporal packet binding differs")
            camera, depth = unity_rgbd.decode_unity_rgbd(rows, cutoff=capture.received_at)
            _require(
                capture.decision_time <= camera.capture_time <= capture.received_at,
                "temporal capture epoch differs",
            )
            _, rgb = natural_vision.decode_rgb(rows[0], cutoff=capture.received_at)
            record = tracker.observe(rows[0], cutoff=capture.received_at)
            candidates = [
                dict(method=PROFILE, id=t["anchor_id"], box=list(t["box_xyxy"]))
                for t in record["tracks"]
                if t["status"] == "PIXEL_SUPPORTED"
            ]
            surface = soft_surface_position.readout_frame(
                rgb,
                depth,
                camera,
                candidates,
                self.affinity_model,
                self.affinity_pin,
                provenance=dict(
                    source_sha256=capture.packet["raw_sha256"],
                    receipt_sha256=rows[0].capture_receipt_sha256,
                    observation_ids=keys,
                    payload_sha256=[sha256(r.payload_bytes).hexdigest() for r in rows],
                ),
            )
            signature = content_sha256(
                camera.model_dump(mode="json", exclude={"action_id", "capture_time"})
            )
            current = {}
            for track in record["tracks"]:
                anchor = track["anchor_id"]
                history.setdefault(anchor, [])
                signatures.setdefault(anchor, set())
                eligible = [
                    s
                    for s in surface["seeds"]
                    if s["valid"] and any(p["id"] == anchor for p in s["sources"])
                ]
                obs = None
                if eligible and signature not in signatures[anchor]:
                    seed = min(eligible, key=lambda s: tuple(s["pixel_uv"]))
                    item = next(
                        o
                        for o in surface["observations"]
                        if o["seed_id"] == seed["seed_id"]
                        and o["estimator"] == self.position_model["estimator"]
                    )
                    obs = {k: item[k] for k in OBSERVATION_KEYS}
                    history[anchor].append(obs)
                    signatures[anchor].add(signature)
                current[anchor] = obs
            record["new_position_observations"] = current
            record["unique_position_counts"] = {k: len(v) for k, v in history.items()}
            records.append(record)
        return dict(records=records, history=history, current=current, captures=captures)

    def _condition_observation(
        self,
        sequence: dict[str, Any],
        key: str,
        prior: ConditionalAnalyticState,
        cluster: UUID,
        record_id: UUID,
    ) -> tuple[ConditionalMeasurement, dict[str, Any]]:
        return temporal_position.condition(
            self.position_model,
            self.position_pin,
            sequence["history"][key],
            prior,
            rho=self.configuration["shared_fraction"],
            evidence_cluster_id=cluster,
            source_record_ids=tuple(
                UUID(k) for c in sequence["captures"] for k in c.packet["observation_ids"]
            ),
        )

    def produce(self, context: NativeJointContext) -> ProducedJointCandidates:
        if context.previous_batch is None:
            _require(
                context.observation_update is None, "temporal observation requires an actual parent"
            )
            return super().produce(context)
        # Preserve each existing branch on later semantic advances. Never merge
        # identity alternatives by actor or multiply an old capture again.
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
        evidence = context.previous_weight_evidence
        _require(
            evidence is not None and evidence.batch() == context.previous_batch,
            "association requires actual prior log weights",
        )
        assert evidence is not None
        weights, aggregate = evidence.normalized_logs()
        sequence = self._sequence(context) if active else None
        mapping = deepcopy(getattr(self, "_branches", {}))
        first = not self.consumed_keys
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
            if sequence is not None and known and first:
                anchors = sorted(sequence["history"])
                u = self.configuration["unknown_prior"]
                alternatives = [
                    (k, sequence["current"][k], log((1 - u) / len(anchors)), True) for k in anchors
                ]
                alternatives.append(("unmatched", None, log(u) if anchors else 0.0, False))
            elif sequence is not None and known:
                anchor = mapping.get(str(parent.state.particle_id))
                _require(anchor in sequence["history"], "temporal branch ancestry missing")
                alternatives = [(anchor, sequence["current"][anchor], 0.0, True)]
            else:
                alternatives = [("preserve", None, 0.0, known)]
            for key, observation, gate, associated in alternatives:
                prior = parent.statistics
                measure = self._neutral(prior, cluster, record_id)
                log_ratio = 0.0
                detail = None
                if observation is not None:
                    assert sequence is not None
                    measure, detail = self._condition_observation(
                        sequence, key, prior, cluster, record_id
                    )
                    log_ratio = detail["log_ratio"]
                analytic = rebuild_conditional_state(prior, (measure,))
                pid = content_uuid(
                    self.profile_id + ":branch", (cluster, parent.state.particle_id, key)
                )
                statistics[pid] = analytic
                mapping[str(pid)] = (
                    key
                    if sequence is not None and associated
                    else mapping.get(str(parent.state.particle_id))
                )
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
                            proposal_id=content_uuid(self.profile_id + ":proposal", pid),
                            evidence_cluster_id=cluster,
                            operation="branch" if associated else "preserve_unresolved",
                            source_particle_id=parent.state.particle_id,
                            source_snapshot_id=source.snapshot_id,
                            proposed_state=state,
                            proposal_log_probability=0.0,
                            proposer_model_version="explicit-prepared-candidates@1",
                            proposer_code_version=self.profile_id,
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
            assert update is not None and sequence is not None
            self.consumed_keys.append(update.logical_key)
            self._captures = sequence["captures"]
        self._branches = mapping
        self.last_diagnostic = dict(
            active=active,
            sequence=sequence,
            branches=branches,
            aggregate_log_weight=aggregate,
            semantic_anchor="CONTROLLED_INITIAL_REFERENCE_SET",
            density="CONDITIONAL_SHARED_BIAS_COMPOSITE_DEVELOPMENT",
        )
        return result
