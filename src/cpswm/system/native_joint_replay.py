"""Full prepared-joint recomputation from accepted, still-live semantic sources.

This is an explicit full-history fallback, not a local rejuvenation kernel. It
preserves old generations and the semantic ledger; the configured producer must
be reset to its recorded initial state by its continuous-input owner. It does not
certify that producer's scientific model, likelihoods, or calibration.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_particle_workspace import (
    NativeParticleWorkspace,
    NativePosteriorSource,
    native_content_sha256,
)


@dataclass(frozen=True)
class ReplayAssessment:
    """Historical inference context and current correction context, kept distinct."""

    historical_assessment: Any
    snapshot: Any
    basis_sha256: str
    original_source: NativePosteriorSource


@dataclass(frozen=True)
class JointReplayGeneration:
    old_workspace: NativeParticleWorkspace
    old_input_anchors: dict[UUID, str]
    old_source_anchors: dict[UUID, str]
    basis_sha256: str
    sources: tuple[NativePosteriorSource, ...]
    removed_revision_ids: tuple[UUID, ...]

    @property
    def content_sha256(self) -> str:
        if type(self.old_workspace) is not NativeParticleWorkspace:
            raise ValueError("joint replay archive has an invalid workspace type")
        return native_content_sha256(
            (
                vars(self.old_workspace),
                self.old_input_anchors,
                self.old_source_anchors,
                self.basis_sha256,
                self.sources,
                self.removed_revision_ids,
            )
        )


def correction_basis(core: Any) -> str:
    """Pin the actual live histories, causes, snapshot, and unique ledger head."""
    return native_content_sha256(
        (
            core.current_snapshot,
            core.current_cause_snapshot,
            core._hybrid_loop.ledger.export_state().manifest.head_hash,
            tuple(
                (rid, core._event_histories.get(rid), event)
                for rid, event in sorted(core._observed_events.items(), key=lambda x: str(x[0]))
            ),
        )
    )


def validate_generations(core: Any) -> None:
    generations = core._particle_replay_generations
    if len(generations) != len(core._particle_replay_generation_anchors):
        raise ValueError("joint replay archive closure changed")
    for generation, anchor in zip(
        generations, core._particle_replay_generation_anchors, strict=True
    ):
        if generation.content_sha256 != anchor:
            raise ValueError("joint replay archive differs from its core acceptance anchor")
        old = generation.old_workspace
        old._validate_persisted_state()
        if {
            k: v.body_sha256 for k, v in old.posterior_sources.items()
        } != generation.old_source_anchors:
            raise ValueError("joint replay archive has changed producer source anchors")
        if old.input_journal != generation.old_input_anchors:
            raise ValueError("joint replay archive has changed accepted inputs")


def validate_replay_source(core: Any, source: NativePosteriorSource) -> None:
    validate_generations(core)
    matches = [
        item
        for generation in core._particle_replay_generations
        for item in generation.sources
        if item.source_id == source.source_id
    ]
    if len(matches) != 1 or matches[0] != source:
        raise ValueError("joint replay source is not a core-accepted recomputation")
    assessment = source.producer_context[1]
    if type(assessment) is not ReplayAssessment or assessment.basis_sha256 != correction_basis(
        core
    ):
        raise ValueError("joint replay source is stale after semantic correction")


def prepare_generation(core: Any) -> JointReplayGeneration:
    """Compile every live observed revision, failing on any missing source.

    Every source is bound to the core's acceptance anchor recorded at actual
    publication, including sources not yet consumed by a joint batch.
    No old weight, conditional statistic, or candidate list is recycled.
    """
    core._check_particle_workspace_binding()
    core._validate_particle_input_anchors()
    validate_generations(core)
    old = core._particle_workspace
    old._validate_persisted_state()
    if not old.invalidated_revisions:
        raise ValueError("full joint replay requires a populated invalidated history")
    if not core._observed_events:
        raise ValueError("no retained semantic source for a nonempty joint posterior")
    source_pool: dict[UUID, NativePosteriorSource] = {}
    # Current and archived bodies have each already passed their core anchors.
    workspaces = [g.old_workspace for g in core._particle_replay_generations] + [old]
    for workspace in workspaces:
        for source in workspace.posterior_sources.values():
            source_pool[source.history_after.latest.revision_id] = source
    basis = correction_basis(core)
    runtime_id = content_uuid("full-joint-replay-generation", (old.runtime_id, basis))
    new = NativeParticleWorkspace(registered_locations=core._registered_particle_locations)
    new.runtime_id = runtime_id
    sources = []
    ordered = sorted(
        core._observed_events.items(),
        key=lambda row: (row[1].evidence.event_time, str(row[0])),
    )
    for rid, event in ordered:
        original = source_pool.get(rid)
        if original is None:
            raise ValueError("full joint replay lacks a retained revision's original source")
        original.validate_content()
        history = core._event_histories.get(rid)
        if (
            history is None
            or content_sha256(history) != content_sha256(original.history_after)
            or original.transition.after.metadata.record_id != event.source_record_id
            or original.transition.after.detected_location_id != event.location_id
            or original.producer_context[0].applied_weight != event.propensity_weight
        ):
            raise ValueError("retained source no longer matches its live semantic history")
        branch = core._event_engine.branch(
            before=original.transition.before,
            after=original.transition.after,
            actor_prior=dict(original.transition.actor_prior),
            unresolved_probability=original.transition.unresolved_probability,
            allow_unknown_handoff_roles=True,
        )
        posterior = core._message_passing.infer(branch, original.transition.evidence)
        if content_sha256(branch) != content_sha256(original.history_before) or content_sha256(
            posterior
        ) != content_sha256(original.posterior):
            raise ValueError("retained source does not reproduce its ORRER/PCHMP computation")
        assessment = original.producer_context[1]
        if type(assessment) is ReplayAssessment:
            origin = assessment.original_source
            historical = assessment.historical_assessment
        else:
            origin, historical = original, assessment
        source = new.publish_posterior(
            object_instance_id=core.object_instance_id,
            snapshot_id=core.current_snapshot.snapshot_id,
            locations=core._registered_particle_locations,
            history_before=branch,
            history_after=history,
            posterior=posterior,
            transition=original.transition,
            producer_context=(
                original.producer_context[0],
                ReplayAssessment(historical, core.current_cause_snapshot, basis, origin),
            ),
        )
        sources.append(source)
    return JointReplayGeneration(
        deepcopy(old),
        dict(core._particle_input_anchors),
        dict(core._particle_posterior_source_anchors),
        basis,
        tuple(sources),
        tuple(sorted(old.invalidated_revisions, key=str)),
    )


def install_empty_generation(core: Any, generation: JointReplayGeneration) -> None:
    """Internal step under the core transaction; never a public reset operation."""
    if generation.basis_sha256 != correction_basis(core):
        raise ValueError("joint replay basis changed before reconstruction")
    workspace = core._particle_workspace
    fresh = NativeParticleWorkspace(registered_locations=core._registered_particle_locations)
    fresh.runtime_id = generation.sources[0].runtime_id
    # Keep the runtime-owned object identity and method bindings intact.
    vars(workspace).clear()
    vars(workspace).update(vars(fresh))
    core._particle_input_anchors = {}
    core._particle_posterior_source_anchors = {}
    core._particle_replay_generations += (generation,)
    core._particle_replay_generation_anchors += (generation.content_sha256,)
