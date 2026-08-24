"""Plant known changes into a real stream, so real data can be scored at all.

Real household logs carry no change-point annotation.  Waiting for hand-labelled
ones means never running on real data; deriving them from the model under test
means grading its own homework.  The third option is to take a real stream and
plant a change whose time, location and cause *we* chose -- semi-synthetic
evaluation.

Two rules make the result trustworthy, and both are enforced here rather than
left to the caller.

**A disturbance is not a change.**  ``one_shot_disturbance`` and
``temporary_disturbance`` carry ``true_change_point = False`` by construction.
They exist to catch false alarms, and an injector that labelled them as changes
would reward exactly the behaviour the project is trying to suppress.

**The source stream is never mutated.**  Injection returns a new stream and
records the source's content hash, so the baseline run stays reproducible and
the injection log always describes a stream someone can rebuild.

Scope, stated plainly: the base habit is taken to be what the log actually
observed.  That is an assumption, not a fact -- a real log already contains
real changes we did not plant, and an arm may legitimately flag one.  Results
here are therefore about *detecting the planted change*, never about a clean
false-positive rate.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from .dataset_adapters import InMemoryAdapter
from .project_one_dataset import (
    ChangeCause,
    ProjectOneGroundTruth,
    ProjectOneStream,
    ProjectOneTruthSet,
)

__all__ = [
    "DEFAULT_LOCATION_POOL",
    "SEMI_SYNTHETIC_VERSION",
    "InjectionBlock",
    "InjectionKind",
    "InjectionRecord",
    "SemiSyntheticResult",
    "inject_changes",
]

SEMI_SYNTHETIC_VERSION = "project-one-semi-synthetic@0.1"

#: Household locations to relocate an object *to*.  Deliberately generic: the
#: injected location only has to be somewhere the current habit is not, and
#: drawing from the stream's own vocabulary would sometimes be impossible (a
#: stream where the object never moved has a vocabulary of one).
DEFAULT_LOCATION_POOL: tuple[str, ...] = (
    "balcony",
    "desk",
    "shelf",
    "counter",
    "cabinet",
    "sofa",
)


class InjectionKind(StrEnum):
    """The four planted patterns, and what each one is for."""

    #: A single event elsewhere, then straight back.  Catches arms that treat
    #: any outlier as a new habit.
    ONE_SHOT_DISTURBANCE = "one_shot_disturbance"
    #: A short run elsewhere, then back.  Catches arms whose confirmation
    #: window is too short to tell a trip away from a move.
    TEMPORARY_DISTURBANCE = "temporary_disturbance"
    #: Relocated from a point onward, permanently.  The only unambiguous
    #: change point in the set.
    PERMANENT_CHANGE = "permanent_change"
    #: Two separated runs at the *same* new location.  Tests whether an arm can
    #: reuse a regime it has already seen instead of inventing a second one.
    RECURRING_REGIME = "recurring_regime"


#: Processing order.  ``PERMANENT_CHANGE`` runs to the end of the stream by
#: definition, so it is always placed last; the others get earlier, disjoint
#: windows.
_ORDER: tuple[InjectionKind, ...] = (
    InjectionKind.ONE_SHOT_DISTURBANCE,
    InjectionKind.TEMPORARY_DISTURBANCE,
    InjectionKind.RECURRING_REGIME,
    InjectionKind.PERMANENT_CHANGE,
)

#: Events each kind needs, including room to return to the base habit.
_MINIMUM_SPAN: Mapping[InjectionKind, int] = {
    InjectionKind.ONE_SHOT_DISTURBANCE: 3,
    InjectionKind.TEMPORARY_DISTURBANCE: 6,
    InjectionKind.RECURRING_REGIME: 10,
    InjectionKind.PERMANENT_CHANGE: 4,
}

#: Injection kind -> the evaluator's shared cause vocabulary.
#:
#: The kind is *provenance* (which plant produced this event) and the cause is
#: *semantics* (what the evaluator should make of it).  They were once the same
#: string, spelled privately here -- with the result that the metric module,
#: which recognises only :data:`ANOMALY_CAUSES`, saw none of these and scored
#: every semi-synthetic ``anomaly_detection_rate`` as exactly zero.  The kind
#: still travels, on :class:`InjectionRecord`, where it cannot affect scoring.
_CAUSE: Mapping[InjectionKind, ChangeCause] = {
    InjectionKind.ONE_SHOT_DISTURBANCE: ChangeCause.TRANSIENT,
    InjectionKind.TEMPORARY_DISTURBANCE: ChangeCause.TRANSIENT,
    InjectionKind.PERMANENT_CHANGE: ChangeCause.OWNER_HABIT,
    InjectionKind.RECURRING_REGIME: ChangeCause.REGIME_RECURRENCE,
}


@dataclass(frozen=True, slots=True)
class InjectionBlock:
    """One contiguous run of relocated events."""

    location: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InjectionRecord:
    """Everything needed to reconstruct one planted change."""

    kind: InjectionKind
    stream_id: str
    original_location: str
    injected_location: str
    duration: int
    affected_event_ids: tuple[str, ...]
    #: ``None`` for disturbances -- that is the point of them.
    change_point_event_id: str | None
    cause: ChangeCause
    blocks: tuple[InjectionBlock, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "stream_id": self.stream_id,
            "original_location": self.original_location,
            "injected_location": self.injected_location,
            "duration": self.duration,
            "affected_event_ids": list(self.affected_event_ids),
            "change_point_event_id": self.change_point_event_id,
            "cause": self.cause.value,
            "blocks": [
                {"location": block.location, "event_ids": list(block.event_ids)}
                for block in self.blocks
            ],
        }


@dataclass(frozen=True, slots=True)
class SemiSyntheticResult:
    """The injected stream, its truth, and the log of what was planted."""

    stream: ProjectOneStream
    truth: ProjectOneTruthSet
    injections: tuple[InjectionRecord, ...]
    source_content_hash: str


@dataclass(frozen=True, slots=True)
class _Plan:
    """One kind's placement, resolved before anything is written."""

    kind: InjectionKind
    indices: tuple[int, ...]
    blocks: tuple[tuple[int, ...], ...]
    location: str
    change_point_index: int | None


def _slots(
    kinds: Sequence[InjectionKind], *, warmup: int, total: int
) -> list[tuple[InjectionKind, int, int]]:
    """Disjoint windows, one per kind, left to right."""

    usable = total - warmup
    need = sum(_MINIMUM_SPAN[kind] for kind in kinds)
    if usable < need:
        raise ValueError(
            f"stream too short for {[kind.value for kind in kinds]}: {total} event(s) with a "
            f"{warmup}-event warm-up leaves {usable}, and {need} are needed"
        )

    windows: list[tuple[InjectionKind, int, int]] = []
    cursor = warmup
    spare = usable - need
    remaining = len(kinds)
    for index, kind in enumerate(kinds):
        remaining -= 1
        if index == len(kinds) - 1:
            end = total
        else:
            extra = spare // (len(kinds) - index)
            spare -= extra
            end = cursor + _MINIMUM_SPAN[kind] + extra
        windows.append((kind, cursor, end))
        cursor = end
    return windows


def _pick_location(rng: random.Random, *, original: str, pool: Sequence[str]) -> str:
    options = [name for name in pool if name != original]
    if not options:
        raise ValueError(f"location pool offers nothing other than {original!r}")
    return rng.choice(options)


def _plan_one(
    kind: InjectionKind,
    *,
    start: int,
    end: int,
    total: int,
    base: Sequence[str],
    rng: random.Random,
    pool: Sequence[str],
) -> _Plan:
    if kind is InjectionKind.ONE_SHOT_DISTURBANCE:
        index = rng.randrange(start, end - 1)
        location = _pick_location(rng, original=base[index], pool=pool)
        return _Plan(kind, (index,), ((index,),), location, None)

    if kind is InjectionKind.TEMPORARY_DISTURBANCE:
        span = rng.randint(2, min(4, (end - start) - 2))
        index = rng.randrange(start, end - span - 1)
        indices = tuple(range(index, index + span))
        location = _pick_location(rng, original=base[index], pool=pool)
        return _Plan(kind, indices, (indices,), location, None)

    if kind is InjectionKind.PERMANENT_CHANGE:
        index = rng.randrange(start, total - 1)
        indices = tuple(range(index, total))
        location = _pick_location(rng, original=base[index], pool=pool)
        return _Plan(kind, indices, (indices,), location, index)

    block = rng.randint(2, 3)
    gap = rng.randint(2, 3)
    first_start = rng.randrange(start, end - (2 * block + gap))
    second_start = first_start + block + gap
    first = tuple(range(first_start, first_start + block))
    second = tuple(range(second_start, second_start + block))
    location = _pick_location(rng, original=base[first_start], pool=pool)
    return _Plan(kind, first + second, (first, second), location, first_start)


def inject_changes(
    stream: ProjectOneStream,
    truth: ProjectOneTruthSet | None = None,
    *,
    kinds: Sequence[InjectionKind],
    seed: int,
    location_pool: Sequence[str] = DEFAULT_LOCATION_POOL,
    split: str = "semi-synthetic",
) -> SemiSyntheticResult:
    """Plant the requested changes into a copy of ``stream``.

    ``kinds`` is treated as a set: each kind is planted at most once, in the
    fixed order of :data:`_ORDER`, into disjoint windows.  A warm-up prefix is
    always left untouched so every arm has a baseline before the first plant.
    """

    requested = tuple(kind for kind in _ORDER if kind in set(kinds))
    if not requested:
        raise ValueError("at least one injection kind is required")

    records = stream.records
    total = len(records)
    base = [record.observed_location for record in records]
    warmup = max(3, total // 8)

    rng = random.Random(seed)
    windows = _slots(requested, warmup=warmup, total=total)
    plans = [
        _plan_one(kind, start=start, end=end, total=total, base=base, rng=rng, pool=location_pool)
        for kind, start, end in windows
    ]

    observed = list(base)
    expected = list(base)
    regimes = ["base"] * total
    change_points: set[int] = set()
    causes: dict[int, ChangeCause] = {}
    injections: list[InjectionRecord] = []

    for order, plan in enumerate(plans):
        for index in plan.indices:
            observed[index] = plan.location
            causes[index] = _CAUSE[plan.kind]

        # A disturbance leaves the habit where it was; only a real change moves
        # the location the truth says the object *should* be at.
        if plan.kind is InjectionKind.PERMANENT_CHANGE:
            for index in plan.indices:
                expected[index] = plan.location
                regimes[index] = f"permanent-{order}"
            change_points.update(block[0] for block in plan.blocks)
        elif plan.kind is InjectionKind.RECURRING_REGIME:
            for block in plan.blocks:
                for index in block:
                    expected[index] = plan.location
                    regimes[index] = f"recurring-{order}"
                change_points.add(block[0])

        injections.append(
            InjectionRecord(
                kind=plan.kind,
                stream_id=stream.manifest.stream_id,
                original_location=base[plan.indices[0]],
                injected_location=plan.location,
                duration=len(plan.indices),
                affected_event_ids=tuple(records[index].event_id for index in plan.indices),
                change_point_event_id=(
                    records[plan.change_point_index].event_id
                    if plan.change_point_index is not None
                    else None
                ),
                cause=_CAUSE[plan.kind],
                blocks=tuple(
                    InjectionBlock(
                        location=plan.location,
                        event_ids=tuple(records[index].event_id for index in block),
                    )
                    for block in plan.blocks
                ),
            )
        )

    injected_records = [
        replace(record, observed_location=observed[index]) for index, record in enumerate(records)
    ]
    injected_truths = [
        ProjectOneGroundTruth(
            stream_id=record.stream_id,
            event_id=record.event_id,
            expected_location=expected[index],
            true_regime_id=regimes[index],
            true_change_point=index in change_points,
            true_change_cause=causes.get(index),
        )
        for index, record in enumerate(records)
    ]
    if truth is not None:
        # Anything the source already knew about an event survives unless the
        # injection explicitly overrode it.
        by_event = {item.event_id: item for item in injected_truths}
        for index, record in enumerate(records):
            existing = truth.get(record.event_id)
            if existing is None or index in causes:
                continue
            by_event[record.event_id] = replace(
                by_event[record.event_id],
                expected_location=existing.expected_location or expected[index],
                true_regime_id=existing.true_regime_id or regimes[index],
                true_change_point=existing.true_change_point,
                true_change_cause=existing.true_change_cause,
            )
        injected_truths = [by_event[record.event_id] for record in records]

    adapter = InMemoryAdapter(
        injected_records,
        injected_truths,
        source=f"semi-synthetic/{stream.manifest.source}",
        source_version=SEMI_SYNTHETIC_VERSION,
        preprocessing={
            "seed": str(seed),
            "injections": str(len(injections)),
            "kinds": ",".join(kind.value for kind in requested),
            "warmup_events": str(warmup),
            "source_content_hash": stream.manifest.content_hash,
        },
        change_labels=True,
    )
    injected_stream, injected_truth = adapter.load(stream_id=stream.manifest.stream_id, split=split)
    return SemiSyntheticResult(
        stream=injected_stream,
        truth=injected_truth,
        injections=tuple(injections),
        source_content_hash=stream.manifest.content_hash,
    )
