"""结构一十二条路线的就绪账本: 状态不能超过磁盘上真实存在的东西.

This is the RQ2 / RQ3 / RQ7 / RQ11 / RQ12 half of the audit.  Those four gaps
are module-sized (M05--M12 perception, M20--M22 query, M23--M27 embodiment) and
were *not* implemented in this pass.  What is implemented is the refusal: a
route that has nothing runnable cannot be the source of a number, and a
registry entry that names a file which does not exist is a failure rather than
a comment.
"""

from __future__ import annotations

import pytest

from cpswm.system.progress_ledger.structure_one_routes import (
    EMPIRICAL_CLAIM_THRESHOLD,
    STRUCTURE_ONE_ROUTES,
    RouteClaimError,
    RouteEntry,
    RouteStatus,
    StructureOneRoute,
    assert_empirical_claim,
    assert_route_claim,
    readiness_report,
    verify_registry,
)

# ---------------------------------------------------------------------------
# The registry must describe the tree, not an intention
# ---------------------------------------------------------------------------


def test_every_route_names_modules_and_tests_that_actually_exist() -> None:
    """The failure this guards: a ledger that stops tracking the code.

    Fails the moment a module is renamed or a test deleted without updating the
    entry, which is exactly when a progress summary starts lying.
    """

    problems = verify_registry()
    assert problems == (), "\n".join(problems)


def test_all_twelve_routes_are_registered() -> None:
    assert set(STRUCTURE_ONE_ROUTES) == set(StructureOneRoute)
    assert len(STRUCTURE_ONE_ROUTES) == 12


def test_a_runnable_route_must_name_a_test() -> None:
    """ "Runnable with no test" is a contract with extra steps."""

    with pytest.raises(ValueError, match="names no test"):
        RouteEntry(
            route=StructureOneRoute.RQ2_INSTANCE_IDENTITY,
            title="t",
            audit_judgement="j",
            status=RouteStatus.VERTICAL_SLICE,
            remaining_gap="g",
            next_gate="do the thing",
            modules=("cpswm.contracts",),
            tests=(),
        )


def test_a_started_route_must_name_a_module() -> None:
    with pytest.raises(ValueError, match="names no module"):
        RouteEntry(
            route=StructureOneRoute.RQ3_SCENE_ATTRIBUTES_COMMONSENSE,
            title="t",
            audit_judgement="j",
            status=RouteStatus.CONTRACT_ONLY,
            remaining_gap="g",
            next_gate="do the thing",
        )


def test_every_route_states_what_would_advance_it() -> None:
    """A gap without a gate is a complaint, not a plan.

    Fails if any entry's gate degenerates into "finish the module".
    """

    for entry in STRUCTURE_ONE_ROUTES.values():
        assert entry.next_gate.strip()
        assert "finish the module" not in entry.next_gate.lower()
        assert entry.remaining_gap.strip()


# ---------------------------------------------------------------------------
# What the registry currently says
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route",
    [
        StructureOneRoute.RQ1_SELECTIVE_OBSERVATION,
        StructureOneRoute.RQ4_MOBILITY_PROFILE,
        StructureOneRoute.RQ5_LAYERED_PERSONAL_HABIT,
        StructureOneRoute.RQ6_MULTI_LOCATION_TRANSITION,
        StructureOneRoute.RQ8_MULTI_PERSON_ATTRIBUTION,
        StructureOneRoute.RQ9_NONSTATIONARY_REGIME,
        StructureOneRoute.RQ10_HABIT_PREFERENCE_NORM,
        StructureOneRoute.RQ11_LANGUAGE_QUERY,
    ],
)
def test_no_route_claims_to_be_integrated_or_validated(
    route: StructureOneRoute,
) -> None:
    """Nothing here has been compared to an outside baseline under matched conditions.

    Fails if any route is promoted without that comparison, which is the same
    error ``innovation_ledger`` guards for the seven operators.
    """

    entry = STRUCTURE_ONE_ROUTES[route]
    assert entry.status is not RouteStatus.VALIDATED
    assert entry.status is not RouteStatus.INTEGRATED


@pytest.mark.parametrize(
    "route",
    [
        StructureOneRoute.RQ3_SCENE_ATTRIBUTES_COMMONSENSE,
        StructureOneRoute.RQ7_HIDDEN_EVENT,
        StructureOneRoute.RQ12_EMBODIED_LOOP,
    ],
)
def test_the_three_contract_only_routes_cannot_produce_a_number(
    route: StructureOneRoute,
) -> None:
    """These were not implemented in this pass and must not read as if they were."""

    entry = STRUCTURE_ONE_ROUTES[route]
    assert not entry.supports_empirical_claim
    with pytest.raises(RouteClaimError, match="no empirical statement"):
        assert_empirical_claim(route)


def test_rq7_is_still_a_bypass_experiment() -> None:
    """The audit's exact wording: CHEH 输出必须成为结构一正式输入, 而非旁路实验.

    Fails if RQ7 is promoted before that channel exists, which would let a
    CHEH result be reported as a 结构一 result.
    """

    entry = STRUCTURE_ONE_ROUTES[StructureOneRoute.RQ7_HIDDEN_EVENT]
    assert entry.status is RouteStatus.CONTRACT_ONLY
    assert "INFERRED_EVENT" in entry.next_gate


def test_rq12_records_the_shared_root_cause() -> None:
    entry = STRUCTURE_ONE_ROUTES[StructureOneRoute.RQ12_EMBODIED_LOOP]
    assert "argmax" in entry.note


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------


def test_a_claim_above_the_declared_status_is_refused() -> None:
    with pytest.raises(RouteClaimError, match="cannot be claimed as"):
        assert_route_claim(
            StructureOneRoute.RQ3_SCENE_ATTRIBUTES_COMMONSENSE,
            RouteStatus.VERTICAL_SLICE,
        )


def test_a_claim_at_or_below_the_declared_status_passes() -> None:
    assert_route_claim(StructureOneRoute.RQ8_MULTI_PERSON_ATTRIBUTION, RouteStatus.VERTICAL_SLICE)
    assert_route_claim(StructureOneRoute.RQ8_MULTI_PERSON_ATTRIBUTION, RouteStatus.CONTRACT_ONLY)


def test_the_refusal_message_carries_the_gap_and_the_gate() -> None:
    """A refusal that does not say what to do next gets worked around."""

    with pytest.raises(RouteClaimError) as error:
        assert_empirical_claim(StructureOneRoute.RQ3_SCENE_ATTRIBUTES_COMMONSENSE)
    assert "Next gate" in str(error.value)


def test_the_empirical_threshold_is_the_runnable_boundary() -> None:
    assert EMPIRICAL_CLAIM_THRESHOLD is RouteStatus.VERTICAL_SLICE


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def test_the_report_leads_with_what_is_missing() -> None:
    report = readiness_report()
    assert report["route_count"] == 12
    assert report["routes_that_cannot_support_a_number"]
    assert sum(report["status_counts"].values()) == 12
    assert report["registry_version"].startswith("structure-one-routes@")


def test_the_report_is_deterministic() -> None:
    assert readiness_report() == readiness_report()
