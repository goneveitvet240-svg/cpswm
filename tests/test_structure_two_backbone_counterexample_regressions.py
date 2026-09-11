"""Regressions for the independent adversarial counterexamples of 2026-09-11.

Source of the counterexamples:
``docs/reviews/data/structure_two_windows2_3_adversarial_review_2026-09-11/counterexamples.py``.

Each test states the pre-fix observation it pins, and the frozen clause it is
grounded in.  Frozen clauses are quoted from
``configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json``
(``hard_safety_kernel`` and ``legal_paths[P0_SAFE_DEFERRED]``) and from
``ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS`` in ``cpswm.system.structure_two_execution``.

These are engineering contract regressions.  They establish no scientific gate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe,
    CIAVOutcomeKind,
    FailingTraceSink,
    verify_and_flatten,
)

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import AdaptiveMaintenanceContractError

PREDEATH_CONFIG = Path(
    "configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json"
)
P0_ROUTER_FEATURES = {"action_margin": 0.9, "regime_hazard": 0.0}


def _p0_features(probe: BackboneWiringProbe):
    return probe.router_features(**P0_ROUTER_FEATURES)


def _frozen() -> dict[str, Any]:
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        path = candidate / PREDEATH_CONFIG
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError("frozen pre-death protocol config not found")


def _core_state(probe: BackboneWiringProbe) -> tuple[Any, ...]:
    core = probe.system.core
    return (
        probe.observable_state_sha256(),
        core._habit.canonical_state_hash(),
        repr(core._fast_action_events),
        len(core._committed_events),
        len(core._quarantined_events),
        core.active_regime,
        probe.action_distribution_sha256(),
    )


# ---------------------------------------------------------------------------
# The frozen clauses this file depends on must stay frozen.
# ---------------------------------------------------------------------------


def test_the_frozen_hard_safety_kernel_still_carries_the_clauses_used_here() -> None:
    kernel = _frozen()["hard_safety_kernel"]
    assert kernel["provenance_and_dependency_checks_always_executed"] is True
    assert kernel["unexecuted_inference_may_not_be_encoded_as_negative_evidence"] is True
    assert kernel["router_may_grant_long_term_write"] is False
    assert kernel["rgrc_is_only_long_term_write_retract_authority"] is True
    assert kernel["maximum_safety_violations"] == 0
    assert kernel["maximum_provenance_violations"] == 0
    assert kernel["maximum_unresolved_as_negative_events"] == 0
    assert kernel["maximum_unauthorized_long_term_commits"] == 0

    p0 = next(item for item in _frozen()["legal_paths"] if item["path_id"] == "P0_SAFE_DEFERRED")
    assert p0["semantic_purpose"].startswith("Run mandatory semantic and write-safety maintenance")
    assert p0["rgrc_remains_only_long_term_write_authority"] is True
    assert p0["all_seven_operator_receipts_required"] is True


# ---------------------------------------------------------------------------
# R2 -- P0 downstream maintenance must check its declared dependency
# ---------------------------------------------------------------------------


def test_a_clean_p0_run_still_produces_the_seven_receipts_after_the_checks() -> None:
    """Control: the added checks must not break the legal path."""

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_adaptive(transition, features=_p0_features(probe), debt_expiry_steps=1)
    _, rows = verify_and_flatten(sink)

    assert result.path_selection.selected_path_id == "P0_SAFE_DEFERRED"
    assert len(rows) == 7
    assert len(result.debt_certificates) == 1


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"posterior_advanced": True}, "advanced CF-BOCPD posterior"),
        ({"observation_count": -999}, "observation count differs"),
        ({"current_snapshot_sha256": "foreign"}, "current_snapshot_sha256 is not a content hash"),
        ({"current_snapshot_sha256": "f" * 64}, "foreign or stale cause snapshot"),
        ({"current_snapshot_sha256": -999}, "current_snapshot_sha256 is not a content hash"),
        ({"observation_count": True}, "non-integer observation count"),
        (
            {"maintenance_kind": "pchmp_safety_maintenance"},
            "not a cf_bocpd_safety_maintenance",
        ),
        ({"unexpected_field": 1}, "field set drifted"),
    ],
)
def test_ccrr_maintenance_rejects_a_contradictory_cf_bocpd_dependency(
    mutation: dict[str, Any], match: str
) -> None:
    """Pre-fix: every one of these payloads was accepted and only changed a hash.

    Frozen basis: ``hard_safety_kernel.provenance_and_dependency_checks_always_executed``
    plus ``P0_SAFE_DEFERRED``'s deferral ``semantic_purpose``.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    with probe.maintenance_context(transition):
        clean = core._adaptive_cf_bocpd_safety_maintenance()
        assert core._adaptive_ccrr_safety_maintenance(clean)["regime_transition_applied"] is False

        before = _core_state(probe)
        with pytest.raises(AdaptiveMaintenanceContractError, match=match):
            core._adaptive_ccrr_safety_maintenance({**clean, **mutation})
        assert _core_state(probe) == before


def test_ccrr_maintenance_rejects_a_dropped_field_and_a_non_mapping() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    with probe.maintenance_context(transition):
        clean = core._adaptive_cf_bocpd_safety_maintenance()

        dropped = {key: value for key, value in clean.items() if key != "posterior_advanced"}
        with pytest.raises(AdaptiveMaintenanceContractError, match="field set drifted"):
            core._adaptive_ccrr_safety_maintenance(dropped)
        not_a_mapping: Any = ("cf_bocpd_safety_maintenance",)
        with pytest.raises(AdaptiveMaintenanceContractError, match="not a payload mapping"):
            core._adaptive_ccrr_safety_maintenance(not_a_mapping)


def test_ccrr_maintenance_rejects_a_payload_produced_by_another_runtime() -> None:
    """Cross-execution substitution: a payload from a runtime at a different step."""

    source = BackboneWiringProbe.build(seed=7)
    transition = source.transition_for(source.observed_days()[0])
    source.run_direct_p5(transition, ciav_input=source.ciav_input(transition))
    with source.maintenance_context(transition):
        foreign = source.system.core._adaptive_cf_bocpd_safety_maintenance()

    target = BackboneWiringProbe.build(seed=7)
    target_transition = target.transition_for(target.observed_days()[0])
    with target.maintenance_context(target_transition):
        assert foreign != target.system.core._adaptive_cf_bocpd_safety_maintenance()
        before = _core_state(target)
        with pytest.raises(AdaptiveMaintenanceContractError):
            target.system.core._adaptive_ccrr_safety_maintenance(foreign)
        assert _core_state(target) == before


def test_ccrr_maintenance_rejects_a_twin_runtime_payload_at_the_same_head_state() -> None:
    """Round-2 review counterexample ``different_runtime_same_head_accepted``.

    Two freshly built runtimes with the same seed hold byte-identical semantic
    heads, so before this fix the semantic dependency check could not tell them
    apart and the substituted payload was accepted.  The trusted context makes
    the two executions distinguishable without weakening any semantic check.
    """

    source = BackboneWiringProbe.build(seed=7)
    target = BackboneWiringProbe.build(seed=7)
    source_transition = source.transition_for(source.observed_days()[0])
    target_transition = target.transition_for(target.observed_days()[0])

    with source.maintenance_context(source_transition):
        foreign = source.system.core._adaptive_cf_bocpd_safety_maintenance()
    with target.maintenance_context(target_transition):
        native = target.system.core._adaptive_cf_bocpd_safety_maintenance()

        # The two heads really are identical apart from the execution stamp.
        stamp = ("runtime_execution_id", "maintenance_epoch")
        assert {k: v for k, v in foreign.items() if k not in stamp} == {
            k: v for k, v in native.items() if k not in stamp
        }

        before = _core_state(target)
        with pytest.raises(AdaptiveMaintenanceContractError, match="foreign runtime execution"):
            target.system.core._adaptive_ccrr_safety_maintenance(foreign)
        assert _core_state(target) == before


def test_a_payload_from_an_earlier_execution_of_the_same_runtime_is_rejected() -> None:
    """Replay within one runtime: same execution id is not enough, the epoch differs.

    ``provenance_and_dependency_checks_always_executed`` is only a real check if a
    stale-but-well-formed payload from the same runtime cannot be replayed into a
    later execution.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    execution_id = uuid4()

    with probe.maintenance_context(transition, runtime_execution_id=execution_id):
        stale = core._adaptive_cf_bocpd_safety_maintenance()
    with probe.maintenance_context(transition, runtime_execution_id=execution_id):
        fresh = core._adaptive_cf_bocpd_safety_maintenance()
        assert stale["runtime_execution_id"] == fresh["runtime_execution_id"]
        assert stale["maintenance_epoch"] != fresh["maintenance_epoch"]
        before = _core_state(probe)
        with pytest.raises(AdaptiveMaintenanceContractError, match="different execution epoch"):
            core._adaptive_ccrr_safety_maintenance(stale)
        assert _core_state(probe) == before


@pytest.mark.parametrize(
    ("payload_name", "mutation", "match"),
    [
        ("pchmp", {"unexecuted_inference_encoded_as_negative": True}, "negative evidence"),
        ("pchmp", {"message_passing_runtime_type": "foreign.Type"}, "foreign message-passing"),
        ("pchmp", {"maintenance_kind": "ccrr_safety_maintenance"}, "not a pchmp_safety"),
        ("ccrr", {"regime_transition_applied": True}, "applied regime transition"),
        ("ccrr", {"active_regime": "foreign-regime"}, "foreign or stale active regime"),
        ("ccrr", {"pending_candidate_sha256": "0" * 64}, "stale CCRR pending candidate"),
        ("ccrr", {"maintenance_kind": "cf_bocpd_safety_maintenance"}, "not a ccrr_safety"),
    ],
)
def test_rgrc_debt_guard_rejects_a_contradictory_declared_dependency(
    payload_name: str, mutation: dict[str, Any], match: str
) -> None:
    """Pre-fix: ``{"unexecuted_inference_encoded_as_negative": True}`` was accepted.

    Frozen basis:
    ``hard_safety_kernel.unexecuted_inference_may_not_be_encoded_as_negative_evidence``
    with ``maximum_unresolved_as_negative_events == 0``, and
    ``provenance_and_dependency_checks_always_executed``.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    with probe.maintenance_context(transition):
        pchmp = core._adaptive_pchmp_safety_maintenance(transition)
        ccrr = core._adaptive_ccrr_safety_maintenance(core._adaptive_cf_bocpd_safety_maintenance())
        assert core._adaptive_rgrc_debt_guard(pchmp, ccrr)["long_term_write_authorized"] is False

        payloads = {"pchmp": dict(pchmp), "ccrr": dict(ccrr)}
        payloads[payload_name].update(mutation)
        before = _core_state(probe)
        with pytest.raises(AdaptiveMaintenanceContractError, match=match):
            core._adaptive_rgrc_debt_guard(payloads["pchmp"], payloads["ccrr"])
        assert _core_state(probe) == before


def test_the_rgrc_debt_guard_never_authorizes_a_long_term_write() -> None:
    """``router_may_grant_long_term_write`` is ``false`` in the frozen kernel."""

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    for _ in range(3):
        with probe.maintenance_context(transition):
            pchmp = core._adaptive_pchmp_safety_maintenance(transition)
            ccrr = core._adaptive_ccrr_safety_maintenance(
                core._adaptive_cf_bocpd_safety_maintenance()
            )
            guard = core._adaptive_rgrc_debt_guard(pchmp, ccrr)
        assert guard["long_term_write_authorized"] is False
        assert guard["committed_revision_count"] == 0


def test_a_refused_p0_commit_leaves_no_pending_debt_and_no_state_change() -> None:
    """The rejection path must not have mutated state first.

    P0 issues its debt certificate *before* the maintenance loop and before the sink
    commit, so an aborted P0 transaction is the strongest available check that the
    wrapper rolls the debt ledger back with the core.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    before = _core_state(probe)

    with pytest.raises(RuntimeError, match="refused the commit"):
        probe.run_adaptive(
            transition,
            features=_p0_features(probe),
            debt_expiry_steps=1,
            sink=FailingTraceSink(),
        )

    assert probe.system.pending_adaptive_debts() == ()
    assert _core_state(probe) == before


# ---------------------------------------------------------------------------
# R2 -- what the P0 maintenance receipts may and may not be read as
# ---------------------------------------------------------------------------


def test_a_passing_p0_dependency_check_does_not_make_the_body_upstream_dependent() -> None:
    """The honest boundary, pinned as a test.

    The downstream body is a snapshot of live runtime state.  Because a payload must
    *equal* that live state to pass the check, no accepted payload can move the body.
    The receipt therefore proves "dependency checked and consistent", never "upstream
    inference consumed".
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    with probe.maintenance_context(transition):
        clean = core._adaptive_cf_bocpd_safety_maintenance()
        first = core._adaptive_ccrr_safety_maintenance(clean)
        second = core._adaptive_ccrr_safety_maintenance(dict(clean))

    def semantic(body: Mapping[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in body.items() if not k.startswith("consumed_")}

    assert semantic(first) == semantic(second)
    assert first["consumed_cf_bocpd_maintenance_sha256"] == content_sha256(clean)


# ---------------------------------------------------------------------------
# R4/S8 -- the retraction claim the review narrowed
# ---------------------------------------------------------------------------


def test_a_hybrid_only_retraction_does_not_move_the_decoded_action() -> None:
    """Pins the review's own S8 counterexample as an expected, documented limitation.

    Retracting only the Hybrid sub-ledger changes the mixed distribution but leaves
    ``_committed_events``, the Dirichlet state and the fast ledger untouched, so the
    decoded PUT_BACK top-1 does not move.  This is why S8 alone cannot be read as a
    full late-counter-evidence closure.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    for observation in probe.observed_days()[:12]:
        core.process_transition(probe.transition_for(observation))

    target = core._committed_events[next(reversed(core._committed_events))]
    revision = target.hybrid_revision_id or target.revision_id
    before = probe.action_distribution()
    habit_before = core._habit.canonical_state_hash()
    fast_before = repr(core._fast_action_events)
    committed_before = len(core._committed_events)

    core._hybrid_loop.retract_revision(revision)
    after = probe.action_distribution()

    def top(dist: dict[Any, float]) -> str:
        return str(min(dist, key=lambda key: (-dist[key], str(key))))

    assert before != after
    assert top(before) == top(after)
    assert len(core._committed_events) == committed_before
    assert target.revision_id in core._committed_events
    assert core._habit.canonical_state_hash() == habit_before
    assert repr(core._fast_action_events) == fast_before


# ---------------------------------------------------------------------------
# R6 -- the CIAV negative-observation layering
# ---------------------------------------------------------------------------


def test_a_negative_ciav_observation_computes_a_real_local_posterior() -> None:
    """Correction of round one: the local Bayes update does happen."""

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, _ = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED),
    )
    assert result.ciav_receipt is not None
    owner = probe.case.owner_actor
    primary = result.primary_result.actor_posterior[owner]
    local = result.ciav_receipt.evidence.actor_posterior[owner]
    assert local != pytest.approx(primary)
    assert sum(result.ciav_receipt.evidence.actor_posterior.values()) == pytest.approx(1.0)
