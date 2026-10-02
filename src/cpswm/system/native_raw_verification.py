"""Owner-configured raw candidate reconstruction, independent of submitted proof.

Only the explicitly supported controlled position profile is protected here.
Legacy candidate models retain their existing contract. A proof cannot select a
profile, import a class, provide mutable pre-state, or authorize a raw context.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from cpswm.system.native_joint_production import (
    NativeJointContext,
    NativeJointProducer,
    producer_implementation_binding,
)
from cpswm.system.structure_two_particle_workspace import (
    NativeParticleWorkspace,
    native_content_sha256,
)

if TYPE_CHECKING:
    from cpswm.system.controlled_position_producer import ControlledPositionProducer
    from cpswm.system.native_neural_production import NativeNeuralEvidence, NeuralNativeProducer


@dataclass(frozen=True)
class RawCandidateAuthority:
    key: UUID

    @classmethod
    def create(cls) -> RawCandidateAuthority:
        return cls(uuid4())


def profile_for(producer: NativeJointProducer | None) -> dict[str, Any] | None:
    # Do not make optional torch a dependency of legacy/non-neural collection.
    # A genuine NeuralNativeProducer necessarily loaded its canonical module.
    cls = type(producer)
    module_name = "cpswm.system.native_neural_production"
    if cls.__module__ != module_name or cls.__qualname__ != "NeuralNativeProducer":
        return None
    module = sys.modules.get(module_name)
    if module is None or vars(module).get("NeuralNativeProducer") is not cls:
        raise ValueError("canonical neural producer class was replaced")
    # Closed registry, imported from installed source, never a checkpoint path.
    from cpswm.system.appearance_geometry_position import (
        PROFILE as ASSOCIATION_PROFILE,
    )
    from cpswm.system.appearance_geometry_position import (
        AppearanceGeometryPositionProducer,
    )
    from cpswm.system.controlled_position_producer import ControlledPositionProducer
    from cpswm.system.mask_surface_support import PROFILE as SURFACE_PROFILE
    from cpswm.system.mask_surface_support import MaskSurfaceSupportProducer
    from cpswm.system.natural_candidate_position import (
        NATURAL_PROFILE,
        NaturalCandidatePositionProducer,
    )
    from cpswm.system.owned_position_producer import PROFILE, OwnedPositionProducer
    from cpswm.system.temporal_target_position import PROFILE as TEMPORAL_PROFILE
    from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

    neural = cast("NeuralNativeProducer", producer)
    candidate = neural._candidate_model
    if type(candidate) not in (
        ControlledPositionProducer,
        OwnedPositionProducer,
        NaturalCandidatePositionProducer,
        AppearanceGeometryPositionProducer,
        TemporalTargetPositionProducer,
        MaskSurfaceSupportProducer,
    ):
        return None
    candidate = cast("ControlledPositionProducer", candidate)
    return dict(
        profile={
            ControlledPositionProducer: "controlled-position-raw@1",
            OwnedPositionProducer: PROFILE,
            NaturalCandidatePositionProducer: NATURAL_PROFILE,
            AppearanceGeometryPositionProducer: ASSOCIATION_PROFILE,
            TemporalTargetPositionProducer: TEMPORAL_PROFILE,
            MaskSurfaceSupportProducer: SURFACE_PROFILE,
        }[type(candidate)],
        verifier_source=sha256(Path(__file__).read_bytes()).hexdigest(),
        weight_source=sha256(
            Path(__file__).with_name("structure_two_particle_workspace.py").read_bytes()
        ).hexdigest(),
        joint_binding=neural.binding_sha256,
        candidate_binding=candidate.binding_sha256,
        implementation=producer_implementation_binding(candidate),
        arguments=deepcopy(
            dict(
                configuration=candidate.configuration,
                affinity_model=candidate.affinity_model,
                affinity_pin=candidate.affinity_pin,
                position_model=candidate.position_model,
                position_pin=candidate.position_pin,
            )
        ),
    )


def reconstruct(profile: dict[str, Any]) -> ControlledPositionProducer:
    from cpswm.system.appearance_geometry_position import (
        PROFILE as ASSOCIATION_PROFILE,
    )
    from cpswm.system.appearance_geometry_position import (
        AppearanceGeometryPositionProducer,
    )
    from cpswm.system.controlled_position_producer import ControlledPositionProducer
    from cpswm.system.mask_surface_support import PROFILE as SURFACE_PROFILE
    from cpswm.system.mask_surface_support import MaskSurfaceSupportProducer
    from cpswm.system.natural_candidate_position import (
        NATURAL_PROFILE,
        NaturalCandidatePositionProducer,
    )
    from cpswm.system.owned_position_producer import PROFILE, OwnedPositionProducer
    from cpswm.system.temporal_target_position import PROFILE as TEMPORAL_PROFILE
    from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

    if (
        type(profile) is not dict
        or set(profile)
        != {
            "profile",
            "verifier_source",
            "weight_source",
            "joint_binding",
            "candidate_binding",
            "implementation",
            "arguments",
        }
        or profile["profile"]
        not in (
            "controlled-position-raw@1",
            PROFILE,
            NATURAL_PROFILE,
            ASSOCIATION_PROFILE,
            TEMPORAL_PROFILE,
            SURFACE_PROFILE,
        )
    ):
        raise ValueError("unrecognized configured raw candidate profile")
    if profile["verifier_source"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("raw verifier source differs from owner configuration")
    if (
        profile["weight_source"]
        != sha256(
            Path(__file__).with_name("structure_two_particle_workspace.py").read_bytes()
        ).hexdigest()
    ):
        raise ValueError("raw weight source differs from owner configuration")
    cls = {
        PROFILE: OwnedPositionProducer,
        NATURAL_PROFILE: NaturalCandidatePositionProducer,
        ASSOCIATION_PROFILE: AppearanceGeometryPositionProducer,
        TEMPORAL_PROFILE: TemporalTargetPositionProducer,
        SURFACE_PROFILE: MaskSurfaceSupportProducer,
        "controlled-position-raw@1": ControlledPositionProducer,
    }[profile["profile"]]
    result = cls(**deepcopy(profile["arguments"]))
    if (
        result.binding_sha256 != profile["candidate_binding"]
        or producer_implementation_binding(result) != profile["implementation"]
    ):
        raise ValueError("configured raw candidate implementation or model changed")
    return result


def raw_context_digest(context: NativeJointContext) -> str:
    if type(context) is not NativeJointContext:
        raise ValueError("raw owner context has the wrong type")
    return native_content_sha256(
        (
            context.content_sha256,
            tuple(
                (
                    raw.envelope_json,
                    sha256(raw.payload_bytes).hexdigest(),
                    raw.capture_receipt_sha256,
                    raw.archive_sampling_json,
                    raw.depth_unit,
                )
                for raw in context.visible_prefix
            ),
        )
    )


def verify_raw_base(
    evidence: NativeNeuralEvidence,
    workspace: NativeParticleWorkspace,
    native_context: NativeJointContext,
) -> None:
    """Reproduce every base field using owned raw inputs and actual ancestry."""
    profile = workspace.raw_candidate_profile
    if native_content_sha256(profile) != workspace.raw_candidate_profile_sha256:
        raise ValueError("configured raw candidate profile was changed or removed")
    if profile is None:
        return
    if profile["joint_binding"] != workspace.joint_dependency_binding:
        raise ValueError("raw profile differs from configured neural producer")
    original = workspace.raw_contexts.get(evidence.input_context_sha256)
    if original is None:
        raise ValueError("raw candidate context was not admitted by the owner")
    if raw_context_digest(original) != workspace.raw_context_anchors.get(
        evidence.input_context_sha256
    ):
        raise ValueError("owned raw candidate context changed")
    from cpswm.system.native_neural_production import canonical_records

    canonical_original = replace(
        original, records=canonical_records(original.records), visible_prefix=()
    )
    if canonical_original.content_sha256 != native_context.content_sha256:
        raise ValueError("raw candidate source, cutoff or prior differs from owner admission")
    candidate = reconstruct(profile)
    clusters = {record.evidence_cluster_id for record in native_context.records}
    sources = []
    contexts = []
    for cluster in clusters:
        prior = workspace.input_bodies.get(cluster)
        if prior is None or prior.neural_evidence is None:
            raise ValueError("raw candidate predecessor evidence is missing")
        source_id = prior.neural_evidence.base_candidates.source_posterior_id
        source = workspace.posterior_sources.get(source_id)
        if source is None:
            raise ValueError("raw candidate predecessor source is not owned")
        sources.append(source)
        key = prior.neural_evidence.input_context_sha256
        if key in workspace.raw_contexts:
            contexts.append(workspace.raw_contexts[key])
    from cpswm.system.owned_position_producer import OwnedPositionProducer

    full_context = replace(native_context, visible_prefix=original.visible_prefix)
    from cpswm.system.appearance_geometry_position import AppearanceGeometryPositionProducer
    from cpswm.system.mask_surface_support import MaskSurfaceSupportProducer
    from cpswm.system.natural_candidate_position import NaturalCandidatePositionProducer
    from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

    if type(candidate) in (
        OwnedPositionProducer,
        NaturalCandidatePositionProducer,
        AppearanceGeometryPositionProducer,
        TemporalTargetPositionProducer,
        MaskSurfaceSupportProducer,
    ):
        if len(contexts) != len(clusters):
            raise ValueError("owned update predecessor context is missing")
        expected = cast("OwnedPositionProducer", candidate).recompute_updates(
            full_context, tuple(contexts)
        )
    else:
        expected = candidate.recompute(full_context, tuple(sources))
    expected = replace(expected, context_sha256=native_context.content_sha256)
    if native_content_sha256(expected) != native_content_sha256(evidence.base_candidates):
        raise ValueError("raw candidate base differs from complete owner recomputation")
