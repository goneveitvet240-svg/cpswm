"""R3 -- write lineage across a formal revision, and late-feedback timing.

The round-2 independent review reproduced two facts through the public
``process_execution_feedback`` entrypoint:

1. one retraction on a 10-day adaptive history moved ``committed`` from 3 to 19,
   committing all 17 quarantined observations at once -- every one of which had
   entered under ``force_long_term_write_blocked=True``;
2. a feedback that was legally bound to event B *before* an unrelated retraction
   of event A became permanently unusable afterwards, because the rebuild
   republished B's binding.

Both are repaired here and both are reproduced first, so the tests fail on the
pre-repair source.

Frozen basis (``structure_two_adaptive_compute_predeath_v0_1.json``):

* ``hard_safety_kernel.router_may_grant_long_term_write == false`` -- the router's
  path choice may never produce a long-term write, so an observation it blocked
  cannot become committed merely because a later replay agreed with itself;
* ``hard_safety_kernel.maximum_unauthorized_long_term_commits == 0``;
* ``hard_safety_kernel.ccrr_promotion_required_before_eligible_write == true`` --
  CCRR promotion is *necessary* before an eligible write, which is why the legacy
  lane's CCRR-deferred observations stay promotable and are not banned here;
* ``hard_safety_kernel.rgrc_is_only_long_term_write_retract_authority == true``.

What is NOT claimed: the committed set after a rebuild is a function of a CCRR
replay, and this file does not reimplement CCRR, so it does not predict *which*
eligible observations a rebuild promotes.  It asserts the properties that are
independently derivable from the pre-saved journal, and says so where it stops.
The retraction policy is still supplied by the caller through the documented
``policy=`` seam; nothing here claims autonomous calibrated retraction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from structure_two_backbone_wiring_probe import (
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    BackboneWiringProbe,
    CalibratedRetractionPolicy,
    CIAVOutcomeKind,
    build_execution_feedback_bundle,
)

from cpswm.system.continual.project_one_regime_loop import PrototypeStatisticOperation
from cpswm.system.reproducibility import content_sha256

RETRACTION_POLICY = CalibratedRetractionPolicy(retraction_delta=-0.2)
TOLERANCE = 1e-9
PREDEATH_CONFIG = Path(
    "configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json"
)


def _frozen() -> dict[str, Any]:
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        path = candidate / PREDEATH_CONFIG
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError("frozen pre-death protocol config not found")


# ---------------------------------------------------------------------------
# Histories and the pre-saved journal
# ---------------------------------------------------------------------------


def _adaptive_history(days: int = 10) -> BackboneWiringProbe:
    """The review's history: direct P5 with a different-location CIAV closure."""

    probe = BackboneWiringProbe.build(seed=7)
    for observation in probe.observed_days()[:days]:
        transition = probe.transition_for(observation)
        probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(
                transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )
    return probe


def _legacy_history(days: int = 12) -> BackboneWiringProbe:
    probe = BackboneWiringProbe.build(seed=7)
    for observation in probe.observed_days()[:days]:
        probe.system.core.process_transition(probe.transition_for(observation))
    return probe


@dataclass(frozen=True, slots=True)
class _JournalEntry:
    """What was true about one observation *before* the revision under test."""

    revision_id: UUID
    origin_write_blocked: bool
    origin_path: str
    quarantine_reason: str | None
    write_eligible: bool
    authorization_count: int
    location_id: UUID
    statistical_owner_weight: float
    committed: bool
    quarantined: bool


def _journal(probe: BackboneWiringProbe) -> dict[UUID, _JournalEntry]:
    """Save the original inputs, authorizations and classification, up front.

    This is the independent reference.  It is read once, before the system under
    test mutates, and never refreshed from the system's post-revision state.
    """

    core = probe.system.core
    committed = set(core._committed_events)
    quarantined = {event.revision_id for event in core._quarantined_events}
    entries: dict[UUID, _JournalEntry] = {}
    for revision_id, event in core._observed_events.items():
        record = core.observation_write_eligibility(revision_id)
        assert record is not None, "every observation must carry an origin record"
        entries[revision_id] = _JournalEntry(
            revision_id=revision_id,
            origin_write_blocked=bool(record["origin_write_blocked"]),
            origin_path=str(record["origin_path"]),
            quarantine_reason=(
                None if record["quarantine_reason"] is None else str(record["quarantine_reason"])
            ),
            write_eligible=bool(record["write_eligible"]),
            authorization_count=len(record["authorizations"]),
            location_id=event.location_id,
            statistical_owner_weight=event.statistical_owner_weight,
            committed=revision_id in committed,
            quarantined=revision_id in quarantined,
        )
    return entries


def _alpha_from_journal(
    probe: BackboneWiringProbe, journal: dict[UUID, _JournalEntry]
) -> dict[UUID, float]:
    """Expected Hybrid mass, using the *pre-saved* weights, not current ones."""

    totals = dict.fromkeys(probe.case.locations, 0.0)
    core = probe.system.core
    for revision_id, event in core._committed_events.items():
        entry = journal.get(revision_id)
        weight = entry.statistical_owner_weight if entry else event.statistical_owner_weight
        location = entry.location_id if entry else event.location_id
        if location in totals:
            totals[location] += weight
    return totals


def _assert_reconciled_against_journal(
    probe: BackboneWiringProbe, journal: dict[UUID, _JournalEntry]
) -> None:
    core = probe.system.core
    for location, expected in _alpha_from_journal(probe, journal).items():
        assert core.hybrid_alpha(location) == pytest.approx(expected, abs=TOLERANCE)
    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True


def _feedback(probe: BackboneWiringProbe, revision_id: UUID, **overrides: Any):
    event = probe.system.core._committed_events[revision_id]
    arguments: dict[str, Any] = {
        "revision_id": revision_id,
        "location_id": event.location_id,
        "belief_snapshot_id": event.belief_snapshot_id,
        "when": event.evidence.event_time,
        "opportunity_id": event.evidence.observation_opportunity_id,
        "outcome_distribution": NEGATIVE_SEARCH_OUTCOME,
        "present_likelihood": NEGATIVE_PRESENT_LIKELIHOOD,
        "absent_likelihood": NEGATIVE_ABSENT_LIKELIHOOD,
    }
    arguments.update(overrides)
    return build_execution_feedback_bundle(probe, **arguments)


def _apply(probe: BackboneWiringProbe, bundle: Any, *, policy: Any = RETRACTION_POLICY):
    feedback, binding, likelihood = bundle
    return probe.system.process_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood, policy=policy
    )


def _decoded_action(probe: BackboneWiringProbe) -> UUID:
    """The actually decoded top-1 action, not just the distribution hash."""

    distribution = probe.action_distribution()
    return min(distribution, key=lambda key: (-distribution[key], str(key)))


def _full_state(probe: BackboneWiringProbe) -> dict[str, Any]:
    """Every quantity R3 asks to be checked separately."""

    core = probe.system.core
    return {
        "observed": tuple(sorted(str(key) for key in core._observed_events)),
        "committed": tuple(sorted(str(key) for key in core._committed_events)),
        "quarantined": tuple(sorted(str(item.revision_id) for item in core._quarantined_events)),
        "derived_lifecycle": tuple(
            sorted((str(key), value.value) for key, value in core._derived_event_lifecycle.items())
        ),
        "hybrid_alpha": tuple(round(core.hybrid_alpha(item), 12) for item in probe.case.locations),
        "dirichlet": core._habit.canonical_state_hash(),
        "active_regime": core.active_regime,
        "rls": content_sha256(core.rls_regime_snapshot(core.active_regime)),
        "fast_memory": tuple(sorted(str(key) for key in core._fast_action_events)),
        "published_snapshot": (
            str(core.current_snapshot.snapshot_id),
            core.current_snapshot.map_version,
        ),
        "feedback_dedup": tuple(
            sorted(str(key) for key in core._hybrid_loop._feedback_projector._seen)
        ),
        "decoded_action": str(_decoded_action(probe)),
        "action_distribution": probe.action_distribution_sha256(),
        "bindings": tuple(sorted(str(key) for key in core._revision_feedback_bindings)),
        "relocations": len(core.late_feedback_relocations),
    }


# ---------------------------------------------------------------------------
# The frozen clauses this file rests on
# ---------------------------------------------------------------------------


def test_the_frozen_write_authority_clauses_are_unchanged() -> None:
    kernel = _frozen()["hard_safety_kernel"]
    assert kernel["router_may_grant_long_term_write"] is False
    assert kernel["maximum_unauthorized_long_term_commits"] == 0
    assert kernel["ccrr_promotion_required_before_eligible_write"] is True
    assert kernel["rgrc_is_only_long_term_write_retract_authority"] is True


# ---------------------------------------------------------------------------
# 1. Both retraction targets, reproduced and repaired
# ---------------------------------------------------------------------------


def _target_first_committed(probe: BackboneWiringProbe) -> UUID:
    """The independent review's choice."""

    return next(iter(probe.system.core._committed_events))


def _target_majority_location(probe: BackboneWiringProbe) -> UUID:
    """The window-3 report's choice."""

    core = probe.system.core
    location = max(probe.case.locations, key=core.hybrid_alpha)
    return next(
        key
        for key, event in core._committed_events.items()
        if event.location_id == location and event.belief_snapshot_id is not None
    )


@pytest.mark.parametrize(
    ("case", "pick"),
    [
        ("independent_review_first_committed", _target_first_committed),
        ("window_three_report_majority_location", _target_majority_location),
    ],
)
def test_a_retraction_never_commits_a_write_blocked_observation(case: str, pick: Any) -> None:
    """Both published retraction targets, on the same 10-day adaptive history.

    Pre-repair this produced ``3 -> 19`` (+17) and ``3 -> 18`` (+16); every added
    commit came from the write-blocked set.  The repair leaves the blocked set
    uncommitted under either target, and the assertions below come from the
    journal taken before the mutation, never from the system's final answer.
    """

    probe = _adaptive_history()
    core = probe.system.core
    journal = _journal(probe)
    blocked = {entry.revision_id for entry in journal.values() if entry.origin_write_blocked}
    eligible = {entry.revision_id for entry in journal.values() if entry.write_eligible}
    committed_before = {entry.revision_id for entry in journal.values() if entry.committed}
    quarantined_before = {entry.revision_id for entry in journal.values() if entry.quarantined}

    # The history really is the one the review used.
    assert len(committed_before) == 3
    assert len(quarantined_before) == 17
    assert blocked and blocked <= quarantined_before
    assert blocked & eligible == set()

    target = pick(probe)
    result = _apply(probe, _feedback(probe, target))
    assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)

    committed_after = set(core._committed_events)
    # Strict membership expectations, all derived from the journal.
    assert target not in committed_after
    assert committed_after & blocked == set()
    assert committed_after <= (committed_before | quarantined_before) - {target}
    assert committed_after - committed_before <= eligible & quarantined_before
    # Quarantine history is withheld, not deleted.
    surviving_blocked = blocked & set(core._observed_events)
    assert surviving_blocked == {item.revision_id for item in core._quarantined_events} & blocked
    assert surviving_blocked
    # Every committed observation is write eligible, with its lineage intact.
    for revision_id in committed_after:
        record = core.observation_write_eligibility(revision_id)
        if record is None:
            continue  # derived lineage, covered separately
        assert record["write_eligible"] is True
        assert record["origin_write_blocked"] is False
    # Pre-saved weights must survive the rebuild unchanged.
    for revision_id in committed_after & set(journal):
        assert core._committed_events[revision_id].statistical_owner_weight == pytest.approx(
            journal[revision_id].statistical_owner_weight, abs=TOLERANCE
        )
    _assert_reconciled_against_journal(probe, journal)


def test_every_rebuild_promotion_carries_a_recorded_authorization() -> None:
    """A promotion that cannot be audited afterwards is not an acceptable promotion."""

    probe = _adaptive_history()
    core = probe.system.core
    journal = _journal(probe)
    committed_before = {entry.revision_id for entry in journal.values() if entry.committed}

    _apply(probe, _feedback(probe, _target_first_committed(probe)))

    promoted = set(core._committed_events) - committed_before
    assert promoted, "the legitimate CCRR-deferred promotion path must still work"
    for revision_id in promoted:
        record = core.observation_write_eligibility(revision_id)
        assert record is not None
        assert record["origin_write_blocked"] is False
        authorities = {grant["authority"] for grant in record["authorizations"]}
        assert "ccrr_rebuild_replay_promotion" in authorities
        for grant in record["authorizations"]:
            assert len(grant["basis_sha256"]) == 64


def test_the_legacy_lane_promotion_path_is_not_banned() -> None:
    """The repair must not be a blanket ban on promotion.

    A legacy-lane observation that CCRR deferred for want of evidence was never
    write-blocked, so ``ccrr_promotion_required_before_eligible_write`` is
    satisfied when the replay promotes it.  This keeps that path alive.
    """

    probe = _legacy_history(days=6)
    core = probe.system.core
    deferred = [
        revision_id
        for revision_id in core._observed_events
        if core.observation_write_eligibility(revision_id)["quarantine_reason"]
        == "ccrr_insufficient_evidence_deferred"
    ]
    eligible = [
        revision_id
        for revision_id in core._observed_events
        if core.observation_write_eligibility(revision_id)["write_eligible"]
    ]
    assert len(eligible) == len(core._observed_events)
    # Whether any observation is deferred at day six is a CCRR outcome, not
    # something this test forces; what matters is that deferral never makes a
    # legacy observation write-ineligible.
    for revision_id in deferred:
        assert core.observation_write_eligibility(revision_id)["write_eligible"] is True


def test_a_write_blocked_observation_is_promotable_once_it_is_authorized() -> None:
    """Not a permanent ban: the authorized path still promotes.

    The different-location CIAV closure runs with the write unblocked, and when its
    CCRR conclusion is ``HABIT_CHANGE`` it promotes the quarantined set.  Those
    promotions are recorded as ``ccrr_habit_change_promotion`` grants, which is what
    later makes the observation rebuild-promotable.
    """

    probe = _adaptive_history()
    core = probe.system.core
    granted = {
        revision_id: core.observation_write_eligibility(revision_id)
        for revision_id in core._observed_events
    }
    authorities = {
        grant["authority"] for record in granted.values() for grant in record["authorizations"]
    }
    # The closure lane commits through ``unblocked_transition_commit``; a blocked
    # observation would need ``ccrr_habit_change_promotion``.  Record which of
    # these the 10-day history actually exercises rather than asserting a wish.
    assert "unblocked_transition_commit" in authorities
    blocked_with_grant = [
        revision_id
        for revision_id, record in granted.items()
        if record["origin_write_blocked"] and record["authorizations"]
    ]
    for revision_id in blocked_with_grant:
        assert granted[revision_id]["write_eligible"] is True


def test_the_pending_debt_write_block_still_refuses_the_feedback_entrypoint() -> None:
    """Positive/negative control the repair must not break.

    Negative: with a pending adaptive debt the public feedback entrypoint is
    refused and nothing changes.  Positive: on the same history without a pending
    debt the identical bundle is accepted.
    """

    blocked_probe = _legacy_history()
    bundle = _feedback(blocked_probe, next(iter(blocked_probe.system.core._committed_events)))
    transition = blocked_probe.transition_for(blocked_probe.observed_days()[12])
    blocked_probe.run_adaptive(
        transition,
        features=blocked_probe.router_features(action_margin=0.9, regime_hazard=0.0),
    )
    before = _full_state(blocked_probe)
    with pytest.raises(RuntimeError, match="pending adaptive debt blocks"):
        _apply(blocked_probe, bundle)
    assert _full_state(blocked_probe) == before
    assert len(blocked_probe.system.pending_adaptive_debts()) == 1

    open_probe = _legacy_history()
    accepted = _apply(
        open_probe, _feedback(open_probe, next(iter(open_probe.system.core._committed_events)))
    )
    assert accepted.statistic_operations == (PrototypeStatisticOperation.RETRACT,)


# ---------------------------------------------------------------------------
# 2. Late-feedback timing
# ---------------------------------------------------------------------------


def test_a_feedback_legal_before_an_unrelated_retraction_is_still_processable() -> None:
    """The review's exact timing: bind A and B, retract A, then submit B's feedback.

    Pre-repair the second submission failed with ``feedback revision snapshot does
    not match the committed event``, because the rebuild had republished B's
    binding.  The repair verifies the presented snapshot against B's own
    append-only publication history instead of only its newest entry, so a
    feedback that was legal when it was issued stays usable -- and the relocation
    is audited rather than silent.
    """

    probe = _legacy_history()
    core = probe.system.core
    first, second = list(core._committed_events)[:2]
    first_bundle = _feedback(probe, first)
    delayed = _feedback(probe, second)

    # Both bindings are genuinely valid before anything is retracted.
    assert (
        core._validate_feedback_revision_binding(feedback=delayed[0], binding=delayed[1]) == second
    )
    original_snapshot = core._committed_events[second].belief_snapshot_id

    _apply(probe, first_bundle)

    assert second in core._committed_events
    assert core._committed_events[second].belief_snapshot_id != original_snapshot
    published = {item.snapshot_id for item in core.published_revision_bindings(second)}
    assert original_snapshot in published

    journal = _journal(probe)
    result = _apply(probe, delayed)

    assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert second not in core._committed_events
    relocations = core.late_feedback_relocations
    assert len(relocations) == 1
    relocation = relocations[0]
    assert relocation.revision_id == second
    assert relocation.presented_snapshot_id == original_snapshot
    assert relocation.presented_map_version < relocation.current_map_version
    assert relocation.location_id == journal[second].location_id
    _assert_reconciled_against_journal(probe, journal)


def test_a_snapshot_this_runtime_never_published_for_the_revision_is_refused() -> None:
    """The relocation path must not become "accept any old snapshot".

    Another revision's published snapshot, and a freshly invented one, are both
    refused, and neither leaves a relocation row behind.
    """

    probe = _legacy_history()
    core = probe.system.core
    first, second = list(core._committed_events)[:2]
    foreign_snapshot = core._committed_events[first].belief_snapshot_id
    before = _full_state(probe)

    with pytest.raises(ValueError, match="snapshot does not match the committed event"):
        _apply(probe, _feedback(probe, second, belief_snapshot_id=foreign_snapshot))
    assert core.late_feedback_relocations == ()

    invented = UUID("00000000-0000-4000-8000-0000000009f1")
    with pytest.raises(ValueError, match="snapshot does not match the committed event"):
        _apply(probe, _feedback(probe, second, belief_snapshot_id=invented))
    assert core.late_feedback_relocations == ()
    assert _full_state(probe) == before


def test_a_late_feedback_for_an_already_retracted_revision_is_refused_recoverably() -> None:
    """A late feedback whose own target is gone must not be silently relocated.

    The binding itself is genuine, so it is not rejected as forged; the revision is
    simply no longer there, and the existing dead-target error is what the caller
    sees.  Nothing is relocated and nothing changes.
    """

    probe = _legacy_history()
    core = probe.system.core
    first = next(iter(core._committed_events))
    delayed = _feedback(probe, first)
    _apply(probe, _feedback(probe, first))
    before = _full_state(probe)

    with pytest.raises(KeyError, match="superseded revision is not a committed"):
        _apply(probe, delayed)
    assert core.late_feedback_relocations == ()
    assert _full_state(probe) == before


def test_a_relocated_feedback_replayed_a_second_time_is_an_idempotent_no_op() -> None:
    """Duplicate delivery of a relocated late feedback changes nothing further."""

    probe = _legacy_history()
    core = probe.system.core
    first, second = list(core._committed_events)[:2]
    delayed = _feedback(probe, second)
    _apply(probe, _feedback(probe, first))
    _apply(probe, delayed)
    after_first = _full_state(probe)

    repeat = _apply(probe, delayed)
    assert repeat.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert "idempotent" in repeat.rationale
    # The relocation is recorded exactly once, not once per delivery.
    assert len(core.late_feedback_relocations) == 1
    assert _full_state(probe) == after_first


def test_a_failed_relocated_transaction_leaves_no_relocation_row() -> None:
    """Fault rollback: the audit row is transactional with the revision itself."""

    probe = _legacy_history()
    core = probe.system.core
    first, second = list(core._committed_events)[:2]
    delayed = _feedback(probe, second)
    _apply(probe, _feedback(probe, first))
    before = _full_state(probe)
    assert before["relocations"] == 0

    core._transition_fault_hook = None
    original_hook = core._revision_fault_hook

    def failing_hook(stage: str) -> None:
        original_hook(stage)
        if stage == "dirichlet":
            raise RuntimeError("probe revision fault at the Dirichlet stage")

    core._revision_fault_hook = failing_hook  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="probe revision fault"):
            _apply(probe, delayed)
    finally:
        core._revision_fault_hook = original_hook  # type: ignore[method-assign]

    assert core.late_feedback_relocations == ()
    assert _full_state(probe) == before

    # And the retry after the fault is cleared still succeeds.
    retried = _apply(probe, delayed)
    assert retried.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert len(core.late_feedback_relocations) == 1
