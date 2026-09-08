from __future__ import annotations

import copy
from pathlib import Path
from uuid import uuid4

import pytest

from cpswm.contracts import ObservationOpportunityRecord
from cpswm.system.evaluation_operations import StructureTwoActionScenarioGenerator
from cpswm.system.prototype_spine import PrototypeTransition
from cpswm.system.structure_two_production_system import (
    PRODUCTION_OPERATOR_BINDINGS,
    PRODUCTION_OPERATOR_ORDER,
    StructureTwoProductionSystem,
    build_production_assembly_manifest,
    verify_production_assembly_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def _system_and_transition() -> tuple[StructureTwoProductionSystem, PrototypeTransition]:
    case = StructureTwoActionScenarioGenerator().generate(3).visible
    observation = next(
        item for item in case.days if item.before is not None and item.after is not None
    )
    assert observation.before is not None
    assert observation.after is not None
    assert observation.after.detection_time is not None
    opportunity = ObservationOpportunityRecord(
        metadata=observation.after.metadata.model_copy(
            update={
                "record_id": observation.after.observation_opportunity_id,
                "schema_name": "cpswm.ObservationOpportunityRecord",
            }
        ),
        observation_action_id=uuid4(),
        opportunity_time=observation.after.detection_time,
        selected=True,
        selection_probability=0.8,
        p_visible_given_state=0.9,
        p_detect_given_visible=0.9,
        likelihood_model_id="structure-two-production-system-test@0.2",
    )
    evidence = tuple(
        item
        for item in (
            observation.actor_evidence,
            observation.mechanism_evidence,
            observation.role_evidence,
        )
        if item is not None
    )
    system = StructureTwoProductionSystem(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations,
        authorization_scope_id=uuid4(),
    )
    transition = PrototypeTransition(
        opportunity=opportunity,
        before=observation.before,
        after=observation.after,
        actor_prior={
            case.owner_actor: 0.4,
            case.guest_actor: 0.3,
            "unknown_actor": 0.3,
        },
        evidence=evidence,
        context_key="weekday|home",
        context_value=float(observation.day),
    )
    return system, transition


def test_one_public_runtime_owns_all_seven_real_operator_instances() -> None:
    system, transition = _system_and_transition()
    system.verify_runtime_assembly()
    instances = system.runtime_operator_instances()

    assert tuple(instances) == PRODUCTION_OPERATOR_ORDER
    assert all(instances[operator] for operator in PRODUCTION_OPERATOR_ORDER)
    assert tuple(binding.operator for binding in PRODUCTION_OPERATOR_BINDINGS) == (
        PRODUCTION_OPERATOR_ORDER
    )

    result = system.process_transition(transition)
    assert result.event_history.latest.revision_id == result.event_revision_id
    assert result.decision.evidence_source_record_ids
    assert result.belief_snapshot.map_version >= 1


def test_production_assembly_manifest_recomputes_every_source_binding() -> None:
    manifest = build_production_assembly_manifest(ROOT)
    verify_production_assembly_manifest(manifest, ROOT)

    assert manifest["runtime_assembly_verified"] is True
    assert [row["operator"] for row in manifest["operators"]] == list(PRODUCTION_OPERATOR_ORDER)
    assert len(manifest["forward_edges"]) == len(PRODUCTION_OPERATOR_ORDER) - 1


def test_manifest_cannot_claim_runtime_assembly_without_live_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        StructureTwoProductionSystem,
        "runtime_operator_instances",
        lambda self: {"opceu": (self.core._corrector,)},
    )

    with pytest.raises(ValueError, match="runtime operator order drifted"):
        build_production_assembly_manifest(ROOT)


def test_declared_override_must_implement_the_operator_contract() -> None:
    system, _ = _system_and_transition()
    system.core._message_passing = object()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="override type is not registered"):
        system.verify_runtime_assembly(allowed_operator_overrides=frozenset({"pchmp"}))


def test_forged_but_complete_production_manifest_is_rejected() -> None:
    forged = copy.deepcopy(build_production_assembly_manifest(ROOT))
    forged["operators"][0]["sources"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="production assembly manifest mismatch"):
        verify_production_assembly_manifest(forged, ROOT)
