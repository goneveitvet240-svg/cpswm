"""Multi-entity binding: one model state per (household, actor, object).

The controlled scenarios carry a single household, a single owner and a single
object, so a flat model is harmless there.  A real log is not like that: one
file holds several households, several residents and dozens of objects.  A
model that pools them learns a household-average habit belonging to nobody, and
worse, it does so invisibly -- the run still produces numbers.

This module makes the partition explicit.  :func:`bind_stream` splits a stream
into one :class:`ProjectOneStreamBinding` per entity triple, and
:class:`ProjectOneMethodFactory` builds a *fresh* arm set per binding.  Isolation
of the Dirichlet counts, the RLS heads, the CF-BOCPD beam and the CCRR regime
bank then follows from object lifetime rather than from a key discipline every
component would have to remember.

Two decisions worth stating.

**Candidate locations come from the binding's own records, or from a manifest
the operator wrote.**  Deriving them from the whole file would let the test
half's locations into training; deriving them from *other* bindings would let
another household's furniture in.

**A binding no arm can run on is reported, not dropped.**  An object seen in
one place only has nothing to predict, but a pilot that evaluated 4 of 40
objects must not be readable as one that evaluated 40.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from .project_one_dataset import ProjectOneDatasetRecord, ProjectOneStream
from .project_one_methods import (
    OPEN_SET_LOCATION,
    CategoricalBOCPDMethod,
    ContextFrequencyMethod,
    CoreHabitChainMethod,
    PersistenceMethod,
    ProjectOneMethod,
)
from .project_one_protocol import (
    CategoricalBOCPDConfig,
    ContextFrequencyConfig,
    PersistenceConfig,
    ProjectOneProtocolConfig,
    ResidualCalibration,
    SignalAblation,
)

__all__ = [
    "DEFAULT_TRAIN_FRACTION",
    "MINIMUM_CANDIDATE_LOCATIONS",
    "OPEN_SET_LOCATION",
    "PILOT_ARM_NAMES",
    "CandidatePolicy",
    "ProjectOneBindingKey",
    "ProjectOneMethodFactory",
    "ProjectOneStreamBinding",
    "bind_stream",
]

#: A method has nothing to discriminate between with fewer than two candidates.
MINIMUM_CANDIDATE_LOCATIONS = 2

#: Fraction of a binding's records treated as its training prefix when the
#: candidate set is derived rather than declared.
DEFAULT_TRAIN_FRACTION = 0.4

# ``OPEN_SET_LOCATION`` is re-exported above from the methods module, which owns
# the single definition (that module cannot import this one).


class CandidatePolicy(StrEnum):
    """Where a binding's candidate location set comes from.

    This is not a detail.  Deriving the set from the whole stream tells the arm,
    at step zero, exactly which locations will ever appear -- including the one
    the habit is about to move to.  A ``stable_habit`` binding then presents one
    candidate and a ``permanent_change`` binding two, so the *cardinality of the
    candidate set leaks the answer* before a single event is scored.
    """

    #: Derive from the binding's training prefix only.  No leak, but an unseen
    #: location later is an error -- use when the vocabulary is genuinely closed.
    TRAIN_ONLY = "train_only"
    #: The operator declares the vocabulary.  No leak, because a human supplied
    #: it rather than the data; the declaration must cover what is observed.
    MANIFEST = "manifest"
    #: Training prefix (or a declaration) plus :data:`OPEN_SET_LOCATION`.
    #: Anything unseen maps to that bucket instead of crashing the arm.  The
    #: honest default for real logs, where the vocabulary is never closed.
    OPEN_SET = "open_set"
    #: Everything the binding ever observes.  **Leaky** -- retained only to
    #: reproduce runs recorded before the policy existed.
    OBSERVED_ALL = "observed_all"


#: The fixed-parameter pilot arm set, in report order.
#:
#: ``full_as_is`` and ``full_raw_clip`` are the same method reading the RLS
#: score by two different routes.  Since the 2026-08-24 source fix those routes
#: agree, so running both is a free consistency check on real data rather than a
#: redundant arm: divergence means the head is not emitting what the harness
#: believes it is.
PILOT_ARM_NAMES: tuple[str, ...] = (
    "full_as_is",
    "full_raw_clip",
    "no_rls",
    "rls_only",
    "categorical_bocpd",
    "context_frequency",
    "persistence",
)

_CHAIN_ARMS: tuple[tuple[str, SignalAblation, ResidualCalibration], ...] = (
    ("full_as_is", SignalAblation.FULL, ResidualCalibration.AS_IS),
    ("full_raw_clip", SignalAblation.FULL, ResidualCalibration.RAW_CLIP),
    ("no_rls", SignalAblation.NO_RLS, ResidualCalibration.AS_IS),
    ("rls_only", SignalAblation.RLS_ONLY, ResidualCalibration.AS_IS),
)


@dataclass(frozen=True, slots=True, order=True)
class ProjectOneBindingKey:
    """The entity triple a single model state belongs to.

    Keyed on ``subject_id`` -- *whose habit this is* -- and deliberately not on
    ``actor_id``, which records who physically moved the object.  Binding on the
    actor would give every guest their own phantom habit model for someone
    else's cup, and would remove from the owner's model exactly the events the
    contamination work exists to reason about.  A guest event belongs in the
    owner's binding, down-weighted, not in a binding of its own.
    """

    household_id: str
    subject_id: str
    object_id: str

    def __post_init__(self) -> None:
        for name in ("household_id", "subject_id", "object_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be a non-empty identifier")


@dataclass(frozen=True, slots=True)
class ProjectOneStreamBinding:
    """One entity triple's slice of a stream, plus its candidate set."""

    key: ProjectOneBindingKey
    stream_id: str
    records: tuple[ProjectOneDatasetRecord, ...]
    candidate_locations: tuple[str, ...]
    #: ``training_stream`` or ``manifest`` -- recorded so a later reader can
    #: tell whether the candidate set was observed or declared.
    location_source: str
    is_evaluable: bool
    skip_reason: str = ""

    def __post_init__(self) -> None:
        if not self.records:
            raise ValueError("a binding must hold at least one record")
        if self.is_evaluable and self.skip_reason:
            raise ValueError("an evaluable binding cannot carry a skip reason")
        if not self.is_evaluable and not self.skip_reason:
            raise ValueError("a skipped binding must say why")

    @property
    def binding_id(self) -> str:
        """Stable identity, safe to use as a filename component or a join key."""

        return "|".join(
            (
                self.stream_id,
                self.key.household_id,
                self.key.subject_id,
                self.key.object_id,
            )
        )

    def summary(self) -> dict[str, object]:
        """The binding as it appears in a pilot manifest."""

        return {
            "binding_id": self.binding_id,
            "stream_id": self.stream_id,
            "household_id": self.key.household_id,
            "subject_id": self.key.subject_id,
            "object_id": self.key.object_id,
            "record_count": len(self.records),
            "candidate_locations": list(self.candidate_locations),
            "location_source": self.location_source,
            "is_evaluable": self.is_evaluable,
            "skip_reason": self.skip_reason,
        }


def bind_stream(
    stream: ProjectOneStream,
    *,
    policy: CandidatePolicy | None = None,
    candidate_locations: Mapping[ProjectOneBindingKey, Sequence[str]] | None = None,
    minimum_locations: int = MINIMUM_CANDIDATE_LOCATIONS,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
) -> tuple[ProjectOneStreamBinding, ...]:
    """Partition a stream into one binding per (household, subject, object).

    Keys appear in first-observed order and records keep the stream's order,
    which the stream itself guarantees is chronological.

    ``policy`` decides where the candidate set comes from -- see
    :class:`CandidatePolicy`.  It defaults to :attr:`CandidatePolicy.MANIFEST`
    when a manifest is supplied and :attr:`CandidatePolicy.OPEN_SET` otherwise,
    because the safe default has to be the one that neither leaks the future nor
    crashes on an unseen location.
    """

    if minimum_locations < 1:
        raise ValueError("minimum_locations must be at least 1")
    if not 0.0 < train_fraction <= 1.0:
        raise ValueError("train_fraction must lie in (0, 1]")

    declared = dict(candidate_locations or {})
    if policy is CandidatePolicy.MANIFEST and not declared:
        raise ValueError("CandidatePolicy.MANIFEST needs candidate_locations")

    grouped: dict[ProjectOneBindingKey, list[ProjectOneDatasetRecord]] = {}
    for record in stream.records:
        key = ProjectOneBindingKey(
            household_id=record.household_id,
            subject_id=record.subject_id,
            object_id=record.object_id,
        )
        grouped.setdefault(key, []).append(record)

    bindings: list[ProjectOneStreamBinding] = []
    for key, records in grouped.items():
        observed = tuple(dict.fromkeys(record.observed_location for record in records))
        prefix_length = max(1, int(len(records) * train_fraction))
        prefix = tuple(
            dict.fromkeys(record.observed_location for record in records[:prefix_length])
        )

        # Resolved per binding, not once for the stream: a partial manifest is a
        # normal situation (the operator knows some rooms, not all), and forcing
        # it to be all-or-nothing would push callers into declaring guesses.
        resolved = policy or (
            CandidatePolicy.MANIFEST if key in declared else CandidatePolicy.OPEN_SET
        )

        if resolved is CandidatePolicy.MANIFEST:
            if key not in declared:
                raise ValueError(f"no declared candidate set for {key}")
            locations = tuple(dict.fromkeys(declared[key]))
            missing = [name for name in observed if name not in locations]
            if missing:
                raise ValueError(
                    f"declared candidate set for {key} omits observed location(s) "
                    f"{sorted(missing)}; declare them, or use CandidatePolicy.OPEN_SET "
                    "to route unseen locations to an explicit bucket"
                )
            source = "manifest"
        elif resolved is CandidatePolicy.TRAIN_ONLY:
            locations = prefix
            source = "train_only"
        elif resolved is CandidatePolicy.OPEN_SET:
            base = tuple(declared[key]) if key in declared else prefix
            locations = (*dict.fromkeys(base), OPEN_SET_LOCATION)
            source = "open_set"
        else:  # OBSERVED_ALL
            locations = observed
            source = "observed_all"

        evaluable = len(locations) >= minimum_locations
        reason = ""
        if not evaluable:
            reason = (
                f"single observed location {locations[0]!r}: a method needs at least "
                f"{minimum_locations} candidates to discriminate between"
                if len(locations) == 1
                else f"only {len(locations)} candidate location(s)"
            )
        bindings.append(
            ProjectOneStreamBinding(
                key=key,
                stream_id=stream.manifest.stream_id,
                records=tuple(records),
                candidate_locations=locations,
                location_source=source,
                is_evaluable=evaluable,
                skip_reason=reason,
            )
        )
    return tuple(bindings)


class ProjectOneMethodFactory:
    """Build one fresh arm set per binding.

    The isolation guarantee is deliberately structural: every call constructs
    new component objects, so no Dirichlet table, RLS head, CF-BOCPD beam or
    CCRR bank can outlive the binding it was built for.  Nothing depends on a
    caller remembering to key their state correctly.
    """

    def __init__(
        self,
        *,
        config: ProjectOneProtocolConfig | None = None,
        bocpd_config: CategoricalBOCPDConfig | None = None,
        frequency_config: ContextFrequencyConfig | None = None,
        persistence_config: PersistenceConfig | None = None,
    ) -> None:
        self.config = config or ProjectOneProtocolConfig()
        self.bocpd_config = bocpd_config
        self.frequency_config = frequency_config
        self.persistence_config = persistence_config

    def build(self, binding: ProjectOneStreamBinding) -> tuple[ProjectOneMethod, ...]:
        """The seven fixed-parameter pilot arms, in :data:`PILOT_ARM_NAMES` order."""

        if not binding.is_evaluable:
            raise ValueError(
                f"binding {binding.binding_id} is not evaluable: {binding.skip_reason}"
            )

        open_set = binding.location_source == CandidatePolicy.OPEN_SET.value
        arms: list[ProjectOneMethod] = [
            CoreHabitChainMethod(
                name=name,
                locations=binding.candidate_locations,
                owner_id=binding.key.subject_id,
                household_id=binding.key.household_id,
                object_id=binding.key.object_id,
                config=replace(self.config, ablation=ablation, residual_calibration=calibration),
                open_set=open_set,
            )
            for name, ablation, calibration in _CHAIN_ARMS
        ]
        arms.append(
            CategoricalBOCPDMethod(
                binding.candidate_locations, self.bocpd_config, open_set=open_set
            )
        )
        arms.append(
            ContextFrequencyMethod(
                binding.candidate_locations, self.frequency_config, open_set=open_set
            )
        )
        arms.append(
            PersistenceMethod(
                binding.candidate_locations, self.persistence_config, open_set=open_set
            )
        )
        return tuple(arms)
