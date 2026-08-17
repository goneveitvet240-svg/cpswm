from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import EntityType, SourceType
from cpswm_gt import GTEntity, GTRelationAssertion, GroundTruthWorldState
from simobs import SyntheticObservation


def test_ground_truth_types_are_nominally_separate(now, interval):
    person = GTEntity(entity_type=EntityType.PERSON, attributes={"name": "A"})
    cup = GTEntity(entity_type=EntityType.OBJECT_INSTANCE, attributes={"color": "red"})
    relation = GTRelationAssertion(
        subject_gt_entity_id=cup.gt_entity_id,
        predicate="carried_by",
        object_gt_entity_id=person.gt_entity_id,
        valid_time=interval,
    )
    state = GroundTruthWorldState(
        simulation_run_id=uuid4(),
        simulation_time=now,
        entities=(person, cup),
        relations=(relation,),
    )
    assert state.relations[0].gt_relation_id != relation.subject_gt_entity_id
    assert not hasattr(relation, "metadata")
    assert not hasattr(relation, "evidence")


def test_non_oracle_observation_cannot_carry_gt_references(metadata_factory):
    with pytest.raises(ValidationError):
        SyntheticObservation(
            metadata=metadata_factory(
                schema_name="simobs.SyntheticObservation",
                source_type=SourceType.SIMULATION,
            ),
            observation_type="event_candidate",
            payload={"event": "pick_up"},
            noise_profile_id="controlled-noise@0.1",
            oracle_channel=False,
            ground_truth_refs=(uuid4(),),
        )


def test_oracle_observation_must_be_explicit(metadata_factory):
    observation = SyntheticObservation(
        metadata=metadata_factory(
            schema_name="simobs.SyntheticObservation",
            source_type=SourceType.SIMULATION,
        ),
        observation_type="event_candidate",
        payload={"event": "pick_up"},
        noise_profile_id="oracle@0.1",
        oracle_channel=True,
        ground_truth_refs=(uuid4(),),
    )
    assert observation.oracle_channel


def test_only_explicit_oracle_side_packages_can_import_ground_truth():
    repo_root = Path(__file__).resolve().parents[1]
    cpswm_root = repo_root / "src" / "cpswm"
    allowed_roots = (
        cpswm_root / "system" / "world_model_simulator",
        cpswm_root / "system" / "evaluation_operations",
    )
    violations: list[str] = []
    for path in cpswm_root.rglob("*.py"):
        if any(path.is_relative_to(root) for root in allowed_roots):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "cpswm_gt" or name.startswith("cpswm_gt.") for name in names):
                violations.append(f"{path}:{node.lineno}")
    assert violations == []
