"""§9 placement-memory separation invariants.

`项目结构一 §9` requires observed habit / stated preference / household norm /
commonsense norm to be *kept apart*, and fixes the principle that "最可能在哪里
找到" (find) and "机器人应该放回哪里" (put-back) are different decision problems.

These tests encode that as enforced behaviour: the four kinds cannot masquerade
as one another at construction time, FIND never consults preferences or norms,
and PUT_BACK never borrows the observed habit.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    EntityRef,
    EntityType,
    NormRuleKind,
    PlacementMemoryClass,
    PlacementNormAssertion,
    PlacementSubject,
    SourceType,
    StatedPreferenceAssertion,
)
from cpswm.world_model.placement_decision import (
    PlacementDecisionResolver,
    PlacementDecisionStatus,
    PlacementIntent,
)

SOFA = UUID(int=701)
CLOSET = UUID(int=702)
FRIDGE = UUID(int=703)
COUNTER = UUID(int=704)
COAT = UUID(int=801)


@pytest.fixture
def person(entity_factory) -> EntityRef:
    return entity_factory(EntityType.PERSON)


def _instance_subject(object_instance_id: UUID = COAT) -> PlacementSubject:
    return PlacementSubject(kind="instance", object_instance_id=object_instance_id)


def make_preference(
    metadata_factory,
    interval,
    person,
    evidence_ref,
    *,
    preferred_location_id: UUID,
    subject: PlacementSubject | None = None,
    source_type: SourceType = SourceType.USER,
) -> StatedPreferenceAssertion:
    return StatedPreferenceAssertion(
        metadata=metadata_factory(schema_name="test.Preference", source_type=source_type),
        subject=subject or _instance_subject(),
        preferred_location_id=preferred_location_id,
        stated_by=person,
        authority_level="household_owner",
        valid_time=interval,
        user_statement_ref=evidence_ref,
    )


def make_norm(
    metadata_factory,
    interval,
    *,
    norm_class: PlacementMemoryClass,
    rule_kind: NormRuleKind,
    target_location_id: UUID | None = None,
    required_condition_key: str | None = None,
    safety_priority: int = 100,
    is_hard_constraint: bool = True,
    subject: PlacementSubject | None = None,
    source_type: SourceType | None = None,
) -> PlacementNormAssertion:
    if source_type is None:
        source_type = (
            SourceType.USER
            if norm_class == PlacementMemoryClass.HOUSEHOLD_NORM
            else SourceType.MODEL
        )
    return PlacementNormAssertion(
        metadata=metadata_factory(schema_name="test.Norm", source_type=source_type),
        norm_class=norm_class,
        subject=subject or _instance_subject(),
        rule_kind=rule_kind,
        target_location_id=target_location_id,
        required_condition_key=required_condition_key,
        safety_priority=safety_priority,
        is_hard_constraint=is_hard_constraint,
        valid_time=interval,
    )


# --- construction-time firewall (the four kinds cannot be confused) ----------


def test_preference_has_no_training_weight_field() -> None:
    # The structural guarantee of Option A: a preference simply has no channel
    # into the habit statistics, unlike HabitLearningEvidence.
    assert "proposed_training_weight" not in StatedPreferenceAssertion.model_fields
    assert not hasattr(StatedPreferenceAssertion, "effective_training_weight")
    assert "proposed_training_weight" not in PlacementNormAssertion.model_fields


def test_preference_must_come_from_a_user_statement(
    metadata_factory, interval, person, evidence_ref
) -> None:
    # Observed behaviour (a sensor/simulation source) cannot be recorded as a
    # stated preference — that is exactly the §9 collapse to prevent.
    with pytest.raises(ValidationError, match="source_type=user"):
        make_preference(
            metadata_factory,
            interval,
            person,
            evidence_ref,
            preferred_location_id=CLOSET,
            source_type=SourceType.SIMULATION,
        )


def test_preference_must_be_stated_by_a_person(
    metadata_factory, interval, evidence_ref, entity_factory
) -> None:
    with pytest.raises(ValidationError, match="stated by a person"):
        make_preference(
            metadata_factory,
            interval,
            entity_factory(EntityType.OBJECT_INSTANCE),
            evidence_ref,
            preferred_location_id=CLOSET,
        )


def test_household_norm_rejects_a_model_source(metadata_factory, interval) -> None:
    with pytest.raises(ValidationError, match="incompatible"):
        make_norm(
            metadata_factory,
            interval,
            norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
            rule_kind=NormRuleKind.MUST_NOT_BE_AT,
            target_location_id=COUNTER,
            source_type=SourceType.MODEL,
        )


def test_commonsense_norm_rejects_a_user_source(metadata_factory, interval) -> None:
    with pytest.raises(ValidationError, match="incompatible"):
        make_norm(
            metadata_factory,
            interval,
            norm_class=PlacementMemoryClass.COMMONSENSE_NORM,
            rule_kind=NormRuleKind.REQUIRES_CONDITION,
            required_condition_key="refrigerated",
            source_type=SourceType.USER,
        )


def test_observed_habit_is_not_a_valid_norm_class(metadata_factory, interval) -> None:
    with pytest.raises(ValidationError, match="household_norm or commonsense_norm"):
        make_norm(
            metadata_factory,
            interval,
            norm_class=PlacementMemoryClass.OBSERVED_HABIT,
            rule_kind=NormRuleKind.MUST_NOT_BE_AT,
            target_location_id=COUNTER,
            source_type=SourceType.IMPORT,
        )


def test_condition_norm_cannot_also_pin_a_location(metadata_factory, interval) -> None:
    with pytest.raises(ValidationError, match="required_condition_key and no target"):
        make_norm(
            metadata_factory,
            interval,
            norm_class=PlacementMemoryClass.COMMONSENSE_NORM,
            rule_kind=NormRuleKind.REQUIRES_CONDITION,
            required_condition_key="refrigerated",
            target_location_id=FRIDGE,
        )


# --- FIND reads observed habit only -----------------------------------------


def test_find_ignores_preferences_and_norms(
    metadata_factory, interval, person, evidence_ref, now
) -> None:
    # Observed habit says the coat is usually on the sofa.  A preference and a
    # hard norm both say it *should* be in the closet.  FIND must still answer
    # "sofa": where it should go cannot move where it is.
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.FIND,
        object_instance_id=COAT,
        decision_time=now,
        observed_location_distribution={SOFA: 0.8, CLOSET: 0.2},
        preferences=(
            make_preference(
                metadata_factory, interval, person, evidence_ref, preferred_location_id=CLOSET
            ),
        ),
        norms=(
            make_norm(
                metadata_factory,
                interval,
                norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
                rule_kind=NormRuleKind.MUST_BE_AT,
                target_location_id=CLOSET,
            ),
        ),
    )
    assert decision.status is PlacementDecisionStatus.RESOLVED
    assert decision.governing_memory_class is PlacementMemoryClass.OBSERVED_HABIT
    assert decision.target_location_id == SOFA
    assert decision.applied_norms == ()


def test_find_abstains_without_observed_habit(now) -> None:
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.FIND,
        object_instance_id=COAT,
        decision_time=now,
        observed_location_distribution=None,
    )
    assert decision.status is PlacementDecisionStatus.ABSTAIN


# --- PUT_BACK reads preference/norm, never the observed habit ----------------


def test_put_back_abstains_rather_than_using_observed_habit(now) -> None:
    # No stated preference and no forcing norm: the robot must not decide to put
    # the coat back on the sofa just because that is where it usually is.
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=COAT,
        decision_time=now,
        observed_location_distribution={SOFA: 1.0},
    )
    assert decision.status is PlacementDecisionStatus.ABSTAIN
    assert decision.target_location_id is None
    assert decision.governing_memory_class is None


def test_put_back_uses_stated_preference_and_flags_disagreement(
    metadata_factory, interval, person, evidence_ref, now
) -> None:
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=COAT,
        decision_time=now,
        observed_location_distribution={SOFA: 1.0},
        preferences=(
            make_preference(
                metadata_factory, interval, person, evidence_ref, preferred_location_id=CLOSET
            ),
        ),
    )
    assert decision.status is PlacementDecisionStatus.RESOLVED
    assert decision.governing_memory_class is PlacementMemoryClass.STATED_PREFERENCE
    assert decision.target_location_id == CLOSET
    # observed=sofa vs put-back=closet is the tidy signal.
    assert decision.preference_habit_disagreement is True


def test_hard_norm_overrides_stated_preference(
    metadata_factory, interval, person, evidence_ref, now
) -> None:
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=COAT,
        decision_time=now,
        preferences=(
            make_preference(
                metadata_factory, interval, person, evidence_ref, preferred_location_id=COUNTER
            ),
        ),
        norms=(
            make_norm(
                metadata_factory,
                interval,
                norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
                rule_kind=NormRuleKind.MUST_BE_AT,
                target_location_id=CLOSET,
            ),
        ),
    )
    assert decision.status is PlacementDecisionStatus.RESOLVED
    assert decision.governing_memory_class is PlacementMemoryClass.HOUSEHOLD_NORM
    assert decision.target_location_id == CLOSET


def test_hard_forbidding_norm_blocks_the_preferred_location(
    metadata_factory, interval, person, evidence_ref, now
) -> None:
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.PUT_BACK,
        object_instance_id=COAT,
        decision_time=now,
        preferences=(
            make_preference(
                metadata_factory, interval, person, evidence_ref, preferred_location_id=COUNTER
            ),
        ),
        norms=(
            make_norm(
                metadata_factory,
                interval,
                norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
                rule_kind=NormRuleKind.MUST_NOT_BE_AT,
                target_location_id=COUNTER,
            ),
        ),
    )
    assert decision.status is PlacementDecisionStatus.BLOCKED_BY_NORM
    assert decision.target_location_id is None


# --- SAFETY_CHECK ------------------------------------------------------------


def test_safety_check_flags_a_forbidden_location(metadata_factory, interval, now) -> None:
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.SAFETY_CHECK,
        object_instance_id=COAT,
        decision_time=now,
        proposed_location_id=COUNTER,
        norms=(
            make_norm(
                metadata_factory,
                interval,
                norm_class=PlacementMemoryClass.HOUSEHOLD_NORM,
                rule_kind=NormRuleKind.MUST_NOT_BE_AT,
                target_location_id=COUNTER,
            ),
        ),
    )
    assert decision.status is PlacementDecisionStatus.NORM_VIOLATION
    assert decision.applied_norms[0].effect == "violated_must_not_be_at"


def test_class_level_norm_applies_by_object_class(metadata_factory, interval, now) -> None:
    # "fresh food requires refrigeration" is a class-level commonsense norm and
    # must apply to a specific instance of that class.
    resolver = PlacementDecisionResolver()
    decision = resolver.resolve(
        intent=PlacementIntent.SAFETY_CHECK,
        object_instance_id=uuid4(),
        object_class="fresh_food",
        decision_time=now,
        proposed_location_id=COUNTER,
        norms=(
            make_norm(
                metadata_factory,
                interval,
                norm_class=PlacementMemoryClass.COMMONSENSE_NORM,
                rule_kind=NormRuleKind.REQUIRES_CONDITION,
                required_condition_key="refrigerated",
                subject=PlacementSubject(kind="class", object_class="fresh_food"),
            ),
        ),
    )
    assert decision.applied_norms
    assert decision.applied_norms[0].required_condition_key == "refrigerated"
