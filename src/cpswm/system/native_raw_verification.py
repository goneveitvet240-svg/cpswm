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
from uuid import UUID, uuid4

from cpswm.system.native_joint_production import NativeJointContext, producer_implementation_binding
from cpswm.system.structure_two_particle_workspace import native_content_sha256


@dataclass(frozen=True)
class RawCandidateAuthority:
    key: UUID

    @classmethod
    def create(cls):
        return cls(uuid4())


def profile_for(producer):
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
    from cpswm.system.controlled_position_producer import ControlledPositionProducer

    candidate = producer._candidate_model
    if type(candidate) is not ControlledPositionProducer:
        return None
    return dict(
        profile="controlled-position-raw@1",
        verifier_source=sha256(Path(__file__).read_bytes()).hexdigest(),
        weight_source=sha256(
            Path(__file__).with_name("structure_two_particle_workspace.py").read_bytes()
        ).hexdigest(),
        joint_binding=producer.binding_sha256,
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


def reconstruct(profile):
    from cpswm.system.controlled_position_producer import ControlledPositionProducer

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
        or profile["profile"] != "controlled-position-raw@1"
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
    result = ControlledPositionProducer(**deepcopy(profile["arguments"]))
    if (
        result.binding_sha256 != profile["candidate_binding"]
        or producer_implementation_binding(result) != profile["implementation"]
    ):
        raise ValueError("configured raw candidate implementation or model changed")
    return result


def raw_context_digest(context):
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


def verify_raw_base(evidence, workspace, native_context):
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
    for cluster in clusters:
        prior = workspace.input_bodies.get(cluster)
        if prior is None or prior.neural_evidence is None:
            raise ValueError("raw candidate predecessor evidence is missing")
        source_id = prior.neural_evidence.base_candidates.source_posterior_id
        source = workspace.posterior_sources.get(source_id)
        if source is None:
            raise ValueError("raw candidate predecessor source is not owned")
        sources.append(source)
    expected = candidate.recompute(
        replace(native_context, visible_prefix=original.visible_prefix), tuple(sources)
    )
    expected = replace(expected, context_sha256=native_context.content_sha256)
    if native_content_sha256(expected) != native_content_sha256(evidence.base_candidates):
        raise ValueError("raw candidate base differs from complete owner recomputation")
