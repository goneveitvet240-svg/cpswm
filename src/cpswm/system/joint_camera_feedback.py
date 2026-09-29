"""Replay actual camera measurements into a short-lived full-joint decision view.

Likelihoods are the explicitly configured model saved BEFORE the action. Their
calibration is not certified here. Measurement decoders see returned pixels only;
unknown/failed measurements cannot become semantic absence or a ledger write.
Each new native batch starts a new conditioning chain, avoiding double counting
when the semantic producer has subsequently consumed the same observations.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from math import fsum, isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.joint_camera_policy import CameraModelSources, JointCameraProblem
from cpswm.system.native_joint_production import python_dependency_implementation_binding
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_joint_consumption import JointDecisionView

if TYPE_CHECKING:
    from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery
    from cpswm.world_model.grounded_search.active_verification import (
        CauseInformationActiveVerificationPlanner,
    )


class CameraOutcomeDecoder(Protocol):
    """Deterministic, stateless measurement from arrived pixels; None is abstention.

    A local pure-inference cache is permitted. Artifact binding must verify the
    live decoder/model and configuration; it is not a calibration certificate.
    """

    sources: CameraModelSources

    @property
    def binding_sha256(self) -> str: ...

    def decode(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> str | None: ...


def decoder_binding(decoder: CameraOutcomeDecoder | None) -> str | None:
    from cpswm.perception_mapping.unity_rgbd import implementation_binding
    from cpswm.system.structure_two_execution import _code_object_sha256

    if decoder is None:
        return None
    artifact = decoder.binding_sha256
    if len(artifact) != 64 or any(c not in "0123456789abcdef" for c in artifact):
        raise ValueError("camera decoder requires a SHA256 artifact binding")
    sources = CameraModelSources.model_validate(decoder.sources.model_dump())
    return content_sha256(
        (
            artifact,
            sources,
            implementation_binding(),
            python_dependency_implementation_binding(decoder, required_methods=("decode",)),
            sha256(Path(__file__).read_bytes()).hexdigest(),
            tuple(
                (name, _code_object_sha256(globals()[name].__code__))
                for name in ("condition_view", "replay_camera_history")
            ),
        )
    )


@dataclass(frozen=True)
class JointObservationUpdate:
    action_id: UUID
    source_observation_ids: tuple[UUID, ...]
    prior_sha256: str
    posterior_sha256: str
    decoder_binding_sha256: str
    outcome: str | None
    execution_success: bool
    marginal_likelihood: float | None
    prior: tuple[tuple[UUID, float], ...]
    posterior: tuple[tuple[UUID, float], ...]
    evidence_sha256: str


def condition_view(
    view: JointDecisionView, likelihood: Mapping[UUID, float] | None, *, evidence_sha256: str
) -> tuple[JointDecisionView, float | None]:
    """Pure Bayes calculation; a returned value confers no publication authority."""
    prior = view.verification_belief().as_uuid_prior()
    posterior = prior
    normalizer = None
    if likelihood is not None:
        if set(likelihood) != set(prior) or any(
            not isfinite(v) or not 0 <= v <= 1 for v in likelihood.values()
        ):
            raise ValueError("camera likelihood must cover every full joint atom")
        normalizer = fsum(prior[key] * likelihood[key] for key in prior)
        if normalizer <= 0:
            raise ValueError("observed camera outcome is impossible under the configured model")
        posterior = {key: prior[key] * likelihood[key] / normalizer for key in prior}
    if len(evidence_sha256) != 64 or evidence_sha256 in view.observation_evidence:
        raise ValueError("duplicate or invalid camera evidence identity")
    return (
        replace(
            view,
            atoms=tuple(replace(a, probability=posterior[a.particle_id]) for a in view.atoms),
            unresolved_probability=posterior[view.unresolved_id],
            observation_evidence=(*view.observation_evidence, evidence_sha256),
        ),
        normalizer,
    )


def replay_camera_history(
    base: JointDecisionView,
    *,
    commands: Mapping[UUID, tuple[ObservationCommand, str]],
    statuses: Mapping[UUID, str | ObservationDelivery],
    native_origins: Mapping[UUID, str],
    raw: Mapping[UUID, RawModalityObservation],
    decoder: CameraOutcomeDecoder,
    expected_binding: str,
    planner: CauseInformationActiveVerificationPlanner,
) -> tuple[JointDecisionView, tuple[JointObservationUpdate, ...]]:
    """Only runtime-owned delivered commands matching this actual view are used.

    Follow the source-belief chain, independent of dictionary insertion order.
    Disconnected older generations remain history, never guessed onto new atoms.
    """
    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    if decoder_binding(decoder) != expected_binding:
        raise ValueError("camera decoder dependency changed")
    if set(statuses) != set(commands) or not set(native_origins) <= set(commands):
        raise ValueError("camera native origin or command/status journal is incomplete")
    pending = {}
    for key, (command, digest) in commands.items():
        status = statuses[key]
        if key in native_origins and not command.reason.startswith("joint-ciav@1:"):
            raise ValueError("owned model camera origin lost its issued problem")
        if type(status) is not ObservationDelivery or not command.reason.startswith(
            "joint-ciav@1:"
        ):
            continue
        if key != command.action_id or key != status.action_id or content_sha256(command) != digest:
            raise ValueError("owned camera command or delivery identity changed")
        if key not in native_origins:
            raise ValueError("model camera feedback has no owner-issued native origin")
        if native_origins[key] != base.content_sha256:
            continue
        problem = JointCameraProblem.model_validate_json(
            command.reason.removeprefix("joint-ciav@1:")
        )
        pending[key] = (command, status, problem)
    view, updates = base, []
    while True:
        matching = [
            key
            for key, (_, _, p) in pending.items()
            if p.source_belief_sha256 == view.content_sha256
        ]
        if not matching:
            break
        if len(matching) != 1:
            raise ValueError("delivered camera commands fork the same joint belief")
        command, delivery, problem = pending.pop(matching[0])
        if (
            problem.model_sources != decoder.sources
            or problem.source_observation_ids != command.source_ids
        ):
            raise ValueError(
                "camera measurement model or input dependencies differ from issued action"
            )
        _, selected = problem.select(view, planner)
        if (
            selected is None
            or selected.action != command.action
            or selected.degrees != command.degrees
            or command.snapshot_id != view.snapshot_id
            or delivery.received_at < command.decision_time
        ):
            raise ValueError("camera feedback is not from the actually selected current action")
        ids = tuple(x.envelope().identity.observation_id for x in delivery.observations)
        if len(ids) != len(set(ids)) or not set(command.source_ids) <= set(raw):
            raise ValueError("camera feedback has duplicate or missing source observations")
        for key, observation in zip(ids, delivery.observations, strict=True):
            env = observation.envelope()
            if (
                raw.get(key) != observation
                or key in command.source_ids
                or not command.decision_time
                <= env.capture_time
                <= env.arrival_time
                <= delivery.received_at
            ):
                raise ValueError("camera feedback pixels differ from owned post-action input")
        if (
            type(delivery.success) is not bool
            or (delivery.success and not delivery.observations)
            or (not delivery.success and not delivery.error)
        ):
            raise ValueError("camera execution receipt is incomplete")
        outcome = (
            decoder.decode(deepcopy(delivery.observations), cutoff=delivery.received_at)
            if delivery.success
            else None
        )
        if outcome is not None and (
            type(outcome) is not str or outcome not in selected.candidate.outcome_likelihoods
        ):
            raise ValueError("decoded measurement is outside the issued observation model")
        if decoder_binding(decoder) != expected_binding:
            raise ValueError("camera decoder changed while interpreting evidence")
        evidence = content_sha256(
            (
                command,
                delivery.success,
                delivery.error,
                delivery.received_at,
                tuple(
                    (x.envelope_json, x.capture_receipt_sha256, sha256(x.payload_bytes).hexdigest())
                    for x in delivery.observations
                ),
                expected_binding,
                outcome,
            )
        )
        before = view
        view, normalizer = condition_view(
            before,
            None if outcome is None else selected.candidate.outcome_likelihoods[outcome],
            evidence_sha256=evidence,
        )
        updates.append(
            JointObservationUpdate(
                command.action_id,
                ids,
                before.content_sha256,
                view.content_sha256,
                expected_binding,
                outcome,
                delivery.success,
                normalizer,
                tuple(
                    sorted(
                        before.verification_belief().as_uuid_prior().items(),
                        key=lambda x: str(x[0]),
                    )
                ),
                tuple(
                    sorted(
                        view.verification_belief().as_uuid_prior().items(), key=lambda x: str(x[0])
                    )
                ),
                evidence,
            )
        )
    if pending:
        raise ValueError("current native camera history cannot reconstruct its full evidence chain")
    return view, tuple(updates)
