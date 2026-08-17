from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    EntityRelationObject,
    EntityType,
    EventEvidenceClass,
    EventParticipant,
    EventParticipantRole,
    EventRecord,
    EventType,
    EvidenceScoredMixin,
    RelationAssertion,
    RelationPredicate,
    SourceType,
    TemporalValidityMixin,
)


def test_relation_assertion_round_trip(
    metadata_factory, interval, now, entity_factory, evidence_ref
):
    cup = entity_factory(EntityType.OBJECT_INSTANCE)
    kitchen = entity_factory(EntityType.PLACE)
    assertion = RelationAssertion(
        metadata=metadata_factory(
            schema_name="cpswm.RelationAssertion", source_type=SourceType.MODEL
        ),
        temporal=TemporalValidityMixin(valid_time=interval, observed_time=now),
        subject=cup,
        predicate=RelationPredicate.LOCATED_AT,
        object=EntityRelationObject(entity=kitchen),
        evidence=EvidenceScoredMixin(evidence_reliability=0.85, evidence_refs=(evidence_ref,)),
    )
    restored = RelationAssertion.model_validate_json(assertion.model_dump_json())
    assert restored == assertion
    assert "posterior_probability" not in assertion.model_dump_json()


def test_relation_cannot_supersede_itself(metadata_factory, interval, now, entity_factory):
    metadata = metadata_factory(schema_name="cpswm.RelationAssertion")
    with pytest.raises(ValidationError):
        RelationAssertion(
            metadata=metadata,
            temporal=TemporalValidityMixin(valid_time=interval, observed_time=now),
            subject=entity_factory(),
            predicate=RelationPredicate.NEAR,
            object=EntityRelationObject(entity=entity_factory(EntityType.PLACE)),
            evidence=EvidenceScoredMixin(
                evidence_reliability=0.5,
                supersedes=(metadata.record_id,),
            ),
        )


def test_event_source_class_is_enforced(metadata_factory, interval, now, entity_factory):
    with pytest.raises(ValidationError):
        EventRecord(
            metadata=metadata_factory(schema_name="cpswm.EventRecord", source_type=SourceType.USER),
            temporal=TemporalValidityMixin(valid_time=interval, observed_time=now),
            event_type=EventType.PICK_UP,
            evidence_class=EventEvidenceClass.INFERRED,
            participants=(
                EventParticipant(
                    role=EventParticipantRole.ACTOR,
                    entity=entity_factory(EntityType.PERSON),
                ),
            ),
            evidence=EvidenceScoredMixin(evidence_reliability=0.8),
        )


def test_inferred_event_is_valid(metadata_factory, interval, now, entity_factory, evidence_ref):
    event = EventRecord(
        metadata=metadata_factory(
            schema_name="cpswm.EventRecord", source_type=SourceType.INFERENCE
        ),
        temporal=TemporalValidityMixin(valid_time=interval, observed_time=now),
        event_type=EventType.CARRY,
        evidence_class=EventEvidenceClass.INFERRED,
        participants=(
            EventParticipant(
                role=EventParticipantRole.ACTOR,
                entity=entity_factory(EntityType.PERSON),
            ),
            EventParticipant(
                role=EventParticipantRole.OBJECT,
                entity=entity_factory(EntityType.OBJECT_INSTANCE),
            ),
        ),
        evidence=EvidenceScoredMixin(
            evidence_reliability=0.7,
            evidence_refs=(evidence_ref,),
            supersedes=(uuid4(),),
        ),
    )
    assert event.evidence_class == EventEvidenceClass.INFERRED
