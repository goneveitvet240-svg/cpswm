"""Controlled raw RGB-D position consumer; no natural identity or live default.

The world/association, detector box and single seed are declared fixtures. Only
the context's admitted, externally bound packet may supply the measurement.
Unknown particle and residual unresolved bucket use the same declared world
metre density N(0, 100 I3). They are not empirically calibrated clutter models.
"""

from __future__ import annotations

import inspect
import marshal
from copy import deepcopy
from hashlib import sha256
from math import isfinite, log, pi
from pathlib import Path
from uuid import UUID

import numpy as np

from cpswm.data_preflight import instance_affinity, soft_surface_position
from cpswm.perception_mapping import natural_vision, unity_rgbd
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
    TypedParticleState,
)
from cpswm.system.native_joint_production import ProducedJointCandidates
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_execution import _code_object_payload
from cpswm.system.structure_two_particle_workspace import (
    ConditionalAnalyticState,
    native_content_sha256,
)

FORMAT = "controlled-raw-position-producer@1"
EYE6 = tuple(tuple(float(i == j) for j in range(6)) for i in range(6))
EYE3 = tuple(tuple(float(i == j) for j in range(3)) for i in range(3))


def _require(value, message):
    if not value:
        raise ValueError(message)


def _uuid(value):
    return type(value) is str and str(UUID(value)) == value


def _helper_code_sha256(code):
    """Full type-exact code identity without execution/reference-count flags.

    This encoding is local to this declared controlled producer. It preserves
    every existing code-payload field; generic checkpoint protocols are unchanged.
    """
    return sha256(marshal.dumps(_code_object_payload(code), 2)).hexdigest()


def packet_binding(observations):
    """Bind actual public originals; this helper grants no acquisition authority."""
    _require(type(observations) is tuple and len(observations) == 3, "three raw channels required")
    envelopes = tuple(row.envelope() for row in observations)
    camera, _ = unity_rgbd.decode_unity_rgbd(observations, cutoff=envelopes[0].arrival_time)
    first = envelopes[0].identity
    return dict(
        observation_ids=[str(row.identity.observation_id) for row in envelopes],
        scope=[str(first.household_id), str(first.session_id), str(first.trace_id)],
        action_id=str(camera.action_id),
        raw_sha256=native_content_sha256(
            tuple(
                (
                    row.envelope_json,
                    sha256(row.payload_bytes).hexdigest(),
                    row.capture_receipt_sha256,
                    row.archive_sampling_json,
                    row.depth_unit,
                )
                for row in observations
            )
        ),
    )


def implementation_binding():
    """Bind helper source bytes and loaded Python bodies, including camera math."""
    members = []
    for module in (instance_affinity, soft_surface_position, position, natural_vision, unity_rgbd):
        functions = []
        for name, value in sorted(vars(module).items()):
            if inspect.isfunction(value):
                functions.append((name, _helper_code_sha256(value.__code__)))
            elif inspect.isclass(value) and value.__module__ == module.__name__:
                for key, descriptor in sorted(vars(value).items()):
                    bodies = (
                        (descriptor.fget, descriptor.fset, descriptor.fdel)
                        if isinstance(descriptor, property)
                        else (
                            descriptor.__func__
                            if isinstance(descriptor, (classmethod, staticmethod))
                            else descriptor,
                        )
                    )
                    for index, body in enumerate(bodies):
                        if inspect.isfunction(body):
                            functions.append(
                                (f"{name}.{key}.{index}", _helper_code_sha256(body.__code__))
                            )
        members.append(
            (module.__name__, sha256(Path(module.__file__).read_bytes()).hexdigest(), functions)
        )
    return content_sha256(
        (
            sha256(Path(__file__).read_bytes()).hexdigest(),
            members,
            position.H,
            position.CONFIG,
            position.SCHEMA,
            position.SCOPE,
            soft_surface_position.DEFINITION,
            soft_surface_position.SCHEMA,
            soft_surface_position.DOMAIN,
            soft_surface_position.ESTIMATORS,
            EYE6,
            EYE3,
            FORMAT,
        )
    )


class ControlledPositionProducer:
    """Two explicit particles plus the native unresolved bucket, equal at birth.

    Configuration has exactly semantic_record_id, packet, candidate, seed_uv,
    enabled. The enabled switch defines the paired no-factor engineering control;
    it is binding-covered and cannot be changed after collector configuration.
    Wrap with NeuralNativeProducer for verified exact-enumeration q cancellation.

    semantic_record_id matches the native after record, or the before record
    only when after.metadata.source_id is exactly the controlled CIAV closure
    `structure-two-adaptive-ciav-feedback-closure`. It never searches historical
    records. Diagnostics retain configured/before/after IDs; retraction removes
    the actual published after revision, without moving the packet to a new one.
    """

    def __init__(
        self,
        *,
        configuration,
        affinity_model,
        affinity_pin,
        position_model,
        position_pin,
    ):
        self.configuration = deepcopy(configuration)
        self.affinity_model = instance_affinity.restore(affinity_model, affinity_pin)
        self.affinity_pin = affinity_pin
        self.position_model = position.restore(position_model, position_pin)
        self.position_pin = position_pin
        self._implementation = implementation_binding()
        config = self.configuration
        _require(
            type(config) is dict
            and set(config) == {"semantic_record_id", "packet", "candidate", "seed_uv", "enabled"}
            and _uuid(config["semantic_record_id"])
            and type(config["enabled"]) is bool,
            "invalid controlled position configuration",
        )
        packet = config["packet"]
        _require(
            type(packet) is dict
            and set(packet) == {"observation_ids", "scope", "action_id", "raw_sha256"}
            and type(packet["observation_ids"]) is list
            and len(packet["observation_ids"]) == 3
            and len(set(packet["observation_ids"])) == 3
            and all(_uuid(v) for v in packet["observation_ids"])
            and type(packet["scope"]) is list
            and len(packet["scope"]) == 3
            and all(_uuid(v) for v in packet["scope"])
            and _uuid(packet["action_id"])
            and type(packet["raw_sha256"]) is str
            and len(packet["raw_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in packet["raw_sha256"]),
            "invalid controlled packet binding",
        )
        seed = config["seed_uv"]
        candidate = config["candidate"]
        _require(
            type(seed) is list
            and len(seed) == 2
            and all(type(v) is int and v >= 0 for v in seed)
            and type(candidate) is dict
            and set(candidate) == {"method", "id", "box"}
            and type(candidate["method"]) is str
            and bool(candidate["method"])
            and _uuid(candidate["id"])
            and type(candidate["box"]) is list
            and len(candidate["box"]) == 4
            and all(type(v) is float and isfinite(v) for v in candidate["box"]),
            "one declared public candidate and pixel required",
        )
        self._binding = self._content_binding()
        self.calls = 0
        self.consumed_keys = []
        self.last_diagnostic = None

    def _content_binding(self):
        current_implementation = implementation_binding()
        _require(
            current_implementation == self._implementation,
            "controlled helper implementation changed",
        )
        instance_affinity.restore(self.affinity_model, self.affinity_pin)
        position.restore(self.position_model, self.position_pin)
        return content_sha256(
            (
                FORMAT,
                self.configuration,
                self.affinity_pin,
                self.position_pin,
                current_implementation,
                tuple(
                    (name, _helper_code_sha256(value.__code__))
                    for name, value in sorted(globals().items())
                    if inspect.isfunction(value) and value.__module__ == __name__
                ),
                "unknown-N(0,100I3)",
            )
        )

    @property
    def binding_sha256(self):
        binding = self._content_binding()
        if binding != self._binding:
            raise ValueError("controlled dependency changed")
        return binding

    def _measurement_key(self):
        return content_sha256((self.binding_sha256, "single-source-single-public-seed"))

    def checkpoint_state(self):
        return deepcopy(
            dict(
                binding=self.binding_sha256,
                calls=self.calls,
                consumed_keys=self.consumed_keys,
                last_diagnostic=self.last_diagnostic,
            )
        )

    def restore_state(self, state):
        _require(
            type(state) is dict
            and set(state) == {"binding", "calls", "consumed_keys", "last_diagnostic"}
            and state["binding"] == self.binding_sha256
            and type(state["calls"]) is int
            and state["calls"] >= 0
            and type(state["consumed_keys"]) is list
            and state["consumed_keys"] in ([], [self._measurement_key()])
            and (state["last_diagnostic"] is None or type(state["last_diagnostic"]) is dict)
            and (not state["consumed_keys"] or state["calls"] > 0),
            "invalid controlled producer checkpoint",
        )
        self.calls = state["calls"]
        self.consumed_keys = deepcopy(state["consumed_keys"])
        self.last_diagnostic = deepcopy(state["last_diagnostic"])

    def _public(self, context):
        expected = self.configuration["packet"]
        lookup = {
            str(row.envelope().identity.observation_id): row for row in context.visible_prefix
        }
        _require(len(lookup) == len(context.visible_prefix), "duplicate visible raw identity")
        _require(
            all(key in lookup for key in expected["observation_ids"]), "bound raw packet missing"
        )
        rows = tuple(lookup[key] for key in expected["observation_ids"])
        _require(packet_binding(rows) == expected, "bound raw packet differs")
        camera, depth = unity_rgbd.decode_unity_rgbd(rows, cutoff=context.cutoff)
        meta = context.source.transition.after.metadata
        _require(
            expected["scope"] == [str(meta.household_id), str(meta.session_id), str(meta.trace_id)]
            and camera.capture_time <= context.source.transition.after.detection_time
            and all(row.envelope().arrival_time <= context.cutoff for row in rows),
            "public packet outside semantic scope or epoch",
        )
        _, rgb = natural_vision.decode_rgb(rows[0], cutoff=context.cutoff)
        result = soft_surface_position.readout_frame(
            rgb,
            depth,
            camera,
            [self.configuration["candidate"]],
            self.affinity_model,
            self.affinity_pin,
            provenance=dict(
                source_sha256=expected["raw_sha256"],
                receipt_sha256=rows[0].capture_receipt_sha256,
                observation_ids=expected["observation_ids"],
                payload_sha256=[row.envelope().payload.payload_sha256 for row in rows],
            ),
        )
        seeds = [row for row in result["seeds"] if row["pixel_uv"] == self.configuration["seed_uv"]]
        _require(len(seeds) == 1 and seeds[0]["valid"], "fixed public seed unavailable")
        selected = next(
            row
            for row in result["observations"]
            if row["seed_id"] == seeds[0]["seed_id"]
            and row["estimator"] == self.position_model["estimator"]
        )
        return {
            key: selected[key]
            for key in (
                "measurement_id",
                "estimator",
                "estimator_pin",
                "domain_id",
                "frame_id",
                "action_id",
                "valid_at",
                "world_point_m",
            )
        }

    def _neutral(self, prior, cluster, record_id):
        return ConditionalMeasurement(
            cluster,
            (record_id,),
            FORMAT + ":no-position-information",
            (0.0,) * len(prior.alpha),
            (0.0,) * len(prior.b),
            0.0,
            0.0,
            (0.0, 0.0, 0.0),
            position.H,
            EYE3,
            0.0,
        )

    def _selected(self, source):
        record_id = source.transition.after.metadata.record_id
        return str(record_id) == self.configuration["semantic_record_id"] or (
            source.transition.after.metadata.source_id
            == "structure-two-adaptive-ciav-feedback-closure"
            and source.transition.before is not None
            and str(source.transition.before.metadata.record_id)
            == self.configuration["semantic_record_id"]
        )

    def recompute(self, context, predecessor_sources):
        """On a fresh verifier instance, derive consumption from actual ancestry.

        No submitted checkpoint state, diagnostic, or stored measurement is used.
        Sources are supplied by the native owner from the accepted parent graph.
        """
        _require(self.calls == 0 and not self.consumed_keys, "verifier must start fresh")
        consumed = sum(
            self._selected(source) and self.configuration["enabled"]
            for source in predecessor_sources
        )
        _require(consumed <= 1, "raw measurement appears twice in native ancestry")
        if consumed:
            self.consumed_keys = [self._measurement_key()]
        return self.produce(context)

    def produce(self, context):
        # All validations and arithmetic precede mutation of the producer state.
        binding = self.binding_sha256
        source = context.source
        source.validate_content()
        record_id = source.transition.after.metadata.record_id
        selected = self._selected(source)
        active = selected and self.configuration["enabled"]
        _require(not active or not self.consumed_keys, "bound raw observation already consumed")
        observation = self._public(context) if active else None
        cluster = content_uuid(FORMAT + ":cluster", (source.source_id, binding))
        from cpswm.system.structure_two_particle_workspace import NativePreviousWeightEvidence

        evidence = context.previous_weight_evidence
        if context.previous_batch is None:
            _require(evidence is None, "initial raw context cannot invent previous weights")
            weights, unresolved = {}, 0.0
        else:
            _require(
                type(evidence) is NativePreviousWeightEvidence
                and evidence.batch() == context.previous_batch,
                "raw context requires actual previous log weight evidence",
            )
            weights, unresolved = evidence.normalized_logs()
        unknown_logpdf = (
            0.0
            if observation is None
            else float(
                -0.5
                * (
                    3 * log(2 * pi * 100.0)
                    + np.dot(observation["world_point_m"], observation["world_point_m"]) / 100.0
                )
            )
        )
        receipts, statistics = [], {}
        diagnostic = dict(
            active=active,
            semantic_record_id=str(record_id),
            public_observation=observation,
            configured_record_id=self.configuration["semantic_record_id"],
            native_before_record_id=str(source.transition.before.metadata.record_id)
            if source.transition.before is not None
            else None,
            native_after_record_id=str(record_id),
            mapping="exact-native-after"
            if str(record_id) == self.configuration["semantic_record_id"]
            else "controlled-ciav-before"
            if selected
            else "unrelated-source",
        )
        for index, actor in enumerate(("owner", "unknown_actor")):
            chains = [
                h
                for h in source.history_after.latest.hypotheses
                if len(h.steps) == 3 and h.responsible_actor_key == actor
            ]
            _require(len(chains) == 1, "controlled actor chain not uniquely supported")
            chain = chains[0]
            parents = [
                r
                for r in context.records
                if r.state.particle_id in weights
                and r.state.ordered_actor_roles[0].actor_key == actor
            ]
            _require(len(parents) == (1 if weights else 0), "controlled parent support differs")
            parent = parents[0] if parents else None
            prior = (
                parent.statistics
                if parent
                else ConditionalAnalyticState(
                    source.locations,
                    (1.0,) * len(source.locations),
                    ((1.0, 0.0), (0.0, 1.0)),
                    (0.0, 0.0),
                    EYE6,
                    (0.0,) * 6,
                )
            )
            measure = self._neutral(prior, cluster, record_id)
            logpdf = unknown_logpdf
            if observation is not None and index == 0:
                reference = dict(
                    reference_id=content_sha256(
                        (FORMAT, "controlled-origin-zero", self.position_pin)
                    ),
                    reference_kind=self.position_model["reference_kind"],
                    domain_id=observation["domain_id"],
                    frame_id=observation["frame_id"],
                    valid_at=observation["valid_at"],
                    xyz_m=[0.0, 0.0, 0.0],
                )
                measure, diagnostic["known"] = position.condition(
                    self.position_model,
                    self.position_pin,
                    observation,
                    reference,
                    prior,
                    evidence_cluster_id=cluster,
                    source_record_ids=tuple(
                        UUID(v) for v in self.configuration["packet"]["observation_ids"]
                    ),
                )
                logpdf = diagnostic["known"]["observation_log_likelihood"]
            analytic = rebuild_conditional_state(prior, (measure,))
            pid = content_uuid(FORMAT + ":particle", (cluster, index))
            statistics[pid] = analytic
            state = TypedParticleState(
                particle_id=pid,
                parent_particle_id=None if parent is None else parent.state.particle_id,
                parent_revision_id=None if parent is None else parent.state.revision_id,
                source_snapshot_id=source.snapshot_id,
                event_hypothesis_id=chain.hypothesis_id,
                revision_id=source.history_after.latest.revision_id,
                ordered_actor_roles=tuple(
                    OrderedActorRole(role=role, actor_key=actor)
                    for role in ("pickup_actor", "carrier", "placer")
                ),
                instance_association_key=str(source.object_instance_id)
                if index == 0
                else "unknown_instance",
                change_cause="unresolved",
                regime_decision="unresolved",
                regime_id=None,
                run_length=len(prior.evidence_cluster_ids),
                statistic_state_ref=analytic.reference,
                ledger_lineage_ref="hybrid-ledger:" + context.ledger_head_sha256,
            )
            receipts.append(
                ParticleRevisionReceipt(
                    proposal=NeuralParticleProposal(
                        proposal_id=content_uuid(FORMAT + ":proposal", pid),
                        evidence_cluster_id=cluster,
                        operation="branch" if parent and index == 0 else "preserve_unresolved",
                        source_particle_id=state.parent_particle_id,
                        source_snapshot_id=source.snapshot_id,
                        proposed_state=state,
                        proposal_log_probability=log(0.5),
                        proposer_model_version="explicit-prepared-candidates@1",
                        proposer_code_version=FORMAT,
                    ),
                    prior_log_weight=0.0 if parent is None else weights[parent.state.particle_id],
                    transition_log_probability=0.0,
                    observation_log_likelihood=logpdf,
                    constraints=tuple(
                        StructuredConstraint(factor=f, accepted=True, log_potential=0.0)
                        for f in StructuredWeightFactor
                        if f.value.endswith("constraint")
                    ),
                )
            )
        diagnostic.update(
            unknown_log_likelihood=unknown_logpdf, aggregate_log_weight=unresolved + unknown_logpdf
        )
        result = ProducedJointCandidates(
            context.content_sha256,
            source.source_id,
            source.body_sha256,
            binding,
            tuple(receipts),
            statistics,
            unresolved + unknown_logpdf,
        )
        self.calls += 1
        if active:
            self.consumed_keys.append(self._measurement_key())
        self.last_diagnostic = diagnostic
        return result
