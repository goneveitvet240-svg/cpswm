"""R2 -- fault injection at the formal P0 production entry.

The round-2 independent review showed four complete wrong maintenance payloads
being accepted by the deferred-path nodes, a payload from a *different* runtime
instance at the same head state being accepted, and an injected PCHMP node
carrying evidence hashes from no real transition still producing a
``P0_SAFE_DEFERRED`` run with seven verified operator rows and a pending debt.

This file pins the repair.  Every case enters through
``StructureTwoProductionSystem.process_adaptive_transition`` -- the formal
production entry -- and every case asserts the same no-residue invariant:
no committed trace, no pending debt, no core state change, and no maintenance
context left open that a later call could be checked against.

Frozen basis (``structure_two_adaptive_compute_predeath_v0_1.json``):

* ``hard_safety_kernel.provenance_and_dependency_checks_always_executed`` is
  ``true`` for every legal path.  A dependency check whose reference values come
  from the payload being checked is not a check.
* ``hard_safety_kernel.unexecuted_inference_may_not_be_encoded_as_negative_evidence``
  with ``maximum_unresolved_as_negative_events == 0``.
* ``hard_safety_kernel.maximum_unauthorized_long_term_commits == 0`` and
  ``maximum_provenance_violations == 0``.
* ``legal_paths.P0_SAFE_DEFERRED.semantic_purpose`` -- P0 runs *mandatory*
  maintenance and defers the expensive refinement.  It does not claim the seven
  inference operators ran, and this repair does not make them run.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe,
    FailingTraceSink,
    ProbeTraceSink,
    verify_and_flatten,
)

from cpswm.system import structure_two_execution
from cpswm.system.prototype_spine import CorePrototypeSpine, PrototypeTransition
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import AdaptiveMaintenanceContractError

PREDEATH_CONFIG = Path(
    "configs/project_two_experiments/structure_two_adaptive_compute_predeath_v0_1.json"
)


def _frozen() -> dict[str, Any]:
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        path = candidate / PREDEATH_CONFIG
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise AssertionError("frozen pre-death protocol config not found")


def _p0_features(probe: BackboneWiringProbe):
    return probe.router_features(action_margin=0.9, regime_hazard=0.0)


def _residue(probe: BackboneWiringProbe) -> dict[str, Any]:
    """Everything a failed P0 transaction must leave exactly as it found it."""

    core = probe.system.core
    return {
        "observable_state": probe.observable_state_sha256(),
        "habit": core._habit.canonical_state_hash(),
        "committed": len(core._committed_events),
        "quarantined": len(core._quarantined_events),
        "observed": len(core._observed_events),
        "fast_action_events": repr(core._fast_action_events),
        "active_regime": core.active_regime,
        "action_distribution": probe.action_distribution_sha256(),
        "pending_debts": len(probe.system.pending_adaptive_debts()),
        "debt_ledger": len(probe.system._adaptive_debt_ledger),
        "action_scoped_negatives": len(core._action_scoped_negatives),
        "feedback_bindings": len(core._revision_feedback_bindings),
    }


def _assert_no_success_residue(
    probe: BackboneWiringProbe, before: Mapping[str, Any], sink: Any
) -> None:
    assert _residue(probe) == dict(before)
    assert probe.system.pending_adaptive_debts() == ()
    # Nothing a later reader could mistake for an accepted execution.
    assert sink.trace is None
    assert probe.system.core._adaptive_maintenance_context is None


# ---------------------------------------------------------------------------
# The frozen clauses this file depends on must stay frozen.
# ---------------------------------------------------------------------------


def test_the_frozen_clauses_this_file_depends_on_are_unchanged() -> None:
    frozen = _frozen()
    kernel = frozen["hard_safety_kernel"]
    assert kernel["provenance_and_dependency_checks_always_executed"] is True
    assert kernel["unexecuted_inference_may_not_be_encoded_as_negative_evidence"] is True
    assert kernel["maximum_unauthorized_long_term_commits"] == 0
    assert kernel["maximum_provenance_violations"] == 0
    assert kernel["maximum_unresolved_as_negative_events"] == 0
    p0 = next(path for path in frozen["legal_paths"] if path["path_id"] == "P0_SAFE_DEFERRED")
    assert "deferring expensive refinement" in p0["semantic_purpose"]
    modes = {item["operator"]: item["mode"] for item in p0["operator_modes"]}
    assert modes["pchmp"] == "mandatory_maintenance_executed"
    assert modes["orrer_cheh"] == "deferred_with_valid_debt_certificate"
    assert modes["ciav"] == "deferred_with_valid_debt_certificate"


# ---------------------------------------------------------------------------
# The legal P0 happy path is preserved.
# ---------------------------------------------------------------------------


def test_the_legal_p0_path_still_runs_maintenance_and_commits_nothing() -> None:
    """Control.  The repair must not turn a legal deferred path into a refusal.

    P0 still executes exactly its maintenance nodes and still defers
    ``orrer_cheh`` and ``ciav`` under a debt certificate.  It is deliberately not
    made to run the seven inference operators: that would hide the contract
    question rather than answer it.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_adaptive(transition, features=_p0_features(probe), debt_expiry_steps=1)
    trace, rows = verify_and_flatten(sink)

    assert result.path_selection.selected_path_id == "P0_SAFE_DEFERRED"
    executed = {row.operator: row for row in rows if row.status == "executed"}
    deferred = {row.operator for row in rows if row.status != "executed"}
    assert set(executed) == {"opceu", "pchmp", "cf_bocpd", "ccrr", "rgrc"}
    assert deferred == {"orrer_cheh", "ciav"}
    assert len(rows) == 7
    assert len(probe.system.pending_adaptive_debts()) == 1
    assert len(probe.system.core._committed_events) == 0
    assert trace is not None
    # The maintenance context is execution-scoped: it does not outlive the run.
    assert probe.system.core._adaptive_maintenance_context is None


# ---------------------------------------------------------------------------
# The review's four complete wrong payloads, reproduced exactly.
# ---------------------------------------------------------------------------


def _clean_chain(probe: BackboneWiringProbe, transition: PrototypeTransition):
    core = probe.system.core
    cf = core._adaptive_cf_bocpd_safety_maintenance()
    ccrr = core._adaptive_ccrr_safety_maintenance(cf)
    pchmp = core._adaptive_pchmp_safety_maintenance(transition)
    return cf, ccrr, pchmp


@pytest.mark.parametrize(
    ("case", "target", "mutation", "match"),
    [
        (
            "wrong_evidence_hashes",
            "pchmp",
            {"evidence_content_sha256s": ("f" * 64,)},
            "evidence from another transition",
        ),
        (
            "wrong_evidence_type",
            "pchmp",
            {"evidence_content_sha256s": -999},
            "evidence_content_sha256s is not a content-hash tuple",
        ),
        (
            "wrong_cf_dependency_hash",
            "ccrr",
            {"consumed_cf_bocpd_maintenance_sha256": "f" * 64},
            "a ccrr output this execution never produced",
        ),
        (
            "wrong_cf_dependency_type",
            "ccrr",
            {"consumed_cf_bocpd_maintenance_sha256": None},
            "consumed_cf_bocpd_maintenance_sha256 is not a content hash",
        ),
    ],
)
def test_the_round_two_review_wrong_payloads_are_now_refused(
    case: str, target: str, mutation: dict[str, Any], match: str
) -> None:
    """Pre-fix all four were accepted with ``semantic_guard_unchanged: true``.

    The pre-fix failure mode is the important one: the guard body did not change,
    only the receipt hash did, so a wrong payload produced a *different but still
    accepted* receipt.  Each case is now a refusal, and the refusal is silent on
    state: the guard reads and raises, it never writes.

    Note on ``wrong_cf_dependency_hash``: the declared CF consumption is part of the
    content-bound CCRR body, so rewriting it is caught one step earlier, as a CCRR
    body this execution never produced.  That is a stronger refusal than the
    field-level one, and it is reported as what actually happens rather than as the
    error the counterexample script expected.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    before = _residue(probe)

    with probe.maintenance_context(transition):
        _, ccrr, pchmp = _clean_chain(probe, transition)
        good = core._adaptive_rgrc_debt_guard(pchmp, ccrr)
        assert good["long_term_write_authorized"] is False

        payloads: dict[str, dict[str, Any]] = {"pchmp": dict(pchmp), "ccrr": dict(ccrr)}
        payloads[target].update(mutation)
        with pytest.raises(AdaptiveMaintenanceContractError, match=match):
            core._adaptive_rgrc_debt_guard(payloads["pchmp"], payloads["ccrr"])

    assert _residue(probe) == before
    assert core._adaptive_maintenance_context is None


def test_a_downstream_node_cannot_run_before_its_declared_upstream() -> None:
    """The frozen P0 graph is ``ccrr <- cf_bocpd`` and ``rgrc <- (pchmp, ccrr)``.

    Order is part of the dependency, not only content: a downstream node that runs
    before its declared upstream has nothing real to have consumed.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    before = _residue(probe)

    with probe.maintenance_context(transition):
        # CCRR before CF-BOCPD.
        with pytest.raises(
            AdaptiveMaintenanceContractError,
            match="ccrr declared consumption of cf_bocpd before it ran",
        ):
            core._adaptive_ccrr_safety_maintenance(
                {
                    "maintenance_kind": "cf_bocpd_safety_maintenance",
                    "runtime_execution_id": str(
                        core._adaptive_maintenance_context.runtime_execution_id
                    ),
                    "maintenance_epoch": core._adaptive_maintenance_context.epoch,
                    "observation_count": core.observation_count,
                    "current_snapshot_sha256": None,
                    "posterior_advanced": False,
                }
            )
        # RGRC before PCHMP.
        cf = core._adaptive_cf_bocpd_safety_maintenance()
        ccrr = core._adaptive_ccrr_safety_maintenance(cf)
        pchmp_shaped = {
            "maintenance_kind": "pchmp_safety_maintenance",
            "runtime_execution_id": str(core._adaptive_maintenance_context.runtime_execution_id),
            "maintenance_epoch": core._adaptive_maintenance_context.epoch,
            "evidence_content_sha256s": tuple(content_sha256(item) for item in transition.evidence),
            "unexecuted_inference_encoded_as_negative": False,
            "message_passing_runtime_type": (
                f"{type(core._message_passing).__module__}."
                f"{type(core._message_passing).__qualname__}"
            ),
        }
        with pytest.raises(
            AdaptiveMaintenanceContractError,
            match="rgrc declared consumption of pchmp before it ran",
        ):
            core._adaptive_rgrc_debt_guard(pchmp_shaped, ccrr)

    assert _residue(probe) == before


def test_a_refused_payload_cannot_be_laundered_through_a_second_attempt() -> None:
    """A refusal must not leave the context able to accept the same payload later.

    The pre-fix path let a wrong payload change only the receipt hash, so a caller
    could retry until a hash it wanted came out.  After the repair, the refused
    payload stays refused for the life of the execution, and the *correct* payload
    for that execution still passes -- the check is discriminating, not blanket.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])

    with probe.maintenance_context(transition):
        _, ccrr, pchmp = _clean_chain(probe, transition)
        forged = {**dict(pchmp), "evidence_content_sha256s": ("f" * 64,)}
        for _ in range(3):
            with pytest.raises(AdaptiveMaintenanceContractError):
                core._adaptive_rgrc_debt_guard(forged, ccrr)
        accepted = core._adaptive_rgrc_debt_guard(pchmp, ccrr)

    assert accepted["long_term_write_authorized"] is False
    assert accepted["consumed_pchmp_maintenance_sha256"] == content_sha256(pchmp)
    assert accepted["origin_transition_sha256"] == content_sha256(transition)


# ---------------------------------------------------------------------------
# The review's injected P0 path, at the formal production entry.
# ---------------------------------------------------------------------------


def _injected_pchmp(self: CorePrototypeSpine, transition: PrototypeTransition):
    """The round-2 review's injected node, reproduced byte-for-byte in behaviour.

    It validates the transition, then reports evidence hashes belonging to no real
    transition and omits the execution stamp entirely.
    """

    self._validate_transition(transition)
    return {
        "maintenance_kind": "pchmp_safety_maintenance",
        "evidence_content_sha256s": ("f" * 64,),
        "unexecuted_inference_encoded_as_negative": False,
        "message_passing_runtime_type": (
            f"{type(self._message_passing).__module__}.{type(self._message_passing).__qualname__}"
        ),
    }


def test_an_injected_pchmp_node_is_refused_at_the_p0_binding_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Layer one: the deferred-path seam refuses a callable it did not declare.

    Pre-fix this injection produced ``verified_operator_rows: 7`` and a pending
    debt, because the binding only asked whether the callable matched *its own*
    source file -- which a function in any other module trivially satisfies.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    before = _residue(probe)
    sink = ProbeTraceSink()
    monkeypatch.setattr(CorePrototypeSpine, "_adaptive_pchmp_safety_maintenance", _injected_pchmp)

    with pytest.raises(ValueError, match="does not belong to the bound implementation"):
        probe.run_adaptive(
            transition,
            features=_p0_features(probe),
            debt_expiry_steps=1,
            sink=sink,
        )

    _assert_no_success_residue(probe, before, sink)


def _injected_stamped_pchmp(self: CorePrototypeSpine, transition: PrototypeTransition):
    """A stronger injection: it copies this execution's real stamp.

    The stamp alone must not buy acceptance -- the evidence still belongs to no
    real transition, and that is a semantic contract violation regardless of
    provenance.
    """

    context = self._adaptive_maintenance_context
    if context is None:  # pragma: no cover - the probe always binds one
        raise RuntimeError("injection probe requires a bound maintenance context")
    self._validate_transition(transition)
    return {
        "maintenance_kind": "pchmp_safety_maintenance",
        "runtime_execution_id": str(context.runtime_execution_id),
        "maintenance_epoch": context.epoch,
        "evidence_content_sha256s": ("f" * 64,),
        "unexecuted_inference_encoded_as_negative": False,
        "message_passing_runtime_type": context.message_passing_runtime_type,
    }


def _injected_unrecorded_pchmp(self: CorePrototypeSpine, transition: PrototypeTransition):
    """The strongest injection: byte-identical to what the real node would return.

    Every semantic field and the whole execution stamp are correct.  The one thing
    it cannot fake is the runtime's own record that the node ran, which is the
    point of the repair: a payload cannot certify itself.
    """

    context = self._adaptive_maintenance_context
    if context is None:  # pragma: no cover - the probe always binds one
        raise RuntimeError("injection probe requires a bound maintenance context")
    self._validate_transition(transition)
    return {
        "maintenance_kind": "pchmp_safety_maintenance",
        "runtime_execution_id": str(context.runtime_execution_id),
        "maintenance_epoch": context.epoch,
        "evidence_content_sha256s": context.evidence_content_sha256s,
        "unexecuted_inference_encoded_as_negative": False,
        "message_passing_runtime_type": context.message_passing_runtime_type,
    }


@pytest.mark.parametrize(
    ("case", "injection", "match"),
    [
        (
            "review_injection_unstamped",
            _injected_pchmp,
            "field set drifted from the frozen shape",
        ),
        (
            "stamped_but_foreign_evidence",
            _injected_stamped_pchmp,
            "binds evidence from another transition",
        ),
        (
            "perfect_payload_never_recorded",
            _injected_unrecorded_pchmp,
            "declared consumption of pchmp before it ran in this execution",
        ),
    ],
)
def test_an_injected_pchmp_payload_is_refused_at_the_p0_context_layer(
    case: str,
    injection: Any,
    match: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Layer two, with layer one deliberately neutralized.

    Defense in depth has to be demonstrated, not asserted.  Here the declared-member
    binding check is disabled so each injected node really runs inside a formal
    ``P0_SAFE_DEFERRED`` execution, bound and receipted by the real runtime.

    The three cases climb the ladder: a payload missing the execution stamp, one
    that copies the stamp but carries evidence from no real transition, and one
    that is byte-identical to the correct payload but was produced by a node the
    runtime never recorded.  All three are refused, so a wrong payload cannot go on
    to form an accepted complete receipt chain, and each failed transaction leaves
    no residue readable as success.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    before = _residue(probe)

    monkeypatch.setattr(CorePrototypeSpine, "_adaptive_pchmp_safety_maintenance", injection)
    monkeypatch.setattr(
        structure_two_execution,
        "_require_declared_implementation_member",
        lambda **_: None,
    )

    sink = ProbeTraceSink()
    with pytest.raises(AdaptiveMaintenanceContractError, match=match):
        probe.run_adaptive(
            transition,
            features=_p0_features(probe),
            debt_expiry_steps=1,
            sink=sink,
        )

    _assert_no_success_residue(probe, before, sink)


def test_a_p0_sink_refusal_leaves_no_residue_and_no_open_context() -> None:
    """The other failure shape: the operators pass and the sink refuses the commit.

    P0 issues its debt certificate *before* the maintenance loop, so an aborted P0
    transaction is the strongest available check that the debt ledger rolls back
    with the core -- and that the execution-scoped maintenance context is closed
    even when the failure happens after every node has run.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    before = _residue(probe)
    sink = FailingTraceSink()

    with pytest.raises(RuntimeError, match="refused the commit"):
        probe.run_adaptive(transition, features=_p0_features(probe), debt_expiry_steps=1, sink=sink)

    assert _residue(probe) == before
    assert probe.system.pending_adaptive_debts() == ()
    assert probe.system.core._adaptive_maintenance_context is None


def test_a_legal_p0_run_still_succeeds_after_a_refused_one() -> None:
    """No poisoned state: the runtime is usable again after a refusal.

    A fail-closed check that bricks the runtime would satisfy the letter of R2 and
    break the system, so this pins recoverability explicitly.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    with pytest.raises(RuntimeError, match="refused the commit"):
        probe.run_adaptive(
            transition,
            features=_p0_features(probe),
            debt_expiry_steps=1,
            sink=FailingTraceSink(),
        )

    result, sink = probe.run_adaptive(transition, features=_p0_features(probe), debt_expiry_steps=1)
    _, rows = verify_and_flatten(sink)
    assert result.path_selection.selected_path_id == "P0_SAFE_DEFERRED"
    assert len(rows) == 7
    assert len(probe.system.pending_adaptive_debts()) == 1
    assert len(probe.system.core._committed_events) == 0
