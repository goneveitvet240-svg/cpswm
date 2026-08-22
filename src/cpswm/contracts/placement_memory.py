"""Placement-memory contracts for `项目结构一 §9`.

§9 requires four *separate* kinds of placement memory that must never be
collapsed into one target:

    observed habit    where an object usually *is*        → predict / find
    stated preference where the owner *wants* it          → tidy / put-back
    household norm    a household safety rule             → hard constraint
    commonsense norm  a general safety prior              → soft constraint

The observed-habit layer already exists (``RelationPredicate.USUALLY_LOCATED_AT``
plus :class:`HabitLearningEvidence` and the mobility profiler).  This module adds
the two missing layers as *first-class record types* rather than as flags on an
observed-habit record.  The separation is therefore structural: a stated
preference or a norm has no training-weight field at all, so it is impossible to
route one into the habit statistics — mirroring the ``effective_training_weight``
firewall in :mod:`cpswm.contracts.habit_learning`.

`§9` original: *"最可能在哪里找到" 与 "机器人应该放回哪里" 是两个不同的决策问题。*
The resolver in :mod:`cpswm.world_model.placement_decision` consumes these
records and keeps that distinction; nothing here decides *how* a commonsense
norm is sourced (`§17` choice #4 stays open).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)
from .corrections import AuthorityLevel


class PlacementMemoryClass(StrEnum):
    """The four §9 placement-memory kinds, kept semantically distinct."""

    OBSERVED_HABIT = "observed_habit"
    STATED_PREFERENCE = "stated_preference"
    HOUSEHOLD_NORM = "household_norm"
    COMMONSENSE_NORM = "commonsense_norm"


#: The two classes that a :class:`PlacementNormAssertion` may carry.  Both are
#: norms, but they keep different provenance and different override strength.
NORM_CLASSES = frozenset(
    {PlacementMemoryClass.HOUSEHOLD_NORM, PlacementMemoryClass.COMMONSENSE_NORM}
)


class NormRuleKind(StrEnum):
    """What a placement norm asserts about an object."""

    #: The object must be stored at ``target_location_id``.
    MUST_BE_AT = "must_be_at"
    #: The object must not be at ``target_location_id`` (e.g. medicine reachable
    #: by children).
    MUST_NOT_BE_AT = "must_not_be_at"
    #: The object requires a stored condition (e.g. refrigeration), independent
    #: of any single location.
    REQUIRES_CONDITION = "requires_condition"


class PlacementSubject(ContractModel):
    """What a preference or norm is about: one instance, or an object class.

    Class-level subjects let a norm like "fresh food needs refrigeration" apply
    without enumerating every instance.  The resolver treats an instance-level
    subject as more specific than a class-level one.
    """

    kind: Literal["instance", "class"]
    object_instance_id: UUID | None = None
    object_class: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_subject(self) -> PlacementSubject:
        if self.kind == "instance":
            if self.object_instance_id is None or self.object_class is not None:
                raise ValueError("instance subject requires object_instance_id and no object_class")
        elif self.object_class is None or self.object_instance_id is not None:
            raise ValueError("class subject requires object_class and no object_instance_id")
        return self

    def applies_to(self, *, object_instance_id: UUID, object_class: str | None) -> bool:
        if self.kind == "instance":
            return self.object_instance_id == object_instance_id
        return object_class is not None and self.object_class == object_class


class StatedPreferenceAssertion(ContractModel):
    """Where a household member *says* an object should go.

    This is never a claim about where the object *is*.  It carries no training
    weight, so it cannot enter the observed-habit statistics.
    """

    metadata: BaseRecordMetadata
    subject: PlacementSubject
    preferred_location_id: UUID
    stated_by: EntityRef
    authority_level: AuthorityLevel
    valid_time: ValidTimeInterval
    user_statement_ref: EvidenceRef
    superseded: bool = False

    @model_validator(mode="after")
    def validate_preference(self) -> StatedPreferenceAssertion:
        # A stated preference must come from a person's statement.  This is the
        # structural guard that keeps observed behaviour from being silently
        # promoted to "where it should go".
        if self.metadata.source_type != SourceType.USER:
            raise ValueError("StatedPreferenceAssertion must have source_type=user")
        if self.stated_by.entity_type != EntityType.PERSON:
            raise ValueError("a stated preference must be stated by a person")
        return self

    @property
    def memory_class(self) -> PlacementMemoryClass:
        return PlacementMemoryClass.STATED_PREFERENCE


class PlacementNormAssertion(ContractModel):
    """A household or commonsense placement rule, used as a safety constraint.

    Household norms are set by an authorized member or imported policy;
    commonsense norms are general priors from a model or an imported knowledge
    base.  Neither carries a training weight, so a norm cannot become an
    observed habit.
    """

    metadata: BaseRecordMetadata
    norm_class: PlacementMemoryClass
    subject: PlacementSubject
    rule_kind: NormRuleKind
    target_location_id: UUID | None = None
    required_condition_key: str | None = Field(default=None, min_length=1)
    safety_priority: int = Field(ge=0)
    is_hard_constraint: bool
    valid_time: ValidTimeInterval
    superseded: bool = False

    @model_validator(mode="after")
    def validate_norm(self) -> PlacementNormAssertion:
        if self.norm_class not in NORM_CLASSES:
            raise ValueError("norm_class must be household_norm or commonsense_norm")

        allowed_sources = {
            PlacementMemoryClass.HOUSEHOLD_NORM: {SourceType.USER, SourceType.IMPORT},
            PlacementMemoryClass.COMMONSENSE_NORM: {SourceType.MODEL, SourceType.IMPORT},
        }
        if self.metadata.source_type not in allowed_sources[self.norm_class]:
            raise ValueError(
                f"source_type={self.metadata.source_type.value} is incompatible with "
                f"norm_class={self.norm_class.value}"
            )

        if self.rule_kind == NormRuleKind.REQUIRES_CONDITION:
            if self.required_condition_key is None or self.target_location_id is not None:
                raise ValueError(
                    "requires_condition needs required_condition_key and no target_location_id"
                )
        elif self.target_location_id is None or self.required_condition_key is not None:
            raise ValueError(
                f"{self.rule_kind.value} needs target_location_id and no required_condition_key"
            )
        return self

    @property
    def memory_class(self) -> PlacementMemoryClass:
        return self.norm_class
