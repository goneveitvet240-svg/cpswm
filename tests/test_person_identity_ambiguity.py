"""First review: identity alternatives and conditional roles on legal geometry."""

from dataclasses import replace
from uuid import uuid4

import pytest
from test_interaction_evidence import frame

from cpswm.perception_mapping.interaction_evidence import (
    CausalInstanceAssociator,
    person_identity_pairs,
    role_readout,
)


def associated(boxes):
    first = frame(boxes=(*boxes, (20, 20, 80, 70)), categories=(*("person",) * len(boxes), "cup"))
    tracker = CausalInstanceAssociator()
    a = tracker.update(first, sequence_id="fixture", media_time=0)
    b = tracker.update(
        frame(
            first,
            boxes=tuple(d.box_xyxy for d in first.candidates),
            categories=tuple(d.category for d in first.candidates),
        ),
        sequence_id="fixture",
        media_time=0.1,
    )
    return a, b


@pytest.mark.parametrize(
    "boxes",
    [
        ((0, 0, 100, 100), (10, 10, 30, 40)),  # body and body part: possible duplicate
        ((0, 0, 55, 90), (45, 0, 100, 90)),  # possible real overlapping people
        ((0, 0, 30, 90), (70, 0, 100, 90)),  # disjoint boxes still not physical identity proof
    ],
)
def test_geometry_keeps_both_identity_branches_and_conditional_roles(boxes):
    a, b = associated(boxes)
    result = role_readout(a, b)
    assert len(result.person_identity_pairs) == 1
    pair = result.person_identity_pairs[0]
    assert pair.hypotheses == ("same_person_multiple_detections", "distinct_people")
    assert pair.status == "UNRESOLVED_GEOMETRY_ONLY"
    assert len(result.role_alternatives) == 2
    assert all(
        r.identity_pair_id == pair.pair_id and r.required_identity_hypothesis == "distinct_people"
        for r in result.role_alternatives
    )
    assert "physical_person_identity_not_resolved" in result.unresolved_reasons
    assert not result.memory_write_authorized
    # No suppression of real overlapping people; same-person alternative is explicit.
    assert len(b.detections) == 3


def test_three_people_pairwise_constraints_are_complete_and_order_invariant():
    a, b = associated(((0, 0, 25, 90), (35, 0, 60, 90), (75, 0, 100, 90)))
    pairs = person_identity_pairs(b)
    assert len(pairs) == 3
    assert len({p.pair_id for p in pairs}) == 3
    assert person_identity_pairs(replace(b, detections=tuple(reversed(b.detections)))) == pairs
    result = role_readout(a, b)
    assert len(result.role_alternatives) == 6
    assert {r.identity_pair_id for r in result.role_alternatives} == {p.pair_id for p in pairs}


def test_identity_break_removes_roles_without_erasing_uncertainty():
    a, b = associated(((0, 0, 55, 90), (45, 0, 100, 90)))
    changed = replace(
        b,
        detections=tuple(
            replace(d, track_id=uuid4(), status="NEW_UNVERIFIED") for d in b.detections
        ),
    )
    result = role_readout(a, changed)
    assert not result.role_alternatives
    assert len(result.person_identity_pairs) == 1
    assert result.person_identity_pairs != role_readout(a, b).person_identity_pairs


def test_duplicate_track_cannot_masquerade_as_two_people():
    _, b = associated(((0, 0, 55, 90), (45, 0, 100, 90)))
    with pytest.raises(ValueError, match="duplicate person track"):
        role_readout(None, replace(b, detections=(b.detections[0], b.detections[0])))


def test_single_person_does_not_invent_pair():
    _, b = associated(((0, 0, 100, 100),))
    result = role_readout(None, b)
    assert not result.person_identity_pairs and not result.role_alternatives
    assert "fewer_than_two_person_candidates" in result.unresolved_reasons
